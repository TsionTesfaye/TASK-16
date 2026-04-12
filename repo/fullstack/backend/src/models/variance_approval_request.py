from dataclasses import dataclass
from typing import Optional

from ..enums.variance_approval_status import VarianceApprovalStatus


@dataclass
class VarianceApprovalRequest:
    id: Optional[int] = None
    ticket_id: int = 0
    requested_by_user_id: int = 0
    approver_user_id: Optional[int] = None
    variance_amount: float = 0.0
    variance_pct: float = 0.0
    threshold_amount: float = 0.0
    threshold_pct: float = 0.0
    confirmation_note: Optional[str] = None
    status: str = VarianceApprovalStatus.PENDING
    password_confirmation_used: bool = False
    expires_at: Optional[str] = None
    created_at: Optional[str] = None
    approved_at: Optional[str] = None
    rejected_at: Optional[str] = None
    executed_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "VarianceApprovalRequest":
        return VarianceApprovalRequest(
            id=row["id"],
            ticket_id=row["ticket_id"],
            requested_by_user_id=row["requested_by_user_id"],
            approver_user_id=row["approver_user_id"],
            variance_amount=row["variance_amount"],
            variance_pct=row["variance_pct"],
            threshold_amount=row["threshold_amount"],
            threshold_pct=row["threshold_pct"],
            confirmation_note=row["confirmation_note"],
            status=row["status"],
            password_confirmation_used=bool(row["password_confirmation_used"]),
            expires_at=row["expires_at"],
            created_at=row["created_at"],
            approved_at=row["approved_at"],
            rejected_at=row["rejected_at"],
            executed_at=row["executed_at"],
        )
