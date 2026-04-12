"""UI page routes — serves Jinja2 templates for all sections.

Every page except `/ui/login` requires a valid session AND an
appropriate role. We re-use the same `validate_session` path that the
API decorator uses (server-side nonce check, expiry, frozen accounts),
so a user who is logged out of the API is logged out of the UI by
construction.

Role policy (least-privilege):
  tickets      — front_desk_agent, qc_inspector, shift_supervisor,
                 operations_manager, administrator
  qc           — qc_inspector, shift_supervisor, operations_manager,
                 administrator
  tables       — host, shift_supervisor, operations_manager, administrator
  notifications — front_desk_agent, shift_supervisor, operations_manager,
                  administrator
  members      — administrator
  exports      — shift_supervisor, operations_manager, administrator
  schedules    — shift_supervisor, operations_manager, administrator
"""
import logging
from typing import Optional, Set

from flask import Blueprint, redirect, render_template, request

from ..enums.user_role import UserRole
from ..security.session_cookie import verify_session_cookie
from .helpers import get_auth_service

logger = logging.getLogger(__name__)

ui_bp = Blueprint("ui", __name__, url_prefix="/ui")

# Role sets for each page group
_TICKETS_ROLES: Set[str] = {
    UserRole.FRONT_DESK_AGENT, UserRole.QC_INSPECTOR,
    UserRole.SHIFT_SUPERVISOR, UserRole.OPERATIONS_MANAGER,
    UserRole.ADMINISTRATOR,
}
_QC_ROLES: Set[str] = {
    UserRole.QC_INSPECTOR, UserRole.SHIFT_SUPERVISOR,
    UserRole.OPERATIONS_MANAGER, UserRole.ADMINISTRATOR,
}
_TABLE_ROLES: Set[str] = {
    UserRole.HOST, UserRole.SHIFT_SUPERVISOR,
    UserRole.OPERATIONS_MANAGER, UserRole.ADMINISTRATOR,
}
_NOTIFICATION_ROLES: Set[str] = {
    UserRole.FRONT_DESK_AGENT, UserRole.SHIFT_SUPERVISOR,
    UserRole.OPERATIONS_MANAGER, UserRole.ADMINISTRATOR,
}
_MEMBER_ROLES: Set[str] = {UserRole.ADMINISTRATOR}
_EXPORT_ROLES: Set[str] = {
    UserRole.SHIFT_SUPERVISOR, UserRole.OPERATIONS_MANAGER,
    UserRole.ADMINISTRATOR,
}
_SCHEDULE_ROLES: Set[str] = {
    UserRole.SHIFT_SUPERVISOR, UserRole.OPERATIONS_MANAGER,
    UserRole.ADMINISTRATOR,
}


def _get_authenticated_user():
    """Validate session and return the User object, or None."""
    raw_cookie = request.cookies.get("session_nonce")
    if not raw_cookie:
        return None
    nonce = verify_session_cookie(raw_cookie)
    if nonce is None:
        logger.debug("UI auth: session cookie signature invalid")
        return None
    try:
        result = get_auth_service().validate_session(nonce)
        return result["user"]
    except Exception as e:
        logger.debug("UI auth check failed: %s", e)
        return None


def _gated(template: str, allowed_roles: Optional[Set[str]] = None):
    """Render `template` if the request is authenticated and authorized,
    else redirect to the login page.

    When `allowed_roles` is provided, the user's role must be in the set
    or the request is redirected to login (the user sees the generic
    'you are not logged in' page rather than a raw 403 — the page shell
    does not contain sensitive data itself, and the partials enforce
    their own role gates independently).
    """
    user = _get_authenticated_user()
    if not user:
        return redirect("/ui/login")
    if allowed_roles and user.role not in allowed_roles:
        return redirect("/ui/login")
    return render_template(template)


@ui_bp.route("/login")
def login_page():
    return render_template("login.html")


@ui_bp.route("/")
def index():
    return redirect("/ui/tickets")


@ui_bp.route("/tickets")
def tickets_page():
    return _gated("tickets/index.html", _TICKETS_ROLES)


@ui_bp.route("/qc")
def qc_page():
    return _gated("qc/index.html", _QC_ROLES)


@ui_bp.route("/tables")
def tables_page():
    return _gated("tables/index.html", _TABLE_ROLES)


@ui_bp.route("/notifications")
def notifications_page():
    return _gated("notifications/index.html", _NOTIFICATION_ROLES)


@ui_bp.route("/members")
def members_page():
    return _gated("members/index.html", _MEMBER_ROLES)


@ui_bp.route("/exports")
def exports_page():
    return _gated("exports/index.html", _EXPORT_ROLES)


@ui_bp.route("/schedules")
def schedules_page():
    return _gated("schedules/index.html", _SCHEDULE_ROLES)
