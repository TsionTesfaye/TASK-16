"""Admin routes — store and pricing rule management (administrator only)."""
from flask import Blueprint, g

from .helpers import (
    error_response, get_audit_service, get_json_body,
    require_auth, require_fields, serialize, success_response, _repos,
)
from ..services._authz import require_admin

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


# ── Stores ──

@admin_bp.route("/stores", methods=["POST"])
@require_auth
def create_store():
    data = get_json_body()
    err = require_fields(data, "code", "name")
    if err:
        return err
    try:
        require_admin(g.current_user.role)
        r = _repos()
        from ..models.store import Store
        existing = r["store"].get_by_code(data["code"])
        if existing:
            return error_response(400, f"Store code '{data['code']}' already exists")
        store = r["store"].create(Store(
            code=data["code"],
            name=data["name"],
            route_code=data.get("route_code"),
        ))
        # Auto-create settings for the new store
        from ..models.settings import Settings
        r["settings"].create(Settings(store_id=store.id))
        from app import get_db
        get_db().commit()

        get_audit_service().log(
            actor_user_id=g.current_user.id,
            actor_username=g.current_user.username,
            action_code="admin.store_created",
            object_type="store",
            object_id=str(store.id),
            after={"code": store.code, "name": store.name},
        )
        return success_response(serialize(store), 201)
    except PermissionError as e:
        return error_response(403, str(e))
    except ValueError as e:
        return error_response(400, str(e))


@admin_bp.route("/stores", methods=["GET"])
@require_auth
def list_stores():
    try:
        require_admin(g.current_user.role)
        r = _repos()
        stores = r["store"].list_all()
        return success_response(serialize(stores))
    except PermissionError as e:
        return error_response(403, str(e))


# ── Pricing Rules ──

@admin_bp.route("/pricing_rules", methods=["POST"])
@require_auth
def create_pricing_rule():
    data = get_json_body()
    err = require_fields(data, "store_id", "base_rate_per_lb")
    if err:
        return err
    try:
        require_admin(g.current_user.role)
        r = _repos()
        store = r["store"].get_by_id(int(data["store_id"]))
        if not store:
            return error_response(404, "Store not found")

        # Validate eligibility window if provided
        elig_start = data.get("eligibility_start_local")
        elig_end = data.get("eligibility_end_local")
        if elig_start or elig_end:
            if not (elig_start and elig_end):
                return error_response(400, "Both eligibility_start_local and eligibility_end_local are required when setting an eligibility window")
            from ..services.pricing_service import PricingService
            parsed_start = PricingService._parse_local_datetime(elig_start)
            parsed_end = PricingService._parse_local_datetime(elig_end)
            if parsed_start is None:
                return error_response(400, f"Invalid eligibility_start_local format: {elig_start}")
            if parsed_end is None:
                return error_response(400, f"Invalid eligibility_end_local format: {elig_end}")
            if parsed_start >= parsed_end:
                return error_response(400, "eligibility_start_local must be before eligibility_end_local")

        from ..models.pricing_rule import PricingRule
        rule = r["pricing_rule"].create(PricingRule(
            store_id=int(data["store_id"]),
            category_filter=data.get("category_filter"),
            condition_grade_filter=data.get("condition_grade_filter"),
            base_rate_per_lb=float(data["base_rate_per_lb"]),
            bonus_pct=float(data.get("bonus_pct", 0)),
            min_weight_lbs=float(data["min_weight_lbs"]) if data.get("min_weight_lbs") else 0.1,
            max_weight_lbs=float(data["max_weight_lbs"]) if data.get("max_weight_lbs") else 1000.0,
            max_ticket_payout=float(data.get("max_ticket_payout", 200.0)),
            max_rate_per_lb=float(data.get("max_rate_per_lb", 10.0)),
            eligibility_start_local=elig_start,
            eligibility_end_local=elig_end,
            priority=int(data.get("priority", 1)),
        ))
        from app import get_db
        get_db().commit()

        get_audit_service().log(
            actor_user_id=g.current_user.id,
            actor_username=g.current_user.username,
            action_code="admin.pricing_rule_created",
            object_type="pricing_rule",
            object_id=str(rule.id),
            after={"store_id": rule.store_id, "base_rate": rule.base_rate_per_lb},
        )
        return success_response(serialize(rule), 201)
    except PermissionError as e:
        return error_response(403, str(e))
    except (ValueError, TypeError) as e:
        return error_response(400, str(e))


# ── Service Tables ──

@admin_bp.route("/service_tables", methods=["POST"])
@require_auth
def create_service_table():
    data = get_json_body()
    err = require_fields(data, "store_id", "table_code", "area_type")
    if err:
        return err
    try:
        require_admin(g.current_user.role)
        r = _repos()
        store = r["store"].get_by_id(int(data["store_id"]))
        if not store:
            return error_response(404, "Store not found")

        # Check for duplicate table_code within the store
        existing = r["table"].list_by_store(int(data["store_id"]))
        for t in existing:
            if t.table_code == data["table_code"]:
                return error_response(400, f"Table code '{data['table_code']}' already exists in this store")

        from ..enums.area_type import AreaType
        valid_area_types = {e.value for e in AreaType}
        area_type = data["area_type"]
        if area_type not in valid_area_types:
            return error_response(400, f"area_type must be one of: {', '.join(sorted(valid_area_types))}")

        from ..models.service_table import ServiceTable
        table = r["table"].create(ServiceTable(
            store_id=int(data["store_id"]),
            table_code=data["table_code"],
            area_type=area_type,
        ))
        from app import get_db
        get_db().commit()

        get_audit_service().log(
            actor_user_id=g.current_user.id,
            actor_username=g.current_user.username,
            action_code="admin.service_table_created",
            object_type="service_table",
            object_id=str(table.id),
            after={"store_id": table.store_id, "table_code": table.table_code, "area_type": area_type},
        )
        return success_response(serialize(table), 201)
    except PermissionError as e:
        return error_response(403, str(e))
    except (ValueError, TypeError) as e:
        return error_response(400, str(e))


@admin_bp.route("/service_tables", methods=["GET"])
@require_auth
def list_service_tables():
    try:
        require_admin(g.current_user.role)
        r = _repos()
        from flask import request as flask_request
        store_id = flask_request.args.get("store_id", type=int)
        if store_id:
            tables = r["table"].list_by_store(store_id)
        else:
            tables = r["table"].list_by_store(0)  # empty — admin must filter
            # For admin listing all tables across stores, query all stores
            all_stores = r["store"].list_all()
            tables = []
            for s in all_stores:
                tables.extend(r["table"].list_by_store(s.id))
        return success_response(serialize(tables))
    except PermissionError as e:
        return error_response(403, str(e))
