"""Ticket lifecycle routes — intake, QC handoff, variance, refund, cancel."""
from flask import Blueprint, g

from .helpers import (
    error_response, get_json_body, get_ticket_service,
    require_auth, require_fields, serialize, success_response,
)

ticket_bp = Blueprint("tickets", __name__, url_prefix="/api/tickets")


@ticket_bp.route("", methods=["POST"])
@require_auth
def create_ticket():
    data = get_json_body()
    err = require_fields(data, "customer_name", "clothing_category",
                         "condition_grade", "estimated_weight_lbs")
    if err:
        return err
    # Derive store from the authenticated session — never trust a
    # client-supplied store_id for non-admin users. Admins may pass it
    # explicitly because they have no pinned store.
    if g.current_user.role == "administrator":
        store_id = int(data["store_id"]) if data.get("store_id") else None
        if store_id is None:
            return error_response(400, "Administrators must supply store_id")
    else:
        store_id = g.current_user.store_id
        if store_id is None:
            return error_response(400, "User has no store context")
    try:
        svc = get_ticket_service()
        ticket = svc.create_ticket(
            store_id=store_id,
            user_id=g.current_user.id,
            user_role=g.current_user.role,
            username=g.current_user.username,
            actor_store_id=g.current_user.store_id,
            customer_name=data["customer_name"],
            clothing_category=data["clothing_category"],
            condition_grade=data["condition_grade"],
            estimated_weight_lbs=float(data["estimated_weight_lbs"]),
            customer_phone_preference=data.get("customer_phone_preference", "standard_calls"),
            customer_phone=data.get("customer_phone"),
            customer_phone_last4=data.get("customer_phone_last4"),
            now_local=data.get("now_local"),
        )
        return success_response(serialize(ticket), 201)
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@ticket_bp.route("/<int:ticket_id>/submit-qc", methods=["POST"])
@require_auth
def submit_for_qc(ticket_id):
    try:
        svc = get_ticket_service()
        ticket = svc.submit_for_qc(
            ticket_id, g.current_user.id, g.current_user.username,
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
        )
        return success_response(serialize(ticket))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@ticket_bp.route("/<int:ticket_id>/qc-final", methods=["POST"])
@require_auth
def record_qc_final(ticket_id):
    data = get_json_body()
    # actual_weight_lbs is now optional — the service derives it from
    # the persisted QC inspection.  If supplied it is used as a safety
    # cross-check (must match the inspection value).
    raw_weight = data.get("actual_weight_lbs")
    actual_weight_lbs = float(raw_weight) if raw_weight is not None else None
    try:
        svc = get_ticket_service()
        result = svc.record_qc_and_compute_final(
            ticket_id=ticket_id,
            actual_weight_lbs=actual_weight_lbs,
            user_id=g.current_user.id,
            username=g.current_user.username,
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
            now_local=data.get("now_local"),
        )
        return success_response({
            "ticket": serialize(result["ticket"]),
            "approval_required": result["approval_required"],
            "variance_amount": result["variance_amount"],
            "variance_pct": result["variance_pct"],
        })
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@ticket_bp.route("/<int:ticket_id>/confirm-variance", methods=["POST"])
@require_auth
def confirm_variance(ticket_id):
    data = get_json_body()
    err = require_fields(data, "confirmation_note")
    if err:
        return err
    try:
        svc = get_ticket_service()
        req = svc.confirm_variance(
            ticket_id=ticket_id,
            user_id=g.current_user.id,
            username=g.current_user.username,
            confirmation_note=data["confirmation_note"],
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
        )
        return success_response(serialize(req))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@ticket_bp.route("/variance/<int:request_id>/approve", methods=["POST"])
@require_auth
def approve_variance(request_id):
    data = get_json_body()
    err = require_fields(data, "password")
    if err:
        return err
    try:
        svc = get_ticket_service()
        ticket = svc.approve_variance(
            approval_request_id=request_id,
            approver_user_id=g.current_user.id,
            approver_username=g.current_user.username,
            approver_role=g.current_user.role,
            password=data["password"],
            approver_store_id=g.current_user.store_id,
        )
        return success_response(serialize(ticket))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@ticket_bp.route("/variance/<int:request_id>/reject", methods=["POST"])
@require_auth
def reject_variance(request_id):
    data = get_json_body()
    err = require_fields(data, "reason")
    if err:
        return err
    try:
        svc = get_ticket_service()
        req = svc.reject_variance(
            approval_request_id=request_id,
            approver_user_id=g.current_user.id,
            approver_username=g.current_user.username,
            approver_role=g.current_user.role,
            reason=data["reason"],
            approver_store_id=g.current_user.store_id,
        )
        return success_response(serialize(req))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@ticket_bp.route("/<int:ticket_id>/refund", methods=["POST"])
@require_auth
def initiate_refund(ticket_id):
    data = get_json_body()
    try:
        svc = get_ticket_service()
        ticket = svc.initiate_refund(
            ticket_id=ticket_id,
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
            actor_store_id=g.current_user.store_id,
            refund_amount=float(data["refund_amount"]) if data.get("refund_amount") else None,
            reason=data.get("reason"),
        )
        return success_response(serialize(ticket))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@ticket_bp.route("/<int:ticket_id>/refund/approve", methods=["POST"])
@require_auth
def approve_refund(ticket_id):
    data = get_json_body()
    err = require_fields(data, "password")
    if err:
        return err
    try:
        svc = get_ticket_service()
        ticket = svc.approve_refund(
            ticket_id=ticket_id,
            approver_user_id=g.current_user.id,
            approver_username=g.current_user.username,
            approver_role=g.current_user.role,
            password=data["password"],
            approver_store_id=g.current_user.store_id,
        )
        return success_response(serialize(ticket))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@ticket_bp.route("/<int:ticket_id>/refund/reject", methods=["POST"])
@require_auth
def reject_refund(ticket_id):
    data = get_json_body()
    err = require_fields(data, "reason")
    if err:
        return err
    try:
        svc = get_ticket_service()
        ticket = svc.reject_refund(
            ticket_id=ticket_id,
            approver_user_id=g.current_user.id,
            approver_username=g.current_user.username,
            approver_role=g.current_user.role,
            reason=data["reason"],
            approver_store_id=g.current_user.store_id,
        )
        return success_response(serialize(ticket))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@ticket_bp.route("/<int:ticket_id>/dial", methods=["POST"])
@require_auth
def dial_ticket_phone(ticket_id):
    """Decrypt and return the customer's phone number for an authorized
    dialer. Audited. Default ticket responses still mask the phone."""
    try:
        svc = get_ticket_service()
        result = svc.get_ticket_phone_for_dial(
            ticket_id=ticket_id,
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
            actor_store_id=g.current_user.store_id,
        )
        return success_response(result)
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@ticket_bp.route("/<int:ticket_id>/cancel", methods=["POST"])
@require_auth
def cancel_ticket(ticket_id):
    data = get_json_body()
    err = require_fields(data, "reason")
    if err:
        return err
    try:
        svc = get_ticket_service()
        ticket = svc.cancel_ticket(
            ticket_id=ticket_id,
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
            reason=data["reason"],
            actor_store_id=g.current_user.store_id,
        )
        return success_response(serialize(ticket))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))
