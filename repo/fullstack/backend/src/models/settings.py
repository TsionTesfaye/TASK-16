from dataclasses import dataclass
from typing import Optional


@dataclass
class Settings:
    id: Optional[int] = None
    store_id: Optional[int] = None
    business_timezone: str = "America/New_York"
    variance_pct_threshold: float = 5.0
    variance_amount_threshold: float = 5.00
    max_ticket_payout: float = 200.00
    max_rate_per_lb: float = 3.00
    qc_sample_pct: float = 10.0
    qc_sample_min_items: int = 3
    qc_escalation_nonconformances_per_day: int = 2
    export_requires_supervisor_default: bool = False
    file_upload_max_mb: int = 5
    daily_capacity: int = 50
    bootstrap_completed: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "Settings":
        return Settings(
            id=row["id"],
            store_id=row["store_id"],
            business_timezone=row["business_timezone"],
            variance_pct_threshold=row["variance_pct_threshold"],
            variance_amount_threshold=row["variance_amount_threshold"],
            max_ticket_payout=row["max_ticket_payout"],
            max_rate_per_lb=row["max_rate_per_lb"],
            qc_sample_pct=row["qc_sample_pct"],
            qc_sample_min_items=row["qc_sample_min_items"],
            qc_escalation_nonconformances_per_day=row["qc_escalation_nonconformances_per_day"],
            export_requires_supervisor_default=bool(row["export_requires_supervisor_default"]),
            file_upload_max_mb=row["file_upload_max_mb"],
            daily_capacity=row["daily_capacity"],
            bootstrap_completed=bool(row["bootstrap_completed"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
