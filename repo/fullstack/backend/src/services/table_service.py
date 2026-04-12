"""Table / Room operations service — state machine, merge, transfer.

Enforces the table session state machine (available -> occupied ->
pre_checkout -> cleared -> available) with merge/transfer support
and a full activity event timeline.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from ..enums.table_activity_event_type import TableActivityEventType
from ..enums.table_state import TableState
from ..enums.user_role import UserRole
from ..models.service_table import ServiceTable
from ..models.table_activity_event import TableActivityEvent
from ..models.table_session import TableSession
from ..repositories.service_table_repository import ServiceTableRepository
from ..repositories.table_activity_event_repository import TableActivityEventRepository
from ..repositories.table_session_repository import TableSessionRepository
from ..repositories.user_repository import UserRepository
from ._authz import enforce_store_access
from ._tx import atomic
from .audit_service import AuditService

logger = logging.getLogger(__name__)

VALID_TABLE_TRANSITIONS = {
    TableState.AVAILABLE: {TableState.OCCUPIED},
    TableState.OCCUPIED: {TableState.PRE_CHECKOUT, TableState.CLEARED},
    TableState.PRE_CHECKOUT: {TableState.CLEARED},
    TableState.CLEARED: {TableState.AVAILABLE},
}


class TableService:
    def __init__(
        self,
        table_repo: ServiceTableRepository,
        session_repo: TableSessionRepository,
        event_repo: TableActivityEventRepository,
        audit_service: AuditService,
        user_repo: UserRepository = None,
    ):
        self.table_repo = table_repo
        self.session_repo = session_repo
        self.event_repo = event_repo
        self.audit_service = audit_service
        self.user_repo = user_repo

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _validate_table_transition(self, current: str, target: str) -> None:
        allowed = VALID_TABLE_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise ValueError(
                f"Invalid table transition: {current} -> {target}"
            )

    def _require_host_role(self, user_role: str) -> None:
        if user_role not in (
            UserRole.HOST, UserRole.SHIFT_SUPERVISOR,
            UserRole.ADMINISTRATOR,
        ):
            raise PermissionError("Only Hosts can manage tables")

    def _create_event(
        self, session_id: int, user_id: int, event_type: str,
        before_state: Optional[str], after_state: Optional[str],
        notes: Optional[str] = None,
    ) -> TableActivityEvent:
        return self.event_repo.create(TableActivityEvent(
            table_session_id=session_id,
            actor_user_id=user_id,
            event_type=event_type,
            before_state=before_state,
            after_state=after_state,
            notes=notes,
        ))

    def open_table(
        self,
        table_id: int,
        store_id: int,
        user_id: int,
        username: str,
        user_role: str,
        actor_store_id: Optional[int] = None,
        customer_label: Optional[str] = None,
    ) -> TableSession:
        self._require_host_role(user_role)

        # The actor must belong to the same store they're claiming to
        # operate on. Don't trust the client-supplied `store_id`.
        enforce_store_access(
            entity_store_id=store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role,
            entity_name="table",
        )

        table = self.table_repo.get_by_id(table_id)
        if not table:
            raise ValueError("Table not found")
        if not table.is_active:
            raise ValueError("Table is inactive")
        if table.merged_into_id is not None:
            raise ValueError("Table is currently merged")
        if table.store_id != store_id:
            raise PermissionError("Table does not belong to this store")
        enforce_store_access(
            entity_store_id=table.store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role,
            entity_name="table",
        )

        existing = self.session_repo.get_active_by_table(table_id)
        if existing and existing.current_state != TableState.AVAILABLE:
            raise ValueError(f"Table already has active session in state: {existing.current_state}")

        with atomic(self.session_repo.conn):
            session = TableSession(
                store_id=store_id,
                table_id=table_id,
                opened_by_user_id=user_id,
                current_state=TableState.OCCUPIED,
                current_customer_label=customer_label,
            )
            session = self.session_repo.create(session)

            self._create_event(
                session.id, user_id, TableActivityEventType.OPENED,
                None, TableState.OCCUPIED,
            )

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="table.opened",
                object_type="table_session",
                object_id=str(session.id),
                after={"table_id": table_id, "state": TableState.OCCUPIED},
            )

        return session

    def transition_table(
        self,
        session_id: int,
        target_state: str,
        user_id: int,
        username: str,
        user_role: str,
        actor_store_id: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> TableSession:
        self._require_host_role(user_role)

        session = self.session_repo.get_by_id(session_id)
        if not session:
            raise ValueError("Session not found")
        enforce_store_access(
            entity_store_id=session.store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role,
            entity_name="table_session",
        )

        self._validate_table_transition(session.current_state, target_state)

        before_state = session.current_state
        session.current_state = target_state

        if target_state == TableState.CLEARED:
            session.closed_at = self._now_utc()

        event_type_map = {
            TableState.OCCUPIED: TableActivityEventType.OCCUPIED,
            TableState.PRE_CHECKOUT: TableActivityEventType.PRE_CHECKOUT,
            TableState.CLEARED: TableActivityEventType.CLEARED,
            TableState.AVAILABLE: TableActivityEventType.RELEASED,
        }

        with atomic(self.session_repo.conn):
            session = self.session_repo.update(session)

            self._create_event(
                session.id, user_id, event_type_map.get(target_state, target_state),
                before_state, target_state, notes,
            )

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="table.transition",
                object_type="table_session",
                object_id=str(session.id),
                before={"state": before_state},
                after={"state": target_state},
            )

        return session

    def merge_tables(
        self,
        session_ids: list,
        store_id: int,
        user_id: int,
        username: str,
        user_role: str,
        actor_store_id: Optional[int] = None,
    ) -> str:
        self._require_host_role(user_role)
        enforce_store_access(
            entity_store_id=store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role,
            entity_name="table_session",
        )

        if len(session_ids) < 2:
            raise ValueError("At least two sessions are required for merge")

        sessions = []
        for sid in session_ids:
            s = self.session_repo.get_by_id(sid)
            if not s:
                raise ValueError(f"Session {sid} not found")
            if s.store_id != store_id:
                raise PermissionError(f"Session {sid} belongs to a different store")
            enforce_store_access(
                entity_store_id=s.store_id,
                actor_store_id=actor_store_id,
                actor_role=user_role,
                entity_name="table_session",
            )
            if s.current_state not in (TableState.OCCUPIED, TableState.AVAILABLE):
                raise ValueError(f"Session {sid} is in state {s.current_state}, cannot merge")
            if s.merged_group_code is not None:
                raise ValueError(f"Session {sid} is already merged")
            sessions.append(s)

        group_code = f"MRG-{uuid.uuid4().hex[:8].upper()}"

        with atomic(self.session_repo.conn):
            for s in sessions:
                s.merged_group_code = group_code
                self.session_repo.update(s)
                self._create_event(
                    s.id, user_id, TableActivityEventType.MERGED,
                    s.current_state, s.current_state,
                    f"Merged into group {group_code}",
                )

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="table.merged",
                object_type="table_session",
                object_id=group_code,
                after={"session_ids": session_ids, "group_code": group_code},
            )

        return group_code

    def transfer_table(
        self,
        session_id: int,
        new_user_id: int,
        user_id: int,
        username: str,
        user_role: str,
        actor_store_id: Optional[int] = None,
    ) -> TableSession:
        self._require_host_role(user_role)

        session = self.session_repo.get_by_id(session_id)
        if not session:
            raise ValueError("Session not found")
        enforce_store_access(
            entity_store_id=session.store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role,
            entity_name="table_session",
        )
        if session.current_state in (TableState.CLEARED, TableState.AVAILABLE):
            raise ValueError("Cannot transfer a cleared or available table")

        # Cross-store guard: the target user must belong to the same
        # store as the session.  A transfer to a user from another
        # store would break store isolation.
        if self.user_repo is not None:
            target_user = self.user_repo.get_by_id(new_user_id)
            if not target_user:
                raise ValueError("Target user not found")
            if (
                target_user.role != UserRole.ADMINISTRATOR
                and target_user.store_id != session.store_id
            ):
                raise PermissionError(
                    "Cannot transfer table to a user from a different store"
                )

        before_owner = session.opened_by_user_id
        session.opened_by_user_id = new_user_id

        with atomic(self.session_repo.conn):
            session = self.session_repo.update(session)

            self._create_event(
                session.id, user_id, TableActivityEventType.TRANSFERRED,
                session.current_state, session.current_state,
                f"Transferred from user {before_owner} to {new_user_id}",
            )

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="table.transferred",
                object_type="table_session",
                object_id=str(session.id),
                before={"opened_by": before_owner},
                after={"opened_by": new_user_id},
            )

        return session

    def get_timeline(
        self,
        session_id: int,
        actor_store_id: Optional[int] = None,
        user_role: Optional[str] = None,
    ) -> list:
        session = self.session_repo.get_by_id(session_id)
        if not session:
            raise ValueError("Session not found")
        # Timeline access is a read path — still must not leak across
        # store boundaries.
        enforce_store_access(
            entity_store_id=session.store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role or "",
            entity_name="table_session",
        )
        return self.event_repo.list_by_session(session_id)
