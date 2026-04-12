from typing import List, Optional

from ..models.ticket_message_log import TicketMessageLog
from .base_repository import BaseRepository


class TicketMessageLogRepository(BaseRepository):
    def create(self, log: TicketMessageLog) -> TicketMessageLog:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO ticket_message_logs (
               ticket_id, template_id, actor_user_id, message_body,
               contact_channel, call_attempt_status, retry_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (log.ticket_id, log.template_id, log.actor_user_id,
             log.message_body, log.contact_channel,
             log.call_attempt_status, log.retry_at, now),
        )
        log.id = cursor.lastrowid
        log.created_at = now
        return log

    def get_by_id(self, log_id: int) -> Optional[TicketMessageLog]:
        row = self._fetchone(
            "SELECT * FROM ticket_message_logs WHERE id = ?", (log_id,)
        )
        return TicketMessageLog.from_row(row) if row else None

    def list_by_ticket(self, ticket_id: int) -> List[TicketMessageLog]:
        rows = self._fetchall(
            "SELECT * FROM ticket_message_logs WHERE ticket_id = ? ORDER BY created_at ASC",
            (ticket_id,),
        )
        return [TicketMessageLog.from_row(r) for r in rows]

    def list_pending_retries(self, before_time: str) -> List[TicketMessageLog]:
        """All pending retries across all stores. Used by the scheduler
        and by admins; the user-facing route MUST instead call
        `list_pending_retries_by_store` to avoid cross-store leaks."""
        rows = self._fetchall(
            """SELECT * FROM ticket_message_logs
               WHERE retry_at IS NOT NULL AND retry_at <= ?
               ORDER BY retry_at ASC""",
            (before_time,),
        )
        return [TicketMessageLog.from_row(r) for r in rows]

    def list_pending_retries_by_store(
        self, store_id: int, before_time: str
    ) -> List[TicketMessageLog]:
        """Store-scoped pending retries. Joins on `buyback_tickets` so
        only messages whose parent ticket belongs to the given store
        are returned."""
        rows = self._fetchall(
            """SELECT m.* FROM ticket_message_logs m
               INNER JOIN buyback_tickets t ON t.id = m.ticket_id
               WHERE m.retry_at IS NOT NULL
                 AND m.retry_at <= ?
                 AND t.store_id = ?
               ORDER BY m.retry_at ASC""",
            (before_time, store_id),
        )
        return [TicketMessageLog.from_row(r) for r in rows]

    def list_failed_attempts_by_ticket(self, ticket_id: int) -> List[TicketMessageLog]:
        rows = self._fetchall(
            """SELECT * FROM ticket_message_logs
               WHERE ticket_id = ? AND call_attempt_status = 'failed'
               ORDER BY created_at DESC""",
            (ticket_id,),
        )
        return [TicketMessageLog.from_row(r) for r in rows]

    def delete(self, log_id: int) -> None:
        self._execute(
            "DELETE FROM ticket_message_logs WHERE id = ?", (log_id,)
        )
