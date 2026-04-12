from dataclasses import dataclass
from typing import Optional


@dataclass
class NotificationTemplate:
    id: Optional[int] = None
    store_id: Optional[int] = None
    template_code: str = ""
    name: str = ""
    body: str = ""
    event_type: str = ""
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "NotificationTemplate":
        return NotificationTemplate(
            id=row["id"],
            store_id=row["store_id"],
            template_code=row["template_code"],
            name=row["name"],
            body=row["body"],
            event_type=row["event_type"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
