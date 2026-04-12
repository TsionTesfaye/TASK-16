from typing import List, Optional

from ..models.store import Store
from .base_repository import BaseRepository


class StoreRepository(BaseRepository):
    def create(self, store: Store) -> Store:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO stores (code, name, route_code, address_ciphertext, address_iv,
               phone_ciphertext, phone_iv, is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (store.code, store.name, store.route_code,
             store.address_ciphertext, store.address_iv,
             store.phone_ciphertext, store.phone_iv,
             int(store.is_active), now, now),
        )
        store.id = cursor.lastrowid
        store.created_at = now
        store.updated_at = now
        return store

    def get_by_id(self, store_id: int) -> Optional[Store]:
        row = self._fetchone("SELECT * FROM stores WHERE id = ?", (store_id,))
        return Store.from_row(row) if row else None

    def get_by_code(self, code: str) -> Optional[Store]:
        row = self._fetchone("SELECT * FROM stores WHERE code = ?", (code,))
        return Store.from_row(row) if row else None

    def list_all(self, active_only: bool = False) -> List[Store]:
        if active_only:
            rows = self._fetchall("SELECT * FROM stores WHERE is_active = 1 ORDER BY name")
        else:
            rows = self._fetchall("SELECT * FROM stores ORDER BY name")
        return [Store.from_row(r) for r in rows]

    def update(self, store: Store) -> Store:
        now = self._now_utc()
        self._execute(
            """UPDATE stores SET code = ?, name = ?, route_code = ?,
               address_ciphertext = ?, address_iv = ?,
               phone_ciphertext = ?, phone_iv = ?,
               is_active = ?, updated_at = ?
               WHERE id = ?""",
            (store.code, store.name, store.route_code,
             store.address_ciphertext, store.address_iv,
             store.phone_ciphertext, store.phone_iv,
             int(store.is_active), now, store.id),
        )
        store.updated_at = now
        return store

    def delete(self, store_id: int) -> None:
        self._execute("DELETE FROM stores WHERE id = ?", (store_id,))
