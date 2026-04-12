"""Audit logging service — tamper-evident, append-only audit trail.

Every sensitive action in the system must call this service to record
an immutable log entry with actor, before/after state, and a chained hash
that makes deletion or mutation detectable.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from ..models.audit_log import AuditLog
from ..repositories.audit_log_repository import AuditLogRepository

logger = logging.getLogger(__name__)


class AuditService:
    def __init__(self, audit_repo: AuditLogRepository):
        self.audit_repo = audit_repo

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _compute_chain_hash(self, previous_hash: str, action_code: str,
                            object_type: str, object_id: str,
                            actor_user_id: Optional[int],
                            before_json: Optional[str],
                            after_json: Optional[str],
                            created_at: str) -> str:
        payload = (
            f"{previous_hash}|{action_code}|{object_type}|{object_id}"
            f"|{actor_user_id}|{before_json}|{after_json}|{created_at}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def log(
        self,
        actor_user_id: Optional[int],
        actor_username: str,
        action_code: str,
        object_type: str,
        object_id: str,
        before: object = None,
        after: object = None,
        client_device_id: Optional[str] = None,
    ) -> AuditLog:
        before_json = json.dumps(before, default=str) if before is not None else None
        after_json = json.dumps(after, default=str) if after is not None else None
        created_at = self._now_utc()

        latest = self.audit_repo.get_latest()
        previous_hash = latest.tamper_chain_hash if latest else "GENESIS"

        chain_hash = self._compute_chain_hash(
            previous_hash, action_code, object_type, object_id,
            actor_user_id, before_json, after_json, created_at,
        )

        entry = AuditLog(
            actor_user_id=actor_user_id,
            actor_username_snapshot=actor_username,
            action_code=action_code,
            object_type=object_type,
            object_id=str(object_id),
            before_json=before_json,
            after_json=after_json,
            client_device_id=client_device_id,
            tamper_chain_hash=chain_hash,
        )
        created = self.audit_repo.create(entry)
        logger.info("Audit: %s on %s/%s by %s", action_code, object_type, object_id, actor_username)
        return created
