from dataclasses import dataclass
from typing import Optional

from ..enums.member_status import MemberStatus


@dataclass
class Member:
    id: Optional[int] = None
    club_organization_id: int = 0
    full_name: str = ""
    status: str = MemberStatus.ACTIVE
    joined_at: Optional[str] = None
    left_at: Optional[str] = None
    transferred_at: Optional[str] = None
    current_group: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "Member":
        return Member(
            id=row["id"],
            club_organization_id=row["club_organization_id"],
            full_name=row["full_name"],
            status=row["status"],
            joined_at=row["joined_at"],
            left_at=row["left_at"],
            transferred_at=row["transferred_at"],
            current_group=row["current_group"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
