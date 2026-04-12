from dataclasses import dataclass
from typing import Optional


@dataclass
class QCInspection:
    id: Optional[int] = None
    ticket_id: int = 0
    inspector_user_id: int = 0
    actual_weight_lbs: float = 0.0
    lot_size: int = 0
    sample_size: int = 0
    nonconformance_count: int = 0
    inspection_outcome: str = ""
    quarantine_required: bool = False
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "QCInspection":
        return QCInspection(
            id=row["id"],
            ticket_id=row["ticket_id"],
            inspector_user_id=row["inspector_user_id"],
            actual_weight_lbs=row["actual_weight_lbs"],
            lot_size=row["lot_size"],
            sample_size=row["sample_size"],
            nonconformance_count=row["nonconformance_count"],
            inspection_outcome=row["inspection_outcome"],
            quarantine_required=bool(row["quarantine_required"]),
            notes=row["notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
