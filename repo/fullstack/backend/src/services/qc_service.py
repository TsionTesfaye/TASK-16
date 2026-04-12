"""Quality Control service — inspections, sampling, escalation, quarantine.

Implements sampling rules (10% min 3, escalate to 100% on 2 nonconformances/day),
quarantine with dispositions (return, scrap, concession), and batch genealogy
integration.
"""
import json
import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Optional

from ..enums.batch_genealogy_event_type import BatchGenealogyEventType
from ..enums.batch_status import BatchStatus
from ..enums.inspection_outcome import InspectionOutcome
from ..enums.quarantine_disposition import QuarantineDisposition
from ..enums.user_role import UserRole
from ..models.batch import Batch
from ..models.batch_genealogy_event import BatchGenealogyEvent
from ..models.qc_inspection import QCInspection
from ..models.quarantine_record import QuarantineRecord
from ..repositories.batch_genealogy_event_repository import BatchGenealogyEventRepository
from ..repositories.batch_repository import BatchRepository
from ..repositories.buyback_ticket_repository import BuybackTicketRepository
from ..repositories.qc_inspection_repository import QCInspectionRepository
from ..repositories.quarantine_record_repository import QuarantineRecordRepository
from ..repositories.settings_repository import SettingsRepository
from ..repositories.user_repository import UserRepository
from ._authz import enforce_store_access
from ._tx import atomic
from .audit_service import AuditService
from .auth_service import AuthService

logger = logging.getLogger(__name__)

SUPERVISOR_ROLES = {
    UserRole.SHIFT_SUPERVISOR,
    UserRole.OPERATIONS_MANAGER,
    UserRole.ADMINISTRATOR,
}

# SLA: a quarantine must be resolved (returned, scrapped, or concession-
# accepted) within this window from its creation. Anything older and
# still unresolved is surfaced by the scheduler as overdue.
QUARANTINE_SLA_DAYS = 7


class QCService:
    def __init__(
        self,
        qc_repo: QCInspectionRepository,
        quarantine_repo: QuarantineRecordRepository,
        batch_repo: BatchRepository,
        genealogy_repo: BatchGenealogyEventRepository,
        settings_repo: SettingsRepository,
        audit_service: AuditService,
        auth_service: AuthService,
        user_repo: UserRepository = None,
        ticket_repo: BuybackTicketRepository = None,
    ):
        if user_repo is None:
            raise ValueError("user_repo is required — concession role validation cannot be bypassed")
        if auth_service is None:
            raise ValueError("auth_service is required — concession sign-off must verify passwords")
        if ticket_repo is None:
            raise ValueError("ticket_repo is required — QC ↔ ticket relationship validation")
        self.qc_repo = qc_repo
        self.quarantine_repo = quarantine_repo
        self.batch_repo = batch_repo
        self.genealogy_repo = genealogy_repo
        self.settings_repo = settings_repo
        self.audit_service = audit_service
        self.auth_service = auth_service
        self.user_repo = user_repo
        self.ticket_repo = ticket_repo

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _today_utc(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def compute_sample_size(self, store_id: int, lot_size: int) -> int:
        if lot_size <= 0:
            raise ValueError("Lot size must be positive")

        settings = self.settings_repo.get_effective(store_id)
        if not settings:
            from ..models.settings import Settings
            settings = Settings()

        today = self._today_utc()
        nc_count = self.qc_repo.count_nonconformances_for_date(store_id, today)

        if nc_count >= settings.qc_escalation_nonconformances_per_day:
            return lot_size  # 100% inspection

        pct_sample = math.ceil(lot_size * settings.qc_sample_pct / 100.0)
        return max(pct_sample, settings.qc_sample_min_items)

    def create_inspection(
        self,
        ticket_id: int,
        store_id: int,
        inspector_user_id: int,
        inspector_username: str,
        inspector_role: str,
        actual_weight_lbs: float,
        lot_size: int,
        nonconformance_count: int,
        inspection_outcome: str,
        actor_store_id: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> QCInspection:
        if inspector_role not in (UserRole.QC_INSPECTOR, UserRole.ADMINISTRATOR):
            raise PermissionError("Only QC Inspectors can create inspections")
        enforce_store_access(
            entity_store_id=store_id,
            actor_store_id=actor_store_id,
            actor_role=inspector_role,
            entity_name="qc_inspection",
        )

        # Domain validation: the referenced ticket MUST exist and MUST
        # belong to the same store as the inspection. A bad foreign key
        # would otherwise blow up at INSERT time with a sqlite3
        # IntegrityError that the route would surface as a 500.
        ticket = self.ticket_repo.get_by_id(ticket_id)
        if not ticket:
            raise ValueError(f"Ticket {ticket_id} not found")
        if ticket.store_id != store_id:
            raise PermissionError(
                f"Cross-store access denied: ticket {ticket_id} belongs to "
                f"store {ticket.store_id}, not the inspection store {store_id}"
            )

        if actual_weight_lbs <= 0:
            raise ValueError("Actual weight must be positive")
        if lot_size <= 0:
            raise ValueError("Lot size must be positive")
        if nonconformance_count < 0:
            raise ValueError("Nonconformance count cannot be negative")
        if inspection_outcome not in (
            InspectionOutcome.PASS,
            InspectionOutcome.FAIL,
            InspectionOutcome.PASS_WITH_CONCESSION,
        ):
            raise ValueError(f"Invalid inspection outcome: {inspection_outcome}")

        sample_size = self.compute_sample_size(store_id, lot_size)

        quarantine_required = inspection_outcome == InspectionOutcome.FAIL

        with atomic(self.qc_repo.conn):
            inspection = QCInspection(
                ticket_id=ticket_id,
                inspector_user_id=inspector_user_id,
                actual_weight_lbs=actual_weight_lbs,
                lot_size=lot_size,
                sample_size=sample_size,
                nonconformance_count=nonconformance_count,
                inspection_outcome=inspection_outcome,
                quarantine_required=quarantine_required,
                notes=notes,
            )
            inspection = self.qc_repo.create(inspection)

            self.audit_service.log(
                actor_user_id=inspector_user_id,
                actor_username=inspector_username,
                action_code="qc.inspection_created",
                object_type="qc_inspection",
                object_id=str(inspection.id),
                after={
                    "ticket_id": ticket_id,
                    "outcome": inspection_outcome,
                    "nonconformances": nonconformance_count,
                    "sample_size": sample_size,
                    "quarantine_required": quarantine_required,
                },
            )

        return inspection

    def create_quarantine(
        self,
        ticket_id: int,
        batch_id: int,
        user_id: int,
        username: str,
        actor_store_id: Optional[int] = None,
        user_role: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> QuarantineRecord:
        # Domain validation: load BOTH parents up front, verify each
        # exists, verify they live in the same store, and verify the
        # batch's source ticket (if any) matches the ticket the caller
        # is quarantining. Reject any inconsistent combination here so
        # the INSERT below cannot fail with a foreign-key 500.
        batch = self.batch_repo.get_by_id(batch_id)
        if not batch:
            raise ValueError(f"Batch {batch_id} not found")
        ticket = self.ticket_repo.get_by_id(ticket_id)
        if not ticket:
            raise ValueError(f"Ticket {ticket_id} not found")
        if ticket.store_id != batch.store_id:
            raise ValueError(
                f"Ticket {ticket_id} (store {ticket.store_id}) and batch "
                f"{batch_id} (store {batch.store_id}) belong to different stores"
            )
        if (
            batch.source_ticket_id is not None
            and batch.source_ticket_id != ticket_id
        ):
            raise ValueError(
                f"Batch {batch_id} was sourced from ticket "
                f"{batch.source_ticket_id}, not ticket {ticket_id}"
            )

        enforce_store_access(
            entity_store_id=batch.store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role or "",
            entity_name="batch",
        )

        # Every quarantine gets an explicit resolution deadline at
        # creation time. The scheduler uses this to surface overdue
        # quarantines that haven't been dispositioned in time.
        sla_deadline = (
            datetime.now(timezone.utc) + timedelta(days=QUARANTINE_SLA_DAYS)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        with atomic(self.quarantine_repo.conn):
            record = QuarantineRecord(
                ticket_id=ticket_id,
                batch_id=batch_id,
                created_by_user_id=user_id,
                due_back_to_customer_at=sla_deadline,
                notes=notes,
            )
            record = self.quarantine_repo.create(record)

            batch.status = BatchStatus.QUARANTINED
            self.batch_repo.update(batch)

            self.genealogy_repo.create(BatchGenealogyEvent(
                batch_id=batch_id,
                event_type=BatchGenealogyEventType.QUARANTINED,
                actor_user_id=user_id,
                metadata_json=json.dumps({"ticket_id": ticket_id, "quarantine_id": record.id}),
            ))

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="qc.quarantine_created",
                object_type="quarantine_record",
                object_id=str(record.id),
                after={"ticket_id": ticket_id, "batch_id": batch_id},
            )

        return record

    def resolve_quarantine(
        self,
        quarantine_id: int,
        disposition: str,
        user_id: int,
        username: str,
        user_role: str,
        actor_store_id: Optional[int] = None,
        concession_supervisor_id: Optional[int] = None,
        concession_supervisor_username: Optional[str] = None,
        concession_supervisor_password: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> QuarantineRecord:
        # Quarantine resolution is an inventory-control action — restrict
        # to QC inspectors and supervisors.
        RESOLVE_ROLES = {
            UserRole.QC_INSPECTOR,
            UserRole.SHIFT_SUPERVISOR,
            UserRole.OPERATIONS_MANAGER,
            UserRole.ADMINISTRATOR,
        }
        if user_role not in RESOLVE_ROLES:
            raise PermissionError(
                f"Role '{user_role}' is not authorized to resolve quarantines"
            )

        record = self.quarantine_repo.get_by_id(quarantine_id)
        if not record:
            raise ValueError("Quarantine record not found")
        if record.resolved_at is not None:
            raise ValueError("Quarantine already resolved")

        # Cross-store guard — resolve the associated batch to get its
        # store, then verify the actor belongs to that store.
        ref_batch = self.batch_repo.get_by_id(record.batch_id)
        if ref_batch:
            enforce_store_access(
                entity_store_id=ref_batch.store_id,
                actor_store_id=actor_store_id,
                actor_role=user_role,
                entity_name="quarantine_record",
            )

        if disposition not in (
            QuarantineDisposition.RETURN_TO_CUSTOMER,
            QuarantineDisposition.SCRAP,
            QuarantineDisposition.CONCESSION_ACCEPTANCE,
        ):
            raise ValueError(f"Invalid disposition: {disposition}")

        now = self._now_utc()

        if disposition == QuarantineDisposition.CONCESSION_ACCEPTANCE:
            if not concession_supervisor_id:
                raise ValueError("Supervisor sign-off required for concession acceptance")
            if concession_supervisor_id == user_id:
                raise PermissionError("Self-approval of concession is forbidden")
            if concession_supervisor_username is None:
                raise ValueError("Supervisor username required")
            supervisor = self.user_repo.get_by_id(concession_supervisor_id)
            if not supervisor:
                raise ValueError("Supervisor user not found")
            if supervisor.role not in SUPERVISOR_ROLES:
                raise PermissionError(
                    f"Concession sign-off requires supervisor role, got '{supervisor.role}'"
                )
            if not supervisor.is_active or supervisor.is_frozen:
                raise PermissionError("Supervisor account is inactive or frozen")

            # Cross-store guard: the concession supervisor must belong
            # to the same store as the quarantined batch.  Admins are
            # exempt (system-wide operators with no pinned store).
            if (
                supervisor.role != UserRole.ADMINISTRATOR
                and ref_batch is not None
                and supervisor.store_id != ref_batch.store_id
            ):
                raise PermissionError(
                    "Concession supervisor must belong to the same store as the batch"
                )

            # Concession sign-off is a dual-control path — the sign-off
            # supervisor must re-enter their password. Boolean flags are
            # not accepted.
            if not concession_supervisor_password:
                raise ValueError("Supervisor password is required for concession sign-off")
            if not self.auth_service.verify_password_for_approval(
                concession_supervisor_id, concession_supervisor_password
            ):
                raise PermissionError("Invalid supervisor password")

            record.concession_signed_by = concession_supervisor_id

        # NOTE: `due_back_to_customer_at` is set at quarantine creation
        # (see `create_quarantine`) and represents the SLA resolution
        # deadline. We do NOT overwrite it here — resolving the
        # quarantine freezes the original deadline for audit purposes.

        record.disposition = disposition
        record.notes = notes
        record.resolved_at = now

        with atomic(self.quarantine_repo.conn):
            record = self.quarantine_repo.update(record)

            batch = self.batch_repo.get_by_id(record.batch_id)
            if batch:
                if disposition == QuarantineDisposition.SCRAP:
                    batch.status = BatchStatus.SCRAPPED
                elif disposition == QuarantineDisposition.RETURN_TO_CUSTOMER:
                    batch.status = BatchStatus.RETURNED
                elif disposition == QuarantineDisposition.CONCESSION_ACCEPTANCE:
                    batch.status = BatchStatus.RECEIVED
                self.batch_repo.update(batch)

            self.genealogy_repo.create(BatchGenealogyEvent(
                batch_id=record.batch_id,
                event_type=BatchGenealogyEventType.DISPOSITIONED,
                actor_user_id=user_id,
                metadata_json=json.dumps({
                    "disposition": disposition,
                    "quarantine_id": quarantine_id,
                }),
            ))

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="qc.quarantine_resolved",
                object_type="quarantine_record",
                object_id=str(quarantine_id),
                before={"disposition": None},
                after={
                    "disposition": disposition,
                    "concession_signed_by": record.concession_signed_by,
                },
            )

        return record
