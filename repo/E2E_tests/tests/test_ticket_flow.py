"""Playwright E2E — full ticket lifecycle through the browser."""
import pytest
from playwright.sync_api import Page, expect


def _login_as_operator(page: Page, provisioned):
    base = provisioned["base_url"]
    page.goto(f"{base}/ui/login")
    page.fill("input[name='username']", provisioned["operator_user"])
    page.fill("input[name='password']", provisioned["operator_password"])
    page.click("button[type='submit']")
    page.wait_for_url(f"{base}/ui/tickets", timeout=10_000)


def _create_ticket(page: Page, customer="PW", weight="10"):
    """Fill and submit the new-ticket form (id='ticket-form')."""
    form = page.locator("#ticket-form")
    form.locator("input[name='customer_name']").fill(customer)
    form.locator("select[name='clothing_category']").select_option("shirts")
    form.locator("select[name='condition_grade']").select_option("A")
    form.locator("input[name='estimated_weight_lbs']").fill(weight)
    form.locator("button[type='submit']").click()


def test_create_ticket_and_appears_in_queue(page: Page, provisioned):
    _login_as_operator(page, provisioned)
    _create_ticket(page, customer="Playwright Customer", weight="10")

    # Queue reloads after create → wait for the customer name to appear
    queue = page.locator("#ticket-queue")
    # Refresh the queue manually to be robust — HTMX loads on `load` trigger
    page.locator("button", has_text="Refresh").first.click()
    expect(queue).to_contain_text("Playwright Customer", timeout=10_000)
    expect(queue).to_contain_text("intake_open")


def test_queue_refresh_button_reloads(page: Page, provisioned):
    _login_as_operator(page, provisioned)
    # Click the "Refresh" button (inside the Ticket Queue card)
    refresh = page.locator("button", has_text="Refresh").first
    refresh.click()
    expect(page.locator("#ticket-queue")).to_be_visible(timeout=5_000)


def test_logout_clears_session(page: Page, provisioned):
    _login_as_operator(page, provisioned)
    base = provisioned["base_url"]

    # Logout link triggers hx-post + delayed redirect
    page.locator("a", has_text="Logout").click()
    page.wait_for_url(f"{base}/ui/login", timeout=10_000)

    page.goto(f"{base}/ui/tickets")
    expect(page).to_have_url(f"{base}/ui/login")
