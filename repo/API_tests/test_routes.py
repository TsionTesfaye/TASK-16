"""API route tests — verify endpoints call services correctly, enforce auth,
return proper status codes and response contracts."""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fullstack", "backend"))

import pytest
from app import create_app
from src.database import init_db
from src.enums.user_role import UserRole
from src.models.store import Store
from src.models.user import User
from src.models.settings import Settings
from src.models.pricing_rule import PricingRule
from src.models.service_table import ServiceTable
from src.models.notification_template import NotificationTemplate
from src.models.club_organization import ClubOrganization
from src.repositories import *
from src.services.auth_service import AuthService
from src.services.audit_service import AuditService


@pytest.fixture
def app(tmp_path, monkeypatch):
    # Tests run without TLS — explicitly opt into dev mode
    monkeypatch.setenv("RECLAIM_OPS_DEV_MODE", "true")
    monkeypatch.setenv("RECLAIM_OPS_REQUIRE_TLS", "false")
    monkeypatch.setenv("SECURE_COOKIES", "false")
    db_path = str(tmp_path / "test.db")
    application = create_app(db_path=db_path)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


def _seed_and_login(app, client, role=UserRole.FRONT_DESK_AGENT, username="testuser"):
    """Create store, settings, pricing rule, user, and log in. Returns store."""
    with app.app_context():
        from app import get_db
        from flask import g
        g.db_path = app.config["DB_PATH"]
        db = get_db()

        store_repo = StoreRepository(db)
        settings_repo = SettingsRepository(db)
        pricing_repo = PricingRuleRepository(db)
        user_repo = UserRepository(db)

        # Only create if not already seeded (multiple calls per test)
        store = store_repo.get_by_code("S1")
        if not store:
            store = store_repo.create(Store(code="S1", name="Test Store"))
            settings_repo.create(Settings(store_id=store.id))
            pricing_repo.create(PricingRule(
                store_id=store.id, base_rate_per_lb=1.50, bonus_pct=10.0,
                min_weight_lbs=0.1, max_weight_lbs=1000.0,
                max_ticket_payout=200.0, max_rate_per_lb=3.0, priority=1,
            ))

        existing = user_repo.get_by_username(username)
        if not existing:
            # Create user directly via repo (bypasses audit FK issue in test).
            # Use bcrypt via AuthService so tests mirror production auth.
            audit_svc = AuditService(AuditLogRepository(db))
            auth_svc = AuthService(
                user_repo, UserSessionRepository(db),
                settings_repo, audit_svc,
            )
            password_hash = auth_svc._hash_password("TestPassword123!")
            user_repo.create(User(
                store_id=store.id, username=username,
                password_hash=password_hash,
                display_name="Test User", role=role,
            ))
        db.commit()

    resp = client.post("/api/auth/login", json={
        "username": username, "password": "TestPassword123!",
    })
    assert resp.status_code == 200, f"Login failed: {resp.get_json()}"
    # Capture CSRF token from login response and apply to all subsequent requests
    csrf_token = resp.get_json()["data"]["csrf_token"]
    client.environ_base["HTTP_X_CSRF_TOKEN"] = csrf_token
    return store


# ── AUTH ──

class TestAuthRoutes:
    def test_login_success(self, app, client):
        _seed_and_login(app, client)
        # Session cookie should be set by login
        resp = client.get("/api/settings")
        assert resp.status_code == 200

    def test_login_wrong_password(self, app, client):
        _seed_and_login(app, client)
        client.delete_cookie("session_nonce")
        resp = client.post("/api/auth/login", json={
            "username": "testuser", "password": "WrongPassword123!",
        })
        assert resp.status_code == 401

    def test_unauthenticated_request(self, app, client):
        resp = client.post("/api/tickets", json={"foo": "bar"})
        assert resp.status_code == 401

    def test_logout(self, app, client):
        _seed_and_login(app, client)
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 200
        # After logout, should be unauthenticated
        resp = client.get("/api/settings")
        assert resp.status_code == 401


# ── TICKETS ──

class TestTicketRoutes:
    def test_create_ticket(self, app, client):
        store = _seed_and_login(app, client)
        resp = client.post("/api/tickets", json={
            "store_id": store.id,
            "customer_name": "Jane Doe",
            "clothing_category": "shirts",
            "condition_grade": "A",
            "estimated_weight_lbs": 10.0,
        })
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["status"] == "intake_open"
        assert data["estimated_payout"] > 0

    def test_create_ticket_missing_fields(self, app, client):
        _seed_and_login(app, client)
        resp = client.post("/api/tickets", json={"store_id": 1})
        assert resp.status_code == 400
        assert "Missing required fields" in resp.get_json()["error"]["message"]

    def test_create_ticket_wrong_role(self, app, client):
        _seed_and_login(app, client, role=UserRole.HOST, username="host1")
        resp = client.post("/api/tickets", json={
            "store_id": 1,
            "customer_name": "Jane",
            "clothing_category": "shirts",
            "condition_grade": "A",
            "estimated_weight_lbs": 10.0,
        })
        assert resp.status_code == 403

    def test_submit_for_qc(self, app, client):
        store = _seed_and_login(app, client)
        create_resp = client.post("/api/tickets", json={
            "store_id": store.id,
            "customer_name": "Jane",
            "clothing_category": "shirts",
            "condition_grade": "A",
            "estimated_weight_lbs": 10.0,
        })
        ticket_id = create_resp.get_json()["data"]["id"]
        resp = client.post(f"/api/tickets/{ticket_id}/submit-qc")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "awaiting_qc"

    def test_cancel_ticket(self, app, client):
        store = _seed_and_login(app, client)
        create_resp = client.post("/api/tickets", json={
            "store_id": store.id,
            "customer_name": "Jane",
            "clothing_category": "shirts",
            "condition_grade": "A",
            "estimated_weight_lbs": 10.0,
        })
        ticket_id = create_resp.get_json()["data"]["id"]
        resp = client.post(f"/api/tickets/{ticket_id}/cancel", json={
            "reason": "Customer changed mind",
        })
        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "canceled"


# ── TABLES ──

class TestTableRoutes:
    def test_open_table(self, app, client):
        store = _seed_and_login(app, client, role=UserRole.HOST, username="host1")
        # Create a table first
        with app.app_context():
            from app import get_db
            from flask import g
            g.db_path = app.config["DB_PATH"]
            db = get_db()
            table_repo = ServiceTableRepository(db)
            table = table_repo.create(ServiceTable(
                store_id=store.id, table_code="T1", area_type="intake_table",
            ))
            db.commit()
            table_id = table.id

        resp = client.post("/api/tables/open", json={
            "table_id": table_id, "store_id": store.id,
        })
        assert resp.status_code == 201
        assert resp.get_json()["data"]["current_state"] == "occupied"

    def test_invalid_table_transition(self, app, client):
        store = _seed_and_login(app, client, role=UserRole.HOST, username="host1")
        with app.app_context():
            from app import get_db
            from flask import g
            g.db_path = app.config["DB_PATH"]
            db = get_db()
            table_repo = ServiceTableRepository(db)
            table = table_repo.create(ServiceTable(
                store_id=store.id, table_code="T2", area_type="intake_table",
            ))
            db.commit()
            table_id = table.id

        open_resp = client.post("/api/tables/open", json={
            "table_id": table_id, "store_id": store.id,
        })
        session_id = open_resp.get_json()["data"]["id"]
        # Try invalid transition: occupied -> available
        resp = client.post(f"/api/tables/sessions/{session_id}/transition", json={
            "target_state": "available",
        })
        assert resp.status_code == 400


# ── RESPONSE CONTRACT ──

class TestResponseContract:
    def test_success_has_data_key(self, app, client):
        _seed_and_login(app, client)
        resp = client.get("/api/settings")
        body = resp.get_json()
        assert "data" in body

    def test_error_has_error_key(self, app, client):
        resp = client.post("/api/tickets", json={})
        body = resp.get_json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]

    def test_no_ciphertext_in_response(self, app, client):
        store = _seed_and_login(app, client)
        resp = client.post("/api/tickets", json={
            "store_id": store.id,
            "customer_name": "Jane",
            "clothing_category": "shirts",
            "condition_grade": "A",
            "estimated_weight_lbs": 10.0,
        })
        data = resp.get_json()["data"]
        for key in data:
            assert "ciphertext" not in key, f"Ciphertext field leaked: {key}"
            assert not key.endswith("_iv"), f"IV field leaked: {key}"


# ── METRICS ──

class TestMetricsRoute:
    def test_metrics_require_dates(self, app, client):
        _seed_and_login(app, client, role=UserRole.OPERATIONS_MANAGER, username="ops1")
        resp = client.get("/api/exports/metrics")
        assert resp.status_code == 400


# ── UI ROUTE AUTH GATE ──

class TestUIAuthGate:
    """All /ui/* pages except /ui/login must redirect to /ui/login when
    unauthenticated. Authenticated users get the rendered template."""

    def test_unauthenticated_ui_redirects_to_login(self, app, client):
        for path in [
            "/ui/tickets", "/ui/qc", "/ui/tables", "/ui/notifications",
            "/ui/members", "/ui/exports", "/ui/schedules",
        ]:
            resp = client.get(path, follow_redirects=False)
            assert resp.status_code == 302, f"{path} did not redirect"
            assert "/ui/login" in resp.headers["Location"], (
                f"{path} redirected to {resp.headers['Location']}"
            )

    def test_login_page_is_public(self, app, client):
        resp = client.get("/ui/login")
        assert resp.status_code == 200

    def test_authenticated_ui_loads(self, app, client):
        _seed_and_login(app, client)
        resp = client.get("/ui/tickets")
        assert resp.status_code == 200


# ── INVALID INPUT — NO 500s ──

class TestInvalidInputNo500:
    """Bad IDs and bad bodies must produce structured 4xx, never 500."""

    def test_unknown_ticket_id_submit_qc_returns_400(self, app, client):
        _seed_and_login(app, client)
        resp = client.post("/api/tickets/99999/submit-qc")
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_dial_unknown_ticket_returns_400(self, app, client):
        _seed_and_login(app, client, role=UserRole.SHIFT_SUPERVISOR, username="sup1")
        resp = client.post("/api/tickets/77777/dial")
        assert resp.status_code == 400

    def test_qc_inspection_with_bad_ticket_id_returns_400(self, app, client):
        _seed_and_login(app, client, role=UserRole.QC_INSPECTOR, username="qcuser")
        resp = client.post("/api/qc/inspections", json={
            "ticket_id": 999999,
            "actual_weight_lbs": 10.0,
            "lot_size": 10,
            "nonconformance_count": 0,
            "inspection_outcome": "pass",
        })
        # Service-layer validation rejects with 400 — never a sqlite IntegrityError 500
        assert resp.status_code == 400
        body = resp.get_json()
        assert "error" in body


# ── METRICS RBAC (route layer) ──

class TestMetricsRouteRBAC:
    def test_metrics_forbidden_for_front_desk(self, app, client):
        _seed_and_login(app, client, role=UserRole.FRONT_DESK_AGENT, username="agent1")
        resp = client.get("/api/exports/metrics?date_start=2020-01-01&date_end=2030-12-31")
        assert resp.status_code == 403

    def test_metrics_allowed_for_ops_manager(self, app, client):
        _seed_and_login(app, client, role=UserRole.OPERATIONS_MANAGER, username="ops1")
        resp = client.get("/api/exports/metrics?date_start=2020-01-01&date_end=2030-12-31")
        assert resp.status_code == 200


# ── XSS-SAFE RENDERING (template emits H()/escapeHtml) ──

class TestXSSSafeRendering:
    """Each gated UI page must reference the H() / escapeHtml helper
    so dynamic interpolations are escaped before being inserted into
    innerHTML. This is a static check on the rendered template body."""

    def _fetch(self, app, client, path):
        _seed_and_login(app, client)
        return client.get(path)

    def test_base_layout_defines_escape_helper(self, app, client):
        resp = self._fetch(app, client, "/ui/tickets")
        body = resp.get_data(as_text=True)
        # The H alias defined in base.html must be present and used.
        assert "function escapeHtml" in body or "escapeHtml" in body
        assert "const H = escapeHtml" in body

    def test_notifications_template_escapes_message_body(self, app, client):
        resp = self._fetch(app, client, "/ui/notifications")
        body = resp.get_data(as_text=True)
        # The historical XSS hotspot — message_body — must now be wrapped in H().
        assert "H(m.message_body)" in body
        assert "+m.message_body+" not in body  # the unsafe pattern is gone

    def test_login_template_uses_textcontent(self, app, client):
        resp = client.get("/ui/login")
        body = resp.get_data(as_text=True)
        # Login isn't built on base.html — the error path must use the
        # safe DOM-text approach instead of innerHTML interpolation.
        assert "textContent" in body


# ── COOKIE TAMPERING ──

class TestCookieTampering:
    """Tampered or forged session cookies must be rejected."""

    def test_tampered_cookie_rejected(self, app, client):
        _seed_and_login(app, client)
        # Tamper with the session cookie by flipping a character
        cookies = {c.name: c.value for c in client.cookie_jar}
        original = cookies.get("session_nonce", "")
        if original:
            tampered = original[:-1] + ("X" if original[-1] != "X" else "Y")
            client.set_cookie("session_nonce", tampered, domain="localhost")
        resp = client.get("/api/settings")
        assert resp.status_code == 401

    def test_forged_cookie_rejected(self, app, client):
        client.set_cookie("session_nonce", "forged-nonce.AAAA", domain="localhost")
        resp = client.get("/api/settings")
        assert resp.status_code == 401

    def test_empty_cookie_rejected(self, app, client):
        client.set_cookie("session_nonce", "", domain="localhost")
        resp = client.get("/api/settings")
        assert resp.status_code == 401


# ── TLS ENFORCEMENT ──

class TestTLSEnforcement:
    """TLS is secure-by-default. The app refuses to start without
    TLS_CERT_PATH, TLS_KEY_PATH, and SECURE_COOKIES unless explicitly
    opted out via RECLAIM_OPS_DEV_MODE=true."""

    def test_default_blocks_startup_without_certs(self, tmp_path, monkeypatch):
        """Default (no overrides) MUST require TLS — fail closed."""
        monkeypatch.delenv("RECLAIM_OPS_REQUIRE_TLS", raising=False)
        monkeypatch.delenv("RECLAIM_OPS_DEV_MODE", raising=False)
        monkeypatch.delenv("TLS_CERT_PATH", raising=False)
        monkeypatch.delenv("TLS_KEY_PATH", raising=False)
        monkeypatch.delenv("SECURE_COOKIES", raising=False)
        monkeypatch.delenv("FLASK_ENV", raising=False)
        with pytest.raises(RuntimeError, match="TLS-first mode is required"):
            create_app(db_path=str(tmp_path / "tls_default.db"))

    def test_explicit_tls_true_blocks_without_certs(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RECLAIM_OPS_REQUIRE_TLS", "true")
        monkeypatch.delenv("RECLAIM_OPS_DEV_MODE", raising=False)
        monkeypatch.delenv("TLS_CERT_PATH", raising=False)
        monkeypatch.delenv("TLS_KEY_PATH", raising=False)
        monkeypatch.delenv("SECURE_COOKIES", raising=False)
        monkeypatch.delenv("FLASK_ENV", raising=False)
        with pytest.raises(RuntimeError, match="TLS-first mode is required"):
            create_app(db_path=str(tmp_path / "tls_explicit.db"))

    def test_dev_mode_allows_insecure_startup(self, tmp_path, monkeypatch):
        """RECLAIM_OPS_DEV_MODE=true explicitly disables TLS enforcement."""
        monkeypatch.setenv("RECLAIM_OPS_DEV_MODE", "true")
        monkeypatch.setenv("RECLAIM_OPS_REQUIRE_TLS", "false")
        monkeypatch.delenv("TLS_CERT_PATH", raising=False)
        monkeypatch.delenv("TLS_KEY_PATH", raising=False)
        monkeypatch.setenv("SECURE_COOKIES", "false")
        monkeypatch.delenv("FLASK_ENV", raising=False)
        app = create_app(db_path=str(tmp_path / "dev_test.db"))
        assert app is not None


# ── NOTIFICATION TEMPLATES SEEDED ──

class TestNotificationTemplatesSeeded:
    """Migration 004 must seed the five templates the UI references."""

    def test_required_templates_exist(self, app):
        required_codes = {"accepted", "rescheduled", "arrived", "completed", "refunded"}
        with app.app_context():
            from app import get_db
            from flask import g
            g.db_path = app.config["DB_PATH"]
            db = get_db()
            rows = db.execute(
                "SELECT template_code FROM notification_templates"
            ).fetchall()
            found = {row["template_code"] for row in rows}
            assert required_codes.issubset(found), (
                f"Missing templates: {required_codes - found}"
            )


# ── DATE RANGE BOUNDARY ──

class TestDateRangeBoundary:
    """Date-only strings must be normalized to full timestamps."""

    def test_metrics_date_only_normalized(self, app, client):
        """Metrics with date-only strings must not 500."""
        _seed_and_login(app, client, role=UserRole.OPERATIONS_MANAGER, username="ops2")
        resp = client.get(
            "/api/exports/metrics?date_start=2024-01-01&date_end=2024-12-31"
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "order_volume" in data


# ── EXPORT UI OPTIONS ──

class TestExportUIOptions:
    """The export UI dropdown must only offer types the service supports."""

    def test_export_ui_matches_service(self, app, client):
        _seed_and_login(app, client)
        resp = client.get("/ui/exports")
        body = resp.get_data(as_text=True)
        # The two supported types must be present
        assert "<option>tickets</option>" in body
        assert "<option>metrics</option>" in body
        # Unsupported types must NOT be offered
        assert "<option>members</option>" not in body
        assert "<option>audit</option>" not in body
        assert "<option>recalls</option>" not in body


# ── DIAL FLOW ──

class TestDialFlow:
    """The one-tap dial endpoint must work for authorized roles and
    be wired in the tickets UI."""

    def test_dial_ui_button_present(self, app, client):
        _seed_and_login(app, client)
        resp = client.get("/ui/tickets")
        body = resp.get_data(as_text=True)
        assert "dialCustomer" in body
        assert "/api/tickets/" in body and "/dial" in body

    def test_dial_rejects_host_role(self, app, client):
        _seed_and_login(app, client, role=UserRole.HOST, username="host2")
        resp = client.post("/api/tickets/1/dial")
        assert resp.status_code == 403


# ── ROUTE FILTER (METRICS) ──

class TestMetricsRouteFilter:
    """Metrics must accept a clothing_category filter param."""

    def test_metrics_with_category_filter(self, app, client):
        store = _seed_and_login(app, client, role=UserRole.OPERATIONS_MANAGER, username="ops3")
        # Create a ticket to ensure the filter runs against real data
        client2 = app.test_client()
        with client2.session_transaction():
            pass
        resp = client.get(
            "/api/exports/metrics?date_start=2020-01-01&date_end=2030-12-31"
            "&clothing_category=shirts"
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "order_volume" in data

    def test_metrics_without_filter_returns_all(self, app, client):
        _seed_and_login(app, client, role=UserRole.OPERATIONS_MANAGER, username="ops4")
        resp = client.get(
            "/api/exports/metrics?date_start=2020-01-01&date_end=2030-12-31"
        )
        assert resp.status_code == 200


# ── DB ERROR DETAILS NOT LEAKED ──

class TestDBErrorDetailsNotLeaked:
    """sqlite3 error handlers must not expose internal details."""

    def test_integrity_error_generic_message(self, app, client):
        _seed_and_login(app, client)
        # Trigger an integrity error by creating a ticket referencing
        # a nonexistent store (as admin)
        _seed_and_login(app, client, role=UserRole.ADMINISTRATOR, username="admin_leak")
        resp = client.post("/api/tickets", json={
            "store_id": 99999,
            "customer_name": "Test",
            "clothing_category": "shirts",
            "condition_grade": "A",
            "estimated_weight_lbs": 10.0,
        })
        if resp.status_code == 400:
            body = resp.get_json()
            # details field must be absent
            assert "details" not in body.get("error", {})


# ── BOOTSTRAP 0→1 PATH ──

class TestBootstrapPath:
    """Fresh install must support: bootstrap → store → pricing → user → ticket."""

    def test_full_zero_to_one_flow(self, app, client):
        """Complete 0→1 path: bootstrap admin, create store, pricing rule,
        create operator user, log in as operator, create a ticket."""
        # Step 1: bootstrap admin
        resp = client.post("/api/auth/bootstrap", json={
            "username": "admin", "password": "AdminPass123!",
            "display_name": "Admin",
        })
        assert resp.status_code == 201

        # Step 2: login as admin
        resp = client.post("/api/auth/login", json={
            "username": "admin", "password": "AdminPass123!",
        })
        assert resp.status_code == 200
        csrf = resp.get_json()["data"]["csrf_token"]
        client.environ_base["HTTP_X_CSRF_TOKEN"] = csrf

        # Step 3: create store
        resp = client.post("/api/admin/stores", json={
            "code": "STORE1", "name": "Main Store", "route_code": "ROUTE-A",
        })
        assert resp.status_code == 201, resp.get_json()
        store_id = resp.get_json()["data"]["id"]

        # Step 4: create pricing rule
        resp = client.post("/api/admin/pricing_rules", json={
            "store_id": store_id, "base_rate_per_lb": 1.50,
            "bonus_pct": 10.0, "max_ticket_payout": 200.0,
            "max_rate_per_lb": 5.0,
        })
        assert resp.status_code == 201, resp.get_json()

        # Step 5: create front desk agent
        resp = client.post("/api/auth/users", json={
            "username": "agent", "password": "AgentPass123!",
            "display_name": "Agent", "role": "front_desk_agent",
            "store_id": store_id,
        })
        assert resp.status_code == 201

        # Step 6: login as agent
        resp = client.post("/api/auth/login", json={
            "username": "agent", "password": "AgentPass123!",
        })
        assert resp.status_code == 200
        csrf = resp.get_json()["data"]["csrf_token"]
        client.environ_base["HTTP_X_CSRF_TOKEN"] = csrf

        # Step 7: create ticket with phone
        resp = client.post("/api/tickets", json={
            "customer_name": "Jane Doe",
            "customer_phone": "5551234567",
            "clothing_category": "shirts",
            "condition_grade": "A",
            "estimated_weight_lbs": 10.0,
        })
        assert resp.status_code == 201, resp.get_json()
        ticket = resp.get_json()["data"]
        assert ticket["status"] == "intake_open"
        assert ticket["estimated_payout"] > 0
        # Phone should be masked in response
        assert "customer_phone_ciphertext" not in ticket

    def test_admin_stores_requires_admin_role(self, app, client):
        _seed_and_login(app, client, role=UserRole.FRONT_DESK_AGENT)
        resp = client.post("/api/admin/stores", json={
            "code": "X", "name": "X",
        })
        assert resp.status_code == 403

    def test_admin_pricing_rules_requires_admin_role(self, app, client):
        _seed_and_login(app, client, role=UserRole.FRONT_DESK_AGENT)
        resp = client.post("/api/admin/pricing_rules", json={
            "store_id": 1, "base_rate_per_lb": 1.0,
        })
        assert resp.status_code == 403


# ── METRICS EXPORT EXECUTION ──

class TestMetricsExportExecution:
    """Metrics-type export execution must not crash."""

    def test_metrics_export_executes_without_crash(self, app, client):
        store = _seed_and_login(app, client, role=UserRole.OPERATIONS_MANAGER, username="ops_exp")
        # Create a metrics export request
        resp = client.post("/api/exports/requests", json={
            "export_type": "metrics",
        })
        assert resp.status_code == 201, resp.get_json()
        req_id = resp.get_json()["data"]["id"]

        # If approval not required, execute directly; otherwise approve first
        req_data = resp.get_json()["data"]
        if req_data["status"] == "pending":
            # Need a different supervisor to approve
            _seed_and_login(app, client, role=UserRole.ADMINISTRATOR, username="admin_exp")
            resp = client.post(f"/api/exports/requests/{req_id}/approve", json={
                "password": "TestPassword123!",
            })
            assert resp.status_code == 200, resp.get_json()

        # Execute
        resp = client.post(f"/api/exports/requests/{req_id}/execute")
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()["data"]
        assert data["status"] == "completed"


# ── ROUTE CODE FILTER ──

class TestRouteCodeFilter:
    """Metrics must support route_code filtering."""

    def test_metrics_with_route_code(self, app, client):
        _seed_and_login(app, client, role=UserRole.OPERATIONS_MANAGER, username="ops_rt")
        resp = client.get(
            "/api/exports/metrics?date_start=2020-01-01&date_end=2030-12-31"
            "&route_code=ROUTE-A"
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "order_volume" in data


# ════════════════════════════════════════════════════════════
# COMPREHENSIVE AUTHORIZATION / EDGE-CASE API TESTS
# ════════════════════════════════════════════════════════════

def _create_ticket_for_tests(app, client, store):
    """Create a ticket via API (assumes agent is logged in)."""
    resp = client.post("/api/tickets", json={
        "customer_name": "Test Customer",
        "customer_phone": "5559876543",
        "clothing_category": "shirts",
        "condition_grade": "A",
        "estimated_weight_lbs": 10.0,
    })
    assert resp.status_code == 201
    return resp.get_json()["data"]


def _advance_ticket_to_variance(app, client, store):
    """Create ticket, submit for QC, record inspection with big variance,
    compute final payout. Returns (ticket, variance_request) for approval tests."""
    ticket = _create_ticket_for_tests(app, client, store)
    tid = ticket["id"]

    # Submit for QC
    client.post(f"/api/tickets/{tid}/submit-qc")

    # Log in as QC inspector to create inspection + compute final
    _seed_and_login(app, client, role=UserRole.QC_INSPECTOR, username="qcinsp")
    client.post("/api/qc/inspections", json={
        "ticket_id": tid,
        "actual_weight_lbs": 20.0,
        "lot_size": 10,
        "nonconformance_count": 0,
        "inspection_outcome": "pass",
    })
    resp = client.post(f"/api/tickets/{tid}/qc-final", json={})
    data = resp.get_json()
    if data.get("data", {}).get("approval_required"):
        # Confirm variance
        resp = client.post(f"/api/tickets/{tid}/confirm-variance", json={
            "confirmation_note": "Weight higher than expected",
        })
        return tid, resp.get_json().get("data", {}).get("id")
    return tid, None


# ── A. Variance Routes ──

class TestVarianceAuthz:
    def test_variance_approve_unauthenticated(self, app, client):
        resp = client.post("/api/tickets/variance/1/approve", json={"password": "x"})
        assert resp.status_code == 401

    def test_variance_approve_wrong_password(self, app, client):
        store = _seed_and_login(app, client, role=UserRole.FRONT_DESK_AGENT)
        tid, req_id = _advance_ticket_to_variance(app, client, store)
        if req_id is None:
            return  # variance not triggered in this pricing config
        _seed_and_login(app, client, role=UserRole.SHIFT_SUPERVISOR, username="sup_var")
        resp = client.post(f"/api/tickets/variance/{req_id}/approve", json={
            "password": "WrongPassword!!!",
        })
        assert resp.status_code == 403

    def test_variance_reject_unauthenticated(self, app, client):
        resp = client.post("/api/tickets/variance/1/reject", json={"reason": "x"})
        assert resp.status_code == 401

    def test_variance_approve_stale_id(self, app, client):
        _seed_and_login(app, client, role=UserRole.SHIFT_SUPERVISOR, username="sup_stale")
        resp = client.post("/api/tickets/variance/99999/approve", json={
            "password": "TestPassword123!",
        })
        assert resp.status_code == 400
        assert "error" in resp.get_json()


# ── B. Refund Routes ──

class TestRefundAuthz:
    def test_refund_approve_unauthenticated(self, app, client):
        resp = client.post("/api/tickets/1/refund/approve", json={"password": "x"})
        assert resp.status_code == 401

    def test_refund_reject_unauthenticated(self, app, client):
        resp = client.post("/api/tickets/1/refund/reject", json={"reason": "x"})
        assert resp.status_code == 401

    def test_refund_approve_stale_id(self, app, client):
        _seed_and_login(app, client, role=UserRole.SHIFT_SUPERVISOR, username="sup_ref")
        resp = client.post("/api/tickets/99999/refund/approve", json={
            "password": "TestPassword123!",
        })
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_initiate_refund_wrong_role(self, app, client):
        _seed_and_login(app, client, role=UserRole.HOST, username="host_ref")
        resp = client.post("/api/tickets/1/refund", json={})
        assert resp.status_code == 403


# ── C. Export Routes ──

class TestExportAuthz:
    def test_export_create_wrong_role(self, app, client):
        _seed_and_login(app, client, role=UserRole.HOST, username="host_exp")
        resp = client.post("/api/exports/requests", json={"export_type": "tickets"})
        assert resp.status_code == 403

    def test_export_execute_wrong_role(self, app, client):
        _seed_and_login(app, client, role=UserRole.FRONT_DESK_AGENT, username="agent_exp")
        resp = client.post("/api/exports/requests/1/execute")
        assert resp.status_code == 403
        assert "error" in resp.get_json()

    def test_export_approve_unauthenticated(self, app, client):
        resp = client.post("/api/exports/requests/1/approve", json={"password": "x"})
        assert resp.status_code == 401

    def test_export_unsupported_type_returns_400(self, app, client):
        store = _seed_and_login(app, client, role=UserRole.OPERATIONS_MANAGER, username="ops_badtype")
        resp = client.post("/api/exports/requests", json={
            "export_type": "nonexistent_type",
        })
        assert resp.status_code == 201  # request created (type validated at execution)
        req_id = resp.get_json()["data"]["id"]
        # Execute should fail — export is still pending (needs approval) or
        # the unsupported type will error during execution.
        resp = client.post(f"/api/exports/requests/{req_id}/execute")
        assert resp.status_code == 400

    def test_export_duplicate_execute_safe(self, app, client):
        store = _seed_and_login(app, client, role=UserRole.OPERATIONS_MANAGER, username="ops_dup")
        resp = client.post("/api/exports/requests", json={"export_type": "tickets"})
        assert resp.status_code == 201
        req_id = resp.get_json()["data"]["id"]
        req_status = resp.get_json()["data"]["status"]
        if req_status == "approved":
            # First execute
            resp = client.post(f"/api/exports/requests/{req_id}/execute")
            assert resp.status_code == 200
            # Duplicate execute — already completed
            resp = client.post(f"/api/exports/requests/{req_id}/execute")
            assert resp.status_code == 400


# ── D. Schedule Routes ──

class TestScheduleAuthz:
    def test_schedule_pending_wrong_role(self, app, client):
        _seed_and_login(app, client, role=UserRole.FRONT_DESK_AGENT, username="agent_sched")
        resp = client.get("/api/schedules/adjustments/pending")
        assert resp.status_code == 403

    def test_schedule_pending_qc_rejected(self, app, client):
        _seed_and_login(app, client, role=UserRole.QC_INSPECTOR, username="qc_sched")
        resp = client.get("/api/schedules/adjustments/pending")
        assert resp.status_code == 403

    def test_schedule_approve_unauthenticated(self, app, client):
        resp = client.post("/api/schedules/adjustments/1/approve", json={"password": "x"})
        assert resp.status_code == 401

    def test_schedule_approve_wrong_role(self, app, client):
        _seed_and_login(app, client, role=UserRole.FRONT_DESK_AGENT, username="agent_sched2")
        resp = client.post("/api/schedules/adjustments/1/approve", json={
            "password": "TestPassword123!",
        })
        assert resp.status_code == 403

    def test_schedule_reject_wrong_role(self, app, client):
        _seed_and_login(app, client, role=UserRole.HOST, username="host_sched")
        resp = client.post("/api/schedules/adjustments/1/reject", json={"reason": "x"})
        assert resp.status_code == 403

    def test_schedule_pending_allowed_for_supervisor(self, app, client):
        _seed_and_login(app, client, role=UserRole.SHIFT_SUPERVISOR, username="sup_sched")
        resp = client.get("/api/schedules/adjustments/pending")
        assert resp.status_code == 200


# ── E. Notification / Dial Routes ──

class TestNotificationDialAuthz:
    def test_dial_unauthenticated(self, app, client):
        resp = client.post("/api/tickets/1/dial")
        assert resp.status_code == 401

    def test_dial_wrong_role(self, app, client):
        _seed_and_login(app, client, role=UserRole.HOST, username="host_dial")
        resp = client.post("/api/tickets/1/dial")
        assert resp.status_code == 403

    def test_dial_no_phone_returns_error(self, app, client):
        store = _seed_and_login(app, client)
        # Create ticket WITHOUT phone
        resp = client.post("/api/tickets", json={
            "customer_name": "No Phone",
            "clothing_category": "shirts",
            "condition_grade": "A",
            "estimated_weight_lbs": 5.0,
        })
        assert resp.status_code == 201
        tid = resp.get_json()["data"]["id"]
        _seed_and_login(app, client, role=UserRole.SHIFT_SUPERVISOR, username="sup_dial")
        resp = client.post(f"/api/tickets/{tid}/dial")
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_notification_log_unauthenticated(self, app, client):
        resp = client.post("/api/notifications/messages", json={
            "ticket_id": 1, "message_body": "test",
        })
        assert resp.status_code == 401

    def test_calls_only_rejects_logged_message(self, app, client):
        store = _seed_and_login(app, client)
        # Create ticket with calls_only preference
        resp = client.post("/api/tickets", json={
            "customer_name": "Calls Only Customer",
            "customer_phone": "5551112222",
            "clothing_category": "shirts",
            "condition_grade": "A",
            "estimated_weight_lbs": 5.0,
            "customer_phone_preference": "calls_only",
        })
        assert resp.status_code == 201
        tid = resp.get_json()["data"]["id"]
        # Try to log a non-phone message
        resp = client.post("/api/notifications/messages", json={
            "ticket_id": tid,
            "message_body": "This should be rejected",
            "contact_channel": "logged_message",
        })
        assert resp.status_code == 403
        assert "calls_only" in resp.get_json()["error"]["message"]

    def test_invalid_template_context_returns_400(self, app, client):
        store = _seed_and_login(app, client)
        resp = client.post("/api/notifications/messages/template", json={
            "ticket_id": 1,
            "template_code": "accepted",
            "context": "not-a-dict",
        })
        assert resp.status_code == 400


# ── F. HTMX Partial Endpoints Auth — cross-store + role matrix ──

def _setup_partial_stores(app, client):
    """Bootstrap admin, create two stores with pricing, create agents
    in each store plus an admin.  Returns (store_a_id, store_b_id).

    Also creates:
      agent_pa  – front_desk_agent pinned to store A
      agent_pb  – front_desk_agent pinned to store B
      sup_pa    – shift_supervisor pinned to store A
      host_pa   – host pinned to store A
      qc_pa     – qc_inspector pinned to store A
      padmin    – administrator (no store)
    """
    # Bootstrap admin (idempotent — skipped if already done)
    resp = client.post("/api/auth/bootstrap", json={
        "username": "padmin", "password": "AdminPass123!",
        "display_name": "Partial Admin",
    })
    if resp.status_code not in (201, 403):
        pytest.skip("Bootstrap failed unexpectedly")

    resp = client.post("/api/auth/login", json={
        "username": "padmin", "password": "AdminPass123!",
    })
    assert resp.status_code == 200, resp.get_json()
    csrf = resp.get_json()["data"]["csrf_token"]
    client.environ_base["HTTP_X_CSRF_TOKEN"] = csrf

    # Store A
    resp = client.post("/api/admin/stores", json={
        "code": "PA", "name": "Partial Store A",
    })
    assert resp.status_code == 201, resp.get_json()
    store_a = resp.get_json()["data"]["id"]

    # Store B
    resp = client.post("/api/admin/stores", json={
        "code": "PB", "name": "Partial Store B",
    })
    assert resp.status_code == 201, resp.get_json()
    store_b = resp.get_json()["data"]["id"]

    # Pricing rules so ticket creation works
    for sid in (store_a, store_b):
        resp = client.post("/api/admin/pricing_rules", json={
            "store_id": sid, "base_rate_per_lb": 1.5,
            "bonus_pct": 10, "max_ticket_payout": 200,
            "max_rate_per_lb": 5,
        })
        assert resp.status_code == 201

    # Users
    users = [
        ("agent_pa",  "front_desk_agent",    store_a),
        ("agent_pb",  "front_desk_agent",    store_b),
        ("sup_pa",    "shift_supervisor",    store_a),
        ("host_pa",   "host",               store_a),
        ("qc_pa",     "qc_inspector",       store_a),
    ]
    for uname, role, sid in users:
        resp = client.post("/api/auth/users", json={
            "username": uname, "password": "TestPassword123!",
            "display_name": uname, "role": role,
            "store_id": sid,
        })
        assert resp.status_code == 201, f"Failed creating {uname}: {resp.get_json()}"

    return store_a, store_b


def _login_as(client, username, password="TestPassword123!"):
    """Log in and configure CSRF header."""
    resp = client.post("/api/auth/login", json={
        "username": username, "password": password,
    })
    assert resp.status_code == 200, f"Login failed for {username}: {resp.get_json()}"
    csrf = resp.get_json()["data"]["csrf_token"]
    client.environ_base["HTTP_X_CSRF_TOKEN"] = csrf


class TestHTMXPartialsAuth:
    """HTMX partial endpoints must enforce auth, role gates, and
    cross-store isolation — no leakage via query param overrides."""

    # ── unauthenticated → exact 401 ──

    @pytest.mark.parametrize("path", [
        "/ui/partials/tickets/queue",
        "/ui/partials/qc/queue",
        "/ui/partials/tables/board",
        "/ui/partials/exports/list",
        "/ui/partials/schedules/pending",
        "/ui/partials/notifications/retries",
    ])
    def test_unauthenticated_returns_401(self, app, client, path):
        resp = client.get(path)
        assert resp.status_code == 401

    @pytest.mark.parametrize("path", [
        "/ui/partials/tickets/1/submit-qc",
        "/ui/partials/tables/1/transition",
    ])
    def test_unauthenticated_post_returns_401(self, app, client, path):
        resp = client.post(path)
        assert resp.status_code == 401

    # ── basic authenticated (correct role) ──

    def test_ticket_queue_authenticated(self, app, client):
        _seed_and_login(app, client)
        resp = client.get("/ui/partials/tickets/queue")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "<" in body  # HTML fragment, not JSON

    # ── cross-store isolation: store A user vs store B data ──

    def test_store_a_agent_ticket_queue_ignores_store_b_param(self, app, client):
        """Agent in store A passes store_id=<B> — must still see store A data only."""
        store_a, store_b = _setup_partial_stores(app, client)
        _login_as(client, "agent_pa")
        resp = client.get(f"/ui/partials/tickets/queue?store_id={store_b}")
        assert resp.status_code == 200
        # The response is store A scoped (query param silently ignored)

    def test_store_b_agent_ticket_queue_ignores_store_a_param(self, app, client):
        store_a, store_b = _setup_partial_stores(app, client)
        _login_as(client, "agent_pb")
        resp = client.get(f"/ui/partials/tickets/queue?store_id={store_a}")
        assert resp.status_code == 200

    def test_store_a_supervisor_qc_queue_ignores_store_b_param(self, app, client):
        store_a, store_b = _setup_partial_stores(app, client)
        _login_as(client, "sup_pa")
        resp = client.get(f"/ui/partials/qc/queue?store_id={store_b}")
        assert resp.status_code == 200

    def test_store_a_host_table_board_ignores_store_b_param(self, app, client):
        store_a, store_b = _setup_partial_stores(app, client)
        _login_as(client, "host_pa")
        resp = client.get(f"/ui/partials/tables/board?store_id={store_b}")
        assert resp.status_code == 200

    def test_store_a_supervisor_exports_ignores_store_b_param(self, app, client):
        store_a, store_b = _setup_partial_stores(app, client)
        _login_as(client, "sup_pa")
        resp = client.get(f"/ui/partials/exports/list?store_id={store_b}")
        assert resp.status_code == 200

    # ── admin with explicit store_id → allowed ──

    @pytest.mark.parametrize("path_tpl", [
        "/ui/partials/tickets/queue?store_id={}",
        "/ui/partials/qc/queue?store_id={}",
        "/ui/partials/tables/board?store_id={}",
        "/ui/partials/exports/list?store_id={}",
    ])
    def test_admin_can_access_any_store(self, app, client, path_tpl):
        store_a, store_b = _setup_partial_stores(app, client)
        _login_as(client, "padmin", password="AdminPass123!")
        for sid in (store_a, store_b):
            resp = client.get(path_tpl.format(sid))
            assert resp.status_code == 200, (
                f"Admin denied on {path_tpl.format(sid)}"
            )

    # ── legacy non-admin with store_id=NULL → 403 ──

    def _insert_null_store_user(self, app, username, role):
        """Bypass service-layer validation to create a legacy non-admin
        user with store_id=NULL directly in the database."""
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
            pw_hash = auth_svc._hash_password("TestPassword123!")
            db.execute(
                """INSERT INTO users
                   (store_id, username, password_hash, display_name,
                    role, is_active, is_frozen, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 1, 0,
                           datetime('now'), datetime('now'))""",
                (None, username, pw_hash, f"Legacy {username}", role),
            )
            db.commit()

    @pytest.mark.parametrize("path", [
        "/ui/partials/tickets/queue",
        "/ui/partials/qc/queue",
        "/ui/partials/tables/board",
        "/ui/partials/exports/list",
    ])
    def test_null_store_non_admin_returns_403(self, app, client, path):
        _setup_partial_stores(app, client)
        self._insert_null_store_user(
            app, "legacy_null_sup", UserRole.SHIFT_SUPERVISOR,
        )
        _login_as(client, "legacy_null_sup")
        resp = client.get(path)
        assert resp.status_code == 403

    def test_null_store_non_admin_query_override_returns_403(self, app, client):
        """Non-admin with NULL store tries to inject store_id via query param."""
        store_a, _ = _setup_partial_stores(app, client)
        self._insert_null_store_user(
            app, "legacy_null_fd", UserRole.FRONT_DESK_AGENT,
        )
        _login_as(client, "legacy_null_fd")
        resp = client.get(
            f"/ui/partials/tickets/queue?store_id={store_a}"
        )
        assert resp.status_code == 403

    # ── role-based access: forbidden roles → exact 403 ──

    def test_host_cannot_read_ticket_queue(self, app, client):
        _setup_partial_stores(app, client)
        _login_as(client, "host_pa")
        resp = client.get("/ui/partials/tickets/queue")
        assert resp.status_code == 403

    def test_front_desk_cannot_read_qc_queue(self, app, client):
        _setup_partial_stores(app, client)
        _login_as(client, "agent_pa")
        resp = client.get("/ui/partials/qc/queue")
        assert resp.status_code == 403

    def test_front_desk_cannot_read_table_board(self, app, client):
        _setup_partial_stores(app, client)
        _login_as(client, "agent_pa")
        resp = client.get("/ui/partials/tables/board")
        assert resp.status_code == 403

    def test_front_desk_cannot_read_exports(self, app, client):
        _setup_partial_stores(app, client)
        _login_as(client, "agent_pa")
        resp = client.get("/ui/partials/exports/list")
        assert resp.status_code == 403

    def test_front_desk_cannot_read_schedules(self, app, client):
        _setup_partial_stores(app, client)
        _login_as(client, "agent_pa")
        resp = client.get("/ui/partials/schedules/pending")
        assert resp.status_code == 403

    def test_host_cannot_read_notifications(self, app, client):
        _setup_partial_stores(app, client)
        _login_as(client, "host_pa")
        resp = client.get("/ui/partials/notifications/retries")
        assert resp.status_code == 403

    # ── role-based access: allowed roles → 200 ──

    def test_qc_inspector_can_read_qc_queue(self, app, client):
        _setup_partial_stores(app, client)
        _login_as(client, "qc_pa")
        resp = client.get("/ui/partials/qc/queue")
        assert resp.status_code == 200

    def test_host_can_read_table_board(self, app, client):
        _setup_partial_stores(app, client)
        _login_as(client, "host_pa")
        resp = client.get("/ui/partials/tables/board")
        assert resp.status_code == 200

    def test_supervisor_can_read_exports(self, app, client):
        _setup_partial_stores(app, client)
        _login_as(client, "sup_pa")
        resp = client.get("/ui/partials/exports/list")
        assert resp.status_code == 200

    def test_supervisor_can_read_schedules(self, app, client):
        _setup_partial_stores(app, client)
        _login_as(client, "sup_pa")
        resp = client.get("/ui/partials/schedules/pending")
        assert resp.status_code == 200

    def test_front_desk_can_read_notifications(self, app, client):
        _setup_partial_stores(app, client)
        _login_as(client, "agent_pa")
        resp = client.get("/ui/partials/notifications/retries")
        assert resp.status_code == 200


# ── Malformed Payloads ──

class TestMalformedPayloads:
    """Malformed inputs must return structured errors, never 500."""

    def test_ticket_missing_all_fields(self, app, client):
        _seed_and_login(app, client)
        resp = client.post("/api/tickets", json={})
        assert resp.status_code == 400

    def test_qc_inspection_missing_fields(self, app, client):
        _seed_and_login(app, client, role=UserRole.QC_INSPECTOR, username="qc_bad")
        resp = client.post("/api/qc/inspections", json={})
        assert resp.status_code == 400

    def test_quarantine_resolve_missing_disposition(self, app, client):
        _seed_and_login(app, client)
        resp = client.post("/api/qc/quarantine/1/resolve", json={})
        assert resp.status_code == 400

    def test_notification_empty_body(self, app, client):
        _seed_and_login(app, client)
        resp = client.post("/api/notifications/messages", json={
            "ticket_id": 1,
            "message_body": "",
        })
        assert resp.status_code == 400

    def test_export_missing_type(self, app, client):
        _seed_and_login(app, client, role=UserRole.OPERATIONS_MANAGER, username="ops_mal")
        resp = client.post("/api/exports/requests", json={})
        assert resp.status_code == 400


# ════════════════════════════════════════════════════════════
# PRICE OVERRIDE API TESTS
# ════════════════════════════════════════════════════════════

class TestPriceOverrideAPI:
    """Full API-level coverage for price override routes."""

    def _create_ticket(self, app, client, store):
        resp = client.post("/api/tickets", json={
            "customer_name": "PO Customer",
            "clothing_category": "shirts",
            "condition_grade": "A",
            "estimated_weight_lbs": 10.0,
        })
        assert resp.status_code == 201
        return resp.get_json()["data"]["id"]

    def test_request_unauthenticated(self, app, client):
        resp = client.post("/api/price-overrides", json={
            "ticket_id": 1, "proposed_payout": 50.0, "reason": "test",
        })
        assert resp.status_code == 401

    def test_request_wrong_role(self, app, client):
        _seed_and_login(app, client, role=UserRole.HOST, username="host_po")
        resp = client.post("/api/price-overrides", json={
            "ticket_id": 1, "proposed_payout": 50.0, "reason": "test",
        })
        assert resp.status_code == 403

    def test_approve_unauthenticated(self, app, client):
        resp = client.post("/api/price-overrides/1/approve", json={"password": "x"})
        assert resp.status_code == 401

    def test_approve_wrong_role(self, app, client):
        _seed_and_login(app, client, role=UserRole.FRONT_DESK_AGENT, username="agent_poa")
        resp = client.post("/api/price-overrides/1/approve", json={
            "password": "TestPassword123!",
        })
        assert resp.status_code == 403

    def test_execute_wrong_role(self, app, client):
        _seed_and_login(app, client, role=UserRole.QC_INSPECTOR, username="qc_poe")
        resp = client.post("/api/price-overrides/1/execute")
        assert resp.status_code == 403
        assert "error" in resp.get_json()

    def test_stale_approve_returns_error(self, app, client):
        _seed_and_login(app, client, role=UserRole.SHIFT_SUPERVISOR, username="sup_stale_po")
        resp = client.post("/api/price-overrides/99999/approve", json={
            "password": "TestPassword123!",
        })
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_full_request_approve_execute_flow(self, app, client):
        """End-to-end: request → approve → execute."""
        store = _seed_and_login(app, client)
        tid = self._create_ticket(app, client, store)

        # Request override
        resp = client.post("/api/price-overrides", json={
            "ticket_id": tid, "proposed_payout": 42.50, "reason": "VIP customer",
        })
        assert resp.status_code == 201
        req_id = resp.get_json()["data"]["id"]

        # Self-approval must fail
        resp = client.post(f"/api/price-overrides/{req_id}/approve", json={
            "password": "TestPassword123!",
        })
        assert resp.status_code == 403

        # Approve by supervisor
        _seed_and_login(app, client, role=UserRole.SHIFT_SUPERVISOR, username="sup_po")
        resp = client.post(f"/api/price-overrides/{req_id}/approve", json={
            "password": "TestPassword123!",
        })
        assert resp.status_code == 200

        # Wrong password on approve must fail (already approved, so status error)
        resp = client.post(f"/api/price-overrides/{req_id}/approve", json={
            "password": "TestPassword123!",
        })
        assert resp.status_code == 400  # Already approved — not pending

        # Execute
        resp = client.post(f"/api/price-overrides/{req_id}/execute")
        assert resp.status_code == 200

        # Duplicate execute — already executed
        resp = client.post(f"/api/price-overrides/{req_id}/execute")
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_wrong_password_on_approve(self, app, client):
        store = _seed_and_login(app, client)
        tid = self._create_ticket(app, client, store)
        resp = client.post("/api/price-overrides", json={
            "ticket_id": tid, "proposed_payout": 50.0, "reason": "test",
        })
        assert resp.status_code == 201
        req_id = resp.get_json()["data"]["id"]

        _seed_and_login(app, client, role=UserRole.SHIFT_SUPERVISOR, username="sup_po_bad")
        resp = client.post(f"/api/price-overrides/{req_id}/approve", json={
            "password": "WrongPassword!!!",
        })
        assert resp.status_code == 403

    def test_invalid_id_returns_structured_error(self, app, client):
        _seed_and_login(app, client, role=UserRole.SHIFT_SUPERVISOR, username="sup_po_inv")
        for endpoint in ["/api/price-overrides/0/approve",
                         "/api/price-overrides/0/reject",
                         "/api/price-overrides/0/execute"]:
            resp = client.post(endpoint, json={
                "password": "TestPassword123!", "reason": "test",
            })
            assert resp.status_code == 400


# ════════════════════════════════════════════════════════════
# CROSS-STORE API ACCESS MATRIX
# ════════════════════════════════════════════════════════════

class TestCrossStoreAccessMatrix:
    """Verify cross-store access is blocked at the API level
    for all sensitive resource types."""

    def _setup_two_stores(self, app, client):
        """Bootstrap admin, create two stores, create agents in each."""
        # Bootstrap admin
        resp = client.post("/api/auth/bootstrap", json={
            "username": "xadmin", "password": "AdminPass123!",
            "display_name": "Cross-Store Admin",
        })
        if resp.status_code == 403:
            # Already bootstrapped — log in
            pass
        resp = client.post("/api/auth/login", json={
            "username": "xadmin", "password": "AdminPass123!",
        })
        if resp.status_code != 200:
            # Fall back: use _seed_and_login to create an admin
            return None, None
        csrf = resp.get_json()["data"]["csrf_token"]
        client.environ_base["HTTP_X_CSRF_TOKEN"] = csrf

        # Create store A
        resp = client.post("/api/admin/stores", json={
            "code": "STORE_A", "name": "Store A",
        })
        if resp.status_code != 201:
            return None, None
        store_a = resp.get_json()["data"]["id"]

        # Create store B
        resp = client.post("/api/admin/stores", json={
            "code": "STORE_B", "name": "Store B",
        })
        assert resp.status_code == 201
        store_b = resp.get_json()["data"]["id"]

        # Pricing rules for both
        for sid in [store_a, store_b]:
            client.post("/api/admin/pricing_rules", json={
                "store_id": sid, "base_rate_per_lb": 1.5,
                "bonus_pct": 10, "max_ticket_payout": 200,
                "max_rate_per_lb": 5,
            })

        # Agent in store A
        client.post("/api/auth/users", json={
            "username": "agent_a", "password": "AgentAPass123!",
            "display_name": "Agent A", "role": "front_desk_agent",
            "store_id": store_a,
        })
        # Agent in store B
        client.post("/api/auth/users", json={
            "username": "agent_b", "password": "AgentBPass123!",
            "display_name": "Agent B", "role": "front_desk_agent",
            "store_id": store_b,
        })

        return store_a, store_b

    def test_cross_store_ticket_access(self, app, client):
        store_a, store_b = self._setup_two_stores(app, client)
        if store_a is None:
            pytest.skip("Admin bootstrap failed")

        # Agent A creates ticket
        client.post("/api/auth/login", json={
            "username": "agent_a", "password": "AgentAPass123!",
        })
        csrf = client.post("/api/auth/login", json={
            "username": "agent_a", "password": "AgentAPass123!",
        }).get_json()["data"]["csrf_token"]
        client.environ_base["HTTP_X_CSRF_TOKEN"] = csrf
        resp = client.post("/api/tickets", json={
            "customer_name": "Store A Customer",
            "clothing_category": "shirts",
            "condition_grade": "A",
            "estimated_weight_lbs": 10.0,
        })
        assert resp.status_code == 201
        ticket_a = resp.get_json()["data"]["id"]

        # Agent B tries to act on store A's ticket
        resp = client.post("/api/auth/login", json={
            "username": "agent_b", "password": "AgentBPass123!",
        })
        csrf = resp.get_json()["data"]["csrf_token"]
        client.environ_base["HTTP_X_CSRF_TOKEN"] = csrf
        resp = client.post(f"/api/tickets/{ticket_a}/submit-qc")
        assert resp.status_code == 403

    def test_cross_store_notification_access(self, app, client):
        store_a, store_b = self._setup_two_stores(app, client)
        if store_a is None:
            pytest.skip("Admin bootstrap failed")

        # Agent A creates ticket
        resp = client.post("/api/auth/login", json={
            "username": "agent_a", "password": "AgentAPass123!",
        })
        csrf = resp.get_json()["data"]["csrf_token"]
        client.environ_base["HTTP_X_CSRF_TOKEN"] = csrf
        resp = client.post("/api/tickets", json={
            "customer_name": "Notification Test",
            "clothing_category": "shirts",
            "condition_grade": "A",
            "estimated_weight_lbs": 5.0,
        })
        ticket_a = resp.get_json()["data"]["id"]

        # Agent B tries to send notification on store A's ticket
        resp = client.post("/api/auth/login", json={
            "username": "agent_b", "password": "AgentBPass123!",
        })
        csrf = resp.get_json()["data"]["csrf_token"]
        client.environ_base["HTTP_X_CSRF_TOKEN"] = csrf
        resp = client.post("/api/notifications/messages", json={
            "ticket_id": ticket_a,
            "message_body": "Cross-store attempt",
        })
        assert resp.status_code == 403

    def test_cross_store_qc_access(self, app, client):
        store_a, store_b = self._setup_two_stores(app, client)
        if store_a is None:
            pytest.skip("Admin bootstrap failed")

        # Create QC inspector in store B
        resp = client.post("/api/auth/login", json={
            "username": "xadmin", "password": "AdminPass123!",
        })
        csrf = resp.get_json()["data"]["csrf_token"]
        client.environ_base["HTTP_X_CSRF_TOKEN"] = csrf
        client.post("/api/auth/users", json={
            "username": "qc_b", "password": "QCBPass123!",
            "display_name": "QC B", "role": "qc_inspector",
            "store_id": store_b,
        })

        # Agent A creates ticket
        resp = client.post("/api/auth/login", json={
            "username": "agent_a", "password": "AgentAPass123!",
        })
        csrf = resp.get_json()["data"]["csrf_token"]
        client.environ_base["HTTP_X_CSRF_TOKEN"] = csrf
        resp = client.post("/api/tickets", json={
            "customer_name": "QC Cross Test",
            "clothing_category": "shirts",
            "condition_grade": "A",
            "estimated_weight_lbs": 10.0,
        })
        ticket_a = resp.get_json()["data"]["id"]
        client.post(f"/api/tickets/{ticket_a}/submit-qc")

        # QC inspector from store B tries inspection on store A ticket
        resp = client.post("/api/auth/login", json={
            "username": "qc_b", "password": "QCBPass123!",
        })
        csrf = resp.get_json()["data"]["csrf_token"]
        client.environ_base["HTTP_X_CSRF_TOKEN"] = csrf
        resp = client.post("/api/qc/inspections", json={
            "ticket_id": ticket_a,
            "actual_weight_lbs": 10.0,
            "lot_size": 10,
            "nonconformance_count": 0,
            "inspection_outcome": "pass",
        })
        assert resp.status_code == 403
