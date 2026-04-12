from typing import List, Optional

from ..models.quarantine_record import QuarantineRecord
from .base_repository import BaseRepository


class QuarantineRecordRepository(BaseRepository):
    def create(self, record: QuarantineRecord) -> QuarantineRecord:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO quarantine_records (
               ticket_id, batch_id, created_by_user_id, disposition,
               concession_signed_by, due_back_to_customer_at, notes,
               created_at, resolved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (record.ticket_id, record.batch_id, record.created_by_user_id,
             record.disposition, record.concession_signed_by,
             record.due_back_to_customer_at, record.notes,
             now, record.resolved_at),
        )
        record.id = cursor.lastrowid
        record.created_at = now
        return record

    def get_by_id(self, record_id: int) -> Optional[QuarantineRecord]:
        row = self._fetchone(
            "SELECT * FROM quarantine_records WHERE id = ?", (record_id,)
        )
        return QuarantineRecord.from_row(row) if row else None

    def list_by_ticket(self, ticket_id: int) -> List[QuarantineRecord]:
        rows = self._fetchall(
            "SELECT * FROM quarantine_records WHERE ticket_id = ? ORDER BY created_at DESC",
            (ticket_id,),
        )
        return [QuarantineRecord.from_row(r) for r in rows]

    def list_by_batch(self, batch_id: int) -> List[QuarantineRecord]:
        rows = self._fetchall(
            "SELECT * FROM quarantine_records WHERE batch_id = ? ORDER BY created_at DESC",
            (batch_id,),
        )
        return [QuarantineRecord.from_row(r) for r in rows]

    def list_unresolved(self) -> List[QuarantineRecord]:
        rows = self._fetchall(
            "SELECT * FROM quarantine_records WHERE resolved_at IS NULL ORDER BY created_at ASC"
        )
        return [QuarantineRecord.from_row(r) for r in rows]

    def list_overdue_returns(self, current_date: str) -> List[QuarantineRecord]:
        """List quarantines that are past their SLA deadline and still
        unresolved. The SLA deadline is populated at quarantine creation
        time (see `QCService.create_quarantine`) regardless of what the
        eventual disposition will be.
        """
        rows = self._fetchall(
            """SELECT * FROM quarantine_records
               WHERE resolved_at IS NULL
               AND due_back_to_customer_at IS NOT NULL
               AND due_back_to_customer_at < ?
               ORDER BY due_back_to_customer_at ASC""",
            (current_date,),
        )
        return [QuarantineRecord.from_row(r) for r in rows]

    def update(self, record: QuarantineRecord) -> QuarantineRecord:
        self._execute(
            """UPDATE quarantine_records SET
               disposition = ?, concession_signed_by = ?,
               due_back_to_customer_at = ?, notes = ?, resolved_at = ?
               WHERE id = ?""",
            (record.disposition, record.concession_signed_by,
             record.due_back_to_customer_at, record.notes,
             record.resolved_at, record.id),
        )
        return record

    def delete(self, record_id: int) -> None:
        self._execute("DELETE FROM quarantine_records WHERE id = ?", (record_id,))
