from dataclasses import dataclass
from typing import Optional


@dataclass
class RecallRun:
    id: Optional[int] = None
    store_id: Optional[int] = None
    requested_by_user_id: int = 0
    batch_filter: Optional[str] = None
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    result_count: int = 0
    result_json: Optional[str] = None
    output_path: Optional[str] = None
    created_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "RecallRun":
        return RecallRun(
            id=row["id"],
            store_id=row["store_id"],
            requested_by_user_id=row["requested_by_user_id"],
            batch_filter=row["batch_filter"],
            date_start=row["date_start"],
            date_end=row["date_end"],
            result_count=row["result_count"],
            result_json=row["result_json"] if "result_json" in row.keys() else None,
            output_path=row["output_path"],
            created_at=row["created_at"],
        )
