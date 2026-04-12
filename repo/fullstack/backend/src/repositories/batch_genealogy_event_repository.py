from typing import List, Optional

from ..models.batch_genealogy_event import BatchGenealogyEvent
from .base_repository import BaseRepository


class BatchGenealogyEventRepository(BaseRepository):
    def create(self, event: BatchGenealogyEvent) -> BatchGenealogyEvent:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO batch_genealogy_events (
               batch_id, parent_batch_id, child_batch_id, event_type,
               actor_user_id, location_context, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event.batch_id, event.parent_batch_id, event.child_batch_id,
             event.event_type, event.actor_user_id, event.location_context,
             now, event.metadata_json),
        )
        event.id = cursor.lastrowid
        event.created_at = now
        return event

    def get_by_id(self, event_id: int) -> Optional[BatchGenealogyEvent]:
        row = self._fetchone(
            "SELECT * FROM batch_genealogy_events WHERE id = ?", (event_id,)
        )
        return BatchGenealogyEvent.from_row(row) if row else None

    def list_by_batch(self, batch_id: int) -> List[BatchGenealogyEvent]:
        rows = self._fetchall(
            "SELECT * FROM batch_genealogy_events WHERE batch_id = ? ORDER BY created_at ASC",
            (batch_id,),
        )
        return [BatchGenealogyEvent.from_row(r) for r in rows]

    def list_by_event_type(self, event_type: str) -> List[BatchGenealogyEvent]:
        rows = self._fetchall(
            "SELECT * FROM batch_genealogy_events WHERE event_type = ? ORDER BY created_at ASC",
            (event_type,),
        )
        return [BatchGenealogyEvent.from_row(r) for r in rows]

    def list_by_date_range(
        self, date_start: str, date_end: str
    ) -> List[BatchGenealogyEvent]:
        """Unscoped date-range query — retained for back-compat, but
        user-facing callers must use `list_by_store_and_date_range` so
        genealogy events cannot leak across store boundaries."""
        rows = self._fetchall(
            """SELECT * FROM batch_genealogy_events
               WHERE created_at >= ? AND created_at <= ?
               ORDER BY created_at ASC""",
            (date_start, date_end),
        )
        return [BatchGenealogyEvent.from_row(r) for r in rows]

    def list_by_store_and_date_range(
        self, store_id: int, date_start: str, date_end: str
    ) -> List[BatchGenealogyEvent]:
        """Store-scoped date-range query. Joins against `batches` so
        only events belonging to the actor's store are returned. Used by
        recall generation where a blanket cross-store sweep must never
        happen."""
        rows = self._fetchall(
            """SELECT e.* FROM batch_genealogy_events e
               INNER JOIN batches b ON b.id = e.batch_id
               WHERE b.store_id = ?
                 AND e.created_at >= ?
                 AND e.created_at <= ?
               ORDER BY e.created_at ASC""",
            (store_id, date_start, date_end),
        )
        return [BatchGenealogyEvent.from_row(r) for r in rows]

    def list_by_batch_and_date_range(
        self, batch_id: int, date_start: str, date_end: str
    ) -> List[BatchGenealogyEvent]:
        rows = self._fetchall(
            """SELECT * FROM batch_genealogy_events
               WHERE batch_id = ? AND created_at >= ? AND created_at <= ?
               ORDER BY created_at ASC""",
            (batch_id, date_start, date_end),
        )
        return [BatchGenealogyEvent.from_row(r) for r in rows]

    def delete(self, event_id: int) -> None:
        self._execute(
            "DELETE FROM batch_genealogy_events WHERE id = ?", (event_id,)
        )
