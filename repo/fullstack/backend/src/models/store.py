from dataclasses import dataclass
from typing import Optional


@dataclass
class Store:
    id: Optional[int] = None
    code: str = ""
    name: str = ""
    route_code: Optional[str] = None
    address_ciphertext: Optional[bytes] = None
    address_iv: Optional[bytes] = None
    phone_ciphertext: Optional[bytes] = None
    phone_iv: Optional[bytes] = None
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "Store":
        return Store(
            id=row["id"],
            code=row["code"],
            name=row["name"],
            route_code=row["route_code"],
            address_ciphertext=row["address_ciphertext"],
            address_iv=row["address_iv"],
            phone_ciphertext=row["phone_ciphertext"],
            phone_iv=row["phone_iv"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
