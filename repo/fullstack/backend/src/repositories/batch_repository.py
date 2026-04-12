from typing import List, Optional

from ..models.batch import Batch
from .base_repository import BaseRepository


class BatchRepository(BaseRepository):
    def create(self, batch: Batch) -> Batch:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO batches (
               store_id, batch_code, source_ticket_id, status,
               procurement_at, receiving_at, issued_at, finished_goods_at,
               created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (batch.store_id, batch.batch_code, batch.source_ticket_id,
             batch.status, batch.procurement_at, batch.receiving_at,
             batch.issued_at, batch.finished_goods_at, now, now),
        )
        batch.id = cursor.lastrowid
        batch.created_at = now
        batch.updated_at = now
        return batch

    def get_by_id(self, batch_id: int) -> Optional[Batch]:
        row = self._fetchone("SELECT * FROM batches WHERE id = ?", (batch_id,))
        return Batch.from_row(row) if row else None

    def get_by_batch_code(self, batch_code: str) -> Optional[Batch]:
        """Legacy lookup — NOT store-scoped. Kept for migrations/tests
        that don't have a store context. All user-facing callers must
        use `get_by_store_and_batch_code` instead so cross-store leaks
        are impossible at the query layer."""
        row = self._fetchone(
            "SELECT * FROM batches WHERE batch_code = ?", (batch_code,)
        )
        return Batch.from_row(row) if row else None

    def get_by_store_and_batch_code(
        self, store_id: int, batch_code: str
    ) -> Optional[Batch]:
        """Scoped lookup: a batch code is only unique WITHIN a store.
        This is the only safe way to resolve a user-supplied batch code
        because otherwise a caller could reference a foreign store's
        batch and leak its genealogy."""
        row = self._fetchone(
            "SELECT * FROM batches WHERE store_id = ? AND batch_code = ?",
            (store_id, batch_code),
        )
        return Batch.from_row(row) if row else None

    def list_by_store(self, store_id: int, status: Optional[str] = None) -> List[Batch]:
        if status:
            rows = self._fetchall(
                "SELECT * FROM batches WHERE store_id = ? AND status = ? ORDER BY created_at DESC",
                (store_id, status),
            )
        else:
            rows = self._fetchall(
                "SELECT * FROM batches WHERE store_id = ? ORDER BY created_at DESC",
                (store_id,),
            )
        return [Batch.from_row(r) for r in rows]

    def list_by_date_range(
        self, date_start: str, date_end: str, store_id: Optional[int] = None
    ) -> List[Batch]:
        if store_id is not None:
            rows = self._fetchall(
                """SELECT * FROM batches
                   WHERE store_id = ? AND created_at >= ? AND created_at <= ?
                   ORDER BY created_at DESC""",
                (store_id, date_start, date_end),
            )
        else:
            rows = self._fetchall(
                """SELECT * FROM batches
                   WHERE created_at >= ? AND created_at <= ?
                   ORDER BY created_at DESC""",
                (date_start, date_end),
            )
        return [Batch.from_row(r) for r in rows]

    def update(self, batch: Batch) -> Batch:
        now = self._now_utc()
        self._execute(
            """UPDATE batches SET
               batch_code = ?, source_ticket_id = ?, status = ?,
               procurement_at = ?, receiving_at = ?,
               issued_at = ?, finished_goods_at = ?, updated_at = ?
               WHERE id = ?""",
            (batch.batch_code, batch.source_ticket_id, batch.status,
             batch.procurement_at, batch.receiving_at,
             batch.issued_at, batch.finished_goods_at, now, batch.id),
        )
        batch.updated_at = now
        return batch

    def delete(self, batch_id: int) -> None:
        self._execute("DELETE FROM batches WHERE id = ?", (batch_id,))
