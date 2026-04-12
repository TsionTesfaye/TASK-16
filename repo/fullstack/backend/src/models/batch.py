from dataclasses import dataclass
from typing import Optional

from ..enums.batch_status import BatchStatus


@dataclass
class Batch:
    id: Optional[int] = None
    store_id: int = 0
    batch_code: str = ""
    source_ticket_id: Optional[int] = None
    status: str = BatchStatus.PROCURED
    procurement_at: Optional[str] = None
    receiving_at: Optional[str] = None
    issued_at: Optional[str] = None
    finished_goods_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "Batch":
        return Batch(
            id=row["id"],
            store_id=row["store_id"],
            batch_code=row["batch_code"],
            source_ticket_id=row["source_ticket_id"],
            status=row["status"],
            procurement_at=row["procurement_at"],
            receiving_at=row["receiving_at"],
            issued_at=row["issued_at"],
            finished_goods_at=row["finished_goods_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
