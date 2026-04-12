from typing import List, Optional

from ..models.buyback_ticket import BuybackTicket
from .base_repository import BaseRepository


class BuybackTicketRepository(BaseRepository):
    def create(self, ticket: BuybackTicket) -> BuybackTicket:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO buyback_tickets (
               store_id, created_by_user_id, customer_name,
               customer_phone_ciphertext, customer_phone_iv, customer_phone_last4,
               customer_phone_preference, clothing_category, condition_grade,
               estimated_weight_lbs, actual_weight_lbs,
               estimated_base_rate, estimated_bonus_pct, estimated_payout, estimated_cap_applied,
               actual_base_rate, actual_bonus_pct, final_payout, final_cap_applied,
               variance_amount, variance_pct,
               status, qc_result, qc_notes, current_batch_id,
               created_at, updated_at, completed_at, refunded_at,
               refund_amount, refund_initiated_by_user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ticket.store_id, ticket.created_by_user_id, ticket.customer_name,
             ticket.customer_phone_ciphertext, ticket.customer_phone_iv,
             ticket.customer_phone_last4, ticket.customer_phone_preference,
             ticket.clothing_category, ticket.condition_grade,
             ticket.estimated_weight_lbs, ticket.actual_weight_lbs,
             ticket.estimated_base_rate, ticket.estimated_bonus_pct,
             ticket.estimated_payout, int(ticket.estimated_cap_applied),
             ticket.actual_base_rate, ticket.actual_bonus_pct,
             ticket.final_payout,
             int(ticket.final_cap_applied) if ticket.final_cap_applied is not None else None,
             ticket.variance_amount, ticket.variance_pct,
             ticket.status, ticket.qc_result, ticket.qc_notes,
             ticket.current_batch_id,
             now, now, ticket.completed_at, ticket.refunded_at,
             ticket.refund_amount, ticket.refund_initiated_by_user_id),
        )
        ticket.id = cursor.lastrowid
        ticket.created_at = now
        ticket.updated_at = now
        return ticket

    def get_by_id(self, ticket_id: int) -> Optional[BuybackTicket]:
        row = self._fetchone("SELECT * FROM buyback_tickets WHERE id = ?", (ticket_id,))
        return BuybackTicket.from_row(row) if row else None

    def list_by_store(self, store_id: int, status: Optional[str] = None) -> List[BuybackTicket]:
        if status:
            rows = self._fetchall(
                "SELECT * FROM buyback_tickets WHERE store_id = ? AND status = ? ORDER BY created_at DESC",
                (store_id, status),
            )
        else:
            rows = self._fetchall(
                "SELECT * FROM buyback_tickets WHERE store_id = ? ORDER BY created_at DESC",
                (store_id,),
            )
        return [BuybackTicket.from_row(r) for r in rows]

    def list_by_store_and_date_range(
        self, store_id: int, date_start: str, date_end: str
    ) -> List[BuybackTicket]:
        rows = self._fetchall(
            """SELECT * FROM buyback_tickets
               WHERE store_id = ? AND created_at >= ? AND created_at <= ?
               ORDER BY created_at DESC""",
            (store_id, date_start, date_end),
        )
        return [BuybackTicket.from_row(r) for r in rows]

    def update(self, ticket: BuybackTicket) -> BuybackTicket:
        now = self._now_utc()
        self._execute(
            """UPDATE buyback_tickets SET
               customer_name = ?, customer_phone_ciphertext = ?, customer_phone_iv = ?,
               customer_phone_last4 = ?, customer_phone_preference = ?,
               clothing_category = ?, condition_grade = ?,
               estimated_weight_lbs = ?, actual_weight_lbs = ?,
               estimated_base_rate = ?, estimated_bonus_pct = ?,
               estimated_payout = ?, estimated_cap_applied = ?,
               actual_base_rate = ?, actual_bonus_pct = ?,
               final_payout = ?, final_cap_applied = ?,
               variance_amount = ?, variance_pct = ?,
               status = ?, qc_result = ?, qc_notes = ?,
               current_batch_id = ?, updated_at = ?,
               completed_at = ?, refunded_at = ?,
               refund_amount = ?, refund_initiated_by_user_id = ?
               WHERE id = ?""",
            (ticket.customer_name, ticket.customer_phone_ciphertext,
             ticket.customer_phone_iv, ticket.customer_phone_last4,
             ticket.customer_phone_preference,
             ticket.clothing_category, ticket.condition_grade,
             ticket.estimated_weight_lbs, ticket.actual_weight_lbs,
             ticket.estimated_base_rate, ticket.estimated_bonus_pct,
             ticket.estimated_payout, int(ticket.estimated_cap_applied),
             ticket.actual_base_rate, ticket.actual_bonus_pct,
             ticket.final_payout,
             int(ticket.final_cap_applied) if ticket.final_cap_applied is not None else None,
             ticket.variance_amount, ticket.variance_pct,
             ticket.status, ticket.qc_result, ticket.qc_notes,
             ticket.current_batch_id, now,
             ticket.completed_at, ticket.refunded_at,
             ticket.refund_amount, ticket.refund_initiated_by_user_id,
             ticket.id),
        )
        ticket.updated_at = now
        return ticket

    def delete(self, ticket_id: int) -> None:
        self._execute("DELETE FROM buyback_tickets WHERE id = ?", (ticket_id,))

    def count_by_store_and_status(self, store_id: int, status: str) -> int:
        row = self._fetchone(
            "SELECT COUNT(*) as cnt FROM buyback_tickets WHERE store_id = ? AND status = ?",
            (store_id, status),
        )
        return row["cnt"] if row else 0

    def try_transition_status(
        self, ticket_id: int, from_status: str, to_status: str,
        completed_at: Optional[str] = None, refunded_at: Optional[str] = None,
    ) -> bool:
        """Atomically transition a ticket from one status to another.

        Returns True if the transition succeeded; False if the ticket is no
        longer in from_status (e.g., another request changed it concurrently).
        """
        now = self._now_utc()
        cursor = self._execute(
            """UPDATE buyback_tickets
               SET status = ?, updated_at = ?,
                   completed_at = COALESCE(?, completed_at),
                   refunded_at = COALESCE(?, refunded_at)
               WHERE id = ? AND status = ?""",
            (to_status, now, completed_at, refunded_at, ticket_id, from_status),
        )
        return cursor.rowcount > 0
