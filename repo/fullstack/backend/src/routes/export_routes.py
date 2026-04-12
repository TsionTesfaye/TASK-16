"""Export and reporting routes — requests, approvals, metrics."""
from flask import Blueprint, g

from .helpers import (
    error_response, get_export_service, get_json_body,
    require_auth, require_fields, serialize, session_store_id, success_response,
)

export_bp = Blueprint("exports", __name__, url_prefix="/api/exports")


@export_bp.route("/requests", methods=["POST"])
@require_auth
def create_export_request():
    data = get_json_body()
    err = require_fields(data, "export_type")
    if err:
        return err
    store_id = session_store_id(data.get("store_id"))
    if store_id is None:
        return error_response(400, "store_id required (admin only)")
    try:
        svc = get_export_service()
        req = svc.create_export_request(
            store_id=store_id,
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
            actor_store_id=g.current_user.store_id,
            export_type=data["export_type"],
            filter_json=data.get("filter_json"),
            watermark_enabled=bool(data.get("watermark_enabled", False)),
            attribution_text=data.get("attribution_text"),
        )
        return success_response(serialize(req), 201)
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@export_bp.route("/requests/<int:request_id>/approve", methods=["POST"])
@require_auth
def approve_export(request_id):
    data = get_json_body()
    err = require_fields(data, "password")
    if err:
        return err
    try:
        svc = get_export_service()
        req = svc.approve_export(
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


@export_bp.route("/requests/<int:request_id>/reject", methods=["POST"])
@require_auth
def reject_export(request_id):
    data = get_json_body()
    err = require_fields(data, "reason")
    if err:
        return err
    try:
        svc = get_export_service()
        req = svc.reject_export(
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


@export_bp.route("/requests/<int:request_id>/execute", methods=["POST"])
@require_auth
def execute_export(request_id):
    try:
        svc = get_export_service()
        req = svc.execute_export(
            request_id=request_id,
            user_id=g.current_user.id,
            username=g.current_user.username,
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
        )
        return success_response(serialize(req))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@export_bp.route("/metrics", methods=["GET"])
@require_auth
def get_metrics():
    store_id = g.current_user.store_id
    if not store_id:
        return error_response(400, "Store context required for metrics")

    from flask import request as flask_request
    date_start = flask_request.args.get("date_start")
    date_end = flask_request.args.get("date_end")
    if not date_start or not date_end:
        return error_response(400, "date_start and date_end are required")

    clothing_category = flask_request.args.get("clothing_category")
    route_code = flask_request.args.get("route_code")

    try:
        svc = get_export_service()
        metrics = svc.compute_metrics(
            store_id=store_id,
            date_start=date_start,
            date_end=date_end,
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
            clothing_category=clothing_category,
            route_code=route_code,
        )
        return success_response(metrics)
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))
