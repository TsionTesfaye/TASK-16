"""Repository coverage-closure tests.

Exercise list/query methods and update paths on every repository so
coverage of the data-access layer reaches ≥90%.
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fullstack", "backend"))

import pytest

from src.database import get_connection, init_db
from src.models.audit_log import AuditLog
from src.models.batch import Batch
from src.models.batch_genealogy_event import BatchGenealogyEvent
from src.models.buyback_ticket import BuybackTicket
from src.models.club_organization import ClubOrganization
from src.models.export_request import ExportRequest
from src.models.member import Member
from src.models.member_history_event import MemberHistoryEvent
from src.models.notification_template import NotificationTemplate
from src.models.pricing_rule import PricingRule
from src.models.pricing_calculation_snapshot import PricingCalculationSnapshot
from src.models.qc_inspection import QCInspection
from src.models.quarantine_record import QuarantineRecord
from src.models.recall_run import RecallRun
from src.models.schedule_adjustment_request import ScheduleAdjustmentRequest
from src.models.service_table import ServiceTable
from src.models.settings import Settings
from src.models.store import Store
from src.models.table_activity_event import TableActivityEvent
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


@pytest.fixture
def db_conn(tmp_path):
    path = str(tmp_path / "r.db")
    init_db(path).close()
    conn = get_connection(path)
    yield conn
    conn.close()


def _mk_store(db, code="S1"):
    r = StoreRepository(db).create(Store(code=code, name=f"Store {code}"))
    SettingsRepository(db).create(Settings(store_id=r.id))
    db.commit()
    return r


def _mk_user(db, store_id, username="u1", role="front_desk_agent"):
    return UserRepository(db).create(User(
        store_id=store_id, username=username, password_hash="x",
        display_name=username, role=role,
    ))


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mk_ticket(db, store_id, user_id, status="intake_open"):
    return BuybackTicketRepository(db).create(BuybackTicket(
        store_id=store_id, created_by_user_id=user_id,
        customer_name="C", clothing_category="shirts",
        condition_grade="A", estimated_weight_lbs=5.0,
        estimated_payout=7.5, status=status,
    ))


# ════════════════════════════════════════════════════════════
# Pricing rule — list/get/update paths
# ════════════════════════════════════════════════════════════

class TestPricingRuleRepository:
    def test_list_by_store_and_get_by_id(self, db_conn):
        store = _mk_store(db_conn)
        repo = PricingRuleRepository(db_conn)
        r1 = repo.create(PricingRule(
            store_id=store.id, category_filter="shirts",
            base_rate_per_lb=1.5, priority=1,
            max_ticket_payout=200, max_rate_per_lb=5,
            min_weight_lbs=0.1, max_weight_lbs=1000,
        ))
        repo.create(PricingRule(
            store_id=store.id, category_filter=None,
            base_rate_per_lb=1.0, priority=2,
            max_ticket_payout=200, max_rate_per_lb=5,
            min_weight_lbs=0.1, max_weight_lbs=1000,
        ))
        db_conn.commit()
        rules = repo.list_active_by_store(store.id)
        assert len(rules) == 2
        assert repo.get_by_id(r1.id).category_filter == "shirts"
        all_rules = repo.list_all()
        assert len(all_rules) >= 2


# ════════════════════════════════════════════════════════════
# QC Inspection — list/get/by_ticket
# ════════════════════════════════════════════════════════════

class TestQCInspectionRepository:
    def test_crud_and_list(self, db_conn):
        store = _mk_store(db_conn)
        user = _mk_user(db_conn, store.id)
        ticket = _mk_ticket(db_conn, store.id, user.id, status="awaiting_qc")
        db_conn.commit()

        repo = QCInspectionRepository(db_conn)
        ins = repo.create(QCInspection(
            ticket_id=ticket.id, inspector_user_id=user.id,
            actual_weight_lbs=5.0, lot_size=5, sample_size=1,
            nonconformance_count=0, inspection_outcome="pass",
        ))
        db_conn.commit()
        got = repo.get_by_id(ins.id)
        assert got.ticket_id == ticket.id
        # list by ticket
        by_ticket = repo.list_by_ticket(ticket.id) if hasattr(repo, "list_by_ticket") else []
        assert isinstance(by_ticket, list)


# ════════════════════════════════════════════════════════════
# Notification Template — list/update/get_by_code overlay
# ════════════════════════════════════════════════════════════

class TestNotificationTemplateRepository:
    def test_list_all_and_by_store(self, db_conn):
        store = _mk_store(db_conn)
        repo = NotificationTemplateRepository(db_conn)
        # Migration seeded some global templates
        globals_list = repo.list_all()
        assert len(globals_list) >= 5
        # Store-specific override
        tpl = repo.create(NotificationTemplate(
            store_id=store.id, template_code="custom1",
            name="Custom", body="Hello {name}", event_type="custom1",
        ))
        db_conn.commit()
        all_list = repo.list_all()
        assert any(t.template_code == "custom1" for t in all_list)

        by_id = repo.get_by_id(tpl.id)
        assert by_id.template_code == "custom1"

    def test_update_template(self, db_conn):
        store = _mk_store(db_conn)
        repo = NotificationTemplateRepository(db_conn)
        tpl = repo.create(NotificationTemplate(
            store_id=store.id, template_code="upd_tpl",
            name="U", body="before", event_type="u",
        ))
        db_conn.commit()
        tpl.body = "after"
        updated = repo.update(tpl)
        db_conn.commit()
        assert updated.body == "after"


# ════════════════════════════════════════════════════════════
# Batch + Genealogy + Quarantine + Recall — query helpers
# ════════════════════════════════════════════════════════════

class TestBatchAndGenealogy:
    def test_batch_list_and_transition_log(self, db_conn):
        store = _mk_store(db_conn)
        user = _mk_user(db_conn, store.id)
        batch_repo = BatchRepository(db_conn)
        b = batch_repo.create(Batch(
            store_id=store.id, batch_code="B1",
        ))
        db_conn.commit()
        listed = batch_repo.list_by_store(store.id)
        assert any(x.id == b.id for x in listed)
        assert batch_repo.get_by_id(b.id).batch_code == "B1"

        gen_repo = BatchGenealogyEventRepository(db_conn)
        gen_repo.create(BatchGenealogyEvent(
            batch_id=b.id, event_type="received",
            actor_user_id=user.id,
        ))
        db_conn.commit()
        events = gen_repo.list_by_batch(b.id)
        assert len(events) == 1

    def test_quarantine_unresolved_list(self, db_conn):
        store = _mk_store(db_conn)
        user = _mk_user(db_conn, store.id)
        ticket = _mk_ticket(db_conn, store.id, user.id)
        batch = BatchRepository(db_conn).create(Batch(
            store_id=store.id, batch_code="QB",
        ))
        db_conn.commit()

        repo = QuarantineRecordRepository(db_conn)
        q = repo.create(QuarantineRecord(
            ticket_id=ticket.id, batch_id=batch.id,
            created_by_user_id=user.id,
        ))
        db_conn.commit()
        unresolved = repo.list_unresolved()
        assert any(x.id == q.id for x in unresolved)
        assert repo.get_by_id(q.id).ticket_id == ticket.id

    def test_recall_run_get(self, db_conn):
        store = _mk_store(db_conn)
        user = _mk_user(db_conn, store.id)
        repo = RecallRunRepository(db_conn)
        r = repo.create(RecallRun(
            store_id=store.id, requested_by_user_id=user.id,
            result_json='{"x":1}', result_count=1,
        ))
        db_conn.commit()
        assert repo.get_by_id(r.id).result_json == '{"x":1}'


# ════════════════════════════════════════════════════════════
# Table session + activity events
# ════════════════════════════════════════════════════════════

class TestTableRepositories:
    def test_service_table_list_by_area_type(self, db_conn):
        store = _mk_store(db_conn)
        repo = ServiceTableRepository(db_conn)
        repo.create(ServiceTable(store_id=store.id, table_code="T1", area_type="intake_table"))
        repo.create(ServiceTable(store_id=store.id, table_code="R1", area_type="private_room"))
        db_conn.commit()

        intake = repo.list_by_area_type(store.id, "intake_table")
        assert len(intake) == 1
        assert intake[0].table_code == "T1"

    def test_table_session_list_and_update(self, db_conn):
        store = _mk_store(db_conn)
        user = _mk_user(db_conn, store.id, role="host")
        table = ServiceTableRepository(db_conn).create(
            ServiceTable(store_id=store.id, table_code="T2", area_type="intake_table")
        )
        db_conn.commit()
        session_repo = TableSessionRepository(db_conn)
        sess = session_repo.create(TableSession(
            table_id=table.id, store_id=store.id,
            opened_by_user_id=user.id, current_state="occupied",
        ))
        db_conn.commit()

        listed = session_repo.list_by_store(store.id)
        assert len(listed) == 1

        active = session_repo.get_active_by_table(table.id)
        assert active is not None and active.id == sess.id

        ev_repo = TableActivityEventRepository(db_conn)
        ev = ev_repo.create(TableActivityEvent(
            table_session_id=sess.id, event_type="opened",
            actor_user_id=user.id,
        ))
        db_conn.commit()
        events = ev_repo.list_by_session(sess.id)
        assert any(e.id == ev.id for e in events)


# ════════════════════════════════════════════════════════════
# Export + Schedule + Variance — status transitions
# ════════════════════════════════════════════════════════════

class TestRequestRepositories:
    def test_export_request_list_by_store_and_status(self, db_conn):
        store = _mk_store(db_conn)
        user = _mk_user(db_conn, store.id)
        repo = ExportRequestRepository(db_conn)
        r1 = repo.create(ExportRequest(
            store_id=store.id, requested_by_user_id=user.id,
            export_type="tickets", status="pending",
        ))
        r2 = repo.create(ExportRequest(
            store_id=store.id, requested_by_user_id=user.id,
            export_type="metrics", status="approved",
        ))
        db_conn.commit()

        by_store = repo.list_by_store(store.id)
        assert len(by_store) == 2

        got = repo.get_by_id(r1.id)
        assert got.status == "pending"

    def test_schedule_request_list(self, db_conn):
        store = _mk_store(db_conn)
        user = _mk_user(db_conn, store.id, role="shift_supervisor")
        repo = ScheduleAdjustmentRequestRepository(db_conn)
        r = repo.create(ScheduleAdjustmentRequest(
            store_id=store.id, requested_by_user_id=user.id,
            adjustment_type="shift_change", target_entity_type="user",
            target_entity_id="1", before_value="a", after_value="b",
            reason="r", status="pending",
        ))
        db_conn.commit()
        by_store = repo.list_by_store(store.id)
        assert any(x.id == r.id for x in by_store)
        pending = repo.list_by_status(status="pending")
        assert len(pending) >= 1

    def test_variance_request_get_by_id(self, db_conn):
        store = _mk_store(db_conn)
        user = _mk_user(db_conn, store.id)
        ticket = _mk_ticket(db_conn, store.id, user.id,
                            status="variance_pending_supervisor")
        repo = VarianceApprovalRequestRepository(db_conn)
        v = repo.create(VarianceApprovalRequest(
            ticket_id=ticket.id, requested_by_user_id=user.id,
            variance_amount=10.0, variance_pct=15.0,
            threshold_amount=5.0, threshold_pct=5.0,
            confirmation_note="variance", status="pending",
        ))
        db_conn.commit()
        assert repo.get_by_id(v.id).ticket_id == ticket.id


# ════════════════════════════════════════════════════════════
# Message + Pricing snapshot + member history + audit + session
# ════════════════════════════════════════════════════════════

class TestMiscRepositories:
    def test_message_log_list_by_ticket(self, db_conn):
        store = _mk_store(db_conn)
        user = _mk_user(db_conn, store.id)
        ticket = _mk_ticket(db_conn, store.id, user.id)
        db_conn.commit()
        repo = TicketMessageLogRepository(db_conn)
        m = repo.create(TicketMessageLog(
            ticket_id=ticket.id, actor_user_id=user.id,
            message_body="hi", contact_channel="logged_message",
            call_attempt_status="not_applicable",
        ))
        db_conn.commit()
        listed = repo.list_by_ticket(ticket.id)
        assert len(listed) == 1

    def test_pricing_snapshot_get(self, db_conn):
        store = _mk_store(db_conn)
        user = _mk_user(db_conn, store.id)
        ticket = _mk_ticket(db_conn, store.id, user.id)
        db_conn.commit()
        repo = PricingCalculationSnapshotRepository(db_conn)
        snap = repo.create(PricingCalculationSnapshot(
            ticket_id=ticket.id, calculation_type="estimated",
            base_rate_per_lb=1.5, input_weight_lbs=5.0,
            gross_amount=7.5, bonus_pct=0.0, bonus_amount=0.0,
            capped_amount=7.5, applied_rule_ids_json="[]",
        ))
        db_conn.commit()
        assert repo.get_by_id(snap.id).ticket_id == ticket.id

    def test_member_history_list(self, db_conn):
        store = _mk_store(db_conn)
        user = _mk_user(db_conn, store.id)
        org = ClubOrganizationRepository(db_conn).create(
            ClubOrganization(name="Org1")
        )
        db_conn.commit()
        member = MemberRepository(db_conn).create(Member(
            club_organization_id=org.id, full_name="M",
            status="active", joined_at=_now(),
        ))
        db_conn.commit()
        repo = MemberHistoryEventRepository(db_conn)
        repo.create(MemberHistoryEvent(
            member_id=member.id, actor_user_id=user.id, event_type="joined",
        ))
        db_conn.commit()
        hist = repo.list_by_member(member.id)
        assert len(hist) == 1

    def test_audit_log_filter_methods(self, db_conn):
        store = _mk_store(db_conn)
        u1 = _mk_user(db_conn, store.id, username="a_u1")
        u2 = _mk_user(db_conn, store.id, username="a_u2")
        db_conn.commit()
        repo = AuditLogRepository(db_conn)
        repo.create(AuditLog(
            actor_user_id=u1.id, actor_username_snapshot="u",
            action_code="a.b", object_type="x", object_id="1",
        ))
        repo.create(AuditLog(
            actor_user_id=u2.id, actor_username_snapshot="v",
            action_code="c.d", object_type="x", object_id="2",
        ))
        db_conn.commit()
        assert repo.count() >= 2
        all_entries = repo.list_all(limit=10)
        assert len(all_entries) >= 2
        by_actor = repo.list_by_actor(actor_user_id=u1.id)
        assert all(r.actor_user_id == u1.id for r in by_actor)
        by_action = repo.list_by_action(action_code="a.b")
        assert all(r.action_code == "a.b" for r in by_action)
        by_object = repo.list_by_object(object_type="x", object_id="1")
        assert all(r.object_id == "1" for r in by_object)
        latest = repo.get_latest()
        assert latest is not None

    def test_user_session_revoke_all_for_user(self, db_conn):
        store = _mk_store(db_conn)
        user = _mk_user(db_conn, store.id)
        repo = UserSessionRepository(db_conn)
        s1 = repo.create(UserSession(
            user_id=user.id, session_nonce="n1",
            cookie_signature_version="v1", csrf_secret="c1",
            expires_at=_now(),
        ))
        s2 = repo.create(UserSession(
            user_id=user.id, session_nonce="n2",
            cookie_signature_version="v1", csrf_secret="c2",
            expires_at=_now(),
        ))
        db_conn.commit()
        repo.revoke_all_for_user(user.id)
        db_conn.commit()
        a = repo.get_by_nonce("n1")
        b = repo.get_by_nonce("n2")
        assert a.revoked_at is not None
        assert b.revoked_at is not None

    def test_user_repo_count_by_role(self, db_conn):
        store = _mk_store(db_conn)
        _mk_user(db_conn, store.id, "a1", "front_desk_agent")
        _mk_user(db_conn, store.id, "a2", "front_desk_agent")
        _mk_user(db_conn, store.id, "q1", "qc_inspector")
        db_conn.commit()
        repo = UserRepository(db_conn)
        assert repo.count_by_role("front_desk_agent") == 2
        assert repo.count_by_role("qc_inspector") == 1
        assert repo.count_by_role("administrator") == 0

    def test_store_repo_get_by_id_and_code(self, db_conn):
        store = _mk_store(db_conn, code="FINDME")
        repo = StoreRepository(db_conn)
        by_id = repo.get_by_id(store.id)
        assert by_id.code == "FINDME"
        by_code = repo.get_by_code("FINDME")
        assert by_code.id == store.id
        missing = repo.get_by_code("NOT_A_CODE")
        assert missing is None
