from typing import List, Optional

from ..models.pricing_rule import PricingRule
from .base_repository import BaseRepository


class PricingRuleRepository(BaseRepository):
    def create(self, rule: PricingRule) -> PricingRule:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO pricing_rules (
               store_id, category_filter, condition_grade_filter,
               base_rate_per_lb, bonus_pct, min_weight_lbs, max_weight_lbs,
               max_ticket_payout, max_rate_per_lb,
               eligibility_start_local, eligibility_end_local,
               is_active, priority, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rule.store_id, rule.category_filter, rule.condition_grade_filter,
             rule.base_rate_per_lb, rule.bonus_pct,
             rule.min_weight_lbs, rule.max_weight_lbs,
             rule.max_ticket_payout, rule.max_rate_per_lb,
             rule.eligibility_start_local, rule.eligibility_end_local,
             int(rule.is_active), rule.priority, now, now),
        )
        rule.id = cursor.lastrowid
        rule.created_at = now
        rule.updated_at = now
        return rule

    def get_by_id(self, rule_id: int) -> Optional[PricingRule]:
        row = self._fetchone("SELECT * FROM pricing_rules WHERE id = ?", (rule_id,))
        return PricingRule.from_row(row) if row else None

    def list_active_by_store(self, store_id: Optional[int] = None) -> List[PricingRule]:
        if store_id is not None:
            rows = self._fetchall(
                """SELECT * FROM pricing_rules
                   WHERE is_active = 1 AND (store_id = ? OR store_id IS NULL)
                   ORDER BY priority ASC""",
                (store_id,),
            )
        else:
            rows = self._fetchall(
                """SELECT * FROM pricing_rules
                   WHERE is_active = 1 AND store_id IS NULL
                   ORDER BY priority ASC""",
            )
        return [PricingRule.from_row(r) for r in rows]

    def list_all(self, store_id: Optional[int] = None) -> List[PricingRule]:
        if store_id is not None:
            rows = self._fetchall(
                "SELECT * FROM pricing_rules WHERE store_id = ? OR store_id IS NULL ORDER BY priority ASC",
                (store_id,),
            )
        else:
            rows = self._fetchall("SELECT * FROM pricing_rules ORDER BY priority ASC")
        return [PricingRule.from_row(r) for r in rows]

    def update(self, rule: PricingRule) -> PricingRule:
        now = self._now_utc()
        self._execute(
            """UPDATE pricing_rules SET
               store_id = ?, category_filter = ?, condition_grade_filter = ?,
               base_rate_per_lb = ?, bonus_pct = ?,
               min_weight_lbs = ?, max_weight_lbs = ?,
               max_ticket_payout = ?, max_rate_per_lb = ?,
               eligibility_start_local = ?, eligibility_end_local = ?,
               is_active = ?, priority = ?, updated_at = ?
               WHERE id = ?""",
            (rule.store_id, rule.category_filter, rule.condition_grade_filter,
             rule.base_rate_per_lb, rule.bonus_pct,
             rule.min_weight_lbs, rule.max_weight_lbs,
             rule.max_ticket_payout, rule.max_rate_per_lb,
             rule.eligibility_start_local, rule.eligibility_end_local,
             int(rule.is_active), rule.priority, now, rule.id),
        )
        rule.updated_at = now
        return rule

    def delete(self, rule_id: int) -> None:
        self._execute("DELETE FROM pricing_rules WHERE id = ?", (rule_id,))
