from dataclasses import dataclass
from typing import Optional


@dataclass
class ScheduleAdjustmentRequest:
    id: Optional[int] = None
    store_id: int = 0
    requested_by_user_id: int = 0
    approver_user_id: Optional[int] = None
    adjustment_type: str = ""
    target_entity_type: str = ""
    target_entity_id: str = ""
    before_value: str = ""
    after_value: str = ""
    reason: str = ""
    status: str = "pending"
    password_confirmation_used: bool = False
    created_at: Optional[str] = None
    approved_at: Optional[str] = None
    rejected_at: Optional[str] = None
    executed_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "ScheduleAdjustmentRequest":
        return ScheduleAdjustmentRequest(
            id=row["id"],
            store_id=row["store_id"],
            requested_by_user_id=row["requested_by_user_id"],
            approver_user_id=row["approver_user_id"],
            adjustment_type=row["adjustment_type"],
            target_entity_type=row["target_entity_type"],
            target_entity_id=row["target_entity_id"],
            before_value=row["before_value"],
            after_value=row["after_value"],
            reason=row["reason"],
            status=row["status"],
            password_confirmation_used=bool(row["password_confirmation_used"]),
            created_at=row["created_at"],
            approved_at=row["approved_at"],
            rejected_at=row["rejected_at"],
            executed_at=row["executed_at"],
        )
