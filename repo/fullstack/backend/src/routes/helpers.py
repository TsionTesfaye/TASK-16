"""Shared route helpers — service construction, auth, response formatting.

Every route uses these helpers to avoid duplicating dependency wiring,
authentication checks, and response serialization.
"""
import dataclasses
import hmac
import logging
from functools import wraps
from typing import Optional

from flask import g, jsonify, request

from ..security.masking import mask_last4
from ..security.session_cookie import verify_session_cookie

from ..repositories import (
    AuditLogRepository,
    BatchGenealogyEventRepository,
    BatchRepository,
    BuybackTicketRepository,
    ClubOrganizationRepository,
    ExportRequestRepository,
    MemberHistoryEventRepository,
    MemberRepository,
    NotificationTemplateRepository,
    PriceOverrideRequestRepository,
    PricingCalculationSnapshotRepository,
    PricingRuleRepository,
    QCInspectionRepository,
    QuarantineRecordRepository,
    RecallRunRepository,
    ScheduleAdjustmentRequestRepository,
    ServiceTableRepository,
    SettingsRepository,
    StoreRepository,
    TableActivityEventRepository,
    TableSessionRepository,
    TicketMessageLogRepository,
    UserRepository,
    UserSessionRepository,
    VarianceApprovalRequestRepository,
)
from ..services.audit_service import AuditService
from ..services.auth_service import AuthService
from ..services.export_service import ExportService
from ..services.member_service import MemberService
from ..services.notification_service import NotificationService
from ..services.price_override_service import PriceOverrideService
from ..services.pricing_service import PricingService
from ..services.qc_service import QCService
from ..services.schedule_service import ScheduleService
from ..services.settings_service import SettingsService
from ..services.table_service import TableService
from ..services.ticket_service import TicketService
from ..services.traceability_service import TraceabilityService

logger = logging.getLogger(__name__)


# ── response helpers ──

def success_response(data, status=200, meta=None):
    body = {"data": data}
    if meta:
        body["meta"] = meta
    return jsonify(body), status


def error_response(code, message, details=None):
    body = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return jsonify({"error": body}), code


def serialize(obj):
    """Convert a dataclass instance to a JSON-safe dict.

    Automatically:
    - redacts secrets (password_hash, csrf_secret, session_nonce)
    - strips encryption artifacts (*_ciphertext, *_iv)
    - masks sensitive phone fields (customer_phone_last4 -> ••••1234)
    """
    if obj is None:
        return None
    if dataclasses.is_dataclass(obj):
        d = dataclasses.asdict(obj)
        REDACTED_FIELDS = {"password_hash", "csrf_secret", "session_nonce"}
        result = {}
        for k, v in d.items():
            if isinstance(v, (bytes, bytearray)):
                continue
            if k in REDACTED_FIELDS:
                continue
            if k.endswith("_ciphertext") or k.endswith("_iv"):
                continue
            # Mask sensitive fields by default
            if k == "customer_phone_last4" and v:
                result[k] = mask_last4(v)
                continue
            result[k] = v
        return result
    if isinstance(obj, list):
        return [serialize(item) for item in obj]
    return obj


# ── service factory (per-request) ──

def _get_db():
    from app import get_db
    return get_db()


def _repos():
    db = _get_db()
    if "repos" not in g:
        g.repos = {
            "store": StoreRepository(db),
            "audit": AuditLogRepository(db),
            "user": UserRepository(db),
            "session": UserSessionRepository(db),
            "settings": SettingsRepository(db),
            "ticket": BuybackTicketRepository(db),
            "pricing_rule": PricingRuleRepository(db),
            "snapshot": PricingCalculationSnapshotRepository(db),
            "variance": VarianceApprovalRequestRepository(db),
            "qc": QCInspectionRepository(db),
            "quarantine": QuarantineRecordRepository(db),
            "batch": BatchRepository(db),
            "genealogy": BatchGenealogyEventRepository(db),
            "recall": RecallRunRepository(db),
            "table": ServiceTableRepository(db),
            "table_session": TableSessionRepository(db),
            "table_event": TableActivityEventRepository(db),
            "template": NotificationTemplateRepository(db),
            "message": TicketMessageLogRepository(db),
            "org": ClubOrganizationRepository(db),
            "member": MemberRepository(db),
            "member_history": MemberHistoryEventRepository(db),
            "export": ExportRequestRepository(db),
            "schedule": ScheduleAdjustmentRequestRepository(db),
            "price_override": PriceOverrideRequestRepository(db),
        }
    return g.repos


def get_audit_service():
    r = _repos()
    return AuditService(r["audit"])


def get_auth_service():
    r = _repos()
    return AuthService(r["user"], r["session"], r["settings"], get_audit_service())


def get_ticket_service():
    r = _repos()
    audit = get_audit_service()
    pricing = PricingService(r["pricing_rule"], r["snapshot"], r["settings"])
    return TicketService(
        r["ticket"], r["variance"], pricing, audit,
        auth_service=get_auth_service(),
        qc_repo=r["qc"],
    )


def get_qc_service():
    r = _repos()
    return QCService(
        r["qc"], r["quarantine"], r["batch"], r["genealogy"],
        r["settings"], get_audit_service(),
        auth_service=get_auth_service(),
        user_repo=r["user"],
        ticket_repo=r["ticket"],
    )


def get_table_service():
    r = _repos()
    return TableService(
        r["table"], r["table_session"], r["table_event"],
        get_audit_service(), user_repo=r["user"],
    )


def get_notification_service():
    r = _repos()
    return NotificationService(r["message"], r["template"], r["ticket"], get_audit_service())


def get_member_service():
    r = _repos()
    return MemberService(r["member"], r["member_history"], r["org"], get_audit_service())


def get_export_service():
    r = _repos()
    return ExportService(
        r["export"], r["ticket"], r["settings"], get_audit_service(),
        auth_service=get_auth_service(),
        store_repo=r["store"],
    )


def get_traceability_service():
    r = _repos()
    return TraceabilityService(r["batch"], r["genealogy"], r["recall"], get_audit_service())


def get_schedule_service():
    r = _repos()
    return ScheduleService(
        r["schedule"], get_audit_service(),
        auth_service=get_auth_service(),
    )


def get_settings_service():
    r = _repos()
    return SettingsService(r["settings"], get_audit_service())


def get_price_override_service():
    r = _repos()
    return PriceOverrideService(
        r["price_override"], r["ticket"], get_audit_service(),
        auth_service=get_auth_service(),
    )


# ── authentication decorator ──

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CSRF_HEADER = "X-CSRF-Token"


def require_auth(f):
    """Decorator that validates the session + CSRF and injects identity into g.

    After this decorator runs, routes can use:
      g.current_user   — full User object
      g.current_session — full UserSession object
      g.user_id        — int (shortcut)
      g.user_role      — str (shortcut)
      g.username        — str (shortcut)

    ALL identity comes from the server-side session. NEVER from request body.

    For mutating methods (POST/PUT/PATCH/DELETE), a valid CSRF token must be
    provided in the X-CSRF-Token header, matching the session's csrf_secret.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        raw_cookie = request.cookies.get("session_nonce")
        if not raw_cookie:
            return error_response(401, "Authentication required")
        # Verify the HMAC signature BEFORE touching the database. A
        # forged or tampered cookie is rejected here, in constant time,
        # and never reaches the auth service.
        session_nonce = verify_session_cookie(raw_cookie)
        if session_nonce is None:
            logger.warning("Session cookie signature verification failed")
            return error_response(401, "Invalid session cookie")
        try:
            auth = get_auth_service()
            result = auth.validate_session(session_nonce)
            user = result["user"]
            session = result["session"]
            g.current_user = user
            g.current_session = session
            # Canonical identity shortcuts — never trust client for these
            g.user_id = user.id
            g.user_role = user.role
            g.username = user.username
        except PermissionError as e:
            return error_response(401, str(e))
        except Exception as e:
            logger.warning("Auth validation failed: %s", e)
            return error_response(401, "Authentication failed")

        # CSRF check for state-changing requests
        if request.method in MUTATING_METHODS:
            provided = request.headers.get(CSRF_HEADER, "")
            expected = session.csrf_secret or ""
            if not provided or not hmac.compare_digest(provided, expected):
                logger.warning(
                    "CSRF validation failed for %s %s (user=%s)",
                    request.method, request.path, user.username,
                )
                return error_response(403, "CSRF token missing or invalid")

        return f(*args, **kwargs)
    return decorated


# ── input helpers ──

def get_json_body():
    """Get parsed JSON body, or empty dict if not JSON."""
    if request.is_json:
        return request.get_json(silent=True) or {}
    return {}


def session_store_id(client_value=None):
    """Resolve the store_id for a write operation.

    Pinned-store users (everyone except administrators) ALWAYS use the
    store_id from their session — any client-supplied value is ignored
    so a logged-in agent cannot create rows in another store by hand-
    crafting a JSON body.

    Administrators have no pinned store, so for admin requests the
    client value is honored. If the admin omits it, the caller should
    treat that as a 400.
    """
    user = g.current_user
    if user.role == "administrator":
        if client_value is None:
            return None
        try:
            return int(client_value)
        except (TypeError, ValueError):
            return None
    return user.store_id


def require_fields(data: dict, *fields) -> Optional[tuple]:
    """Return error response tuple if any field missing, else None.

    A field is considered missing only if it is absent, None, or an
    empty string. Boolean `False` and numeric `0` are valid values and
    must pass this check.
    """
    missing = [
        f for f in fields
        if f not in data or data[f] is None or data[f] == ""
    ]
    if missing:
        return error_response(400, f"Missing required fields: {', '.join(missing)}")
    return None


def is_htmx():
    return request.headers.get("HX-Request") == "true"
