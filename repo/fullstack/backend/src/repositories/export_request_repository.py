from typing import List, Optional

from ..models.export_request import ExportRequest
from .base_repository import BaseRepository


class ExportRequestRepository(BaseRepository):
    def create(self, request: ExportRequest) -> ExportRequest:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO export_requests (
               store_id, requested_by_user_id, export_type, filter_json,
               watermark_enabled, attribution_text,
               approval_required, approver_user_id, status,
               output_path, created_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (request.store_id, request.requested_by_user_id, request.export_type,
             request.filter_json, int(request.watermark_enabled),
             request.attribution_text, int(request.approval_required),
             request.approver_user_id, request.status,
             request.output_path, now, request.completed_at),
        )
        request.id = cursor.lastrowid
        request.created_at = now
        return request

    def get_by_id(self, request_id: int) -> Optional[ExportRequest]:
        row = self._fetchone(
            "SELECT * FROM export_requests WHERE id = ?", (request_id,)
        )
        return ExportRequest.from_row(row) if row else None

    def list_by_store(self, store_id: int) -> List[ExportRequest]:
        rows = self._fetchall(
            "SELECT * FROM export_requests WHERE store_id = ? ORDER BY created_at DESC",
            (store_id,),
        )
        return [ExportRequest.from_row(r) for r in rows]

    def list_by_user(self, user_id: int) -> List[ExportRequest]:
        rows = self._fetchall(
            "SELECT * FROM export_requests WHERE requested_by_user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        return [ExportRequest.from_row(r) for r in rows]

    def list_by_status(self, status: str) -> List[ExportRequest]:
        rows = self._fetchall(
            "SELECT * FROM export_requests WHERE status = ? ORDER BY created_at DESC",
            (status,),
        )
        return [ExportRequest.from_row(r) for r in rows]

    def list_all(self) -> List[ExportRequest]:
        rows = self._fetchall(
            "SELECT * FROM export_requests ORDER BY created_at DESC"
        )
        return [ExportRequest.from_row(r) for r in rows]

    def update(self, request: ExportRequest) -> ExportRequest:
        self._execute(
            """UPDATE export_requests SET
               approver_user_id = ?, status = ?,
               output_path = ?, completed_at = ?
               WHERE id = ?""",
            (request.approver_user_id, request.status,
             request.output_path, request.completed_at, request.id),
        )
        return request

    def delete(self, request_id: int) -> None:
        self._execute("DELETE FROM export_requests WHERE id = ?", (request_id,))

    def try_approve(self, request_id: int, approver_user_id: int) -> bool:
        """Atomically approve a pending export request.
        Returns False if another request already touched it.
        """
        cursor = self._execute(
            """UPDATE export_requests
               SET approver_user_id = ?, status = 'approved'
               WHERE id = ? AND status = 'pending'""",
            (approver_user_id, request_id),
        )
        return cursor.rowcount > 0

    def try_reject(self, request_id: int, approver_user_id: int) -> bool:
        cursor = self._execute(
            """UPDATE export_requests
               SET approver_user_id = ?, status = 'rejected'
               WHERE id = ? AND status = 'pending'""",
            (approver_user_id, request_id),
        )
        return cursor.rowcount > 0

    def try_execute(self, request_id: int, now: str) -> bool:
        """Atomically mark an approved export as completed — one-time only."""
        cursor = self._execute(
            """UPDATE export_requests
               SET status = 'completed', completed_at = ?
               WHERE id = ? AND status = 'approved' AND completed_at IS NULL""",
            (now, request_id),
        )
        return cursor.rowcount > 0
