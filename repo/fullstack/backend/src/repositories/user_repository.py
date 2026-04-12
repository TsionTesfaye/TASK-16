from typing import List, Optional

from ..models.user import User
from .base_repository import BaseRepository


class UserRepository(BaseRepository):
    def create(self, user: User) -> User:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO users (store_id, username, password_hash, display_name, role,
               is_active, is_frozen, password_changed_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user.store_id, user.username, user.password_hash,
             user.display_name, user.role,
             int(user.is_active), int(user.is_frozen),
             user.password_changed_at, now, now),
        )
        user.id = cursor.lastrowid
        user.created_at = now
        user.updated_at = now
        return user

    def get_by_id(self, user_id: int) -> Optional[User]:
        row = self._fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
        return User.from_row(row) if row else None

    def get_by_username(self, username: str) -> Optional[User]:
        row = self._fetchone("SELECT * FROM users WHERE username = ?", (username,))
        return User.from_row(row) if row else None

    def list_by_store(self, store_id: int, active_only: bool = False) -> List[User]:
        if active_only:
            rows = self._fetchall(
                "SELECT * FROM users WHERE store_id = ? AND is_active = 1 ORDER BY username",
                (store_id,),
            )
        else:
            rows = self._fetchall(
                "SELECT * FROM users WHERE store_id = ? ORDER BY username",
                (store_id,),
            )
        return [User.from_row(r) for r in rows]

    def list_all(self, active_only: bool = False) -> List[User]:
        if active_only:
            rows = self._fetchall("SELECT * FROM users WHERE is_active = 1 ORDER BY username")
        else:
            rows = self._fetchall("SELECT * FROM users ORDER BY username")
        return [User.from_row(r) for r in rows]

    def list_by_role(self, role: str, store_id: Optional[int] = None) -> List[User]:
        if store_id is not None:
            rows = self._fetchall(
                "SELECT * FROM users WHERE role = ? AND store_id = ? ORDER BY username",
                (role, store_id),
            )
        else:
            rows = self._fetchall(
                "SELECT * FROM users WHERE role = ? ORDER BY username",
                (role,),
            )
        return [User.from_row(r) for r in rows]

    def update(self, user: User) -> User:
        now = self._now_utc()
        self._execute(
            """UPDATE users SET store_id = ?, username = ?, password_hash = ?,
               display_name = ?, role = ?, is_active = ?, is_frozen = ?,
               password_changed_at = ?, updated_at = ?
               WHERE id = ?""",
            (user.store_id, user.username, user.password_hash,
             user.display_name, user.role,
             int(user.is_active), int(user.is_frozen),
             user.password_changed_at, now, user.id),
        )
        user.updated_at = now
        return user

    def delete(self, user_id: int) -> None:
        self._execute("DELETE FROM users WHERE id = ?", (user_id,))

    def count_by_role(self, role: str) -> int:
        row = self._fetchone(
            "SELECT COUNT(*) as cnt FROM users WHERE role = ?", (role,)
        )
        return row["cnt"] if row else 0
