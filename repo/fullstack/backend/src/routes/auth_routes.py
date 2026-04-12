"""Authentication routes — login, logout, user management."""
import os

from flask import Blueprint, jsonify, make_response

from ..security.session_cookie import sign_session_nonce
from .helpers import (
    error_response, get_auth_service, get_json_body,
    require_auth, require_fields, serialize, success_response,
)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# Secure-by-default: cookies get the Secure flag unless explicitly
# disabled for dev mode (SECURE_COOKIES=false).
SECURE_COOKIES = os.environ.get("SECURE_COOKIES", "true").lower() == "true"
SESSION_MAX_AGE = 8 * 3600  # 8 hours


def _set_auth_cookies(resp, session):
    """Set hardened session + CSRF cookies on the response."""
    # session_nonce: httponly (JS cannot read), strict samesite, short
    # lifetime, AND HMAC-signed so a tampered cookie is rejected by the
    # request decorator before it ever hits the DB.
    signed_nonce = sign_session_nonce(session.session_nonce)
    resp.set_cookie(
        "session_nonce", signed_nonce,
        httponly=True,
        secure=SECURE_COOKIES,
        samesite="Strict",
        max_age=SESSION_MAX_AGE,
        path="/",
    )
    # csrf_token: NOT httponly so JS can read it and echo in X-CSRF-Token header
    resp.set_cookie(
        "csrf_token", session.csrf_secret,
        httponly=False,
        secure=SECURE_COOKIES,
        samesite="Strict",
        max_age=SESSION_MAX_AGE,
        path="/",
    )


@auth_bp.route("/bootstrap", methods=["POST"])
def bootstrap():
    """Create the first administrator.

    Unauthenticated by design — this is the only way to bring up a
    brand-new deployment. Locks itself as soon as the first admin is
    created; subsequent calls return 403.
    """
    data = get_json_body()
    err = require_fields(data, "username", "password", "display_name")
    if err:
        return err
    try:
        auth = get_auth_service()
        user = auth.bootstrap_admin(
            username=data["username"],
            password=data["password"],
            display_name=data["display_name"],
        )
        return success_response(
            {"message": "Bootstrap complete", "user": serialize(user)},
            201,
        )
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@auth_bp.route("/login", methods=["POST"])
def login():
    data = get_json_body()
    err = require_fields(data, "username", "password")
    if err:
        return err
    try:
        auth = get_auth_service()
        result = auth.authenticate(
            username=data["username"],
            password=data["password"],
            client_device_id=data.get("client_device_id"),
        )
        session = result["session"]
        resp = make_response(jsonify({
            "data": {
                "user": serialize(result["user"]),
                "session_id": session.id,
                "csrf_token": session.csrf_secret,
            }
        }), 200)
        _set_auth_cookies(resp, session)
        return resp
    except PermissionError as e:
        return error_response(401, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@auth_bp.route("/logout", methods=["POST"])
@require_auth
def logout():
    from flask import g
    auth = get_auth_service()
    auth.logout(g.current_session.id, g.current_user.id, g.current_user.username)
    resp = make_response(jsonify({"data": {"message": "Logged out"}}), 200)
    resp.delete_cookie("session_nonce", path="/")
    resp.delete_cookie("csrf_token", path="/")
    return resp


@auth_bp.route("/users", methods=["POST"])
@require_auth
def create_user():
    from flask import g
    data = get_json_body()
    err = require_fields(data, "username", "password", "display_name", "role")
    if err:
        return err
    try:
        auth = get_auth_service()
        user = auth.create_user(
            username=data["username"],
            password=data["password"],
            display_name=data["display_name"],
            role=data["role"],
            admin_user_id=g.current_user.id,
            admin_username=g.current_user.username,
            admin_role=g.current_user.role,
            store_id=data.get("store_id"),
        )
        return success_response(serialize(user), 201)
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@auth_bp.route("/users/<int:user_id>/freeze", methods=["POST"])
@require_auth
def freeze_user(user_id):
    from flask import g
    try:
        auth = get_auth_service()
        user = auth.freeze_user(
            user_id, g.current_user.id, g.current_user.username,
            admin_role=g.current_user.role,
        )
        return success_response(serialize(user))
    except (PermissionError, ValueError) as e:
        code = 403 if isinstance(e, PermissionError) else 400
        return error_response(code, str(e))


@auth_bp.route("/users/<int:user_id>/unfreeze", methods=["POST"])
@require_auth
def unfreeze_user(user_id):
    from flask import g
    try:
        auth = get_auth_service()
        user = auth.unfreeze_user(
            user_id, g.current_user.id, g.current_user.username,
            admin_role=g.current_user.role,
        )
        return success_response(serialize(user))
    except (PermissionError, ValueError) as e:
        code = 403 if isinstance(e, PermissionError) else 400
        return error_response(code, str(e))
