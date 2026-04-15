"""Playwright E2E test configuration.

Targets the `backend-e2e` Docker service (plain HTTP, dev mode).
Waits for the service's /health endpoint to be reachable, then
bootstraps the first admin and provisions a test store + users.
"""
import os
import time

import pytest
import requests


BASE_URL = os.environ.get("E2E_BASE_URL", "http://backend-e2e:5000")


def _wait_for_health(timeout_s: int = 60) -> None:
    """Block until /health returns 200 or the timeout elapses."""
    deadline = time.time() + timeout_s
    last_err = None
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE_URL}/health", timeout=2)
            if r.status_code == 200:
                return
        except requests.RequestException as e:
            last_err = e
        time.sleep(1)
    raise RuntimeError(f"Backend not healthy at {BASE_URL}: {last_err}")


@pytest.fixture(scope="session", autouse=True)
def _ensure_backend_ready():
    _wait_for_health()


@pytest.fixture(scope="session")
def admin_credentials():
    """Bootstrap the first admin if not yet done. Returns (user, pw)."""
    _wait_for_health()
    username = "e2eadmin"
    password = "E2EAdminPass123!"
    r = requests.post(
        f"{BASE_URL}/api/auth/bootstrap",
        json={
            "username": username, "password": password,
            "display_name": "E2E Admin",
        },
        timeout=10,
    )
    # 201 on first boot, 403 if already bootstrapped — both OK
    assert r.status_code in (201, 403), r.text
    return username, password


@pytest.fixture(scope="session")
def provisioned(admin_credentials):
    """Admin logs in, creates a store + front-desk operator. Returns dict."""
    sess = requests.Session()
    admin_user, admin_pw = admin_credentials

    r = sess.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": admin_user, "password": admin_pw},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    csrf = r.json()["data"]["csrf_token"]
    headers = {"X-CSRF-Token": csrf}

    # Create or re-use store "E2E"
    r = sess.post(
        f"{BASE_URL}/api/admin/stores",
        json={"code": "E2E", "name": "E2E Store"},
        headers=headers, timeout=10,
    )
    if r.status_code == 201:
        store_id = r.json()["data"]["id"]
    else:
        # Already exists — look it up
        r = sess.get(f"{BASE_URL}/api/admin/stores", headers=headers, timeout=10)
        assert r.status_code == 200, r.text
        stores = r.json()["data"]
        store_id = next(s["id"] for s in stores if s["code"] == "E2E")

    # Create a pricing rule (idempotent — create fresh each session attempt)
    sess.post(
        f"{BASE_URL}/api/admin/pricing_rules",
        json={
            "store_id": store_id, "base_rate_per_lb": 1.5, "bonus_pct": 10.0,
            "max_ticket_payout": 50.0, "max_rate_per_lb": 5.0,
        },
        headers=headers, timeout=10,
    )

    # Provision one user per business role so multi-role E2E specs can
    # log in as the right actor.  All users share the same password so
    # the specs stay readable.
    operator_password = "E2EOperatorPass123!"
    role_users = [
        ("e2eoperator", "front_desk_agent",  "E2E Operator"),
        ("e2esup1",     "shift_supervisor",  "E2E Supervisor 1"),
        ("e2esup2",     "shift_supervisor",  "E2E Supervisor 2"),
        ("e2eqc",       "qc_inspector",      "E2E QC Inspector"),
        ("e2ehost",     "host",              "E2E Host"),
        ("e2eops",      "operations_manager","E2E Ops Manager"),
    ]
    for username, role, display in role_users:
        sess.post(
            f"{BASE_URL}/api/auth/users",
            json={
                "username": username, "password": operator_password,
                "display_name": display,
                "role": role, "store_id": store_id,
            },
            headers=headers, timeout=10,
        )

    return {
        "base_url": BASE_URL,
        "admin_user": admin_user,
        "admin_password": admin_pw,
        "operator_user": "e2eoperator",
        "operator_password": operator_password,
        "supervisor_user": "e2esup1",
        "supervisor_2_user": "e2esup2",
        "qc_user": "e2eqc",
        "host_user": "e2ehost",
        "ops_user": "e2eops",
        "store_id": store_id,
    }
