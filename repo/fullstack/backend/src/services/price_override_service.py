"""Price override service — manual payout adjustments under dual control.

The deterministic pricing engine in `PricingService` handles 100% of
normal payouts. This service is the ONLY supported escape hatch for
operator-initiated overrides, and it enforces the same dual-control
guarantees the rest of the system uses:

  - requester != approver (self-approval forbidden)
  - approver re-enters their password (real bcrypt verify, not a flag)
  - approval and execution are atomic conditional UPDATEs so duplicate
    clicks under race conditions cannot apply the override twice
  - every state transition is audit-logged
  - cross-store access is rejected by enforce_store_access
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from ..enums.user_role import UserRole
from ..models.price_override_request import PriceOverrideRequest
from ..repositories.buyback_ticket_repository import BuybackTicketRepository
from ..repositories.price_override_request_repository import PriceOverrideRequestRepository
from ._authz import enforce_store_access
from ._tx import atomic
from .audit_service import AuditService
from .auth_service import AuthService

logger = logging.getLogger(__name__)

REQUEST_ROLES = {
    UserRole.FRONT_DESK_AGENT,
    UserRole.SHIFT_SUPERVISOR,
    UserRole.OPERATIONS_MANAGER,
    UserRole.ADMINISTRATOR,
}

APPROVER_ROLES = {
    UserRole.SHIFT_SUPERVISOR,
    UserRole.OPERATIONS_MANAGER,
    UserRole.ADMINISTRATOR,
}


class PriceOverrideService:
    def __init__(
        self,
        override_repo: PriceOverrideRequestRepository,
        ticket_repo: BuybackTicketRepository,
        audit_service: AuditService,
        auth_service: AuthService,
    ):
        if auth_service is None:
            raise ValueError("auth_service is required — overrides must verify passwords")
        self.override_repo = override_repo
        self.ticket_repo = ticket_repo
        self.audit_service = audit_service
        self.auth_service = auth_service

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _verify_approver_password(self, user_id: int, password: Optional[str]) -> None:
        if not password:
            raise ValueError("Password is required for approval")
        if not self.auth_service.verify_password_for_approval(user_id, password):
            raise PermissionError("Invalid password")

    # -- request --

    def request_price_override(
        self,
        ticket_id: int,
        proposed_payout: float,
        reason: str,
        user_id: int,
        username: str,
        user_role: str,
        actor_store_id: Optional[int] = None,
    ) -> PriceOverrideRequest:
        if user_role not in REQUEST_ROLES:
            raise PermissionError(
                f"Role '{user_role}' cannot request a price override"
            )
        if proposed_payout is None or proposed_payout < 0:
            raise ValueError("Proposed payout must be a non-negative number")
        if not reason or not reason.strip():
            raise ValueError("Reason is required for a price override")

        ticket = self.ticket_repo.get_by_id(ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")
        enforce_store_access(
            entity_store_id=ticket.store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role,
            entity_name="ticket",
        )

        original = ticket.final_payout if ticket.final_payout is not None else ticket.estimated_payout

        with atomic(self.override_repo.conn):
            request = PriceOverrideRequest(
                ticket_id=ticket_id,
                store_id=ticket.store_id,
                requested_by_user_id=user_id,
                original_payout=float(original or 0.0),
                proposed_payout=float(proposed_payout),
                reason=reason.strip(),
                status="pending",
            )
            request = self.override_repo.create(request)

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="price_override.requested",
                object_type="price_override_request",
                object_id=str(request.id),
                after={
                    "ticket_id": ticket_id,
                    "original_payout": request.original_payout,
                    "proposed_payout": request.proposed_payout,
                    "reason": request.reason,
                },
            )

        return request

    # -- approve --

    def approve_price_override(
        self,
        request_id: int,
        approver_user_id: int,
        approver_username: str,
        approver_role: str,
        password: str,
        approver_store_id: Optional[int] = None,
    ) -> PriceOverrideRequest:
        if approver_role not in APPROVER_ROLES:
            raise PermissionError(
                f"Role '{approver_role}' cannot approve a price override"
            )

        request = self.override_repo.get_by_id(request_id)
        if not request:
            raise ValueError("Price override request not found")
        enforce_store_access(
            entity_store_id=request.store_id,
            actor_store_id=approver_store_id,
            actor_role=approver_role,
            entity_name="price_override_request",
        )
        if request.status != "pending":
            raise ValueError(
                f"Request is not pending, status: {request.status}"
            )
        if request.requested_by_user_id == approver_user_id:
            raise PermissionError("Self-approval of price override is forbidden")

        # Real password verification — boolean flags from the client are
        # never sufficient.
        self._verify_approver_password(approver_user_id, password)

        now = self._now_utc()
        with atomic(self.override_repo.conn):
            if not self.override_repo.try_approve(request_id, approver_user_id, now):
                raise ValueError(
                    "Price override was already processed (concurrent or duplicate request)"
                )
            request = self.override_repo.get_by_id(request_id)

            self.audit_service.log(
                actor_user_id=approver_user_id,
                actor_username=approver_username,
                action_code="price_override.approved",
                object_type="price_override_request",
                object_id=str(request.id),
                before={"status": "pending"},
                after={
                    "status": request.status,
                    "approver": approver_username,
                    "proposed_payout": request.proposed_payout,
                },
            )

        return request

    # -- reject --

    def reject_price_override(
        self,
        request_id: int,
        approver_user_id: int,
        approver_username: str,
        approver_role: str,
        reason: str,
        approver_store_id: Optional[int] = None,
    ) -> PriceOverrideRequest:
        if approver_role not in APPROVER_ROLES:
            raise PermissionError(
                f"Role '{approver_role}' cannot reject a price override"
            )

        request = self.override_repo.get_by_id(request_id)
        if not request:
            raise ValueError("Price override request not found")
        enforce_store_access(
            entity_store_id=request.store_id,
            actor_store_id=approver_store_id,
            actor_role=approver_role,
            entity_name="price_override_request",
        )
        if request.status != "pending":
            raise ValueError(f"Request is not pending, status: {request.status}")

        now = self._now_utc()
        with atomic(self.override_repo.conn):
            if not self.override_repo.try_reject(request_id, approver_user_id, now):
                raise ValueError(
                    "Price override was already processed (concurrent or duplicate request)"
                )
            request = self.override_repo.get_by_id(request_id)

            self.audit_service.log(
                actor_user_id=approver_user_id,
                actor_username=approver_username,
                action_code="price_override.rejected",
                object_type="price_override_request",
                object_id=str(request.id),
                after={"reason": reason},
            )

        return request

    # -- execute --

    EXECUTE_ROLES = {
        UserRole.SHIFT_SUPERVISOR,
        UserRole.OPERATIONS_MANAGER,
        UserRole.ADMINISTRATOR,
    }

    def execute_override(
        self,
        request_id: int,
        user_id: int,
        username: str,
        user_role: str,
        actor_store_id: Optional[int] = None,
    ) -> PriceOverrideRequest:
        """Apply an APPROVED price override to its ticket. One-time only.

        The conditional UPDATE in `try_execute` is the idempotency
        guard: a duplicate execute will leave the request in `executed`
        state and the second caller's transition will return False, so
        the ticket payout is never doubly modified.
        """
        if user_role not in self.EXECUTE_ROLES:
            raise PermissionError(
                f"Role '{user_role}' is not authorized to execute price overrides"
            )

        request = self.override_repo.get_by_id(request_id)
        if not request:
            raise ValueError("Price override request not found")
        enforce_store_access(
            entity_store_id=request.store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role or "",
            entity_name="price_override_request",
        )
        if request.status != "approved":
            raise ValueError(
                f"Override must be approved before execution, status: {request.status}"
            )
        if request.executed_at is not None:
            raise ValueError("Override already executed (one-time only)")

        ticket = self.ticket_repo.get_by_id(request.ticket_id)
        if not ticket:
            raise ValueError("Associated ticket not found")

        now = self._now_utc()
        with atomic(self.override_repo.conn):
            if not self.override_repo.try_execute(request_id, now):
                raise ValueError(
                    "Override was already executed (concurrent or duplicate request)"
                )

            previous_final = ticket.final_payout
            ticket.final_payout = float(request.proposed_payout)
            self.ticket_repo.update(ticket)

            request = self.override_repo.get_by_id(request_id)

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="price_override.executed",
                object_type="price_override_request",
                object_id=str(request.id),
                before={"final_payout": previous_final},
                after={
                    "final_payout": ticket.final_payout,
                    "ticket_id": ticket.id,
                },
            )

        return request

    # -- read --

    def list_pending(
        self,
        actor_store_id: Optional[int] = None,
        user_role: Optional[str] = None,
    ) -> List[PriceOverrideRequest]:
        if user_role == UserRole.ADMINISTRATOR and actor_store_id is None:
            # System-wide admins can see everything by querying every
            # store; for now we keep this scoped to a single store
            # because it's the realistic dispatcher view.
            raise ValueError("Administrators must supply a store filter")
        if actor_store_id is None:
            raise PermissionError(
                "Cross-store access denied on price_override_request: no store context"
            )
        return self.override_repo.list_pending_by_store(actor_store_id)
