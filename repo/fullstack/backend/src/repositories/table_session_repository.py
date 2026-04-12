from typing import List, Optional

from ..models.table_session import TableSession
from .base_repository import BaseRepository


class TableSessionRepository(BaseRepository):
    def create(self, session: TableSession) -> TableSession:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO table_sessions (
               store_id, table_id, opened_by_user_id, current_state,
               merged_group_code, current_customer_label,
               created_at, updated_at, closed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session.store_id, session.table_id, session.opened_by_user_id,
             session.current_state, session.merged_group_code,
             session.current_customer_label, now, now, session.closed_at),
        )
        session.id = cursor.lastrowid
        session.created_at = now
        session.updated_at = now
        return session

    def get_by_id(self, session_id: int) -> Optional[TableSession]:
        row = self._fetchone(
            "SELECT * FROM table_sessions WHERE id = ?", (session_id,)
        )
        return TableSession.from_row(row) if row else None

    def get_active_by_table(self, table_id: int) -> Optional[TableSession]:
        row = self._fetchone(
            """SELECT * FROM table_sessions
               WHERE table_id = ? AND closed_at IS NULL
               ORDER BY created_at DESC LIMIT 1""",
            (table_id,),
        )
        return TableSession.from_row(row) if row else None

    def list_by_store(self, store_id: int, state: Optional[str] = None) -> List[TableSession]:
        if state:
            rows = self._fetchall(
                """SELECT * FROM table_sessions
                   WHERE store_id = ? AND current_state = ? AND closed_at IS NULL
                   ORDER BY created_at DESC""",
                (store_id, state),
            )
        else:
            rows = self._fetchall(
                "SELECT * FROM table_sessions WHERE store_id = ? ORDER BY created_at DESC",
                (store_id,),
            )
        return [TableSession.from_row(r) for r in rows]

    def list_by_merged_group(self, merged_group_code: str) -> List[TableSession]:
        rows = self._fetchall(
            "SELECT * FROM table_sessions WHERE merged_group_code = ? ORDER BY created_at ASC",
            (merged_group_code,),
        )
        return [TableSession.from_row(r) for r in rows]

    def update(self, session: TableSession) -> TableSession:
        now = self._now_utc()
        self._execute(
            """UPDATE table_sessions SET
               current_state = ?, merged_group_code = ?,
               current_customer_label = ?, updated_at = ?, closed_at = ?
               WHERE id = ?""",
            (session.current_state, session.merged_group_code,
             session.current_customer_label, now,
             session.closed_at, session.id),
        )
        session.updated_at = now
        return session

    def delete(self, session_id: int) -> None:
        self._execute("DELETE FROM table_sessions WHERE id = ?", (session_id,))
