"""Validation + error-path coverage closure.

Targets the specific uncovered ValueError / PermissionError / status-guard
branches identified in the per-file coverage report:

  - ticket_service.py       lines 69, 71, 85-88, 138-153, 271, 366, 442, 656...
  - qc_service.py           lines 62-66, 84-90, 137-148, 287-354
  - export_service.py       lines 111, 175-193, 222-239, 274, 396-397
  - member_service.py       lines 134, 180, 221-229, 284-350
  - schedule_service.py     lines 36, 71-79, 184-186
  - price_override_service  lines 53, 85-91, 168, 215-220, 282-287
  - traceability_service    lines 107, 150, 165, 245, 271
  - repositories            delete + list_by_* methods on every repo
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fullstack", "backend"))

import pytest

from src.database import get_connection, init_db
from src.enums.user_role import UserRole
from src.models.batch import Batch
from src.models.buyback_ticket import BuybackTicket
from src.models.club_organization import ClubOrganization
from src.models.export_request import ExportRequest
from src.models.member import Member
from src.models.notification_template import NotificationTemplate
from src.models.pricing_rule import PricingRule
from src.models.qc_inspection import QCInspection
from src.models.quarantine_record import QuarantineRecord
from src.models.recall_run import RecallRun
from src.models.schedule_adjustment_request import ScheduleAdjustmentRequest
from src.models.service_table import ServiceTable
from src.models.settings import Settings
from src.models.store import Store
from src.models.table_session import TableSession
from src.models.ticket_message_log import TicketMessageLog
from src.models.user import User
from src.models.user_session import UserSession
from src.models.variance_approval_request import VarianceApprovalRequest
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
    p = str(tmp_path / "vc.db")
    init_db(p).close()
    conn = get_connection(p)
    yield conn
    conn.close()


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _store(db, code="VC"):
    s = StoreRepository(db).create(Store(code=code, name=code))
    SettingsRepository(db).create(Settings(store_id=s.id))
    db.commit()
    return s


def _user(db, sid, name, role="front_desk_agent", password_hash="x"):
    u = UserRepository(db).create(User(
        store_id=sid, username=name, password_hash=password_hash,
        display_name=name, role=role,
    ))
    db.commit()
    return u


def _ticket(db, sid, uid, status="intake_open"):
    t = BuybackTicketRepository(db).create(BuybackTicket(
        store_id=sid, created_by_user_id=uid,
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


def _qc_svc(db):
    return QCService(
        QCInspectionRepository(db), QuarantineRecordRepository(db),
        BatchRepository(db), BatchGenealogyEventRepository(db),
        SettingsRepository(db), _audit(db),
        auth_service=_auth(db),
        user_repo=UserRepository(db),
        ticket_repo=BuybackTicketRepository(db),
    )


# ════════════════════════════════════════════════════════════
# Constructor guards (cheap lines, multiple files)
# ════════════════════════════════════════════════════════════

class TestConstructorGuards:
    def test_ticket_service_requires_qc_repo(self, db):
        pricing = PricingService(
            PricingRuleRepository(db),
            PricingCalculationSnapshotRepository(db),
            SettingsRepository(db),
        )
        with pytest.raises(ValueError, match="qc_repo"):
            TicketService(
                BuybackTicketRepository(db),
                VarianceApprovalRequestRepository(db),
                pricing, _audit(db),
                auth_service=_auth(db),
                qc_repo=None,
            )

    def test_ticket_service_requires_auth_service(self, db):
        pricing = PricingService(
            PricingRuleRepository(db),
            PricingCalculationSnapshotRepository(db),
            SettingsRepository(db),
        )
        with pytest.raises(ValueError, match="auth_service"):
            TicketService(
                BuybackTicketRepository(db),
                VarianceApprovalRequestRepository(db),
                pricing, _audit(db),
                auth_service=None,
                qc_repo=QCInspectionRepository(db),
            )

    def test_qc_service_requires_user_repo(self, db):
        with pytest.raises(ValueError, match="user_repo"):
            QCService(
                QCInspectionRepository(db), QuarantineRecordRepository(db),
                BatchRepository(db), BatchGenealogyEventRepository(db),
                SettingsRepository(db), _audit(db),
                auth_service=_auth(db),
                user_repo=None,
                ticket_repo=BuybackTicketRepository(db),
            )

    def test_qc_service_requires_auth_service(self, db):
        with pytest.raises(ValueError, match="auth_service"):
            QCService(
                QCInspectionRepository(db), QuarantineRecordRepository(db),
                BatchRepository(db), BatchGenealogyEventRepository(db),
                SettingsRepository(db), _audit(db),
                auth_service=None,
                user_repo=UserRepository(db),
                ticket_repo=BuybackTicketRepository(db),
            )

    def test_qc_service_requires_ticket_repo(self, db):
        with pytest.raises(ValueError, match="ticket_repo"):
            QCService(
                QCInspectionRepository(db), QuarantineRecordRepository(db),
                BatchRepository(db), BatchGenealogyEventRepository(db),
                SettingsRepository(db), _audit(db),
                auth_service=_auth(db),
                user_repo=UserRepository(db),
                ticket_repo=None,
            )


# ════════════════════════════════════════════════════════════
# TicketService validation branches
# ════════════════════════════════════════════════════════════

class TestTicketValidationBranches:
    def _setup(self, db):
        s = _store(db)
        u = _user(db, s.id, "fdv", "front_desk_agent")
        # Pricing rule so calculate_payout doesn't fail later
        PricingRuleRepository(db).create(PricingRule(
            store_id=s.id, base_rate_per_lb=1.5, priority=1,
            max_ticket_payout=200, max_rate_per_lb=5,
            min_weight_lbs=0.1, max_weight_lbs=1000,
        ))
        db.commit()
        return s, u

    def _create_kwargs(self, s, u, **overrides):
        base = dict(
            store_id=s.id, user_id=u.id, user_role="front_desk_agent",
            username=u.username, actor_store_id=s.id,
            customer_name="C", clothing_category="shirts",
            condition_grade="A", estimated_weight_lbs=5.0,
        )
        base.update(overrides)
        return base

    def test_blank_customer_name(self, db):
        s, u = self._setup(db)
        svc = _ticket_svc(db)
        with pytest.raises(ValueError, match="Customer name"):
            svc.create_ticket(**self._create_kwargs(s, u, customer_name=""))

    def test_blank_category(self, db):
        s, u = self._setup(db)
        svc = _ticket_svc(db)
        with pytest.raises(ValueError, match="Clothing category"):
            svc.create_ticket(**self._create_kwargs(s, u, clothing_category=""))

    def test_blank_grade(self, db):
        s, u = self._setup(db)
        svc = _ticket_svc(db)
        with pytest.raises(ValueError, match="Condition grade"):
            svc.create_ticket(**self._create_kwargs(s, u, condition_grade=""))

    def test_zero_weight(self, db):
        s, u = self._setup(db)
        svc = _ticket_svc(db)
        with pytest.raises(ValueError, match="Estimated weight"):
            svc.create_ticket(**self._create_kwargs(s, u, estimated_weight_lbs=0))

    def test_phone_too_short(self, db):
        s, u = self._setup(db)
        svc = _ticket_svc(db)
        with pytest.raises(ValueError, match="at least 4 digits"):
            svc.create_ticket(**self._create_kwargs(s, u, customer_phone="12"))

    def test_verify_password_no_password(self, db):
        s = _store(db)
        u = _user(db, s.id, "ap", "shift_supervisor")
        svc = _ticket_svc(db)
        with pytest.raises(ValueError, match="Password is required"):
            svc._verify_approver_password(u.id, None)
        with pytest.raises(ValueError, match="Password is required"):
            svc._verify_approver_password(u.id, "")

    def test_verify_password_wrong(self, db):
        s = _store(db)
        # Create user with a real password hash
        auth = _auth(db)
        u = UserRepository(db).create(User(
            store_id=s.id, username="apx",
            password_hash=auth._hash_password("RealPassword1234!"),
            display_name="apx", role="shift_supervisor",
        ))
        db.commit()
        svc = _ticket_svc(db)
        with pytest.raises(PermissionError, match="Invalid password"):
            svc._verify_approver_password(u.id, "WrongPassword1234!")


# ════════════════════════════════════════════════════════════
# QCService validation branches
# ════════════════════════════════════════════════════════════

class TestQCValidationBranches:
    def _setup(self, db):
        s = _store(db)
        qc = _user(db, s.id, "qcv", "qc_inspector")
        fd = _user(db, s.id, "fdq", "front_desk_agent")
        t = _ticket(db, s.id, fd.id, status="awaiting_qc")
        return s, qc, fd, t

    def test_compute_sample_size_invalid_lot(self, db):
        s = _store(db)
        with pytest.raises(ValueError, match="positive"):
            _qc_svc(db).compute_sample_size(s.id, 0)

    def test_inspection_zero_weight(self, db):
        s, qc, fd, t = self._setup(db)
        with pytest.raises(ValueError, match="Actual weight"):
            _qc_svc(db).create_inspection(
                ticket_id=t.id, store_id=s.id,
                inspector_user_id=qc.id, inspector_username=qc.username,
                inspector_role="qc_inspector", actor_store_id=s.id,
                actual_weight_lbs=0, lot_size=5,
                nonconformance_count=0, inspection_outcome="pass",
            )

    def test_inspection_zero_lot_size(self, db):
        s, qc, fd, t = self._setup(db)
        with pytest.raises(ValueError, match="Lot size"):
            _qc_svc(db).create_inspection(
                ticket_id=t.id, store_id=s.id,
                inspector_user_id=qc.id, inspector_username=qc.username,
                inspector_role="qc_inspector", actor_store_id=s.id,
                actual_weight_lbs=5.0, lot_size=0,
                nonconformance_count=0, inspection_outcome="pass",
            )

    def test_inspection_negative_nonconformance(self, db):
        s, qc, fd, t = self._setup(db)
        with pytest.raises(ValueError, match="Nonconformance"):
            _qc_svc(db).create_inspection(
                ticket_id=t.id, store_id=s.id,
                inspector_user_id=qc.id, inspector_username=qc.username,
                inspector_role="qc_inspector", actor_store_id=s.id,
                actual_weight_lbs=5.0, lot_size=5,
                nonconformance_count=-1, inspection_outcome="pass",
            )

    def test_inspection_invalid_outcome(self, db):
        s, qc, fd, t = self._setup(db)
        with pytest.raises(ValueError, match="Invalid inspection outcome"):
            _qc_svc(db).create_inspection(
                ticket_id=t.id, store_id=s.id,
                inspector_user_id=qc.id, inspector_username=qc.username,
                inspector_role="qc_inspector", actor_store_id=s.id,
                actual_weight_lbs=5.0, lot_size=5,
                nonconformance_count=0, inspection_outcome="invalid_outcome",
            )

    def test_inspection_missing_ticket(self, db):
        s, qc, fd, t = self._setup(db)
        with pytest.raises(ValueError, match="Ticket .* not found"):
            _qc_svc(db).create_inspection(
                ticket_id=99999, store_id=s.id,
                inspector_user_id=qc.id, inspector_username=qc.username,
                inspector_role="qc_inspector", actor_store_id=s.id,
                actual_weight_lbs=5.0, lot_size=5,
                nonconformance_count=0, inspection_outcome="pass",
            )

    def test_inspection_cross_store_ticket(self, db):
        s = _store(db)
        s2 = _store(db, "OTHER")
        qc = _user(db, s.id, "qccross", "qc_inspector")
        fd = _user(db, s.id, "fdcross", "front_desk_agent")
        t_other = _ticket(db, s2.id, fd.id, status="awaiting_qc")
        with pytest.raises(PermissionError, match="Cross-store"):
            _qc_svc(db).create_inspection(
                ticket_id=t_other.id, store_id=s.id,
                inspector_user_id=qc.id, inspector_username=qc.username,
                inspector_role="qc_inspector", actor_store_id=s.id,
                actual_weight_lbs=5.0, lot_size=5,
                nonconformance_count=0, inspection_outcome="pass",
            )

    def test_quarantine_missing_batch(self, db):
        s, qc, fd, t = self._setup(db)
        with pytest.raises(ValueError, match="Batch .* not found"):
            _qc_svc(db).create_quarantine(
                ticket_id=t.id, batch_id=99999,
                user_id=qc.id, username=qc.username,
                actor_store_id=s.id, user_role="qc_inspector",
            )

    def test_quarantine_missing_ticket(self, db):
        s, qc, fd, t = self._setup(db)
        b = BatchRepository(db).create(Batch(store_id=s.id, batch_code="QB"))
        db.commit()
        with pytest.raises(ValueError, match="Ticket .* not found"):
            _qc_svc(db).create_quarantine(
                ticket_id=99999, batch_id=b.id,
                user_id=qc.id, username=qc.username,
                actor_store_id=s.id, user_role="qc_inspector",
            )

    def test_quarantine_cross_store(self, db):
        s = _store(db)
        s2 = _store(db, "Q2")
        qc = _user(db, s.id, "qcq", "qc_inspector")
        fd = _user(db, s.id, "fdq2", "front_desk_agent")
        t = _ticket(db, s.id, fd.id)
        b = BatchRepository(db).create(Batch(store_id=s2.id, batch_code="OB"))
        db.commit()
        with pytest.raises(ValueError, match="different stores"):
            _qc_svc(db).create_quarantine(
                ticket_id=t.id, batch_id=b.id,
                user_id=qc.id, username=qc.username,
                actor_store_id=s.id, user_role="qc_inspector",
            )

    def test_resolve_quarantine_missing(self, db):
        s, qc, fd, t = self._setup(db)
        with pytest.raises(ValueError):
            _qc_svc(db).resolve_quarantine(
                quarantine_id=99999, disposition="scrap",
                user_id=qc.id, username=qc.username,
                user_role="qc_inspector", actor_store_id=s.id,
            )


# ════════════════════════════════════════════════════════════
# ExportService validation branches
# ════════════════════════════════════════════════════════════

class TestExportValidationBranches:
    def _svc(self, db):
        return ExportService(
            ExportRequestRepository(db), BuybackTicketRepository(db),
            SettingsRepository(db), _audit(db),
            auth_service=_auth(db),
            store_repo=StoreRepository(db),
        )

    def test_create_blank_export_type(self, db):
        s = _store(db)
        u = _user(db, s.id, "sup_ex", "shift_supervisor")
        with pytest.raises(ValueError, match="Export type is required"):
            self._svc(db).create_export_request(
                store_id=s.id, user_id=u.id, username=u.username,
                user_role="shift_supervisor", actor_store_id=s.id,
                export_type="",
            )

    def test_approve_unknown_request(self, db):
        s = _store(db)
        u = _user(db, s.id, "sup_ex2", "shift_supervisor")
        with pytest.raises(ValueError, match="not found"):
            self._svc(db).approve_export(
                request_id=99999, approver_user_id=u.id,
                approver_username=u.username, approver_role="shift_supervisor",
                password="x", approver_store_id=s.id,
            )

    def test_reject_unknown_request(self, db):
        s = _store(db)
        u = _user(db, s.id, "sup_er", "shift_supervisor")
        with pytest.raises(ValueError, match="not found"):
            self._svc(db).reject_export(
                request_id=99999, approver_user_id=u.id,
                approver_username=u.username, approver_role="shift_supervisor",
                reason="r", approver_store_id=s.id,
            )

    def test_execute_unknown_request(self, db):
        s = _store(db)
        u = _user(db, s.id, "sup_ee", "shift_supervisor")
        with pytest.raises(ValueError, match="not found"):
            self._svc(db).execute_export(
                request_id=99999, user_id=u.id, username=u.username,
                actor_store_id=s.id, user_role="shift_supervisor",
            )

    def test_approve_not_pending(self, db):
        s = _store(db)
        sup1 = _user(db, s.id, "sup_a1", "shift_supervisor")
        sup2 = _user(db, s.id, "sup_a2", "shift_supervisor")
        # Pre-create an already-approved request
        r = ExportRequestRepository(db).create(ExportRequest(
            store_id=s.id, requested_by_user_id=sup1.id,
            export_type="tickets", status="approved",
        ))
        db.commit()
        with pytest.raises(ValueError, match="not pending"):
            self._svc(db).approve_export(
                request_id=r.id, approver_user_id=sup2.id,
                approver_username=sup2.username, approver_role="shift_supervisor",
                password="x", approver_store_id=s.id,
            )

    def test_reject_not_pending(self, db):
        s = _store(db)
        sup1 = _user(db, s.id, "sup_b1", "shift_supervisor")
        sup2 = _user(db, s.id, "sup_b2", "shift_supervisor")
        r = ExportRequestRepository(db).create(ExportRequest(
            store_id=s.id, requested_by_user_id=sup1.id,
            export_type="tickets", status="rejected",
        ))
        db.commit()
        with pytest.raises(ValueError, match="not pending"):
            self._svc(db).reject_export(
                request_id=r.id, approver_user_id=sup2.id,
                approver_username=sup2.username, approver_role="shift_supervisor",
                reason="r", approver_store_id=s.id,
            )


# ════════════════════════════════════════════════════════════
# MemberService validation branches
# ════════════════════════════════════════════════════════════

class TestMemberValidationBranches:
    def _svc(self, db):
        return MemberService(
            MemberRepository(db), MemberHistoryEventRepository(db),
            ClubOrganizationRepository(db), _audit(db),
        )

    def test_create_org_blank_name(self, db):
        s = _store(db)
        u = _user(db, s.id, "ad", "administrator")
        with pytest.raises(ValueError, match="Organization name"):
            self._svc(db).create_organization(
                name="", user_id=u.id, username=u.username,
                user_role="administrator",
            )

    def test_update_org_unknown(self, db):
        s = _store(db)
        u = _user(db, s.id, "ad2", "administrator")
        with pytest.raises(ValueError, match="not found"):
            self._svc(db).update_organization(
                org_id=99999, user_id=u.id, username=u.username,
                user_role="administrator", name="X",
            )

    def test_add_member_blank_name(self, db):
        s = _store(db)
        u = _user(db, s.id, "ad3", "administrator")
        org = ClubOrganizationRepository(db).create(ClubOrganization(name="O"))
        db.commit()
        with pytest.raises(ValueError, match="Full name"):
            self._svc(db).add_member(
                org_id=org.id, full_name="",
                user_id=u.id, username=u.username,
                user_role="administrator",
            )

    def test_add_member_unknown_org(self, db):
        s = _store(db)
        u = _user(db, s.id, "ad4", "administrator")
        with pytest.raises(ValueError, match="Organization"):
            self._svc(db).add_member(
                org_id=99999, full_name="X",
                user_id=u.id, username=u.username,
                user_role="administrator",
            )

    def test_remove_member_unknown(self, db):
        s = _store(db)
        u = _user(db, s.id, "ad5", "administrator")
        with pytest.raises(ValueError, match="not found"):
            self._svc(db).remove_member(
                member_id=99999,
                user_id=u.id, username=u.username,
                user_role="administrator",
            )

    def test_transfer_member_unknown(self, db):
        s = _store(db)
        u = _user(db, s.id, "ad6", "administrator")
        with pytest.raises(ValueError, match="Member"):
            self._svc(db).transfer_member(
                member_id=99999, target_org_id=1,
                user_id=u.id, username=u.username,
                user_role="administrator",
            )

    def test_transfer_to_unknown_org(self, db):
        s = _store(db)
        u = _user(db, s.id, "ad7", "administrator")
        org = ClubOrganizationRepository(db).create(ClubOrganization(name="O7"))
        db.commit()
        m = MemberRepository(db).create(Member(
            club_organization_id=org.id, full_name="X",
            status="active", joined_at=_now(),
        ))
        db.commit()
        with pytest.raises(ValueError, match="Target organization"):
            self._svc(db).transfer_member(
                member_id=m.id, target_org_id=99999,
                user_id=u.id, username=u.username,
                user_role="administrator",
            )

    def test_csv_validate_empty_file(self, db):
        ok, msg = self._svc(db).validate_csv(b"")
        assert ok is False
        assert "empty" in msg.lower()

    def test_csv_validate_too_large(self, db):
        big = b"a,b,c\n" + b"x,y,z\n" * 1_500_000
        ok, msg = self._svc(db).validate_csv(big[:6 * 1024 * 1024])
        assert ok is False
        assert "exceeds" in msg.lower() or "5MB" in msg

    def test_csv_validate_nul_bytes(self, db):
        ok, msg = self._svc(db).validate_csv(b"full_name,organization_id\n\x00,1\n")
        assert ok is False

    def test_csv_validate_no_header(self, db):
        ok, msg = self._svc(db).validate_csv(b"\n")
        assert ok is False

    def test_csv_validate_missing_required_columns(self, db):
        ok, msg = self._svc(db).validate_csv(b"name,age\nA,1\n")
        assert ok is False
        assert "required" in msg.lower() or "Missing" in msg

    def test_csv_validate_no_data_rows(self, db):
        ok, msg = self._svc(db).validate_csv(b"full_name,organization_id\n")
        assert ok is False

    def test_csv_import_admin_required(self, db):
        s = _store(db)
        with pytest.raises(PermissionError):
            self._svc(db).import_members_csv(
                file_content=b"full_name,organization_id\nX,1\n",
                user_id=1, username="u", user_role="front_desk_agent",
            )


# ════════════════════════════════════════════════════════════
# Schedule + PriceOverride + Traceability validation branches
# ════════════════════════════════════════════════════════════

class TestApprovalServicesBranches:
    def test_schedule_approve_unknown(self, db):
        s = _store(db)
        u = _user(db, s.id, "sup_su", "shift_supervisor")
        svc = ScheduleService(
            ScheduleAdjustmentRequestRepository(db), _audit(db),
            auth_service=_auth(db),
        )
        with pytest.raises(ValueError, match="not found"):
            svc.approve_adjustment(
                request_id=99999, approver_user_id=u.id,
                approver_username=u.username, approver_role="shift_supervisor",
                password="x", approver_store_id=s.id,
            )

    def test_schedule_reject_unknown(self, db):
        s = _store(db)
        u = _user(db, s.id, "sup_sr", "shift_supervisor")
        svc = ScheduleService(
            ScheduleAdjustmentRequestRepository(db), _audit(db),
            auth_service=_auth(db),
        )
        with pytest.raises(ValueError, match="not found"):
            svc.reject_adjustment(
                request_id=99999, approver_user_id=u.id,
                approver_username=u.username, approver_role="shift_supervisor",
                reason="r", approver_store_id=s.id,
            )

    def test_schedule_self_approve_forbidden(self, db):
        s = _store(db)
        u = _user(db, s.id, "sup_sa", "shift_supervisor")
        repo = ScheduleAdjustmentRequestRepository(db)
        r = repo.create(ScheduleAdjustmentRequest(
            store_id=s.id, requested_by_user_id=u.id,
            adjustment_type="t", target_entity_type="user",
            target_entity_id="1", before_value="a", after_value="b",
            reason="r", status="pending",
        ))
        db.commit()
        svc = ScheduleService(repo, _audit(db), auth_service=_auth(db))
        with pytest.raises(PermissionError):
            svc.approve_adjustment(
                request_id=r.id, approver_user_id=u.id,
                approver_username=u.username, approver_role="shift_supervisor",
                password="x", approver_store_id=s.id,
            )

    def test_price_override_request_unknown_ticket(self, db):
        s = _store(db)
        u = _user(db, s.id, "fdpo", "front_desk_agent")
        svc = PriceOverrideService(
            PriceOverrideRequestRepository(db),
            BuybackTicketRepository(db),
            _audit(db),
            auth_service=_auth(db),
        )
        with pytest.raises(ValueError):
            svc.request_price_override(
                ticket_id=99999, proposed_payout=10.0, reason="r",
                user_id=u.id, username=u.username,
                user_role="front_desk_agent", actor_store_id=s.id,
            )

    def test_price_override_approve_unknown(self, db):
        s = _store(db)
        u = _user(db, s.id, "sup_pa", "shift_supervisor")
        svc = PriceOverrideService(
            PriceOverrideRequestRepository(db),
            BuybackTicketRepository(db),
            _audit(db),
            auth_service=_auth(db),
        )
        with pytest.raises(ValueError):
            svc.approve_price_override(
                request_id=99999, approver_user_id=u.id,
                approver_username=u.username, approver_role="shift_supervisor",
                password="x", approver_store_id=s.id,
            )

    def test_price_override_reject_unknown(self, db):
        s = _store(db)
        u = _user(db, s.id, "sup_pr", "shift_supervisor")
        svc = PriceOverrideService(
            PriceOverrideRequestRepository(db),
            BuybackTicketRepository(db),
            _audit(db),
            auth_service=_auth(db),
        )
        with pytest.raises(ValueError):
            svc.reject_price_override(
                request_id=99999, approver_user_id=u.id,
                approver_username=u.username, approver_role="shift_supervisor",
                reason="r", approver_store_id=s.id,
            )

    def test_price_override_execute_unknown(self, db):
        s = _store(db)
        u = _user(db, s.id, "sup_pe", "shift_supervisor")
        svc = PriceOverrideService(
            PriceOverrideRequestRepository(db),
            BuybackTicketRepository(db),
            _audit(db),
            auth_service=_auth(db),
        )
        with pytest.raises(ValueError):
            svc.execute_override(
                request_id=99999, user_id=u.id, username=u.username,
                user_role="shift_supervisor", actor_store_id=s.id,
            )

    def test_traceability_batch_unknown(self, db):
        s = _store(db)
        u = _user(db, s.id, "qct", "qc_inspector")
        svc = TraceabilityService(
            BatchRepository(db), BatchGenealogyEventRepository(db),
            RecallRunRepository(db), _audit(db),
        )
        with pytest.raises(ValueError):
            svc.transition_batch(
                batch_id=99999, target_status="received",
                user_id=u.id, username=u.username,
                actor_store_id=s.id, user_role="qc_inspector",
            )

    def test_traceability_lineage_unknown(self, db):
        s = _store(db)
        svc = TraceabilityService(
            BatchRepository(db), BatchGenealogyEventRepository(db),
            RecallRunRepository(db), _audit(db),
        )
        with pytest.raises(ValueError):
            svc.get_batch_lineage(
                batch_id=99999, actor_store_id=s.id,
                user_role="qc_inspector",
            )

    def test_traceability_recall_unknown(self, db):
        s = _store(db)
        svc = TraceabilityService(
            BatchRepository(db), BatchGenealogyEventRepository(db),
            RecallRunRepository(db), _audit(db),
        )
        # Recall view is admin-only — try with admin to hit the "not found"
        # branch instead of the permission gate.
        with pytest.raises(ValueError):
            svc.get_recall_run(
                run_id=99999, actor_store_id=s.id,
                user_role="administrator",
            )


# ════════════════════════════════════════════════════════════
# Repository delete + secondary list paths
# ════════════════════════════════════════════════════════════

class TestRepoDeletePaths:
    def test_store_delete(self, db):
        repo = StoreRepository(db)
        s = repo.create(Store(code="DEL", name="DEL"))
        db.commit()
        repo.delete(s.id)
        db.commit()
        assert repo.get_by_id(s.id) is None

    def test_user_delete(self, db):
        s = _store(db)
        repo = UserRepository(db)
        u = repo.create(User(
            store_id=s.id, username="udel", password_hash="x",
            display_name="x", role="front_desk_agent",
        ))
        db.commit()
        repo.delete(u.id)
        db.commit()
        assert repo.get_by_id(u.id) is None

    def test_user_session_delete(self, db):
        s = _store(db)
        u = _user(db, s.id, "ud")
        repo = UserSessionRepository(db)
        sess = repo.create(UserSession(
            user_id=u.id, session_nonce="n_del",
            cookie_signature_version="v1", csrf_secret="c",
            expires_at=_now(),
        ))
        db.commit()
        repo.delete(sess.id)
        db.commit()
        assert repo.get_by_id(sess.id) is None

    def test_pricing_calc_snapshot_via_create_only(self, db):
        # Snapshot has no public delete; just confirm get returns None for missing
        repo = PricingCalculationSnapshotRepository(db)
        assert repo.get_by_id(99999) is None

    def test_recall_delete(self, db):
        s = _store(db)
        u = _user(db, s.id, "ru")
        repo = RecallRunRepository(db)
        r = repo.create(RecallRun(
            store_id=s.id, requested_by_user_id=u.id,
            result_count=0, result_json="[]",
        ))
        db.commit()
        repo.delete(r.id)
        db.commit()
        assert repo.get_by_id(r.id) is None

    def test_template_delete(self, db):
        repo = NotificationTemplateRepository(db)
        t = repo.create(NotificationTemplate(
            store_id=None, template_code="del_tpl",
            name="N", body="B", event_type="e",
        ))
        db.commit()
        repo.delete(t.id)
        db.commit()
        assert repo.get_by_id(t.id) is None

    def test_message_log_delete(self, db):
        s = _store(db)
        u = _user(db, s.id, "mu")
        t = _ticket(db, s.id, u.id)
        repo = TicketMessageLogRepository(db)
        m = repo.create(TicketMessageLog(
            ticket_id=t.id, actor_user_id=u.id,
            message_body="x", contact_channel="logged_message",
            call_attempt_status="not_applicable",
        ))
        db.commit()
        repo.delete(m.id)
        db.commit()
        assert repo.get_by_id(m.id) is None

    def test_service_table_delete(self, db):
        s = _store(db)
        repo = ServiceTableRepository(db)
        t = repo.create(ServiceTable(
            store_id=s.id, table_code="DTBL", area_type="intake_table",
        ))
        db.commit()
        repo.delete(t.id)
        db.commit()
        assert repo.get_by_id(t.id) is None

    def test_table_session_delete(self, db):
        s = _store(db)
        u = _user(db, s.id, "hsd", role="host")
        st = ServiceTableRepository(db).create(ServiceTable(
            store_id=s.id, table_code="DTS", area_type="intake_table",
        ))
        repo = TableSessionRepository(db)
        sess = repo.create(TableSession(
            store_id=s.id, table_id=st.id, opened_by_user_id=u.id,
            current_state="occupied",
        ))
        db.commit()
        repo.delete(sess.id)
        db.commit()
        assert repo.get_by_id(sess.id) is None

    def test_batch_delete(self, db):
        s = _store(db)
        repo = BatchRepository(db)
        b = repo.create(Batch(store_id=s.id, batch_code="BD"))
        db.commit()
        repo.delete(b.id)
        db.commit()
        assert repo.get_by_id(b.id) is None

    def test_quarantine_delete(self, db):
        s = _store(db)
        u = _user(db, s.id, "qd")
        t = _ticket(db, s.id, u.id)
        b = BatchRepository(db).create(Batch(store_id=s.id, batch_code="QD"))
        db.commit()
        repo = QuarantineRecordRepository(db)
        q = repo.create(QuarantineRecord(
            ticket_id=t.id, batch_id=b.id, created_by_user_id=u.id,
        ))
        db.commit()
        repo.delete(q.id)
        db.commit()
        assert repo.get_by_id(q.id) is None

    def test_qc_inspection_delete(self, db):
        s = _store(db)
        u = _user(db, s.id, "qid", "qc_inspector")
        t = _ticket(db, s.id, u.id, status="awaiting_qc")
        repo = QCInspectionRepository(db)
        ins = repo.create(QCInspection(
            ticket_id=t.id, inspector_user_id=u.id,
            actual_weight_lbs=5.0, lot_size=5, sample_size=1,
            nonconformance_count=0, inspection_outcome="pass",
        ))
        db.commit()
        repo.delete(ins.id)
        db.commit()
        assert repo.get_by_id(ins.id) is None

    def test_export_delete(self, db):
        s = _store(db)
        u = _user(db, s.id, "exd", "shift_supervisor")
        repo = ExportRequestRepository(db)
        r = repo.create(ExportRequest(
            store_id=s.id, requested_by_user_id=u.id,
            export_type="tickets", status="pending",
        ))
        db.commit()
        repo.delete(r.id)
        db.commit()
        assert repo.get_by_id(r.id) is None

    def test_schedule_delete(self, db):
        s = _store(db)
        u = _user(db, s.id, "sd", "shift_supervisor")
        repo = ScheduleAdjustmentRequestRepository(db)
        r = repo.create(ScheduleAdjustmentRequest(
            store_id=s.id, requested_by_user_id=u.id,
            adjustment_type="t", target_entity_type="user",
            target_entity_id="1", before_value="a", after_value="b",
            reason="r", status="pending",
        ))
        db.commit()
        repo.delete(r.id)
        db.commit()
        assert repo.get_by_id(r.id) is None

    def test_variance_delete(self, db):
        s = _store(db)
        u = _user(db, s.id, "vd")
        t = _ticket(db, s.id, u.id, status="variance_pending_supervisor")
        repo = VarianceApprovalRequestRepository(db)
        v = repo.create(VarianceApprovalRequest(
            ticket_id=t.id, requested_by_user_id=u.id,
            variance_amount=10.0, variance_pct=15.0,
            threshold_amount=5.0, threshold_pct=5.0,
            confirmation_note="n", status="pending",
        ))
        db.commit()
        repo.delete(v.id)
        db.commit()
        assert repo.get_by_id(v.id) is None

    def test_table_activity_delete(self, db):
        s = _store(db)
        u = _user(db, s.id, "tad", role="host")
        st = ServiceTableRepository(db).create(ServiceTable(
            store_id=s.id, table_code="TAD", area_type="intake_table",
        ))
        sess = TableSessionRepository(db).create(TableSession(
            store_id=s.id, table_id=st.id, opened_by_user_id=u.id,
            current_state="occupied",
        ))
        repo = TableActivityEventRepository(db)
        from src.models.table_activity_event import TableActivityEvent
        ev = repo.create(TableActivityEvent(
            table_session_id=sess.id, event_type="opened",
            actor_user_id=u.id,
        ))
        db.commit()
        repo.delete(ev.id)
        db.commit()
        assert repo.get_by_id(ev.id) is None

    def test_genealogy_event_delete(self, db):
        s = _store(db)
        u = _user(db, s.id, "ged")
        b = BatchRepository(db).create(Batch(store_id=s.id, batch_code="GD"))
        db.commit()
        repo = BatchGenealogyEventRepository(db)
        from src.models.batch_genealogy_event import BatchGenealogyEvent
        ev = repo.create(BatchGenealogyEvent(
            batch_id=b.id, event_type="received", actor_user_id=u.id,
        ))
        db.commit()
        repo.delete(ev.id)
        db.commit()
        assert repo.get_by_id(ev.id) is None

    def test_member_delete(self, db):
        org = ClubOrganizationRepository(db).create(ClubOrganization(name="MD"))
        db.commit()
        repo = MemberRepository(db)
        m = repo.create(Member(
            club_organization_id=org.id, full_name="MD",
            status="active", joined_at=_now(),
        ))
        db.commit()
        repo.delete(m.id)
        db.commit()
        assert repo.get_by_id(m.id) is None

    def test_member_history_delete(self, db):
        s = _store(db)
        u = _user(db, s.id, "mhd")
        org = ClubOrganizationRepository(db).create(ClubOrganization(name="MH"))
        db.commit()
        m = MemberRepository(db).create(Member(
            club_organization_id=org.id, full_name="X",
            status="active", joined_at=_now(),
        ))
        db.commit()
        repo = MemberHistoryEventRepository(db)
        from src.models.member_history_event import MemberHistoryEvent
        ev = repo.create(MemberHistoryEvent(
            member_id=m.id, actor_user_id=u.id, event_type="joined",
        ))
        db.commit()
        repo.delete(ev.id)
        db.commit()
        assert repo.get_by_id(ev.id) is None

    def test_org_delete(self, db):
        repo = ClubOrganizationRepository(db)
        org = repo.create(ClubOrganization(name="OD"))
        db.commit()
        repo.delete(org.id)
        db.commit()
        assert repo.get_by_id(org.id) is None

    def test_pricing_rule_delete(self, db):
        s = _store(db)
        repo = PricingRuleRepository(db)
        r = repo.create(PricingRule(
            store_id=s.id, base_rate_per_lb=1.0, priority=1,
            max_ticket_payout=200, max_rate_per_lb=5,
            min_weight_lbs=0.1, max_weight_lbs=1000,
        ))
        db.commit()
        repo.delete(r.id)
        db.commit()
        assert repo.get_by_id(r.id) is None

    def test_price_override_get_by_id(self, db):
        # PriceOverrideRequestRepository has no delete method — exercise
        # get_by_id round-trip instead.
        s = _store(db)
        u = _user(db, s.id, "pod")
        t = _ticket(db, s.id, u.id)
        from src.models.price_override_request import PriceOverrideRequest
        repo = PriceOverrideRequestRepository(db)
        r = repo.create(PriceOverrideRequest(
            ticket_id=t.id, store_id=s.id, requested_by_user_id=u.id,
            original_payout=10.0, proposed_payout=20.0,
            reason="r", status="pending",
        ))
        db.commit()
        assert repo.get_by_id(r.id).proposed_payout == 20.0
