from typing import List, Optional

from ..models.user_session import UserSession
from .base_repository import BaseRepository


class UserSessionRepository(BaseRepository):
    def create(self, session: UserSession) -> UserSession:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO user_sessions (user_id, session_nonce, cookie_signature_version,
               csrf_secret, client_device_id, issued_at, expires_at, last_seen_at, revoked_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session.user_id, session.session_nonce, session.cookie_signature_version,
             session.csrf_secret, session.client_device_id,
             now, session.expires_at, now, session.revoked_at),
        )
        session.id = cursor.lastrowid
        session.issued_at = now
        session.last_seen_at = now
        return session

    def get_by_id(self, session_id: int) -> Optional[UserSession]:
        row = self._fetchone("SELECT * FROM user_sessions WHERE id = ?", (session_id,))
        return UserSession.from_row(row) if row else None

    def get_by_nonce(self, nonce: str) -> Optional[UserSession]:
        row = self._fetchone(
            "SELECT * FROM user_sessions WHERE session_nonce = ?", (nonce,)
        )
        return UserSession.from_row(row) if row else None

    def list_by_user(self, user_id: int) -> List[UserSession]:
        rows = self._fetchall(
            "SELECT * FROM user_sessions WHERE user_id = ? ORDER BY issued_at DESC",
            (user_id,),
        )
        return [UserSession.from_row(r) for r in rows]

    def list_active_by_user(self, user_id: int) -> List[UserSession]:
        rows = self._fetchall(
            """SELECT * FROM user_sessions
               WHERE user_id = ? AND revoked_at IS NULL
               ORDER BY issued_at DESC""",
            (user_id,),
        )
        return [UserSession.from_row(r) for r in rows]

    def update(self, session: UserSession) -> UserSession:
        self._execute(
            """UPDATE user_sessions SET last_seen_at = ?, revoked_at = ?
               WHERE id = ?""",
            (session.last_seen_at, session.revoked_at, session.id),
        )
        return session

    def revoke(self, session_id: int) -> None:
        now = self._now_utc()
        self._execute(
            "UPDATE user_sessions SET revoked_at = ? WHERE id = ?",
            (now, session_id),
        )

    def revoke_all_for_user(self, user_id: int) -> None:
        now = self._now_utc()
        self._execute(
            "UPDATE user_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
            (now, user_id),
        )

    def delete(self, session_id: int) -> None:
        self._execute("DELETE FROM user_sessions WHERE id = ?", (session_id,))
