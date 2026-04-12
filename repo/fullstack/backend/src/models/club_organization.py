from dataclasses import dataclass
from typing import Optional


@dataclass
class ClubOrganization:
    id: Optional[int] = None
    name: str = ""
    department: Optional[str] = None
    route_code: Optional[str] = None
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "ClubOrganization":
        return ClubOrganization(
            id=row["id"],
            name=row["name"],
            department=row["department"],
            route_code=row["route_code"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
