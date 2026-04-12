from typing import List, Optional

from ..models.qc_inspection import QCInspection
from .base_repository import BaseRepository


class QCInspectionRepository(BaseRepository):
    def create(self, inspection: QCInspection) -> QCInspection:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO qc_inspections (
               ticket_id, inspector_user_id, actual_weight_lbs,
               lot_size, sample_size, nonconformance_count,
               inspection_outcome, quarantine_required, notes,
               created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (inspection.ticket_id, inspection.inspector_user_id,
             inspection.actual_weight_lbs, inspection.lot_size,
             inspection.sample_size, inspection.nonconformance_count,
             inspection.inspection_outcome, int(inspection.quarantine_required),
             inspection.notes, now, now),
        )
        inspection.id = cursor.lastrowid
        inspection.created_at = now
        inspection.updated_at = now
        return inspection

    def get_by_id(self, inspection_id: int) -> Optional[QCInspection]:
        row = self._fetchone(
            "SELECT * FROM qc_inspections WHERE id = ?", (inspection_id,)
        )
        return QCInspection.from_row(row) if row else None

    def get_by_ticket(self, ticket_id: int) -> Optional[QCInspection]:
        row = self._fetchone(
            "SELECT * FROM qc_inspections WHERE ticket_id = ? ORDER BY created_at DESC LIMIT 1",
            (ticket_id,),
        )
        return QCInspection.from_row(row) if row else None

    def list_by_ticket(self, ticket_id: int) -> List[QCInspection]:
        rows = self._fetchall(
            "SELECT * FROM qc_inspections WHERE ticket_id = ? ORDER BY created_at DESC",
            (ticket_id,),
        )
        return [QCInspection.from_row(r) for r in rows]

    def list_by_inspector(self, inspector_user_id: int) -> List[QCInspection]:
        rows = self._fetchall(
            "SELECT * FROM qc_inspections WHERE inspector_user_id = ? ORDER BY created_at DESC",
            (inspector_user_id,),
        )
        return [QCInspection.from_row(r) for r in rows]

    def count_nonconformances_for_date(self, store_id: int, date_str: str) -> int:
        row = self._fetchone(
            """SELECT COALESCE(SUM(qi.nonconformance_count), 0) as total
               FROM qc_inspections qi
               JOIN buyback_tickets bt ON bt.id = qi.ticket_id
               WHERE bt.store_id = ? AND qi.created_at LIKE ?""",
            (store_id, date_str + "%"),
        )
        return row["total"] if row else 0

    def update(self, inspection: QCInspection) -> QCInspection:
        now = self._now_utc()
        self._execute(
            """UPDATE qc_inspections SET
               actual_weight_lbs = ?, lot_size = ?, sample_size = ?,
               nonconformance_count = ?, inspection_outcome = ?,
               quarantine_required = ?, notes = ?, updated_at = ?
               WHERE id = ?""",
            (inspection.actual_weight_lbs, inspection.lot_size,
             inspection.sample_size, inspection.nonconformance_count,
             inspection.inspection_outcome, int(inspection.quarantine_required),
             inspection.notes, now, inspection.id),
        )
        inspection.updated_at = now
        return inspection

    def delete(self, inspection_id: int) -> None:
        self._execute("DELETE FROM qc_inspections WHERE id = ?", (inspection_id,))
