"""Table / Room routes — open, transition, merge, transfer, timeline."""
from flask import Blueprint, g

from .helpers import (
    error_response, get_json_body, get_table_service,
    require_auth, require_fields, serialize, session_store_id, success_response,
)

table_bp = Blueprint("tables", __name__, url_prefix="/api/tables")


@table_bp.route("/open", methods=["POST"])
@require_auth
def open_table():
    data = get_json_body()
    err = require_fields(data, "table_id")
    if err:
        return err
    store_id = session_store_id(data.get("store_id"))
    if store_id is None:
        return error_response(400, "store_id required (admin only)")
    try:
        svc = get_table_service()
        session = svc.open_table(
            table_id=int(data["table_id"]),
            store_id=store_id,
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
            actor_store_id=g.current_user.store_id,
            customer_label=data.get("customer_label"),
        )
        return success_response(serialize(session), 201)
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@table_bp.route("/sessions/<int:session_id>/transition", methods=["POST"])
@require_auth
def transition_table(session_id):
    data = get_json_body()
    err = require_fields(data, "target_state")
    if err:
        return err
    try:
        svc = get_table_service()
        session = svc.transition_table(
            session_id=session_id,
            target_state=data["target_state"],
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
            actor_store_id=g.current_user.store_id,
            notes=data.get("notes"),
        )
        return success_response(serialize(session))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@table_bp.route("/merge", methods=["POST"])
@require_auth
def merge_tables():
    data = get_json_body()
    err = require_fields(data, "session_ids")
    if err:
        return err
    session_ids = data["session_ids"]
    if not isinstance(session_ids, list) or len(session_ids) < 2:
        return error_response(400, "session_ids must be a list of at least 2 IDs")
    store_id = session_store_id(data.get("store_id"))
    if store_id is None:
        return error_response(400, "store_id required (admin only)")
    try:
        svc = get_table_service()
        group_code = svc.merge_tables(
            session_ids=[int(sid) for sid in session_ids],
            store_id=store_id,
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
            actor_store_id=g.current_user.store_id,
        )
        return success_response({"group_code": group_code})
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@table_bp.route("/sessions/<int:session_id>/transfer", methods=["POST"])
@require_auth
def transfer_table(session_id):
    data = get_json_body()
    err = require_fields(data, "new_user_id")
    if err:
        return err
    try:
        svc = get_table_service()
        session = svc.transfer_table(
            session_id=session_id,
            new_user_id=int(data["new_user_id"]),
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
            actor_store_id=g.current_user.store_id,
        )
        return success_response(serialize(session))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@table_bp.route("/sessions/<int:session_id>/timeline", methods=["GET"])
@require_auth
def get_timeline(session_id):
    try:
        svc = get_table_service()
        events = svc.get_timeline(
            session_id,
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
        )
        return success_response(serialize(events))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(404, str(e))
