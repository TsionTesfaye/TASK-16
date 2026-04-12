from dataclasses import dataclass
from typing import Optional

from ..enums.customer_phone_preference import CustomerPhonePreference
from ..enums.ticket_status import TicketStatus


@dataclass
class BuybackTicket:
    id: Optional[int] = None
    store_id: int = 0
    created_by_user_id: int = 0
    customer_name: str = ""
    customer_phone_ciphertext: Optional[bytes] = None
    customer_phone_iv: Optional[bytes] = None
    customer_phone_last4: Optional[str] = None
    customer_phone_preference: str = CustomerPhonePreference.STANDARD_CALLS
    clothing_category: str = ""
    condition_grade: str = ""
    estimated_weight_lbs: float = 0.0
    actual_weight_lbs: Optional[float] = None
    estimated_base_rate: float = 0.0
    estimated_bonus_pct: float = 0.0
    estimated_payout: float = 0.0
    estimated_cap_applied: bool = False
    actual_base_rate: Optional[float] = None
    actual_bonus_pct: Optional[float] = None
    final_payout: Optional[float] = None
    final_cap_applied: Optional[bool] = None
    variance_amount: Optional[float] = None
    variance_pct: Optional[float] = None
    status: str = TicketStatus.INTAKE_OPEN
    qc_result: Optional[str] = None
    qc_notes: Optional[str] = None
    current_batch_id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None
    refunded_at: Optional[str] = None
    refund_amount: Optional[float] = None
    refund_initiated_by_user_id: Optional[int] = None

    @staticmethod
    def from_row(row) -> "BuybackTicket":
        return BuybackTicket(
            id=row["id"],
            store_id=row["store_id"],
            created_by_user_id=row["created_by_user_id"],
            customer_name=row["customer_name"],
            customer_phone_ciphertext=row["customer_phone_ciphertext"],
            customer_phone_iv=row["customer_phone_iv"],
            customer_phone_last4=row["customer_phone_last4"],
            customer_phone_preference=row["customer_phone_preference"],
            clothing_category=row["clothing_category"],
            condition_grade=row["condition_grade"],
            estimated_weight_lbs=row["estimated_weight_lbs"],
            actual_weight_lbs=row["actual_weight_lbs"],
            estimated_base_rate=row["estimated_base_rate"],
            estimated_bonus_pct=row["estimated_bonus_pct"],
            estimated_payout=row["estimated_payout"],
            estimated_cap_applied=bool(row["estimated_cap_applied"]),
            actual_base_rate=row["actual_base_rate"],
            actual_bonus_pct=row["actual_bonus_pct"],
            final_payout=row["final_payout"],
            final_cap_applied=bool(row["final_cap_applied"]) if row["final_cap_applied"] is not None else None,
            variance_amount=row["variance_amount"],
            variance_pct=row["variance_pct"],
            status=row["status"],
            qc_result=row["qc_result"],
            qc_notes=row["qc_notes"],
            current_batch_id=row["current_batch_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
            refunded_at=row["refunded_at"],
            refund_amount=row["refund_amount"],
            refund_initiated_by_user_id=row["refund_initiated_by_user_id"],
        )
