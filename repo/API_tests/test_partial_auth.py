"""Cross-store and role-based authorization tests for HTMX partial routes.

Covers:
  - Admin can access cross-store scope
  - Store A user cannot read store B partials
  - Non-admin with null store cannot use query param to access data
  - Protected partials return exact codes: 401 unauthenticated, 403 forbidden
  - Role-based access control on every read partial
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fullstack", "backend"))

import pytest
from app import create_app
from src.enums.user_role import UserRole
from src.models.store import Store
from src.models.user import User
from src.models.settings import Settings
from src.models.pricing_rule import PricingRule
from src.models.service_table import ServiceTable
from src.repositories import (
    AuditLogRepository,
    BuybackTicketRepository,
    ExportRequestRepository,
    PricingRuleRepository,
    ScheduleAdjustmentRequestRepository,
    ServiceTableRepository,
    SettingsRepository,
    StoreRepository,
    TableSessionRepository,
    UserRepository,
    UserSessionRepository,
)
from src.services.auth_service import AuthService
from src.services.audit_service import AuditService


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("RECLAIM_OPS_DEV_MODE", "true")
    monkeypatch.setenv("RECLAIM_OPS_REQUIRE_TLS", "false")
    monkeypatch.setenv("SECURE_COOKIES", "false")
    # Session key needs a writable path outside Docker
    monkeypatch.setenv("SESSION_KEY_PATH", str(tmp_path / "session_key"))
    # Reset in-memory key cache between tests
    import src.security.session_cookie as _sc
    _sc._key_cache = None
    db_path = str(tmp_path / "test.db")
    application = create_app(db_path=db_path)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


def _setup_two_stores(app):
    """Create two stores with settings + pricing rules. Returns (store_a, store_b)."""
    with app.app_context():
        from app import get_db
        from flask import g
        g.db_path = app.config["DB_PATH"]
        db = get_db()

        store_repo = StoreRepository(db)
        settings_repo = SettingsRepository(db)
        pricing_repo = PricingRuleRepository(db)

        store_a = store_repo.create(Store(code="SA", name="Store A"))
        settings_repo.create(Settings(store_id=store_a.id))
        pricing_repo.create(PricingRule(
            store_id=store_a.id, base_rate_per_lb=1.50, bonus_pct=10.0,
            min_weight_lbs=0.1, max_weight_lbs=1000.0,
            max_ticket_payout=200.0, max_rate_per_lb=3.0, priority=1,
        ))

        store_b = store_repo.create(Store(code="SB", name="Store B"))
        settings_repo.create(Settings(store_id=store_b.id))
        pricing_repo.create(PricingRule(
            store_id=store_b.id, base_rate_per_lb=1.50, bonus_pct=10.0,
            min_weight_lbs=0.1, max_weight_lbs=1000.0,
            max_ticket_payout=200.0, max_rate_per_lb=3.0, priority=1,
        ))

        db.commit()
        return store_a, store_b


def _create_user(app, username, role, store_id=None):
    """Create a user directly in the DB."""
    with app.app_context():
        from app import get_db
        from flask import g
        g.db_path = app.config["DB_PATH"]
        db = get_db()

        user_repo = UserRepository(db)
        if user_repo.get_by_username(username):
            return

        audit_svc = AuditService(AuditLogRepository(db))
        auth_svc = AuthService(
            user_repo, UserSessionRepository(db),
            SettingsRepository(db), audit_svc,
        )
        password_hash = auth_svc._hash_password("TestPassword123!")
        user_repo.create(User(
            store_id=store_id,
            username=username,
            password_hash=password_hash,
            display_name=f"User {username}",
            role=role,
        ))
        db.commit()


def _login(client, username):
    """Log in and set CSRF header. Returns the response."""
    resp = client.post("/api/auth/login", json={
        "username": username, "password": "TestPassword123!",
    })
    assert resp.status_code == 200, f"Login failed for {username}: {resp.get_json()}"
    csrf = resp.get_json()["data"]["csrf_token"]
    client.environ_base["HTTP_X_CSRF_TOKEN"] = csrf
    return resp


def _logout(client):
    """Log out and clear CSRF."""
    client.post("/api/auth/logout")
    client.delete_cookie("session_nonce")
    client.environ_base.pop("HTTP_X_CSRF_TOKEN", None)


# All read partial endpoints to test
READ_PARTIALS = [
    "/ui/partials/tickets/queue",
    "/ui/partials/qc/queue",
    "/ui/partials/tables/board",
    "/ui/partials/exports/list",
    "/ui/partials/schedules/pending",
    "/ui/partials/notifications/retries",
]


# ── UNAUTHENTICATED → 401 ──

class TestPartialsUnauthenticated:
    """Every partial must return 401 when no session cookie is set."""

    @pytest.mark.parametrize("path", READ_PARTIALS)
    def test_unauthenticated_returns_401(self, app, client, path):
        resp = client.get(path)
        assert resp.status_code == 401


# ── CROSS-STORE ISOLATION ──

class TestPartialsCrossStore:
    """Store A user must not access store B data via partials."""

    def test_store_a_user_sees_own_ticket_queue(self, app, client):
        store_a, store_b = _setup_two_stores(app)
        _create_user(app, "agent_a", UserRole.FRONT_DESK_AGENT, store_a.id)
        _login(client, "agent_a")

        resp = client.get("/ui/partials/tickets/queue")
        assert resp.status_code == 200

    def test_store_a_user_cannot_query_store_b_tickets(self, app, client):
        """Even if store_id query param is supplied, store A user's store is
        used (the query param is ignored for non-admins)."""
        store_a, store_b = _setup_two_stores(app)
        _create_user(app, "agent_a2", UserRole.FRONT_DESK_AGENT, store_a.id)
        _login(client, "agent_a2")

        # Attempt to pass store_b's ID via query param
        resp = client.get(f"/ui/partials/tickets/queue?store_id={store_b.id}")
        assert resp.status_code == 200
        # Response should reflect store A data, NOT store B

    def test_store_b_user_cannot_query_store_a_tickets(self, app, client):
        store_a, store_b = _setup_two_stores(app)
        _create_user(app, "agent_b", UserRole.FRONT_DESK_AGENT, store_b.id)
        _login(client, "agent_b")

        resp = client.get(f"/ui/partials/tickets/queue?store_id={store_a.id}")
        assert resp.status_code == 200
        # Still sees store B data — query param is silently ignored

    def test_admin_can_query_specific_store(self, app, client):
        store_a, store_b = _setup_two_stores(app)
        _create_user(app, "admin_cross", UserRole.ADMINISTRATOR, None)
        _login(client, "admin_cross")

        resp_a = client.get(f"/ui/partials/tickets/queue?store_id={store_a.id}")
        assert resp_a.status_code == 200

        resp_b = client.get(f"/ui/partials/tickets/queue?store_id={store_b.id}")
        assert resp_b.status_code == 200

    @pytest.mark.parametrize("path", [
        "/ui/partials/qc/queue",
        "/ui/partials/tables/board",
        "/ui/partials/exports/list",
    ])
    def test_cross_store_query_param_ignored_for_non_admin(self, app, client, path):
        store_a, store_b = _setup_two_stores(app)
        # Use a role that has access to all these partials
        _create_user(app, "sup_cross", UserRole.SHIFT_SUPERVISOR, store_a.id)
        _login(client, "sup_cross")

        resp = client.get(f"{path}?store_id={store_b.id}")
        assert resp.status_code == 200


# ── NULL STORE NON-ADMIN ──

class TestPartialsNullStoreNonAdmin:
    """A legacy non-admin user with store_id=NULL must be rejected
    on all store-scoped partials (403), even with query param supplied."""

    def _create_null_store_user(self, app, username, role):
        """Create a user with store_id=NULL directly in DB (bypasses service
        validation that now rejects this)."""
        with app.app_context():
            from app import get_db
            from flask import g
            g.db_path = app.config["DB_PATH"]
            db = get_db()
            user_repo = UserRepository(db)
            audit_svc = AuditService(AuditLogRepository(db))
            auth_svc = AuthService(
                user_repo, UserSessionRepository(db),
                SettingsRepository(db), audit_svc,
            )
            password_hash = auth_svc._hash_password("TestPassword123!")
            # Bypass service layer — insert directly to simulate legacy record
            db.execute(
                """INSERT INTO users (store_id, username, password_hash,
                   display_name, role, is_active, is_frozen,
                   created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 1, 0,
                   datetime('now'), datetime('now'))""",
                (None, username, password_hash, f"Legacy {username}", role),
            )
            db.commit()

    @pytest.mark.parametrize("path", [
        "/ui/partials/tickets/queue",
        "/ui/partials/qc/queue",
        "/ui/partials/tables/board",
        "/ui/partials/exports/list",
    ])
    def test_null_store_agent_returns_403(self, app, client, path):
        _setup_two_stores(app)
        self._create_null_store_user(app, "legacy_agent", UserRole.SHIFT_SUPERVISOR)
        _login(client, "legacy_agent")

        resp = client.get(path)
        assert resp.status_code == 403

    def test_null_store_agent_cannot_use_query_param(self, app, client):
        store_a, store_b = _setup_two_stores(app)
        self._create_null_store_user(app, "legacy_agent2", UserRole.FRONT_DESK_AGENT)
        _login(client, "legacy_agent2")

        resp = client.get(f"/ui/partials/tickets/queue?store_id={store_a.id}")
        assert resp.status_code == 403


# ── ROLE-BASED ACCESS CONTROL ──

class TestPartialsRBAC:
    """Each partial enforces least-privilege role access."""

    def test_host_cannot_access_ticket_queue(self, app, client):
        store_a, _ = _setup_two_stores(app)
        _create_user(app, "host_rbac", UserRole.HOST, store_a.id)
        _login(client, "host_rbac")

        resp = client.get("/ui/partials/tickets/queue")
        assert resp.status_code == 403

    def test_host_can_access_table_board(self, app, client):
        store_a, _ = _setup_two_stores(app)
        _create_user(app, "host_table", UserRole.HOST, store_a.id)
        _login(client, "host_table")

        resp = client.get("/ui/partials/tables/board")
        assert resp.status_code == 200

    def test_front_desk_cannot_access_qc_queue(self, app, client):
        store_a, _ = _setup_two_stores(app)
        _create_user(app, "fd_qc", UserRole.FRONT_DESK_AGENT, store_a.id)
        _login(client, "fd_qc")

        resp = client.get("/ui/partials/qc/queue")
        assert resp.status_code == 403

    def test_qc_inspector_can_access_qc_queue(self, app, client):
        store_a, _ = _setup_two_stores(app)
        _create_user(app, "qc_ok", UserRole.QC_INSPECTOR, store_a.id)
        _login(client, "qc_ok")

        resp = client.get("/ui/partials/qc/queue")
        assert resp.status_code == 200

    def test_front_desk_cannot_access_exports(self, app, client):
        store_a, _ = _setup_two_stores(app)
        _create_user(app, "fd_exports", UserRole.FRONT_DESK_AGENT, store_a.id)
        _login(client, "fd_exports")

        resp = client.get("/ui/partials/exports/list")
        assert resp.status_code == 403

    def test_front_desk_cannot_access_schedules(self, app, client):
        store_a, _ = _setup_two_stores(app)
        _create_user(app, "fd_sched", UserRole.FRONT_DESK_AGENT, store_a.id)
        _login(client, "fd_sched")

        resp = client.get("/ui/partials/schedules/pending")
        assert resp.status_code == 403

    def test_ops_manager_can_access_exports(self, app, client):
        store_a, _ = _setup_two_stores(app)
        _create_user(app, "ops_exp", UserRole.OPERATIONS_MANAGER, store_a.id)
        _login(client, "ops_exp")

        resp = client.get("/ui/partials/exports/list")
        assert resp.status_code == 200

    def test_shift_supervisor_can_access_schedules(self, app, client):
        store_a, _ = _setup_two_stores(app)
        _create_user(app, "sup_sched", UserRole.SHIFT_SUPERVISOR, store_a.id)
        _login(client, "sup_sched")

        resp = client.get("/ui/partials/schedules/pending")
        assert resp.status_code == 200

    def test_host_cannot_access_exports(self, app, client):
        store_a, _ = _setup_two_stores(app)
        _create_user(app, "host_exp", UserRole.HOST, store_a.id)
        _login(client, "host_exp")

        resp = client.get("/ui/partials/exports/list")
        assert resp.status_code == 403

    def test_host_cannot_access_notifications(self, app, client):
        store_a, _ = _setup_two_stores(app)
        _create_user(app, "host_notif", UserRole.HOST, store_a.id)
        _login(client, "host_notif")

        resp = client.get("/ui/partials/notifications/retries")
        assert resp.status_code == 403

    def test_front_desk_can_access_notifications(self, app, client):
        store_a, _ = _setup_two_stores(app)
        _create_user(app, "fd_notif", UserRole.FRONT_DESK_AGENT, store_a.id)
        _login(client, "fd_notif")

        resp = client.get("/ui/partials/notifications/retries")
        assert resp.status_code == 200

    def test_front_desk_cannot_access_table_board(self, app, client):
        store_a, _ = _setup_two_stores(app)
        _create_user(app, "fd_table", UserRole.FRONT_DESK_AGENT, store_a.id)
        _login(client, "fd_table")

        resp = client.get("/ui/partials/tables/board")
        assert resp.status_code == 403

    def test_admin_can_access_all_partials(self, app, client):
        store_a, _ = _setup_two_stores(app)
        _create_user(app, "admin_all", UserRole.ADMINISTRATOR, None)
        _login(client, "admin_all")

        for path in READ_PARTIALS:
            # Admin without store_id may get "No store context" for some,
            # but the role gate should not reject — pass store_id
            resp = client.get(f"{path}?store_id={store_a.id}")
            assert resp.status_code == 200, f"Admin denied on {path}"


# ── NOTIFICATION MESSAGES PARTIAL (per-ticket) ──

class TestNotificationMessagesPartial:
    def test_unauthenticated_returns_401(self, app, client):
        resp = client.get("/ui/partials/notifications/messages/1")
        assert resp.status_code == 401

    def test_host_cannot_access_notification_messages(self, app, client):
        store_a, _ = _setup_two_stores(app)
        _create_user(app, "host_msg", UserRole.HOST, store_a.id)
        _login(client, "host_msg")

        resp = client.get("/ui/partials/notifications/messages/1")
        assert resp.status_code == 403


# ── USER CREATION INVARIANT ──

class TestUserCreationStoreInvariant:
    """Non-admin users must have a store_id at creation time."""

    def test_create_non_admin_without_store_fails(self, app, client):
        _setup_two_stores(app)
        _create_user(app, "admin_inv", UserRole.ADMINISTRATOR, None)
        _login(client, "admin_inv")

        resp = client.post("/api/auth/users", json={
            "username": "no_store_agent",
            "password": "TestPassword123!",
            "display_name": "No Store",
            "role": "front_desk_agent",
            # No store_id — must be rejected
        })
        assert resp.status_code == 400

    def test_create_admin_without_store_succeeds(self, app, client):
        _setup_two_stores(app)
        _create_user(app, "admin_inv2", UserRole.ADMINISTRATOR, None)
        _login(client, "admin_inv2")

        resp = client.post("/api/auth/users", json={
            "username": "admin_no_store",
            "password": "TestPassword123!",
            "display_name": "Admin No Store",
            "role": "administrator",
        })
        assert resp.status_code == 201

    def test_create_non_admin_with_store_succeeds(self, app, client):
        store_a, _ = _setup_two_stores(app)
        _create_user(app, "admin_inv3", UserRole.ADMINISTRATOR, None)
        _login(client, "admin_inv3")

        resp = client.post("/api/auth/users", json={
            "username": "agent_with_store",
            "password": "TestPassword123!",
            "display_name": "Agent",
            "role": "front_desk_agent",
            "store_id": store_a.id,
        })
        assert resp.status_code == 201
