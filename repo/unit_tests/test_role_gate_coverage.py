"""Service-layer role-gate coverage closure.

Every service method that begins with `if role not in {…}: raise
PermissionError(…)` is exercised here by calling it with an
explicitly-disallowed role.  These branches are otherwise hard to
reach from the route layer because the routes themselves filter most
unauthorized callers earlier.
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fullstack", "backend"))

import pytest

from src.database import get_connection, init_db
from src.enums.user_role import UserRole
from src.models.buyback_ticket import BuybackTicket
from src.models.export_request import ExportRequest
from src.models.member import Member
from src.models.club_organization import ClubOrganization
from src.models.schedule_adjustment_request import ScheduleAdjustmentRequest
from src.models.settings import Settings
from src.models.store import Store
from src.models.user import User
from src.models.variance_approval_request import VarianceApprovalRequest
from src.models.quarantine_record import QuarantineRecord
from src.models.batch import Batch
from src.repositories import (
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
    SettingsRepository,
    StoreRepository,
    TableActivityEventRepository,
    TableSessionRepository,
    TicketMessageLogRepository,
    UserRepository,
    UserSessionRepository,
    VarianceApprovalRequestRepository,
)
from src.services.audit_service import AuditService
from src.services.auth_service import AuthService
from src.services.export_service import ExportService
from src.services.member_service import MemberService
from src.services.notification_service import NotificationService
from src.services.price_override_service import PriceOverrideService
from src.services.pricing_service import PricingService
from src.services.qc_service import QCService
from src.services.schedule_service import ScheduleService
from src.services.table_service import TableService
from src.services.ticket_service import TicketService
from src.services.traceability_service import TraceabilityService


@pytest.fixture
def db(tmp_path):
    p = str(tmp_path / "rg.db")
    init_db(p).close()
    conn = get_connection(p)
    yield conn
    conn.close()


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _store(db, code="S"):
    s = StoreRepository(db).create(Store(code=code, name=code))
    SettingsRepository(db).create(Settings(store_id=s.id))
    db.commit()
    return s


def _user(db, store_id, username="u", role="front_desk_agent"):
    u = UserRepository(db).create(User(
        store_id=store_id, username=username, password_hash="x",
        display_name=username, role=role,
    ))
    db.commit()
    return u


def _ticket(db, store_id, user_id, status="intake_open"):
    t = BuybackTicketRepository(db).create(BuybackTicket(
        store_id=store_id, created_by_user_id=user_id,
        customer_name="C", clothing_category="shirts",
        condition_grade="A", estimated_weight_lbs=5.0,
        estimated_payout=7.5, status=status,
    ))
    db.commit()
    return t


def _audit(db):
    return AuditService(AuditLogRepository(db))


def _auth(db):
    return AuthService(
        UserRepository(db), UserSessionRepository(db),
        SettingsRepository(db), _audit(db),
    )


# ════════════════════════════════════════════════════════════
# TicketService — role gates on every method
# ════════════════════════════════════════════════════════════

def _ticket_svc(db):
    pricing = PricingService(
        PricingRuleRepository(db),
        PricingCalculationSnapshotRepository(db),
        SettingsRepository(db),
    )
    return TicketService(
        BuybackTicketRepository(db),
        VarianceApprovalRequestRepository(db),
        pricing, _audit(db),
        auth_service=_auth(db),
        qc_repo=QCInspectionRepository(db),
    )


class TestTicketServiceRoleGates:
    def test_create_ticket_rejects_host_role(self, db):
        s = _store(db)
        u = _user(db, s.id, "h", "host")
        svc = _ticket_svc(db)
        with pytest.raises(PermissionError):
            svc.create_ticket(
                store_id=s.id, user_id=u.id, user_role="host",
                username="h", actor_store_id=s.id,
                customer_name="C", clothing_category="shirts",
                condition_grade="A", estimated_weight_lbs=5.0,
            )

    def test_qc_final_rejects_host(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fd2", "front_desk_agent")
        host = _user(db, s.id, "h3", "host")
        t = _ticket(db, s.id, fd.id, status="awaiting_qc")
        svc = _ticket_svc(db)
        with pytest.raises(PermissionError):
            svc.record_qc_and_compute_final(
                ticket_id=t.id, actual_weight_lbs=5.0,
                user_id=host.id, username=host.username,
                actor_store_id=s.id, user_role="host",
            )

    def test_initiate_refund_rejects_qc_role(self, db):
        s = _store(db)
        qc = _user(db, s.id, "qc", "qc_inspector")
        fd = _user(db, s.id, "fd3", "front_desk_agent")
        t = _ticket(db, s.id, fd.id, status="completed")
        # final_payout must be set so refund logic is reachable
        BuybackTicketRepository(db).conn.execute(
            "UPDATE buyback_tickets SET final_payout=10.0 WHERE id=?", (t.id,),
        )
        db.commit()
        svc = _ticket_svc(db)
        with pytest.raises(PermissionError):
            svc.initiate_refund(
                ticket_id=t.id, user_id=qc.id, username=qc.username,
                user_role="qc_inspector", actor_store_id=s.id,
            )

    def test_approve_refund_rejects_qc_role(self, db):
        s = _store(db)
        qc = _user(db, s.id, "qc2", "qc_inspector")
        svc = _ticket_svc(db)
        with pytest.raises(PermissionError):
            svc.approve_refund(
                ticket_id=1, approver_user_id=qc.id,
                approver_username=qc.username, approver_role="qc_inspector",
                password="anything", approver_store_id=s.id,
            )

    def test_reject_refund_rejects_fd_role(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fd4", "front_desk_agent")
        svc = _ticket_svc(db)
        with pytest.raises(PermissionError):
            svc.reject_refund(
                ticket_id=1, approver_user_id=fd.id,
                approver_username=fd.username, approver_role="front_desk_agent",
                reason="x", approver_store_id=s.id,
            )

    def test_dial_rejects_host_role(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fd6", "front_desk_agent")
        host = _user(db, s.id, "h5", "host")
        t = _ticket(db, s.id, fd.id)
        svc = _ticket_svc(db)
        with pytest.raises(PermissionError):
            svc.get_ticket_phone_for_dial(
                ticket_id=t.id, user_id=host.id, username=host.username,
                user_role="host", actor_store_id=s.id,
            )

    def test_approve_variance_rejects_fd(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fdv", "front_desk_agent")
        svc = _ticket_svc(db)
        with pytest.raises(PermissionError):
            svc.approve_variance(
                approval_request_id=1, approver_user_id=fd.id,
                approver_username=fd.username, approver_role="front_desk_agent",
                password="x", approver_store_id=s.id,
            )

    def test_reject_variance_rejects_fd(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fdv2", "front_desk_agent")
        svc = _ticket_svc(db)
        with pytest.raises(PermissionError):
            svc.reject_variance(
                approval_request_id=1, approver_user_id=fd.id,
                approver_username=fd.username, approver_role="front_desk_agent",
                reason="r", approver_store_id=s.id,
            )


# ════════════════════════════════════════════════════════════
# QCService — role gates
# ════════════════════════════════════════════════════════════

def _qc_svc(db):
    return QCService(
        QCInspectionRepository(db), QuarantineRecordRepository(db),
        BatchRepository(db), BatchGenealogyEventRepository(db),
        SettingsRepository(db), _audit(db),
        auth_service=_auth(db),
        user_repo=UserRepository(db),
        ticket_repo=BuybackTicketRepository(db),
    )


class TestQCServiceRoleGates:
    def test_inspection_rejects_host(self, db):
        s = _store(db)
        host = _user(db, s.id, "qh", "host")
        svc = _qc_svc(db)
        with pytest.raises(PermissionError):
            svc.create_inspection(
                ticket_id=1, store_id=s.id,
                inspector_user_id=host.id, inspector_username=host.username,
                inspector_role="host", actor_store_id=s.id,
                actual_weight_lbs=5.0, lot_size=5,
                nonconformance_count=0, inspection_outcome="pass",
            )

    def test_quarantine_resolve_rejects_fd(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fdqr", "front_desk_agent")
        svc = _qc_svc(db)
        with pytest.raises(PermissionError):
            svc.resolve_quarantine(
                quarantine_id=1, disposition="scrap",
                user_id=fd.id, username=fd.username,
                user_role="front_desk_agent", actor_store_id=s.id,
            )


# ════════════════════════════════════════════════════════════
# ExportService — role gates
# ════════════════════════════════════════════════════════════

def _export_svc(db):
    return ExportService(
        ExportRequestRepository(db), BuybackTicketRepository(db),
        SettingsRepository(db), _audit(db),
        auth_service=_auth(db),
        store_repo=StoreRepository(db),
    )


class TestExportServiceRoleGates:
    def test_create_request_rejects_fd(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fde", "front_desk_agent")
        svc = _export_svc(db)
        with pytest.raises(PermissionError):
            svc.create_export_request(
                store_id=s.id, user_id=fd.id, username=fd.username,
                user_role="front_desk_agent", actor_store_id=s.id,
                export_type="tickets",
            )

    def test_create_request_rejects_qc(self, db):
        s = _store(db)
        qc = _user(db, s.id, "qce", "qc_inspector")
        svc = _export_svc(db)
        with pytest.raises(PermissionError):
            svc.create_export_request(
                store_id=s.id, user_id=qc.id, username=qc.username,
                user_role="qc_inspector", actor_store_id=s.id,
                export_type="tickets",
            )

    def test_approve_rejects_fd(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fdea", "front_desk_agent")
        svc = _export_svc(db)
        with pytest.raises(PermissionError):
            svc.approve_export(
                request_id=1, approver_user_id=fd.id,
                approver_username=fd.username, approver_role="front_desk_agent",
                password="x", approver_store_id=s.id,
            )

    def test_reject_rejects_fd(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fder", "front_desk_agent")
        svc = _export_svc(db)
        with pytest.raises(PermissionError):
            svc.reject_export(
                request_id=1, approver_user_id=fd.id,
                approver_username=fd.username, approver_role="front_desk_agent",
                reason="x", approver_store_id=s.id,
            )

    def test_execute_rejects_fd(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fdex", "front_desk_agent")
        svc = _export_svc(db)
        with pytest.raises(PermissionError):
            svc.execute_export(
                request_id=1, user_id=fd.id, username=fd.username,
                actor_store_id=s.id, user_role="front_desk_agent",
            )

    def test_metrics_rejects_fd(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fdm", "front_desk_agent")
        svc = _export_svc(db)
        with pytest.raises(PermissionError):
            svc.compute_metrics(
                store_id=s.id, date_start="2020-01-01", date_end="2030-12-31",
                actor_store_id=s.id, user_role="front_desk_agent",
            )


# ════════════════════════════════════════════════════════════
# ScheduleService — role gates
# ════════════════════════════════════════════════════════════

def _sched_svc(db):
    return ScheduleService(
        ScheduleAdjustmentRequestRepository(db), _audit(db),
        auth_service=_auth(db),
    )


class TestScheduleServiceRoleGates:
    def test_approve_rejects_fd(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fdsa", "front_desk_agent")
        svc = _sched_svc(db)
        with pytest.raises(PermissionError):
            svc.approve_adjustment(
                request_id=1, approver_user_id=fd.id,
                approver_username=fd.username, approver_role="front_desk_agent",
                password="x", approver_store_id=s.id,
            )

    def test_reject_rejects_fd(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fdsr", "front_desk_agent")
        svc = _sched_svc(db)
        with pytest.raises(PermissionError):
            svc.reject_adjustment(
                request_id=1, approver_user_id=fd.id,
                approver_username=fd.username, approver_role="front_desk_agent",
                reason="x", approver_store_id=s.id,
            )

    def test_list_pending_rejects_fd(self, db):
        s = _store(db)
        with pytest.raises(PermissionError):
            _sched_svc(db).list_pending(
                store_id=s.id, actor_store_id=s.id,
                user_role="front_desk_agent",
            )


# ════════════════════════════════════════════════════════════
# PriceOverrideService — role gates
# ════════════════════════════════════════════════════════════

def _po_svc(db):
    return PriceOverrideService(
        PriceOverrideRequestRepository(db),
        BuybackTicketRepository(db),
        _audit(db),
        auth_service=_auth(db),
    )


class TestPriceOverrideServiceRoleGates:
    def test_request_rejects_host(self, db):
        s = _store(db)
        host = _user(db, s.id, "hpo", "host")
        svc = _po_svc(db)
        with pytest.raises(PermissionError):
            svc.request_price_override(
                ticket_id=1, proposed_payout=10.0, reason="r",
                user_id=host.id, username=host.username,
                user_role="host", actor_store_id=s.id,
            )

    def test_approve_rejects_fd(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fdpo", "front_desk_agent")
        svc = _po_svc(db)
        with pytest.raises(PermissionError):
            svc.approve_price_override(
                request_id=1, approver_user_id=fd.id,
                approver_username=fd.username, approver_role="front_desk_agent",
                password="x", approver_store_id=s.id,
            )

    def test_reject_rejects_fd(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fdpor", "front_desk_agent")
        svc = _po_svc(db)
        with pytest.raises(PermissionError):
            svc.reject_price_override(
                request_id=1, approver_user_id=fd.id,
                approver_username=fd.username, approver_role="front_desk_agent",
                reason="x", approver_store_id=s.id,
            )

    def test_execute_rejects_fd(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fdpoe", "front_desk_agent")
        svc = _po_svc(db)
        with pytest.raises(PermissionError):
            svc.execute_override(
                request_id=1, user_id=fd.id, username=fd.username,
                user_role="front_desk_agent", actor_store_id=s.id,
            )

    def test_list_pending_returns_list(self, db):
        s = _store(db)
        # No role restriction on list_pending — just exercises the path
        result = _po_svc(db).list_pending(
            actor_store_id=s.id, user_role="front_desk_agent",
        )
        assert isinstance(result, list)


# ════════════════════════════════════════════════════════════
# TableService — host-only / role-restricted methods
# ════════════════════════════════════════════════════════════

def _table_svc(db):
    return TableService(
        __import__("src.repositories", fromlist=["ServiceTableRepository"]).ServiceTableRepository(db),
        TableSessionRepository(db),
        TableActivityEventRepository(db),
        _audit(db),
        user_repo=UserRepository(db),
    )


class TestTableServiceRoleGates:
    def test_open_table_rejects_fd(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fdt", "front_desk_agent")
        svc = _table_svc(db)
        with pytest.raises(PermissionError):
            svc.open_table(
                table_id=1, store_id=s.id,
                user_id=fd.id, username=fd.username,
                user_role="front_desk_agent", actor_store_id=s.id,
            )

    def test_transition_rejects_fd(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fdtt", "front_desk_agent")
        svc = _table_svc(db)
        with pytest.raises(PermissionError):
            svc.transition_table(
                session_id=1, target_state="pre_checkout",
                user_id=fd.id, username=fd.username,
                user_role="front_desk_agent", actor_store_id=s.id,
            )

    def test_merge_rejects_fd(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fdtm", "front_desk_agent")
        svc = _table_svc(db)
        with pytest.raises(PermissionError):
            svc.merge_tables(
                session_ids=[1, 2], store_id=s.id,
                user_id=fd.id, username=fd.username,
                user_role="front_desk_agent", actor_store_id=s.id,
            )


# ════════════════════════════════════════════════════════════
# TraceabilityService — role-gated methods
# ════════════════════════════════════════════════════════════

def _trace_svc(db):
    return TraceabilityService(
        BatchRepository(db),
        BatchGenealogyEventRepository(db),
        RecallRunRepository(db),
        _audit(db),
    )


class TestTraceabilityServiceRoleGates:
    def test_create_batch_rejects_fd(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fdb", "front_desk_agent")
        svc = _trace_svc(db)
        with pytest.raises(PermissionError):
            svc.create_batch(
                store_id=s.id, batch_code="B1",
                user_id=fd.id, username=fd.username,
                actor_store_id=s.id, user_role="front_desk_agent",
            )

    def test_transition_batch_rejects_fd(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fdbt", "front_desk_agent")
        svc = _trace_svc(db)
        with pytest.raises(PermissionError):
            svc.transition_batch(
                batch_id=1, target_status="received",
                user_id=fd.id, username=fd.username,
                actor_store_id=s.id, user_role="front_desk_agent",
            )

    def test_generate_recall_rejects_fd(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fdr", "front_desk_agent")
        svc = _trace_svc(db)
        with pytest.raises(PermissionError):
            svc.generate_recall(
                user_id=fd.id, username=fd.username,
                store_id=s.id, actor_store_id=s.id,
                user_role="front_desk_agent",
            )


# ════════════════════════════════════════════════════════════
# NotificationService — role gates
# ════════════════════════════════════════════════════════════

def _notif_svc(db):
    return NotificationService(
        TicketMessageLogRepository(db),
        NotificationTemplateRepository(db),
        BuybackTicketRepository(db),
        _audit(db),
    )


class TestNotificationServiceCoverage:
    def test_log_message_unknown_ticket(self, db):
        s = _store(db)
        u = _user(db, s.id, "fdn", "front_desk_agent")
        svc = _notif_svc(db)
        with pytest.raises(ValueError):
            svc.log_message(
                ticket_id=99999, user_id=u.id, username=u.username,
                message_body="hi", actor_store_id=s.id,
                user_role="front_desk_agent",
            )

    def test_log_from_template_unknown_template(self, db):
        s = _store(db)
        u = _user(db, s.id, "fdnt", "front_desk_agent")
        t = _ticket(db, s.id, u.id)
        svc = _notif_svc(db)
        with pytest.raises(ValueError):
            svc.log_from_template(
                ticket_id=t.id, template_code="does_not_exist",
                store_id=s.id, user_id=u.id, username=u.username,
                context={"customer_name": "X"},
                actor_store_id=s.id, user_role="front_desk_agent",
            )
