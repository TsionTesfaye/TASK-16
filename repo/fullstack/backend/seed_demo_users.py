"""Seed demo accounts for development and acceptance testing.

Activated by setting RECLAIM_OPS_SEED_DEMO_USERS=true in the environment.
Called from create_app() immediately after migrations — safe to run on
every container start because every step is idempotent.

Seeded accounts
---------------
admin        / AdminPass123!   administrator
operator     / DemoPass1234!   front_desk_agent
supervisor   / DemoPass1234!   shift_supervisor
qcinspector  / DemoPass1234!   qc_inspector
host         / DemoPass1234!   host
opsmanager   / DemoPass1234!   operations_manager
"""
import logging

from src.database import get_connection
from src.models.store import Store
from src.repositories import (
    AuditLogRepository,
    SettingsRepository,
    StoreRepository,
    UserRepository,
    UserSessionRepository,
)
from src.services.audit_service import AuditService
from src.services.auth_service import AuthService

logger = logging.getLogger(__name__)

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "AdminPass123!"
DEMO_PASSWORD = "DemoPass1234!"
DEMO_STORE_CODE = "DEMO"

_ROLE_USERS = [
    ("operator",    "front_desk_agent",   "Demo Operator"),
    ("supervisor",  "shift_supervisor",   "Demo Supervisor"),
    ("qcinspector", "qc_inspector",       "Demo QC Inspector"),
    ("host",        "host",               "Demo Host"),
    ("opsmanager",  "operations_manager", "Demo Ops Manager"),
]


def seed_demo_users(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        user_repo = UserRepository(conn)
        session_repo = UserSessionRepository(conn)
        settings_repo = SettingsRepository(conn)
        audit_service = AuditService(AuditLogRepository(conn))
        auth_service = AuthService(user_repo, session_repo, settings_repo, audit_service)
        store_repo = StoreRepository(conn)

        # Bootstrap admin (idempotent — 409/PermissionError if already done)
        admin = user_repo.get_by_username(ADMIN_USERNAME)
        if admin is None:
            try:
                admin = auth_service.bootstrap_admin(
                    username=ADMIN_USERNAME,
                    password=ADMIN_PASSWORD,
                    display_name="Demo Admin",
                )
                logger.info("[seed] Bootstrapped admin: %s", ADMIN_USERNAME)
            except PermissionError:
                logger.info("[seed] Bootstrap already completed; skipping admin creation")
                return

        # Get or create the demo store
        store = store_repo.get_by_code(DEMO_STORE_CODE)
        if store is None:
            store = store_repo.create(Store(code=DEMO_STORE_CODE, name="Demo Store"))
            logger.info("[seed] Created demo store: %s (id=%d)", DEMO_STORE_CODE, store.id)

        # Create one user per role (skip if username already exists)
        for username, role, display_name in _ROLE_USERS:
            if user_repo.get_by_username(username) is not None:
                continue
            auth_service.create_user(
                username=username,
                password=DEMO_PASSWORD,
                display_name=display_name,
                role=role,
                admin_user_id=admin.id,
                admin_username=admin.username,
                admin_role=admin.role,
                store_id=store.id,
            )
            logger.info("[seed] Created demo user: %s (%s)", username, role)

        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.warning("[seed] Demo seeding failed (non-fatal): %s", exc)
    finally:
        conn.close()
