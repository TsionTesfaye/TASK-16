"""Buyback ticket lifecycle service.

Manages intake, QC handoff, variance flows, completion, refund, and
cancellation — all with strict state machine enforcement and audit logging.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from ..enums.ticket_status import TicketStatus
from ..enums.user_role import UserRole
from ..enums.variance_approval_status import VarianceApprovalStatus
from ..models.buyback_ticket import BuybackTicket
from ..models.variance_approval_request import VarianceApprovalRequest
from ..repositories.buyback_ticket_repository import BuybackTicketRepository
from ..repositories.qc_inspection_repository import QCInspectionRepository
from ..repositories.variance_approval_request_repository import VarianceApprovalRequestRepository
from ..security.crypto import decrypt_field, encrypt_field
from ._authz import enforce_store_access
from ._tx import atomic
from .audit_service import AuditService
from .auth_service import AuthService
from .pricing_service import PricingService

logger = logging.getLogger(__name__)

# Valid ticket state transitions
VALID_TRANSITIONS = {
    TicketStatus.INTAKE_OPEN: {
        TicketStatus.AWAITING_QC,
        TicketStatus.CANCELED,
    },
    TicketStatus.AWAITING_QC: {
        TicketStatus.VARIANCE_PENDING_CONFIRMATION,
        TicketStatus.COMPLETED,
        TicketStatus.CANCELED,
    },
    TicketStatus.VARIANCE_PENDING_CONFIRMATION: {
        TicketStatus.VARIANCE_PENDING_SUPERVISOR,
        TicketStatus.CANCELED,
    },
    TicketStatus.VARIANCE_PENDING_SUPERVISOR: {
        TicketStatus.COMPLETED,
        TicketStatus.CANCELED,
    },
    TicketStatus.COMPLETED: {
        TicketStatus.REFUND_PENDING_SUPERVISOR,
    },
    TicketStatus.REFUND_PENDING_SUPERVISOR: {
        TicketStatus.REFUNDED,
        TicketStatus.COMPLETED,  # rejected refund returns to completed
    },
    TicketStatus.REFUNDED: set(),
    TicketStatus.CANCELED: set(),
}


class TicketService:
    def __init__(
        self,
        ticket_repo: BuybackTicketRepository,
        variance_repo: VarianceApprovalRequestRepository,
        pricing_service: PricingService,
        audit_service: AuditService,
        auth_service: AuthService,
        qc_repo: QCInspectionRepository = None,
    ):
        if qc_repo is None:
            raise ValueError("qc_repo is required — QC enforcement cannot be bypassed")
        if auth_service is None:
            raise ValueError("auth_service is required — approvals must verify passwords")
        self.ticket_repo = ticket_repo
        self.variance_repo = variance_repo
        self.pricing_service = pricing_service
        self.audit_service = audit_service
        self.auth_service = auth_service
        self.qc_repo = qc_repo

    def _verify_approver_password(self, user_id: int, password: Optional[str]) -> None:
        """Reject missing or incorrect passwords on any approval path."""
        if not password:
            raise ValueError("Password is required for approval")
        try:
            ok = self.auth_service.verify_password_for_approval(user_id, password)
        except PermissionError:
            raise
        except ValueError:
            raise
        if not ok:
            raise PermissionError("Invalid password")

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _validate_transition(self, current: str, target: str) -> None:
        allowed = VALID_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise ValueError(
                f"Invalid ticket transition: {current} -> {target}"
            )

    def _require_role(self, user_role: str, allowed_roles: set) -> None:
        if user_role not in allowed_roles:
            raise PermissionError(
                f"Role '{user_role}' is not authorized for this action"
            )

    def create_ticket(
        self,
        store_id: int,
        user_id: int,
        user_role: str,
        username: str,
        customer_name: str,
        clothing_category: str,
        condition_grade: str,
        estimated_weight_lbs: float,
        actor_store_id: Optional[int] = None,
        customer_phone_preference: str = "standard_calls",
        customer_phone: Optional[str] = None,
        customer_phone_ciphertext: Optional[bytes] = None,
        customer_phone_iv: Optional[bytes] = None,
        customer_phone_last4: Optional[str] = None,
        now_local: Optional[str] = None,
    ) -> BuybackTicket:
        self._require_role(user_role, {
            UserRole.FRONT_DESK_AGENT, UserRole.ADMINISTRATOR,
        })
        # Cross-store write guard — agent cannot create tickets in a
        # store they don't belong to.
        enforce_store_access(
            entity_store_id=store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role,
            entity_name="ticket",
        )

        if not customer_name or not customer_name.strip():
            raise ValueError("Customer name is required")
        if not clothing_category or not clothing_category.strip():
            raise ValueError("Clothing category is required")
        if not condition_grade or not condition_grade.strip():
            raise ValueError("Condition grade is required")
        if estimated_weight_lbs <= 0:
            raise ValueError("Estimated weight must be greater than zero")

        # Phone capture: accept the FULL number, encrypt at rest with
        # AES-256-GCM, persist only the ciphertext + iv + a derived
        # last-4 mask. The plaintext is never stored.
        if customer_phone:
            digits = "".join(ch for ch in str(customer_phone) if ch.isdigit())
            if len(digits) < 4:
                raise ValueError("Phone number must contain at least 4 digits")
            ciphertext, iv = encrypt_field(digits)
            customer_phone_ciphertext = ciphertext
            customer_phone_iv = iv
            customer_phone_last4 = digits[-4:]

        calc = self.pricing_service.calculate_payout(
            store_id=store_id,
            category=clothing_category,
            condition_grade=condition_grade,
            weight_lbs=estimated_weight_lbs,
            now_local=now_local,
        )

        with atomic(self.ticket_repo.conn):
            ticket = BuybackTicket(
                store_id=store_id,
                created_by_user_id=user_id,
                customer_name=customer_name.strip(),
                customer_phone_ciphertext=customer_phone_ciphertext,
                customer_phone_iv=customer_phone_iv,
                customer_phone_last4=customer_phone_last4,
                customer_phone_preference=customer_phone_preference,
                clothing_category=clothing_category.strip(),
                condition_grade=condition_grade.strip(),
                estimated_weight_lbs=estimated_weight_lbs,
                estimated_base_rate=calc["base_rate"],
                estimated_bonus_pct=calc["bonus_pct"],
                estimated_payout=calc["capped_amount"],
                estimated_cap_applied=calc["cap_applied"],
                status=TicketStatus.INTAKE_OPEN,
            )
            ticket = self.ticket_repo.create(ticket)

            self.pricing_service.persist_snapshot(
                ticket_id=ticket.id,
                calculation_type="estimated",
                calc_result={**calc, "weight_lbs": estimated_weight_lbs},
            )

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="ticket.created",
                object_type="buyback_ticket",
                object_id=str(ticket.id),
                after={"status": ticket.status, "estimated_payout": ticket.estimated_payout},
            )

        return ticket

    def submit_for_qc(
        self,
        ticket_id: int,
        user_id: int,
        username: str,
        actor_store_id: Optional[int] = None,
        user_role: Optional[str] = None,
    ) -> BuybackTicket:
        ticket = self.ticket_repo.get_by_id(ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")

        enforce_store_access(
            entity_store_id=ticket.store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role or "",
            entity_name="ticket",
        )

        self._validate_transition(ticket.status, TicketStatus.AWAITING_QC)

        before_status = ticket.status
        with atomic(self.ticket_repo.conn):
            ticket.status = TicketStatus.AWAITING_QC
            ticket = self.ticket_repo.update(ticket)

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="ticket.submitted_for_qc",
                object_type="buyback_ticket",
                object_id=str(ticket.id),
                before={"status": before_status},
                after={"status": ticket.status},
            )

        return ticket

    QC_FINAL_ROLES = {
        UserRole.QC_INSPECTOR,
        UserRole.ADMINISTRATOR,
    }

    def record_qc_and_compute_final(
        self,
        ticket_id: int,
        actual_weight_lbs: Optional[float],
        user_id: int,
        username: str,
        actor_store_id: Optional[int] = None,
        user_role: Optional[str] = None,
        now_local: Optional[str] = None,
    ) -> dict:
        """Compute final payout from the persisted QC inspection weight.

        The payout is ALWAYS derived from the QC inspection's
        `actual_weight_lbs` — never from the request body.  If the
        caller passes an `actual_weight_lbs` value it MUST match the
        inspection record; a mismatch is rejected so no one can
        silently override the QC-measured weight.

        Returns dict with ticket, calc result, and whether variance approval needed.
        """
        self._require_role(user_role or "", self.QC_FINAL_ROLES)

        ticket = self.ticket_repo.get_by_id(ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")
        enforce_store_access(
            entity_store_id=ticket.store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role or "",
            entity_name="ticket",
        )
        if ticket.status != TicketStatus.AWAITING_QC:
            raise ValueError(f"Ticket must be in awaiting_qc state, got {ticket.status}")

        inspection = self.qc_repo.get_by_ticket(ticket_id)
        if not inspection:
            raise ValueError("QC inspection must be recorded before ticket can proceed")

        # The QC inspection is the single source of truth for the
        # actual weight.  If the caller supplied a weight it must
        # match — otherwise reject to prevent silent overrides.
        qc_weight = inspection.actual_weight_lbs
        if actual_weight_lbs is not None and actual_weight_lbs != qc_weight:
            raise ValueError(
                f"Provided weight ({actual_weight_lbs}) does not match "
                f"QC inspection weight ({qc_weight})"
            )

        calc = self.pricing_service.calculate_payout(
            store_id=ticket.store_id,
            category=ticket.clothing_category,
            condition_grade=ticket.condition_grade,
            weight_lbs=qc_weight,
            now_local=now_local,
        )

        ticket.actual_weight_lbs = qc_weight
        ticket.actual_base_rate = calc["base_rate"]
        ticket.actual_bonus_pct = calc["bonus_pct"]
        ticket.final_payout = calc["capped_amount"]
        ticket.final_cap_applied = calc["cap_applied"]

        (approval_required, variance_amount, variance_pct,
         threshold_amount, threshold_pct) = self.pricing_service.check_variance(
            ticket.estimated_payout, ticket.final_payout, ticket.store_id
        )

        ticket.variance_amount = variance_amount
        ticket.variance_pct = variance_pct

        if approval_required:
            ticket.status = TicketStatus.VARIANCE_PENDING_CONFIRMATION
        else:
            ticket.status = TicketStatus.COMPLETED
            ticket.completed_at = self._now_utc()

        with atomic(self.ticket_repo.conn):
            self.pricing_service.persist_snapshot(
                ticket_id=ticket.id,
                calculation_type="actual",
                calc_result={**calc, "weight_lbs": qc_weight},
            )

            ticket = self.ticket_repo.update(ticket)

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="ticket.qc_completed",
                object_type="buyback_ticket",
                object_id=str(ticket.id),
                before={"estimated_payout": ticket.estimated_payout},
                after={
                    "final_payout": ticket.final_payout,
                    "status": ticket.status,
                    "variance_amount": variance_amount,
                    "approval_required": approval_required,
                },
            )

        return {
            "ticket": ticket,
            "calc": calc,
            "approval_required": approval_required,
            "variance_amount": variance_amount,
            "variance_pct": variance_pct,
        }

    def confirm_variance(
        self,
        ticket_id: int,
        user_id: int,
        username: str,
        confirmation_note: str,
        actor_store_id: Optional[int] = None,
        user_role: Optional[str] = None,
    ) -> VarianceApprovalRequest:
        ticket = self.ticket_repo.get_by_id(ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")
        enforce_store_access(
            entity_store_id=ticket.store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role or "",
            entity_name="ticket",
        )
        if ticket.status != TicketStatus.VARIANCE_PENDING_CONFIRMATION:
            raise ValueError("Ticket is not pending variance confirmation")
        if not confirmation_note or not confirmation_note.strip():
            raise ValueError("Confirmation note is required")

        settings = self.pricing_service._get_settings(ticket.store_id)
        pct_threshold_amount = round(
            ticket.estimated_payout * settings.variance_pct_threshold / 100.0, 2
        )

        with atomic(self.ticket_repo.conn):
            request = VarianceApprovalRequest(
                ticket_id=ticket_id,
                requested_by_user_id=user_id,
                variance_amount=ticket.variance_amount or 0.0,
                variance_pct=ticket.variance_pct or 0.0,
                threshold_amount=settings.variance_amount_threshold,
                threshold_pct=settings.variance_pct_threshold,
                confirmation_note=confirmation_note.strip(),
                status=VarianceApprovalStatus.PENDING,
            )
            request = self.variance_repo.create(request)

            ticket.status = TicketStatus.VARIANCE_PENDING_SUPERVISOR
            self.ticket_repo.update(ticket)

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="ticket.variance_confirmed",
                object_type="buyback_ticket",
                object_id=str(ticket.id),
                after={
                    "variance_amount": request.variance_amount,
                    "approval_request_id": request.id,
                },
            )

        return request

    def approve_variance(
        self,
        approval_request_id: int,
        approver_user_id: int,
        approver_username: str,
        approver_role: str,
        password: str,
        approver_store_id: Optional[int] = None,
    ) -> BuybackTicket:
        self._require_role(approver_role, {
            UserRole.SHIFT_SUPERVISOR, UserRole.OPERATIONS_MANAGER,
            UserRole.ADMINISTRATOR,
        })

        request = self.variance_repo.get_by_id(approval_request_id)
        if not request:
            raise ValueError("Approval request not found")
        if request.status != VarianceApprovalStatus.PENDING:
            raise ValueError(f"Approval request is not pending, status: {request.status}")
        if request.requested_by_user_id == approver_user_id:
            raise PermissionError("Self-approval is forbidden")

        # Real password verification — a boolean flag from the client
        # can be trivially forged and is NOT a substitute for checking
        # the hash against the stored bcrypt value.
        self._verify_approver_password(approver_user_id, password)

        ticket = self.ticket_repo.get_by_id(request.ticket_id)
        if not ticket:
            raise ValueError("Associated ticket not found")
        enforce_store_access(
            entity_store_id=ticket.store_id,
            actor_store_id=approver_store_id,
            actor_role=approver_role,
            entity_name="ticket",
        )
        if ticket.status != TicketStatus.VARIANCE_PENDING_SUPERVISOR:
            raise ValueError("Ticket is not pending supervisor approval")

        now = self._now_utc()
        # Atomic multi-step execution. If any step fails, atomic() rolls
        # back the entire block BEFORE the exception leaves the service,
        # so no partial state can be committed even if the route catches
        # the exception and returns a 4xx response.
        with atomic(self.ticket_repo.conn):
            if not self.variance_repo.try_execute_approval(
                approval_request_id, approver_user_id, now,
            ):
                raise ValueError(
                    "Approval request was already processed "
                    "(concurrent or duplicate request)"
                )

            if not self.ticket_repo.try_transition_status(
                ticket.id,
                from_status=TicketStatus.VARIANCE_PENDING_SUPERVISOR,
                to_status=TicketStatus.COMPLETED,
                completed_at=now,
            ):
                raise ValueError(
                    "Ticket state changed by another request during approval"
                )

            # Reload the ticket so the returned object reflects the new state.
            ticket = self.ticket_repo.get_by_id(ticket.id)

            self.audit_service.log(
                actor_user_id=approver_user_id,
                actor_username=approver_username,
                action_code="ticket.variance_approved",
                object_type="buyback_ticket",
                object_id=str(ticket.id),
                before={"status": TicketStatus.VARIANCE_PENDING_SUPERVISOR},
                after={
                    "status": ticket.status,
                    "final_payout": ticket.final_payout,
                    "approver": approver_username,
                    "approval_request_id": approval_request_id,
                },
            )

        logger.info(
            "Variance approved: ticket=%d request=%d approver=%s",
            ticket.id, approval_request_id, approver_username,
        )
        return ticket

    def reject_variance(
        self,
        approval_request_id: int,
        approver_user_id: int,
        approver_username: str,
        approver_role: str,
        reason: str,
        approver_store_id: Optional[int] = None,
    ) -> VarianceApprovalRequest:
        self._require_role(approver_role, {
            UserRole.SHIFT_SUPERVISOR, UserRole.OPERATIONS_MANAGER,
            UserRole.ADMINISTRATOR,
        })

        request = self.variance_repo.get_by_id(approval_request_id)
        if not request:
            raise ValueError("Approval request not found")
        if request.status != VarianceApprovalStatus.PENDING:
            raise ValueError("Approval request is not pending")
        if request.requested_by_user_id == approver_user_id:
            raise PermissionError("Self-rejection of own request is forbidden")

        # Cross-store authorization — supervisors may only reject
        # variance requests on tickets in their own store.
        ref_ticket = self.ticket_repo.get_by_id(request.ticket_id)
        if ref_ticket:
            enforce_store_access(
                entity_store_id=ref_ticket.store_id,
                actor_store_id=approver_store_id,
                actor_role=approver_role,
                entity_name="ticket",
            )

        with atomic(self.ticket_repo.conn):
            request.approver_user_id = approver_user_id
            request.status = VarianceApprovalStatus.REJECTED
            request.rejected_at = self._now_utc()
            request.confirmation_note = reason
            self.variance_repo.update(request)

            ticket = self.ticket_repo.get_by_id(request.ticket_id)
            if ticket and ticket.status == TicketStatus.VARIANCE_PENDING_SUPERVISOR:
                ticket.status = TicketStatus.CANCELED
                self.ticket_repo.update(ticket)

            self.audit_service.log(
                actor_user_id=approver_user_id,
                actor_username=approver_username,
                action_code="ticket.variance_rejected",
                object_type="buyback_ticket",
                object_id=str(request.ticket_id),
                after={"reason": reason, "approval_request_id": request.id},
            )

        return request

    def initiate_refund(
        self,
        ticket_id: int,
        user_id: int,
        username: str,
        user_role: str,
        actor_store_id: Optional[int] = None,
        refund_amount: Optional[float] = None,
        reason: Optional[str] = None,
    ) -> BuybackTicket:
        self._require_role(user_role, {
            UserRole.FRONT_DESK_AGENT, UserRole.OPERATIONS_MANAGER,
            UserRole.ADMINISTRATOR,
        })

        ticket = self.ticket_repo.get_by_id(ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")
        enforce_store_access(
            entity_store_id=ticket.store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role,
            entity_name="ticket",
        )
        self._validate_transition(ticket.status, TicketStatus.REFUND_PENDING_SUPERVISOR)

        if refund_amount is not None:
            if refund_amount <= 0:
                raise ValueError("Refund amount must be positive")
            if refund_amount > (ticket.final_payout or 0):
                raise ValueError("Refund amount cannot exceed final payout")
            if not reason or not reason.strip():
                raise ValueError("Reason is required for partial refund")

        before_status = ticket.status
        with atomic(self.ticket_repo.conn):
            ticket.status = TicketStatus.REFUND_PENDING_SUPERVISOR
            ticket.refund_amount = (
                refund_amount if refund_amount is not None else ticket.final_payout
            )
            ticket.refund_initiated_by_user_id = user_id
            ticket = self.ticket_repo.update(ticket)

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="ticket.refund_initiated",
                object_type="buyback_ticket",
                object_id=str(ticket.id),
                before={"status": before_status, "final_payout": ticket.final_payout},
                after={
                    "status": ticket.status,
                    "refund_amount": ticket.refund_amount,
                    "reason": reason,
                },
            )

        return ticket

    def approve_refund(
        self,
        ticket_id: int,
        approver_user_id: int,
        approver_username: str,
        approver_role: str,
        password: str,
        approver_store_id: Optional[int] = None,
    ) -> BuybackTicket:
        self._require_role(approver_role, {
            UserRole.SHIFT_SUPERVISOR, UserRole.OPERATIONS_MANAGER,
            UserRole.ADMINISTRATOR,
        })

        ticket = self.ticket_repo.get_by_id(ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")
        enforce_store_access(
            entity_store_id=ticket.store_id,
            actor_store_id=approver_store_id,
            actor_role=approver_role,
            entity_name="ticket",
        )
        if ticket.status != TicketStatus.REFUND_PENDING_SUPERVISOR:
            raise ValueError("Ticket is not pending refund approval")
        if ticket.refund_initiated_by_user_id == approver_user_id:
            raise PermissionError("Refund initiator cannot approve their own refund")

        self._verify_approver_password(approver_user_id, password)

        now = self._now_utc()
        before_status = ticket.status
        # Atomic conditional transition — prevents double approval of the
        # same refund under concurrent supervisor clicks.
        with atomic(self.ticket_repo.conn):
            if not self.ticket_repo.try_transition_status(
                ticket.id,
                from_status=TicketStatus.REFUND_PENDING_SUPERVISOR,
                to_status=TicketStatus.REFUNDED,
                refunded_at=now,
            ):
                raise ValueError(
                    "Refund was already processed (concurrent or duplicate request)"
                )
            ticket = self.ticket_repo.get_by_id(ticket.id)

            self.audit_service.log(
                actor_user_id=approver_user_id,
                actor_username=approver_username,
                action_code="ticket.refund_approved",
                object_type="buyback_ticket",
                object_id=str(ticket.id),
                before={"status": before_status, "final_payout": ticket.final_payout},
                after={
                    "status": ticket.status,
                    "refund_amount": ticket.refund_amount,
                    "refunded_at": ticket.refunded_at,
                },
            )

        return ticket

    def reject_refund(
        self,
        ticket_id: int,
        approver_user_id: int,
        approver_username: str,
        approver_role: str,
        reason: str,
        approver_store_id: Optional[int] = None,
    ) -> BuybackTicket:
        self._require_role(approver_role, {
            UserRole.SHIFT_SUPERVISOR, UserRole.OPERATIONS_MANAGER,
            UserRole.ADMINISTRATOR,
        })

        ticket = self.ticket_repo.get_by_id(ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")
        enforce_store_access(
            entity_store_id=ticket.store_id,
            actor_store_id=approver_store_id,
            actor_role=approver_role,
            entity_name="ticket",
        )
        if ticket.status != TicketStatus.REFUND_PENDING_SUPERVISOR:
            raise ValueError("Ticket is not pending refund approval")

        with atomic(self.ticket_repo.conn):
            ticket.status = TicketStatus.COMPLETED
            ticket = self.ticket_repo.update(ticket)

            self.audit_service.log(
                actor_user_id=approver_user_id,
                actor_username=approver_username,
                action_code="ticket.refund_rejected",
                object_type="buyback_ticket",
                object_id=str(ticket.id),
                after={"status": ticket.status, "reason": reason},
            )

        return ticket

    # -- Phone "dial" action: decrypt only when authorized --

    DIAL_ALLOWED_ROLES = {
        UserRole.FRONT_DESK_AGENT,
        UserRole.SHIFT_SUPERVISOR,
        UserRole.OPERATIONS_MANAGER,
        UserRole.ADMINISTRATOR,
    }

    def get_ticket_phone_for_dial(
        self,
        ticket_id: int,
        user_id: int,
        username: str,
        user_role: str,
        actor_store_id: Optional[int] = None,
    ) -> dict:
        """Decrypt and return the customer phone number for an
        authorized caller.

        Default API responses mask phone fields (last4 only). This
        method is the ONLY path that returns the plaintext, and it:
          - rejects callers without an allowed role,
          - rejects cross-store access,
          - writes an audit entry that records WHO dialed WHICH ticket.

        The plaintext is never logged.
        """
        if user_role not in self.DIAL_ALLOWED_ROLES:
            raise PermissionError(
                f"Role '{user_role}' is not authorized to dial customer phones"
            )

        ticket = self.ticket_repo.get_by_id(ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")
        enforce_store_access(
            entity_store_id=ticket.store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role,
            entity_name="ticket",
        )

        if not ticket.customer_phone_ciphertext or not ticket.customer_phone_iv:
            raise ValueError("Ticket has no stored phone number")

        plaintext = decrypt_field(
            ticket.customer_phone_ciphertext, ticket.customer_phone_iv,
        )
        if plaintext is None:
            # Decryption failed (tamper / key mismatch). Don't leak details.
            raise ValueError("Phone number could not be decrypted")

        # Audit the dial — supervisors must be able to see who pulled
        # the plaintext for which customer.
        self.audit_service.log(
            actor_user_id=user_id,
            actor_username=username,
            action_code="ticket.phone_dialed",
            object_type="buyback_ticket",
            object_id=str(ticket.id),
            after={"last4": ticket.customer_phone_last4},
        )

        return {
            "ticket_id": ticket.id,
            "phone": plaintext,
            "last4": ticket.customer_phone_last4,
        }

    def cancel_ticket(
        self,
        ticket_id: int,
        user_id: int,
        username: str,
        user_role: str,
        reason: str,
        actor_store_id: Optional[int] = None,
    ) -> BuybackTicket:
        ticket = self.ticket_repo.get_by_id(ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")
        enforce_store_access(
            entity_store_id=ticket.store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role,
            entity_name="ticket",
        )

        self._validate_transition(ticket.status, TicketStatus.CANCELED)

        # Cancellation from variance states requires supervisor
        if ticket.status in (
            TicketStatus.VARIANCE_PENDING_CONFIRMATION,
            TicketStatus.VARIANCE_PENDING_SUPERVISOR,
        ):
            self._require_role(user_role, {
                UserRole.SHIFT_SUPERVISOR, UserRole.OPERATIONS_MANAGER,
                UserRole.ADMINISTRATOR,
            })

        if not reason or not reason.strip():
            raise ValueError("Cancellation reason is required")

        before_status = ticket.status
        with atomic(self.ticket_repo.conn):
            ticket.status = TicketStatus.CANCELED
            ticket = self.ticket_repo.update(ticket)

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="ticket.canceled",
                object_type="buyback_ticket",
                object_id=str(ticket.id),
                before={"status": before_status},
                after={"status": ticket.status, "reason": reason},
            )

        return ticket
