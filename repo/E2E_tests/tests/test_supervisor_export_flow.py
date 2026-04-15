"""Playwright E2E — supervisor approves and executes an export end-to-end.

Drives the actual /ui/exports page as a shift_supervisor: requests an
export, waits for the partial to refresh, then a SECOND supervisor
approves it (dual-control) via the partial Approve button.
"""
import pytest
import requests
from playwright.sync_api import Page, expect


def _login(page: Page, base_url: str, username: str, password: str,
           landing_path: str):
    page.goto(f"{base_url}/ui/login")
    page.fill("input[name='username']", username)
    page.fill("input[name='password']", password)
    page.click("button[type='submit']")
    # Login JS unconditionally redirects to /ui/tickets — wait for any
    # navigation away from /ui/login, then go to the page we care about.
    page.wait_for_url(lambda u: "/ui/login" not in u, timeout=10_000)
    page.goto(f"{base_url}{landing_path}")


def _seed_ticket(provisioned):
    """API-create a ticket so the export has something to render."""
    base = provisioned["base_url"]
    sess = requests.Session()
    r = sess.post(f"{base}/api/auth/login", json={
        "username": provisioned["operator_user"],
        "password": provisioned["operator_password"],
    }, timeout=10)
    csrf = r.json()["data"]["csrf_token"]
    sess.post(
        f"{base}/api/tickets",
        json={
            "customer_name": "Export Seed", "clothing_category": "shirts",
            "condition_grade": "A", "estimated_weight_lbs": 5.0,
        },
        headers={"X-CSRF-Token": csrf}, timeout=10,
    )


def test_supervisor_requests_export_visible_in_list(page: Page, provisioned):
    _seed_ticket(provisioned)
    base = provisioned["base_url"]

    # Supervisor 1 logs into Reports & Exports page
    _login(page, base, provisioned["supervisor_user"],
           provisioned["operator_password"], "/ui/exports")
    expect(page).to_have_title("ReclaimOps — Reports & Exports")

    # Submit the request-export form
    form = page.locator("#export-form")
    form.locator("select[name='export_type']").select_option("tickets")
    form.locator("button[type='submit']").click()

    # The submission renders a JSON success blob into #export-result
    expect(page.locator("#export-result")).to_contain_text("status", timeout=10_000)

    # Refresh the export list partial and verify the new request appears
    page.locator("button", has_text="Refresh").first.click()
    listing = page.locator("#export-list")
    expect(listing).to_contain_text("tickets", timeout=10_000)


def test_second_supervisor_approves_export_via_partial(page: Page, provisioned):
    """Dual-control: a different supervisor approves the request through
    the HTMX partial Approve button (uses hx-prompt for the password)."""
    _seed_ticket(provisioned)
    base = provisioned["base_url"]

    # Force approval-required by toggling the store setting via API
    sess = requests.Session()
    r = sess.post(f"{base}/api/auth/login", json={
        "username": provisioned["admin_user"],
        "password": provisioned["admin_password"],
    }, timeout=10)
    csrf = r.json()["data"]["csrf_token"]
    sess.put(f"{base}/api/settings",
             json={"store_id": provisioned["store_id"],
                   "export_requires_supervisor_default": True},
             headers={"X-CSRF-Token": csrf}, timeout=10)

    # Supervisor 1 creates a pending request via API
    r = sess.post(f"{base}/api/auth/login", json={
        "username": provisioned["supervisor_user"],
        "password": provisioned["operator_password"],
    }, timeout=10)
    sup_csrf = r.json()["data"]["csrf_token"]
    r = sess.post(f"{base}/api/exports/requests",
                  json={"export_type": "tickets"},
                  headers={"X-CSRF-Token": sup_csrf}, timeout=10)
    assert r.status_code == 201, r.text
    req_id = r.json()["data"]["id"]
    assert r.json()["data"]["status"] == "pending"

    # Supervisor 2 logs into the UI and approves via the partial
    _login(page, base, provisioned["supervisor_2_user"],
           provisioned["operator_password"], "/ui/exports")

    # Refresh the list so it picks up the new pending request
    page.locator("button", has_text="Refresh").first.click()
    listing = page.locator("#export-list")
    expect(listing).to_contain_text(f"#{req_id}", timeout=10_000)

    # The Approve button uses hx-prompt — accept the dialog with the password
    page.once("dialog", lambda d: d.accept(provisioned["operator_password"]))
    listing.get_by_role("button", name="Approve").first.click()

    # After the swap, the request should show "approved" status
    expect(listing).to_contain_text("approved", timeout=10_000)
