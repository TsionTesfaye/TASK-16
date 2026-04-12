from dataclasses import dataclass
from typing import Optional

from ..enums.table_state import TableState


@dataclass
class TableSession:
    id: Optional[int] = None
    store_id: int = 0
    table_id: int = 0
    opened_by_user_id: int = 0
    current_state: str = TableState.AVAILABLE
    merged_group_code: Optional[str] = None
    current_customer_label: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    closed_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "TableSession":
        return TableSession(
            id=row["id"],
            store_id=row["store_id"],
            table_id=row["table_id"],
            opened_by_user_id=row["opened_by_user_id"],
            current_state=row["current_state"],
            merged_group_code=row["merged_group_code"],
            current_customer_label=row["current_customer_label"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=row["closed_at"],
        )
