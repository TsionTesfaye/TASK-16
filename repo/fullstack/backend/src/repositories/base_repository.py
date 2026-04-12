import sqlite3
from datetime import datetime, timezone
from typing import List, Optional


class BaseRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def _fetchone(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        cursor = self.conn.execute(sql, params)
        return cursor.fetchone()

    def _fetchall(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        cursor = self.conn.execute(sql, params)
        return cursor.fetchall()
