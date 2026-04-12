from typing import List, Optional

from ..models.schedule_adjustment_request import ScheduleAdjustmentRequest
from .base_repository import BaseRepository


class ScheduleAdjustmentRequestRepository(BaseRepository):
    def create(self, request: ScheduleAdjustmentRequest) -> ScheduleAdjustmentRequest:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO schedule_adjustment_requests (
               store_id, requested_by_user_id, approver_user_id,
               adjustment_type, target_entity_type, target_entity_id,
               before_value, after_value, reason, status,
               password_confirmation_used,
               created_at, approved_at, rejected_at, executed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (request.store_id, request.requested_by_user_id,
             request.approver_user_id, request.adjustment_type,
             request.target_entity_type, request.target_entity_id,
             request.before_value, request.after_value, request.reason,
             request.status, int(request.password_confirmation_used),
             now, request.approved_at, request.rejected_at, request.executed_at),
        )
        request.id = cursor.lastrowid
        request.created_at = now
        return request

    def get_by_id(self, request_id: int) -> Optional[ScheduleAdjustmentRequest]:
        row = self._fetchone(
            "SELECT * FROM schedule_adjustment_requests WHERE id = ?", (request_id,)
        )
        return ScheduleAdjustmentRequest.from_row(row) if row else None

    def list_by_store(self, store_id: int) -> List[ScheduleAdjustmentRequest]:
        rows = self._fetchall(
            "SELECT * FROM schedule_adjustment_requests WHERE store_id = ? ORDER BY created_at DESC",
            (store_id,),
        )
        return [ScheduleAdjustmentRequest.from_row(r) for r in rows]

    def list_by_status(self, status: str) -> List[ScheduleAdjustmentRequest]:
        rows = self._fetchall(
            "SELECT * FROM schedule_adjustment_requests WHERE status = ? ORDER BY created_at DESC",
            (status,),
        )
        return [ScheduleAdjustmentRequest.from_row(r) for r in rows]

    def update(self, request: ScheduleAdjustmentRequest) -> ScheduleAdjustmentRequest:
        self._execute(
            """UPDATE schedule_adjustment_requests SET
               approver_user_id = ?, status = ?,
               password_confirmation_used = ?,
               approved_at = ?, rejected_at = ?, executed_at = ?
               WHERE id = ?""",
            (request.approver_user_id, request.status,
             int(request.password_confirmation_used),
             request.approved_at, request.rejected_at,
             request.executed_at, request.id),
        )
        return request

    def delete(self, request_id: int) -> None:
        self._execute(
            "DELETE FROM schedule_adjustment_requests WHERE id = ?", (request_id,)
        )

    def try_execute_approval(
        self, request_id: int, approver_user_id: int, now: str
    ) -> bool:
        """Atomically approve+execute a pending schedule adjustment.

        Returns False if a concurrent request already processed it.
        """
        cursor = self._execute(
            """UPDATE schedule_adjustment_requests
               SET approver_user_id = ?, status = 'executed',
                   password_confirmation_used = 1,
                   approved_at = ?, executed_at = ?
               WHERE id = ? AND status = 'pending'""",
            (approver_user_id, now, now, request_id),
        )
        return cursor.rowcount > 0
