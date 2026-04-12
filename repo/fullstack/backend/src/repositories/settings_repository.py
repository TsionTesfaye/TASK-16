from typing import List, Optional

from ..models.settings import Settings
from .base_repository import BaseRepository


class SettingsRepository(BaseRepository):
    def create(self, settings: Settings) -> Settings:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO settings (
               store_id, business_timezone,
               variance_pct_threshold, variance_amount_threshold,
               max_ticket_payout, max_rate_per_lb,
               qc_sample_pct, qc_sample_min_items,
               qc_escalation_nonconformances_per_day,
               export_requires_supervisor_default,
               file_upload_max_mb, daily_capacity, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (settings.store_id, settings.business_timezone,
             settings.variance_pct_threshold, settings.variance_amount_threshold,
             settings.max_ticket_payout, settings.max_rate_per_lb,
             settings.qc_sample_pct, settings.qc_sample_min_items,
             settings.qc_escalation_nonconformances_per_day,
             int(settings.export_requires_supervisor_default),
             settings.file_upload_max_mb, settings.daily_capacity, now, now),
        )
        settings.id = cursor.lastrowid
        settings.created_at = now
        settings.updated_at = now
        return settings

    def get_by_id(self, settings_id: int) -> Optional[Settings]:
        row = self._fetchone("SELECT * FROM settings WHERE id = ?", (settings_id,))
        return Settings.from_row(row) if row else None

    def get_global(self) -> Optional[Settings]:
        row = self._fetchone(
            "SELECT * FROM settings WHERE store_id IS NULL LIMIT 1"
        )
        return Settings.from_row(row) if row else None

    def get_by_store(self, store_id: int) -> Optional[Settings]:
        row = self._fetchone(
            "SELECT * FROM settings WHERE store_id = ? LIMIT 1",
            (store_id,),
        )
        return Settings.from_row(row) if row else None

    def get_effective(self, store_id: int) -> Optional[Settings]:
        row = self._fetchone(
            """SELECT * FROM settings
               WHERE store_id = ? OR store_id IS NULL
               ORDER BY store_id DESC LIMIT 1""",
            (store_id,),
        )
        return Settings.from_row(row) if row else None

    def list_all(self) -> List[Settings]:
        rows = self._fetchall("SELECT * FROM settings ORDER BY store_id")
        return [Settings.from_row(r) for r in rows]

    def update(self, settings: Settings) -> Settings:
        now = self._now_utc()
        self._execute(
            """UPDATE settings SET
               business_timezone = ?,
               variance_pct_threshold = ?, variance_amount_threshold = ?,
               max_ticket_payout = ?, max_rate_per_lb = ?,
               qc_sample_pct = ?, qc_sample_min_items = ?,
               qc_escalation_nonconformances_per_day = ?,
               export_requires_supervisor_default = ?,
               file_upload_max_mb = ?, daily_capacity = ?, updated_at = ?
               WHERE id = ?""",
            (settings.business_timezone,
             settings.variance_pct_threshold, settings.variance_amount_threshold,
             settings.max_ticket_payout, settings.max_rate_per_lb,
             settings.qc_sample_pct, settings.qc_sample_min_items,
             settings.qc_escalation_nonconformances_per_day,
             int(settings.export_requires_supervisor_default),
             settings.file_upload_max_mb, settings.daily_capacity, now, settings.id),
        )
        settings.updated_at = now
        return settings

    def delete(self, settings_id: int) -> None:
        self._execute("DELETE FROM settings WHERE id = ?", (settings_id,))

    # -- Bootstrap flag --

    def is_bootstrap_completed(self) -> bool:
        """Return True if any settings row has bootstrap_completed=1.

        The global settings row is the canonical holder; store-scoped rows
        inherit the semantic answer since bootstrap is a system-wide
        one-shot. We check MAX() so either holder is sufficient.
        """
        row = self._fetchone(
            "SELECT COALESCE(MAX(bootstrap_completed), 0) AS flag FROM settings"
        )
        return bool(row["flag"]) if row else False

    def mark_bootstrap_completed(self) -> None:
        """Atomically set bootstrap_completed=1. Creates a global settings
        row if none exists yet so the flag has somewhere to live."""
        now = self._now_utc()
        existing = self._fetchone(
            "SELECT id FROM settings WHERE store_id IS NULL LIMIT 1"
        )
        if existing:
            self._execute(
                "UPDATE settings SET bootstrap_completed = 1, updated_at = ? WHERE id = ?",
                (now, existing["id"]),
            )
        else:
            self._execute(
                """INSERT INTO settings (
                   store_id, bootstrap_completed, created_at, updated_at
                ) VALUES (NULL, 1, ?, ?)""",
                (now, now),
            )
