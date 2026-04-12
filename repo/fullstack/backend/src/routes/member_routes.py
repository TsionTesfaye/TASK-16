"""Member / Club routes — organizations, members, CSV import + export."""
from flask import Blueprint, Response, g, request as flask_request

from .helpers import (
    error_response, get_json_body, get_member_service,
    require_auth, require_fields, serialize, success_response,
)

member_bp = Blueprint("members", __name__, url_prefix="/api/members")


@member_bp.route("/organizations", methods=["POST"])
@require_auth
def create_organization():
    data = get_json_body()
    err = require_fields(data, "name")
    if err:
        return err
    try:
        svc = get_member_service()
        org = svc.create_organization(
            name=data["name"],
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
            department=data.get("department"),
            route_code=data.get("route_code"),
        )
        return success_response(serialize(org), 201)
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@member_bp.route("/organizations/<int:org_id>", methods=["PUT"])
@require_auth
def update_organization(org_id):
    data = get_json_body()
    try:
        svc = get_member_service()
        org = svc.update_organization(
            org_id=org_id,
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
            name=data.get("name"),
            department=data.get("department"),
            route_code=data.get("route_code"),
            is_active=data.get("is_active"),
        )
        return success_response(serialize(org))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@member_bp.route("", methods=["POST"])
@require_auth
def add_member():
    data = get_json_body()
    err = require_fields(data, "org_id", "full_name")
    if err:
        return err
    try:
        svc = get_member_service()
        member = svc.add_member(
            org_id=int(data["org_id"]),
            full_name=data["full_name"],
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
            group=data.get("group"),
        )
        return success_response(serialize(member), 201)
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@member_bp.route("/<int:member_id>/remove", methods=["POST"])
@require_auth
def remove_member(member_id):
    try:
        svc = get_member_service()
        member = svc.remove_member(
            member_id=member_id,
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
        )
        return success_response(serialize(member))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@member_bp.route("/<int:member_id>/transfer", methods=["POST"])
@require_auth
def transfer_member(member_id):
    data = get_json_body()
    err = require_fields(data, "target_org_id")
    if err:
        return err
    try:
        svc = get_member_service()
        member = svc.transfer_member(
            member_id=member_id,
            target_org_id=int(data["target_org_id"]),
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
        )
        return success_response(serialize(member))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@member_bp.route("/<int:member_id>/history", methods=["GET"])
@require_auth
def get_member_history(member_id):
    try:
        svc = get_member_service()
        events = svc.get_member_history(
            member_id, user_role=g.current_user.role,
        )
        return success_response(serialize(events))
    except PermissionError as e:
        return error_response(403, str(e))


@member_bp.route("/export", methods=["GET"])
@require_auth
def export_csv():
    """Download all members as a CSV file.

    Admin-only. Optional `organization_id` query param limits output to
    a single club. The returned file passes the same validation rules
    as the import endpoint, so it is directly re-importable.
    """
    org_id_raw = flask_request.args.get("organization_id")
    try:
        org_id = int(org_id_raw) if org_id_raw else None
    except (TypeError, ValueError):
        return error_response(400, "organization_id must be an integer")

    try:
        svc = get_member_service()
        csv_body = svc.export_members_csv(
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
            organization_id=org_id,
        )
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))

    filename = (
        f"members_org_{org_id}.csv" if org_id is not None else "members.csv"
    )
    return Response(
        csv_body,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@member_bp.route("/import", methods=["POST"])
@require_auth
def import_csv():
    if "file" not in flask_request.files:
        return error_response(400, "No file provided")

    file = flask_request.files["file"]
    if not file.filename or not file.filename.lower().endswith(".csv"):
        return error_response(400, "Only CSV files are accepted")
    if file.content_type not in (
        "text/csv",
        "application/csv",
        "application/vnd.ms-excel",
    ):
        return error_response(400, "Only CSV files are accepted")

    content = file.read()
    if len(content) > 5 * 1024 * 1024:
        return error_response(400, "File exceeds 5MB limit")
    if len(content) == 0:
        return error_response(400, "File is empty")
    # Early binary rejection at route level — reject NUL bytes before
    # handing off to the service layer's full validation.
    if b"\x00" in content:
        return error_response(400, "File contains binary content")

    try:
        svc = get_member_service()
        result = svc.import_members_csv(
            file_content=content,
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
        )
        return success_response(result, 201)
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))
