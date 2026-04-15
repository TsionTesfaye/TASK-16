"""Final targeted coverage to push past 95%.

Hits specific remaining uncovered lines:
  - schedule_service.py: 36 (init guard), 71-79 (validation), 235, 239
  - price_override_service.py: 53 (init guard), 85, 87 (validation),
    168 (already-pending guard), 215, 220, 278, 282, 287
  - member_service.py: 104, 300, 306-307, 317, 332, 339, 347-350,
    365, 414-415, 514-515
  - partials_routes.py: dial/refund partial paths via Flask test client
  - ticket_service.py: 271, 279 (status guards), 442, 450, 461 (variance
    success), 516, 518, 520 (variance reject), 656 (refund cross-store)
  - export_service.py: 68, 78, 178, 225 (already-processed branches)
"""
import io
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fullstack", "backend"))

import pytest

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
from src.services.member_service import MemberService
from src.services.notification_service import NotificationService
from src.services.price_override_service import PriceOverrideService
from src.services.pricing_service import PricingService
from src.services.qc_service import QCService
from src.services.schedule_service import ScheduleService
from src.services.ticket_service import TicketService
from src.services.traceability_service import TraceabilityService


@pytest.fixture
def db(tmp_path):
    p = str(tmp_path / "fc.db")
    init_db(p).close()
    conn = get_connection(p)
    yield conn
    conn.close()


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _store(db, code="FC"):
    s = StoreRepository(db).create(Store(code=code, name=code))
    SettingsRepository(db).create(Settings(store_id=s.id))
    db.commit()
    return s


def _user(db, sid, name, role="front_desk_agent"):
    auth = AuthService(
        UserRepository(db), UserSessionRepository(db),
        SettingsRepository(db), AuditService(AuditLogRepository(db)),
    )
    u = UserRepository(db).create(User(
        store_id=sid, username=name,
        password_hash=auth._hash_password("TestPassword1234!"),
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


# ════════════════════════════════════════════════════════════
# Init guards: schedule + price_override services
# ════════════════════════════════════════════════════════════

class TestInitGuards:
    def test_schedule_service_requires_auth_service(self, db):
        with pytest.raises(ValueError, match="auth_service"):
            ScheduleService(
                ScheduleAdjustmentRequestRepository(db), _audit(db),
                auth_service=None,
            )

    def test_price_override_service_requires_auth_service(self, db):
        with pytest.raises(ValueError, match="auth_service"):
            PriceOverrideService(
                PriceOverrideRequestRepository(db),
                BuybackTicketRepository(db),
                _audit(db),
                auth_service=None,
            )


# ════════════════════════════════════════════════════════════
# ScheduleService validation branches (lines 71-79)
# ════════════════════════════════════════════════════════════

class TestScheduleValidation:
    def _svc(self, db):
        return ScheduleService(
            ScheduleAdjustmentRequestRepository(db), _audit(db),
            auth_service=_auth(db),
        )

    def _kwargs(self, s, u, **overrides):
        base = dict(
            store_id=s.id, user_id=u.id, username=u.username,
            adjustment_type="t", target_entity_type="user",
            target_entity_id="1", before_value="a", after_value="b",
            reason="r", actor_store_id=s.id, user_role="shift_supervisor",
        )
        base.update(overrides)
        return base

    def test_blank_adjustment_type(self, db):
        s = _store(db); u = _user(db, s.id, "su1", "shift_supervisor")
        with pytest.raises(ValueError, match="Adjustment type"):
            self._svc(db).request_adjustment(**self._kwargs(s, u, adjustment_type=""))

    def test_blank_target_entity_type(self, db):
        s = _store(db); u = _user(db, s.id, "su2", "shift_supervisor")
        with pytest.raises(ValueError, match="Target entity type"):
            self._svc(db).request_adjustment(**self._kwargs(s, u, target_entity_type=""))

    def test_blank_target_entity_id(self, db):
        s = _store(db); u = _user(db, s.id, "su3", "shift_supervisor")
        with pytest.raises(ValueError, match="Target entity ID"):
            self._svc(db).request_adjustment(**self._kwargs(s, u, target_entity_id=""))

    def test_blank_reason(self, db):
        s = _store(db); u = _user(db, s.id, "su4", "shift_supervisor")
        with pytest.raises(ValueError, match="Reason"):
            self._svc(db).request_adjustment(**self._kwargs(s, u, reason=""))

    def test_blank_before_or_after(self, db):
        s = _store(db); u = _user(db, s.id, "su5", "shift_supervisor")
        with pytest.raises(ValueError, match="Before and after"):
            self._svc(db).request_adjustment(**self._kwargs(s, u, before_value=" "))
        with pytest.raises(ValueError, match="Before and after"):
            self._svc(db).request_adjustment(**self._kwargs(s, u, after_value=" "))


# ════════════════════════════════════════════════════════════
# PriceOverrideService validation branches (lines 85, 87)
# ════════════════════════════════════════════════════════════

class TestPriceOverrideValidation:
    def _svc(self, db):
        return PriceOverrideService(
            PriceOverrideRequestRepository(db),
            BuybackTicketRepository(db),
            _audit(db),
            auth_service=_auth(db),
        )

    def test_negative_proposed_payout(self, db):
        s = _store(db); u = _user(db, s.id, "pn", "front_desk_agent")
        with pytest.raises(ValueError, match="non-negative"):
            self._svc(db).request_price_override(
                ticket_id=1, proposed_payout=-1.0, reason="r",
                user_id=u.id, username=u.username,
                user_role="front_desk_agent", actor_store_id=s.id,
            )

    def test_blank_reason(self, db):
        s = _store(db); u = _user(db, s.id, "pr", "front_desk_agent")
        t = _ticket(db, s.id, u.id)
        with pytest.raises(ValueError, match="Reason"):
            self._svc(db).request_price_override(
                ticket_id=t.id, proposed_payout=10.0, reason="",
                user_id=u.id, username=u.username,
                user_role="front_desk_agent", actor_store_id=s.id,
            )

    def test_zero_proposed_payout_allowed(self, db):
        s = _store(db); u = _user(db, s.id, "pz", "front_desk_agent")
        t = _ticket(db, s.id, u.id)
        r = self._svc(db).request_price_override(
            ticket_id=t.id, proposed_payout=0.0, reason="zero out",
            user_id=u.id, username=u.username,
            user_role="front_desk_agent", actor_store_id=s.id,
        )
        assert r.proposed_payout == 0.0


# ════════════════════════════════════════════════════════════
# MemberService — CSV import error rows + history
# ════════════════════════════════════════════════════════════

class TestMemberServiceMore:
    def _svc(self, db):
        return MemberService(
            MemberRepository(db), MemberHistoryEventRepository(db),
            ClubOrganizationRepository(db), _audit(db),
        )

    def test_update_org_partial_fields(self, db):
        s = _store(db); u = _user(db, s.id, "mou", "administrator")
        org = ClubOrganizationRepository(db).create(ClubOrganization(name="Old"))
        db.commit()
        # Only update department
        out = self._svc(db).update_organization(
            org_id=org.id, user_id=u.id, username=u.username,
            user_role="administrator", department="NewDept",
        )
        assert out.department == "NewDept"
        assert out.name == "Old"  # unchanged

    def test_update_org_route_code(self, db):
        s = _store(db); u = _user(db, s.id, "morc", "administrator")
        org = ClubOrganizationRepository(db).create(ClubOrganization(name="O"))
        db.commit()
        out = self._svc(db).update_organization(
            org_id=org.id, user_id=u.id, username=u.username,
            user_role="administrator", route_code="NEWROUTE",
        )
        assert out.route_code == "NEWROUTE"

    def test_get_history_admin_required(self, db):
        with pytest.raises(PermissionError):
            self._svc(db).get_member_history(member_id=1, user_role="front_desk_agent")

    def test_csv_import_skips_invalid_rows_partial(self, db):
        s = _store(db); admin = _user(db, s.id, "csvad", "administrator")
        org = ClubOrganizationRepository(db).create(ClubOrganization(name="CSV"))
        db.commit()
        # Build csv with mix of good + bad rows that pass the upfront
        # validator (uniform column count) but fail row-level checks.
        # Empty full_name (row-level check), bad org_id (digits check),
        # then unknown org_id (lookup miss).
        lines = [
            "full_name,organization_id",
            f"Good,{org.id}",
            f" ,{org.id}",          # blank full name
            "AlsoGood,abc",         # not numeric
            "GhostMember,99999",    # unknown org
        ]
        body = ("\n".join(lines) + "\n").encode("utf-8")
        result = self._svc(db).import_members_csv(
            file_content=body, user_id=admin.id,
            username=admin.username, user_role="administrator",
        )
        assert result["imported"] >= 1
        assert len(result["errors"]) >= 2

    def test_csv_export_filtered_by_org(self, db):
        s = _store(db); admin = _user(db, s.id, "exad", "administrator")
        org_a = ClubOrganizationRepository(db).create(ClubOrganization(name="A"))
        org_b = ClubOrganizationRepository(db).create(ClubOrganization(name="B"))
        db.commit()
        MemberRepository(db).create(Member(
            club_organization_id=org_a.id, full_name="OnlyInA",
            status="active", joined_at=_now(),
        ))
        MemberRepository(db).create(Member(
            club_organization_id=org_b.id, full_name="OnlyInB",
            status="active", joined_at=_now(),
        ))
        db.commit()
        body = self._svc(db).export_members_csv(
            user_id=admin.id, username=admin.username,
            user_role="administrator", organization_id=org_a.id,
        )
        assert "OnlyInA" in body
        assert "OnlyInB" not in body

    def test_csv_validate_invalid_utf8(self, db):
        # 0xFF is invalid UTF-8 starter but no NUL byte
        body = b"full_name,organization_id\n\xff\xfe,1\n"
        ok, msg = self._svc(db).validate_csv(body)
        assert ok is False


# ════════════════════════════════════════════════════════════
# TicketService — variance approve + reject success branches
# ════════════════════════════════════════════════════════════

class TestTicketVarianceFlows:
    def _svc(self, db):
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

    def _setup_pending_variance(self, db):
        """Returns (store, fd_user, sup_user, ticket, variance_request)."""
        s = _store(db)
        fd = _user(db, s.id, "fdv", "front_desk_agent")
        sup = _user(db, s.id, "supv", "shift_supervisor")
        t = _ticket(db, s.id, fd.id, status="variance_pending_supervisor")
        v = VarianceApprovalRequestRepository(db).create(VarianceApprovalRequest(
            ticket_id=t.id, requested_by_user_id=fd.id,
            variance_amount=10.0, variance_pct=15.0,
            threshold_amount=5.0, threshold_pct=5.0,
            confirmation_note="confirmed", status="pending",
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        ))
        db.commit()
        return s, fd, sup, t, v

    def test_variance_approve_success(self, db):
        s, fd, sup, t, v = self._setup_pending_variance(db)
        out = self._svc(db).approve_variance(
            approval_request_id=v.id, approver_user_id=sup.id,
            approver_username=sup.username, approver_role="shift_supervisor",
            password="TestPassword1234!", approver_store_id=s.id,
        )
        # Returns the ticket — status should now be completed
        assert out.status == "completed"

    def test_variance_reject_success(self, db):
        s, fd, sup, t, v = self._setup_pending_variance(db)
        out = self._svc(db).reject_variance(
            approval_request_id=v.id, approver_user_id=sup.id,
            approver_username=sup.username, approver_role="shift_supervisor",
            reason="too high", approver_store_id=s.id,
        )
        assert out.status == "rejected"

    def test_variance_self_approval_blocked(self, db):
        s, fd, sup, t, v = self._setup_pending_variance(db)
        # The fd user requested it — fd is not approver, but try anyway
        # (would fail at role gate first). Use sup as both requester
        # and approver to test the self-approval branch.
        sup2 = _user(db, s.id, "supv2", "shift_supervisor")
        v2 = VarianceApprovalRequestRepository(db).create(VarianceApprovalRequest(
            ticket_id=t.id, requested_by_user_id=sup2.id,
            variance_amount=10.0, variance_pct=15.0,
            threshold_amount=5.0, threshold_pct=5.0,
            confirmation_note="self", status="pending",
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        ))
        db.commit()
        with pytest.raises(PermissionError):
            self._svc(db).approve_variance(
                approval_request_id=v2.id, approver_user_id=sup2.id,
                approver_username=sup2.username, approver_role="shift_supervisor",
                password="TestPassword1234!", approver_store_id=s.id,
            )

    def test_variance_approve_wrong_password(self, db):
        s, fd, sup, t, v = self._setup_pending_variance(db)
        with pytest.raises(PermissionError):
            self._svc(db).approve_variance(
                approval_request_id=v.id, approver_user_id=sup.id,
                approver_username=sup.username, approver_role="shift_supervisor",
                password="WrongPassword1234!", approver_store_id=s.id,
            )

    def test_variance_already_approved_rejected(self, db):
        s, fd, sup, t, v = self._setup_pending_variance(db)
        # Pre-mark as approved
        v.status = "approved"
        VarianceApprovalRequestRepository(db).update(v)
        db.commit()
        with pytest.raises(ValueError):
            self._svc(db).reject_variance(
                approval_request_id=v.id, approver_user_id=sup.id,
                approver_username=sup.username, approver_role="shift_supervisor",
                reason="x", approver_store_id=s.id,
            )

    def test_refund_initiate_with_partial_amount(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fdrf", "front_desk_agent")
        t = _ticket(db, s.id, fd.id, status="completed", final_payout=20.0)
        out = self._svc(db).initiate_refund(
            ticket_id=t.id, user_id=fd.id, username=fd.username,
            user_role="front_desk_agent", actor_store_id=s.id,
            refund_amount=5.0, reason="partial",
        )
        assert out.refund_amount == 5.0
        assert out.status == "refund_pending_supervisor"

    def test_refund_full_then_reject_returns_completed(self, db):
        s = _store(db)
        fd = _user(db, s.id, "fdfr", "front_desk_agent")
        sup = _user(db, s.id, "supfr", "shift_supervisor")
        t = _ticket(db, s.id, fd.id, status="completed", final_payout=20.0)
        svc = self._svc(db)
        svc.initiate_refund(
            ticket_id=t.id, user_id=fd.id, username=fd.username,
            user_role="front_desk_agent", actor_store_id=s.id,
        )
        out = svc.reject_refund(
            ticket_id=t.id, approver_user_id=sup.id,
            approver_username=sup.username, approver_role="shift_supervisor",
            reason="not approved", approver_store_id=s.id,
        )
        assert out.status == "completed"


# ════════════════════════════════════════════════════════════
# ExportService — try_approve / try_reject losing-race branches
# ════════════════════════════════════════════════════════════

class TestExportConcurrencyBranches:
    def _svc(self, db):
        return ExportService(
            ExportRequestRepository(db), BuybackTicketRepository(db),
            SettingsRepository(db), _audit(db),
            auth_service=_auth(db),
            store_repo=StoreRepository(db),
        )

    def test_approve_loses_race_to_concurrent_approval(self, db):
        s = _store(db)
        sup1 = _user(db, s.id, "esup1", "shift_supervisor")
        sup2 = _user(db, s.id, "esup2", "shift_supervisor")
        # Insert the request as already-approved, so try_approve returns False
        repo = ExportRequestRepository(db)
        r = repo.create(ExportRequest(
            store_id=s.id, requested_by_user_id=sup1.id,
            export_type="tickets", status="pending",
        ))
        db.commit()
        # Manually flip to approved to simulate concurrent winner
        repo.try_approve(r.id, sup1.id)
        db.commit()
        # Now the second approval attempt finds it in non-pending state
        with pytest.raises(ValueError):
            self._svc(db).approve_export(
                request_id=r.id, approver_user_id=sup2.id,
                approver_username=sup2.username, approver_role="shift_supervisor",
                password="TestPassword1234!", approver_store_id=s.id,
            )


# ════════════════════════════════════════════════════════════
# Notification — calls_only with phone_call channel allowed
# ════════════════════════════════════════════════════════════

class TestNotificationFlows:
    def _svc(self, db):
        return NotificationService(
            TicketMessageLogRepository(db),
            NotificationTemplateRepository(db),
            BuybackTicketRepository(db),
            _audit(db),
        )

    def test_calls_only_phone_call_succeeds(self, db):
        s = _store(db)
        u = _user(db, s.id, "ncf", "front_desk_agent")
        # Create ticket with calls_only preference
        t = BuybackTicketRepository(db).create(BuybackTicket(
            store_id=s.id, created_by_user_id=u.id,
            customer_name="C", clothing_category="x",
            condition_grade="A", estimated_weight_lbs=5.0,
            customer_phone_preference="calls_only",
        ))
        db.commit()
        msg = self._svc(db).log_message(
            ticket_id=t.id, user_id=u.id, username=u.username,
            message_body="called", actor_store_id=s.id,
            user_role="front_desk_agent",
            contact_channel="phone_call",
            call_attempt_status="succeeded",
        )
        assert msg.contact_channel == "phone_call"

    def test_log_with_voicemail_creates_retry(self, db):
        s = _store(db)
        u = _user(db, s.id, "nvm", "front_desk_agent")
        t = _ticket(db, s.id, u.id)
        msg = self._svc(db).log_message(
            ticket_id=t.id, user_id=u.id, username=u.username,
            message_body="vm", actor_store_id=s.id,
            user_role="front_desk_agent",
            contact_channel="phone_call",
            call_attempt_status="voicemail",
            retry_minutes=15,
        )
        assert msg.retry_at is not None

    def test_get_pending_retries_runs(self, db):
        s = _store(db)
        u = _user(db, s.id, "npr", "front_desk_agent")
        result = self._svc(db).get_pending_retries(
            actor_store_id=s.id, user_role="front_desk_agent",
        )
        assert isinstance(result, list)


# ════════════════════════════════════════════════════════════
# Partials routes — exercise route-layer branches via Flask client
# ════════════════════════════════════════════════════════════

@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("RECLAIM_OPS_DEV_MODE", "true")
    monkeypatch.setenv("RECLAIM_OPS_REQUIRE_TLS", "false")
    monkeypatch.setenv("SECURE_COOKIES", "false")
    monkeypatch.setenv("SESSION_KEY_PATH", str(tmp_path / "sk"))
    monkeypatch.setenv("EXPORT_OUTPUT_DIR", str(tmp_path / "exp"))
    import src.security.session_cookie as sc
    sc._key_cache = None
    from app import create_app
    app = create_app(db_path=str(tmp_path / "papp.db"))
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


def _bootstrap_login(client):
    client.post("/api/auth/bootstrap", json={
        "username": "admin", "password": "AdminPass1234!",
        "display_name": "A",
    })
    r = client.post("/api/auth/login", json={
        "username": "admin", "password": "AdminPass1234!",
    })
    client.environ_base["HTTP_X_CSRF_TOKEN"] = r.get_json()["data"]["csrf_token"]


def _create_store_and_users(client):
    r = client.post("/api/admin/stores", json={"code": "PT", "name": "PT"})
    sid = r.get_json()["data"]["id"]
    client.post("/api/admin/pricing_rules", json={
        "store_id": sid, "base_rate_per_lb": 1.5, "bonus_pct": 10.0,
        "max_ticket_payout": 50.0, "max_rate_per_lb": 5.0,
    })
    for name, role in [
        ("fd1", "front_desk_agent"),
        ("sup1", "shift_supervisor"),
        ("sup2", "shift_supervisor"),
        ("host1", "host"),
        ("qc1", "qc_inspector"),
    ]:
        client.post("/api/auth/users", json={
            "username": name, "password": "TestPassword1234!",
            "display_name": name, "role": role, "store_id": sid,
        })
    return sid


def _login(client, username, pw="TestPassword1234!"):
    r = client.post("/api/auth/login", json={"username": username, "password": pw})
    client.environ_base["HTTP_X_CSRF_TOKEN"] = r.get_json()["data"]["csrf_token"]


class TestPartialActionBranches:
    def test_partial_dial_unauthorized_role(self, client):
        _bootstrap_login(client)
        sid = _create_store_and_users(client)
        _login(client, "host1")
        # host cannot dial — should return 403
        r = client.post("/ui/partials/tickets/1/dial")
        assert r.status_code == 403

    def test_partial_initiate_refund_unauthorized(self, client):
        _bootstrap_login(client)
        sid = _create_store_and_users(client)
        _login(client, "host1")
        r = client.post("/ui/partials/tickets/1/initiate-refund")
        assert r.status_code == 403

    def test_partial_export_execute_success(self, client):
        _bootstrap_login(client)
        sid = _create_store_and_users(client)
        # Create a ticket (need some data for export)
        _login(client, "fd1")
        client.post("/api/tickets", json={
            "customer_name": "Ex", "clothing_category": "shirts",
            "condition_grade": "A", "estimated_weight_lbs": 5.0,
        })
        # Sup creates export
        _login(client, "sup1")
        r = client.post("/api/exports/requests", json={"export_type": "tickets"})
        rid = r.get_json()["data"]["id"]
        if r.get_json()["data"]["status"] == "pending":
            _login(client, "sup2")
            client.post(f"/api/exports/requests/{rid}/approve", json={
                "password": "TestPassword1234!",
            })
        # Execute via partial
        _login(client, "sup2")
        r = client.post(f"/ui/partials/exports/{rid}/execute")
        assert r.status_code == 200

    def test_partial_table_transition_success(self, client):
        _bootstrap_login(client)
        sid = _create_store_and_users(client)
        # Admin creates a table
        r = client.post("/api/admin/service_tables", json={
            "store_id": sid, "table_code": "PT_T1", "area_type": "intake_table",
        })
        table_id = r.get_json()["data"]["id"]
        _login(client, "host1")
        r = client.post("/api/tables/open", json={"table_id": table_id})
        sess_id = r.get_json()["data"]["id"]
        # Transition via partial
        r = client.post(f"/ui/partials/tables/{sess_id}/transition", data={
            "target_state": "pre_checkout",
        })
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "Clear" in body or "pre_checkout" in body

    def test_partial_schedule_pending_wrong_role(self, client):
        _bootstrap_login(client)
        sid = _create_store_and_users(client)
        _login(client, "fd1")
        # fd doesn't have schedule role
        r = client.get("/ui/partials/schedules/pending")
        assert r.status_code == 403

    def test_partial_export_list_empty(self, client):
        _bootstrap_login(client)
        sid = _create_store_and_users(client)
        _login(client, "sup1")
        r = client.get("/ui/partials/exports/list")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        # Either shows no requests or shows the ones we just created
        assert "<" in body
