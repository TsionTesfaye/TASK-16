from dataclasses import dataclass
from typing import Optional


@dataclass
class PricingRule:
    id: Optional[int] = None
    store_id: Optional[int] = None
    category_filter: Optional[str] = None
    condition_grade_filter: Optional[str] = None
    base_rate_per_lb: float = 0.0
    bonus_pct: float = 0.0
    min_weight_lbs: Optional[float] = None
    max_weight_lbs: Optional[float] = None
    max_ticket_payout: float = 0.0
    max_rate_per_lb: float = 0.0
    eligibility_start_local: Optional[str] = None
    eligibility_end_local: Optional[str] = None
    is_active: bool = True
    priority: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "PricingRule":
        return PricingRule(
            id=row["id"],
            store_id=row["store_id"],
            category_filter=row["category_filter"],
            condition_grade_filter=row["condition_grade_filter"],
            base_rate_per_lb=row["base_rate_per_lb"],
            bonus_pct=row["bonus_pct"],
            min_weight_lbs=row["min_weight_lbs"],
            max_weight_lbs=row["max_weight_lbs"],
            max_ticket_payout=row["max_ticket_payout"],
            max_rate_per_lb=row["max_rate_per_lb"],
            eligibility_start_local=row["eligibility_start_local"],
            eligibility_end_local=row["eligibility_end_local"],
            is_active=bool(row["is_active"]),
            priority=row["priority"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
