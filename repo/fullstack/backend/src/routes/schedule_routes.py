"""Schedule adjustment routes — request, approve, reject."""
from flask import Blueprint, g

from .helpers import (
    error_response, get_json_body, get_schedule_service,
    require_auth, require_fields, serialize, session_store_id, success_response,
)

schedule_bp = Blueprint("schedules", __name__, url_prefix="/api/schedules")


@schedule_bp.route("/adjustments", methods=["POST"])
@require_auth
def request_adjustment():
    data = get_json_body()
    err = require_fields(data, "adjustment_type", "target_entity_type",
                         "target_entity_id", "before_value", "after_value", "reason")
    if err:
        return err
    store_id = session_store_id(data.get("store_id"))
    if store_id is None:
        return error_response(400, "store_id required (admin only)")
    try:
        svc = get_schedule_service()
        req = svc.request_adjustment(
            store_id=store_id,
            user_id=g.current_user.id,
            username=g.current_user.username,
            adjustment_type=data["adjustment_type"],
            target_entity_type=data["target_entity_type"],
            target_entity_id=data["target_entity_id"],
            before_value=data["before_value"],
            after_value=data["after_value"],
            reason=data["reason"],
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
        )
        return success_response(serialize(req), 201)
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@schedule_bp.route("/adjustments/<int:request_id>/approve", methods=["POST"])
@require_auth
def approve_adjustment(request_id):
    data = get_json_body()
    err = require_fields(data, "password")
    if err:
        return err
    try:
        svc = get_schedule_service()
        req = svc.approve_adjustment(
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


@schedule_bp.route("/adjustments/<int:request_id>/reject", methods=["POST"])
@require_auth
def reject_adjustment(request_id):
    data = get_json_body()
    err = require_fields(data, "reason")
    if err:
        return err
    try:
        svc = get_schedule_service()
        req = svc.reject_adjustment(
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


@schedule_bp.route("/adjustments/pending", methods=["GET"])
@require_auth
def list_pending():
    from flask import request as flask_request
    store_id = flask_request.args.get("store_id", type=int)
    try:
        svc = get_schedule_service()
        pending = svc.list_pending(
            store_id=store_id,
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
        )
        return success_response(serialize(pending))
    except PermissionError as e:
        return error_response(403, str(e))
