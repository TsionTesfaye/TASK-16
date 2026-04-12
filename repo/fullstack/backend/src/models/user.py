from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    id: Optional[int] = None
    store_id: Optional[int] = None
    username: str = ""
    password_hash: str = ""
    display_name: str = ""
    role: str = ""
    is_active: bool = True
    is_frozen: bool = False
    password_changed_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "User":
        return User(
            id=row["id"],
            store_id=row["store_id"],
            username=row["username"],
            password_hash=row["password_hash"],
            display_name=row["display_name"],
            role=row["role"],
            is_active=bool(row["is_active"]),
            is_frozen=bool(row["is_frozen"]),
            password_changed_at=row["password_changed_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
