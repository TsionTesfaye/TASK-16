from dataclasses import dataclass
from typing import Optional


@dataclass
class ServiceTable:
    id: Optional[int] = None
    store_id: int = 0
    table_code: str = ""
    area_type: str = ""
    merged_into_id: Optional[int] = None
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "ServiceTable":
        return ServiceTable(
            id=row["id"],
            store_id=row["store_id"],
            table_code=row["table_code"],
            area_type=row["area_type"],
            merged_into_id=row["merged_into_id"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
