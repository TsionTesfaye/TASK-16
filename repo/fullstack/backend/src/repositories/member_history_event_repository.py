from typing import List, Optional

from ..models.member_history_event import MemberHistoryEvent
from .base_repository import BaseRepository


class MemberHistoryEventRepository(BaseRepository):
    def create(self, event: MemberHistoryEvent) -> MemberHistoryEvent:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO member_history_events (
               member_id, actor_user_id, event_type,
               before_json, after_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (event.member_id, event.actor_user_id, event.event_type,
             event.before_json, event.after_json, now),
        )
        event.id = cursor.lastrowid
        event.created_at = now
        return event

    def get_by_id(self, event_id: int) -> Optional[MemberHistoryEvent]:
        row = self._fetchone(
            "SELECT * FROM member_history_events WHERE id = ?", (event_id,)
        )
        return MemberHistoryEvent.from_row(row) if row else None

    def list_by_member(self, member_id: int) -> List[MemberHistoryEvent]:
        rows = self._fetchall(
            "SELECT * FROM member_history_events WHERE member_id = ? ORDER BY created_at ASC",
            (member_id,),
        )
        return [MemberHistoryEvent.from_row(r) for r in rows]

    def list_all(self) -> List[MemberHistoryEvent]:
        rows = self._fetchall(
            "SELECT * FROM member_history_events ORDER BY created_at DESC"
        )
        return [MemberHistoryEvent.from_row(r) for r in rows]

    def delete(self, event_id: int) -> None:
        self._execute(
            "DELETE FROM member_history_events WHERE id = ?", (event_id,)
        )
