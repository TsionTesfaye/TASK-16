"""Playwright E2E — HTMX partial endpoints render correct HTML
when driven by a real browser."""
import pytest
from playwright.sync_api import Page, expect


def _login_operator(page: Page, provisioned):
    base = provisioned["base_url"]
    page.goto(f"{base}/ui/login")
    page.fill("input[name='username']", provisioned["operator_user"])
    page.fill("input[name='password']", provisioned["operator_password"])
    page.click("button[type='submit']")
    page.wait_for_url(f"{base}/ui/tickets", timeout=10_000)


def _create_ticket(page: Page, customer="HTMX Row"):
    form = page.locator("#ticket-form")
    form.locator("input[name='customer_name']").fill(customer)
    form.locator("select[name='clothing_category']").select_option("shirts")
    form.locator("select[name='condition_grade']").select_option("A")
    form.locator("input[name='estimated_weight_lbs']").fill("5")
    form.locator("button[type='submit']").click()


def test_ticket_queue_partial_renders_table_structure(page: Page, provisioned):
    _login_operator(page, provisioned)
    _create_ticket(page, "HTMX Structure")

    queue = page.locator("#ticket-queue")
    page.locator("button", has_text="Refresh").first.click()
    expect(queue).to_contain_text("HTMX Structure", timeout=10_000)

    expect(queue.locator("table thead")).to_contain_text("ID")
    expect(queue.locator("table thead")).to_contain_text("Customer")
    expect(queue.locator("table thead")).to_contain_text("Status")
    expect(queue.locator("table thead")).to_contain_text("Actions")


def test_submit_qc_button_updates_row_status_in_place(page: Page, provisioned):
    _login_operator(page, provisioned)
    _create_ticket(page, "Submit-QC Customer")

    queue = page.locator("#ticket-queue")
    page.locator("button", has_text="Refresh").first.click()
    expect(queue).to_contain_text("Submit-QC Customer", timeout=10_000)

    # hx-confirm raises a native dialog — accept it automatically
    page.once("dialog", lambda d: d.accept())
    queue.get_by_role("button", name="QC").first.click()

    expect(queue).to_contain_text("Awaiting QC", timeout=10_000)
