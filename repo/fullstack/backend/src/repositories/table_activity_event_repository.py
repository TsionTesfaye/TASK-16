from typing import List, Optional

from ..models.table_activity_event import TableActivityEvent
from .base_repository import BaseRepository


class TableActivityEventRepository(BaseRepository):
    def create(self, event: TableActivityEvent) -> TableActivityEvent:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO table_activity_events (
               table_session_id, actor_user_id, event_type,
               before_state, after_state, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event.table_session_id, event.actor_user_id, event.event_type,
             event.before_state, event.after_state, event.notes, now),
        )
        event.id = cursor.lastrowid
        event.created_at = now
        return event

    def get_by_id(self, event_id: int) -> Optional[TableActivityEvent]:
        row = self._fetchone(
            "SELECT * FROM table_activity_events WHERE id = ?", (event_id,)
        )
        return TableActivityEvent.from_row(row) if row else None

    def list_by_session(self, table_session_id: int) -> List[TableActivityEvent]:
        rows = self._fetchall(
            "SELECT * FROM table_activity_events WHERE table_session_id = ? ORDER BY created_at ASC",
            (table_session_id,),
        )
        return [TableActivityEvent.from_row(r) for r in rows]

    def list_all(self) -> List[TableActivityEvent]:
        rows = self._fetchall(
            "SELECT * FROM table_activity_events ORDER BY created_at DESC"
        )
        return [TableActivityEvent.from_row(r) for r in rows]

    def delete(self, event_id: int) -> None:
        self._execute(
            "DELETE FROM table_activity_events WHERE id = ?", (event_id,)
        )
