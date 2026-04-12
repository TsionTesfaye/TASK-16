"""System hardening tests.

Verifies:
- scheduler idempotency and sweep behavior
- duplicate approval attempts fail safely (concurrency + idempotency)
- duplicate export execution fails safely
- startup reconciliation is a no-op on a clean DB
- startup reconciliation expires stale state deterministically
- critical transaction rollback paths
"""
import os
import sys
import tempfile
import sqlite3
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fullstack", "backend"))

import pytest

from src.database import init_db
from src.enums.ticket_status import TicketStatus
from src.enums.user_role import UserRole
from src.enums.variance_approval_status import VarianceApprovalStatus
from src.enums.export_request_status import ExportRequestStatus
from src.models.store import Store
from src.models.settings import Settings
from src.models.pricing_rule import PricingRule
from src.models.user import User
from src.models.export_request import ExportRequest
from src.models.variance_approval_request import VarianceApprovalRequest
from src.models.buyback_ticket import BuybackTicket
from src.models.schedule_adjustment_request import ScheduleAdjustmentRequest
from src.models.quarantine_record import QuarantineRecord
from src.models.batch import Batch
from src.repositories import (
    StoreRepository, SettingsRepository, PricingRuleRepository,
    UserRepository, ExportRequestRepository, BuybackTicketRepository,
    VarianceApprovalRequestRepository, QCInspectionRepository,
    ScheduleAdjustmentRequestRepository, QuarantineRecordRepository,
    BatchRepository, BatchGenealogyEventRepository, AuditLogRepository,
)
from src.scheduler import run_expiration_sweep


def _isoformat(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def tmp_db():
    """Create a file-backed SQLite DB so scheduler can open its own connection."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    conn = init_db(path)
    conn.close()
    yield path
    # WAL and SHM cleanup
    for ext in ("", "-wal", "-shm"):
        p = path + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


def _seed_minimal(db_path):
    """Insert a store, user, and settings — minimal fixture for hardening tests."""
    from src.database import get_connection
    conn = get_connection(db_path)
    store = StoreRepository(conn).create(Store(code="S1", name="Test Store"))
    SettingsRepository(conn).create(Settings(store_id=store.id))
    user = UserRepository(conn).create(User(
        store_id=store.id, username="tester", password_hash="x",
        display_name="Tester", role=UserRole.ADMINISTRATOR,
    ))
    conn.commit()
    conn.close()
    return store, user


# ── Scheduler ──

class TestSchedulerSweep:
    def test_sweep_on_empty_db_is_noop(self, tmp_db):
        result = run_expiration_sweep(tmp_db)
        assert result == {
            "exports_expired": 0,
            "variance_expired": 0,
            "schedules_expired": 0,
            "quarantines_overdue": 0,
        }

    def test_sweep_is_idempotent(self, tmp_db):
        _seed_minimal(tmp_db)
        r1 = run_expiration_sweep(tmp_db)
        r2 = run_expiration_sweep(tmp_db)
        # Second run must be no-op
        assert r1["exports_expired"] == r2["exports_expired"] == 0
        assert r1["schedules_expired"] == r2["schedules_expired"] == 0

    def test_expires_stale_pending_export_requests(self, tmp_db):
        from src.database import get_connection
        store, user = _seed_minimal(tmp_db)
        # Insert a pending export with created_at in the distant past
        conn = get_connection(tmp_db)
        old_ts = _isoformat(datetime.now(timezone.utc) - timedelta(hours=48))
        conn.execute(
            "INSERT INTO export_requests (store_id, requested_by_user_id, "
            "export_type, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (store.id, user.id, "tickets", "pending", old_ts),
        )
        conn.commit()
        conn.close()

        result = run_expiration_sweep(tmp_db)
        assert result["exports_expired"] == 1

        # Verify the status changed
        conn = get_connection(tmp_db)
        row = conn.execute(
            "SELECT status FROM export_requests WHERE store_id = ?", (store.id,)
        ).fetchone()
        assert row["status"] == "expired"
        conn.close()

        # Second sweep — already expired, no-op
        result = run_expiration_sweep(tmp_db)
        assert result["exports_expired"] == 0

    def test_recent_pending_export_not_expired(self, tmp_db):
        from src.database import get_connection
        store, user = _seed_minimal(tmp_db)
        conn = get_connection(tmp_db)
        recent = _isoformat(datetime.now(timezone.utc) - timedelta(hours=1))
        conn.execute(
            "INSERT INTO export_requests (store_id, requested_by_user_id, "
            "export_type, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (store.id, user.id, "tickets", "pending", recent),
        )
        conn.commit()
        conn.close()

        result = run_expiration_sweep(tmp_db)
        assert result["exports_expired"] == 0

    def test_expires_stale_variance_requests(self, tmp_db):
        from src.database import get_connection
        store, user = _seed_minimal(tmp_db)
        conn = get_connection(tmp_db)

        # Need a ticket to reference
        cursor = conn.execute(
            "INSERT INTO buyback_tickets (store_id, created_by_user_id, "
            "customer_name, clothing_category, condition_grade, "
            "estimated_weight_lbs, estimated_base_rate, estimated_bonus_pct, "
            "estimated_payout, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (store.id, user.id, "J", "shirts", "A", 10.0, 1.5, 0, 15.0, "awaiting_qc"),
        )
        ticket_id = cursor.lastrowid

        expired_at = _isoformat(datetime.now(timezone.utc) - timedelta(hours=1))
        conn.execute(
            "INSERT INTO variance_approval_requests "
            "(ticket_id, requested_by_user_id, variance_amount, variance_pct, "
            "threshold_amount, threshold_pct, status, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (ticket_id, user.id, 10.0, 10.0, 5.0, 5.0, "pending", expired_at),
        )
        conn.commit()
        conn.close()

        result = run_expiration_sweep(tmp_db)
        assert result["variance_expired"] == 1

        conn = get_connection(tmp_db)
        row = conn.execute(
            "SELECT status FROM variance_approval_requests"
        ).fetchone()
        assert row["status"] == "expired"
        conn.close()

    def test_detects_overdue_quarantine_returns(self, tmp_db):
        from src.database import get_connection
        store, user = _seed_minimal(tmp_db)
        conn = get_connection(tmp_db)

        # Insert batch + ticket + quarantine
        cursor = conn.execute(
            "INSERT INTO batches (store_id, batch_code, status) VALUES (?, ?, ?)",
            (store.id, "B1", "quarantined"),
        )
        batch_id = cursor.lastrowid

        cursor = conn.execute(
            "INSERT INTO buyback_tickets (store_id, created_by_user_id, "
            "customer_name, clothing_category, condition_grade, "
            "estimated_weight_lbs, estimated_base_rate, estimated_bonus_pct, "
            "estimated_payout, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (store.id, user.id, "J", "shirts", "A", 10.0, 1.5, 0, 15.0, "awaiting_qc"),
        )
        ticket_id = cursor.lastrowid

        overdue = _isoformat(datetime.now(timezone.utc) - timedelta(days=10))
        conn.execute(
            "INSERT INTO quarantine_records (ticket_id, batch_id, "
            "created_by_user_id, disposition, due_back_to_customer_at, "
            "resolved_at) VALUES (?, ?, ?, ?, ?, ?)",
            (ticket_id, batch_id, user.id, "return_to_customer", overdue, None),
        )
        conn.commit()
        conn.close()

        result = run_expiration_sweep(tmp_db)
        assert result["quarantines_overdue"] == 1


# ── Concurrency / idempotency ──

class TestConcurrencyGuards:
    def test_duplicate_variance_approval_rejected(self, tmp_db):
        """Second approval attempt on an already-executed request must fail."""
        from src.database import get_connection
        store, user = _seed_minimal(tmp_db)
        conn = get_connection(tmp_db)

        # Create another user to be the requester (different from approver)
        requester = UserRepository(conn).create(User(
            store_id=store.id, username="agent", password_hash="x",
            display_name="Agent", role=UserRole.FRONT_DESK_AGENT,
        ))

        # Insert a pending variance approval
        cursor = conn.execute(
            "INSERT INTO buyback_tickets (store_id, created_by_user_id, "
            "customer_name, clothing_category, condition_grade, "
            "estimated_weight_lbs, estimated_base_rate, estimated_bonus_pct, "
            "estimated_payout, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (store.id, requester.id, "J", "shirts", "A", 10.0, 1.5, 0, 15.0,
             "variance_pending_supervisor"),
        )
        ticket_id = cursor.lastrowid

        cursor = conn.execute(
            "INSERT INTO variance_approval_requests "
            "(ticket_id, requested_by_user_id, variance_amount, variance_pct, "
            "threshold_amount, threshold_pct, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ticket_id, requester.id, 10.0, 10.0, 5.0, 5.0, "pending"),
        )
        request_id = cursor.lastrowid
        conn.commit()

        # Use the repo's try_execute_approval — should succeed first time
        variance_repo = VarianceApprovalRequestRepository(conn)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        assert variance_repo.try_execute_approval(request_id, user.id, now) is True
        conn.commit()

        # Second attempt must fail (no rows match 'pending')
        assert variance_repo.try_execute_approval(request_id, user.id, now) is False

        conn.close()

    def test_duplicate_export_execution_rejected(self, tmp_db):
        from src.database import get_connection
        store, user = _seed_minimal(tmp_db)
        conn = get_connection(tmp_db)

        # Insert an approved export
        cursor = conn.execute(
            "INSERT INTO export_requests (store_id, requested_by_user_id, "
            "export_type, status) VALUES (?, ?, ?, ?)",
            (store.id, user.id, "tickets", "approved"),
        )
        request_id = cursor.lastrowid
        conn.commit()

        export_repo = ExportRequestRepository(conn)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # First execution — succeeds
        assert export_repo.try_execute(request_id, now) is True
        conn.commit()

        # Second execution — must fail (status is now 'completed')
        assert export_repo.try_execute(request_id, now) is False

        conn.close()

    def test_duplicate_export_approval_rejected(self, tmp_db):
        from src.database import get_connection
        store, user = _seed_minimal(tmp_db)
        conn = get_connection(tmp_db)

        cursor = conn.execute(
            "INSERT INTO export_requests (store_id, requested_by_user_id, "
            "export_type, status) VALUES (?, ?, ?, ?)",
            (store.id, user.id, "tickets", "pending"),
        )
        request_id = cursor.lastrowid
        conn.commit()

        export_repo = ExportRequestRepository(conn)

        assert export_repo.try_approve(request_id, user.id) is True
        conn.commit()

        # Second approval attempt — must fail (status is now 'approved')
        assert export_repo.try_approve(request_id, user.id) is False
        # And reject also fails (status is 'approved', not 'pending')
        assert export_repo.try_reject(request_id, user.id) is False
        conn.close()

    def test_ticket_status_transition_is_conditional(self, tmp_db):
        from src.database import get_connection
        store, user = _seed_minimal(tmp_db)
        conn = get_connection(tmp_db)

        cursor = conn.execute(
            "INSERT INTO buyback_tickets (store_id, created_by_user_id, "
            "customer_name, clothing_category, condition_grade, "
            "estimated_weight_lbs, estimated_base_rate, estimated_bonus_pct, "
            "estimated_payout, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (store.id, user.id, "J", "shirts", "A", 10.0, 1.5, 0, 15.0,
             "variance_pending_supervisor"),
        )
        ticket_id = cursor.lastrowid
        conn.commit()

        ticket_repo = BuybackTicketRepository(conn)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # First transition — succeeds
        assert ticket_repo.try_transition_status(
            ticket_id, "variance_pending_supervisor", "completed", completed_at=now,
        ) is True
        conn.commit()

        # Second attempt with same from_status — fails
        assert ticket_repo.try_transition_status(
            ticket_id, "variance_pending_supervisor", "completed",
        ) is False

        # Stale from_status — also fails
        assert ticket_repo.try_transition_status(
            ticket_id, "awaiting_qc", "completed",
        ) is False

        conn.close()

    def test_schedule_approval_idempotent(self, tmp_db):
        from src.database import get_connection
        store, user = _seed_minimal(tmp_db)
        conn = get_connection(tmp_db)

        cursor = conn.execute(
            "INSERT INTO schedule_adjustment_requests "
            "(store_id, requested_by_user_id, adjustment_type, "
            "target_entity_type, target_entity_id, before_value, "
            "after_value, reason, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (store.id, user.id, "retry_timing", "ticket_message_log",
             "1", "30m", "60m", "Test", "pending"),
        )
        request_id = cursor.lastrowid
        conn.commit()

        repo = ScheduleAdjustmentRequestRepository(conn)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        assert repo.try_execute_approval(request_id, user.id, now) is True
        conn.commit()
        # Second call — must fail
        assert repo.try_execute_approval(request_id, user.id, now) is False
        conn.close()


# ── Startup reconciliation ──

class TestStartupReconciliation:
    def test_app_startup_runs_sweep(self, tmp_db, monkeypatch):
        """create_app() must call run_expiration_sweep as reconciliation."""
        monkeypatch.setenv("RECLAIM_OPS_DEV_MODE", "true")
        monkeypatch.setenv("RECLAIM_OPS_REQUIRE_TLS", "false")
        monkeypatch.setenv("SECURE_COOKIES", "false")
        from src.database import get_connection

        # Pre-seed with expired data BEFORE app starts
        conn = get_connection(tmp_db)
        store = StoreRepository(conn).create(Store(code="S1", name="T"))
        user = UserRepository(conn).create(User(
            store_id=store.id, username="u", password_hash="x",
            display_name="U", role="administrator",
        ))
        old_ts = _isoformat(datetime.now(timezone.utc) - timedelta(hours=48))
        conn.execute(
            "INSERT INTO export_requests (store_id, requested_by_user_id, "
            "export_type, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (store.id, user.id, "tickets", "pending", old_ts),
        )
        conn.commit()
        conn.close()

        # Now start the app — reconciliation should expire the stale request
        from app import create_app
        create_app(db_path=tmp_db)

        conn = get_connection(tmp_db)
        row = conn.execute(
            "SELECT status FROM export_requests"
        ).fetchone()
        assert row["status"] == "expired"
        conn.close()


# ── Close_db rollback ──

class TestRequestRollback:
    def test_close_db_rolls_back_on_error(self, tmp_db, monkeypatch):
        """A request that raises must NOT persist writes via auto-commit."""
        monkeypatch.setenv("RECLAIM_OPS_DEV_MODE", "true")
        monkeypatch.setenv("RECLAIM_OPS_REQUIRE_TLS", "false")
        monkeypatch.setenv("SECURE_COOKIES", "false")
        from app import create_app
        app = create_app(db_path=tmp_db)
        # Do NOT set TESTING — that propagates exceptions instead of running
        # the teardown handler. We need the teardown (close_db) to fire with
        # an error so we can verify rollback behavior.
        app.config["PROPAGATE_EXCEPTIONS"] = False

        # Seed a store so we have something identifiable
        from src.database import get_connection
        conn = get_connection(tmp_db)
        StoreRepository(conn).create(Store(code="BEFORE", name="Before"))
        conn.commit()
        conn.close()

        from flask import g

        @app.route("/test-fail", methods=["POST"])
        def test_fail():
            from app import get_db
            g.db_path = app.config["DB_PATH"]
            db = get_db()
            StoreRepository(db).create(Store(code="SHOULD_ROLLBACK", name="rollback"))
            raise RuntimeError("simulated failure")

        with app.test_client() as c:
            resp = c.post("/test-fail")
            assert resp.status_code == 500

        # Verify the write was rolled back
        conn = get_connection(tmp_db)
        row = conn.execute(
            "SELECT * FROM stores WHERE code = 'SHOULD_ROLLBACK'"
        ).fetchone()
        assert row is None
        # But the BEFORE row still exists
        row = conn.execute(
            "SELECT * FROM stores WHERE code = 'BEFORE'"
        ).fetchone()
        assert row is not None
        conn.close()
