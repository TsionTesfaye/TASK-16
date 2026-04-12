from dataclasses import dataclass
from typing import Optional


@dataclass
class PriceOverrideRequest:
    """A request to manually override a ticket's payout.

    Travels through the dual-control state machine:
        pending → approved → executed
        pending → rejected
        pending → expired   (scheduler cleanup)
    """
    id: Optional[int] = None
    ticket_id: int = 0
    store_id: int = 0
    requested_by_user_id: int = 0
    approver_user_id: Optional[int] = None
    original_payout: float = 0.0
    proposed_payout: float = 0.0
    reason: str = ""
    status: str = "pending"
    created_at: Optional[str] = None
    approved_at: Optional[str] = None
    rejected_at: Optional[str] = None
    executed_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "PriceOverrideRequest":
        return PriceOverrideRequest(
            id=row["id"],
            ticket_id=row["ticket_id"],
            store_id=row["store_id"],
            requested_by_user_id=row["requested_by_user_id"],
            approver_user_id=row["approver_user_id"],
            original_payout=row["original_payout"],
            proposed_payout=row["proposed_payout"],
            reason=row["reason"],
            status=row["status"],
            created_at=row["created_at"],
            approved_at=row["approved_at"],
            rejected_at=row["rejected_at"],
            executed_at=row["executed_at"],
        )
