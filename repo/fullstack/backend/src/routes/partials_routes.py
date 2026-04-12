"""HTMX partial routes — server-rendered HTML fragments for queue/board views.

Every endpoint returns an HTML fragment (not JSON) suitable for hx-swap.
All endpoints enforce the same auth + store isolation as the JSON API,
plus role-based access control (least-privilege).

Role policy for read partials:
  ticket queue     — front_desk_agent, qc_inspector, shift_supervisor,
                     operations_manager, administrator
  qc queue         — qc_inspector, shift_supervisor, operations_manager,
                     administrator
  table board      — host, shift_supervisor, operations_manager, administrator
  exports list     — shift_supervisor, operations_manager, administrator
  schedules pending — shift_supervisor, operations_manager, administrator
  notifications    — front_desk_agent, shift_supervisor, operations_manager,
                     administrator
"""
import json
import logging
from typing import Set

from flask import Blueprint, g, render_template_string, request as flask_request

from .helpers import (
    _repos, error_response, get_auth_service,
    require_auth, session_store_id,
)
from ..enums.user_role import UserRole
from ..security.session_cookie import verify_session_cookie

logger = logging.getLogger(__name__)

partials_bp = Blueprint("partials", __name__, url_prefix="/ui/partials")

# Role sets for partial read endpoints
_TICKET_ROLES: Set[str] = {
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
_EXPORT_ROLES: Set[str] = {
    UserRole.SHIFT_SUPERVISOR, UserRole.OPERATIONS_MANAGER,
    UserRole.ADMINISTRATOR,
}
_SCHEDULE_ROLES: Set[str] = {
    UserRole.SHIFT_SUPERVISOR, UserRole.OPERATIONS_MANAGER,
    UserRole.ADMINISTRATOR,
}
_NOTIFICATION_ROLES: Set[str] = {
    UserRole.FRONT_DESK_AGENT, UserRole.SHIFT_SUPERVISOR,
    UserRole.OPERATIONS_MANAGER, UserRole.ADMINISTRATOR,
}


def _require_role(allowed: Set[str]):
    """Return an (html_error, 403) tuple if the current user lacks an
    allowed role, else return None."""
    if g.current_user.role not in allowed:
        return _html_error("Access denied: insufficient role"), 403
    return None


def _html_error(message: str) -> str:
    from markupsafe import escape
    return f'<div class="msg msg-error">{escape(message)}</div>'


def _store_id_for_actor():
    """Return the actor's store_id with strict role-based resolution.

    - Non-admin users ALWAYS use their session-bound store_id.
      Query-param override is never honored.  If a non-admin somehow
      has store_id=NULL (legacy data), the request is rejected.
    - Administrators may supply store_id via query param because they
      operate across stores.
    """
    from ..enums.user_role import UserRole
    user = g.current_user
    if user.role != UserRole.ADMINISTRATOR:
        if not user.store_id:
            return None  # caller checks and returns error
        return user.store_id
    # Admin — honor query param
    sid = flask_request.args.get("store_id")
    if sid:
        try:
            return int(sid)
        except (TypeError, ValueError):
            return None
    # Admin with a pinned store (optional)
    return user.store_id


# ────────────────────────────────────────────────
# TICKET QUEUE
# ────────────────────────────────────────────────

TICKET_QUEUE_TEMPLATE = """
{% if not tickets %}
<div class="msg msg-info">No tickets found.</div>
{% else %}
<table>
<thead><tr>
  <th>ID</th><th>Customer</th><th>Category</th><th>Status</th>
  <th>Est. Payout</th><th>Final</th><th>Actions</th>
</tr></thead>
<tbody>
{% for t in tickets %}
<tr id="ticket-row-{{ t.id }}">
  <td><strong>{{ t.id }}</strong></td>
  <td>{{ t.customer_name }}</td>
  <td>{{ t.clothing_category }}</td>
  <td><span class="badge badge-{{ t.status|replace('_','-') }}">{{ t.status }}</span></td>
  <td>${{ "%.2f"|format(t.estimated_payout or 0) }}</td>
  <td>{{ "$%.2f"|format(t.final_payout) if t.final_payout is not none else "—" }}</td>
  <td style="white-space:nowrap">
    {% if t.status == 'intake_open' %}
      <button class="btn btn-primary btn-sm"
              hx-post="/ui/partials/tickets/{{ t.id }}/submit-qc"
              hx-target="#ticket-queue" hx-swap="innerHTML"
              hx-confirm="Submit ticket #{{ t.id }} for QC?">QC</button>
      <button class="btn btn-sm" style="background:#6b7280;color:#fff"
              hx-post="/ui/partials/tickets/{{ t.id }}/cancel"
              hx-target="#ticket-queue" hx-swap="innerHTML"
              hx-confirm="Cancel ticket #{{ t.id }}?">Cancel</button>
    {% elif t.status == 'awaiting_qc' %}
      <span class="text-muted text-sm">Awaiting QC</span>
    {% elif t.status == 'variance_pending_confirmation' %}
      <button class="btn btn-warn btn-sm"
              onclick="confirmVarianceFromQueue({{ t.id }})">Confirm Variance</button>
    {% elif t.status == 'variance_pending_supervisor' %}
      <span class="badge badge-pending">Needs Supervisor</span>
    {% elif t.status == 'completed' %}
      {% if t.customer_phone_last4 %}
      <span id="dial-{{ t.id }}"
            hx-post="/ui/partials/tickets/{{ t.id }}/dial"
            hx-target="#dial-{{ t.id }}" hx-swap="outerHTML"
            hx-trigger="click" class="btn btn-sm" style="background:#16a34a;color:#fff;cursor:pointer">Dial</span>
      {% endif %}
      <button class="btn btn-danger btn-sm"
              hx-post="/ui/partials/tickets/{{ t.id }}/initiate-refund"
              hx-target="#ticket-queue" hx-swap="innerHTML"
              hx-confirm="Initiate refund for ticket #{{ t.id }}?">Refund</button>
    {% elif t.status == 'refund_pending_supervisor' %}
      <span class="badge badge-pending">Refund Pending</span>
    {% endif %}
  </td>
</tr>
{% endfor %}
</tbody>
</table>
{% endif %}
"""

@partials_bp.route("/tickets/queue")
@require_auth
def ticket_queue():
    denied = _require_role(_TICKET_ROLES)
    if denied:
        return denied
    store_id = _store_id_for_actor()
    if not store_id:
        return _html_error("No store context"), 403
    r = _repos()
    tickets = r["ticket"].list_by_store(store_id)
    return render_template_string(TICKET_QUEUE_TEMPLATE, tickets=tickets)


# Thin POST handlers: each returns the refreshed queue fragment
@partials_bp.route("/tickets/<int:ticket_id>/submit-qc", methods=["POST"])
@require_auth
def partial_submit_qc(ticket_id):
    denied = _require_role(_TICKET_ROLES)
    if denied:
        return denied
    from .helpers import get_ticket_service
    try:
        svc = get_ticket_service()
        svc.submit_for_qc(
            ticket_id, g.current_user.id, g.current_user.username,
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
        )
    except (PermissionError, ValueError) as e:
        return _html_error(str(e))
    return ticket_queue()


@partials_bp.route("/tickets/<int:ticket_id>/cancel", methods=["POST"])
@require_auth
def partial_cancel_ticket(ticket_id):
    denied = _require_role(_TICKET_ROLES)
    if denied:
        return denied
    from .helpers import get_ticket_service
    reason = (flask_request.form.get("reason")
              or (flask_request.get_json(silent=True) or {}).get("reason")
              or "Cancelled from queue")
    try:
        svc = get_ticket_service()
        svc.cancel_ticket(
            ticket_id=ticket_id,
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
            reason=reason,
            actor_store_id=g.current_user.store_id,
        )
    except (PermissionError, ValueError) as e:
        return _html_error(str(e))
    return ticket_queue()


@partials_bp.route("/tickets/<int:ticket_id>/initiate-refund", methods=["POST"])
@require_auth
def partial_initiate_refund(ticket_id):
    denied = _require_role(_TICKET_ROLES)
    if denied:
        return denied
    from .helpers import get_ticket_service
    try:
        svc = get_ticket_service()
        svc.initiate_refund(
            ticket_id=ticket_id,
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
            actor_store_id=g.current_user.store_id,
        )
    except (PermissionError, ValueError) as e:
        return _html_error(str(e))
    return ticket_queue()


@partials_bp.route("/tickets/<int:ticket_id>/dial", methods=["POST"])
@require_auth
def partial_dial(ticket_id):
    """Decrypt phone, log audit, and immediately trigger the workstation
    dialer via an auto-executing tel: redirect. True one-tap: the
    operator clicks the Dial button once, HTMX posts here, the response
    includes a script that opens the tel: URI — no second click."""
    denied = _require_role(_TICKET_ROLES)
    if denied:
        return denied
    from .helpers import get_ticket_service
    from markupsafe import escape
    try:
        svc = get_ticket_service()
        result = svc.get_ticket_phone_for_dial(
            ticket_id=ticket_id,
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
            actor_store_id=g.current_user.store_id,
        )
    except PermissionError as e:
        return _html_error(str(e))
    except ValueError as e:
        return _html_error(str(e))
    phone = result["phone"]
    last4 = result.get("last4", "")
    label = f"••••{escape(last4)}" if last4 else "number"
    # Auto-trigger the OS dialer immediately, then show confirmation.
    return (
        f'<span class="text-sm text-muted">Dialing {label}…</span>'
        f'<script>window.location="tel:{escape(phone)}";</script>'
    )


# -- Export approve/reject/execute partials --

@partials_bp.route("/exports/<int:request_id>/approve", methods=["POST"])
@require_auth
def partial_export_approve(request_id):
    denied = _require_role(_EXPORT_ROLES)
    if denied:
        return denied
    from .helpers import get_export_service
    password = (flask_request.headers.get("HX-Prompt")
                or flask_request.form.get("password")
                or (flask_request.get_json(silent=True) or {}).get("password"))
    if not password:
        return _html_error("Password is required for approval")
    try:
        svc = get_export_service()
        svc.approve_export(
            request_id=request_id,
            approver_user_id=g.current_user.id,
            approver_username=g.current_user.username,
            approver_role=g.current_user.role,
            password=password,
            approver_store_id=g.current_user.store_id,
        )
    except (PermissionError, ValueError) as e:
        return _html_error(str(e))
    return exports_list()


@partials_bp.route("/exports/<int:request_id>/reject", methods=["POST"])
@require_auth
def partial_export_reject(request_id):
    denied = _require_role(_EXPORT_ROLES)
    if denied:
        return denied
    from .helpers import get_export_service
    reason = (flask_request.form.get("reason")
              or (flask_request.get_json(silent=True) or {}).get("reason")
              or "Rejected")
    try:
        svc = get_export_service()
        svc.reject_export(
            request_id=request_id,
            approver_user_id=g.current_user.id,
            approver_username=g.current_user.username,
            approver_role=g.current_user.role,
            reason=reason,
            approver_store_id=g.current_user.store_id,
        )
    except (PermissionError, ValueError) as e:
        return _html_error(str(e))
    return exports_list()


@partials_bp.route("/exports/<int:request_id>/execute", methods=["POST"])
@require_auth
def partial_export_execute(request_id):
    denied = _require_role(_EXPORT_ROLES)
    if denied:
        return denied
    from .helpers import get_export_service
    try:
        svc = get_export_service()
        svc.execute_export(
            request_id=request_id,
            user_id=g.current_user.id,
            username=g.current_user.username,
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
        )
    except (PermissionError, ValueError) as e:
        return _html_error(str(e))
    return exports_list()


# -- Schedule approve/reject partials --

@partials_bp.route("/schedules/<int:request_id>/approve", methods=["POST"])
@require_auth
def partial_schedule_approve(request_id):
    denied = _require_role(_SCHEDULE_ROLES)
    if denied:
        return denied
    from .helpers import get_schedule_service
    password = (flask_request.headers.get("HX-Prompt")
                or flask_request.form.get("password")
                or (flask_request.get_json(silent=True) or {}).get("password"))
    if not password:
        return _html_error("Password is required for approval")
    try:
        svc = get_schedule_service()
        svc.approve_adjustment(
            request_id=request_id,
            approver_user_id=g.current_user.id,
            approver_username=g.current_user.username,
            approver_role=g.current_user.role,
            password=password,
            approver_store_id=g.current_user.store_id,
        )
    except (PermissionError, ValueError) as e:
        return _html_error(str(e))
    return schedules_pending()


@partials_bp.route("/schedules/<int:request_id>/reject", methods=["POST"])
@require_auth
def partial_schedule_reject(request_id):
    denied = _require_role(_SCHEDULE_ROLES)
    if denied:
        return denied
    from .helpers import get_schedule_service
    reason = (flask_request.form.get("reason")
              or (flask_request.get_json(silent=True) or {}).get("reason")
              or "Rejected")
    try:
        svc = get_schedule_service()
        svc.reject_adjustment(
            request_id=request_id,
            approver_user_id=g.current_user.id,
            approver_username=g.current_user.username,
            approver_role=g.current_user.role,
            reason=reason,
            approver_store_id=g.current_user.store_id,
        )
    except (PermissionError, ValueError) as e:
        return _html_error(str(e))
    return schedules_pending()


# ────────────────────────────────────────────────
# QC QUEUE — tickets awaiting QC + quarantines
# ────────────────────────────────────────────────

QC_QUEUE_TEMPLATE = """
<h4 style="margin:.5rem 0">Tickets Awaiting QC ({{ awaiting|length }})</h4>
{% if not awaiting %}
<div class="msg msg-info">No tickets awaiting QC.</div>
{% else %}
<table>
<thead><tr><th>Ticket</th><th>Customer</th><th>Est. Weight</th><th>Est. Payout</th><th>Action</th></tr></thead>
<tbody>
{% for t in awaiting %}
<tr>
  <td><strong>#{{ t.id }}</strong></td>
  <td>{{ t.customer_name }}</td>
  <td>{{ t.estimated_weight_lbs }} lbs</td>
  <td>${{ "%.2f"|format(t.estimated_payout or 0) }}</td>
  <td><button class="btn btn-primary btn-sm"
        onclick="startInspection({{ t.id }})">Inspect</button></td>
</tr>
{% endfor %}
</tbody>
</table>
{% endif %}

<h4 style="margin:.75rem 0 .5rem">Unresolved Quarantines ({{ quarantines|length }})</h4>
{% if not quarantines %}
<div class="msg msg-info">No unresolved quarantines.</div>
{% else %}
<table>
<thead><tr><th>QR ID</th><th>Ticket</th><th>Batch</th><th>Created</th><th>Action</th></tr></thead>
<tbody>
{% for q in quarantines %}
<tr>
  <td><strong>#{{ q.id }}</strong></td>
  <td>#{{ q.ticket_id }}</td>
  <td>#{{ q.batch_id }}</td>
  <td class="text-sm text-muted">{{ q.created_at }}</td>
  <td><button class="btn btn-warn btn-sm"
        onclick="startResolve({{ q.id }})">Resolve</button></td>
</tr>
{% endfor %}
</tbody>
</table>
{% endif %}
"""

@partials_bp.route("/qc/queue")
@require_auth
def qc_queue():
    denied = _require_role(_QC_ROLES)
    if denied:
        return denied
    store_id = _store_id_for_actor()
    if not store_id:
        return _html_error("No store context"), 403
    r = _repos()
    awaiting = r["ticket"].list_by_store(store_id, status="awaiting_qc")
    all_quarantines = r["quarantine"].list_unresolved()
    # Filter to the actor's store by joining through the batch
    quarantines = []
    for q in all_quarantines:
        batch = r["batch"].get_by_id(q.batch_id)
        if batch and batch.store_id == store_id:
            quarantines.append(q)
    return render_template_string(QC_QUEUE_TEMPLATE, awaiting=awaiting, quarantines=quarantines)


# ────────────────────────────────────────────────
# TABLE SESSION BOARD
# ────────────────────────────────────────────────

TABLE_BOARD_TEMPLATE = """
{% if not sessions %}
<div class="msg msg-info">No active table sessions.</div>
{% else %}
<div class="table-grid">
{% for s in sessions %}
<div class="table-card {{ s.current_state }}">
  <div style="font-weight:700">Session #{{ s.id }}</div>
  <div class="text-sm">Table #{{ s.table_id }}</div>
  <span class="badge badge-{{ s.current_state }}">{{ s.current_state }}</span>
  {% if s.current_customer_label %}<div class="text-sm mt-1">{{ s.current_customer_label }}</div>{% endif %}
  <div style="margin-top:.5rem">
    {% if s.current_state == 'occupied' %}
      <button class="btn btn-warn btn-sm"
              hx-post="/ui/partials/tables/{{ s.id }}/transition"
              hx-vals='{"target_state":"pre_checkout"}'
              hx-target="#table-board" hx-swap="innerHTML">Pre-Checkout</button>
    {% elif s.current_state == 'pre_checkout' %}
      <button class="btn btn-sm" style="background:#6b7280;color:#fff"
              hx-post="/ui/partials/tables/{{ s.id }}/transition"
              hx-vals='{"target_state":"cleared"}'
              hx-target="#table-board" hx-swap="innerHTML">Clear</button>
    {% elif s.current_state == 'cleared' %}
      <button class="btn btn-success btn-sm"
              hx-post="/ui/partials/tables/{{ s.id }}/transition"
              hx-vals='{"target_state":"available"}'
              hx-target="#table-board" hx-swap="innerHTML">Release</button>
    {% endif %}
  </div>
</div>
{% endfor %}
</div>
{% endif %}
"""

@partials_bp.route("/tables/board")
@require_auth
def table_board():
    denied = _require_role(_TABLE_ROLES)
    if denied:
        return denied
    store_id = _store_id_for_actor()
    if not store_id:
        return _html_error("No store context"), 403
    r = _repos()
    sessions = r["table_session"].list_by_store(store_id)
    return render_template_string(TABLE_BOARD_TEMPLATE, sessions=sessions)


@partials_bp.route("/tables/<int:session_id>/transition", methods=["POST"])
@require_auth
def partial_table_transition(session_id):
    denied = _require_role(_TABLE_ROLES)
    if denied:
        return denied
    from .helpers import get_table_service
    target = flask_request.form.get("target_state") or (flask_request.get_json(silent=True) or {}).get("target_state")
    if not target:
        return _html_error("target_state required")
    try:
        svc = get_table_service()
        svc.transition_table(
            session_id=session_id,
            target_state=target,
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
            actor_store_id=g.current_user.store_id,
        )
    except (PermissionError, ValueError) as e:
        return _html_error(str(e))
    return table_board()


# ────────────────────────────────────────────────
# EXPORTS PENDING LIST
# ────────────────────────────────────────────────

EXPORTS_PENDING_TEMPLATE = """
{% if not requests %}
<div class="msg msg-info">No pending export requests.</div>
{% else %}
<table>
<thead><tr><th>ID</th><th>Type</th><th>Status</th><th>Requested</th><th>Actions</th></tr></thead>
<tbody>
{% for r in requests %}
<tr>
  <td><strong>#{{ r.id }}</strong></td>
  <td>{{ r.export_type }}</td>
  <td><span class="badge badge-{{ r.status }}">{{ r.status }}</span></td>
  <td class="text-sm text-muted">{{ r.created_at }}</td>
  <td>
    {% if r.status == 'pending' %}
      <button class="btn btn-success btn-sm"
              hx-post="/ui/partials/exports/{{ r.id }}/approve"
              hx-target="#export-list" hx-swap="innerHTML"
              hx-prompt="Enter your password to approve export #{{ r.id }}:">Approve</button>
      <button class="btn btn-danger btn-sm"
              hx-post="/ui/partials/exports/{{ r.id }}/reject"
              hx-target="#export-list" hx-swap="innerHTML"
              hx-confirm="Reject export #{{ r.id }}?">Reject</button>
    {% elif r.status == 'approved' %}
      <button class="btn btn-primary btn-sm"
              hx-post="/ui/partials/exports/{{ r.id }}/execute"
              hx-target="#export-list" hx-swap="innerHTML"
              hx-confirm="Execute export #{{ r.id }}? This is one-time only.">Execute</button>
    {% elif r.status == 'completed' %}
      <span class="text-muted text-sm">Done {{ r.completed_at or '' }}</span>
    {% endif %}
  </td>
</tr>
{% endfor %}
</tbody>
</table>
{% endif %}
"""

@partials_bp.route("/exports/list")
@require_auth
def exports_list():
    denied = _require_role(_EXPORT_ROLES)
    if denied:
        return denied
    store_id = _store_id_for_actor()
    if not store_id:
        return _html_error("No store context"), 403
    r = _repos()
    requests = r["export"].list_by_store(store_id)
    return render_template_string(EXPORTS_PENDING_TEMPLATE, requests=requests)


# ────────────────────────────────────────────────
# SCHEDULES PENDING LIST
# ────────────────────────────────────────────────

SCHEDULES_PENDING_TEMPLATE = """
{% if not items %}
<div class="msg msg-info">No pending schedule adjustments.</div>
{% else %}
<table>
<thead><tr><th>ID</th><th>Type</th><th>Before</th><th>After</th><th>Reason</th><th>Actions</th></tr></thead>
<tbody>
{% for s in items %}
<tr>
  <td><strong>#{{ s.id }}</strong></td>
  <td>{{ s.adjustment_type }}</td>
  <td>{{ s.before_value }}</td>
  <td>{{ s.after_value }}</td>
  <td class="text-sm">{{ s.reason }}</td>
  <td>
    <button class="btn btn-success btn-sm"
            hx-post="/ui/partials/schedules/{{ s.id }}/approve"
            hx-target="#pending-list" hx-swap="innerHTML"
            hx-prompt="Enter your password to approve adjustment #{{ s.id }}:">Approve</button>
    <button class="btn btn-danger btn-sm"
            hx-post="/ui/partials/schedules/{{ s.id }}/reject"
            hx-target="#pending-list" hx-swap="innerHTML"
            hx-confirm="Reject adjustment #{{ s.id }}?">Reject</button>
  </td>
</tr>
{% endfor %}
</tbody>
</table>
{% endif %}
"""

@partials_bp.route("/schedules/pending")
@require_auth
def schedules_pending():
    denied = _require_role(_SCHEDULE_ROLES)
    if denied:
        return denied
    from .helpers import get_schedule_service
    try:
        svc = get_schedule_service()
        items = svc.list_pending(
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
        )
    except PermissionError:
        return _html_error("Insufficient role to view schedule adjustments")
    return render_template_string(SCHEDULES_PENDING_TEMPLATE, items=items)


# ────────────────────────────────────────────────
# NOTIFICATION MESSAGE HISTORY
# ────────────────────────────────────────────────

MESSAGES_TEMPLATE = """
{% if has_phone %}
<div style="margin-bottom:.5rem">
  <span id="notif-dial-{{ ticket_id }}"
        hx-post="/ui/partials/tickets/{{ ticket_id }}/dial"
        hx-target="#notif-dial-{{ ticket_id }}" hx-swap="outerHTML"
        hx-trigger="click"
        class="btn btn-sm" style="background:#16a34a;color:#fff;cursor:pointer">Dial Customer</span>
</div>
{% endif %}
{% if not messages %}
<div class="msg msg-info">No messages for this ticket.</div>
{% else %}
<table>
<thead><tr><th>ID</th><th>Channel</th><th>Body</th><th>Call Status</th><th>Retry</th><th>Time</th></tr></thead>
<tbody>
{% for m in messages %}
<tr>
  <td>{{ m.id }}</td>
  <td>{{ m.contact_channel }}</td>
  <td>{{ m.message_body[:80] }}{{ '...' if m.message_body|length > 80 else '' }}</td>
  <td>{{ m.call_attempt_status or '—' }}</td>
  <td>{{ m.retry_at or '—' }}</td>
  <td class="text-sm text-muted">{{ m.created_at }}</td>
</tr>
{% endfor %}
</tbody>
</table>
{% endif %}
"""

@partials_bp.route("/notifications/messages/<int:ticket_id>")
@require_auth
def notification_messages(ticket_id):
    denied = _require_role(_NOTIFICATION_ROLES)
    if denied:
        return denied
    from .helpers import get_notification_service
    try:
        svc = get_notification_service()
        messages = svc.get_ticket_messages(
            ticket_id,
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
        )
    except (PermissionError, ValueError) as e:
        return _html_error(str(e))
    # Check if ticket has a phone number for the dial action
    r = _repos()
    ticket = r["ticket"].get_by_id(ticket_id)
    has_phone = bool(ticket and ticket.customer_phone_last4)
    return render_template_string(
        MESSAGES_TEMPLATE,
        messages=messages,
        ticket_id=ticket_id,
        has_phone=has_phone,
    )


# ────────────────────────────────────────────────
# NOTIFICATION PENDING RETRIES (with dial action)
# ────────────────────────────────────────────────

RETRIES_TEMPLATE = """
{% if not retries %}
<div class="msg msg-info">No pending retries.</div>
{% else %}
<table>
<thead><tr><th>ID</th><th>Ticket</th><th>Retry At</th><th>Actions</th></tr></thead>
<tbody>
{% for m in retries %}
<tr>
  <td>{{ m.id }}</td>
  <td>#{{ m.ticket_id }}</td>
  <td>{{ m.retry_at }}</td>
  <td style="white-space:nowrap">
    {% if m.has_phone %}
    <span id="retry-dial-{{ m.id }}"
          hx-post="/ui/partials/tickets/{{ m.ticket_id }}/dial"
          hx-target="#retry-dial-{{ m.id }}" hx-swap="outerHTML"
          hx-trigger="click"
          class="btn btn-sm" style="background:#16a34a;color:#fff;cursor:pointer">Dial</span>
    {% endif %}
    <button class="btn btn-sm btn-primary"
            hx-get="/ui/partials/notifications/messages/{{ m.ticket_id }}"
            hx-target="#history-list" hx-swap="innerHTML">History</button>
  </td>
</tr>
{% endfor %}
</tbody>
</table>
{% endif %}
"""

@partials_bp.route("/notifications/retries")
@require_auth
def notification_retries():
    denied = _require_role(_NOTIFICATION_ROLES)
    if denied:
        return denied
    from .helpers import get_notification_service
    try:
        svc = get_notification_service()
        retries = svc.get_pending_retries(
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
        )
    except PermissionError as e:
        return _html_error(str(e))

    # Enrich each retry with phone availability for the dial button
    r = _repos()
    enriched = []
    for m in retries:
        ticket = r["ticket"].get_by_id(m.ticket_id)
        m.has_phone = bool(ticket and ticket.customer_phone_last4)
        enriched.append(m)

    return render_template_string(RETRIES_TEMPLATE, retries=enriched)
