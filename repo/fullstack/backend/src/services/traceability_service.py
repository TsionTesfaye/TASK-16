"""Batch traceability and recall service.

Manages batch lifecycle (procured -> received -> issued -> finished),
genealogy event recording, and recall-list generation by batch/date.
"""
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from ..enums.batch_genealogy_event_type import BatchGenealogyEventType
from ..enums.batch_status import BatchStatus
from ..enums.user_role import UserRole
from ..models.batch import Batch
from ..models.batch_genealogy_event import BatchGenealogyEvent
from ..models.recall_run import RecallRun
from ..repositories.batch_genealogy_event_repository import BatchGenealogyEventRepository
from ..repositories.batch_repository import BatchRepository
from ..repositories.recall_run_repository import RecallRunRepository
from ._authz import enforce_store_access
from ._tx import atomic
from .audit_service import AuditService

logger = logging.getLogger(__name__)

CREATE_BATCH_ROLES = {
    UserRole.QC_INSPECTOR,
    UserRole.SHIFT_SUPERVISOR,
    UserRole.OPERATIONS_MANAGER,
    UserRole.ADMINISTRATOR,
}

TRANSITION_BATCH_ROLES = {
    UserRole.QC_INSPECTOR,
    UserRole.SHIFT_SUPERVISOR,
    UserRole.OPERATIONS_MANAGER,
    UserRole.ADMINISTRATOR,
}

# Recall actions are an operations / compliance escalation — only
# supervisors and above may trigger them.
RECALL_ROLES = {
    UserRole.SHIFT_SUPERVISOR,
    UserRole.OPERATIONS_MANAGER,
    UserRole.ADMINISTRATOR,
}

VALID_BATCH_TRANSITIONS = {
    BatchStatus.PROCURED: {BatchStatus.RECEIVED},
    BatchStatus.RECEIVED: {BatchStatus.QUARANTINED, BatchStatus.ISSUED},
    BatchStatus.QUARANTINED: {
        BatchStatus.RECEIVED, BatchStatus.SCRAPPED,
        BatchStatus.RETURNED, BatchStatus.RECALLED,
    },
    BatchStatus.ISSUED: {BatchStatus.FINISHED, BatchStatus.RECALLED},
    BatchStatus.FINISHED: {BatchStatus.RECALLED},
    BatchStatus.RECALLED: set(),
    BatchStatus.SCRAPPED: set(),
    BatchStatus.RETURNED: set(),
}


class TraceabilityService:
    def __init__(
        self,
        batch_repo: BatchRepository,
        genealogy_repo: BatchGenealogyEventRepository,
        recall_repo: RecallRunRepository,
        audit_service: AuditService,
    ):
        self.batch_repo = batch_repo
        self.genealogy_repo = genealogy_repo
        self.recall_repo = recall_repo
        self.audit_service = audit_service

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _validate_batch_transition(self, current: str, target: str) -> None:
        allowed = VALID_BATCH_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise ValueError(
                f"Invalid batch transition: {current} -> {target}"
            )

    def create_batch(
        self,
        store_id: int,
        batch_code: str,
        user_id: int,
        username: str,
        actor_store_id: Optional[int] = None,
        user_role: Optional[str] = None,
        source_ticket_id: Optional[int] = None,
    ) -> Batch:
        if user_role not in CREATE_BATCH_ROLES:
            raise PermissionError(
                f"Role '{user_role}' cannot create batches"
            )
        enforce_store_access(
            entity_store_id=store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role or "",
            entity_name="batch",
        )
        if not batch_code or not batch_code.strip():
            raise ValueError("Batch code is required")

        now = self._now_utc()
        with atomic(self.batch_repo.conn):
            batch = Batch(
                store_id=store_id,
                batch_code=batch_code.strip(),
                source_ticket_id=source_ticket_id,
                status=BatchStatus.PROCURED,
                procurement_at=now,
            )
            batch = self.batch_repo.create(batch)

            self.genealogy_repo.create(BatchGenealogyEvent(
                batch_id=batch.id,
                event_type=BatchGenealogyEventType.PROCURED,
                actor_user_id=user_id,
                metadata_json=json.dumps({"source_ticket_id": source_ticket_id}),
            ))

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="batch.created",
                object_type="batch",
                object_id=str(batch.id),
                after={"batch_code": batch_code, "status": batch.status},
            )

        return batch

    def transition_batch(
        self,
        batch_id: int,
        target_status: str,
        user_id: int,
        username: str,
        actor_store_id: Optional[int] = None,
        user_role: Optional[str] = None,
        location_context: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Batch:
        if user_role not in TRANSITION_BATCH_ROLES:
            raise PermissionError(
                f"Role '{user_role}' cannot transition batches"
            )
        # Recall is the only transition that's also a compliance event;
        # require supervisor+ for that one specifically.
        if (
            target_status == BatchStatus.RECALLED
            and user_role not in RECALL_ROLES
        ):
            raise PermissionError(
                f"Role '{user_role}' cannot recall a batch"
            )

        batch = self.batch_repo.get_by_id(batch_id)
        if not batch:
            raise ValueError("Batch not found")
        enforce_store_access(
            entity_store_id=batch.store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role or "",
            entity_name="batch",
        )

        self._validate_batch_transition(batch.status, target_status)

        before_status = batch.status
        batch.status = target_status

        now = self._now_utc()
        if target_status == BatchStatus.RECEIVED:
            batch.receiving_at = now
        elif target_status == BatchStatus.ISSUED:
            batch.issued_at = now
        elif target_status == BatchStatus.FINISHED:
            batch.finished_goods_at = now

        event_type_map = {
            BatchStatus.RECEIVED: BatchGenealogyEventType.RECEIVED,
            BatchStatus.ISSUED: BatchGenealogyEventType.ISSUED,
            BatchStatus.FINISHED: BatchGenealogyEventType.FINISHED_GOODS,
            BatchStatus.RECALLED: BatchGenealogyEventType.RECALLED,
            BatchStatus.SCRAPPED: BatchGenealogyEventType.DISPOSITIONED,
            BatchStatus.RETURNED: BatchGenealogyEventType.DISPOSITIONED,
            BatchStatus.QUARANTINED: BatchGenealogyEventType.QUARANTINED,
        }
        event_type = event_type_map.get(target_status, target_status)

        with atomic(self.batch_repo.conn):
            batch = self.batch_repo.update(batch)

            self.genealogy_repo.create(BatchGenealogyEvent(
                batch_id=batch_id,
                event_type=event_type,
                actor_user_id=user_id,
                location_context=location_context,
                metadata_json=json.dumps(metadata) if metadata else None,
            ))

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="batch.transitioned",
                object_type="batch",
                object_id=str(batch_id),
                before={"status": before_status},
                after={"status": target_status},
            )

        return batch

    def generate_recall(
        self,
        user_id: int,
        username: str,
        store_id: Optional[int] = None,
        actor_store_id: Optional[int] = None,
        user_role: Optional[str] = None,
        batch_filter: Optional[str] = None,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
    ) -> RecallRun:
        # Recall generation is a compliance escalation — only
        # supervisors and above may trigger it.
        if user_role not in RECALL_ROLES:
            raise PermissionError(
                f"Role '{user_role}' cannot generate recalls"
            )
        # 1. Resolve the store scope. Non-admins are pinned to their
        #    own store regardless of what they sent in the request.
        is_admin = user_role == UserRole.ADMINISTRATOR
        if is_admin:
            if store_id is None:
                store_id = actor_store_id  # may still be None for system-wide admin
        else:
            if actor_store_id is None:
                raise PermissionError(
                    "Cross-store access denied on recall: no store context"
                )
            if store_id is not None and store_id != actor_store_id:
                raise PermissionError(
                    "Cross-store access denied on recall"
                )
            store_id = actor_store_id

        events = []

        if batch_filter:
            # 2. Resolve the batch by (store_id, batch_code). A
            #    legacy unscoped lookup would let a store A user
            #    probe store B's batches by guessing their codes.
            if store_id is None:
                # Admin without a store filter: fall back to the
                # unscoped lookup, but still verify.
                batch = self.batch_repo.get_by_batch_code(batch_filter)
            else:
                batch = self.batch_repo.get_by_store_and_batch_code(
                    store_id, batch_filter
                )
            if batch:
                # 3. Defence-in-depth: re-check store boundary after load.
                if not is_admin and batch.store_id != actor_store_id:
                    raise PermissionError(
                        "Cross-store access denied on recall"
                    )
                events = self.genealogy_repo.list_by_batch(batch.id)
        elif date_start and date_end:
            if store_id is not None:
                events = self.genealogy_repo.list_by_store_and_date_range(
                    store_id, date_start, date_end,
                )
            else:
                # Admin + no store filter — system-wide recall. Explicit.
                events = self.genealogy_repo.list_by_date_range(
                    date_start, date_end,
                )
        else:
            raise ValueError("Either batch_filter or date range is required")

        # Build structured recall output — affected batches + events
        result_data = self._build_recall_output(events)

        with atomic(self.recall_repo.conn):
            run = RecallRun(
                store_id=store_id,
                requested_by_user_id=user_id,
                batch_filter=batch_filter,
                date_start=date_start,
                date_end=date_end,
                result_count=len(events),
                result_json=json.dumps(result_data),
            )
            run = self.recall_repo.create(run)

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="recall.generated",
                object_type="recall_run",
                object_id=str(run.id),
                after={
                    "result_count": run.result_count,
                    "batch_filter": batch_filter,
                    "date_range": f"{date_start} to {date_end}" if date_start else None,
                },
            )

        return run

    def _build_recall_output(self, events: list) -> dict:
        """Build structured recall data from genealogy events."""
        batch_ids = set()
        event_list = []
        for e in events:
            batch_ids.add(e.batch_id)
            event_list.append({
                "event_id": e.id,
                "batch_id": e.batch_id,
                "event_type": e.event_type,
                "actor_user_id": e.actor_user_id,
                "created_at": e.created_at,
                "location_context": e.location_context,
            })

        affected_batches = []
        for bid in batch_ids:
            batch = self.batch_repo.get_by_id(bid)
            if batch:
                affected_batches.append({
                    "batch_id": batch.id,
                    "batch_code": batch.batch_code,
                    "store_id": batch.store_id,
                    "status": batch.status,
                    "source_ticket_id": batch.source_ticket_id,
                })

        return {
            "affected_batches": affected_batches,
            "events": event_list,
            "total_batches": len(affected_batches),
            "total_events": len(event_list),
        }

    def get_recall_run(
        self,
        run_id: int,
        actor_store_id: Optional[int] = None,
        user_role: Optional[str] = None,
    ) -> RecallRun:
        """Retrieve a recall run by ID with store-scoped access."""
        if user_role not in RECALL_ROLES:
            raise PermissionError(f"Role '{user_role}' cannot view recalls")
        run = self.recall_repo.get_by_id(run_id)
        if not run:
            raise ValueError("Recall run not found")
        if (
            user_role != UserRole.ADMINISTRATOR
            and run.store_id is not None
            and actor_store_id != run.store_id
        ):
            raise PermissionError("Cross-store access denied on recall")
        return run

    def get_batch_lineage(
        self,
        batch_id: int,
        actor_store_id: Optional[int] = None,
        user_role: Optional[str] = None,
    ) -> List[BatchGenealogyEvent]:
        batch = self.batch_repo.get_by_id(batch_id)
        if not batch:
            raise ValueError("Batch not found")
        enforce_store_access(
            entity_store_id=batch.store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role or "",
            entity_name="batch",
        )
        return self.genealogy_repo.list_by_batch(batch_id)
