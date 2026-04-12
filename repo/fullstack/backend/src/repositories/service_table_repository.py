from typing import List, Optional

from ..models.service_table import ServiceTable
from .base_repository import BaseRepository


class ServiceTableRepository(BaseRepository):
    def create(self, table: ServiceTable) -> ServiceTable:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO service_tables (
               store_id, table_code, area_type, merged_into_id,
               is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (table.store_id, table.table_code, table.area_type,
             table.merged_into_id, int(table.is_active), now, now),
        )
        table.id = cursor.lastrowid
        table.created_at = now
        table.updated_at = now
        return table

    def get_by_id(self, table_id: int) -> Optional[ServiceTable]:
        row = self._fetchone(
            "SELECT * FROM service_tables WHERE id = ?", (table_id,)
        )
        return ServiceTable.from_row(row) if row else None

    def list_by_store(self, store_id: int, active_only: bool = False) -> List[ServiceTable]:
        if active_only:
            rows = self._fetchall(
                "SELECT * FROM service_tables WHERE store_id = ? AND is_active = 1 ORDER BY table_code",
                (store_id,),
            )
        else:
            rows = self._fetchall(
                "SELECT * FROM service_tables WHERE store_id = ? ORDER BY table_code",
                (store_id,),
            )
        return [ServiceTable.from_row(r) for r in rows]

    def list_by_area_type(self, store_id: int, area_type: str) -> List[ServiceTable]:
        rows = self._fetchall(
            "SELECT * FROM service_tables WHERE store_id = ? AND area_type = ? ORDER BY table_code",
            (store_id, area_type),
        )
        return [ServiceTable.from_row(r) for r in rows]

    def update(self, table: ServiceTable) -> ServiceTable:
        now = self._now_utc()
        self._execute(
            """UPDATE service_tables SET
               table_code = ?, area_type = ?, merged_into_id = ?,
               is_active = ?, updated_at = ?
               WHERE id = ?""",
            (table.table_code, table.area_type, table.merged_into_id,
             int(table.is_active), now, table.id),
        )
        table.updated_at = now
        return table

    def delete(self, table_id: int) -> None:
        self._execute("DELETE FROM service_tables WHERE id = ?", (table_id,))
