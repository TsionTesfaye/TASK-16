from typing import List, Optional

from ..models.notification_template import NotificationTemplate
from .base_repository import BaseRepository


class NotificationTemplateRepository(BaseRepository):
    def create(self, template: NotificationTemplate) -> NotificationTemplate:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO notification_templates (
               store_id, template_code, name, body, event_type,
               is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (template.store_id, template.template_code, template.name,
             template.body, template.event_type,
             int(template.is_active), now, now),
        )
        template.id = cursor.lastrowid
        template.created_at = now
        template.updated_at = now
        return template

    def get_by_id(self, template_id: int) -> Optional[NotificationTemplate]:
        row = self._fetchone(
            "SELECT * FROM notification_templates WHERE id = ?", (template_id,)
        )
        return NotificationTemplate.from_row(row) if row else None

    def get_by_code(self, template_code: str, store_id: Optional[int] = None) -> Optional[NotificationTemplate]:
        if store_id is not None:
            row = self._fetchone(
                """SELECT * FROM notification_templates
                   WHERE template_code = ? AND (store_id = ? OR store_id IS NULL)
                   ORDER BY store_id DESC LIMIT 1""",
                (template_code, store_id),
            )
        else:
            row = self._fetchone(
                "SELECT * FROM notification_templates WHERE template_code = ? AND store_id IS NULL LIMIT 1",
                (template_code,),
            )
        return NotificationTemplate.from_row(row) if row else None

    def list_active(self, store_id: Optional[int] = None) -> List[NotificationTemplate]:
        if store_id is not None:
            rows = self._fetchall(
                """SELECT * FROM notification_templates
                   WHERE is_active = 1 AND (store_id = ? OR store_id IS NULL)
                   ORDER BY template_code""",
                (store_id,),
            )
        else:
            rows = self._fetchall(
                "SELECT * FROM notification_templates WHERE is_active = 1 ORDER BY template_code"
            )
        return [NotificationTemplate.from_row(r) for r in rows]

    def list_all(self, store_id: Optional[int] = None) -> List[NotificationTemplate]:
        if store_id is not None:
            rows = self._fetchall(
                "SELECT * FROM notification_templates WHERE store_id = ? OR store_id IS NULL ORDER BY template_code",
                (store_id,),
            )
        else:
            rows = self._fetchall(
                "SELECT * FROM notification_templates ORDER BY template_code"
            )
        return [NotificationTemplate.from_row(r) for r in rows]

    def update(self, template: NotificationTemplate) -> NotificationTemplate:
        now = self._now_utc()
        self._execute(
            """UPDATE notification_templates SET
               store_id = ?, template_code = ?, name = ?, body = ?,
               event_type = ?, is_active = ?, updated_at = ?
               WHERE id = ?""",
            (template.store_id, template.template_code, template.name,
             template.body, template.event_type,
             int(template.is_active), now, template.id),
        )
        template.updated_at = now
        return template

    def delete(self, template_id: int) -> None:
        self._execute(
            "DELETE FROM notification_templates WHERE id = ?", (template_id,)
        )
