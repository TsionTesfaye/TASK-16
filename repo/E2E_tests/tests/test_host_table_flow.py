"""Playwright E2E — host opens a table and walks it through the full
state machine via HTMX partial buttons (occupied → pre_checkout →
cleared → available)."""
import pytest
import requests
from playwright.sync_api import Page, expect


def _admin_create_table(provisioned, table_code: str) -> int:
    """Admin creates a service table via API. Returns table_id."""
    base = provisioned["base_url"]
    sess = requests.Session()
    r = sess.post(f"{base}/api/auth/login", json={
        "username": provisioned["admin_user"],
        "password": provisioned["admin_password"],
    }, timeout=10)
    csrf = r.json()["data"]["csrf_token"]
    r = sess.post(f"{base}/api/admin/service_tables", json={
        "store_id": provisioned["store_id"],
        "table_code": table_code, "area_type": "intake_table",
    }, headers={"X-CSRF-Token": csrf}, timeout=10)
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def test_host_opens_table_and_advances_state_machine(page: Page, provisioned):
    base = provisioned["base_url"]
    table_id = _admin_create_table(provisioned, f"HOST-{id(page) % 10000}")

    # Host logs in. The login JS always navigates to /ui/tickets which
    # the host role cannot see — that triggers a redirect back to
    # /ui/login, so we wait for ANY navigation away from the form
    # action then manually go to /ui/tables. The session cookie is
    # already set, so /ui/tables loads cleanly.
    page.goto(f"{base}/ui/login")
    page.fill("input[name='username']", provisioned["host_user"])
    page.fill("input[name='password']", provisioned["operator_password"])
    page.click("button[type='submit']")
    # After click, JS sets location.href; wait for some URL change
    page.wait_for_load_state("networkidle", timeout=10_000)
    page.goto(f"{base}/ui/tables")
    expect(page).to_have_title("ReclaimOps — Tables / Rooms")

    # Open a table via the form
    open_form = page.locator("#open-form")
    open_form.locator("input[name='table_id']").fill(str(table_id))
    open_form.locator("input[name='customer_label']").fill("E2E Customer")
    open_form.locator("button[type='submit']").click()

    result = page.locator("#table-result")
    expect(result).to_contain_text("opened", timeout=10_000)
    expect(result).to_contain_text("occupied")

    # Refresh the board partial and verify the new session card is there
    page.locator("button", has_text="Refresh").first.click()
    board = page.locator("#table-board")
    expect(board).to_contain_text("E2E Customer", timeout=10_000)
    expect(board).to_contain_text("occupied")

    # Click the Pre-Checkout button on the session card (HTMX partial)
    board.get_by_role("button", name="Pre-Checkout").first.click()
    expect(board).to_contain_text("pre_checkout", timeout=10_000)

    # Click Clear
    board.get_by_role("button", name="Clear").first.click()
    expect(board).to_contain_text("cleared", timeout=10_000)

    # Click Release — the session row stays but its state badge flips to
    # "available" (the board partial includes all non-closed sessions).
    board.get_by_role("button", name="Release").first.click()
    expect(board).to_contain_text("available", timeout=10_000)
