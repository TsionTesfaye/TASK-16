"""Final branch-coverage closure to push total coverage past 95%.

Targets specific uncovered lines:
  - helpers.py: serialize() shortcuts + session_store_id admin paths +
    require_fields error path + is_htmx
  - export_service.py: approve/reject success paths (settings must
    require approval for these to fire)
  - ticket_service.py: status-guard rejections (calling submit/cancel/
    dial/refund on tickets in wrong state)
  - qc_service.py: nonconformance escalation + concession edge cases
  - schedule_service.py: pending-approval status guards
  - price_override_service.py: status guards + concurrent-execute paths
  - notification_service.py: validation branches
  - traceability_service.py: cross-store lineage rejection + admin-only
    recall paths
  - partials_routes.py: dial/refund/initiate-refund partials with
    legitimate role and unknown ticket
"""
import io
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fullstack", "backend"))

import pytest
from flask import Flask, g

from src.database import get_connection, init_db
from src.models.batch import Batch
from src.models.buyback_ticket import BuybackTicket
from src.models.club_organization import ClubOrganization
from src.models.export_request import ExportRequest
from src.models.member import Member
from src.models.notification_template import NotificationTemplate
from src.models.price_override_request import PriceOverrideRequest
from src.models.qc_inspection import QCInspection
from src.models.quarantine_record import QuarantineRecord
from src.models.recall_run import RecallRun
from src.models.schedule_adjustment_request import ScheduleAdjustmentRequest
from src.models.settings import Settings
from src.models.store import Store
from src.models.user import User
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
from src.services.notification_service import NotificationService
from src.services.price_override_service import PriceOverrideService
from src.services.pricing_service import PricingService
from src.services.qc_service import QCService
from src.services.schedule_service import ScheduleService
from src.services.ticket_service import TicketService
from src.services.traceability_service import TraceabilityService


@pytest.fixture
def db(tmp_path):
    p = str(tmp_path / "br.db")
    init_db(p).close()
    conn = get_connection(p)
    yield conn
    conn.close()


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _store(db, code="BR", require_approval=False):
    s = StoreRepository(db).create(Store(code=code, name=code))
    SettingsRepository(db).create(Settings(
        store_id=s.id,
        export_requires_supervisor_default=require_approval,
    ))
    db.commit()
    return s


def _user(db, sid, name, role="front_desk_agent", password="TestPassword1234!"):
    auth = AuthService(
        UserRepository(db), UserSessionRepository(db),
        SettingsRepository(db), AuditService(AuditLogRepository(db)),
    )
    u = UserRepository(db).create(User(
        store_id=sid, username=name,
        password_hash=auth._hash_password(password),
        display_name=name, role=role,
    ))
    db.commit()
    return u


def _ticket(db, sid, uid, status="intake_open", final_payout=None):
    t = BuybackTicketRepository(db).create(BuybackTicket(
        store_id=sid, created_by_user_id=uid,
        customer_name="C", clothing_category="shirts",
        condition_grade="A", estimated_weight_lbs=5.0,
        estimated_payout=7.5, final_payout=final_payout, status=status,
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


def _export_svc(db):
    return ExportService(
        ExportRequestRepository(db), BuybackTicketRepository(db),
        SettingsRepository(db), _audit(db),
        auth_service=_auth(db),
        store_repo=StoreRepository(db),
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


def _po_svc(db):
    return PriceOverrideService(
        PriceOverrideRequestRepository(db),
        BuybackTicketRepository(db),
        _audit(db),
        auth_service=_auth(db),
    )


def _sched_svc(db):
    return ScheduleService(
        ScheduleAdjustmentRequestRepository(db), _audit(db),
        auth_service=_auth(db),
    )


# ════════════════════════════════════════════════════════════
# helpers.py: serialize() + success_response/meta + require_fields
# ════════════════════════════════════════════════════════════

class TestHelpersCoverage:
    @pytest.fixture
    def app(self):
        return Flask(__name__)

    def test_serialize_none(self):
        from src.routes.helpers import serialize
        assert serialize(None) is None

    def test_serialize_list_of_dataclasses(self):
        from src.routes.helpers import serialize
        from src.models.store import Store
        items = [Store(id=1, code="A", name="A"), Store(id=2, code="B", name="B")]
        out = serialize(items)
        assert isinstance(out, list)
        assert out[0]["code"] == "A"
        assert out[1]["code"] == "B"

    def test_serialize_passthrough_primitive(self):
        from src.routes.helpers import serialize
        assert serialize("hello") == "hello"
        assert serialize(42) == 42

    def test_serialize_redacts_secrets(self):
        from src.routes.helpers import serialize
        from src.models.user import User
        u = User(id=1, username="u", password_hash="SECRET", role="x", display_name="x")
        d = serialize(u)
        assert "password_hash" not in d

    def test_serialize_strips_ciphertext_fields(self):
        from src.routes.helpers import serialize
        from src.models.buyback_ticket import BuybackTicket
        t = BuybackTicket(
            id=1, store_id=1, created_by_user_id=1,
            customer_name="X", clothing_category="x",
            condition_grade="A", estimated_weight_lbs=5.0,
            customer_phone_ciphertext=b"\x01\x02",
            customer_phone_iv=b"\x03",
            customer_phone_last4="1234",
        )
        d = serialize(t)
        assert "customer_phone_ciphertext" not in d
        assert "customer_phone_iv" not in d
        # last4 is masked
        assert d["customer_phone_last4"].endswith("1234")

    def test_success_response_with_meta(self, app):
        from src.routes.helpers import success_response
        with app.app_context():
            resp, status = success_response({"x": 1}, status=200, meta={"page": 1})
            body = resp.get_json()
            assert body["meta"]["page"] == 1
            assert status == 200

    def test_error_response_with_details(self, app):
        from src.routes.helpers import error_response
        with app.app_context():
            resp, status = error_response(400, "bad", details={"field": "x"})
            body = resp.get_json()
            assert body["error"]["details"]["field"] == "x"

    def test_require_fields_missing_returns_error(self, app):
        from src.routes.helpers import require_fields
        with app.app_context():
            err = require_fields({"a": 1}, "a", "b")
            assert err is not None  # missing 'b'
            resp, status = err
            assert status == 400

    def test_require_fields_all_present(self, app):
        from src.routes.helpers import require_fields
        with app.app_context():
            assert require_fields({"a": 1, "b": "x"}, "a", "b") is None

    def test_session_store_id_admin_with_value(self, app):
        from src.routes.helpers import session_store_id
        from src.models.user import User
        with app.test_request_context("/"):
            g.current_user = User(role="administrator", store_id=None)
            assert session_store_id(client_value="42") == 42
            assert session_store_id(client_value=None) is None
            assert session_store_id(client_value="not-an-int") is None

    def test_session_store_id_pinned_user(self, app):
        from src.routes.helpers import session_store_id
        from src.models.user import User
        with app.test_request_context("/"):
            g.current_user = User(role="front_desk_agent", store_id=7)
            # Client value ignored for non-admin
            assert session_store_id(client_value="999") == 7

    def test_is_htmx_helper(self, app):
        from src.routes.helpers import is_htmx
        with app.test_request_context("/", headers={"HX-Request": "true"}):
            assert is_htmx() is True
        with app.test_request_context("/"):
            assert is_htmx() is False

    def test_get_json_body_returns_empty_when_not_json(self, app):
        from src.routes.helpers import get_json_body
        with app.test_request_context("/"):
            assert get_json_body() == {}


# ════════════════════════════════════════════════════════════
# export_service approve / reject SUCCESS paths
# (require settings to demand approval so status starts pending)
# ════════════════════════════════════════════════════════════

class TestExportApprovalSuccessPaths:
    def test_approve_export_success(self, db):
        s = _store(db, "EX_AP", require_approval=True)
        sup1 = _user(db, s.id, "exsup1", "shift_supervisor")
        sup2 = _user(db, s.id, "exsup2", "shift_supervisor")
        svc = _export_svc(db)

        req = svc.create_export_request(
            store_id=s.id, user_id=sup1.id, username=sup1.username,
            user_role="shift_supervisor", actor_store_id=s.id,
            export_type="tickets",
        )
        assert req.status == "pending"

        approved = svc.approve_export(
            request_id=req.id, approver_user_id=sup2.id,
            approver_username=sup2.username, approver_role="shift_supervisor",
            password="TestPassword1234!", approver_store_id=s.id,
        )
        assert approved.status == "approved"

    def test_reject_export_success(self, db):
        s = _store(db, "EX_RJ", require_approval=True)
        sup1 = _user(db, s.id, "rjsup1", "shift_supervisor")
        sup2 = _user(db, s.id, "rjsup2", "shift_supervisor")
        svc = _export_svc(db)

        req = svc.create_export_request(
            store_id=s.id, user_id=sup1.id, username=sup1.username,
            user_role="shift_supervisor", actor_store_id=s.id,
            export_type="tickets",
        )
        assert req.status == "pending"

        rejected = svc.reject_export(
            request_id=req.id, approver_user_id=sup2.id,
            approver_username=sup2.username, approver_role="shift_supervisor",
            reason="not approved", approver_store_id=s.id,
        )
        assert rejected.status == "rejected"

    def test_execute_already_completed_raises(self, db):
        s = _store(db, "EX_DUP")
        sup = _user(db, s.id, "dsup", "shift_supervisor")
        svc = _export_svc(db)
        req = svc.create_export_request(
            store_id=s.id, user_id=sup.id, username=sup.username,
            user_role="shift_supervisor", actor_store_id=s.id,
            export_type="tickets",
        )
        # First execute succeeds (need writable export dir)
        import tempfile
        import src.services.export_service as _es
        tmpdir = tempfile.mkdtemp()
        old_dir = _es.EXPORT_OUTPUT_DIR
        _es.EXPORT_OUTPUT_DIR = tmpdir
        try:
            svc.execute_export(
                request_id=req.id, user_id=sup.id, username=sup.username,
                actor_store_id=s.id, user_role="shift_supervisor",
            )
            # Second execute must fail (already completed)
            with pytest.raises(ValueError):
                svc.execute_export(
                    request_id=req.id, user_id=sup.id, username=sup.username,
                    actor_store_id=s.id, user_role="shift_supervisor",
                )
        finally:
            _es.EXPORT_OUTPUT_DIR = old_dir


# ════════════════════════════════════════════════════════════
# ticket_service status-guard branches
# ════════════════════════════════════════════════════════════

class TestTicketStatusGuards:
    def test_submit_qc_when_not_intake_open(self, db):
        s = _store(db)
        u = _user(db, s.id, "fdg", "front_desk_agent")
        # Ticket already in awaiting_qc — submit_for_qc must reject
        t = _ticket(db, s.id, u.id, status="awaiting_qc")
        with pytest.raises(ValueError):
            _ticket_svc(db).submit_for_qc(
                t.id, u.id, u.username,
                actor_store_id=s.id, user_role="front_desk_agent",
            )

    def test_cancel_completed_ticket_rejected(self, db):
        s = _store(db)
        u = _user(db, s.id, "fdc", "front_desk_agent")
        t = _ticket(db, s.id, u.id, status="completed")
        with pytest.raises(ValueError):
            _ticket_svc(db).cancel_ticket(
                ticket_id=t.id, user_id=u.id, username=u.username,
                user_role="front_desk_agent", reason="x", actor_store_id=s.id,
            )

    def test_initiate_refund_intake_open_rejected(self, db):
        s = _store(db)
        u = _user(db, s.id, "fdr", "front_desk_agent")
        t = _ticket(db, s.id, u.id, status="intake_open")
        with pytest.raises(ValueError):
            _ticket_svc(db).initiate_refund(
                ticket_id=t.id, user_id=u.id, username=u.username,
                user_role="front_desk_agent", actor_store_id=s.id,
            )

    def test_approve_refund_not_pending(self, db):
        s = _store(db)
        u = _user(db, s.id, "fdrr", "front_desk_agent")
        sup = _user(db, s.id, "supr", "shift_supervisor")
        t = _ticket(db, s.id, u.id, status="completed", final_payout=10.0)
        with pytest.raises(ValueError):
            _ticket_svc(db).approve_refund(
                ticket_id=t.id, approver_user_id=sup.id,
                approver_username=sup.username, approver_role="shift_supervisor",
                password="TestPassword1234!", approver_store_id=s.id,
            )

    def test_reject_refund_not_pending(self, db):
        s = _store(db)
        u = _user(db, s.id, "fdrn", "front_desk_agent")
        sup = _user(db, s.id, "supn", "shift_supervisor")
        t = _ticket(db, s.id, u.id, status="completed", final_payout=10.0)
        with pytest.raises(ValueError):
            _ticket_svc(db).reject_refund(
                ticket_id=t.id, approver_user_id=sup.id,
                approver_username=sup.username, approver_role="shift_supervisor",
                reason="x", approver_store_id=s.id,
            )

    def test_refund_self_approval_blocked(self, db):
        """initiator cannot approve their own refund."""
        s = _store(db)
        u = _user(db, s.id, "rsa", "operations_manager")  # ops can both initiate AND approve
        t = _ticket(db, s.id, u.id, status="completed", final_payout=10.0)
        svc = _ticket_svc(db)
        # Ops manager initiates refund
        svc.initiate_refund(
            ticket_id=t.id, user_id=u.id, username=u.username,
            user_role="operations_manager", actor_store_id=s.id,
        )
        # Same ops manager tries to approve their own refund
        with pytest.raises(PermissionError):
            svc.approve_refund(
                ticket_id=t.id, approver_user_id=u.id,
                approver_username=u.username, approver_role="operations_manager",
                password="TestPassword1234!", approver_store_id=s.id,
            )

    def test_dial_unknown_ticket(self, db):
        s = _store(db)
        u = _user(db, s.id, "dl", "front_desk_agent")
        with pytest.raises(ValueError):
            _ticket_svc(db).get_ticket_phone_for_dial(
                ticket_id=99999, user_id=u.id, username=u.username,
                user_role="front_desk_agent", actor_store_id=s.id,
            )

    def test_dial_no_phone_on_ticket(self, db):
        s = _store(db)
        u = _user(db, s.id, "dln", "front_desk_agent")
        t = _ticket(db, s.id, u.id)  # no phone fields
        with pytest.raises(ValueError):
            _ticket_svc(db).get_ticket_phone_for_dial(
                ticket_id=t.id, user_id=u.id, username=u.username,
                user_role="front_desk_agent", actor_store_id=s.id,
            )

    def test_confirm_variance_unknown_ticket(self, db):
        s = _store(db)
        u = _user(db, s.id, "cvn", "front_desk_agent")
        with pytest.raises(ValueError):
            _ticket_svc(db).confirm_variance(
                ticket_id=99999, user_id=u.id, username=u.username,
                confirmation_note="n", actor_store_id=s.id,
                user_role="front_desk_agent",
            )

    def test_confirm_variance_wrong_status(self, db):
        s = _store(db)
        u = _user(db, s.id, "cvs", "front_desk_agent")
        t = _ticket(db, s.id, u.id, status="completed")
        with pytest.raises(ValueError):
            _ticket_svc(db).confirm_variance(
                ticket_id=t.id, user_id=u.id, username=u.username,
                confirmation_note="n", actor_store_id=s.id,
                user_role="front_desk_agent",
            )


# ════════════════════════════════════════════════════════════
# qc_service edge cases (concession + nonconformance escalation)
# ════════════════════════════════════════════════════════════

class TestQCEdgeCases:
    def test_compute_sample_size_returns_full_when_escalated(self, db):
        s = _store(db)
        u = _user(db, s.id, "qcs", "qc_inspector")
        # Pre-seed lots of nonconformances today so escalation kicks in
        t = _ticket(db, s.id, u.id, status="awaiting_qc")
        repo = QCInspectionRepository(db)
        # Add inspections with high nonconformance to push the day total
        for i in range(5):
            repo.create(QCInspection(
                ticket_id=t.id, inspector_user_id=u.id,
                actual_weight_lbs=1.0, lot_size=10, sample_size=1,
                nonconformance_count=5, inspection_outcome="fail",
            ))
        db.commit()
        # Sample size should be the entire lot now (100%)
        size = _qc_svc(db).compute_sample_size(s.id, lot_size=20)
        assert size == 20

    def test_compute_sample_size_uses_default_when_no_settings(self, db):
        # Create a store WITHOUT settings
        s = StoreRepository(db).create(Store(code="NOSET", name="NoSet"))
        db.commit()
        size = _qc_svc(db).compute_sample_size(s.id, lot_size=20)
        # min items default = 3 → result will be max(2, 3) = 3 since 10% of 20=2
        assert size >= 3

    def test_resolve_quarantine_concession_missing_password(self, db):
        s = _store(db)
        qc = _user(db, s.id, "qrc1", "qc_inspector")
        sup = _user(db, s.id, "supqrc", "shift_supervisor")
        fd = _user(db, s.id, "fdqrc", "front_desk_agent")
        t = _ticket(db, s.id, fd.id)
        b = BatchRepository(db).create(Batch(store_id=s.id, batch_code="QC1"))
        db.commit()
        q = QuarantineRecordRepository(db).create(QuarantineRecord(
            ticket_id=t.id, batch_id=b.id, created_by_user_id=qc.id,
        ))
        db.commit()
        with pytest.raises(ValueError):
            _qc_svc(db).resolve_quarantine(
                quarantine_id=q.id, disposition="concession_acceptance",
                user_id=qc.id, username=qc.username, user_role="qc_inspector",
                actor_store_id=s.id,
                concession_supervisor_id=sup.id,
                concession_supervisor_username=sup.username,
                # Missing password
            )

    def test_resolve_quarantine_concession_wrong_supervisor(self, db):
        s = _store(db)
        qc = _user(db, s.id, "qrc2", "qc_inspector")
        not_sup = _user(db, s.id, "notsup", "front_desk_agent")  # wrong role
        fd = _user(db, s.id, "fdqrc2", "front_desk_agent")
        t = _ticket(db, s.id, fd.id)
        b = BatchRepository(db).create(Batch(store_id=s.id, batch_code="QC2"))
        db.commit()
        q = QuarantineRecordRepository(db).create(QuarantineRecord(
            ticket_id=t.id, batch_id=b.id, created_by_user_id=qc.id,
        ))
        db.commit()
        with pytest.raises(PermissionError):
            _qc_svc(db).resolve_quarantine(
                quarantine_id=q.id, disposition="concession_acceptance",
                user_id=qc.id, username=qc.username, user_role="qc_inspector",
                actor_store_id=s.id,
                concession_supervisor_id=not_sup.id,
                concession_supervisor_username=not_sup.username,
                concession_supervisor_password="TestPassword1234!",
            )

    def test_resolve_already_resolved(self, db):
        s = _store(db)
        qc = _user(db, s.id, "qrr", "qc_inspector")
        fd = _user(db, s.id, "fdrr", "front_desk_agent")
        t = _ticket(db, s.id, fd.id)
        b = BatchRepository(db).create(Batch(store_id=s.id, batch_code="QRR"))
        db.commit()
        q = QuarantineRecordRepository(db).create(QuarantineRecord(
            ticket_id=t.id, batch_id=b.id, created_by_user_id=qc.id,
            resolved_at=_now(), disposition="scrap",
        ))
        db.commit()
        with pytest.raises(ValueError):
            _qc_svc(db).resolve_quarantine(
                quarantine_id=q.id, disposition="scrap",
                user_id=qc.id, username=qc.username, user_role="qc_inspector",
                actor_store_id=s.id,
            )


# ════════════════════════════════════════════════════════════
# schedule_service status guards
# ════════════════════════════════════════════════════════════

class TestScheduleStatusGuards:
    def test_approve_already_approved(self, db):
        s = _store(db)
        sup1 = _user(db, s.id, "ssg1", "shift_supervisor")
        sup2 = _user(db, s.id, "ssg2", "shift_supervisor")
        repo = ScheduleAdjustmentRequestRepository(db)
        r = repo.create(ScheduleAdjustmentRequest(
            store_id=s.id, requested_by_user_id=sup1.id,
            adjustment_type="t", target_entity_type="user",
            target_entity_id="1", before_value="a", after_value="b",
            reason="r", status="approved",
        ))
        db.commit()
        with pytest.raises(ValueError):
            _sched_svc(db).approve_adjustment(
                request_id=r.id, approver_user_id=sup2.id,
                approver_username=sup2.username, approver_role="shift_supervisor",
                password="TestPassword1234!", approver_store_id=s.id,
            )

    def test_reject_already_rejected(self, db):
        s = _store(db)
        sup1 = _user(db, s.id, "srg1", "shift_supervisor")
        sup2 = _user(db, s.id, "srg2", "shift_supervisor")
        repo = ScheduleAdjustmentRequestRepository(db)
        r = repo.create(ScheduleAdjustmentRequest(
            store_id=s.id, requested_by_user_id=sup1.id,
            adjustment_type="t", target_entity_type="user",
            target_entity_id="1", before_value="a", after_value="b",
            reason="r", status="rejected",
        ))
        db.commit()
        with pytest.raises(ValueError):
            _sched_svc(db).reject_adjustment(
                request_id=r.id, approver_user_id=sup2.id,
                approver_username=sup2.username, approver_role="shift_supervisor",
                reason="x", approver_store_id=s.id,
            )

    def test_approve_wrong_password(self, db):
        s = _store(db)
        sup1 = _user(db, s.id, "spw1", "shift_supervisor")
        sup2 = _user(db, s.id, "spw2", "shift_supervisor")
        repo = ScheduleAdjustmentRequestRepository(db)
        r = repo.create(ScheduleAdjustmentRequest(
            store_id=s.id, requested_by_user_id=sup1.id,
            adjustment_type="t", target_entity_type="user",
            target_entity_id="1", before_value="a", after_value="b",
            reason="r", status="pending",
        ))
        db.commit()
        with pytest.raises(PermissionError):
            _sched_svc(db).approve_adjustment(
                request_id=r.id, approver_user_id=sup2.id,
                approver_username=sup2.username, approver_role="shift_supervisor",
                password="WrongPassword1234!", approver_store_id=s.id,
            )

    def test_approve_success(self, db):
        s = _store(db)
        sup1 = _user(db, s.id, "spa1", "shift_supervisor")
        sup2 = _user(db, s.id, "spa2", "shift_supervisor")
        svc = _sched_svc(db)
        r = svc.request_adjustment(
            store_id=s.id, user_id=sup1.id, username=sup1.username,
            adjustment_type="t", target_entity_type="user",
            target_entity_id="1", before_value="a", after_value="b",
            reason="r", actor_store_id=s.id, user_role="shift_supervisor",
        )
        approved = svc.approve_adjustment(
            request_id=r.id, approver_user_id=sup2.id,
            approver_username=sup2.username, approver_role="shift_supervisor",
            password="TestPassword1234!", approver_store_id=s.id,
        )
        # Schedule approval auto-executes after approval
        assert approved.status in ("approved", "executed")

    def test_reject_success(self, db):
        s = _store(db)
        sup1 = _user(db, s.id, "srs1", "shift_supervisor")
        sup2 = _user(db, s.id, "srs2", "shift_supervisor")
        svc = _sched_svc(db)
        r = svc.request_adjustment(
            store_id=s.id, user_id=sup1.id, username=sup1.username,
            adjustment_type="t", target_entity_type="user",
            target_entity_id="1", before_value="a", after_value="b",
            reason="r", actor_store_id=s.id, user_role="shift_supervisor",
        )
        rejected = svc.reject_adjustment(
            request_id=r.id, approver_user_id=sup2.id,
            approver_username=sup2.username, approver_role="shift_supervisor",
            reason="no", approver_store_id=s.id,
        )
        assert rejected.status == "rejected"

    def test_self_reject_forbidden(self, db):
        s = _store(db)
        sup = _user(db, s.id, "ssrf", "shift_supervisor")
        svc = _sched_svc(db)
        r = svc.request_adjustment(
            store_id=s.id, user_id=sup.id, username=sup.username,
            adjustment_type="t", target_entity_type="user",
            target_entity_id="1", before_value="a", after_value="b",
            reason="r", actor_store_id=s.id, user_role="shift_supervisor",
        )
        with pytest.raises(PermissionError):
            svc.reject_adjustment(
                request_id=r.id, approver_user_id=sup.id,
                approver_username=sup.username, approver_role="shift_supervisor",
                reason="x", approver_store_id=s.id,
            )


# ════════════════════════════════════════════════════════════
# price_override_service status + edge cases
# ════════════════════════════════════════════════════════════

class TestPriceOverrideEdges:
    def test_request_unknown_ticket(self, db):
        s = _store(db)
        u = _user(db, s.id, "porq", "front_desk_agent")
        with pytest.raises(ValueError):
            _po_svc(db).request_price_override(
                ticket_id=99999, proposed_payout=10.0, reason="r",
                user_id=u.id, username=u.username,
                user_role="front_desk_agent", actor_store_id=s.id,
            )

    def test_approve_self_forbidden(self, db):
        s = _store(db)
        sup = _user(db, s.id, "posaf", "shift_supervisor")
        t = _ticket(db, s.id, sup.id)
        svc = _po_svc(db)
        # Supervisor requests
        r = svc.request_price_override(
            ticket_id=t.id, proposed_payout=10.0, reason="r",
            user_id=sup.id, username=sup.username,
            user_role="shift_supervisor", actor_store_id=s.id,
        )
        # Supervisor tries to approve their own
        with pytest.raises(PermissionError):
            svc.approve_price_override(
                request_id=r.id, approver_user_id=sup.id,
                approver_username=sup.username, approver_role="shift_supervisor",
                password="TestPassword1234!", approver_store_id=s.id,
            )

    def test_approve_wrong_password(self, db):
        s = _store(db)
        u = _user(db, s.id, "powp_fd", "front_desk_agent")
        sup = _user(db, s.id, "powp_sup", "shift_supervisor")
        t = _ticket(db, s.id, u.id)
        svc = _po_svc(db)
        r = svc.request_price_override(
            ticket_id=t.id, proposed_payout=10.0, reason="r",
            user_id=u.id, username=u.username,
            user_role="front_desk_agent", actor_store_id=s.id,
        )
        with pytest.raises(PermissionError):
            svc.approve_price_override(
                request_id=r.id, approver_user_id=sup.id,
                approver_username=sup.username, approver_role="shift_supervisor",
                password="WrongPassword1234!", approver_store_id=s.id,
            )

    def test_full_request_approve_reject_cycle(self, db):
        s = _store(db)
        u = _user(db, s.id, "polf", "front_desk_agent")
        sup = _user(db, s.id, "polfs", "shift_supervisor")
        t = _ticket(db, s.id, u.id)
        svc = _po_svc(db)
        r = svc.request_price_override(
            ticket_id=t.id, proposed_payout=10.0, reason="r",
            user_id=u.id, username=u.username,
            user_role="front_desk_agent", actor_store_id=s.id,
        )
        approved = svc.approve_price_override(
            request_id=r.id, approver_user_id=sup.id,
            approver_username=sup.username, approver_role="shift_supervisor",
            password="TestPassword1234!", approver_store_id=s.id,
        )
        assert approved.status == "approved"

    def test_reject_then_approve_fails(self, db):
        s = _store(db)
        u = _user(db, s.id, "pora", "front_desk_agent")
        sup = _user(db, s.id, "poras", "shift_supervisor")
        t = _ticket(db, s.id, u.id)
        svc = _po_svc(db)
        r = svc.request_price_override(
            ticket_id=t.id, proposed_payout=10.0, reason="r",
            user_id=u.id, username=u.username,
            user_role="front_desk_agent", actor_store_id=s.id,
        )
        svc.reject_price_override(
            request_id=r.id, approver_user_id=sup.id,
            approver_username=sup.username, approver_role="shift_supervisor",
            reason="no", approver_store_id=s.id,
        )
        # Now approve must fail (status no longer pending)
        with pytest.raises(ValueError):
            svc.approve_price_override(
                request_id=r.id, approver_user_id=sup.id,
                approver_username=sup.username, approver_role="shift_supervisor",
                password="TestPassword1234!", approver_store_id=s.id,
            )

    def test_execute_not_approved_fails(self, db):
        s = _store(db)
        u = _user(db, s.id, "poex", "front_desk_agent")
        sup = _user(db, s.id, "poexs", "shift_supervisor")
        t = _ticket(db, s.id, u.id)
        svc = _po_svc(db)
        r = svc.request_price_override(
            ticket_id=t.id, proposed_payout=10.0, reason="r",
            user_id=u.id, username=u.username,
            user_role="front_desk_agent", actor_store_id=s.id,
        )
        # Status is pending, not approved → execute fails
        with pytest.raises(ValueError):
            svc.execute_override(
                request_id=r.id, user_id=sup.id, username=sup.username,
                user_role="shift_supervisor", actor_store_id=s.id,
            )


# ════════════════════════════════════════════════════════════
# notification_service validation
# ════════════════════════════════════════════════════════════

class TestNotificationServiceEdges:
    def _svc(self, db):
        return NotificationService(
            TicketMessageLogRepository(db),
            NotificationTemplateRepository(db),
            BuybackTicketRepository(db),
            _audit(db),
        )

    def test_log_message_blank_body(self, db):
        s = _store(db)
        u = _user(db, s.id, "fnb", "front_desk_agent")
        t = _ticket(db, s.id, u.id)
        with pytest.raises(ValueError):
            self._svc(db).log_message(
                ticket_id=t.id, user_id=u.id, username=u.username,
                message_body="", actor_store_id=s.id,
                user_role="front_desk_agent",
            )

    def test_log_message_invalid_channel(self, db):
        s = _store(db)
        u = _user(db, s.id, "fnch", "front_desk_agent")
        t = _ticket(db, s.id, u.id)
        with pytest.raises(ValueError):
            self._svc(db).log_message(
                ticket_id=t.id, user_id=u.id, username=u.username,
                message_body="hi", actor_store_id=s.id,
                user_role="front_desk_agent",
                contact_channel="not_a_channel",
            )

    def test_template_render_unknown_template(self, db):
        s = _store(db)
        u = _user(db, s.id, "ftn", "front_desk_agent")
        t = _ticket(db, s.id, u.id)
        with pytest.raises(ValueError):
            self._svc(db).log_from_template(
                ticket_id=t.id, template_code="ghost",
                store_id=s.id, user_id=u.id, username=u.username,
                context={}, actor_store_id=s.id,
                user_role="front_desk_agent",
            )

    def test_calls_only_rejects_logged_message(self, db):
        s = _store(db)
        u = _user(db, s.id, "fcr", "front_desk_agent")
        # Create ticket with calls_only preference
        t = BuybackTicketRepository(db).create(BuybackTicket(
            store_id=s.id, created_by_user_id=u.id,
            customer_name="C", clothing_category="x",
            condition_grade="A", estimated_weight_lbs=5.0,
            customer_phone_preference="calls_only",
        ))
        db.commit()
        # logged_message channel should be rejected for calls_only
        with pytest.raises(PermissionError):
            self._svc(db).log_message(
                ticket_id=t.id, user_id=u.id, username=u.username,
                message_body="hi", actor_store_id=s.id,
                user_role="front_desk_agent",
                contact_channel="logged_message",
            )

    def test_get_messages_unknown_ticket(self, db):
        s = _store(db)
        with pytest.raises(ValueError):
            self._svc(db).get_ticket_messages(
                99999, actor_store_id=s.id, user_role="front_desk_agent",
            )


# ════════════════════════════════════════════════════════════
# traceability_service edge cases
# ════════════════════════════════════════════════════════════

class TestTraceabilityEdges:
    def _svc(self, db):
        return TraceabilityService(
            BatchRepository(db), BatchGenealogyEventRepository(db),
            RecallRunRepository(db), _audit(db),
        )

    def test_recall_view_role_gate(self, db):
        s = _store(db)
        with pytest.raises(PermissionError):
            self._svc(db).get_recall_run(
                run_id=1, actor_store_id=s.id, user_role="qc_inspector",
            )

    def test_lineage_unknown_batch(self, db):
        s = _store(db)
        with pytest.raises(ValueError):
            self._svc(db).get_batch_lineage(
                batch_id=99999, actor_store_id=s.id, user_role="qc_inspector",
            )

    def test_create_batch_with_source_ticket(self, db):
        s = _store(db)
        u = _user(db, s.id, "tcb", "qc_inspector")
        t = _ticket(db, s.id, u.id)
        b = self._svc(db).create_batch(
            store_id=s.id, batch_code="LINK", source_ticket_id=t.id,
            user_id=u.id, username=u.username,
            actor_store_id=s.id, user_role="qc_inspector",
        )
        assert b.source_ticket_id == t.id

    def test_transition_batch_invalid_status(self, db):
        s = _store(db)
        u = _user(db, s.id, "tbi", "qc_inspector")
        b = BatchRepository(db).create(Batch(store_id=s.id, batch_code="BIS"))
        db.commit()
        with pytest.raises(ValueError):
            self._svc(db).transition_batch(
                batch_id=b.id, target_status="not_a_status",
                user_id=u.id, username=u.username,
                actor_store_id=s.id, user_role="qc_inspector",
            )


# ════════════════════════════════════════════════════════════
# auth_service password verification edge paths
# ════════════════════════════════════════════════════════════

class TestAuthVerifyEdges:
    def test_verify_password_for_approval_with_legacy_hash(self, db):
        import hashlib
        s = _store(db)
        salt = "lsalt"
        pw = "LegacyPass1234!"
        digest = hashlib.pbkdf2_hmac(
            "sha256", pw.encode("utf-8"), salt.encode("utf-8"), 100000,
        ).hex()
        u = UserRepository(db).create(User(
            store_id=s.id, username="legacy_u",
            password_hash=f"{salt}:{digest}",
            display_name="L", role="shift_supervisor",
        ))
        db.commit()
        auth = _auth(db)
        assert auth.verify_password_for_approval(u.id, pw) is True
        assert auth.verify_password_for_approval(u.id, "WrongPassword1234!") is False

    def test_logout_revokes_session(self, db):
        s = _store(db)
        u = _user(db, s.id, "lo")
        auth = _auth(db)
        result = auth.authenticate("lo", "TestPassword1234!")
        sess = result["session"]
        auth.logout(sess.id, u.id, u.username)
        # Session should now be revoked
        assert UserSessionRepository(db).get_by_id(sess.id).revoked_at is not None
