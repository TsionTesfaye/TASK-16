"""Settings routes — view and update configuration."""
from flask import Blueprint, g

from .helpers import (
    error_response, get_json_body, get_settings_service,
    require_auth, serialize, success_response,
)

settings_bp = Blueprint("settings", __name__, url_prefix="/api/settings")


@settings_bp.route("", methods=["GET"])
@require_auth
def get_settings():
    store_id = g.current_user.store_id
    svc = get_settings_service()
    if store_id:
        settings = svc.get_effective(store_id)
    else:
        settings = svc.get_global()
    return success_response(serialize(settings))


@settings_bp.route("", methods=["PUT"])
@require_auth
def update_settings():
    data = get_json_body()
    try:
        svc = get_settings_service()
        settings = svc.create_or_update(
            user_id=g.current_user.id,
            username=g.current_user.username,
            user_role=g.current_user.role,
            store_id=data.get("store_id"),
            **{k: v for k, v in data.items() if k != "store_id"},
        )
        return success_response(serialize(settings))
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))
