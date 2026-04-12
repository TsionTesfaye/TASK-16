"""Notification routes — message logging, call attempts, retries."""
import json

from flask import Blueprint, g

from .helpers import (
    error_response, get_json_body, get_notification_service,
    require_auth, require_fields, serialize, session_store_id, success_response,
)

notification_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


@notification_bp.route("/messages", methods=["POST"])
@require_auth
def log_message():
    data = get_json_body()
    err = require_fields(data, "ticket_id", "message_body")
    if err:
        return err
    try:
        svc = get_notification_service()
        log = svc.log_message(
            ticket_id=int(data["ticket_id"]),
            user_id=g.current_user.id,
            username=g.current_user.username,
            message_body=data["message_body"],
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
            contact_channel=data.get("contact_channel", "logged_message"),
            template_id=int(data["template_id"]) if data.get("template_id") else None,
            call_attempt_status=data.get("call_attempt_status"),
            retry_minutes=int(data["retry_minutes"]) if data.get("retry_minutes") else None,
        )
        return success_response(serialize(log), 201)
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@notification_bp.route("/messages/template", methods=["POST"])
@require_auth
def log_from_template():
    data = get_json_body()
    err = require_fields(data, "ticket_id", "template_code", "context")
    if err:
        return err
    store_id = session_store_id(data.get("store_id"))
    if store_id is None:
        return error_response(400, "store_id required (admin only)")

    # The UI sends `context` as either a JSON object or a JSON-encoded
    # string (depending on the form wiring). Normalize both shapes and
    # reject anything else with a 400 rather than letting a TypeError
    # bubble out of the template renderer.
    raw_context = data["context"]
    if isinstance(raw_context, str):
        try:
            parsed_context = json.loads(raw_context)
        except (ValueError, TypeError):
            return error_response(400, "context must be a valid JSON object")
    else:
        parsed_context = raw_context
    if not isinstance(parsed_context, dict):
        return error_response(400, "context must be a JSON object (key/value map)")

    try:
        svc = get_notification_service()
        log = svc.log_from_template(
            ticket_id=int(data["ticket_id"]),
            template_code=data["template_code"],
            store_id=store_id,
            user_id=g.current_user.id,
            username=g.current_user.username,
            context=parsed_context,
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
            contact_channel=data.get("contact_channel", "logged_message"),
            call_attempt_status=data.get("call_attempt_status"),
        )
        return success_response(serialize(log), 201)
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@notification_bp.route("/tickets/<int:ticket_id>/messages", methods=["GET"])
@require_auth
def get_ticket_messages(ticket_id):
    try:
        svc = get_notification_service()
        messages = svc.get_ticket_messages(
            ticket_id,
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
        )
        return success_response(serialize(messages))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(404, str(e))


@notification_bp.route("/retries/pending", methods=["GET"])
@require_auth
def get_pending_retries():
    try:
        svc = get_notification_service()
        retries = svc.get_pending_retries(
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
        )
        return success_response(serialize(retries))
    except PermissionError as e:
        return error_response(403, str(e))
