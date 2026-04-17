"""Verify that seed_demo_users provisions all expected accounts and that
each one can authenticate successfully."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fullstack", "backend"))

import pytest
from app import create_app
from src.database import init_db


@pytest.fixture
def seeded_app(tmp_path, monkeypatch):
    monkeypatch.setenv("RECLAIM_OPS_DEV_MODE", "true")
    monkeypatch.setenv("RECLAIM_OPS_REQUIRE_TLS", "false")
    monkeypatch.setenv("SECURE_COOKIES", "false")
    monkeypatch.setenv("RECLAIM_OPS_SEED_DEMO_USERS", "true")
    export_dir = str(tmp_path / "exports")
    monkeypatch.setenv("EXPORT_OUTPUT_DIR", export_dir)
    import src.services.export_service as _es
    monkeypatch.setattr(_es, "EXPORT_OUTPUT_DIR", export_dir)
    db_path = str(tmp_path / "seed_test.db")
    app = create_app(db_path=db_path)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def seeded_client(seeded_app):
    with seeded_app.test_client() as c:
        yield c


def _login(client, username, password):
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        content_type="application/json",
    )


# --- Seeded account presence ---

def test_admin_account_seeded(seeded_client):
    r = _login(seeded_client, "admin", "AdminPass123!")
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["user"]["role"] == "administrator"
    assert data["user"]["username"] == "admin"


def test_operator_account_seeded(seeded_client):
    r = _login(seeded_client, "operator", "DemoPass1234!")
    assert r.status_code == 200
    assert r.get_json()["data"]["user"]["role"] == "front_desk_agent"


def test_supervisor_account_seeded(seeded_client):
    r = _login(seeded_client, "supervisor", "DemoPass1234!")
    assert r.status_code == 200
    assert r.get_json()["data"]["user"]["role"] == "shift_supervisor"


def test_qcinspector_account_seeded(seeded_client):
    r = _login(seeded_client, "qcinspector", "DemoPass1234!")
    assert r.status_code == 200
    assert r.get_json()["data"]["user"]["role"] == "qc_inspector"


def test_host_account_seeded(seeded_client):
    r = _login(seeded_client, "host", "DemoPass1234!")
    assert r.status_code == 200
    assert r.get_json()["data"]["user"]["role"] == "host"


def test_opsmanager_account_seeded(seeded_client):
    r = _login(seeded_client, "opsmanager", "DemoPass1234!")
    assert r.status_code == 200
    assert r.get_json()["data"]["user"]["role"] == "operations_manager"


# --- CSRF token returned on login ---

def test_login_returns_csrf_token(seeded_client):
    r = _login(seeded_client, "admin", "AdminPass123!")
    assert r.status_code == 200
    assert "csrf_token" in r.get_json()["data"]


# --- Session cookie set ---

def test_login_sets_session_cookie(seeded_client):
    r = _login(seeded_client, "operator", "DemoPass1234!")
    assert r.status_code == 200
    assert seeded_client.get_cookie("session_nonce") is not None


# --- Wrong password rejected ---

def test_wrong_password_rejected(seeded_client):
    r = _login(seeded_client, "admin", "WrongPassword!")
    assert r.status_code == 401


# --- Seeding is idempotent (second create_app call must not crash) ---

def test_seed_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("RECLAIM_OPS_DEV_MODE", "true")
    monkeypatch.setenv("RECLAIM_OPS_REQUIRE_TLS", "false")
    monkeypatch.setenv("SECURE_COOKIES", "false")
    monkeypatch.setenv("RECLAIM_OPS_SEED_DEMO_USERS", "true")
    export_dir = str(tmp_path / "exports")
    monkeypatch.setenv("EXPORT_OUTPUT_DIR", export_dir)
    import src.services.export_service as _es
    monkeypatch.setattr(_es, "EXPORT_OUTPUT_DIR", export_dir)
    db_path = str(tmp_path / "idem_test.db")
    create_app(db_path=db_path)
    app2 = create_app(db_path=db_path)
    app2.config["TESTING"] = True
    with app2.test_client() as c:
        r = _login(c, "admin", "AdminPass123!")
        assert r.status_code == 200


# --- All seeded users assigned to the DEMO store ---

def test_role_users_have_store(seeded_app):
    with seeded_app.app_context():
        from app import get_db
        from flask import g
        g.db_path = seeded_app.config["DB_PATH"]
        db = get_db()
        from src.repositories import UserRepository, StoreRepository
        user_repo = UserRepository(db)
        store_repo = StoreRepository(db)
        store = store_repo.get_by_code("DEMO")
        assert store is not None
        for username in ("operator", "supervisor", "qcinspector", "host", "opsmanager"):
            user = user_repo.get_by_username(username)
            assert user is not None
            assert user.store_id == store.id
