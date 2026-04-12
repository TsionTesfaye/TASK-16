"""QC routes — inspections, quarantine, traceability, recalls."""
from flask import Blueprint, g

from .helpers import (
    error_response, get_json_body, get_qc_service, get_traceability_service,
    require_auth, require_fields, serialize, session_store_id, success_response,
)

qc_bp = Blueprint("qc", __name__, url_prefix="/api/qc")


@qc_bp.route("/inspections", methods=["POST"])
@require_auth
def create_inspection():
    data = get_json_body()
    err = require_fields(data, "ticket_id", "actual_weight_lbs",
                         "lot_size", "nonconformance_count", "inspection_outcome")
    if err:
        return err
    store_id = session_store_id(data.get("store_id"))
    if store_id is None:
        return error_response(400, "store_id required (admin only)")
    try:
        svc = get_qc_service()
        inspection = svc.create_inspection(
            ticket_id=int(data["ticket_id"]),
            store_id=store_id,
            inspector_user_id=g.current_user.id,
            inspector_username=g.current_user.username,
            inspector_role=g.current_user.role,
            actor_store_id=g.current_user.store_id,
            actual_weight_lbs=float(data["actual_weight_lbs"]),
            lot_size=int(data["lot_size"]),
            nonconformance_count=int(data["nonconformance_count"]),
            inspection_outcome=data["inspection_outcome"],
            notes=data.get("notes"),
        )
        return success_response(serialize(inspection), 201)
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@qc_bp.route("/quarantine", methods=["POST"])
@require_auth
def create_quarantine():
    data = get_json_body()
    err = require_fields(data, "ticket_id", "batch_id")
    if err:
        return err
    try:
        svc = get_qc_service()
        record = svc.create_quarantine(
            ticket_id=int(data["ticket_id"]),
            batch_id=int(data["batch_id"]),
            user_id=g.current_user.id,
            username=g.current_user.username,
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
            notes=data.get("notes"),
        )
        return success_response(serialize(record), 201)
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@qc_bp.route("/quarantine/<int:quarantine_id>/resolve", methods=["POST"])
@require_auth
def resolve_quarantine(quarantine_id):
    data = get_json_body()
    err = require_fields(data, "disposition")
    if err:
        return err
    try:
        svc = get_qc_service()
        record = svc.resolve_quarantine(
            quarantine_id=quarantine_id,
            disposition=data["disposition"],
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
            actor_store_id=g.current_user.store_id,
            concession_supervisor_id=int(data["concession_supervisor_id"]) if data.get("concession_supervisor_id") else None,
            concession_supervisor_username=data.get("concession_supervisor_username"),
            concession_supervisor_password=data.get("concession_supervisor_password"),
            notes=data.get("notes"),
        )
        return success_response(serialize(record))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@qc_bp.route("/batches", methods=["POST"])
@require_auth
def create_batch():
    data = get_json_body()
    err = require_fields(data, "batch_code")
    if err:
        return err
    store_id = session_store_id(data.get("store_id"))
    if store_id is None:
        return error_response(400, "store_id required (admin only)")
    try:
        svc = get_traceability_service()
        batch = svc.create_batch(
            store_id=store_id,
            batch_code=data["batch_code"],
            user_id=g.current_user.id,
            username=g.current_user.username,
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
            source_ticket_id=int(data["source_ticket_id"]) if data.get("source_ticket_id") else None,
        )
        return success_response(serialize(batch), 201)
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@qc_bp.route("/batches/<int:batch_id>/transition", methods=["POST"])
@require_auth
def transition_batch(batch_id):
    data = get_json_body()
    err = require_fields(data, "target_status")
    if err:
        return err
    try:
        svc = get_traceability_service()
        batch = svc.transition_batch(
            batch_id=batch_id,
            target_status=data["target_status"],
            user_id=g.current_user.id,
            username=g.current_user.username,
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
            location_context=data.get("location_context"),
            metadata=data.get("metadata"),
        )
        return success_response(serialize(batch))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@qc_bp.route("/batches/<int:batch_id>/lineage", methods=["GET"])
@require_auth
def get_batch_lineage(batch_id):
    try:
        svc = get_traceability_service()
        events = svc.get_batch_lineage(
            batch_id,
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
        )
        return success_response(serialize(events))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(404, str(e))


@qc_bp.route("/recalls", methods=["POST"])
@require_auth
def generate_recall():
    data = get_json_body()
    try:
        svc = get_traceability_service()
        run = svc.generate_recall(
            user_id=g.current_user.id,
            username=g.current_user.username,
            store_id=int(data["store_id"]) if data.get("store_id") else None,
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
            batch_filter=data.get("batch_filter"),
            date_start=data.get("date_start"),
            date_end=data.get("date_end"),
        )
        return success_response(serialize(run), 201)
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@qc_bp.route("/recalls/<int:run_id>", methods=["GET"])
@require_auth
def get_recall(run_id):
    try:
        svc = get_traceability_service()
        run = svc.get_recall_run(
            run_id,
            actor_store_id=g.current_user.store_id,
            user_role=g.current_user.role,
        )
        data = serialize(run)
        import json as _json
        if run.result_json:
            try:
                data["result_data"] = _json.loads(run.result_json)
            except (ValueError, TypeError):
                data["result_data"] = None
        return success_response(data)
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(404, str(e))
