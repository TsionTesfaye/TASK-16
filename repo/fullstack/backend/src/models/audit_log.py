from dataclasses import dataclass
from typing import Optional


@dataclass
class AuditLog:
    id: Optional[int] = None
    actor_user_id: Optional[int] = None
    actor_username_snapshot: str = ""
    action_code: str = ""
    object_type: str = ""
    object_id: str = ""
    before_json: Optional[str] = None
    after_json: Optional[str] = None
    client_device_id: Optional[str] = None
    tamper_chain_hash: str = ""
    created_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "AuditLog":
        return AuditLog(
            id=row["id"],
            actor_user_id=row["actor_user_id"],
            actor_username_snapshot=row["actor_username_snapshot"],
            action_code=row["action_code"],
            object_type=row["object_type"],
            object_id=row["object_id"],
            before_json=row["before_json"],
            after_json=row["after_json"],
            client_device_id=row["client_device_id"],
            tamper_chain_hash=row["tamper_chain_hash"],
            created_at=row["created_at"],
        )
