from typing import List, Optional

from ..models.variance_approval_request import VarianceApprovalRequest
from .base_repository import BaseRepository


class VarianceApprovalRequestRepository(BaseRepository):
    def create(self, request: VarianceApprovalRequest) -> VarianceApprovalRequest:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO variance_approval_requests (
               ticket_id, requested_by_user_id, approver_user_id,
               variance_amount, variance_pct, threshold_amount, threshold_pct,
               confirmation_note, status, password_confirmation_used,
               expires_at, created_at, approved_at, rejected_at, executed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (request.ticket_id, request.requested_by_user_id,
             request.approver_user_id, request.variance_amount,
             request.variance_pct, request.threshold_amount, request.threshold_pct,
             request.confirmation_note, request.status,
             int(request.password_confirmation_used),
             request.expires_at, now, request.approved_at,
             request.rejected_at, request.executed_at),
        )
        request.id = cursor.lastrowid
        request.created_at = now
        return request

    def get_by_id(self, request_id: int) -> Optional[VarianceApprovalRequest]:
        row = self._fetchone(
            "SELECT * FROM variance_approval_requests WHERE id = ?", (request_id,)
        )
        return VarianceApprovalRequest.from_row(row) if row else None

    def list_by_ticket(self, ticket_id: int) -> List[VarianceApprovalRequest]:
        rows = self._fetchall(
            "SELECT * FROM variance_approval_requests WHERE ticket_id = ? ORDER BY created_at DESC",
            (ticket_id,),
        )
        return [VarianceApprovalRequest.from_row(r) for r in rows]

    def get_pending_by_ticket(self, ticket_id: int) -> Optional[VarianceApprovalRequest]:
        row = self._fetchone(
            """SELECT * FROM variance_approval_requests
               WHERE ticket_id = ? AND status = 'pending'
               ORDER BY created_at DESC LIMIT 1""",
            (ticket_id,),
        )
        return VarianceApprovalRequest.from_row(row) if row else None

    def list_by_status(self, status: str) -> List[VarianceApprovalRequest]:
        rows = self._fetchall(
            "SELECT * FROM variance_approval_requests WHERE status = ? ORDER BY created_at DESC",
            (status,),
        )
        return [VarianceApprovalRequest.from_row(r) for r in rows]

    def update(self, request: VarianceApprovalRequest) -> VarianceApprovalRequest:
        self._execute(
            """UPDATE variance_approval_requests SET
               approver_user_id = ?, confirmation_note = ?, status = ?,
               password_confirmation_used = ?,
               approved_at = ?, rejected_at = ?, executed_at = ?
               WHERE id = ?""",
            (request.approver_user_id, request.confirmation_note,
             request.status, int(request.password_confirmation_used),
             request.approved_at, request.rejected_at,
             request.executed_at, request.id),
        )
        return request

    def delete(self, request_id: int) -> None:
        self._execute(
            "DELETE FROM variance_approval_requests WHERE id = ?", (request_id,)
        )

    def try_execute_approval(
        self, request_id: int, approver_user_id: int, now: str
    ) -> bool:
        """Atomically transition a pending variance approval to 'executed'.

        Returns True if the transition succeeded, False if the request was
        already processed (status changed by a concurrent request).
        This is the critical idempotency + concurrency guard for dual-control.
        """
        cursor = self._execute(
            """UPDATE variance_approval_requests
               SET approver_user_id = ?, status = 'executed',
                   password_confirmation_used = 1,
                   approved_at = ?, executed_at = ?
               WHERE id = ? AND status = 'pending'""",
            (approver_user_id, now, now, request_id),
        )
        return cursor.rowcount > 0
