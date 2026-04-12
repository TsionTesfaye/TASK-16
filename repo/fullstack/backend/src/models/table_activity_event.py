from dataclasses import dataclass
from typing import Optional


@dataclass
class TableActivityEvent:
    id: Optional[int] = None
    table_session_id: int = 0
    actor_user_id: int = 0
    event_type: str = ""
    before_state: Optional[str] = None
    after_state: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "TableActivityEvent":
        return TableActivityEvent(
            id=row["id"],
            table_session_id=row["table_session_id"],
            actor_user_id=row["actor_user_id"],
            event_type=row["event_type"],
            before_state=row["before_state"],
            after_state=row["after_state"],
            notes=row["notes"],
            created_at=row["created_at"],
        )
