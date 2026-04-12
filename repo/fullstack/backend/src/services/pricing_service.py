"""Pricing engine — deterministic rule-based payout calculation.

Evaluates pricing rules by priority, applies tier bonuses, enforces per-lb
and per-ticket caps, and persists immutable calculation snapshots.
Manual price overrides go through the dedicated PriceOverrideService
(dual-control + audit); this engine does NOT apply them automatically.
"""
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from ..enums.calculation_type import CalculationType
from ..models.pricing_calculation_snapshot import PricingCalculationSnapshot
from ..models.pricing_rule import PricingRule
from ..models.settings import Settings
from ..repositories.pricing_calculation_snapshot_repository import PricingCalculationSnapshotRepository
from ..repositories.pricing_rule_repository import PricingRuleRepository
from ..repositories.settings_repository import SettingsRepository

logger = logging.getLogger(__name__)


class PricingService:
    def __init__(
        self,
        pricing_rule_repo: PricingRuleRepository,
        snapshot_repo: PricingCalculationSnapshotRepository,
        settings_repo: SettingsRepository,
    ):
        self.pricing_rule_repo = pricing_rule_repo
        self.snapshot_repo = snapshot_repo
        self.settings_repo = settings_repo

    def _get_settings(self, store_id: int) -> Settings:
        settings = self.settings_repo.get_effective(store_id)
        if not settings:
            return Settings()
        return settings

    # Format strings tried in order against operator-supplied date/time
    # values. The list is intentionally permissive so the same field can
    # accept ISO-8601, US-style MM/DD/YYYY, and 12-hour clocks with an
    # AM/PM marker — operators sometimes paste values straight from a
    # spreadsheet or shift schedule.
    _LOCAL_DATETIME_FORMATS = (
        # ISO date / datetime
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        # US-style MM/DD/YYYY (with optional time, both 24h and 12h)
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
        # 12-hour clocks paired with ISO date
        "%Y-%m-%d %I:%M:%S %p",
        "%Y-%m-%d %I:%M %p",
    )

    @classmethod
    def _parse_local_datetime(cls, value: Optional[str]) -> Optional[datetime]:
        """Parse an eligibility-window datetime string.

        Accepts every shape an operator might realistically supply:

          ISO:        YYYY-MM-DD, YYYY-MM-DDTHH:MM[:SS][Z], full ISO-8601
          US:         MM/DD/YYYY, MM/DD/YYYY HH:MM[:SS]
          12-hour:    MM/DD/YYYY 10:30 AM, YYYY-MM-DD 10:30 PM, etc.

        Returns None on completely unparseable input so the caller can
        fall back gracefully rather than crash inside the rule loop.
        """
        if not value:
            return None
        s = value.strip()
        if not s:
            return None
        # Strip trailing Z so fromisoformat is happy on Python 3.10.
        if s.endswith("Z"):
            s = s[:-1]
        # Fast path: native ISO parse handles offsets like +05:30.
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            pass
        # Normalize lowercased am/pm so strptime's %p (which is locale-
        # dependent on some platforms but accepts upper case on glibc)
        # always sees AM/PM.
        normalized = s.replace("am", "AM").replace("pm", "PM")
        for fmt in cls._LOCAL_DATETIME_FORMATS:
            try:
                return datetime.strptime(normalized, fmt)
            except ValueError:
                continue
        return None

    def _find_applicable_rule(
        self,
        store_id: int,
        category: str,
        condition_grade: str,
        weight_lbs: float,
        now_local: Optional[str] = None,
    ) -> Optional[PricingRule]:
        rules = self.pricing_rule_repo.list_active_by_store(store_id)

        # Parse `now_local` once — the eligibility window compare uses
        # real datetime values (not lexical string compare) so that a
        # rule like [2025-01-01, 2025-12-31] correctly excludes a
        # calculation at 2024-12-31 and includes one at 2025-06-15,
        # regardless of whether the stored strings include a time
        # component or not.
        now_dt = self._parse_local_datetime(now_local) if now_local else None

        # Rules come ordered by priority ASC — first match wins
        for rule in rules:
            if rule.category_filter and rule.category_filter != category:
                continue
            if rule.condition_grade_filter and rule.condition_grade_filter != condition_grade:
                continue
            if rule.min_weight_lbs is not None and weight_lbs < rule.min_weight_lbs:
                continue
            if rule.max_weight_lbs is not None and weight_lbs > rule.max_weight_lbs:
                continue
            if now_dt is not None:
                start_dt = self._parse_local_datetime(rule.eligibility_start_local)
                end_dt = self._parse_local_datetime(rule.eligibility_end_local)
                if start_dt is not None and now_dt < start_dt:
                    continue
                if end_dt is not None and now_dt > end_dt:
                    continue
            return rule
        return None

    def calculate_payout(
        self,
        store_id: int,
        category: str,
        condition_grade: str,
        weight_lbs: float,
        now_local: Optional[str] = None,
    ) -> dict:
        """Calculate payout returning a dict with all breakdown fields.

        Returns dict with keys: base_rate, bonus_pct, gross_amount, bonus_amount,
        capped_amount, cap_applied, cap_reason, applied_rule_ids
        """
        if weight_lbs <= 0:
            raise ValueError("Weight must be greater than zero")

        settings = self._get_settings(store_id)
        rule = self._find_applicable_rule(store_id, category, condition_grade, weight_lbs, now_local)

        if rule is None:
            raise ValueError("No applicable pricing rule found")

        base_rate = rule.base_rate_per_lb
        bonus_pct = rule.bonus_pct
        max_rate = min(rule.max_rate_per_lb, settings.max_rate_per_lb)
        max_ticket = min(rule.max_ticket_payout, settings.max_ticket_payout)

        # Step 1: gross = base_rate * weight
        gross_amount = round(base_rate * weight_lbs, 2)

        # Step 2: apply bonus
        bonus_amount = round(gross_amount * bonus_pct / 100.0, 2)
        subtotal = round(gross_amount + bonus_amount, 2)

        # Step 3: enforce per-lb cap
        cap_reason = None
        cap_applied = False
        per_lb_max = round(max_rate * weight_lbs, 2)

        capped_amount = subtotal
        if subtotal > per_lb_max:
            capped_amount = per_lb_max
            cap_reason = f"per_lb_cap:{max_rate}/lb"
            cap_applied = True

        # Step 4: enforce per-ticket cap
        if capped_amount > max_ticket:
            capped_amount = max_ticket
            cap_reason = f"ticket_cap:{max_ticket}"
            cap_applied = True

        return {
            "base_rate": base_rate,
            "bonus_pct": bonus_pct,
            "gross_amount": gross_amount,
            "bonus_amount": bonus_amount,
            "capped_amount": round(capped_amount, 2),
            "cap_applied": cap_applied,
            "cap_reason": cap_reason,
            "applied_rule_ids": [rule.id],
        }

    def persist_snapshot(
        self,
        ticket_id: int,
        calculation_type: str,
        calc_result: dict,
    ) -> PricingCalculationSnapshot:
        snapshot = PricingCalculationSnapshot(
            ticket_id=ticket_id,
            calculation_type=calculation_type,
            base_rate_per_lb=calc_result["base_rate"],
            input_weight_lbs=calc_result.get("weight_lbs", 0.0),
            gross_amount=calc_result["gross_amount"],
            bonus_pct=calc_result["bonus_pct"],
            bonus_amount=calc_result["bonus_amount"],
            capped_amount=calc_result["capped_amount"],
            cap_reason=calc_result.get("cap_reason"),
            applied_rule_ids_json=json.dumps(calc_result["applied_rule_ids"]),
        )
        return self.snapshot_repo.create(snapshot)

    def check_variance(
        self, estimated_payout: float, final_payout: float, store_id: int
    ) -> Tuple[bool, float, float, float, float]:
        """Check if variance approval is required.

        Returns: (approval_required, variance_amount, variance_pct,
                  threshold_amount, threshold_pct)
        """
        settings = self._get_settings(store_id)
        difference = abs(final_payout - estimated_payout)

        if estimated_payout == 0:
            variance_pct = 100.0 if difference > 0 else 0.0
        else:
            variance_pct = round((difference / estimated_payout) * 100, 2)

        pct_threshold = settings.variance_pct_threshold
        amt_threshold = settings.variance_amount_threshold

        pct_threshold_amount = round(estimated_payout * pct_threshold / 100.0, 2)
        controlling_threshold = max(amt_threshold, pct_threshold_amount)

        approval_required = difference > controlling_threshold

        return (approval_required, round(difference, 2), variance_pct,
                amt_threshold, pct_threshold)
