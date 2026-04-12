"""Settings management service.

Manages global and store-level configuration with audit logging.
All business logic reads settings through this service, never directly
from templates or client-side code.
"""
import json
import logging
from typing import Optional

from ..enums.user_role import UserRole
from ..models.settings import Settings
from ..repositories.settings_repository import SettingsRepository
from ._tx import atomic
from .audit_service import AuditService

logger = logging.getLogger(__name__)


class SettingsService:
    def __init__(
        self,
        settings_repo: SettingsRepository,
        audit_service: AuditService,
    ):
        self.settings_repo = settings_repo
        self.audit_service = audit_service

    def get_effective(self, store_id: int) -> Settings:
        settings = self.settings_repo.get_effective(store_id)
        if not settings:
            return Settings()
        return settings

    def get_global(self) -> Optional[Settings]:
        return self.settings_repo.get_global()

    def create_or_update(
        self,
        user_id: int,
        username: str,
        user_role: str,
        store_id: Optional[int] = None,
        **kwargs,
    ) -> Settings:
        if user_role != UserRole.ADMINISTRATOR:
            raise PermissionError("Only administrators can modify settings")

        if store_id is not None:
            existing = self.settings_repo.get_by_store(store_id)
        else:
            existing = self.settings_repo.get_global()

        if existing:
            before = {
                "variance_pct_threshold": existing.variance_pct_threshold,
                "variance_amount_threshold": existing.variance_amount_threshold,
                "max_ticket_payout": existing.max_ticket_payout,
                "max_rate_per_lb": existing.max_rate_per_lb,
            }

            for key, value in kwargs.items():
                if hasattr(existing, key) and key not in ("id", "created_at", "store_id"):
                    setattr(existing, key, value)

            with atomic(self.settings_repo.conn):
                existing = self.settings_repo.update(existing)

                self.audit_service.log(
                    actor_user_id=user_id,
                    actor_username=username,
                    action_code="settings.updated",
                    object_type="settings",
                    object_id=str(existing.id),
                    before=before,
                    after={k: getattr(existing, k) for k in before},
                )

            return existing
        else:
            settings = Settings(store_id=store_id)
            for key, value in kwargs.items():
                if hasattr(settings, key) and key not in ("id", "created_at", "store_id"):
                    setattr(settings, key, value)

            with atomic(self.settings_repo.conn):
                settings = self.settings_repo.create(settings)

                self.audit_service.log(
                    actor_user_id=user_id,
                    actor_username=username,
                    action_code="settings.created",
                    object_type="settings",
                    object_id=str(settings.id),
                    after={"store_id": store_id},
                )

            return settings
