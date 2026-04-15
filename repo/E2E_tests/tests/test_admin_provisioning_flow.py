"""Playwright E2E — administrator provisions a member organization via
the /ui/members page and adds a member, exercising the admin-only UI."""
import pytest
import time

from playwright.sync_api import Page, expect


def test_admin_creates_organization_and_member(page: Page, provisioned):
    base = provisioned["base_url"]

    # Admin logs in (lands on /ui/tickets which admin can see)
    page.goto(f"{base}/ui/login")
    page.fill("input[name='username']", provisioned["admin_user"])
    page.fill("input[name='password']", provisioned["admin_password"])
    page.click("button[type='submit']")
    page.wait_for_url(lambda u: "/ui/login" not in u, timeout=10_000)

    # Navigate to the Members page (admin-only)
    page.goto(f"{base}/ui/members")
    expect(page).to_have_title("ReclaimOps — Members")

    # Create an organization
    org_name = f"E2E Org {int(time.time() * 1000)}"
    org_form = page.locator("#org-form")
    org_form.locator("input[name='name']").fill(org_name)
    org_form.locator("input[name='department']").fill("Acceptance")
    org_form.locator("button[type='submit']").click()

    org_result = page.locator("#org-result")
    expect(org_result).to_contain_text("name", timeout=10_000)
    expect(org_result).to_contain_text(org_name)

    # Pull the new org's ID out of the JSON success blob
    blob_text = org_result.inner_text()
    import re, json
    # The result renders pretty-printed JSON; parse the first {...} block
    m = re.search(r"\{[\s\S]*\}", blob_text)
    assert m, f"Could not find JSON in result: {blob_text}"
    data = json.loads(m.group(0))
    org_id = data["id"]

    # Add a member to that org through the Add Member form
    member_form = page.locator("#member-form")
    member_form.locator("input[name='org_id']").fill(str(org_id))
    member_form.locator("input[name='full_name']").fill("E2E Test Member")
    member_form.locator("button[type='submit']").click()

    member_result = page.locator("#member-result")
    expect(member_result).to_contain_text("E2E Test Member", timeout=10_000)
    expect(member_result).to_contain_text(str(org_id))


def test_non_admin_redirected_from_members_page(page: Page, provisioned):
    """Members admin page must redirect non-admin roles back to login."""
    base = provisioned["base_url"]

    # Log in as the QC inspector and try to hit /ui/members
    page.goto(f"{base}/ui/login")
    page.fill("input[name='username']", provisioned["qc_user"])
    page.fill("input[name='password']", provisioned["operator_password"])
    page.click("button[type='submit']")
    page.wait_for_url(lambda u: "/ui/login" not in u, timeout=10_000)

    page.goto(f"{base}/ui/members")
    expect(page).to_have_url(f"{base}/ui/login")
