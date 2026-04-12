"""Authentication and session management service.

Handles login, session creation with anti-replay nonces, session
validation, logout, and account freeze enforcement.
"""
import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt

from ..enums.user_role import UserRole
from ..models.user import User
from ..models.user_session import UserSession
from ..repositories.user_repository import UserRepository
from ..repositories.user_session_repository import UserSessionRepository
from ..repositories.settings_repository import SettingsRepository
from ._authz import require_admin
from ._tx import atomic
from .audit_service import AuditService

logger = logging.getLogger(__name__)

# Password policy
MIN_PASSWORD_LENGTH = 12
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
SESSION_MAX_HOURS = 8
SESSION_IDLE_MINUTES = 30


class AuthService:
    def __init__(
        self,
        user_repo: UserRepository,
        session_repo: UserSessionRepository,
        settings_repo: SettingsRepository,
        audit_service: AuditService,
    ):
        self.user_repo = user_repo
        self.session_repo = session_repo
        self.settings_repo = settings_repo
        self.audit_service = audit_service

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _prepare_password_bytes(self, password: str) -> bytes:
        """bcrypt has a 72-byte password limit. Pre-hash longer passwords
        with SHA-256 so no password data is silently truncated."""
        pw = password.encode("utf-8")
        if len(pw) > 72:
            pw = hashlib.sha256(pw).digest()
        return pw

    def _hash_password(self, password: str) -> str:
        """Hash a password using bcrypt with 12 rounds of salt."""
        pw = self._prepare_password_bytes(password)
        return bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode("utf-8")

    def _verify_password(self, password: str, stored_hash: str) -> bool:
        """Verify a password against a stored hash.

        Supports bcrypt (new format: $2b$...) and legacy PBKDF2 (salt:hex)
        for backward compatibility with pre-existing user records.
        """
        if not stored_hash:
            return False

        # bcrypt (current)
        if stored_hash.startswith("$2"):
            try:
                pw = self._prepare_password_bytes(password)
                return bcrypt.checkpw(pw, stored_hash.encode("utf-8"))
            except (ValueError, TypeError):
                return False

        # Legacy PBKDF2 format: "salt:hex_hash"
        if ":" in stored_hash:
            try:
                salt, expected_hash = stored_hash.split(":", 1)
                computed = hashlib.pbkdf2_hmac(
                    "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000
                )
                return hmac.compare_digest(computed.hex(), expected_hash)
            except (ValueError, TypeError):
                return False

        return False

    def validate_password_strength(self, password: str) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
            )

    def bootstrap_admin(
        self,
        username: str,
        password: str,
        display_name: str,
    ) -> User:
        """Create the very first administrator. Allowed exactly once.

        Gated on BOTH:
          - settings.bootstrap_completed = 0
          - no administrator user currently exists

        On success, the user is created, bootstrap_completed is flipped
        to 1, and an audit entry is written — all inside a single atomic
        block so a failure anywhere rolls back the whole bootstrap.
        """
        if not username or not username.strip():
            raise ValueError("Username is required")
        if not display_name or not display_name.strip():
            raise ValueError("Display name is required")
        self.validate_password_strength(password)

        if self.settings_repo.is_bootstrap_completed():
            raise PermissionError("Bootstrap has already been completed")
        if self.user_repo.count_by_role(UserRole.ADMINISTRATOR) > 0:
            raise PermissionError(
                "Bootstrap is unavailable: an administrator already exists"
            )

        existing = self.user_repo.get_by_username(username.strip())
        if existing:
            raise ValueError("Username already exists")

        with atomic(self.user_repo.conn):
            # Re-check inside the transaction to close the TOCTOU window.
            if self.settings_repo.is_bootstrap_completed():
                raise PermissionError("Bootstrap has already been completed")
            if self.user_repo.count_by_role(UserRole.ADMINISTRATOR) > 0:
                raise PermissionError(
                    "Bootstrap is unavailable: an administrator already exists"
                )

            user = User(
                username=username.strip(),
                password_hash=self._hash_password(password),
                display_name=display_name.strip(),
                role=UserRole.ADMINISTRATOR,
                password_changed_at=self._now_utc(),
            )
            user = self.user_repo.create(user)

            self.settings_repo.mark_bootstrap_completed()

            self.audit_service.log(
                actor_user_id=user.id,
                actor_username=user.username,
                action_code="auth.bootstrap_admin",
                object_type="user",
                object_id=str(user.id),
                after={"username": user.username, "role": user.role},
            )

        logger.info("Bootstrap admin created: username=%s id=%d", user.username, user.id)
        return user

    def create_user(
        self,
        username: str,
        password: str,
        display_name: str,
        role: str,
        admin_user_id: int,
        admin_username: str,
        admin_role: str,
        store_id: Optional[int] = None,
    ) -> User:
        # Privilege escalation guard — only administrators can mint new
        # users. Enforced in the service layer so the check cannot be
        # bypassed by any route.
        require_admin(admin_role)

        if not username or not username.strip():
            raise ValueError("Username is required")
        if not display_name or not display_name.strip():
            raise ValueError("Display name is required")
        if role not in (
            UserRole.FRONT_DESK_AGENT, UserRole.QC_INSPECTOR,
            UserRole.HOST, UserRole.SHIFT_SUPERVISOR,
            UserRole.OPERATIONS_MANAGER, UserRole.ADMINISTRATOR,
        ):
            raise ValueError(f"Invalid role: {role}")

        # Non-admin users MUST be pinned to a store. Only administrators
        # may have store_id=NULL (they operate system-wide).
        if role != UserRole.ADMINISTRATOR and not store_id:
            raise ValueError(
                "store_id is required for non-administrator users"
            )

        self.validate_password_strength(password)

        existing = self.user_repo.get_by_username(username.strip())
        if existing:
            raise ValueError("Username already exists")

        with atomic(self.user_repo.conn):
            user = User(
                store_id=store_id,
                username=username.strip(),
                password_hash=self._hash_password(password),
                display_name=display_name.strip(),
                role=role,
                password_changed_at=self._now_utc(),
            )
            user = self.user_repo.create(user)

            self.audit_service.log(
                actor_user_id=admin_user_id,
                actor_username=admin_username,
                action_code="user.created",
                object_type="user",
                object_id=str(user.id),
                after={"username": user.username, "role": user.role},
            )

        return user

    def authenticate(
        self,
        username: str,
        password: str,
        client_device_id: Optional[str] = None,
    ) -> dict:
        if not username or not password:
            raise ValueError("Username and password are required")

        user = self.user_repo.get_by_username(username)
        if not user:
            raise PermissionError("Invalid credentials")
        if not user.is_active:
            raise PermissionError("Account is inactive")
        if user.is_frozen:
            raise PermissionError("Account is frozen")

        if not self._verify_password(password, user.password_hash):
            self.audit_service.log(
                actor_user_id=user.id,
                actor_username=username,
                action_code="auth.login_failed",
                object_type="user",
                object_id=str(user.id),
                client_device_id=client_device_id,
            )
            raise PermissionError("Invalid credentials")

        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=SESSION_MAX_HOURS)

        with atomic(self.session_repo.conn):
            session = UserSession(
                user_id=user.id,
                session_nonce=secrets.token_urlsafe(32),
                cookie_signature_version="v1",
                csrf_secret=secrets.token_urlsafe(32),
                client_device_id=client_device_id,
                expires_at=expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            session = self.session_repo.create(session)

            self.audit_service.log(
                actor_user_id=user.id,
                actor_username=username,
                action_code="auth.login_success",
                object_type="user_session",
                object_id=str(session.id),
                client_device_id=client_device_id,
            )

        return {"user": user, "session": session}

    def validate_session(self, session_nonce: str) -> dict:
        session = self.session_repo.get_by_nonce(session_nonce)
        if not session:
            raise PermissionError("Invalid session")
        if session.revoked_at is not None:
            raise PermissionError("Session has been revoked")

        now = datetime.now(timezone.utc)
        expires = datetime.fromisoformat(session.expires_at.replace("Z", "+00:00"))
        if now > expires:
            raise PermissionError("Session has expired")

        if session.last_seen_at:
            last_seen = datetime.fromisoformat(session.last_seen_at.replace("Z", "+00:00"))
            idle = now - last_seen
            if idle > timedelta(minutes=SESSION_IDLE_MINUTES):
                raise PermissionError("Session idle timeout")

        session.last_seen_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.session_repo.update(session)

        user = self.user_repo.get_by_id(session.user_id)
        if not user or not user.is_active or user.is_frozen:
            raise PermissionError("User account is not accessible")

        return {"user": user, "session": session}

    def verify_password_for_approval(
        self, user_id: int, password: str
    ) -> bool:
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        if user.is_frozen:
            raise PermissionError("Account is frozen")
        return self._verify_password(password, user.password_hash)

    def logout(self, session_id: int, user_id: int, username: str) -> None:
        with atomic(self.session_repo.conn):
            self.session_repo.revoke(session_id)

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="auth.logout",
                object_type="user_session",
                object_id=str(session_id),
            )

    def freeze_user(
        self,
        target_user_id: int,
        admin_user_id: int,
        admin_username: str,
        admin_role: str,
    ) -> User:
        require_admin(admin_role)
        user = self.user_repo.get_by_id(target_user_id)
        if not user:
            raise ValueError("User not found")

        user.is_frozen = True
        with atomic(self.user_repo.conn):
            user = self.user_repo.update(user)

            self.session_repo.revoke_all_for_user(target_user_id)

            self.audit_service.log(
                actor_user_id=admin_user_id,
                actor_username=admin_username,
                action_code="user.frozen",
                object_type="user",
                object_id=str(target_user_id),
                before={"is_frozen": False},
                after={"is_frozen": True},
            )

        return user

    def unfreeze_user(
        self,
        target_user_id: int,
        admin_user_id: int,
        admin_username: str,
        admin_role: str,
    ) -> User:
        require_admin(admin_role)
        user = self.user_repo.get_by_id(target_user_id)
        if not user:
            raise ValueError("User not found")

        user.is_frozen = False
        with atomic(self.user_repo.conn):
            user = self.user_repo.update(user)

            self.audit_service.log(
                actor_user_id=admin_user_id,
                actor_username=admin_username,
                action_code="user.unfrozen",
                object_type="user",
                object_id=str(target_user_id),
                before={"is_frozen": True},
                after={"is_frozen": False},
            )

        return user
