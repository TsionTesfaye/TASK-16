from typing import List, Optional

from ..models.price_override_request import PriceOverrideRequest
from .base_repository import BaseRepository


class PriceOverrideRequestRepository(BaseRepository):
    def create(self, request: PriceOverrideRequest) -> PriceOverrideRequest:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO price_override_requests (
               ticket_id, store_id, requested_by_user_id,
               approver_user_id, original_payout, proposed_payout,
               reason, status, created_at, approved_at,
               rejected_at, executed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (request.ticket_id, request.store_id, request.requested_by_user_id,
             request.approver_user_id, request.original_payout,
             request.proposed_payout, request.reason, request.status,
             now, request.approved_at, request.rejected_at,
             request.executed_at),
        )
        request.id = cursor.lastrowid
        request.created_at = now
        return request

    def get_by_id(self, request_id: int) -> Optional[PriceOverrideRequest]:
        row = self._fetchone(
            "SELECT * FROM price_override_requests WHERE id = ?", (request_id,)
        )
        return PriceOverrideRequest.from_row(row) if row else None

    def list_by_ticket(self, ticket_id: int) -> List[PriceOverrideRequest]:
        rows = self._fetchall(
            """SELECT * FROM price_override_requests
               WHERE ticket_id = ? ORDER BY created_at DESC""",
            (ticket_id,),
        )
        return [PriceOverrideRequest.from_row(r) for r in rows]

    def list_pending_by_store(self, store_id: int) -> List[PriceOverrideRequest]:
        rows = self._fetchall(
            """SELECT * FROM price_override_requests
               WHERE store_id = ? AND status = 'pending'
               ORDER BY created_at ASC""",
            (store_id,),
        )
        return [PriceOverrideRequest.from_row(r) for r in rows]

    def try_approve(self, request_id: int, approver_user_id: int, now: str) -> bool:
        """Atomically transition `pending` → `approved`.

        Returns False if another request beat us to it. The conditional
        UPDATE is what makes the dual-control flow safe under concurrent
        approver clicks.
        """
        cursor = self._execute(
            """UPDATE price_override_requests
               SET approver_user_id = ?, status = 'approved', approved_at = ?
               WHERE id = ? AND status = 'pending'""",
            (approver_user_id, now, request_id),
        )
        return cursor.rowcount > 0

    def try_reject(self, request_id: int, approver_user_id: int, now: str) -> bool:
        cursor = self._execute(
            """UPDATE price_override_requests
               SET approver_user_id = ?, status = 'rejected', rejected_at = ?
               WHERE id = ? AND status = 'pending'""",
            (approver_user_id, now, request_id),
        )
        return cursor.rowcount > 0

    def try_execute(self, request_id: int, now: str) -> bool:
        """Atomically transition `approved` → `executed`. One-time only."""
        cursor = self._execute(
            """UPDATE price_override_requests
               SET status = 'executed', executed_at = ?
               WHERE id = ? AND status = 'approved' AND executed_at IS NULL""",
            (now, request_id),
        )
        return cursor.rowcount > 0
