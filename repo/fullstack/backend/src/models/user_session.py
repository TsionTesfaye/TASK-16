from dataclasses import dataclass
from typing import Optional


@dataclass
class UserSession:
    id: Optional[int] = None
    user_id: int = 0
    session_nonce: str = ""
    cookie_signature_version: str = ""
    csrf_secret: str = ""
    client_device_id: Optional[str] = None
    issued_at: Optional[str] = None
    expires_at: str = ""
    last_seen_at: Optional[str] = None
    revoked_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "UserSession":
        return UserSession(
            id=row["id"],
            user_id=row["user_id"],
            session_nonce=row["session_nonce"],
            cookie_signature_version=row["cookie_signature_version"],
            csrf_secret=row["csrf_secret"],
            client_device_id=row["client_device_id"],
            issued_at=row["issued_at"],
            expires_at=row["expires_at"],
            last_seen_at=row["last_seen_at"],
            revoked_at=row["revoked_at"],
        )
