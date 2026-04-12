from typing import List, Optional

from ..models.member import Member
from .base_repository import BaseRepository


class MemberRepository(BaseRepository):
    def create(self, member: Member) -> Member:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO members (
               club_organization_id, full_name, status,
               joined_at, left_at, transferred_at, current_group,
               created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (member.club_organization_id, member.full_name, member.status,
             member.joined_at, member.left_at, member.transferred_at,
             member.current_group, now, now),
        )
        member.id = cursor.lastrowid
        member.created_at = now
        member.updated_at = now
        return member

    def get_by_id(self, member_id: int) -> Optional[Member]:
        row = self._fetchone("SELECT * FROM members WHERE id = ?", (member_id,))
        return Member.from_row(row) if row else None

    def list_by_organization(
        self, org_id: int, status: Optional[str] = None
    ) -> List[Member]:
        if status:
            rows = self._fetchall(
                "SELECT * FROM members WHERE club_organization_id = ? AND status = ? ORDER BY full_name",
                (org_id, status),
            )
        else:
            rows = self._fetchall(
                "SELECT * FROM members WHERE club_organization_id = ? ORDER BY full_name",
                (org_id,),
            )
        return [Member.from_row(r) for r in rows]

    def list_all(self, status: Optional[str] = None) -> List[Member]:
        if status:
            rows = self._fetchall(
                "SELECT * FROM members WHERE status = ? ORDER BY full_name",
                (status,),
            )
        else:
            rows = self._fetchall("SELECT * FROM members ORDER BY full_name")
        return [Member.from_row(r) for r in rows]

    def update(self, member: Member) -> Member:
        now = self._now_utc()
        self._execute(
            """UPDATE members SET
               club_organization_id = ?, full_name = ?, status = ?,
               joined_at = ?, left_at = ?, transferred_at = ?,
               current_group = ?, updated_at = ?
               WHERE id = ?""",
            (member.club_organization_id, member.full_name, member.status,
             member.joined_at, member.left_at, member.transferred_at,
             member.current_group, now, member.id),
        )
        member.updated_at = now
        return member

    def delete(self, member_id: int) -> None:
        self._execute("DELETE FROM members WHERE id = ?", (member_id,))
