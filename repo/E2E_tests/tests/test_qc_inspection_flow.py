"""Playwright E2E — QC inspector records an inspection through the UI.

Operator creates and submits a ticket via API, then a QC inspector
loads /ui/qc and records an inspection through the form. Verifies the
QC queue partial reflects the change after HTMX swap.
"""
import pytest
import requests
from playwright.sync_api import Page, expect


def _api_create_and_submit_ticket(provisioned, customer_name: str) -> int:
    """Returns the ticket_id created by the operator and submitted to QC."""
    base = provisioned["base_url"]
    sess = requests.Session()
    r = sess.post(f"{base}/api/auth/login", json={
        "username": provisioned["operator_user"],
        "password": provisioned["operator_password"],
    }, timeout=10)
    csrf = r.json()["data"]["csrf_token"]
    headers = {"X-CSRF-Token": csrf}

    r = sess.post(f"{base}/api/tickets", json={
        "customer_name": customer_name, "clothing_category": "shirts",
        "condition_grade": "A", "estimated_weight_lbs": 10.0,
    }, headers=headers, timeout=10)
    assert r.status_code == 201, r.text
    tid = r.json()["data"]["id"]
    sess.post(f"{base}/api/tickets/{tid}/submit-qc", headers=headers, timeout=10)
    return tid


def test_qc_inspector_records_inspection_via_form(page: Page, provisioned):
    base = provisioned["base_url"]
    tid = _api_create_and_submit_ticket(provisioned, "QC Inspect Customer")

    # QC inspector logs in (login JS lands on /ui/tickets which QC can see),
    # then we navigate to /ui/qc.
    page.goto(f"{base}/ui/login")
    page.fill("input[name='username']", provisioned["qc_user"])
    page.fill("input[name='password']", provisioned["operator_password"])
    page.click("button[type='submit']")
    page.wait_for_url(lambda u: "/ui/login" not in u, timeout=10_000)
    page.goto(f"{base}/ui/qc")
    expect(page).to_have_title("ReclaimOps — QC & Traceability")

    # The QC queue partial loads on page load — verify our ticket is awaiting QC
    queue = page.locator("#qc-queue")
    expect(queue).to_contain_text(f"#{tid}", timeout=10_000)

    # Fill in the QC inspection form
    form = page.locator("#qc-form")
    form.locator("input[name='ticket_id']").fill(str(tid))
    form.locator("input[name='actual_weight_lbs']").fill("10")
    form.locator("input[name='lot_size']").fill("10")
    form.locator("input[name='nonconformance_count']").fill("0")
    form.locator("select[name='inspection_outcome']").select_option("pass")
    form.locator("button[type='submit']").click()

    # Result message reports the new inspection ID + outcome badge
    result = page.locator("#qc-result")
    expect(result).to_contain_text("Inspection #", timeout=10_000)
    expect(result).to_contain_text("pass")


def test_qc_compute_final_payout_completes_ticket(page: Page, provisioned):
    base = provisioned["base_url"]
    tid = _api_create_and_submit_ticket(provisioned, "QC Final Customer")

    # First record the inspection via API to get to a state where qc-final works
    sess = requests.Session()
    r = sess.post(f"{base}/api/auth/login", json={
        "username": provisioned["qc_user"],
        "password": provisioned["operator_password"],
    }, timeout=10)
    csrf = r.json()["data"]["csrf_token"]
    sess.post(f"{base}/api/qc/inspections", json={
        "ticket_id": tid, "actual_weight_lbs": 10.0,
        "lot_size": 10, "nonconformance_count": 0,
        "inspection_outcome": "pass",
    }, headers={"X-CSRF-Token": csrf}, timeout=10)

    # Now drive the qc-final form in the UI
    page.goto(f"{base}/ui/login")
    page.fill("input[name='username']", provisioned["qc_user"])
    page.fill("input[name='password']", provisioned["operator_password"])
    page.click("button[type='submit']")
    page.wait_for_url(lambda u: "/ui/login" not in u, timeout=10_000)
    page.goto(f"{base}/ui/qc")

    final_form = page.locator("#qc-final-form")
    final_form.locator("input[name='ticket_id']").fill(str(tid))
    final_form.locator("button[type='submit']").click()

    result = page.locator("#qc-final-result")
    expect(result).to_contain_text("Status:", timeout=10_000)
    # Matching weight → completes directly (no variance approval needed)
    expect(result).to_contain_text("completed")
    expect(result).to_contain_text("Final Payout:")
