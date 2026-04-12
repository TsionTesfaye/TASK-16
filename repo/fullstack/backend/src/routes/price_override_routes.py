"""Price override routes — request, approve, reject, execute."""
from flask import Blueprint, g

from .helpers import (
    error_response, get_json_body, get_price_override_service,
    require_auth, require_fields, serialize, success_response,
)

price_override_bp = Blueprint(
    "price_overrides", __name__, url_prefix="/api/price-overrides"
)


@price_override_bp.route("", methods=["POST"])
@require_auth
def request_override():
    data = get_json_body()
    err = require_fields(data, "ticket_id", "proposed_payout", "reason")
    if err:
        return err
    try:
        svc = get_price_override_service()
        req = svc.request_price_override(
            ticket_id=int(data["ticket_id"]),
            proposed_payout=float(data["proposed_payout"]),
            reason=data["reason"],
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
            actor_store_id=g.current_user.store_id,
        )
        return success_response(serialize(req), 201)
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@price_override_bp.route("/<int:request_id>/approve", methods=["POST"])
@require_auth
def approve_override(request_id):
    data = get_json_body()
    err = require_fields(data, "password")
    if err:
        return err
    try:
        svc = get_price_override_service()
        req = svc.approve_price_override(
            request_id=request_id,
            approver_user_id=g.current_user.id,
            approver_username=g.current_user.username,
            approver_role=g.current_user.role,
            password=data["password"],
            approver_store_id=g.current_user.store_id,
        )
        return success_response(serialize(req))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@price_override_bp.route("/<int:request_id>/reject", methods=["POST"])
@require_auth
def reject_override(request_id):
    data = get_json_body()
    err = require_fields(data, "reason")
    if err:
        return err
    try:
        svc = get_price_override_service()
        req = svc.reject_price_override(
            request_id=request_id,
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


@price_override_bp.route("/<int:request_id>/execute", methods=["POST"])
@require_auth
def execute_override(request_id):
    try:
        svc = get_price_override_service()
        req = svc.execute_override(
            request_id=request_id,
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
            actor_store_id=g.current_user.store_id,
        )
        return success_response(serialize(req))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@price_override_bp.route("/pending", methods=["GET"])
@require_auth
def list_pending():
    try:
        svc = get_price_override_service()
        pending = svc.list_pending(
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
        )
        return success_response(serialize(pending))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))
