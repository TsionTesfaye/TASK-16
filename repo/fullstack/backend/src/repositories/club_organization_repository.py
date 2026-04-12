from typing import List, Optional

from ..models.club_organization import ClubOrganization
from .base_repository import BaseRepository


class ClubOrganizationRepository(BaseRepository):
    def create(self, org: ClubOrganization) -> ClubOrganization:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO club_organizations (
               name, department, route_code, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (org.name, org.department, org.route_code,
             int(org.is_active), now, now),
        )
        org.id = cursor.lastrowid
        org.created_at = now
        org.updated_at = now
        return org

    def get_by_id(self, org_id: int) -> Optional[ClubOrganization]:
        row = self._fetchone(
            "SELECT * FROM club_organizations WHERE id = ?", (org_id,)
        )
        return ClubOrganization.from_row(row) if row else None

    def list_all(self, active_only: bool = False) -> List[ClubOrganization]:
        if active_only:
            rows = self._fetchall(
                "SELECT * FROM club_organizations WHERE is_active = 1 ORDER BY name"
            )
        else:
            rows = self._fetchall(
                "SELECT * FROM club_organizations ORDER BY name"
            )
        return [ClubOrganization.from_row(r) for r in rows]

    def update(self, org: ClubOrganization) -> ClubOrganization:
        now = self._now_utc()
        self._execute(
            """UPDATE club_organizations SET
               name = ?, department = ?, route_code = ?,
               is_active = ?, updated_at = ?
               WHERE id = ?""",
            (org.name, org.department, org.route_code,
             int(org.is_active), now, org.id),
        )
        org.updated_at = now
        return org

    def delete(self, org_id: int) -> None:
        self._execute("DELETE FROM club_organizations WHERE id = ?", (org_id,))
