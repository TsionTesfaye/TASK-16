"""Tests for UI page routes and root redirect.

Covers:
- GET / → redirect to /ui/login
- GET /ui/ → redirect chain → /ui/login (unauthenticated)
- GET /ui/login → 200, correct title, login form present
- All protected pages redirect unauthenticated requests to /ui/login
- Authenticated role-gated pages render correct HTML structure
- Wrong-role requests redirected to /ui/login
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fullstack", "backend"))

import pytest
from app import create_app
from src.enums.user_role import UserRole
from src.repositories import (
    UserRepository, UserSessionRepository, SettingsRepository,
    StoreRepository, AuditLogRepository,
)
from src.services.auth_service import AuthService
from src.services.audit_service import AuditService
from src.models.store import Store


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("RECLAIM_OPS_DEV_MODE", "true")
    monkeypatch.setenv("RECLAIM_OPS_REQUIRE_TLS", "false")
    monkeypatch.setenv("SECURE_COOKIES", "false")
    export_dir = str(tmp_path / "exports")
    monkeypatch.setenv("EXPORT_OUTPUT_DIR", export_dir)
    import src.services.export_service as _es
    monkeypatch.setattr(_es, "EXPORT_OUTPUT_DIR", export_dir)
    db_path = str(tmp_path / "ui_test.db")
    application = create_app(db_path=db_path)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


def _seed_and_login(app, client, role=UserRole.FRONT_DESK_AGENT, username="uiuser"):
    with app.app_context():
        from app import get_db
        from flask import g
        g.db_path = app.config["DB_PATH"]
        db = get_db()
        store_repo = StoreRepository(db)
        store = store_repo.get_by_code("UITEST")
        if store is None:
            store = store_repo.create(Store(code="UITEST", name="UI Test Store"))
        audit_svc = AuditService(AuditLogRepository(db))
        auth_svc = AuthService(
            UserRepository(db), UserSessionRepository(db),
            SettingsRepository(db), audit_svc,
        )
        try:
            admin = auth_svc.bootstrap_admin(
                username="uiadmin", password="AdminPass1234!", display_name="UI Admin",
            )
        except PermissionError:
            admin = UserRepository(db).get_by_username("uiadmin")
        if role != UserRole.ADMINISTRATOR:
            try:
                auth_svc.create_user(
                    username=username, password="TestPass1234!",
                    display_name="UI Test User", role=role,
                    admin_user_id=admin.id, admin_username=admin.username,
                    admin_role=admin.role, store_id=store.id,
                )
            except Exception:
                pass
        db.commit()

    if role == UserRole.ADMINISTRATOR:
        login_user, login_pass = "uiadmin", "AdminPass1234!"
    else:
        login_user, login_pass = username, "TestPass1234!"

    r = client.post(
        "/api/auth/login",
        json={"username": login_user, "password": login_pass},
        content_type="application/json",
    )
    assert r.status_code == 200
    return r.get_json()["data"]["csrf_token"]


# ── Root redirect ──────────────────────────────────────────────────────────

def test_root_redirects_to_ui_login(client):
    r = client.get("/")
    assert r.status_code in (301, 302)
    assert "/ui/login" in r.headers["Location"]


def test_root_redirect_follows_to_login_page(client):
    r = client.get("/", follow_redirects=True)
    assert r.status_code == 200
    assert b"ReclaimOps" in r.data
    assert b"Sign In" in r.data


# ── /ui/ index redirect ────────────────────────────────────────────────────

def test_ui_index_redirects_unauthenticated(client):
    r = client.get("/ui/")
    assert r.status_code in (301, 302)


def test_ui_index_redirect_chain_lands_on_login(client):
    r = client.get("/ui/", follow_redirects=True)
    assert r.status_code == 200
    assert b"Sign In" in r.data


# ── /ui/login ──────────────────────────────────────────────────────────────

def test_login_page_returns_200(client):
    r = client.get("/ui/login")
    assert r.status_code == 200


def test_login_page_has_correct_title(client):
    r = client.get("/ui/login")
    assert b"ReclaimOps \xe2\x80\x94 Sign In" in r.data or b"Sign In" in r.data


def test_login_page_has_username_input(client):
    r = client.get("/ui/login")
    assert b'name="username"' in r.data


def test_login_page_has_password_input(client):
    r = client.get("/ui/login")
    assert b'name="password"' in r.data


def test_login_page_has_submit_button(client):
    r = client.get("/ui/login")
    assert b'type="submit"' in r.data


def test_login_page_has_login_msg_div(client):
    r = client.get("/ui/login")
    assert b'id="login-msg"' in r.data


# ── Unauthenticated redirects ──────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "/ui/tickets", "/ui/qc", "/ui/tables", "/ui/notifications",
    "/ui/members", "/ui/exports", "/ui/schedules",
])
def test_protected_page_redirects_unauthenticated(client, path):
    r = client.get(path)
    assert r.status_code in (301, 302)
    assert "/ui/login" in r.headers["Location"]


# ── Authenticated page rendering ───────────────────────────────────────────

def test_tickets_page_renders_for_operator(app, client):
    _seed_and_login(app, client, UserRole.FRONT_DESK_AGENT, "ticketuser")
    r = client.get("/ui/tickets")
    assert r.status_code == 200
    assert b"Tickets" in r.data
    assert b"ticket-form" in r.data


def test_tickets_page_has_htmx_queue(app, client):
    _seed_and_login(app, client, UserRole.FRONT_DESK_AGENT, "htmxuser")
    r = client.get("/ui/tickets")
    assert r.status_code == 200
    assert b"hx-" in r.data


def test_qc_page_renders_for_qc_inspector(app, client):
    _seed_and_login(app, client, UserRole.QC_INSPECTOR, "qcpageuser")
    r = client.get("/ui/qc")
    assert r.status_code == 200
    assert b"QC" in r.data


def test_tables_page_renders_for_host(app, client):
    _seed_and_login(app, client, UserRole.HOST, "hostpageuser")
    r = client.get("/ui/tables")
    assert r.status_code == 200
    assert b"Tables" in r.data or b"table" in r.data.lower()


def test_notifications_page_renders_for_operator(app, client):
    _seed_and_login(app, client, UserRole.FRONT_DESK_AGENT, "notifpageuser")
    r = client.get("/ui/notifications")
    assert r.status_code == 200
    assert b"Notification" in r.data


def test_members_page_renders_for_admin(app, client):
    _seed_and_login(app, client, UserRole.ADMINISTRATOR)
    r = client.get("/ui/members")
    assert r.status_code == 200
    assert b"Member" in r.data


def test_exports_page_renders_for_supervisor(app, client):
    _seed_and_login(app, client, UserRole.SHIFT_SUPERVISOR, "suppageuser")
    r = client.get("/ui/exports")
    assert r.status_code == 200
    assert b"Export" in r.data


def test_schedules_page_renders_for_supervisor(app, client):
    _seed_and_login(app, client, UserRole.SHIFT_SUPERVISOR, "schedpageuser")
    r = client.get("/ui/schedules")
    assert r.status_code == 200
    assert b"Schedule" in r.data


# ── Role gate: wrong-role redirected ──────────────────────────────────────

def test_members_page_redirects_non_admin(app, client):
    _seed_and_login(app, client, UserRole.FRONT_DESK_AGENT, "notadminuser")
    r = client.get("/ui/members")
    assert r.status_code in (301, 302)
    assert "/ui/login" in r.headers["Location"]


def test_qc_page_redirects_front_desk(app, client):
    _seed_and_login(app, client, UserRole.FRONT_DESK_AGENT, "fdaqcuser")
    r = client.get("/ui/qc")
    assert r.status_code in (301, 302)
    assert "/ui/login" in r.headers["Location"]


def test_tables_page_redirects_operator(app, client):
    _seed_and_login(app, client, UserRole.FRONT_DESK_AGENT, "fdatableuser")
    r = client.get("/ui/tables")
    assert r.status_code in (301, 302)
    assert "/ui/login" in r.headers["Location"]


def test_exports_page_redirects_front_desk(app, client):
    _seed_and_login(app, client, UserRole.FRONT_DESK_AGENT, "fdaexportuser")
    r = client.get("/ui/exports")
    assert r.status_code in (301, 302)
    assert "/ui/login" in r.headers["Location"]


# ── Response content contracts ────────────────────────────────────────────

def test_login_page_loads_htmx(client):
    r = client.get("/ui/login")
    assert b"htmx" in r.data.lower() or b"/static/js" in r.data


def test_login_page_loads_stylesheet(client):
    r = client.get("/ui/login")
    assert b"/static/css/style.css" in r.data


def test_tickets_page_contains_csrf_wiring(app, client):
    _seed_and_login(app, client, UserRole.FRONT_DESK_AGENT, "csrfuser")
    r = client.get("/ui/tickets")
    assert r.status_code == 200
    assert b"csrf_token" in r.data or b"X-CSRF-Token" in r.data
