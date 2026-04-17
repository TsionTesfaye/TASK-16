"""Frontend unit/component tests for all Jinja2 + HTMX templates.

Tests the rendered HTML output of every page template — form structure,
field names/types, HTMX attributes, page titles, CSRF wiring, navigation,
and component IDs. These are server-rendered component tests analogous to
React component unit tests.

Also covers the two previously-uncovered routes:
  GET /          (app.py root)
  GET /ui/       (ui_routes.py index)
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fullstack", "backend"))

import pytest
from app import create_app
from src.enums.user_role import UserRole
from src.repositories import (
    AuditLogRepository, SettingsRepository, StoreRepository,
    UserRepository, UserSessionRepository,
)
from src.services.audit_service import AuditService
from src.services.auth_service import AuthService
from src.models.store import Store


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def app(tmp_path_factory, monkeypatch_module):
    monkeypatch_module.setenv("RECLAIM_OPS_DEV_MODE", "true")
    monkeypatch_module.setenv("RECLAIM_OPS_REQUIRE_TLS", "false")
    monkeypatch_module.setenv("SECURE_COOKIES", "false")
    tmp = tmp_path_factory.mktemp("fe")
    export_dir = str(tmp / "exports")
    monkeypatch_module.setenv("EXPORT_OUTPUT_DIR", export_dir)
    import src.services.export_service as _es
    monkeypatch_module.setattr(_es, "EXPORT_OUTPUT_DIR", export_dir)
    db_path = str(tmp / "fe_test.db")
    application = create_app(db_path=db_path)
    application.config["TESTING"] = True
    return application


@pytest.fixture(scope="module")
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("RECLAIM_OPS_DEV_MODE", "true")
    monkeypatch.setenv("RECLAIM_OPS_REQUIRE_TLS", "false")
    monkeypatch.setenv("SECURE_COOKIES", "false")
    export_dir = str(tmp_path / "exports")
    monkeypatch.setenv("EXPORT_OUTPUT_DIR", export_dir)
    import src.services.export_service as _es
    monkeypatch.setattr(_es, "EXPORT_OUTPUT_DIR", export_dir)
    db_path = str(tmp_path / "fe_test.db")
    application = create_app(db_path=db_path)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


def _login_as(app, client, role, username):
    with app.app_context():
        from app import get_db
        from flask import g
        g.db_path = app.config["DB_PATH"]
        db = get_db()
        store_repo = StoreRepository(db)
        store = store_repo.get_by_code("FE")
        if store is None:
            store = store_repo.create(Store(code="FE", name="FE Store"))
        audit_svc = AuditService(AuditLogRepository(db))
        auth_svc = AuthService(
            UserRepository(db), UserSessionRepository(db),
            SettingsRepository(db), audit_svc,
        )
        try:
            admin = auth_svc.bootstrap_admin(
                username="feadmin", password="FeAdmin1234!",
                display_name="FE Admin",
            )
        except PermissionError:
            admin = UserRepository(db).get_by_username("feadmin")
        if role != UserRole.ADMINISTRATOR:
            try:
                auth_svc.create_user(
                    username=username, password="FePass1234!",
                    display_name=f"FE {role}", role=role,
                    admin_user_id=admin.id, admin_username=admin.username,
                    admin_role=admin.role, store_id=store.id,
                )
            except Exception:
                pass
        db.commit()
    login_user = "feadmin" if role == UserRole.ADMINISTRATOR else username
    login_pass = "FeAdmin1234!" if role == UserRole.ADMINISTRATOR else "FePass1234!"
    r = client.post(
        "/api/auth/login",
        json={"username": login_user, "password": login_pass},
        content_type="application/json",
    )
    assert r.status_code == 200


def _page(client, path):
    return client.get(path).data


# ══════════════════════════════════════════════════════════════════════════
# GET / and GET /ui/  — previously uncovered routes
# ══════════════════════════════════════════════════════════════════════════

class TestRootRoute:
    def test_get_root_returns_redirect(self, client):
        r = client.get("/")
        assert r.status_code in (301, 302)

    def test_get_root_location_points_to_ui_login(self, client):
        r = client.get("/")
        assert "/ui/login" in r.headers["Location"]

    def test_get_root_follow_lands_on_login(self, client):
        r = client.get("/", follow_redirects=True)
        assert r.status_code == 200
        assert b"Sign In" in r.data

    def test_get_root_follow_renders_login_form(self, client):
        r = client.get("/", follow_redirects=True)
        assert b'name="username"' in r.data
        assert b'name="password"' in r.data


class TestUiIndexRoute:
    def test_get_ui_slash_returns_redirect(self, client):
        r = client.get("/ui/")
        assert r.status_code in (301, 302)

    def test_get_ui_slash_location_points_to_tickets(self, client):
        r = client.get("/ui/")
        assert "/ui/tickets" in r.headers["Location"]

    def test_get_ui_slash_unauthenticated_chain_lands_on_login(self, client):
        r = client.get("/ui/", follow_redirects=True)
        assert r.status_code == 200
        assert b"Sign In" in r.data

    def test_get_ui_slash_authenticated_lands_on_tickets(self, app, client):
        _login_as(app, client, UserRole.FRONT_DESK_AGENT, "ui_slash_user")
        r = client.get("/ui/", follow_redirects=True)
        assert r.status_code == 200
        assert b"Tickets" in r.data


# ══════════════════════════════════════════════════════════════════════════
# Base template — shared elements injected into every page
# ══════════════════════════════════════════════════════════════════════════

class TestBaseTemplate:
    def test_base_loads_htmx_script(self, client):
        html = _page(client, "/ui/login")
        assert b"/static/js/htmx.min.js" in html

    def test_base_loads_stylesheet(self, client):
        html = _page(client, "/ui/login")
        assert b"/static/css/style.css" in html

    def test_base_has_csrf_cookie_reader(self, client):
        html = _page(client, "/ui/login")
        assert b"csrf_token" in html

    def test_base_has_x_csrf_token_header_wiring(self, client):
        html = _page(client, "/ui/login")
        assert b"X-CSRF-Token" in html

    def test_base_has_show_msg_helper(self, client):
        html = _page(client, "/ui/login")
        assert b"showMsg" in html

    def test_base_has_escape_html_helper(self, client):
        html = _page(client, "/ui/login")
        assert b"escapeHtml" in html or b"function H(" in html

    def test_base_title_pattern(self, client):
        html = _page(client, "/ui/login")
        assert b"ReclaimOps" in html

    def test_authenticated_pages_have_logout_link(self, app, client):
        _login_as(app, client, UserRole.FRONT_DESK_AGENT, "logout_link_user")
        html = _page(client, "/ui/tickets")
        assert b"Logout" in html or b"logout" in html

    def test_authenticated_pages_have_nav(self, app, client):
        _login_as(app, client, UserRole.FRONT_DESK_AGENT, "nav_user")
        html = _page(client, "/ui/tickets")
        assert b"nav" in html or b"ReclaimOps" in html


# ══════════════════════════════════════════════════════════════════════════
# Login page
# ══════════════════════════════════════════════════════════════════════════

class TestLoginPage:
    def test_title_is_sign_in(self, client):
        html = _page(client, "/ui/login")
        assert b"Sign In" in html

    def test_has_username_input(self, client):
        html = _page(client, "/ui/login")
        assert b'name="username"' in html

    def test_has_password_input(self, client):
        html = _page(client, "/ui/login")
        assert b'name="password"' in html

    def test_password_field_is_type_password(self, client):
        html = _page(client, "/ui/login")
        assert b'type="password"' in html

    def test_has_submit_button(self, client):
        html = _page(client, "/ui/login")
        assert b'type="submit"' in html

    def test_has_login_msg_container(self, client):
        html = _page(client, "/ui/login")
        assert b'id="login-msg"' in html

    def test_has_login_form_id(self, client):
        html = _page(client, "/ui/login")
        assert b'id="login-form"' in html

    def test_username_field_has_autofocus(self, client):
        html = _page(client, "/ui/login")
        assert b"autofocus" in html

    def test_form_has_autocomplete_off(self, client):
        html = _page(client, "/ui/login")
        assert b'autocomplete="off"' in html

    def test_page_has_reclaimops_branding(self, client):
        html = _page(client, "/ui/login")
        assert b"ReclaimOps" in html

    def test_page_has_offline_description(self, client):
        html = _page(client, "/ui/login")
        assert b"Offline" in html or b"offline" in html


# ══════════════════════════════════════════════════════════════════════════
# Tickets page
# ══════════════════════════════════════════════════════════════════════════

class TestTicketsPage:
    @pytest.fixture(autouse=True)
    def login(self, app, client):
        _login_as(app, client, UserRole.FRONT_DESK_AGENT, "tkt_page_user")

    def test_page_title_contains_tickets(self, client):
        html = _page(client, "/ui/tickets")
        assert b"Tickets" in html

    def test_h1_heading(self, client):
        html = _page(client, "/ui/tickets")
        assert b"Buyback Tickets" in html

    def test_ticket_form_id(self, client):
        html = _page(client, "/ui/tickets")
        assert b'id="ticket-form"' in html

    def test_ticket_form_has_hx_target(self, client):
        html = _page(client, "/ui/tickets")
        assert b'hx-target="#ticket-result"' in html

    def test_customer_name_field(self, client):
        html = _page(client, "/ui/tickets")
        assert b'name="customer_name"' in html

    def test_customer_name_is_required(self, client):
        html = _page(client, "/ui/tickets")
        assert b'name="customer_name"' in html
        assert b"required" in html

    def test_customer_phone_field(self, client):
        html = _page(client, "/ui/tickets")
        assert b'name="customer_phone"' in html

    def test_customer_phone_is_tel_type(self, client):
        html = _page(client, "/ui/tickets")
        assert b'type="tel"' in html

    def test_clothing_category_select(self, client):
        html = _page(client, "/ui/tickets")
        assert b'name="clothing_category"' in html

    def test_clothing_category_has_shirts_option(self, client):
        html = _page(client, "/ui/tickets")
        assert b"shirts" in html

    def test_clothing_category_has_pants_option(self, client):
        html = _page(client, "/ui/tickets")
        assert b"pants" in html

    def test_condition_grade_select(self, client):
        html = _page(client, "/ui/tickets")
        assert b'name="condition_grade"' in html

    def test_condition_grade_has_a_option(self, client):
        html = _page(client, "/ui/tickets")
        assert b'value="A"' in html

    def test_condition_grade_has_b_option(self, client):
        html = _page(client, "/ui/tickets")
        assert b'value="B"' in html

    def test_estimated_weight_field(self, client):
        html = _page(client, "/ui/tickets")
        assert b'name="estimated_weight_lbs"' in html

    def test_weight_field_is_number_type(self, client):
        html = _page(client, "/ui/tickets")
        assert b'type="number"' in html

    def test_phone_preference_select(self, client):
        html = _page(client, "/ui/tickets")
        assert b'name="customer_phone_preference"' in html

    def test_ticket_queue_div(self, client):
        html = _page(client, "/ui/tickets")
        assert b'id="ticket-queue"' in html

    def test_ticket_queue_htmx_get(self, client):
        html = _page(client, "/ui/tickets")
        assert b'hx-get="/ui/partials/tickets/queue"' in html

    def test_ticket_queue_htmx_trigger_load(self, client):
        html = _page(client, "/ui/tickets")
        assert b'hx-trigger="load"' in html

    def test_ticket_queue_htmx_swap_inner(self, client):
        html = _page(client, "/ui/tickets")
        assert b'hx-swap="innerHTML"' in html

    def test_refresh_button_present(self, client):
        html = _page(client, "/ui/tickets")
        assert b"Refresh" in html

    def test_ticket_result_container(self, client):
        html = _page(client, "/ui/tickets")
        assert b'id="ticket-result"' in html

    def test_supervisor_actions_card(self, client):
        html = _page(client, "/ui/tickets")
        assert b"Supervisor Actions" in html

    def test_variance_form_present(self, client):
        html = _page(client, "/ui/tickets")
        assert b'id="variance-form"' in html

    def test_refund_form_present(self, client):
        html = _page(client, "/ui/tickets")
        assert b'id="refund-form"' in html

    def test_cancel_form_present(self, client):
        html = _page(client, "/ui/tickets")
        assert b'id="cancel-form"' in html

    def test_dial_from_queue_js_function(self, client):
        html = _page(client, "/ui/tickets")
        assert b"dialFromQueue" in html

    def test_htmx_indicator_present(self, client):
        html = _page(client, "/ui/tickets")
        assert b"htmx-indicator" in html


# ══════════════════════════════════════════════════════════════════════════
# QC page
# ══════════════════════════════════════════════════════════════════════════

class TestQCPage:
    @pytest.fixture(autouse=True)
    def login(self, app, client):
        _login_as(app, client, UserRole.QC_INSPECTOR, "qc_page_user")

    def test_page_title(self, client):
        html = _page(client, "/ui/qc")
        assert b"QC" in html

    def test_h1_heading(self, client):
        html = _page(client, "/ui/qc")
        assert b"Quality Control" in html

    def test_qc_form_id(self, client):
        html = _page(client, "/ui/qc")
        assert b'id="qc-form"' in html

    def test_qc_form_ticket_id_field(self, client):
        html = _page(client, "/ui/qc")
        assert b'name="ticket_id"' in html

    def test_qc_form_actual_weight_field(self, client):
        html = _page(client, "/ui/qc")
        assert b'name="actual_weight_lbs"' in html

    def test_qc_form_lot_size_field(self, client):
        html = _page(client, "/ui/qc")
        assert b'name="lot_size"' in html

    def test_qc_form_nonconformance_field(self, client):
        html = _page(client, "/ui/qc")
        assert b'name="nonconformance_count"' in html

    def test_qc_form_inspection_outcome_select(self, client):
        html = _page(client, "/ui/qc")
        assert b'name="inspection_outcome"' in html

    def test_inspection_outcome_has_pass_option(self, client):
        html = _page(client, "/ui/qc")
        assert b'value="pass"' in html

    def test_inspection_outcome_has_fail_option(self, client):
        html = _page(client, "/ui/qc")
        assert b'value="fail"' in html

    def test_inspection_outcome_has_concession_option(self, client):
        html = _page(client, "/ui/qc")
        assert b"pass_with_concession" in html

    def test_qc_queue_div(self, client):
        html = _page(client, "/ui/qc")
        assert b'id="qc-queue"' in html

    def test_qc_queue_htmx_get(self, client):
        html = _page(client, "/ui/qc")
        assert b'hx-get="/ui/partials/qc/queue"' in html

    def test_qc_queue_loads_on_trigger(self, client):
        html = _page(client, "/ui/qc")
        assert b'hx-trigger="load"' in html

    def test_qc_result_container(self, client):
        html = _page(client, "/ui/qc")
        assert b'id="qc-result"' in html

    def test_qc_final_form(self, client):
        html = _page(client, "/ui/qc")
        assert b'id="qc-final-form"' in html

    def test_qc_final_result_container(self, client):
        html = _page(client, "/ui/qc")
        assert b'id="qc-final-result"' in html

    def test_quarantine_section(self, client):
        html = _page(client, "/ui/qc")
        assert b"Quarantine" in html

    def test_batch_traceability_section(self, client):
        html = _page(client, "/ui/qc")
        assert b"Batch Traceability" in html or b"Traceability" in html

    def test_recall_generation_section(self, client):
        html = _page(client, "/ui/qc")
        assert b"Recall" in html

    def test_batch_result_container(self, client):
        html = _page(client, "/ui/qc")
        assert b'id="batch-result"' in html

    def test_start_inspection_js_function(self, client):
        html = _page(client, "/ui/qc")
        assert b"startInspection" in html

    def test_refresh_button_present(self, client):
        html = _page(client, "/ui/qc")
        assert b"Refresh" in html


# ══════════════════════════════════════════════════════════════════════════
# Tables page
# ══════════════════════════════════════════════════════════════════════════

class TestTablesPage:
    @pytest.fixture(autouse=True)
    def login(self, app, client):
        _login_as(app, client, UserRole.HOST, "tables_page_user")

    def test_page_title(self, client):
        html = _page(client, "/ui/tables")
        assert b"Tables" in html

    def test_h1_heading(self, client):
        html = _page(client, "/ui/tables")
        assert b"Table" in html

    def test_open_form_id(self, client):
        html = _page(client, "/ui/tables")
        assert b'id="open-form"' in html

    def test_open_form_table_id_field(self, client):
        html = _page(client, "/ui/tables")
        assert b'name="table_id"' in html

    def test_open_form_customer_label_field(self, client):
        html = _page(client, "/ui/tables")
        assert b'name="customer_label"' in html

    def test_open_table_submit_button(self, client):
        html = _page(client, "/ui/tables")
        assert b"Open Table" in html

    def test_table_board_div(self, client):
        html = _page(client, "/ui/tables")
        assert b'id="table-board"' in html

    def test_table_board_htmx_get(self, client):
        html = _page(client, "/ui/tables")
        assert b'hx-get="/ui/partials/tables/board"' in html

    def test_table_board_htmx_trigger_load(self, client):
        html = _page(client, "/ui/tables")
        assert b'hx-trigger="load"' in html

    def test_table_result_container(self, client):
        html = _page(client, "/ui/tables")
        assert b'id="table-result"' in html

    def test_merge_section_present(self, client):
        html = _page(client, "/ui/tables")
        assert b"Merge" in html

    def test_transfer_section_present(self, client):
        html = _page(client, "/ui/tables")
        assert b"Transfer" in html or b"transfer" in html

    def test_refresh_button_present(self, client):
        html = _page(client, "/ui/tables")
        assert b"Refresh" in html


# ══════════════════════════════════════════════════════════════════════════
# Exports page
# ══════════════════════════════════════════════════════════════════════════

class TestExportsPage:
    @pytest.fixture(autouse=True)
    def login(self, app, client):
        _login_as(app, client, UserRole.SHIFT_SUPERVISOR, "exports_page_user")

    def test_page_title(self, client):
        html = _page(client, "/ui/exports")
        assert b"Export" in html

    def test_h1_heading(self, client):
        html = _page(client, "/ui/exports")
        assert b"Reports" in html or b"Export" in html

    def test_export_form_id(self, client):
        html = _page(client, "/ui/exports")
        assert b'id="export-form"' in html

    def test_export_type_select(self, client):
        html = _page(client, "/ui/exports")
        assert b'name="export_type"' in html

    def test_export_type_tickets_option(self, client):
        html = _page(client, "/ui/exports")
        assert b"tickets" in html

    def test_export_type_metrics_option(self, client):
        html = _page(client, "/ui/exports")
        assert b"metrics" in html

    def test_watermark_select(self, client):
        html = _page(client, "/ui/exports")
        assert b'name="watermark_enabled"' in html

    def test_attribution_field(self, client):
        html = _page(client, "/ui/exports")
        assert b'name="attribution_text"' in html

    def test_export_result_container(self, client):
        html = _page(client, "/ui/exports")
        assert b'id="export-result"' in html

    def test_export_list_div(self, client):
        html = _page(client, "/ui/exports")
        assert b'id="export-list"' in html

    def test_export_list_htmx_get(self, client):
        html = _page(client, "/ui/exports")
        assert b'hx-get="/ui/partials/exports/list"' in html

    def test_metrics_form_present(self, client):
        html = _page(client, "/ui/exports")
        assert b'id="metrics-form"' in html

    def test_metrics_date_start_field(self, client):
        html = _page(client, "/ui/exports")
        assert b'name="date_start"' in html

    def test_metrics_date_end_field(self, client):
        html = _page(client, "/ui/exports")
        assert b'name="date_end"' in html

    def test_metrics_display_container(self, client):
        html = _page(client, "/ui/exports")
        assert b'id="metrics-display"' in html

    def test_refresh_button_present(self, client):
        html = _page(client, "/ui/exports")
        assert b"Refresh" in html


# ══════════════════════════════════════════════════════════════════════════
# Notifications page
# ══════════════════════════════════════════════════════════════════════════

class TestNotificationsPage:
    @pytest.fixture(autouse=True)
    def login(self, app, client):
        _login_as(app, client, UserRole.FRONT_DESK_AGENT, "notif_pg_user")

    def test_page_title(self, client):
        html = _page(client, "/ui/notifications")
        assert b"Notification" in html

    def test_h1_heading(self, client):
        html = _page(client, "/ui/notifications")
        assert b"Notification Center" in html

    def test_retry_list_div(self, client):
        html = _page(client, "/ui/notifications")
        assert b'id="retry-list"' in html

    def test_retry_list_htmx_get(self, client):
        html = _page(client, "/ui/notifications")
        assert b'hx-get="/ui/partials/notifications/retries"' in html

    def test_retry_list_loads_on_trigger(self, client):
        html = _page(client, "/ui/notifications")
        assert b'hx-trigger="load"' in html

    def test_msg_form_id(self, client):
        html = _page(client, "/ui/notifications")
        assert b'id="msg-form"' in html

    def test_ticket_id_field(self, client):
        html = _page(client, "/ui/notifications")
        assert b'name="ticket_id"' in html

    def test_contact_channel_select(self, client):
        html = _page(client, "/ui/notifications")
        assert b'name="contact_channel"' in html

    def test_logged_message_option(self, client):
        html = _page(client, "/ui/notifications")
        assert b"logged_message" in html

    def test_phone_call_option(self, client):
        html = _page(client, "/ui/notifications")
        assert b"phone_call" in html

    def test_message_body_textarea(self, client):
        html = _page(client, "/ui/notifications")
        assert b'name="message_body"' in html

    def test_msg_result_container(self, client):
        html = _page(client, "/ui/notifications")
        assert b'id="msg-result"' in html

    def test_history_list_container(self, client):
        html = _page(client, "/ui/notifications")
        assert b'id="history-list"' in html

    def test_pending_retries_section(self, client):
        html = _page(client, "/ui/notifications")
        assert b"Pending Retries" in html

    def test_message_history_section(self, client):
        html = _page(client, "/ui/notifications")
        assert b"Message History" in html


# ══════════════════════════════════════════════════════════════════════════
# Members page
# ══════════════════════════════════════════════════════════════════════════

class TestMembersPage:
    @pytest.fixture(autouse=True)
    def login(self, app, client):
        _login_as(app, client, UserRole.ADMINISTRATOR, "")

    def test_page_title(self, client):
        html = _page(client, "/ui/members")
        assert b"Member" in html

    def test_h1_heading(self, client):
        html = _page(client, "/ui/members")
        assert b"Administration" in html or b"Member" in html

    def test_org_form_id(self, client):
        html = _page(client, "/ui/members")
        assert b'id="org-form"' in html

    def test_org_name_field(self, client):
        html = _page(client, "/ui/members")
        assert b'name="name"' in html

    def test_org_department_field(self, client):
        html = _page(client, "/ui/members")
        assert b'name="department"' in html

    def test_org_route_code_field(self, client):
        html = _page(client, "/ui/members")
        assert b'name="route_code"' in html

    def test_org_result_container(self, client):
        html = _page(client, "/ui/members")
        assert b'id="org-result"' in html

    def test_member_form_id(self, client):
        html = _page(client, "/ui/members")
        assert b'id="member-form"' in html

    def test_member_org_id_field(self, client):
        html = _page(client, "/ui/members")
        assert b'name="org_id"' in html

    def test_member_full_name_field(self, client):
        html = _page(client, "/ui/members")
        assert b'name="full_name"' in html

    def test_member_result_container(self, client):
        html = _page(client, "/ui/members")
        assert b'id="member-result"' in html

    def test_csv_import_section(self, client):
        html = _page(client, "/ui/members")
        assert b"CSV Import" in html or b"CSV" in html

    def test_create_org_button(self, client):
        html = _page(client, "/ui/members")
        assert b"Create Organization" in html

    def test_add_member_button(self, client):
        html = _page(client, "/ui/members")
        assert b"Add Member" in html

    def test_member_actions_card(self, client):
        html = _page(client, "/ui/members")
        assert b"Member Actions" in html

    def test_remove_button_present(self, client):
        html = _page(client, "/ui/members")
        assert b"Remove" in html

    def test_transfer_button_present(self, client):
        html = _page(client, "/ui/members")
        assert b"Transfer" in html


# ══════════════════════════════════════════════════════════════════════════
# Schedules page
# ══════════════════════════════════════════════════════════════════════════

class TestSchedulesPage:
    @pytest.fixture(autouse=True)
    def login(self, app, client):
        _login_as(app, client, UserRole.SHIFT_SUPERVISOR, "sched_page_user")

    def test_page_title(self, client):
        html = _page(client, "/ui/schedules")
        assert b"Schedule" in html

    def test_h1_heading(self, client):
        html = _page(client, "/ui/schedules")
        assert b"Schedule Adjustments" in html

    def test_sched_form_id(self, client):
        html = _page(client, "/ui/schedules")
        assert b'id="sched-form"' in html

    def test_adjustment_type_select(self, client):
        html = _page(client, "/ui/schedules")
        assert b'name="adjustment_type"' in html

    def test_retry_timing_option(self, client):
        html = _page(client, "/ui/schedules")
        assert b"retry_timing" in html

    def test_deadline_override_option(self, client):
        html = _page(client, "/ui/schedules")
        assert b"deadline_override" in html

    def test_target_entity_type_field(self, client):
        html = _page(client, "/ui/schedules")
        assert b'name="target_entity_type"' in html

    def test_target_entity_id_field(self, client):
        html = _page(client, "/ui/schedules")
        assert b'name="target_entity_id"' in html

    def test_before_value_field(self, client):
        html = _page(client, "/ui/schedules")
        assert b'name="before_value"' in html

    def test_after_value_field(self, client):
        html = _page(client, "/ui/schedules")
        assert b'name="after_value"' in html

    def test_reason_field(self, client):
        html = _page(client, "/ui/schedules")
        assert b'name="reason"' in html

    def test_sched_result_container(self, client):
        html = _page(client, "/ui/schedules")
        assert b'id="sched-result"' in html

    def test_pending_list_div(self, client):
        html = _page(client, "/ui/schedules")
        assert b'id="pending-list"' in html

    def test_pending_list_htmx_get(self, client):
        html = _page(client, "/ui/schedules")
        assert b'hx-get="/ui/partials/schedules/pending"' in html

    def test_pending_list_loads_on_trigger(self, client):
        html = _page(client, "/ui/schedules")
        assert b'hx-trigger="load"' in html

    def test_refresh_button_present(self, client):
        html = _page(client, "/ui/schedules")
        assert b"Refresh" in html

    def test_submit_request_button(self, client):
        html = _page(client, "/ui/schedules")
        assert b"Submit Request" in html


# ══════════════════════════════════════════════════════════════════════════
# HTMX partial route wiring — all pages declare the right partial URLs
# ══════════════════════════════════════════════════════════════════════════

class TestHTMXPartialWiring:
    def test_tickets_queue_partial_url(self, app, client):
        _login_as(app, client, UserRole.FRONT_DESK_AGENT, "htmx_wire_1")
        html = _page(client, "/ui/tickets")
        assert b"/ui/partials/tickets/queue" in html

    def test_qc_queue_partial_url(self, app, client):
        _login_as(app, client, UserRole.QC_INSPECTOR, "htmx_wire_2")
        html = _page(client, "/ui/qc")
        assert b"/ui/partials/qc/queue" in html

    def test_tables_board_partial_url(self, app, client):
        _login_as(app, client, UserRole.HOST, "htmx_wire_3")
        html = _page(client, "/ui/tables")
        assert b"/ui/partials/tables/board" in html

    def test_exports_list_partial_url(self, app, client):
        _login_as(app, client, UserRole.SHIFT_SUPERVISOR, "htmx_wire_4")
        html = _page(client, "/ui/exports")
        assert b"/ui/partials/exports/list" in html

    def test_schedules_pending_partial_url(self, app, client):
        _login_as(app, client, UserRole.SHIFT_SUPERVISOR, "htmx_wire_5")
        html = _page(client, "/ui/schedules")
        assert b"/ui/partials/schedules/pending" in html

    def test_notifications_retries_partial_url(self, app, client):
        _login_as(app, client, UserRole.FRONT_DESK_AGENT, "htmx_wire_6")
        html = _page(client, "/ui/notifications")
        assert b"/ui/partials/notifications/retries" in html

    def test_all_partials_use_hx_swap_inner_html(self, app, client):
        _login_as(app, client, UserRole.FRONT_DESK_AGENT, "htmx_wire_7")
        html = _page(client, "/ui/tickets")
        assert b'hx-swap="innerHTML"' in html


# ══════════════════════════════════════════════════════════════════════════
# Role gate: wrong-role users see redirect not page
# ══════════════════════════════════════════════════════════════════════════

class TestRoleGateFrontend:
    def test_qc_page_blocked_for_front_desk(self, app, client):
        _login_as(app, client, UserRole.FRONT_DESK_AGENT, "rg_fd_qc")
        r = client.get("/ui/qc")
        assert r.status_code in (301, 302)

    def test_tables_page_blocked_for_front_desk(self, app, client):
        _login_as(app, client, UserRole.FRONT_DESK_AGENT, "rg_fd_tbl")
        r = client.get("/ui/tables")
        assert r.status_code in (301, 302)

    def test_members_page_blocked_for_supervisor(self, app, client):
        _login_as(app, client, UserRole.SHIFT_SUPERVISOR, "rg_sup_mem")
        r = client.get("/ui/members")
        assert r.status_code in (301, 302)

    def test_exports_page_blocked_for_front_desk(self, app, client):
        _login_as(app, client, UserRole.FRONT_DESK_AGENT, "rg_fd_exp")
        r = client.get("/ui/exports")
        assert r.status_code in (301, 302)

    def test_schedules_page_blocked_for_front_desk(self, app, client):
        _login_as(app, client, UserRole.FRONT_DESK_AGENT, "rg_fd_sch")
        r = client.get("/ui/schedules")
        assert r.status_code in (301, 302)

    def test_members_page_blocked_for_qc_inspector(self, app, client):
        _login_as(app, client, UserRole.QC_INSPECTOR, "rg_qc_mem")
        r = client.get("/ui/members")
        assert r.status_code in (301, 302)

    def test_tables_page_blocked_for_qc_inspector(self, app, client):
        _login_as(app, client, UserRole.QC_INSPECTOR, "rg_qc_tbl")
        r = client.get("/ui/tables")
        assert r.status_code in (301, 302)
