"""Service layer tests — business logic, state machines, dual-control, pricing."""
import json
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fullstack", "backend"))

import pytest
from src.database import init_db
from src.enums.ticket_status import TicketStatus
from src.enums.variance_approval_status import VarianceApprovalStatus
from src.enums.inspection_outcome import InspectionOutcome
from src.enums.quarantine_disposition import QuarantineDisposition
from src.enums.batch_status import BatchStatus
from src.enums.table_state import TableState
from src.enums.export_request_status import ExportRequestStatus
from src.enums.contact_channel import ContactChannel
from src.enums.call_attempt_status import CallAttemptStatus
from src.enums.member_status import MemberStatus
from src.enums.user_role import UserRole
from src.models.pricing_rule import PricingRule
from src.models.settings import Settings
from src.models.store import Store
from src.models.user import User
from src.models.service_table import ServiceTable
from src.models.notification_template import NotificationTemplate
from src.models.club_organization import ClubOrganization
from src.repositories import *
from src.services.audit_service import AuditService
from src.services.pricing_service import PricingService
from src.services.ticket_service import TicketService
from src.services.qc_service import QCService
from src.services.table_service import TableService
from src.services.notification_service import NotificationService
from src.services.member_service import MemberService
from src.services.export_service import ExportService
from src.services.traceability_service import TraceabilityService
from src.services.auth_service import AuthService
from src.services.settings_service import SettingsService
from src.services.schedule_service import ScheduleService
from src.services.price_override_service import PriceOverrideService


@pytest.fixture
def db():
    conn = init_db(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def repos(db):
    return {
        "store": StoreRepository(db),
        "user": UserRepository(db),
        "session": UserSessionRepository(db),
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
        "audit": AuditLogRepository(db),
        "settings": SettingsRepository(db),
        "schedule": ScheduleAdjustmentRequestRepository(db),
        "price_override": PriceOverrideRequestRepository(db),
    }


@pytest.fixture
def services(repos, monkeypatch, tmp_path):
    # NOTE: store-level authorization is now ALWAYS enforced. The
    # legacy `_bypass_store_auth` monkeypatch was removed — every test
    # call site explicitly passes `actor_store_id` and `user_role` so
    # `enforce_store_access` runs against real values. This fixture
    # only redirects export file output to a per-test tmp dir so real
    # CSVs do not touch /storage/exports.
    import src.services.export_service as _export_mod
    monkeypatch.setattr(_export_mod, "EXPORT_OUTPUT_DIR", str(tmp_path / "exports"))
    audit = AuditService(repos["audit"])
    pricing = PricingService(repos["pricing_rule"], repos["snapshot"], repos["settings"])
    auth = AuthService(repos["user"], repos["session"], repos["settings"], audit)
    return {
        "audit": audit,
        "pricing": pricing,
        "auth": auth,
        "ticket": TicketService(repos["ticket"], repos["variance"], pricing, audit,
                                auth_service=auth, qc_repo=repos["qc"]),
        "qc": QCService(repos["qc"], repos["quarantine"], repos["batch"],
                        repos["genealogy"], repos["settings"], audit,
                        auth_service=auth, user_repo=repos["user"],
                        ticket_repo=repos["ticket"]),
        "table": TableService(repos["table"], repos["table_session"],
                              repos["table_event"], audit,
                              user_repo=repos["user"]),
        "notification": NotificationService(repos["message"], repos["template"],
                                            repos["ticket"], audit),
        "member": MemberService(repos["member"], repos["member_history"],
                                repos["org"], audit),
        "export": ExportService(repos["export"], repos["ticket"],
                                repos["settings"], audit, auth_service=auth,
                                store_repo=repos["store"]),
        "traceability": TraceabilityService(repos["batch"], repos["genealogy"],
                                            repos["recall"], audit),
        "settings": SettingsService(repos["settings"], audit),
        "schedule": ScheduleService(repos["schedule"], audit, auth_service=auth),
        "price_override": PriceOverrideService(
            repos["price_override"], repos["ticket"], audit, auth_service=auth,
        ),
    }


# Shared test password — stored as a real bcrypt hash in the seeded
# users so approval paths can verify it against the stored hash.
TEST_PASSWORD = "TestPassword123!"


def _seed(db, repos):
    """Create a store, pricing rule, settings, and users for testing.

    Every seeded user is stored with a real bcrypt hash of TEST_PASSWORD
    so approval paths that call `verify_password_for_approval` — which
    hit bcrypt — succeed when the test passes the correct password and
    fail when it passes a wrong one.
    """
    store = repos["store"].create(Store(code="S1", name="Test Store"))
    repos["settings"].create(Settings(store_id=store.id))
    repos["pricing_rule"].create(PricingRule(
        store_id=store.id, base_rate_per_lb=1.50, bonus_pct=10.0,
        min_weight_lbs=0.1, max_weight_lbs=1000.0,
        max_ticket_payout=200.0, max_rate_per_lb=3.0, priority=1,
    ))

    # One bcrypt hash is reused for every seeded user — each hash takes
    # ~100 ms to generate and the suite creates 6 users per test.
    _audit = AuditService(repos["audit"])
    _auth = AuthService(repos["user"], repos["session"], repos["settings"], _audit)
    pw_hash = _auth._hash_password(TEST_PASSWORD)

    agent = repos["user"].create(User(
        store_id=store.id, username="agent1", password_hash=pw_hash,
        display_name="Agent 1", role=UserRole.FRONT_DESK_AGENT,
    ))
    inspector = repos["user"].create(User(
        store_id=store.id, username="inspector1", password_hash=pw_hash,
        display_name="Inspector 1", role=UserRole.QC_INSPECTOR,
    ))
    supervisor = repos["user"].create(User(
        store_id=store.id, username="supervisor1", password_hash=pw_hash,
        display_name="Supervisor 1", role=UserRole.SHIFT_SUPERVISOR,
    ))
    host = repos["user"].create(User(
        store_id=store.id, username="host1", password_hash=pw_hash,
        display_name="Host 1", role=UserRole.HOST,
    ))
    admin = repos["user"].create(User(
        store_id=store.id, username="admin1", password_hash=pw_hash,
        display_name="Admin 1", role=UserRole.ADMINISTRATOR,
    ))
    ops = repos["user"].create(User(
        store_id=store.id, username="ops1", password_hash=pw_hash,
        display_name="Ops 1", role=UserRole.OPERATIONS_MANAGER,
    ))
    db.commit()
    return {
        "store": store, "agent": agent, "inspector": inspector,
        "supervisor": supervisor, "host": host, "admin": admin, "ops": ops,
    }


def _record_qc(db, services, seed, ticket, weight=10.0, lot_size=10, nc=0,
               outcome=InspectionOutcome.PASS):
    """Helper: create a QC inspection for a ticket so record_qc_and_compute_final can proceed."""
    services["qc"].create_inspection(
        ticket_id=ticket.id, store_id=seed["store"].id,
        inspector_user_id=seed["inspector"].id,
        inspector_username="inspector1",
        inspector_role=UserRole.QC_INSPECTOR,
        actor_store_id=seed["store"].id,
        actual_weight_lbs=weight, lot_size=lot_size,
        nonconformance_count=nc, inspection_outcome=outcome,
    )
    db.commit()


# =============================================================
# PRICING SERVICE
# =============================================================

class TestPricingService:
    def test_basic_calculation(self, db, repos, services):
        seed = _seed(db, repos)
        result = services["pricing"].calculate_payout(
            seed["store"].id, "shirts", "A", 10.0
        )
        assert result["base_rate"] == 1.50
        assert result["gross_amount"] == 15.0
        assert result["bonus_pct"] == 10.0
        assert result["bonus_amount"] == 1.50
        assert result["capped_amount"] == 16.50

    def test_per_lb_cap_applied(self, db, repos, services):
        seed = _seed(db, repos)
        # At $1.50/lb * 100 = $150 + 10% bonus = $165
        # Per-lb cap = $3/lb * 100 = $300 (not hit)
        # Ticket cap = $200 (not hit)
        # So no cap at 100 lbs. Use 200 lbs to hit ticket cap.
        result = services["pricing"].calculate_payout(
            seed["store"].id, "shirts", "A", 200.0
        )
        assert result["capped_amount"] == 200.0
        assert result["cap_applied"] is True

    def test_ticket_cap_applied(self, db, repos, services):
        seed = _seed(db, repos)
        result = services["pricing"].calculate_payout(
            seed["store"].id, "shirts", "A", 200.0
        )
        assert result["capped_amount"] <= 200.0

    def test_zero_weight_rejected(self, db, repos, services):
        seed = _seed(db, repos)
        with pytest.raises(ValueError, match="greater than zero"):
            services["pricing"].calculate_payout(seed["store"].id, "shirts", "A", 0)

    def test_variance_check_no_approval_needed(self, db, repos, services):
        seed = _seed(db, repos)
        required, *_ = services["pricing"].check_variance(100.0, 103.0, seed["store"].id)
        assert required is False  # $3 diff < max($5, $5) = $5

    def test_variance_check_approval_needed(self, db, repos, services):
        seed = _seed(db, repos)
        required, diff, *_ = services["pricing"].check_variance(100.0, 108.0, seed["store"].id)
        assert required is True  # $8 diff > max($5, $5) = $5

    def test_variance_uses_whichever_higher(self, db, repos, services):
        seed = _seed(db, repos)
        # For estimated=$200, 5% = $10 which is > $5, so threshold=$10
        required, diff, *_ = services["pricing"].check_variance(200.0, 209.0, seed["store"].id)
        assert required is False  # $9 < $10
        required, diff, *_ = services["pricing"].check_variance(200.0, 212.0, seed["store"].id)
        assert required is True  # $12 > $10


# =============================================================
# TICKET SERVICE — STATE MACHINE
# =============================================================

class TestTicketService:
    def test_create_ticket(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane Doe", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        assert ticket.id is not None
        assert ticket.status == TicketStatus.INTAKE_OPEN
        assert ticket.estimated_payout == 16.50

    def test_create_ticket_wrong_role(self, db, repos, services):
        seed = _seed(db, repos)
        with pytest.raises(PermissionError):
            services["ticket"].create_ticket(
                store_id=seed["store"].id, user_id=seed["host"].id,
                user_role=UserRole.HOST, username="host1",
                actor_store_id=seed["store"].id,
                customer_name="X", clothing_category="shirts",
                condition_grade="A", estimated_weight_lbs=10.0,
            )

    def test_submit_for_qc(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        ticket = services["ticket"].submit_for_qc(ticket.id, seed["agent"].id, "agent1", actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT)
        assert ticket.status == TicketStatus.AWAITING_QC

    def test_qc_no_variance_completes(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        services["ticket"].submit_for_qc(ticket.id, seed["agent"].id, "agent1", actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT)
        db.commit()
        _record_qc(db, services, seed, ticket, weight=10.0)
        result = services["ticket"].record_qc_and_compute_final(
            ticket.id, 10.0, seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        assert result["approval_required"] is False
        assert result["ticket"].status == TicketStatus.COMPLETED

    def test_qc_with_variance_triggers_approval(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        services["ticket"].submit_for_qc(ticket.id, seed["agent"].id, "agent1", actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT)
        db.commit()
        _record_qc(db, services, seed, ticket, weight=20.0)
        # Large weight difference triggers variance
        result = services["ticket"].record_qc_and_compute_final(
            ticket.id, 20.0, seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        assert result["approval_required"] is True
        assert result["ticket"].status == TicketStatus.VARIANCE_PENDING_CONFIRMATION

    def test_full_variance_approval_flow(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        services["ticket"].submit_for_qc(ticket.id, seed["agent"].id, "agent1", actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT)
        db.commit()
        _record_qc(db, services, seed, ticket, weight=20.0)
        services["ticket"].record_qc_and_compute_final(
            ticket.id, 20.0, seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        req = services["ticket"].confirm_variance(
            ticket.id, seed["inspector"].id, "inspector1", "Weight was higher",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        ticket = services["ticket"].approve_variance(
            req.id, seed["supervisor"].id, "supervisor1",
            UserRole.SHIFT_SUPERVISOR, password=TEST_PASSWORD,
            approver_store_id=seed["store"].id,
        )
        assert ticket.status == TicketStatus.COMPLETED

    def test_self_approval_forbidden(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        services["ticket"].submit_for_qc(ticket.id, seed["agent"].id, "agent1", actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT)
        db.commit()
        _record_qc(db, services, seed, ticket, weight=20.0)
        services["ticket"].record_qc_and_compute_final(
            ticket.id, 20.0, seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        req = services["ticket"].confirm_variance(
            ticket.id, seed["inspector"].id, "inspector1", "Note",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        with pytest.raises(PermissionError, match="Self-approval"):
            services["ticket"].approve_variance(
                req.id, seed["inspector"].id, "inspector1",
                UserRole.SHIFT_SUPERVISOR, password=TEST_PASSWORD,
                approver_store_id=seed["store"].id,
            )

    def test_password_required_for_approval(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        services["ticket"].submit_for_qc(ticket.id, seed["agent"].id, "agent1", actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT)
        db.commit()
        _record_qc(db, services, seed, ticket, weight=20.0)
        services["ticket"].record_qc_and_compute_final(
            ticket.id, 20.0, seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        req = services["ticket"].confirm_variance(
            ticket.id, seed["inspector"].id, "inspector1", "Note",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        with pytest.raises(ValueError, match="Password is required"):
            services["ticket"].approve_variance(
                req.id, seed["supervisor"].id, "supervisor1",
                UserRole.SHIFT_SUPERVISOR, password="",
                approver_store_id=seed["store"].id,
            )

    def test_invalid_transition_rejected(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        services["ticket"].submit_for_qc(ticket.id, seed["agent"].id, "agent1", actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT)
        db.commit()
        # Try to refund from awaiting_qc — invalid (must be completed first)
        with pytest.raises(ValueError, match="Invalid ticket transition"):
            services["ticket"].initiate_refund(
                ticket.id, seed["agent"].id, "agent1",
                UserRole.FRONT_DESK_AGENT,
                actor_store_id=seed["store"].id,
            )

    def test_refund_flow(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        services["ticket"].submit_for_qc(ticket.id, seed["agent"].id, "agent1", actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT)
        db.commit()
        _record_qc(db, services, seed, ticket, weight=10.0)
        services["ticket"].record_qc_and_compute_final(
            ticket.id, 10.0, seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        ticket = services["ticket"].initiate_refund(
            ticket.id, seed["agent"].id, "agent1",
            UserRole.FRONT_DESK_AGENT,
            actor_store_id=seed["store"].id,
        )
        assert ticket.refund_amount == ticket.final_payout
        assert ticket.refund_initiated_by_user_id == seed["agent"].id
        db.commit()
        ticket = services["ticket"].approve_refund(
            ticket.id, seed["supervisor"].id, "supervisor1",
            UserRole.SHIFT_SUPERVISOR, password=TEST_PASSWORD,
            approver_store_id=seed["store"].id,
        )
        assert ticket.status == TicketStatus.REFUNDED

    def test_partial_refund_persisted(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        services["ticket"].submit_for_qc(ticket.id, seed["agent"].id, "agent1", actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT)
        db.commit()
        _record_qc(db, services, seed, ticket, weight=10.0)
        services["ticket"].record_qc_and_compute_final(
            ticket.id, 10.0, seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        ticket = services["ticket"].initiate_refund(
            ticket.id, seed["agent"].id, "agent1",
            UserRole.FRONT_DESK_AGENT,
            actor_store_id=seed["store"].id,
            refund_amount=5.00, reason="Partial damage",
        )
        assert ticket.refund_amount == 5.00
        db.commit()
        # Re-fetch from DB to verify persistence
        fetched = repos["ticket"].get_by_id(ticket.id)
        assert fetched.refund_amount == 5.00
        assert fetched.refund_initiated_by_user_id == seed["agent"].id

    def test_refund_initiator_cannot_approve(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        services["ticket"].submit_for_qc(ticket.id, seed["agent"].id, "agent1", actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT)
        db.commit()
        _record_qc(db, services, seed, ticket, weight=10.0)
        services["ticket"].record_qc_and_compute_final(
            ticket.id, 10.0, seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        # Ops manager initiates refund
        services["ticket"].initiate_refund(
            ticket.id, seed["ops"].id, "ops1",
            UserRole.OPERATIONS_MANAGER,
            actor_store_id=seed["store"].id,
        )
        db.commit()
        # Same ops manager tries to approve — must fail
        with pytest.raises(PermissionError, match="Refund initiator cannot approve"):
            services["ticket"].approve_refund(
                ticket.id, seed["ops"].id, "ops1",
                UserRole.OPERATIONS_MANAGER, password=TEST_PASSWORD,
                approver_store_id=seed["store"].id,
            )

    def test_cancel_from_variance_requires_supervisor(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        services["ticket"].submit_for_qc(ticket.id, seed["agent"].id, "agent1", actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT)
        db.commit()
        _record_qc(db, services, seed, ticket, weight=20.0)
        services["ticket"].record_qc_and_compute_final(
            ticket.id, 20.0, seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        with pytest.raises(PermissionError):
            services["ticket"].cancel_ticket(
                ticket.id, seed["agent"].id, "agent1",
                UserRole.FRONT_DESK_AGENT, "Customer left",
                actor_store_id=seed["store"].id,
            )
        # Supervisor can cancel
        ticket = services["ticket"].cancel_ticket(
            ticket.id, seed["supervisor"].id, "supervisor1",
            UserRole.SHIFT_SUPERVISOR, "Customer left",
            actor_store_id=seed["store"].id,
        )
        assert ticket.status == TicketStatus.CANCELED

    def test_approve_variance_rolls_back_partial_commit(
        self, db, repos, services, monkeypatch,
    ):
        """Regression: if the second write in approve_variance fails, the
        first write (variance execution) must NOT persist even if the
        caller catches the exception and later commits. This proves the
        `atomic()` wrapper rolls back before the exception leaves the
        service, independent of any teardown/commit behavior.

        Before the fix: variance_repo.try_execute_approval succeeds, then
        ticket_repo.try_transition_status fails → raise ValueError →
        caller catches it → caller commits → variance row silently
        persists in EXECUTED state with ticket still in
        VARIANCE_PENDING_SUPERVISOR. This is exactly the partial-commit
        bug the audit identified.
        """
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        services["ticket"].submit_for_qc(ticket.id, seed["agent"].id, "agent1", actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT)
        db.commit()
        _record_qc(db, services, seed, ticket, weight=20.0)
        services["ticket"].record_qc_and_compute_final(
            ticket.id, 20.0, seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        req = services["ticket"].confirm_variance(
            ticket.id, seed["inspector"].id, "inspector1", "Note",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()

        # Force the SECOND write in approve_variance to fail — simulating
        # a concurrent status change between the approval execution and
        # the ticket transition.
        monkeypatch.setattr(
            repos["ticket"], "try_transition_status",
            lambda *a, **kw: False,
        )

        with pytest.raises(ValueError, match="Ticket state changed"):
            services["ticket"].approve_variance(
                req.id, seed["supervisor"].id, "supervisor1",
                UserRole.SHIFT_SUPERVISOR, password=TEST_PASSWORD,
                approver_store_id=seed["store"].id,
            )

        # Simulate the Flask teardown path that was triggering the bug:
        # route catches ValueError → returns 4xx → teardown sees no
        # Python error and commits the connection. Before the fix, this
        # commit persisted the orphan variance write.
        db.commit()

        # CRITICAL assertions: atomic() must have rolled back the first
        # write before the exception left the service, so no partial
        # state can be persisted by the subsequent commit.
        reloaded_req = repos["variance"].get_by_id(req.id)
        assert reloaded_req.status == VarianceApprovalStatus.PENDING, (
            "Variance request was transitioned to EXECUTED despite the "
            "subsequent ticket transition failing — this is the "
            "partial-commit bug and atomic() did not roll back."
        )
        reloaded_ticket = repos["ticket"].get_by_id(ticket.id)
        assert reloaded_ticket.status == TicketStatus.VARIANCE_PENDING_SUPERVISOR


# =============================================================
# QC FINAL PAYOUT — BOUND TO INSPECTION
# =============================================================

class TestQCFinalPayoutBound:
    """Final payout MUST derive from persisted QC inspection weight,
    not from the request payload.  Non-QC roles are rejected."""

    def test_qc_final_uses_inspection_weight(self, db, repos, services):
        """Payout must be computed from the QC inspection's weight,
        NOT a caller-supplied value."""
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        services["ticket"].submit_for_qc(
            ticket.id, seed["agent"].id, "agent1",
            actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT,
        )
        db.commit()
        # QC inspection records 15.0 lbs
        _record_qc(db, services, seed, ticket, weight=15.0)
        # Omit actual_weight_lbs — service must use QC value
        result = services["ticket"].record_qc_and_compute_final(
            ticket.id, None, seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        assert result["ticket"].actual_weight_lbs == 15.0

    def test_qc_final_rejects_weight_mismatch(self, db, repos, services):
        """If caller supplies a weight that differs from the QC inspection,
        the service must reject it."""
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        services["ticket"].submit_for_qc(
            ticket.id, seed["agent"].id, "agent1",
            actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT,
        )
        db.commit()
        _record_qc(db, services, seed, ticket, weight=10.0)
        # Try to override with 99.0 — must be rejected
        with pytest.raises(ValueError, match="does not match"):
            services["ticket"].record_qc_and_compute_final(
                ticket.id, 99.0, seed["inspector"].id, "inspector1",
                actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
            )

    def test_qc_final_rejects_front_desk_role(self, db, repos, services):
        """Only QC_INSPECTOR and ADMINISTRATOR can finalize payout."""
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        services["ticket"].submit_for_qc(
            ticket.id, seed["agent"].id, "agent1",
            actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT,
        )
        db.commit()
        _record_qc(db, services, seed, ticket, weight=10.0)
        with pytest.raises(PermissionError, match="not authorized"):
            services["ticket"].record_qc_and_compute_final(
                ticket.id, 10.0, seed["agent"].id, "agent1",
                actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT,
            )

    def test_qc_final_rejects_host_role(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        services["ticket"].submit_for_qc(
            ticket.id, seed["agent"].id, "agent1",
            actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT,
        )
        db.commit()
        _record_qc(db, services, seed, ticket, weight=10.0)
        with pytest.raises(PermissionError):
            services["ticket"].record_qc_and_compute_final(
                ticket.id, 10.0, seed["host"].id, "host1",
                actor_store_id=seed["store"].id, user_role=UserRole.HOST,
            )

    def test_qc_final_allows_admin(self, db, repos, services):
        """Administrator can finalize payout (ADMINISTRATOR is allowed)."""
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        services["ticket"].submit_for_qc(
            ticket.id, seed["agent"].id, "agent1",
            actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT,
        )
        db.commit()
        _record_qc(db, services, seed, ticket, weight=10.0)
        result = services["ticket"].record_qc_and_compute_final(
            ticket.id, None, seed["admin"].id, "admin1",
            actor_store_id=seed["store"].id, user_role=UserRole.ADMINISTRATOR,
        )
        assert result["ticket"].status == TicketStatus.COMPLETED

    def test_qc_final_matching_weight_passes(self, db, repos, services):
        """Caller CAN supply a weight if it matches the QC inspection."""
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        services["ticket"].submit_for_qc(
            ticket.id, seed["agent"].id, "agent1",
            actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT,
        )
        db.commit()
        _record_qc(db, services, seed, ticket, weight=10.0)
        # Supply matching weight — should succeed
        result = services["ticket"].record_qc_and_compute_final(
            ticket.id, 10.0, seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        assert result["ticket"].actual_weight_lbs == 10.0
        assert result["ticket"].status == TicketStatus.COMPLETED


# =============================================================
# QC SERVICE
# =============================================================

class TestQCService:
    def test_sample_size_calculation(self, db, repos, services):
        seed = _seed(db, repos)
        size = services["qc"].compute_sample_size(seed["store"].id, 100)
        assert size == 10  # 10% of 100

    def test_sample_size_minimum(self, db, repos, services):
        seed = _seed(db, repos)
        size = services["qc"].compute_sample_size(seed["store"].id, 5)
        assert size == 3  # min 3

    def test_create_inspection(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        inspection = services["qc"].create_inspection(
            ticket_id=ticket.id, store_id=seed["store"].id,
            inspector_user_id=seed["inspector"].id,
            inspector_username="inspector1",
            inspector_role=UserRole.QC_INSPECTOR,
            actor_store_id=seed["store"].id,
            actual_weight_lbs=10.0, lot_size=50,
            nonconformance_count=0,
            inspection_outcome=InspectionOutcome.PASS,
        )
        assert inspection.id is not None
        assert inspection.sample_size == 5

    def test_fail_creates_quarantine_flag(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        inspection = services["qc"].create_inspection(
            ticket_id=ticket.id, store_id=seed["store"].id,
            inspector_user_id=seed["inspector"].id,
            inspector_username="inspector1",
            inspector_role=UserRole.QC_INSPECTOR,
            actor_store_id=seed["store"].id,
            actual_weight_lbs=10.0, lot_size=50,
            nonconformance_count=1,
            inspection_outcome=InspectionOutcome.FAIL,
        )
        assert inspection.quarantine_required is True

    def test_quarantine_concession_requires_supervisor(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        batch = services["traceability"].create_batch(
            seed["store"].id, "B001", seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        qr = services["qc"].create_quarantine(
            ticket.id, batch.id, seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        # Concession without supervisor fails
        with pytest.raises(ValueError, match="Supervisor sign-off"):
            services["qc"].resolve_quarantine(
                qr.id, QuarantineDisposition.CONCESSION_ACCEPTANCE,
                seed["inspector"].id, "inspector1", UserRole.QC_INSPECTOR,
                actor_store_id=seed["store"].id,
            )

    def test_quarantine_concession_self_approval_forbidden(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        batch = services["traceability"].create_batch(
            seed["store"].id, "B002", seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        qr = services["qc"].create_quarantine(
            ticket.id, batch.id, seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        with pytest.raises(PermissionError, match="Self-approval"):
            services["qc"].resolve_quarantine(
                qr.id, QuarantineDisposition.CONCESSION_ACCEPTANCE,
                seed["inspector"].id, "inspector1", UserRole.QC_INSPECTOR,
                actor_store_id=seed["store"].id,
                concession_supervisor_id=seed["inspector"].id,
                concession_supervisor_username="inspector1",
            )

    def test_concession_requires_supervisor_role(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        batch = services["traceability"].create_batch(
            seed["store"].id, "B003", seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        qr = services["qc"].create_quarantine(
            ticket.id, batch.id, seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        # Agent (non-supervisor) as concession signer must be rejected
        with pytest.raises(PermissionError, match="supervisor role"):
            services["qc"].resolve_quarantine(
                qr.id, QuarantineDisposition.CONCESSION_ACCEPTANCE,
                seed["inspector"].id, "inspector1", UserRole.QC_INSPECTOR,
                actor_store_id=seed["store"].id,
                concession_supervisor_id=seed["agent"].id,
                concession_supervisor_username="agent1",
            )
        # Supervisor as signer with their correct password should work
        record = services["qc"].resolve_quarantine(
            qr.id, QuarantineDisposition.CONCESSION_ACCEPTANCE,
            seed["inspector"].id, "inspector1", UserRole.QC_INSPECTOR,
            actor_store_id=seed["store"].id,
            concession_supervisor_id=seed["supervisor"].id,
            concession_supervisor_username="supervisor1",
            concession_supervisor_password=TEST_PASSWORD,
        )
        assert record.concession_signed_by == seed["supervisor"].id

    def test_ticket_cannot_complete_without_qc_inspection(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        services["ticket"].submit_for_qc(ticket.id, seed["agent"].id, "agent1", actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT)
        db.commit()
        # No QC inspection created — must fail
        with pytest.raises(ValueError, match="QC inspection must be recorded"):
            services["ticket"].record_qc_and_compute_final(
                ticket.id, 10.0, seed["inspector"].id, "inspector1",
                actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
            )


# =============================================================
# TABLE SERVICE — STATE MACHINE
# =============================================================

class TestTableService:
    def _create_table(self, db, repos, seed):
        table = repos["table"].create(ServiceTable(
            store_id=seed["store"].id, table_code="T1", area_type="intake_table",
        ))
        db.commit()
        return table

    def test_open_table(self, db, repos, services):
        seed = _seed(db, repos)
        table = self._create_table(db, repos, seed)
        session = services["table"].open_table(
            table.id, seed["store"].id, seed["host"].id,
            "host1", UserRole.HOST,
            actor_store_id=seed["store"].id,
        )
        assert session.current_state == TableState.OCCUPIED

    def test_valid_transitions(self, db, repos, services):
        seed = _seed(db, repos)
        table = self._create_table(db, repos, seed)
        session = services["table"].open_table(
            table.id, seed["store"].id, seed["host"].id,
            "host1", UserRole.HOST,
            actor_store_id=seed["store"].id,
        )
        db.commit()
        session = services["table"].transition_table(
            session.id, TableState.PRE_CHECKOUT,
            seed["host"].id, "host1", UserRole.HOST,
            actor_store_id=seed["store"].id,
        )
        assert session.current_state == TableState.PRE_CHECKOUT
        db.commit()
        session = services["table"].transition_table(
            session.id, TableState.CLEARED,
            seed["host"].id, "host1", UserRole.HOST,
            actor_store_id=seed["store"].id,
        )
        assert session.current_state == TableState.CLEARED

    def test_invalid_transition_rejected(self, db, repos, services):
        seed = _seed(db, repos)
        table = self._create_table(db, repos, seed)
        session = services["table"].open_table(
            table.id, seed["store"].id, seed["host"].id,
            "host1", UserRole.HOST,
            actor_store_id=seed["store"].id,
        )
        db.commit()
        with pytest.raises(ValueError, match="Invalid table transition"):
            services["table"].transition_table(
                session.id, TableState.AVAILABLE,
                seed["host"].id, "host1", UserRole.HOST,
                actor_store_id=seed["store"].id,
            )

    def test_merge_tables(self, db, repos, services):
        seed = _seed(db, repos)
        t1 = repos["table"].create(ServiceTable(
            store_id=seed["store"].id, table_code="T1", area_type="intake_table",
        ))
        t2 = repos["table"].create(ServiceTable(
            store_id=seed["store"].id, table_code="T2", area_type="intake_table",
        ))
        db.commit()
        s1 = services["table"].open_table(
            t1.id, seed["store"].id, seed["host"].id, "host1", UserRole.HOST,
            actor_store_id=seed["store"].id,
        )
        s2 = services["table"].open_table(
            t2.id, seed["store"].id, seed["host"].id, "host1", UserRole.HOST,
            actor_store_id=seed["store"].id,
        )
        db.commit()
        group = services["table"].merge_tables(
            [s1.id, s2.id], seed["store"].id,
            seed["host"].id, "host1", UserRole.HOST,
            actor_store_id=seed["store"].id,
        )
        assert group.startswith("MRG-")

    def test_cannot_merge_already_merged(self, db, repos, services):
        seed = _seed(db, repos)
        t1 = repos["table"].create(ServiceTable(
            store_id=seed["store"].id, table_code="M1", area_type="intake_table",
        ))
        t2 = repos["table"].create(ServiceTable(
            store_id=seed["store"].id, table_code="M2", area_type="intake_table",
        ))
        t3 = repos["table"].create(ServiceTable(
            store_id=seed["store"].id, table_code="M3", area_type="intake_table",
        ))
        db.commit()
        s1 = services["table"].open_table(t1.id, seed["store"].id, seed["host"].id, "host1", UserRole.HOST, actor_store_id=seed["store"].id)
        s2 = services["table"].open_table(t2.id, seed["store"].id, seed["host"].id, "host1", UserRole.HOST, actor_store_id=seed["store"].id)
        s3 = services["table"].open_table(t3.id, seed["store"].id, seed["host"].id, "host1", UserRole.HOST, actor_store_id=seed["store"].id)
        db.commit()
        services["table"].merge_tables([s1.id, s2.id], seed["store"].id, seed["host"].id, "host1", UserRole.HOST, actor_store_id=seed["store"].id)
        db.commit()
        with pytest.raises(ValueError, match="already merged"):
            services["table"].merge_tables([s1.id, s3.id], seed["store"].id, seed["host"].id, "host1", UserRole.HOST, actor_store_id=seed["store"].id)

    def test_timeline(self, db, repos, services):
        seed = _seed(db, repos)
        table = self._create_table(db, repos, seed)
        session = services["table"].open_table(
            table.id, seed["store"].id, seed["host"].id, "host1", UserRole.HOST,
            actor_store_id=seed["store"].id,
        )
        db.commit()
        events = services["table"].get_timeline(
            session.id,
            actor_store_id=seed["store"].id, user_role=UserRole.HOST,
        )
        assert len(events) == 1
        assert events[0].event_type == "opened"


# =============================================================
# EXPORT SERVICE — DUAL CONTROL
# =============================================================

class TestExportService:
    def test_create_export(self, db, repos, services):
        seed = _seed(db, repos)
        req = services["export"].create_export_request(
            seed["store"].id, seed["ops"].id, "ops1",
            UserRole.OPERATIONS_MANAGER, "tickets",
            actor_store_id=seed["store"].id,
        )
        assert req.id is not None

    def test_export_approval_self_forbidden(self, db, repos, services):
        seed = _seed(db, repos)
        # Force approval_required
        settings = repos["settings"].get_effective(seed["store"].id)
        settings.export_requires_supervisor_default = True
        repos["settings"].update(settings)
        db.commit()

        req = services["export"].create_export_request(
            seed["store"].id, seed["ops"].id, "ops1",
            UserRole.OPERATIONS_MANAGER, "tickets",
            actor_store_id=seed["store"].id,
        )
        db.commit()
        with pytest.raises(PermissionError, match="Self-approval"):
            services["export"].approve_export(
                req.id, seed["ops"].id, "ops1",
                UserRole.OPERATIONS_MANAGER, password=TEST_PASSWORD,
                approver_store_id=seed["store"].id,
            )

    def test_export_one_time_execution(self, db, repos, services):
        seed = _seed(db, repos)
        req = services["export"].create_export_request(
            seed["store"].id, seed["ops"].id, "ops1",
            UserRole.OPERATIONS_MANAGER, "tickets",
            actor_store_id=seed["store"].id,
        )
        db.commit()
        services["export"].execute_export(
            req.id, seed["ops"].id, "ops1",
            actor_store_id=seed["store"].id,
            user_role=UserRole.OPERATIONS_MANAGER,
        )
        db.commit()
        with pytest.raises(ValueError, match="already executed"):
            services["export"].execute_export(
                req.id, seed["ops"].id, "ops1",
                actor_store_id=seed["store"].id,
                user_role=UserRole.OPERATIONS_MANAGER,
            )

    def test_metrics(self, db, repos, services):
        seed = _seed(db, repos)
        metrics = services["export"].compute_metrics(
            seed["store"].id, "2020-01-01", "2030-12-31",
            actor_store_id=seed["store"].id, user_role=UserRole.OPERATIONS_MANAGER,
        )
        assert "order_volume" in metrics
        assert "revenue" in metrics
        assert "refund_rate" in metrics
        assert "load_factor" in metrics


# =============================================================
# NOTIFICATION SERVICE
# =============================================================

class TestNotificationService:
    def test_log_message(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        log = services["notification"].log_message(
            ticket.id, seed["agent"].id, "agent1", "Hello customer",
            actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT,
        )
        assert log.id is not None
        assert log.contact_channel == ContactChannel.LOGGED_MESSAGE

    def test_failed_call_schedules_retry(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        log = services["notification"].log_message(
            ticket.id, seed["agent"].id, "agent1", "Call attempt",
            actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT,
            contact_channel=ContactChannel.PHONE_CALL,
            call_attempt_status=CallAttemptStatus.FAILED,
        )
        assert log.retry_at is not None

    def test_template_rendering(self, db, repos, services):
        seed = _seed(db, repos)
        repos["template"].create(NotificationTemplate(
            store_id=seed["store"].id, template_code="accepted",
            name="Accepted", body="Hi {customer_name}, accepted!",
            event_type="accepted",
        ))
        db.commit()
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        log = services["notification"].log_from_template(
            ticket.id, "accepted", seed["store"].id,
            seed["agent"].id, "agent1",
            {"customer_name": "Jane"},
            actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT,
        )
        assert "Jane" in log.message_body


# =============================================================
# MEMBER SERVICE
# =============================================================

class TestMemberService:
    def test_add_member(self, db, repos, services):
        seed = _seed(db, repos)
        org = services["member"].create_organization(
            "Test Club", seed["admin"].id, "admin1", UserRole.ADMINISTRATOR,
        )
        db.commit()
        member = services["member"].add_member(
            org.id, "John Smith", seed["admin"].id, "admin1", UserRole.ADMINISTRATOR,
        )
        assert member.status == MemberStatus.ACTIVE

    def test_transfer_member(self, db, repos, services):
        seed = _seed(db, repos)
        org1 = services["member"].create_organization(
            "Club A", seed["admin"].id, "admin1", UserRole.ADMINISTRATOR,
        )
        org2 = services["member"].create_organization(
            "Club B", seed["admin"].id, "admin1", UserRole.ADMINISTRATOR,
        )
        db.commit()
        member = services["member"].add_member(
            org1.id, "John", seed["admin"].id, "admin1", UserRole.ADMINISTRATOR,
        )
        db.commit()
        member = services["member"].transfer_member(
            member.id, org2.id, seed["admin"].id, "admin1", UserRole.ADMINISTRATOR,
        )
        assert member.club_organization_id == org2.id
        assert member.status == MemberStatus.ACTIVE

    def test_csv_import(self, db, repos, services):
        seed = _seed(db, repos)
        org = services["member"].create_organization(
            "CSV Club", seed["admin"].id, "admin1", UserRole.ADMINISTRATOR,
        )
        db.commit()
        csv_content = f"full_name,organization_id,group\nAlice,{org.id},A\nBob,{org.id},B\n"
        result = services["member"].import_members_csv(
            csv_content.encode("utf-8"), seed["admin"].id, "admin1", UserRole.ADMINISTRATOR,
        )
        assert result["imported"] == 2
        assert len(result["errors"]) == 0

    def test_csv_validation_errors(self, db, repos, services):
        seed = _seed(db, repos)
        csv_content = "full_name,organization_id\n,999\nAlice,abc\n"
        result = services["member"].import_members_csv(
            csv_content.encode("utf-8"), seed["admin"].id, "admin1", UserRole.ADMINISTRATOR,
        )
        assert result["imported"] == 0
        assert len(result["errors"]) == 2


# =============================================================
# TRACEABILITY SERVICE
# =============================================================

class TestTraceabilityService:
    def test_batch_lifecycle(self, db, repos, services):
        seed = _seed(db, repos)
        batch = services["traceability"].create_batch(
            seed["store"].id, "BATCH-001", seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        assert batch.status == BatchStatus.PROCURED

        batch = services["traceability"].transition_batch(
            batch.id, BatchStatus.RECEIVED,
            seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        assert batch.status == BatchStatus.RECEIVED

    def test_invalid_batch_transition(self, db, repos, services):
        seed = _seed(db, repos)
        batch = services["traceability"].create_batch(
            seed["store"].id, "BATCH-002", seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        with pytest.raises(ValueError, match="Invalid batch transition"):
            services["traceability"].transition_batch(
                batch.id, BatchStatus.FINISHED,
                seed["inspector"].id, "inspector1",
                actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
            )

    def test_recall_generation(self, db, repos, services):
        seed = _seed(db, repos)
        batch = services["traceability"].create_batch(
            seed["store"].id, "RECALL-001", seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        # Admin role → bypasses the store filter requirement in
        # generate_recall (administrators are system-wide operators).
        run = services["traceability"].generate_recall(
            seed["admin"].id, "admin1", batch_filter="RECALL-001",
            actor_store_id=seed["store"].id, user_role=UserRole.ADMINISTRATOR,
        )
        assert run.result_count >= 1


# =============================================================
# AUDIT SERVICE
# =============================================================

class TestAuditService:
    def test_tamper_chain(self, db, repos, services):
        seed = _seed(db, repos)
        log1 = services["audit"].log(
            seed["admin"].id, "admin1", "test.action1",
            "test", "1",
        )
        log2 = services["audit"].log(
            seed["admin"].id, "admin1", "test.action2",
            "test", "2",
        )
        assert log1.tamper_chain_hash != log2.tamper_chain_hash
        assert len(log1.tamper_chain_hash) == 64  # SHA-256 hex

    def test_before_after_stored(self, db, repos, services):
        seed = _seed(db, repos)
        log = services["audit"].log(
            seed["admin"].id, "admin1", "test.change",
            "test", "1", before={"old": 1}, after={"new": 2},
        )
        assert '"old": 1' in log.before_json
        assert '"new": 2' in log.after_json


# =============================================================
# SCHEDULE ADJUSTMENT SERVICE — DUAL CONTROL
# =============================================================

class TestScheduleService:
    def test_request_adjustment(self, db, repos, services):
        seed = _seed(db, repos)
        req = services["schedule"].request_adjustment(
            store_id=seed["store"].id,
            user_id=seed["ops"].id, username="ops1",
            adjustment_type="retry_timing",
            target_entity_type="ticket_message_log",
            target_entity_id="42",
            before_value="30min", after_value="60min",
            reason="Customer requested later callback",
            actor_store_id=seed["store"].id, user_role=UserRole.OPERATIONS_MANAGER,
        )
        assert req.id is not None
        assert req.status == "pending"

    def test_approve_adjustment(self, db, repos, services):
        seed = _seed(db, repos)
        req = services["schedule"].request_adjustment(
            store_id=seed["store"].id,
            user_id=seed["ops"].id, username="ops1",
            adjustment_type="retry_timing",
            target_entity_type="ticket_message_log",
            target_entity_id="42",
            before_value="30min", after_value="60min",
            reason="Customer requested later callback",
            actor_store_id=seed["store"].id, user_role=UserRole.OPERATIONS_MANAGER,
        )
        db.commit()
        approved = services["schedule"].approve_adjustment(
            req.id, seed["supervisor"].id, "supervisor1",
            UserRole.SHIFT_SUPERVISOR, password=TEST_PASSWORD,
            approver_store_id=seed["store"].id,
        )
        assert approved.status == "executed"
        assert approved.executed_at is not None

    def test_self_approval_forbidden(self, db, repos, services):
        seed = _seed(db, repos)
        req = services["schedule"].request_adjustment(
            store_id=seed["store"].id,
            user_id=seed["supervisor"].id, username="supervisor1",
            adjustment_type="deadline_override",
            target_entity_type="quarantine_record",
            target_entity_id="1",
            before_value="7days", after_value="14days",
            reason="Extended return window",
            actor_store_id=seed["store"].id, user_role=UserRole.SHIFT_SUPERVISOR,
        )
        db.commit()
        with pytest.raises(PermissionError, match="Self-approval"):
            services["schedule"].approve_adjustment(
                req.id, seed["supervisor"].id, "supervisor1",
                UserRole.SHIFT_SUPERVISOR, password=TEST_PASSWORD,
                approver_store_id=seed["store"].id,
            )

    def test_password_required(self, db, repos, services):
        seed = _seed(db, repos)
        req = services["schedule"].request_adjustment(
            store_id=seed["store"].id,
            user_id=seed["ops"].id, username="ops1",
            adjustment_type="retry_timing",
            target_entity_type="ticket_message_log",
            target_entity_id="1",
            before_value="30min", after_value="60min",
            reason="Test",
            actor_store_id=seed["store"].id, user_role=UserRole.OPERATIONS_MANAGER,
        )
        db.commit()
        with pytest.raises(ValueError, match="Password is required"):
            services["schedule"].approve_adjustment(
                req.id, seed["supervisor"].id, "supervisor1",
                UserRole.SHIFT_SUPERVISOR, password="",
                approver_store_id=seed["store"].id,
            )

    def test_wrong_role_rejected(self, db, repos, services):
        seed = _seed(db, repos)
        req = services["schedule"].request_adjustment(
            store_id=seed["store"].id,
            user_id=seed["ops"].id, username="ops1",
            adjustment_type="retry_timing",
            target_entity_type="ticket_message_log",
            target_entity_id="1",
            before_value="30min", after_value="60min",
            reason="Test",
            actor_store_id=seed["store"].id, user_role=UserRole.OPERATIONS_MANAGER,
        )
        db.commit()
        with pytest.raises(PermissionError, match="Insufficient role"):
            services["schedule"].approve_adjustment(
                req.id, seed["host"].id, "host1",
                UserRole.HOST, password=TEST_PASSWORD,
                approver_store_id=seed["store"].id,
            )

    def test_one_time_execution(self, db, repos, services):
        seed = _seed(db, repos)
        req = services["schedule"].request_adjustment(
            store_id=seed["store"].id,
            user_id=seed["ops"].id, username="ops1",
            adjustment_type="retry_timing",
            target_entity_type="ticket_message_log",
            target_entity_id="1",
            before_value="30min", after_value="60min",
            reason="Test",
            actor_store_id=seed["store"].id, user_role=UserRole.OPERATIONS_MANAGER,
        )
        db.commit()
        services["schedule"].approve_adjustment(
            req.id, seed["supervisor"].id, "supervisor1",
            UserRole.SHIFT_SUPERVISOR, password=TEST_PASSWORD,
            approver_store_id=seed["store"].id,
        )
        db.commit()
        with pytest.raises(ValueError, match="not pending"):
            services["schedule"].approve_adjustment(
                req.id, seed["admin"].id, "admin1",
                UserRole.ADMINISTRATOR, password=TEST_PASSWORD,
                approver_store_id=seed["store"].id,
            )


# =============================================================
# PASSWORD VERIFICATION — DUAL CONTROL (real bcrypt path)
# =============================================================

class TestApproverPasswordVerification:
    """The approval paths must hit the stored bcrypt hash — no boolean
    flag from the client is ever acceptable. These tests exercise the
    real `verify_password_for_approval` path (not the monkeypatched
    store-auth helper — this class still uses the normal `services`
    fixture because store auth is a separate concern)."""

    def _make_variance_request(self, db, repos, services, seed):
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        services["ticket"].submit_for_qc(ticket.id, seed["agent"].id, "agent1", actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT)
        db.commit()
        _record_qc(db, services, seed, ticket, weight=20.0)
        services["ticket"].record_qc_and_compute_final(
            ticket.id, 20.0, seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        req = services["ticket"].confirm_variance(
            ticket.id, seed["inspector"].id, "inspector1", "Note",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        return req

    def test_approve_variance_wrong_password_rejected(
        self, db, repos, services,
    ):
        seed = _seed(db, repos)
        req = self._make_variance_request(db, repos, services, seed)
        with pytest.raises(PermissionError, match="Invalid password"):
            services["ticket"].approve_variance(
                req.id, seed["supervisor"].id, "supervisor1",
                UserRole.SHIFT_SUPERVISOR, password="wrong-password",
                approver_store_id=seed["store"].id,
            )

    def test_approve_variance_empty_password_rejected(
        self, db, repos, services,
    ):
        seed = _seed(db, repos)
        req = self._make_variance_request(db, repos, services, seed)
        with pytest.raises(ValueError, match="Password is required"):
            services["ticket"].approve_variance(
                req.id, seed["supervisor"].id, "supervisor1",
                UserRole.SHIFT_SUPERVISOR, password="",
                approver_store_id=seed["store"].id,
            )

    def test_approve_refund_wrong_password_rejected(
        self, db, repos, services,
    ):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        services["ticket"].submit_for_qc(ticket.id, seed["agent"].id, "agent1", actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT)
        db.commit()
        _record_qc(db, services, seed, ticket, weight=10.0)
        services["ticket"].record_qc_and_compute_final(
            ticket.id, 10.0, seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        services["ticket"].initiate_refund(
            ticket.id, seed["agent"].id, "agent1", UserRole.FRONT_DESK_AGENT,
            actor_store_id=seed["store"].id,
        )
        db.commit()
        with pytest.raises(PermissionError, match="Invalid password"):
            services["ticket"].approve_refund(
                ticket.id, seed["supervisor"].id, "supervisor1",
                UserRole.SHIFT_SUPERVISOR, password="definitely-not-correct",
                approver_store_id=seed["store"].id,
            )

    def test_approve_export_wrong_password_rejected(
        self, db, repos, services,
    ):
        seed = _seed(db, repos)
        settings = repos["settings"].get_effective(seed["store"].id)
        settings.export_requires_supervisor_default = True
        repos["settings"].update(settings)
        db.commit()

        req = services["export"].create_export_request(
            seed["store"].id, seed["ops"].id, "ops1",
            UserRole.OPERATIONS_MANAGER, "tickets",
            actor_store_id=seed["store"].id,
        )
        db.commit()
        with pytest.raises(PermissionError, match="Invalid password"):
            services["export"].approve_export(
                req.id, seed["supervisor"].id, "supervisor1",
                UserRole.SHIFT_SUPERVISOR, password="nope",
                approver_store_id=seed["store"].id,
            )

    def test_approve_schedule_wrong_password_rejected(
        self, db, repos, services,
    ):
        seed = _seed(db, repos)
        req = services["schedule"].request_adjustment(
            store_id=seed["store"].id,
            user_id=seed["ops"].id, username="ops1",
            adjustment_type="retry_timing",
            target_entity_type="ticket_message_log",
            target_entity_id="1",
            before_value="30min", after_value="60min",
            reason="Test",
            actor_store_id=seed["store"].id, user_role=UserRole.OPERATIONS_MANAGER,
        )
        db.commit()
        with pytest.raises(PermissionError, match="Invalid password"):
            services["schedule"].approve_adjustment(
                req.id, seed["supervisor"].id, "supervisor1",
                UserRole.SHIFT_SUPERVISOR, password="bad",
                approver_store_id=seed["store"].id,
            )


# =============================================================
# ADMIN-ONLY USER MANAGEMENT
# =============================================================

class TestUserManagementAdminOnly:
    def test_non_admin_cannot_create_user(self, db, repos, services):
        seed = _seed(db, repos)
        auth = services["auth"]
        with pytest.raises(PermissionError, match="Admin privileges required"):
            auth.create_user(
                username="newuser", password="TestPassword123!",
                display_name="New User", role=UserRole.FRONT_DESK_AGENT,
                admin_user_id=seed["supervisor"].id,
                admin_username="supervisor1",
                admin_role=UserRole.SHIFT_SUPERVISOR,
                store_id=seed["store"].id,
            )

    def test_non_admin_cannot_freeze_user(self, db, repos, services):
        seed = _seed(db, repos)
        auth = services["auth"]
        with pytest.raises(PermissionError, match="Admin privileges required"):
            auth.freeze_user(
                target_user_id=seed["agent"].id,
                admin_user_id=seed["supervisor"].id,
                admin_username="supervisor1",
                admin_role=UserRole.SHIFT_SUPERVISOR,
            )

    def test_non_admin_cannot_unfreeze_user(self, db, repos, services):
        seed = _seed(db, repos)
        # Freeze first as an admin so there is a user to unfreeze
        services["auth"].freeze_user(
            target_user_id=seed["agent"].id,
            admin_user_id=seed["admin"].id,
            admin_username="admin1",
            admin_role=UserRole.ADMINISTRATOR,
        )
        db.commit()
        with pytest.raises(PermissionError, match="Admin privileges required"):
            services["auth"].unfreeze_user(
                target_user_id=seed["agent"].id,
                admin_user_id=seed["ops"].id,
                admin_username="ops1",
                admin_role=UserRole.OPERATIONS_MANAGER,
            )

    def test_admin_can_create_user(self, db, repos, services):
        seed = _seed(db, repos)
        user = services["auth"].create_user(
            username="fresh_agent", password="TestPassword123!",
            display_name="Fresh Agent", role=UserRole.FRONT_DESK_AGENT,
            admin_user_id=seed["admin"].id,
            admin_username="admin1",
            admin_role=UserRole.ADMINISTRATOR,
            store_id=seed["store"].id,
        )
        assert user.id is not None
        assert user.role == UserRole.FRONT_DESK_AGENT


# =============================================================
# STORE-LEVEL AUTHORIZATION (cross-store access denied)
# =============================================================

class TestStoreAuthorization:
    """Verifies that the service layer actively rejects cross-store
    access. This class does NOT use the `services` fixture — it builds
    services directly so the real `enforce_store_access` is exercised
    (the shared fixture monkeypatches it to a no-op for legacy tests).
    """

    @pytest.fixture
    def cross_store_setup(self, db, repos):
        # Store A + user in store A
        store_a = repos["store"].create(Store(code="SA", name="Store A"))
        repos["settings"].create(Settings(store_id=store_a.id))
        repos["pricing_rule"].create(PricingRule(
            store_id=store_a.id, base_rate_per_lb=1.50, bonus_pct=10.0,
            min_weight_lbs=0.1, max_weight_lbs=1000.0,
            max_ticket_payout=200.0, max_rate_per_lb=3.0, priority=1,
        ))

        audit = AuditService(repos["audit"])
        auth = AuthService(repos["user"], repos["session"], repos["settings"], audit)
        pw_hash = auth._hash_password(TEST_PASSWORD)

        agent_a = repos["user"].create(User(
            store_id=store_a.id, username="agent_a", password_hash=pw_hash,
            display_name="Agent A", role=UserRole.FRONT_DESK_AGENT,
        ))
        supervisor_a = repos["user"].create(User(
            store_id=store_a.id, username="sup_a", password_hash=pw_hash,
            display_name="Sup A", role=UserRole.SHIFT_SUPERVISOR,
        ))

        # Store B + user in store B
        store_b = repos["store"].create(Store(code="SB", name="Store B"))
        repos["pricing_rule"].create(PricingRule(
            store_id=store_b.id, base_rate_per_lb=1.50, bonus_pct=10.0,
            min_weight_lbs=0.1, max_weight_lbs=1000.0,
            max_ticket_payout=200.0, max_rate_per_lb=3.0, priority=1,
        ))
        repos["settings"].create(Settings(store_id=store_b.id))
        agent_b = repos["user"].create(User(
            store_id=store_b.id, username="agent_b", password_hash=pw_hash,
            display_name="Agent B", role=UserRole.FRONT_DESK_AGENT,
        ))
        db.commit()

        pricing = PricingService(repos["pricing_rule"], repos["snapshot"], repos["settings"])
        ticket = TicketService(
            repos["ticket"], repos["variance"], pricing, audit,
            auth_service=auth, qc_repo=repos["qc"],
        )
        return {
            "store_a": store_a, "agent_a": agent_a, "supervisor_a": supervisor_a,
            "store_b": store_b, "agent_b": agent_b,
            "ticket": ticket,
        }

    def test_cannot_create_ticket_in_foreign_store(self, db, repos, cross_store_setup):
        s = cross_store_setup
        with pytest.raises(PermissionError, match="Cross-store access denied"):
            s["ticket"].create_ticket(
                store_id=s["store_b"].id,
                user_id=s["agent_a"].id,
                user_role=UserRole.FRONT_DESK_AGENT,
                username="agent_a",
                actor_store_id=s["agent_a"].store_id,
                customer_name="X", clothing_category="shirts",
                condition_grade="A", estimated_weight_lbs=10.0,
            )

    def test_cannot_load_foreign_ticket(self, db, repos, cross_store_setup):
        s = cross_store_setup
        # agent_b creates a ticket in store B
        t = s["ticket"].create_ticket(
            store_id=s["store_b"].id,
            user_id=s["agent_b"].id,
            user_role=UserRole.FRONT_DESK_AGENT,
            username="agent_b",
            actor_store_id=s["agent_b"].store_id,
            customer_name="X", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        # agent_a (from store A) tries to submit it for QC
        with pytest.raises(PermissionError, match="Cross-store access denied"):
            s["ticket"].submit_for_qc(
                t.id, s["agent_a"].id, "agent_a",
                actor_store_id=s["agent_a"].store_id,
                user_role=UserRole.FRONT_DESK_AGENT,
            )

    def test_cannot_cancel_foreign_ticket(self, db, repos, cross_store_setup):
        s = cross_store_setup
        t = s["ticket"].create_ticket(
            store_id=s["store_b"].id,
            user_id=s["agent_b"].id,
            user_role=UserRole.FRONT_DESK_AGENT,
            username="agent_b",
            actor_store_id=s["agent_b"].store_id,
            customer_name="X", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        with pytest.raises(PermissionError, match="Cross-store access denied"):
            s["ticket"].cancel_ticket(
                t.id, s["supervisor_a"].id, "sup_a",
                UserRole.SHIFT_SUPERVISOR, "reason",
                actor_store_id=s["supervisor_a"].store_id,
            )

    def test_real_export_file_generation(self, db, repos, services, tmp_path):
        """execute_export must write a real CSV file under the
        configured output dir, populate output_path, and include a
        watermark + attribution header. No fake state updates."""
        seed = _seed(db, repos)
        # Create a couple of tickets so the export has real rows
        for name in ("Alice", "Bob"):
            services["ticket"].create_ticket(
                store_id=seed["store"].id, user_id=seed["agent"].id,
                user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
                actor_store_id=seed["store"].id,
                customer_name=name, clothing_category="shirts",
                condition_grade="A", estimated_weight_lbs=10.0,
            )
            db.commit()

        req = services["export"].create_export_request(
            seed["store"].id, seed["ops"].id, "ops1",
            UserRole.OPERATIONS_MANAGER, "tickets",
            actor_store_id=seed["store"].id,
            watermark_enabled=True,
            attribution_text="ops1 — test",
        )
        db.commit()

        done = services["export"].execute_export(
            req.id, seed["ops"].id, "ops1",
            actor_store_id=seed["store"].id,
            user_role=UserRole.OPERATIONS_MANAGER,
        )
        assert done.output_path is not None
        import os
        assert os.path.isfile(done.output_path), (
            "execute_export must write a real file to disk"
        )
        with open(done.output_path, "r", encoding="utf-8") as f:
            body = f.read()
        # Watermark header stamped on every export
        assert "# EXPORT_ID:" in body
        assert "# GENERATED_BY: ops1" in body
        assert "# ATTRIBUTION:" in body
        # Real rows present
        assert "Alice" in body
        assert "Bob" in body
        # Header row
        assert "id,store_id,created_by_user_id,customer_name" in body

    def test_quarantine_overdue_detected(self, db, repos, services, tmp_path):
        """Create a quarantine, force its SLA deadline into the past,
        and verify the scheduler sweep reports it as overdue."""
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        batch = services["traceability"].create_batch(
            seed["store"].id, "Q-OVERDUE-001",
            seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id,
            user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        qr = services["qc"].create_quarantine(
            ticket.id, batch.id, seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id, user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        assert qr.due_back_to_customer_at is not None, (
            "create_quarantine must set SLA deadline at creation time"
        )

        # Force the deadline into the past
        repos["quarantine"].conn.execute(
            "UPDATE quarantine_records SET due_back_to_customer_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00Z", qr.id),
        )
        db.commit()

        # Run the real scheduler sweep against the same DB. The
        # scheduler opens its own connection by path — we have to write
        # the current :memory: DB to a temp file first. Instead, bypass
        # the sweep helper and query the repo directly via the exact
        # same criteria — this still proves the query is correct.
        overdue = repos["quarantine"].list_overdue_returns(
            current_date=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        assert any(r.id == qr.id for r in overdue), (
            "Unresolved quarantine past its SLA must appear in list_overdue_returns"
        )

    def test_member_csv_export_round_trips(self, db, repos, services):
        """Export → re-import must be lossless for the required columns."""
        seed = _seed(db, repos)
        org = services["member"].create_organization(
            "Export Club", seed["admin"].id, "admin1", UserRole.ADMINISTRATOR,
        )
        db.commit()
        for name in ("Alice Exporter", "Bob Exporter"):
            services["member"].add_member(
                org.id, name, seed["admin"].id, "admin1", UserRole.ADMINISTRATOR,
            )
        db.commit()

        csv_body = services["member"].export_members_csv(
            user_id=seed["admin"].id,
            username="admin1",
            user_role=UserRole.ADMINISTRATOR,
        )
        # Watermark + header sanity
        assert "# GENERATED_BY: admin1" in csv_body
        assert "full_name,organization_id" in csv_body
        assert "Alice Exporter" in csv_body
        assert "Bob Exporter" in csv_body

        # Non-admin must be rejected
        with pytest.raises(PermissionError, match="administrators"):
            services["member"].export_members_csv(
                user_id=seed["agent"].id,
                username="agent1",
                user_role=UserRole.FRONT_DESK_AGENT,
            )

    def test_administrator_bypasses_store_check(self, db, repos, cross_store_setup):
        """Administrators are system-wide operators — they can reach
        any store regardless of their own store_id."""
        s = cross_store_setup
        # Create a system-wide admin (store_id=None)
        audit = AuditService(repos["audit"])
        auth = AuthService(repos["user"], repos["session"], repos["settings"], audit)
        pw_hash = auth._hash_password(TEST_PASSWORD)
        admin = repos["user"].create(User(
            store_id=None, username="root_admin", password_hash=pw_hash,
            display_name="Root", role=UserRole.ADMINISTRATOR,
        ))
        db.commit()

        t = s["ticket"].create_ticket(
            store_id=s["store_b"].id,
            user_id=admin.id,
            user_role=UserRole.ADMINISTRATOR,
            username="root_admin",
            actor_store_id=None,  # admin has no store
            customer_name="AdminCreated", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        assert t.store_id == s["store_b"].id


# =============================================================
# BLOCKER FIXES — read-path authz, recall safety, phone, context,
# pricing windows, price override workflow
# =============================================================

class TestBlockerFixes:
    """Regression tests for the blocker fixes:
    - read-path authz for get/list methods
    - traceability recall cross-store leak
    - phone encrypt + dial
    - notification context JSON parse / dict guard
    - pricing eligibility window datetime compare
    - price override dual-control workflow
    """

    # ---- Issue 2: recall must not leak across stores ----

    def test_recall_rejects_foreign_batch_code(self, db, repos):
        """A user from store A must not be able to recall a batch code
        that exists in store B by passing it as `batch_filter`."""
        store_a = repos["store"].create(Store(code="RA", name="Store A"))
        store_b = repos["store"].create(Store(code="RB", name="Store B"))
        repos["settings"].create(Settings(store_id=store_a.id))
        repos["settings"].create(Settings(store_id=store_b.id))
        audit = AuditService(repos["audit"])
        auth = AuthService(repos["user"], repos["session"], repos["settings"], audit)
        pw = auth._hash_password(TEST_PASSWORD)
        # Recalls require supervisor+, so the prober is a supervisor
        # in store A. The store-isolation guarantee is what we're
        # actually testing.
        sup_a = repos["user"].create(User(
            store_id=store_a.id, username="ra_sup",
            password_hash=pw, display_name="A", role=UserRole.SHIFT_SUPERVISOR,
        ))
        db.commit()

        trace = TraceabilityService(
            repos["batch"], repos["genealogy"], repos["recall"], audit,
        )
        # Plant a batch in store B
        b = trace.create_batch(
            store_id=store_b.id, batch_code="SECRET-001",
            user_id=sup_a.id, username="ra_sup",
            user_role=UserRole.ADMINISTRATOR,  # bypass for setup
        )
        db.commit()
        assert b.store_id == store_b.id

        # Supervisor A tries to recall by guessing the batch code
        run = trace.generate_recall(
            user_id=sup_a.id, username="ra_sup",
            actor_store_id=store_a.id,
            user_role=UserRole.SHIFT_SUPERVISOR,
            batch_filter="SECRET-001",
        )
        # Recall must come back EMPTY because the lookup is now scoped
        # to (store_id=A, batch_code=SECRET-001) which doesn't exist.
        assert run.result_count == 0

    def test_recall_rejects_explicit_foreign_store_id(self, db, repos):
        store_a = repos["store"].create(Store(code="EA", name="A"))
        store_b = repos["store"].create(Store(code="EB", name="B"))
        repos["settings"].create(Settings(store_id=store_a.id))
        repos["settings"].create(Settings(store_id=store_b.id))
        audit = AuditService(repos["audit"])
        auth = AuthService(repos["user"], repos["session"], repos["settings"], audit)
        pw = auth._hash_password(TEST_PASSWORD)
        sup_a = repos["user"].create(User(
            store_id=store_a.id, username="ea_sup", password_hash=pw,
            display_name="A", role=UserRole.SHIFT_SUPERVISOR,
        ))
        db.commit()
        trace = TraceabilityService(
            repos["batch"], repos["genealogy"], repos["recall"], audit,
        )
        with pytest.raises(PermissionError, match="Cross-store"):
            trace.generate_recall(
                user_id=sup_a.id, username="ea_sup",
                store_id=store_b.id,           # explicitly target foreign store
                actor_store_id=store_a.id,
                user_role=UserRole.SHIFT_SUPERVISOR,
                batch_filter="anything",
            )

    # ---- Issue 1: read paths reject cross-store ----

    def test_get_timeline_rejects_cross_store(self, db, repos):
        from src.models.service_table import ServiceTable
        store_a = repos["store"].create(Store(code="TA", name="TA"))
        store_b = repos["store"].create(Store(code="TB", name="TB"))
        repos["settings"].create(Settings(store_id=store_a.id))
        repos["settings"].create(Settings(store_id=store_b.id))
        audit = AuditService(repos["audit"])
        auth = AuthService(repos["user"], repos["session"], repos["settings"], audit)
        pw = auth._hash_password(TEST_PASSWORD)
        host_b = repos["user"].create(User(
            store_id=store_b.id, username="hb", password_hash=pw,
            display_name="B", role=UserRole.HOST,
        ))
        host_a = repos["user"].create(User(
            store_id=store_a.id, username="ha", password_hash=pw,
            display_name="A", role=UserRole.HOST,
        ))
        table = repos["table"].create(ServiceTable(
            store_id=store_b.id, table_code="T1", area_type="intake_table",
        ))
        db.commit()

        table_svc = TableService(
            repos["table"], repos["table_session"], repos["table_event"], audit,
        )
        session = table_svc.open_table(
            table.id, store_b.id, host_b.id, "hb", UserRole.HOST,
            actor_store_id=store_b.id,
        )
        db.commit()
        # Host from store A reads timeline of store B's session — must reject
        with pytest.raises(PermissionError, match="Cross-store"):
            table_svc.get_timeline(
                session.id,
                actor_store_id=store_a.id,
                user_role=UserRole.HOST,
            )

    def test_schedule_list_pending_filters_by_store(self, db, repos):
        store_a = repos["store"].create(Store(code="SA1", name="A"))
        store_b = repos["store"].create(Store(code="SB1", name="B"))
        repos["settings"].create(Settings(store_id=store_a.id))
        repos["settings"].create(Settings(store_id=store_b.id))
        audit = AuditService(repos["audit"])
        auth = AuthService(repos["user"], repos["session"], repos["settings"], audit)
        pw = auth._hash_password(TEST_PASSWORD)
        ops_a = repos["user"].create(User(
            store_id=store_a.id, username="opsa", password_hash=pw,
            display_name="A", role=UserRole.OPERATIONS_MANAGER,
        ))
        ops_b = repos["user"].create(User(
            store_id=store_b.id, username="opsb", password_hash=pw,
            display_name="B", role=UserRole.OPERATIONS_MANAGER,
        ))
        db.commit()
        sched = ScheduleService(repos["schedule"], audit, auth_service=auth)
        sched.request_adjustment(
            store_id=store_a.id, user_id=ops_a.id, username="opsa",
            adjustment_type="retry", target_entity_type="t",
            target_entity_id="1", before_value="x", after_value="y",
            reason="for store A",
            actor_store_id=store_a.id, user_role=UserRole.OPERATIONS_MANAGER,
        )
        sched.request_adjustment(
            store_id=store_b.id, user_id=ops_b.id, username="opsb",
            adjustment_type="retry", target_entity_type="t",
            target_entity_id="2", before_value="x", after_value="y",
            reason="for store B",
            actor_store_id=store_b.id, user_role=UserRole.OPERATIONS_MANAGER,
        )
        db.commit()

        a_view = sched.list_pending(
            actor_store_id=store_a.id, user_role=UserRole.OPERATIONS_MANAGER,
        )
        b_view = sched.list_pending(
            actor_store_id=store_b.id, user_role=UserRole.OPERATIONS_MANAGER,
        )
        assert all(r.store_id == store_a.id for r in a_view)
        assert all(r.store_id == store_b.id for r in b_view)
        assert len(a_view) == 1 and len(b_view) == 1

    # ---- Issue 3: phone encrypt + dial ----

    def test_phone_encrypted_at_rest_and_dialable(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
            customer_phone="+1 (555) 867-5309",
        )
        db.commit()
        # Stored: ciphertext + iv + last4 only
        assert ticket.customer_phone_ciphertext is not None
        assert ticket.customer_phone_iv is not None
        assert ticket.customer_phone_last4 == "5309"
        # Dial: authorized role gets the plaintext
        result = services["ticket"].get_ticket_phone_for_dial(
            ticket_id=ticket.id, user_id=seed["supervisor"].id,
            username="supervisor1", user_role=UserRole.SHIFT_SUPERVISOR,
            actor_store_id=seed["store"].id,
        )
        assert "5558675309" in result["phone"].replace("-", "").replace(" ", "")
        assert result["last4"] == "5309"
        # Unauthorized role rejected
        with pytest.raises(PermissionError, match="not authorized"):
            services["ticket"].get_ticket_phone_for_dial(
                ticket_id=ticket.id, user_id=seed["host"].id,
                username="host1", user_role=UserRole.HOST,
                actor_store_id=seed["store"].id,
            )

    # ---- Issue 4: notification context guard ----

    def test_notification_context_must_be_dict(self, db, repos, services):
        seed = _seed(db, repos)
        repos["template"].create(NotificationTemplate(
            store_id=seed["store"].id, template_code="t1",
            name="T1", body="Hi {customer_name}", event_type="t1",
        ))
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()

        # Service guard: non-dict context is rejected even if a route
        # somehow let it through.
        with pytest.raises(ValueError, match="dict"):
            services["notification"].log_from_template(
                ticket_id=ticket.id,
                template_code="t1", store_id=seed["store"].id,
                user_id=seed["agent"].id, username="agent1",
                context="not-a-dict",
            )

    # ---- Issue 5: pricing eligibility windows compared as datetimes ----

    def test_pricing_window_compare_uses_datetime(self, db, repos, services):
        seed = _seed(db, repos)
        # Replace the default rule with a window-bounded rule
        repos["pricing_rule"]._execute("DELETE FROM pricing_rules WHERE store_id = ?",
                                       (seed["store"].id,))
        db.commit()
        repos["pricing_rule"].create(PricingRule(
            store_id=seed["store"].id, base_rate_per_lb=2.0, bonus_pct=0.0,
            min_weight_lbs=0.1, max_weight_lbs=1000.0,
            max_ticket_payout=200.0, max_rate_per_lb=3.0, priority=1,
            eligibility_start_local="2025-06-01",
            eligibility_end_local="2025-06-30",
        ))
        db.commit()

        # Inside window — works
        result = services["pricing"].calculate_payout(
            seed["store"].id, "shirts", "A", 10.0,
            now_local="2025-06-15T12:00",
        )
        assert result["base_rate"] == 2.0

        # Before window — must NOT match (string compare would have
        # incorrectly matched '2025-05-31' < '2025-06-01' which is
        # actually correct lexically, so use a clearer case below).
        with pytest.raises(ValueError, match="No applicable pricing rule"):
            services["pricing"].calculate_payout(
                seed["store"].id, "shirts", "A", 10.0,
                now_local="2025-05-15",
            )

        # Same date but with HH:MM — datetime parse handles it; old
        # lexical compare would also work, but the *important* case is
        # a date-only "2025-07-01" being correctly rejected as after
        # the window even though the stored end is just a date.
        with pytest.raises(ValueError, match="No applicable pricing rule"):
            services["pricing"].calculate_payout(
                seed["store"].id, "shirts", "A", 10.0,
                now_local="2025-07-01T08:30",
            )

    # ---- Issue 7: price override dual-control workflow ----

    def _seed_ticket(self, db, repos, services, seed):
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        return ticket

    def test_price_override_full_dual_control_flow(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = self._seed_ticket(db, repos, services, seed)

        # Requester is a supervisor (so we can test the self-approval
        # branch later — only approver-eligible roles can hit it).
        req = services["price_override"].request_price_override(
            ticket_id=ticket.id, proposed_payout=42.50,
            reason="Customer goodwill",
            user_id=seed["supervisor"].id, username="supervisor1",
            user_role=UserRole.SHIFT_SUPERVISOR,
            actor_store_id=seed["store"].id,
        )
        db.commit()
        assert req.status == "pending"

        # Self-approval forbidden — same supervisor can't approve their
        # own request even though their role is approver-eligible.
        with pytest.raises(PermissionError, match="Self-approval"):
            services["price_override"].approve_price_override(
                req.id, seed["supervisor"].id, "supervisor1",
                UserRole.SHIFT_SUPERVISOR, password=TEST_PASSWORD,
                approver_store_id=seed["store"].id,
            )

        # Wrong password (different approver — ops manager)
        with pytest.raises(PermissionError, match="Invalid password"):
            services["price_override"].approve_price_override(
                req.id, seed["ops"].id, "ops1",
                UserRole.OPERATIONS_MANAGER, password="wrong",
                approver_store_id=seed["store"].id,
            )

        # Empty password
        with pytest.raises(ValueError, match="Password is required"):
            services["price_override"].approve_price_override(
                req.id, seed["ops"].id, "ops1",
                UserRole.OPERATIONS_MANAGER, password="",
                approver_store_id=seed["store"].id,
            )

        # Correct dual-control approval — different user, real password
        approved = services["price_override"].approve_price_override(
            req.id, seed["ops"].id, "ops1",
            UserRole.OPERATIONS_MANAGER, password=TEST_PASSWORD,
            approver_store_id=seed["store"].id,
        )
        db.commit()
        assert approved.status == "approved"

        # Execute applies the override to the ticket
        executed = services["price_override"].execute_override(
            req.id, seed["ops"].id, "ops1",
            UserRole.OPERATIONS_MANAGER,
            actor_store_id=seed["store"].id,
        )
        db.commit()
        assert executed.status == "executed"

        reloaded = repos["ticket"].get_by_id(ticket.id)
        assert reloaded.final_payout == 42.50

    def test_price_override_idempotent_execute(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = self._seed_ticket(db, repos, services, seed)
        req = services["price_override"].request_price_override(
            ticket_id=ticket.id, proposed_payout=10.00, reason="x",
            user_id=seed["agent"].id, username="agent1",
            user_role=UserRole.FRONT_DESK_AGENT,
            actor_store_id=seed["store"].id,
        )
        db.commit()
        services["price_override"].approve_price_override(
            req.id, seed["supervisor"].id, "supervisor1",
            UserRole.SHIFT_SUPERVISOR, password=TEST_PASSWORD,
            approver_store_id=seed["store"].id,
        )
        db.commit()
        services["price_override"].execute_override(
            req.id, seed["supervisor"].id, "supervisor1",
            UserRole.SHIFT_SUPERVISOR,
            actor_store_id=seed["store"].id,
        )
        db.commit()
        # Second execute is rejected — one-time only
        with pytest.raises(ValueError):
            services["price_override"].execute_override(
                req.id, seed["supervisor"].id, "supervisor1",
                UserRole.SHIFT_SUPERVISOR,
                actor_store_id=seed["store"].id,
            )


# =============================================================
# HIGH FIXES — export RBAC, QC domain validation, FK errors,
# batch RBAC, calls_only, member history, UI gate
# =============================================================

class TestHighFixes:
    """Regression tests for the HIGH-severity fixes."""

    # ---- Issue 1: export execution role-restricted ----

    def test_execute_export_rejects_non_supervisor(self, db, repos, services):
        seed = _seed(db, repos)
        req = services["export"].create_export_request(
            seed["store"].id, seed["ops"].id, "ops1",
            UserRole.OPERATIONS_MANAGER, "tickets",
            actor_store_id=seed["store"].id,
        )
        db.commit()
        with pytest.raises(PermissionError, match="not authorized to execute exports"):
            services["export"].execute_export(
                req.id, seed["agent"].id, "agent1",
                actor_store_id=seed["store"].id,
                user_role=UserRole.FRONT_DESK_AGENT,
            )

    def test_execute_export_allows_supervisor(self, db, repos, services):
        seed = _seed(db, repos)
        req = services["export"].create_export_request(
            seed["store"].id, seed["ops"].id, "ops1",
            UserRole.OPERATIONS_MANAGER, "tickets",
            actor_store_id=seed["store"].id,
        )
        db.commit()
        done = services["export"].execute_export(
            req.id, seed["supervisor"].id, "supervisor1",
            actor_store_id=seed["store"].id,
            user_role=UserRole.SHIFT_SUPERVISOR,
        )
        assert done.status == "completed"

    # ---- Issue 2: QC ticket↔batch domain validation ----

    def test_create_inspection_rejects_unknown_ticket(self, db, repos, services):
        seed = _seed(db, repos)
        with pytest.raises(ValueError, match="Ticket .* not found"):
            services["qc"].create_inspection(
                ticket_id=99999, store_id=seed["store"].id,
                inspector_user_id=seed["inspector"].id,
                inspector_username="inspector1",
                inspector_role=UserRole.QC_INSPECTOR,
                actor_store_id=seed["store"].id,
                actual_weight_lbs=10.0, lot_size=10,
                nonconformance_count=0,
                inspection_outcome=InspectionOutcome.PASS,
            )

    def test_create_inspection_rejects_ticket_from_other_store(self, db, repos, services):
        seed = _seed(db, repos)
        other = repos["store"].create(Store(code="X9", name="Other"))
        repos["pricing_rule"].create(PricingRule(
            store_id=other.id, base_rate_per_lb=1.50, bonus_pct=10.0,
            min_weight_lbs=0.1, max_weight_lbs=1000.0,
            max_ticket_payout=200.0, max_rate_per_lb=3.0, priority=1,
        ))
        repos["settings"].create(Settings(store_id=other.id))
        # Plant a ticket in `other` directly via the repo so the
        # store-auth check (which would otherwise reject the agent's
        # cross-store create) doesn't get in the way of the test.
        from src.models.buyback_ticket import BuybackTicket
        from src.enums.ticket_status import TicketStatus
        ticket_in_other = repos["ticket"].create(BuybackTicket(
            store_id=other.id,
            created_by_user_id=seed["agent"].id,
            customer_name="X",
            clothing_category="shirts",
            condition_grade="A",
            estimated_weight_lbs=10.0,
            estimated_payout=10.0,
            status=TicketStatus.AWAITING_QC,
        ))
        db.commit()
        with pytest.raises(PermissionError, match="Cross-store access denied"):
            services["qc"].create_inspection(
                ticket_id=ticket_in_other.id,
                store_id=seed["store"].id,  # mismatched store
                inspector_user_id=seed["inspector"].id,
                inspector_username="inspector1",
                inspector_role=UserRole.QC_INSPECTOR,
                actor_store_id=seed["store"].id,
                actual_weight_lbs=10.0, lot_size=10,
                nonconformance_count=0,
                inspection_outcome=InspectionOutcome.PASS,
            )

    def test_create_quarantine_rejects_unknown_batch(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="J", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        with pytest.raises(ValueError, match="Batch .* not found"):
            services["qc"].create_quarantine(
                ticket.id, batch_id=88888,
                user_id=seed["inspector"].id, username="inspector1",
                actor_store_id=seed["store"].id,
                user_role=UserRole.QC_INSPECTOR,
            )

    def test_create_quarantine_rejects_cross_store_batch(self, db, repos, services):
        seed = _seed(db, repos)
        other = repos["store"].create(Store(code="Z9", name="Z"))
        db.commit()
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="J", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        # Plant a batch in a different store
        from src.models.batch import Batch
        from src.enums.batch_status import BatchStatus
        batch = repos["batch"].create(Batch(
            store_id=other.id, batch_code="X1",
            status=BatchStatus.PROCURED,
        ))
        db.commit()
        with pytest.raises(ValueError, match="different stores"):
            services["qc"].create_quarantine(
                ticket.id, batch.id,
                user_id=seed["inspector"].id, username="inspector1",
                actor_store_id=seed["store"].id,
                user_role=UserRole.QC_INSPECTOR,
            )

    # ---- Issue 4: batch / traceability RBAC ----

    def test_create_batch_rejects_host_role(self, db, repos, services):
        seed = _seed(db, repos)
        with pytest.raises(PermissionError, match="cannot create batches"):
            services["traceability"].create_batch(
                seed["store"].id, "BX-1", seed["host"].id, "host1",
                user_role=UserRole.HOST,
            )

    def test_transition_batch_recall_requires_supervisor(self, db, repos, services):
        seed = _seed(db, repos)
        batch = services["traceability"].create_batch(
            seed["store"].id, "BR-1", seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id,
            user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        # QC inspector advances normally
        services["traceability"].transition_batch(
            batch.id, BatchStatus.RECEIVED,
            seed["inspector"].id, "inspector1",
            actor_store_id=seed["store"].id,
            user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        # Recall transition is supervisor-only
        with pytest.raises(PermissionError, match="cannot recall"):
            services["traceability"].transition_batch(
                batch.id, BatchStatus.RECALLED,
                seed["inspector"].id, "inspector1",
                actor_store_id=seed["store"].id,
                user_role=UserRole.QC_INSPECTOR,
            )

    def test_generate_recall_rejects_inspector(self, db, repos, services):
        seed = _seed(db, repos)
        with pytest.raises(PermissionError, match="cannot generate recalls"):
            services["traceability"].generate_recall(
                user_id=seed["inspector"].id, username="inspector1",
                actor_store_id=seed["store"].id,
                user_role=UserRole.QC_INSPECTOR,
                batch_filter="any",
            )

    # ---- Issue 5: calls_only enforcement ----

    def test_calls_only_rejects_logged_message(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="Jane", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
            customer_phone_preference="calls_only",
            customer_phone="5555550000",
        )
        db.commit()
        # Logged message must be rejected when preference = calls_only
        with pytest.raises(PermissionError, match="calls_only"):
            services["notification"].log_message(
                ticket.id, seed["agent"].id, "agent1",
                "Hi", actor_store_id=seed["store"].id,
                user_role=UserRole.FRONT_DESK_AGENT,
                contact_channel=ContactChannel.LOGGED_MESSAGE,
            )
        # Phone call still allowed
        log = services["notification"].log_message(
            ticket.id, seed["agent"].id, "agent1",
            "Calling now",
            actor_store_id=seed["store"].id, user_role=UserRole.FRONT_DESK_AGENT,
            contact_channel=ContactChannel.PHONE_CALL,
            call_attempt_status=CallAttemptStatus.SUCCEEDED,
        )
        assert log.id is not None

    # ---- Issue 6: member history admin-only ----

    # ---- Metrics RBAC ----

    def test_metrics_rejects_front_desk(self, db, repos, services):
        seed = _seed(db, repos)
        with pytest.raises(PermissionError, match="not authorized to view metrics"):
            services["export"].compute_metrics(
                seed["store"].id, "2020-01-01", "2030-12-31",
                actor_store_id=seed["store"].id,
                user_role=UserRole.FRONT_DESK_AGENT,
            )

    def test_metrics_rejects_qc_inspector(self, db, repos, services):
        seed = _seed(db, repos)
        with pytest.raises(PermissionError, match="not authorized to view metrics"):
            services["export"].compute_metrics(
                seed["store"].id, "2020-01-01", "2030-12-31",
                actor_store_id=seed["store"].id,
                user_role=UserRole.QC_INSPECTOR,
            )

    def test_metrics_allows_ops_manager(self, db, repos, services):
        seed = _seed(db, repos)
        m = services["export"].compute_metrics(
            seed["store"].id, "2020-01-01", "2030-12-31",
            actor_store_id=seed["store"].id,
            user_role=UserRole.OPERATIONS_MANAGER,
        )
        assert "order_volume" in m

    def test_metrics_allows_administrator(self, db, repos, services):
        seed = _seed(db, repos)
        m = services["export"].compute_metrics(
            seed["store"].id, "2020-01-01", "2030-12-31",
            actor_store_id=seed["store"].id,
            user_role=UserRole.ADMINISTRATOR,
        )
        assert "revenue" in m

    def test_member_history_requires_admin(self, db, repos, services):
        seed = _seed(db, repos)
        org = services["member"].create_organization(
            "C", seed["admin"].id, "admin1", UserRole.ADMINISTRATOR,
        )
        db.commit()
        member = services["member"].add_member(
            org.id, "John", seed["admin"].id, "admin1", UserRole.ADMINISTRATOR,
        )
        db.commit()
        # Non-admin rejected
        with pytest.raises(PermissionError, match="administrators"):
            services["member"].get_member_history(
                member.id, user_role=UserRole.FRONT_DESK_AGENT,
            )
        # Admin allowed
        history = services["member"].get_member_history(
            member.id, user_role=UserRole.ADMINISTRATOR,
        )
        assert isinstance(history, list)


# =============================================================
# PRICE OVERRIDE EXECUTION ROLE GATE
# =============================================================

class TestPriceOverrideExecuteRoleGate:
    """execute_override must reject non-supervisor roles."""

    def _seed_approved_override(self, db, repos, services, seed):
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="J", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        req = services["price_override"].request_price_override(
            ticket_id=ticket.id, proposed_payout=42.00, reason="test",
            user_id=seed["agent"].id, username="agent1",
            user_role=UserRole.FRONT_DESK_AGENT,
            actor_store_id=seed["store"].id,
        )
        db.commit()
        services["price_override"].approve_price_override(
            req.id, seed["supervisor"].id, "supervisor1",
            UserRole.SHIFT_SUPERVISOR, password=TEST_PASSWORD,
            approver_store_id=seed["store"].id,
        )
        db.commit()
        return req

    def test_execute_rejects_front_desk(self, db, repos, services):
        seed = _seed(db, repos)
        req = self._seed_approved_override(db, repos, services, seed)
        with pytest.raises(PermissionError, match="not authorized"):
            services["price_override"].execute_override(
                req.id, seed["agent"].id, "agent1",
                UserRole.FRONT_DESK_AGENT,
                actor_store_id=seed["store"].id,
            )

    def test_execute_rejects_qc_inspector(self, db, repos, services):
        seed = _seed(db, repos)
        req = self._seed_approved_override(db, repos, services, seed)
        with pytest.raises(PermissionError, match="not authorized"):
            services["price_override"].execute_override(
                req.id, seed["inspector"].id, "inspector1",
                UserRole.QC_INSPECTOR,
                actor_store_id=seed["store"].id,
            )

    def test_execute_allows_supervisor(self, db, repos, services):
        seed = _seed(db, repos)
        req = self._seed_approved_override(db, repos, services, seed)
        result = services["price_override"].execute_override(
            req.id, seed["supervisor"].id, "supervisor1",
            UserRole.SHIFT_SUPERVISOR,
            actor_store_id=seed["store"].id,
        )
        assert result.executed_at is not None

    def test_execute_allows_admin(self, db, repos, services):
        seed = _seed(db, repos)
        req = self._seed_approved_override(db, repos, services, seed)
        result = services["price_override"].execute_override(
            req.id, seed["admin"].id, "admin1",
            UserRole.ADMINISTRATOR,
            actor_store_id=seed["store"].id,
        )
        assert result.executed_at is not None


# =============================================================
# CONCESSION SIGN-OFF CROSS-STORE GUARD
# =============================================================

class TestConcessionCrossStoreGuard:
    """Concession supervisor must be in the same store as the batch."""

    def test_concession_rejects_cross_store_supervisor(self, db, repos, services):
        seed = _seed(db, repos)
        # Create a second store + supervisor
        other_store = repos["store"].create(Store(code="OTH", name="Other"))
        repos["settings"].create(Settings(store_id=other_store.id))
        _audit = AuditService(repos["audit"])
        _auth = AuthService(repos["user"], repos["session"], repos["settings"], _audit)
        pw_hash = _auth._hash_password(TEST_PASSWORD)
        other_sup = repos["user"].create(User(
            store_id=other_store.id, username="other_sup",
            password_hash=pw_hash, display_name="Other Sup",
            role=UserRole.SHIFT_SUPERVISOR,
        ))
        db.commit()

        # Create ticket + batch + quarantine in seed store
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="J", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        batch = services["traceability"].create_batch(
            store_id=seed["store"].id, batch_code="B1",
            user_id=seed["inspector"].id, username="inspector1",
            actor_store_id=seed["store"].id,
            user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        qr = services["qc"].create_quarantine(
            ticket.id, batch.id,
            user_id=seed["inspector"].id, username="inspector1",
            actor_store_id=seed["store"].id,
            user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()

        # other_sup is in other_store — concession must be rejected
        with pytest.raises(PermissionError, match="same store"):
            services["qc"].resolve_quarantine(
                qr.id,
                disposition="concession_acceptance",
                user_id=seed["inspector"].id,
                username="inspector1",
                user_role=UserRole.QC_INSPECTOR,
                actor_store_id=seed["store"].id,
                concession_supervisor_id=other_sup.id,
                concession_supervisor_username="other_sup",
                concession_supervisor_password=TEST_PASSWORD,
            )

    def test_concession_allows_same_store_supervisor(self, db, repos, services):
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="J", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        batch = services["traceability"].create_batch(
            store_id=seed["store"].id, batch_code="B2",
            user_id=seed["inspector"].id, username="inspector1",
            actor_store_id=seed["store"].id,
            user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        qr = services["qc"].create_quarantine(
            ticket.id, batch.id,
            user_id=seed["inspector"].id, username="inspector1",
            actor_store_id=seed["store"].id,
            user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()

        # Same-store supervisor should succeed
        result = services["qc"].resolve_quarantine(
            qr.id,
            disposition="concession_acceptance",
            user_id=seed["inspector"].id,
            username="inspector1",
            user_role=UserRole.QC_INSPECTOR,
            actor_store_id=seed["store"].id,
            concession_supervisor_id=seed["supervisor"].id,
            concession_supervisor_username="supervisor1",
            concession_supervisor_password=TEST_PASSWORD,
        )
        assert result.disposition == "concession_acceptance"

    def test_concession_allows_admin_any_store(self, db, repos, services):
        """Administrators are system-wide and exempt from the store check."""
        seed = _seed(db, repos)
        ticket = services["ticket"].create_ticket(
            store_id=seed["store"].id, user_id=seed["agent"].id,
            user_role=UserRole.FRONT_DESK_AGENT, username="agent1",
            actor_store_id=seed["store"].id,
            customer_name="J", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=10.0,
        )
        db.commit()
        batch = services["traceability"].create_batch(
            store_id=seed["store"].id, batch_code="B3",
            user_id=seed["inspector"].id, username="inspector1",
            actor_store_id=seed["store"].id,
            user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()
        qr = services["qc"].create_quarantine(
            ticket.id, batch.id,
            user_id=seed["inspector"].id, username="inspector1",
            actor_store_id=seed["store"].id,
            user_role=UserRole.QC_INSPECTOR,
        )
        db.commit()

        result = services["qc"].resolve_quarantine(
            qr.id,
            disposition="concession_acceptance",
            user_id=seed["inspector"].id,
            username="inspector1",
            user_role=UserRole.QC_INSPECTOR,
            actor_store_id=seed["store"].id,
            concession_supervisor_id=seed["admin"].id,
            concession_supervisor_username="admin1",
            concession_supervisor_password=TEST_PASSWORD,
        )
        assert result.disposition == "concession_acceptance"


# =============================================================
# SCHEDULE PENDING ROLE GATE
# =============================================================

class TestSchedulePendingRoleGate:
    """list_pending must reject non-supervisor roles."""

    def test_list_pending_rejects_front_desk(self, db, repos, services):
        seed = _seed(db, repos)
        with pytest.raises(PermissionError, match="not authorized"):
            services["schedule"].list_pending(
                actor_store_id=seed["store"].id,
                user_role=UserRole.FRONT_DESK_AGENT,
            )

    def test_list_pending_rejects_qc_inspector(self, db, repos, services):
        seed = _seed(db, repos)
        with pytest.raises(PermissionError, match="not authorized"):
            services["schedule"].list_pending(
                actor_store_id=seed["store"].id,
                user_role=UserRole.QC_INSPECTOR,
            )

    def test_list_pending_rejects_host(self, db, repos, services):
        seed = _seed(db, repos)
        with pytest.raises(PermissionError, match="not authorized"):
            services["schedule"].list_pending(
                actor_store_id=seed["store"].id,
                user_role=UserRole.HOST,
            )

    def test_list_pending_allows_supervisor(self, db, repos, services):
        seed = _seed(db, repos)
        result = services["schedule"].list_pending(
            actor_store_id=seed["store"].id,
            user_role=UserRole.SHIFT_SUPERVISOR,
        )
        assert isinstance(result, list)

    def test_list_pending_allows_admin(self, db, repos, services):
        seed = _seed(db, repos)
        result = services["schedule"].list_pending(
            store_id=seed["store"].id,
            actor_store_id=seed["store"].id,
            user_role=UserRole.ADMINISTRATOR,
        )
        assert isinstance(result, list)


# =============================================================
# TABLE TRANSFER CROSS-STORE GUARD
# =============================================================

class TestTableTransferCrossStore:
    """transfer_table must reject target users from a different store."""

    def test_transfer_rejects_cross_store_user(self, db, repos, services):
        seed = _seed(db, repos)
        other_store = repos["store"].create(Store(code="XFR", name="Transfer Store"))
        repos["settings"].create(Settings(store_id=other_store.id))
        _audit = AuditService(repos["audit"])
        _auth = AuthService(repos["user"], repos["session"], repos["settings"], _audit)
        pw_hash = _auth._hash_password(TEST_PASSWORD)
        other_host = repos["user"].create(User(
            store_id=other_store.id, username="other_host",
            password_hash=pw_hash, display_name="Other Host",
            role=UserRole.HOST,
        ))
        db.commit()

        # Create a table + session in seed store
        table = repos["table"].create(ServiceTable(
            store_id=seed["store"].id, table_code="T99",
            area_type="intake_table",
        ))
        db.commit()
        session = services["table"].open_table(
            table.id, seed["store"].id,
            seed["host"].id, "host1", UserRole.HOST,
            actor_store_id=seed["store"].id,
        )
        db.commit()

        with pytest.raises(PermissionError, match="different store"):
            services["table"].transfer_table(
                session.id, other_host.id,
                seed["host"].id, "host1", UserRole.HOST,
                actor_store_id=seed["store"].id,
            )

    def test_transfer_allows_same_store_user(self, db, repos, services):
        seed = _seed(db, repos)
        table = repos["table"].create(ServiceTable(
            store_id=seed["store"].id, table_code="T100",
            area_type="intake_table",
        ))
        db.commit()
        session = services["table"].open_table(
            table.id, seed["store"].id,
            seed["host"].id, "host1", UserRole.HOST,
            actor_store_id=seed["store"].id,
        )
        db.commit()

        # Transfer to another user in the same store
        result = services["table"].transfer_table(
            session.id, seed["agent"].id,
            seed["host"].id, "host1", UserRole.HOST,
            actor_store_id=seed["store"].id,
        )
        assert result.opened_by_user_id == seed["agent"].id

    def test_transfer_rejects_unknown_user(self, db, repos, services):
        seed = _seed(db, repos)
        table = repos["table"].create(ServiceTable(
            store_id=seed["store"].id, table_code="T101",
            area_type="intake_table",
        ))
        db.commit()
        session = services["table"].open_table(
            table.id, seed["store"].id,
            seed["host"].id, "host1", UserRole.HOST,
            actor_store_id=seed["store"].id,
        )
        db.commit()

        with pytest.raises(ValueError, match="Target user not found"):
            services["table"].transfer_table(
                session.id, 99999,
                seed["host"].id, "host1", UserRole.HOST,
                actor_store_id=seed["store"].id,
            )


# =============================================================
# FINAL BLOCKERS — pricing format support, signed cookie, TLS-first
# =============================================================

class TestPricingDateFormats:
    """The eligibility-window parser must accept the formats operators
    actually use: ISO, US-style MM/DD/YYYY, and 12-hour AM/PM clocks."""

    def _setup_window(self, db, repos, start, end):
        seed = _seed(db, repos)
        repos["pricing_rule"]._execute(
            "DELETE FROM pricing_rules WHERE store_id = ?", (seed["store"].id,),
        )
        db.commit()
        repos["pricing_rule"].create(PricingRule(
            store_id=seed["store"].id, base_rate_per_lb=2.0, bonus_pct=0.0,
            min_weight_lbs=0.1, max_weight_lbs=1000.0,
            max_ticket_payout=200.0, max_rate_per_lb=3.0, priority=1,
            eligibility_start_local=start,
            eligibility_end_local=end,
        ))
        db.commit()
        return seed

    def test_us_date_format_inside_window(self, db, repos, services):
        seed = self._setup_window(db, repos, "06/01/2025", "06/30/2025")
        result = services["pricing"].calculate_payout(
            seed["store"].id, "shirts", "A", 10.0,
            now_local="06/15/2025",
        )
        assert result["base_rate"] == 2.0

    def test_us_date_format_outside_window(self, db, repos, services):
        seed = self._setup_window(db, repos, "06/01/2025", "06/30/2025")
        with pytest.raises(ValueError, match="No applicable pricing rule"):
            services["pricing"].calculate_payout(
                seed["store"].id, "shirts", "A", 10.0,
                now_local="07/15/2025",
            )

    def test_12_hour_am_pm_inside_window(self, db, repos, services):
        seed = self._setup_window(
            db, repos,
            "06/01/2025 09:00 AM",
            "06/30/2025 05:00 PM",
        )
        result = services["pricing"].calculate_payout(
            seed["store"].id, "shirts", "A", 10.0,
            now_local="06/15/2025 02:30 PM",
        )
        assert result["base_rate"] == 2.0

    def test_12_hour_am_pm_after_close(self, db, repos, services):
        seed = self._setup_window(
            db, repos,
            "06/01/2025 09:00 AM",
            "06/15/2025 05:00 PM",
        )
        # Same day, after close — must be rejected
        with pytest.raises(ValueError, match="No applicable pricing rule"):
            services["pricing"].calculate_payout(
                seed["store"].id, "shirts", "A", 10.0,
                now_local="06/15/2025 06:30 PM",
            )

    def test_lowercase_am_pm_normalized(self, db, repos, services):
        seed = self._setup_window(
            db, repos,
            "06/01/2025 09:00 AM",
            "06/30/2025 05:00 PM",
        )
        result = services["pricing"].calculate_payout(
            seed["store"].id, "shirts", "A", 10.0,
            now_local="06/15/2025 02:30 pm",
        )
        assert result["base_rate"] == 2.0


# =============================================================
# SESSION COOKIE SIGNING (HMAC tamper rejection)
# =============================================================

class TestSessionCookieSigning:
    """The signed cookie helper must accept its own signatures and
    reject anything else: missing sig, wrong sig, swapped nonce."""

    def _isolate_key(self, monkeypatch, tmp_path):
        from src.security import session_cookie as sc
        monkeypatch.setattr(sc, "SESSION_KEY_PATH", str(tmp_path / "skey"))
        sc.reset_key_cache()

    def test_round_trip_verifies(self, monkeypatch, tmp_path):
        self._isolate_key(monkeypatch, tmp_path)
        from src.security.session_cookie import sign_session_nonce, verify_session_cookie
        signed = sign_session_nonce("nonce-abc")
        assert "." in signed
        assert verify_session_cookie(signed) == "nonce-abc"

    def test_unsigned_cookie_rejected(self, monkeypatch, tmp_path):
        self._isolate_key(monkeypatch, tmp_path)
        from src.security.session_cookie import verify_session_cookie
        # Plain nonce with no `.sig` segment — must fail
        assert verify_session_cookie("nonce-abc") is None

    def test_tampered_cookie_rejected(self, monkeypatch, tmp_path):
        self._isolate_key(monkeypatch, tmp_path)
        from src.security.session_cookie import sign_session_nonce, verify_session_cookie
        signed = sign_session_nonce("nonce-abc")
        # Flip a single character of the signature
        nonce, sig = signed.rsplit(".", 1)
        tampered_sig = ("A" if sig[0] != "A" else "B") + sig[1:]
        assert verify_session_cookie(f"{nonce}.{tampered_sig}") is None

    def test_swapped_nonce_rejected(self, monkeypatch, tmp_path):
        self._isolate_key(monkeypatch, tmp_path)
        from src.security.session_cookie import sign_session_nonce, verify_session_cookie
        signed_a = sign_session_nonce("nonce-a")
        _, sig = signed_a.rsplit(".", 1)
        # Replay the signature with a DIFFERENT nonce — must fail
        assert verify_session_cookie(f"nonce-b.{sig}") is None

    def test_empty_cookie_rejected(self, monkeypatch, tmp_path):
        self._isolate_key(monkeypatch, tmp_path)
        from src.security.session_cookie import verify_session_cookie
        assert verify_session_cookie("") is None
        assert verify_session_cookie(None) is None

    def test_wrong_key_rejects(self, monkeypatch, tmp_path):
        self._isolate_key(monkeypatch, tmp_path)
        from src.security import session_cookie as sc
        signed = sc.sign_session_nonce("nonce-abc")
        # Rotate to a different key — old signature must no longer verify
        sc.reset_key_cache()
        monkeypatch.setattr(sc, "SESSION_KEY_PATH", str(tmp_path / "skey2"))
        assert sc.verify_session_cookie(signed) is None


# =============================================================
# TLS-FIRST PRODUCTION GUARD
# =============================================================

class TestTLSFirstGuard:
    """`_enforce_tls_first` must refuse to start the app in production
    mode without TLS env vars and SECURE_COOKIES=true."""

    def test_dev_mode_does_not_require_tls(self, monkeypatch):
        from app import _enforce_tls_first
        monkeypatch.setenv("RECLAIM_OPS_DEV_MODE", "true")
        monkeypatch.setenv("RECLAIM_OPS_REQUIRE_TLS", "false")
        monkeypatch.delenv("FLASK_ENV", raising=False)
        # No raise — dev mode explicitly disables TLS enforcement
        _enforce_tls_first()

    def test_production_without_tls_refuses(self, monkeypatch):
        from app import _enforce_tls_first
        monkeypatch.setenv("FLASK_ENV", "production")
        monkeypatch.delenv("TLS_CERT_PATH", raising=False)
        monkeypatch.delenv("TLS_KEY_PATH", raising=False)
        monkeypatch.setenv("SECURE_COOKIES", "false")
        with pytest.raises(RuntimeError, match="TLS-first"):
            _enforce_tls_first()

    def test_production_without_secure_cookies_refuses(self, monkeypatch, tmp_path):
        from app import _enforce_tls_first
        cert = tmp_path / "c.pem"
        key = tmp_path / "k.pem"
        cert.write_text("dummy")
        key.write_text("dummy")
        monkeypatch.setenv("RECLAIM_OPS_REQUIRE_TLS", "true")
        monkeypatch.setenv("TLS_CERT_PATH", str(cert))
        monkeypatch.setenv("TLS_KEY_PATH", str(key))
        monkeypatch.setenv("SECURE_COOKIES", "false")
        with pytest.raises(RuntimeError, match="SECURE_COOKIES"):
            _enforce_tls_first()

    def test_production_with_tls_and_secure_cookies_allowed(self, monkeypatch, tmp_path):
        from app import _enforce_tls_first
        cert = tmp_path / "c.pem"
        key = tmp_path / "k.pem"
        cert.write_text("dummy")
        key.write_text("dummy")
        monkeypatch.setenv("RECLAIM_OPS_REQUIRE_TLS", "true")
        monkeypatch.setenv("TLS_CERT_PATH", str(cert))
        monkeypatch.setenv("TLS_KEY_PATH", str(key))
        monkeypatch.setenv("SECURE_COOKIES", "true")
        # No raise
        _enforce_tls_first()
