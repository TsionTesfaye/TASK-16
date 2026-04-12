from typing import List, Optional

from ..models.pricing_calculation_snapshot import PricingCalculationSnapshot
from .base_repository import BaseRepository


class PricingCalculationSnapshotRepository(BaseRepository):
    def create(self, snapshot: PricingCalculationSnapshot) -> PricingCalculationSnapshot:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO pricing_calculation_snapshots (
               ticket_id, calculation_type, base_rate_per_lb, input_weight_lbs,
               gross_amount, bonus_pct, bonus_amount, capped_amount,
               cap_reason, applied_rule_ids_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (snapshot.ticket_id, snapshot.calculation_type,
             snapshot.base_rate_per_lb, snapshot.input_weight_lbs,
             snapshot.gross_amount, snapshot.bonus_pct, snapshot.bonus_amount,
             snapshot.capped_amount, snapshot.cap_reason,
             snapshot.applied_rule_ids_json, now),
        )
        snapshot.id = cursor.lastrowid
        snapshot.created_at = now
        return snapshot

    def get_by_id(self, snapshot_id: int) -> Optional[PricingCalculationSnapshot]:
        row = self._fetchone(
            "SELECT * FROM pricing_calculation_snapshots WHERE id = ?", (snapshot_id,)
        )
        return PricingCalculationSnapshot.from_row(row) if row else None

    def list_by_ticket(self, ticket_id: int) -> List[PricingCalculationSnapshot]:
        rows = self._fetchall(
            "SELECT * FROM pricing_calculation_snapshots WHERE ticket_id = ? ORDER BY created_at ASC",
            (ticket_id,),
        )
        return [PricingCalculationSnapshot.from_row(r) for r in rows]

    def get_by_ticket_and_type(
        self, ticket_id: int, calculation_type: str
    ) -> Optional[PricingCalculationSnapshot]:
        row = self._fetchone(
            """SELECT * FROM pricing_calculation_snapshots
               WHERE ticket_id = ? AND calculation_type = ?
               ORDER BY created_at DESC LIMIT 1""",
            (ticket_id, calculation_type),
        )
        return PricingCalculationSnapshot.from_row(row) if row else None

    def delete(self, snapshot_id: int) -> None:
        self._execute(
            "DELETE FROM pricing_calculation_snapshots WHERE id = ?", (snapshot_id,)
        )
