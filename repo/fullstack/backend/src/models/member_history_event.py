from dataclasses import dataclass
from typing import Optional


@dataclass
class MemberHistoryEvent:
    id: Optional[int] = None
    member_id: int = 0
    actor_user_id: int = 0
    event_type: str = ""
    before_json: Optional[str] = None
    after_json: Optional[str] = None
    created_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "MemberHistoryEvent":
        return MemberHistoryEvent(
            id=row["id"],
            member_id=row["member_id"],
            actor_user_id=row["actor_user_id"],
            event_type=row["event_type"],
            before_json=row["before_json"],
            after_json=row["after_json"],
            created_at=row["created_at"],
        )
