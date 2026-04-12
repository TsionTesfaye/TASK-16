from dataclasses import dataclass
from typing import Optional


@dataclass
class QuarantineRecord:
    id: Optional[int] = None
    ticket_id: int = 0
    batch_id: int = 0
    created_by_user_id: int = 0
    disposition: Optional[str] = None
    concession_signed_by: Optional[int] = None
    due_back_to_customer_at: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    resolved_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "QuarantineRecord":
        return QuarantineRecord(
            id=row["id"],
            ticket_id=row["ticket_id"],
            batch_id=row["batch_id"],
            created_by_user_id=row["created_by_user_id"],
            disposition=row["disposition"],
            concession_signed_by=row["concession_signed_by"],
            due_back_to_customer_at=row["due_back_to_customer_at"],
            notes=row["notes"],
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
        )
