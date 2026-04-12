from typing import List, Optional

from ..models.audit_log import AuditLog
from .base_repository import BaseRepository


class AuditLogRepository(BaseRepository):
    def create(self, log: AuditLog) -> AuditLog:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO audit_logs (
               actor_user_id, actor_username_snapshot, action_code,
               object_type, object_id, before_json, after_json,
               client_device_id, tamper_chain_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (log.actor_user_id, log.actor_username_snapshot,
             log.action_code, log.object_type, log.object_id,
             log.before_json, log.after_json, log.client_device_id,
             log.tamper_chain_hash, now),
        )
        log.id = cursor.lastrowid
        log.created_at = now
        return log

    def get_by_id(self, log_id: int) -> Optional[AuditLog]:
        row = self._fetchone("SELECT * FROM audit_logs WHERE id = ?", (log_id,))
        return AuditLog.from_row(row) if row else None

    def get_latest(self) -> Optional[AuditLog]:
        row = self._fetchone(
            "SELECT * FROM audit_logs ORDER BY id DESC LIMIT 1"
        )
        return AuditLog.from_row(row) if row else None

    def list_by_object(self, object_type: str, object_id: str) -> List[AuditLog]:
        rows = self._fetchall(
            """SELECT * FROM audit_logs
               WHERE object_type = ? AND object_id = ?
               ORDER BY created_at ASC""",
            (object_type, object_id),
        )
        return [AuditLog.from_row(r) for r in rows]

    def list_by_actor(self, actor_user_id: int) -> List[AuditLog]:
        rows = self._fetchall(
            "SELECT * FROM audit_logs WHERE actor_user_id = ? ORDER BY created_at DESC",
            (actor_user_id,),
        )
        return [AuditLog.from_row(r) for r in rows]

    def list_by_action(self, action_code: str) -> List[AuditLog]:
        rows = self._fetchall(
            "SELECT * FROM audit_logs WHERE action_code = ? ORDER BY created_at DESC",
            (action_code,),
        )
        return [AuditLog.from_row(r) for r in rows]

    def list_by_date_range(self, date_start: str, date_end: str) -> List[AuditLog]:
        rows = self._fetchall(
            """SELECT * FROM audit_logs
               WHERE created_at >= ? AND created_at <= ?
               ORDER BY created_at ASC""",
            (date_start, date_end),
        )
        return [AuditLog.from_row(r) for r in rows]

    def list_all(self, limit: int = 100, offset: int = 0) -> List[AuditLog]:
        rows = self._fetchall(
            "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [AuditLog.from_row(r) for r in rows]

    def count(self) -> int:
        row = self._fetchone("SELECT COUNT(*) as cnt FROM audit_logs")
        return row["cnt"] if row else 0
