from dataclasses import dataclass
from typing import Optional


@dataclass
class PricingCalculationSnapshot:
    id: Optional[int] = None
    ticket_id: int = 0
    calculation_type: str = ""
    base_rate_per_lb: float = 0.0
    input_weight_lbs: float = 0.0
    gross_amount: float = 0.0
    bonus_pct: float = 0.0
    bonus_amount: float = 0.0
    capped_amount: float = 0.0
    cap_reason: Optional[str] = None
    applied_rule_ids_json: Optional[str] = None
    created_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "PricingCalculationSnapshot":
        return PricingCalculationSnapshot(
            id=row["id"],
            ticket_id=row["ticket_id"],
            calculation_type=row["calculation_type"],
            base_rate_per_lb=row["base_rate_per_lb"],
            input_weight_lbs=row["input_weight_lbs"],
            gross_amount=row["gross_amount"],
            bonus_pct=row["bonus_pct"],
            bonus_amount=row["bonus_amount"],
            capped_amount=row["capped_amount"],
            cap_reason=row["cap_reason"],
            applied_rule_ids_json=row["applied_rule_ids_json"],
            created_at=row["created_at"],
        )
