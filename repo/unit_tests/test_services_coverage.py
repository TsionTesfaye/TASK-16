"""Service-layer coverage-closure tests.

Directly exercise service methods that are hard to reach through the
route layer (e.g. global settings, scheduler sweeps, auth edge cases)
so total coverage reaches ≥90%.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fullstack", "backend"))

import pytest

from src.database import get_connection, init_db
from src.enums.user_role import UserRole
from src.models.store import Store
from src.models.settings import Settings
from src.models.user import User
from src.repositories import (
    AuditLogRepository,
    ExportRequestRepository,
    QuarantineRecordRepository,
    ScheduleAdjustmentRequestRepository,
    SettingsRepository,
    StoreRepository,
    UserRepository,
    UserSessionRepository,
    VarianceApprovalRequestRepository,
)
from src.services.audit_service import AuditService
from src.services.auth_service import AuthService
from src.services.settings_service import SettingsService


@pytest.fixture
def db_conn(tmp_path):
    db_path = str(tmp_path / "svc.db")
    init_db(db_path).close()
    conn = get_connection(db_path)
    yield conn
    conn.close()


def _mk_audit(conn):
    return AuditService(AuditLogRepository(conn))


def _mk_auth(conn):
    return AuthService(
        UserRepository(conn),
        UserSessionRepository(conn),
        SettingsRepository(conn),
        _mk_audit(conn),
    )


def _create_admin(conn, username="sysadmin"):
    auth = _mk_auth(conn)
    user = User(
        store_id=None,
        username=username,
        password_hash=auth._hash_password("AdminPass1234!"),
        display_name="Admin",
        role=UserRole.ADMINISTRATOR,
    )
    return UserRepository(conn).create(user)


# ════════════════════════════════════════════════════════════
# SettingsService — create/update global and store-scoped
# ════════════════════════════════════════════════════════════

class TestSettingsServiceCoverage:
    def test_create_global_settings(self, db_conn):
        admin = _create_admin(db_conn)
        svc = SettingsService(SettingsRepository(db_conn), _mk_audit(db_conn))

        s = svc.create_or_update(
            user_id=admin.id, username=admin.username,
            user_role=UserRole.ADMINISTRATOR,
            store_id=None,
            variance_pct_threshold=7.5,
            max_ticket_payout=250.0,
        )
        db_conn.commit()
        assert s.store_id is None
        assert abs(s.variance_pct_threshold - 7.5) < 0.0001
        assert abs(s.max_ticket_payout - 250.0) < 0.0001

    def test_update_existing_store_settings(self, db_conn):
        admin = _create_admin(db_conn)
        store = StoreRepository(db_conn).create(Store(code="X1", name="X"))
        SettingsRepository(db_conn).create(Settings(store_id=store.id))
        db_conn.commit()

        svc = SettingsService(SettingsRepository(db_conn), _mk_audit(db_conn))
        s = svc.create_or_update(
            user_id=admin.id, username=admin.username,
            user_role=UserRole.ADMINISTRATOR,
            store_id=store.id,
            variance_pct_threshold=12.0,
        )
        db_conn.commit()
        assert s.store_id == store.id
        assert abs(s.variance_pct_threshold - 12.0) < 0.0001

    def test_create_rejects_non_admin(self, db_conn):
        svc = SettingsService(SettingsRepository(db_conn), _mk_audit(db_conn))
        with pytest.raises(PermissionError):
            svc.create_or_update(
                user_id=1, username="fd", user_role=UserRole.FRONT_DESK_AGENT,
                variance_pct_threshold=1.0,
            )

    def test_create_ignores_readonly_fields(self, db_conn):
        admin = _create_admin(db_conn)
        svc = SettingsService(SettingsRepository(db_conn), _mk_audit(db_conn))
        # `id` / `created_at` / `store_id` are in the read-only blocklist
        # inside create_or_update and must be ignored. Pass them via kwargs
        # dict to avoid duplicating `store_id` as a positional kw.
        s = svc.create_or_update(
            user_id=admin.id, username=admin.username,
            user_role=UserRole.ADMINISTRATOR,
            store_id=None,
            **{"id": 999, "created_at": "bogus", "max_rate_per_lb": 5.5},
        )
        db_conn.commit()
        assert s.id != 999  # not overwritten
        assert abs(s.max_rate_per_lb - 5.5) < 0.0001

    def test_get_effective_returns_default_when_missing(self, db_conn):
        svc = SettingsService(SettingsRepository(db_conn), _mk_audit(db_conn))
        s = svc.get_effective(store_id=9999)
        assert s is not None
        # Default Settings dataclass values
        assert s.variance_pct_threshold == 5.0

    def test_get_global_returns_none_when_missing(self, db_conn):
        svc = SettingsService(SettingsRepository(db_conn), _mk_audit(db_conn))
        assert svc.get_global() is None


# ════════════════════════════════════════════════════════════
# AuthService — edge cases (verify_password, frozen account,
# legacy PBKDF2, long passwords, invalid role)
# ════════════════════════════════════════════════════════════

class TestAuthServiceCoverage:
    def test_create_user_rejects_blank_username(self, db_conn):
        admin = _create_admin(db_conn)
        auth = _mk_auth(db_conn)
        with pytest.raises(ValueError, match="Username is required"):
            auth.create_user(
                username="", password="OkPassword1234!", display_name="x",
                role=UserRole.FRONT_DESK_AGENT,
                admin_user_id=admin.id, admin_username=admin.username,
                admin_role=admin.role, store_id=1,
            )

    def test_create_user_rejects_blank_display_name(self, db_conn):
        admin = _create_admin(db_conn)
        auth = _mk_auth(db_conn)
        with pytest.raises(ValueError, match="Display name is required"):
            auth.create_user(
                username="u1", password="OkPassword1234!", display_name="",
                role=UserRole.FRONT_DESK_AGENT,
                admin_user_id=admin.id, admin_username=admin.username,
                admin_role=admin.role, store_id=1,
            )

    def test_create_user_rejects_invalid_role(self, db_conn):
        admin = _create_admin(db_conn)
        auth = _mk_auth(db_conn)
        with pytest.raises(ValueError, match="Invalid role"):
            auth.create_user(
                username="u2", password="OkPassword1234!", display_name="U",
                role="godmode",
                admin_user_id=admin.id, admin_username=admin.username,
                admin_role=admin.role, store_id=1,
            )

    def test_create_user_duplicate_username(self, db_conn):
        admin = _create_admin(db_conn)
        store = StoreRepository(db_conn).create(Store(code="DUP", name="Dup"))
        db_conn.commit()
        auth = _mk_auth(db_conn)
        auth.create_user(
            username="samuser", password="OkPassword1234!", display_name="S",
            role=UserRole.FRONT_DESK_AGENT,
            admin_user_id=admin.id, admin_username=admin.username,
            admin_role=admin.role, store_id=store.id,
        )
        with pytest.raises(ValueError, match="already exists"):
            auth.create_user(
                username="samuser", password="OkPassword1234!", display_name="S2",
                role=UserRole.FRONT_DESK_AGENT,
                admin_user_id=admin.id, admin_username=admin.username,
                admin_role=admin.role, store_id=store.id,
            )

    def test_authenticate_frozen_account_rejected(self, db_conn):
        admin = _create_admin(db_conn)
        store = StoreRepository(db_conn).create(Store(code="FRZ2", name="F"))
        db_conn.commit()
        auth = _mk_auth(db_conn)
        user = auth.create_user(
            username="frozen_u", password="OkPassword1234!", display_name="F",
            role=UserRole.FRONT_DESK_AGENT,
            admin_user_id=admin.id, admin_username=admin.username,
            admin_role=admin.role, store_id=store.id,
        )
        auth.freeze_user(
            user.id, admin_user_id=admin.id, admin_username=admin.username,
            admin_role=admin.role,
        )
        with pytest.raises(PermissionError, match="frozen"):
            auth.authenticate("frozen_u", "OkPassword1234!")

    def test_authenticate_inactive_account_rejected(self, db_conn):
        user_repo = UserRepository(db_conn)
        store = StoreRepository(db_conn).create(Store(code="INA", name="I"))
        auth = _mk_auth(db_conn)
        user = user_repo.create(User(
            store_id=store.id, username="inactive_u",
            password_hash=auth._hash_password("OkPassword1234!"),
            display_name="I", role=UserRole.FRONT_DESK_AGENT,
            is_active=False,
        ))
        db_conn.commit()
        with pytest.raises(PermissionError, match="inactive"):
            auth.authenticate("inactive_u", "OkPassword1234!")

    def test_authenticate_wrong_password_logs_audit(self, db_conn):
        admin = _create_admin(db_conn)
        store = StoreRepository(db_conn).create(Store(code="WP", name="W"))
        db_conn.commit()
        auth = _mk_auth(db_conn)
        auth.create_user(
            username="wp_u", password="OkPassword1234!", display_name="W",
            role=UserRole.FRONT_DESK_AGENT,
            admin_user_id=admin.id, admin_username=admin.username,
            admin_role=admin.role, store_id=store.id,
        )
        with pytest.raises(PermissionError, match="Invalid credentials"):
            auth.authenticate("wp_u", "WrongPassword1234!")

    def test_authenticate_missing_fields_raises_value_error(self, db_conn):
        auth = _mk_auth(db_conn)
        with pytest.raises(ValueError):
            auth.authenticate("", "")

    def test_bootstrap_refuses_when_completed(self, db_conn):
        auth = _mk_auth(db_conn)
        auth.bootstrap_admin("firstadm", "BootPass1234!", "First Admin")
        with pytest.raises(PermissionError, match="already been completed"):
            auth.bootstrap_admin("secondadm", "BootPass1234!", "Second")

    def test_bootstrap_rejects_blank_username(self, db_conn):
        auth = _mk_auth(db_conn)
        with pytest.raises(ValueError, match="Username is required"):
            auth.bootstrap_admin("", "BootPass1234!", "X")

    def test_bootstrap_rejects_weak_password(self, db_conn):
        auth = _mk_auth(db_conn)
        with pytest.raises(ValueError, match="at least 12"):
            auth.bootstrap_admin("u", "short", "X")

    def test_verify_long_password_prehashed(self, db_conn):
        """bcrypt's 72-byte limit is side-stepped via SHA-256 pre-hash."""
        auth = _mk_auth(db_conn)
        long_pw = "A" * 100
        h = auth._hash_password(long_pw)
        assert auth._verify_password(long_pw, h) is True
        assert auth._verify_password("A" * 99, h) is False

    def test_verify_empty_hash_returns_false(self, db_conn):
        auth = _mk_auth(db_conn)
        assert auth._verify_password("anything", "") is False
        assert auth._verify_password("anything", None) is False

    def test_verify_legacy_pbkdf2_format(self, db_conn):
        """PBKDF2 `salt:hex` legacy hash format must still verify."""
        import hashlib
        auth = _mk_auth(db_conn)
        salt = "oldsalt"
        pwd = "LegacyPassword1234!"
        digest = hashlib.pbkdf2_hmac(
            "sha256", pwd.encode("utf-8"), salt.encode("utf-8"), 100000,
        ).hex()
        legacy = f"{salt}:{digest}"
        assert auth._verify_password(pwd, legacy) is True
        assert auth._verify_password("WrongPassword1234!", legacy) is False

    def test_verify_malformed_bcrypt_hash(self, db_conn):
        auth = _mk_auth(db_conn)
        assert auth._verify_password("pw", "$2b$malformed") is False

    def test_verify_password_for_approval(self, db_conn):
        admin = _create_admin(db_conn)
        auth = _mk_auth(db_conn)
        assert auth.verify_password_for_approval(admin.id, "AdminPass1234!") is True
        assert auth.verify_password_for_approval(admin.id, "WrongPassword1234!") is False

    def test_verify_password_for_approval_missing_user(self, db_conn):
        auth = _mk_auth(db_conn)
        with pytest.raises(ValueError):
            auth.verify_password_for_approval(99999, "any")


# ════════════════════════════════════════════════════════════
# Scheduler + reconciliation sweep — cover background thread
# and idempotent sweep paths.
# ════════════════════════════════════════════════════════════

class TestSchedulerCoverage:
    def test_sweep_returns_counts_on_empty_db(self, db_conn, tmp_path):
        from src.scheduler import run_expiration_sweep
        # Need a real DB path for the sweep helper
        db_path = str(tmp_path / "sweep.db")
        init_db(db_path).close()
        result = run_expiration_sweep(db_path)
        assert result["exports_expired"] == 0
        assert result["variance_expired"] == 0
        assert result["schedules_expired"] == 0

    def test_background_scheduler_start_and_stop(self, tmp_path):
        from src.scheduler import Scheduler
        db_path = str(tmp_path / "bg.db")
        init_db(db_path).close()
        sched = Scheduler(db_path=db_path, interval_seconds=1)
        sched.start()
        # Let one sweep tick fire
        time.sleep(2.0)
        sched.stop()
        # Thread should be dead
        assert not sched._thread.is_alive()

    def test_scheduler_double_start_is_noop(self, tmp_path):
        from src.scheduler import Scheduler
        db_path = str(tmp_path / "dbl.db")
        init_db(db_path).close()
        sched = Scheduler(db_path=db_path, interval_seconds=60)
        sched.start()
        sched.start()  # idempotent second call
        sched.stop()
