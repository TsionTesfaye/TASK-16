"""Playwright E2E — login flow + session/CSRF wiring."""
import pytest
from playwright.sync_api import Page, expect


@pytest.fixture
def app_url(provisioned):
    """Alias — `base_url` name collides with pytest-base-url plugin."""
    return provisioned["base_url"]


def test_login_page_loads(page: Page, app_url):
    page.goto(f"{app_url}/ui/login")
    expect(page).to_have_title("ReclaimOps — Sign In")
    expect(page.locator("input[name='username']")).to_be_visible()
    expect(page.locator("input[name='password']")).to_be_visible()


def test_unauthenticated_pages_redirect_to_login(page: Page, app_url):
    for path in ["/ui/tickets", "/ui/qc", "/ui/tables", "/ui/notifications"]:
        page.goto(f"{app_url}{path}")
        expect(page).to_have_url(f"{app_url}/ui/login")


def test_operator_login_and_tickets_page_loads(page: Page, provisioned):
    base = provisioned["base_url"]
    page.goto(f"{base}/ui/login")
    page.fill("input[name='username']", provisioned["operator_user"])
    page.fill("input[name='password']", provisioned["operator_password"])
    page.click("button[type='submit']")

    page.wait_for_url(f"{base}/ui/tickets", timeout=10_000)
    expect(page).to_have_title("ReclaimOps — Tickets")

    cookies = {c["name"] for c in page.context.cookies()}
    assert "session_nonce" in cookies
    assert "csrf_token" in cookies


def test_bad_password_shows_error(page: Page, app_url):
    page.goto(f"{app_url}/ui/login")
    page.fill("input[name='username']", "e2eoperator")
    page.fill("input[name='password']", "WrongPassword1234!")
    page.click("button[type='submit']")

    # Error div appears inside #login-msg
    expect(page.locator("#login-msg .msg-error")).to_be_visible(timeout=5_000)
    expect(page).to_have_url(f"{app_url}/ui/login")
