"""Tests for all repository CRUD operations against an in-memory SQLite database."""
import json

from src.repositories import (
    StoreRepository,
    UserRepository,
    UserSessionRepository,
    BuybackTicketRepository,
    PricingRuleRepository,
    PricingCalculationSnapshotRepository,
    VarianceApprovalRequestRepository,
    QCInspectionRepository,
    QuarantineRecordRepository,
    BatchRepository,
    BatchGenealogyEventRepository,
    RecallRunRepository,
    ServiceTableRepository,
    TableSessionRepository,
    TableActivityEventRepository,
    NotificationTemplateRepository,
    TicketMessageLogRepository,
    ClubOrganizationRepository,
    MemberRepository,
    MemberHistoryEventRepository,
    ExportRequestRepository,
    AuditLogRepository,
    SettingsRepository,
)
from src.models import (
    Store, User, UserSession, BuybackTicket, PricingRule,
    PricingCalculationSnapshot, VarianceApprovalRequest,
    QCInspection, QuarantineRecord, Batch, BatchGenealogyEvent,
    RecallRun, ServiceTable, TableSession, TableActivityEvent,
    NotificationTemplate, TicketMessageLog, ClubOrganization,
    Member, MemberHistoryEvent, ExportRequest, AuditLog, Settings,
)


def _create_store(conn):
    repo = StoreRepository(conn)
    store = Store(code="S001", name="Test Store")
    return repo.create(store)


def _create_user(conn, store_id=None, role="front_desk_agent", username="agent1"):
    repo = UserRepository(conn)
    user = User(
        store_id=store_id, username=username,
        password_hash="hashed", display_name="Test User", role=role,
    )
    return repo.create(user)


def _create_batch(conn, store_id):
    repo = BatchRepository(conn)
    batch = Batch(store_id=store_id, batch_code="B001")
    return repo.create(batch)


def _create_ticket(conn, store_id, user_id):
    repo = BuybackTicketRepository(conn)
    ticket = BuybackTicket(
        store_id=store_id, created_by_user_id=user_id,
        customer_name="Jane Doe", clothing_category="shirts",
        condition_grade="A", estimated_weight_lbs=25.0,
        estimated_base_rate=1.50, estimated_bonus_pct=10.0,
        estimated_payout=41.25, estimated_cap_applied=False,
    )
    return repo.create(ticket)


# --- Store ---

class TestStoreRepository:
    def test_create_and_get(self, db_conn):
        repo = StoreRepository(db_conn)
        store = Store(code="S001", name="Main Store", route_code="R1")
        created = repo.create(store)
        db_conn.commit()

        assert created.id is not None
        assert created.created_at is not None

        fetched = repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.code == "S001"
        assert fetched.name == "Main Store"
        assert fetched.route_code == "R1"
        assert fetched.is_active is True

    def test_get_by_code(self, db_conn):
        repo = StoreRepository(db_conn)
        repo.create(Store(code="S002", name="Branch"))
        db_conn.commit()
        fetched = repo.get_by_code("S002")
        assert fetched is not None
        assert fetched.name == "Branch"

    def test_list_all(self, db_conn):
        repo = StoreRepository(db_conn)
        repo.create(Store(code="A", name="Alpha"))
        repo.create(Store(code="B", name="Beta", is_active=False))
        db_conn.commit()

        all_stores = repo.list_all()
        assert len(all_stores) == 2

        active = repo.list_all(active_only=True)
        assert len(active) == 1

    def test_update(self, db_conn):
        repo = StoreRepository(db_conn)
        store = repo.create(Store(code="U1", name="Before"))
        db_conn.commit()

        store.name = "After"
        repo.update(store)
        db_conn.commit()

        fetched = repo.get_by_id(store.id)
        assert fetched.name == "After"

    def test_delete(self, db_conn):
        repo = StoreRepository(db_conn)
        store = repo.create(Store(code="D1", name="Delete Me"))
        db_conn.commit()
        repo.delete(store.id)
        db_conn.commit()
        assert repo.get_by_id(store.id) is None


# --- User ---

class TestUserRepository:
    def test_create_and_get(self, db_conn):
        store = _create_store(db_conn)
        repo = UserRepository(db_conn)
        user = User(
            store_id=store.id, username="jdoe",
            password_hash="hash123", display_name="John Doe",
            role="front_desk_agent",
        )
        created = repo.create(user)
        db_conn.commit()

        assert created.id is not None
        fetched = repo.get_by_id(created.id)
        assert fetched.username == "jdoe"
        assert fetched.role == "front_desk_agent"
        assert fetched.is_active is True
        assert fetched.is_frozen is False

    def test_get_by_username(self, db_conn):
        _create_user(db_conn, username="lookup_user")
        db_conn.commit()
        repo = UserRepository(db_conn)
        fetched = repo.get_by_username("lookup_user")
        assert fetched is not None

    def test_list_by_store(self, db_conn):
        store = _create_store(db_conn)
        _create_user(db_conn, store_id=store.id, username="u1")
        _create_user(db_conn, store_id=store.id, username="u2")
        db_conn.commit()

        repo = UserRepository(db_conn)
        users = repo.list_by_store(store.id)
        assert len(users) == 2

    def test_list_by_role(self, db_conn):
        _create_user(db_conn, role="administrator", username="admin1")
        db_conn.commit()
        repo = UserRepository(db_conn)
        admins = repo.list_by_role("administrator")
        assert len(admins) == 1

    def test_count_by_role(self, db_conn):
        _create_user(db_conn, role="administrator", username="admin_count")
        db_conn.commit()
        repo = UserRepository(db_conn)
        assert repo.count_by_role("administrator") >= 1


# --- UserSession ---

class TestUserSessionRepository:
    def test_create_and_get(self, db_conn):
        user = _create_user(db_conn, username="sess_user")
        repo = UserSessionRepository(db_conn)
        session = UserSession(
            user_id=user.id, session_nonce="nonce123",
            cookie_signature_version="v1", csrf_secret="secret",
            expires_at="2026-12-31T23:59:59Z",
        )
        created = repo.create(session)
        db_conn.commit()

        assert created.id is not None
        fetched = repo.get_by_id(created.id)
        assert fetched.session_nonce == "nonce123"

    def test_get_by_nonce(self, db_conn):
        user = _create_user(db_conn, username="nonce_user")
        repo = UserSessionRepository(db_conn)
        repo.create(UserSession(
            user_id=user.id, session_nonce="unique_nonce",
            cookie_signature_version="v1", csrf_secret="s",
            expires_at="2026-12-31T23:59:59Z",
        ))
        db_conn.commit()

        fetched = repo.get_by_nonce("unique_nonce")
        assert fetched is not None

    def test_revoke(self, db_conn):
        user = _create_user(db_conn, username="revoke_user")
        repo = UserSessionRepository(db_conn)
        session = repo.create(UserSession(
            user_id=user.id, session_nonce="rev_nonce",
            cookie_signature_version="v1", csrf_secret="s",
            expires_at="2026-12-31T23:59:59Z",
        ))
        db_conn.commit()

        repo.revoke(session.id)
        db_conn.commit()

        fetched = repo.get_by_id(session.id)
        assert fetched.revoked_at is not None


# --- BuybackTicket ---

class TestBuybackTicketRepository:
    def test_create_and_get(self, db_conn):
        store = _create_store(db_conn)
        user = _create_user(db_conn, store_id=store.id, username="ticket_user")
        ticket = _create_ticket(db_conn, store.id, user.id)
        db_conn.commit()

        repo = BuybackTicketRepository(db_conn)
        fetched = repo.get_by_id(ticket.id)
        assert fetched is not None
        assert fetched.customer_name == "Jane Doe"
        assert fetched.status == "intake_open"
        assert fetched.estimated_weight_lbs == 25.0

    def test_list_by_store(self, db_conn):
        store = _create_store(db_conn)
        user = _create_user(db_conn, store_id=store.id, username="list_user")
        _create_ticket(db_conn, store.id, user.id)
        _create_ticket(db_conn, store.id, user.id)
        db_conn.commit()

        repo = BuybackTicketRepository(db_conn)
        tickets = repo.list_by_store(store.id)
        assert len(tickets) == 2

    def test_update_status(self, db_conn):
        store = _create_store(db_conn)
        user = _create_user(db_conn, store_id=store.id, username="upd_user")
        ticket = _create_ticket(db_conn, store.id, user.id)
        db_conn.commit()

        repo = BuybackTicketRepository(db_conn)
        ticket.status = "awaiting_qc"
        repo.update(ticket)
        db_conn.commit()

        fetched = repo.get_by_id(ticket.id)
        assert fetched.status == "awaiting_qc"

    def test_count_by_store_and_status(self, db_conn):
        store = _create_store(db_conn)
        user = _create_user(db_conn, store_id=store.id, username="cnt_user")
        _create_ticket(db_conn, store.id, user.id)
        db_conn.commit()

        repo = BuybackTicketRepository(db_conn)
        count = repo.count_by_store_and_status(store.id, "intake_open")
        assert count == 1


# --- PricingRule ---

class TestPricingRuleRepository:
    def test_create_and_list(self, db_conn):
        store = _create_store(db_conn)
        repo = PricingRuleRepository(db_conn)
        rule = PricingRule(
            store_id=store.id, base_rate_per_lb=1.50,
            bonus_pct=10.0, max_ticket_payout=200.0,
            max_rate_per_lb=3.0, priority=1,
        )
        created = repo.create(rule)
        db_conn.commit()

        assert created.id is not None
        rules = repo.list_active_by_store(store.id)
        assert len(rules) == 1


# --- PricingCalculationSnapshot ---

class TestPricingCalculationSnapshotRepository:
    def test_create_and_get(self, db_conn):
        store = _create_store(db_conn)
        user = _create_user(db_conn, store_id=store.id, username="snap_user")
        ticket = _create_ticket(db_conn, store.id, user.id)
        db_conn.commit()

        repo = PricingCalculationSnapshotRepository(db_conn)
        snapshot = PricingCalculationSnapshot(
            ticket_id=ticket.id, calculation_type="estimated",
            base_rate_per_lb=1.5, input_weight_lbs=25.0,
            gross_amount=37.5, bonus_pct=10.0, bonus_amount=3.75,
            capped_amount=41.25,
            applied_rule_ids_json=json.dumps([1]),
        )
        created = repo.create(snapshot)
        db_conn.commit()

        assert created.id is not None
        fetched = repo.get_by_ticket_and_type(ticket.id, "estimated")
        assert fetched is not None
        assert fetched.gross_amount == 37.5


# --- VarianceApprovalRequest ---

class TestVarianceApprovalRequestRepository:
    def test_create_and_get(self, db_conn):
        store = _create_store(db_conn)
        user = _create_user(db_conn, store_id=store.id, username="var_user")
        ticket = _create_ticket(db_conn, store.id, user.id)
        db_conn.commit()

        repo = VarianceApprovalRequestRepository(db_conn)
        req = VarianceApprovalRequest(
            ticket_id=ticket.id, requested_by_user_id=user.id,
            variance_amount=8.0, variance_pct=8.0,
            threshold_amount=5.0, threshold_pct=5.0,
        )
        created = repo.create(req)
        db_conn.commit()

        assert created.id is not None
        pending = repo.get_pending_by_ticket(ticket.id)
        assert pending is not None
        assert pending.status == "pending"


# --- QCInspection ---

class TestQCInspectionRepository:
    def test_create_and_get(self, db_conn):
        store = _create_store(db_conn)
        user = _create_user(db_conn, store_id=store.id, username="qc_user", role="qc_inspector")
        ticket = _create_ticket(db_conn, store.id, user.id)
        db_conn.commit()

        repo = QCInspectionRepository(db_conn)
        inspection = QCInspection(
            ticket_id=ticket.id, inspector_user_id=user.id,
            actual_weight_lbs=24.5, lot_size=30, sample_size=3,
            inspection_outcome="pass",
        )
        created = repo.create(inspection)
        db_conn.commit()

        assert created.id is not None
        fetched = repo.get_by_ticket(ticket.id)
        assert fetched.actual_weight_lbs == 24.5

    def test_count_nonconformances(self, db_conn):
        store = _create_store(db_conn)
        user = _create_user(db_conn, store_id=store.id, username="nc_user", role="qc_inspector")
        ticket = _create_ticket(db_conn, store.id, user.id)
        db_conn.commit()

        repo = QCInspectionRepository(db_conn)
        repo.create(QCInspection(
            ticket_id=ticket.id, inspector_user_id=user.id,
            actual_weight_lbs=10.0, lot_size=10, sample_size=3,
            nonconformance_count=2, inspection_outcome="fail",
        ))
        db_conn.commit()

        fetched = repo.get_by_ticket(ticket.id)
        assert fetched.nonconformance_count == 2


# --- QuarantineRecord ---

class TestQuarantineRecordRepository:
    def test_create_and_list(self, db_conn):
        store = _create_store(db_conn)
        user = _create_user(db_conn, store_id=store.id, username="qr_user")
        ticket = _create_ticket(db_conn, store.id, user.id)
        batch = _create_batch(db_conn, store.id)
        db_conn.commit()

        repo = QuarantineRecordRepository(db_conn)
        record = QuarantineRecord(
            ticket_id=ticket.id, batch_id=batch.id,
            created_by_user_id=user.id,
            disposition="return_to_customer",
            due_back_to_customer_at="2026-04-17T00:00:00Z",
        )
        created = repo.create(record)
        db_conn.commit()

        assert created.id is not None
        unresolved = repo.list_unresolved()
        assert len(unresolved) == 1


# --- Batch ---

class TestBatchRepository:
    def test_create_and_get(self, db_conn):
        store = _create_store(db_conn)
        batch = _create_batch(db_conn, store.id)
        db_conn.commit()

        repo = BatchRepository(db_conn)
        fetched = repo.get_by_id(batch.id)
        assert fetched.batch_code == "B001"
        assert fetched.status == "procured"

    def test_get_by_batch_code(self, db_conn):
        store = _create_store(db_conn)
        _create_batch(db_conn, store.id)
        db_conn.commit()

        repo = BatchRepository(db_conn)
        fetched = repo.get_by_batch_code("B001")
        assert fetched is not None


# --- BatchGenealogyEvent ---

class TestBatchGenealogyEventRepository:
    def test_create_and_list(self, db_conn):
        store = _create_store(db_conn)
        user = _create_user(db_conn, store_id=store.id, username="gen_user")
        batch = _create_batch(db_conn, store.id)
        db_conn.commit()

        repo = BatchGenealogyEventRepository(db_conn)
        event = BatchGenealogyEvent(
            batch_id=batch.id, event_type="procured",
            actor_user_id=user.id, location_context="Warehouse A",
        )
        created = repo.create(event)
        db_conn.commit()

        assert created.id is not None
        events = repo.list_by_batch(batch.id)
        assert len(events) == 1


# --- RecallRun ---

class TestRecallRunRepository:
    def test_create_and_get(self, db_conn):
        store = _create_store(db_conn)
        user = _create_user(db_conn, store_id=store.id, username="recall_user")
        db_conn.commit()

        repo = RecallRunRepository(db_conn)
        run = RecallRun(
            store_id=store.id, requested_by_user_id=user.id,
            result_count=5,
        )
        created = repo.create(run)
        db_conn.commit()

        assert created.id is not None
        fetched = repo.get_by_id(created.id)
        assert fetched.result_count == 5


# --- ServiceTable ---

class TestServiceTableRepository:
    def test_create_and_list(self, db_conn):
        store = _create_store(db_conn)
        repo = ServiceTableRepository(db_conn)
        table = ServiceTable(
            store_id=store.id, table_code="T1", area_type="intake_table",
        )
        created = repo.create(table)
        db_conn.commit()

        assert created.id is not None
        tables = repo.list_by_store(store.id)
        assert len(tables) == 1

    def test_list_by_area_type(self, db_conn):
        store = _create_store(db_conn)
        repo = ServiceTableRepository(db_conn)
        repo.create(ServiceTable(store_id=store.id, table_code="T1", area_type="intake_table"))
        repo.create(ServiceTable(store_id=store.id, table_code="R1", area_type="private_room"))
        db_conn.commit()

        tables = repo.list_by_area_type(store.id, "private_room")
        assert len(tables) == 1
        assert tables[0].area_type == "private_room"


# --- TableSession ---

class TestTableSessionRepository:
    def test_create_and_get_active(self, db_conn):
        store = _create_store(db_conn)
        user = _create_user(db_conn, store_id=store.id, username="host1", role="host")
        table_repo = ServiceTableRepository(db_conn)
        table = table_repo.create(ServiceTable(
            store_id=store.id, table_code="T1", area_type="intake_table",
        ))
        db_conn.commit()

        repo = TableSessionRepository(db_conn)
        session = TableSession(
            store_id=store.id, table_id=table.id,
            opened_by_user_id=user.id, current_state="occupied",
        )
        created = repo.create(session)
        db_conn.commit()

        active = repo.get_active_by_table(table.id)
        assert active is not None
        assert active.current_state == "occupied"


# --- TableActivityEvent ---

class TestTableActivityEventRepository:
    def test_create_and_list(self, db_conn):
        store = _create_store(db_conn)
        user = _create_user(db_conn, store_id=store.id, username="evt_user", role="host")
        table_repo = ServiceTableRepository(db_conn)
        table = table_repo.create(ServiceTable(
            store_id=store.id, table_code="T1", area_type="intake_table",
        ))
        session_repo = TableSessionRepository(db_conn)
        session = session_repo.create(TableSession(
            store_id=store.id, table_id=table.id,
            opened_by_user_id=user.id,
        ))
        db_conn.commit()

        repo = TableActivityEventRepository(db_conn)
        event = TableActivityEvent(
            table_session_id=session.id, actor_user_id=user.id,
            event_type="opened", after_state="occupied",
        )
        created = repo.create(event)
        db_conn.commit()

        events = repo.list_by_session(session.id)
        assert len(events) == 1


# --- NotificationTemplate ---

class TestNotificationTemplateRepository:
    def test_create_and_get_by_code(self, db_conn):
        repo = NotificationTemplateRepository(db_conn)
        # Use a unique template_code to avoid colliding with the seeded
        # "accepted" template from migration 004.
        template = NotificationTemplate(
            template_code="test_custom", name="Test Custom",
            body="Your items have been accepted.", event_type="test_custom",
        )
        created = repo.create(template)
        db_conn.commit()

        fetched = repo.get_by_code("test_custom")
        assert fetched is not None
        assert fetched.body == "Your items have been accepted."


# --- TicketMessageLog ---

class TestTicketMessageLogRepository:
    def test_create_and_list(self, db_conn):
        store = _create_store(db_conn)
        user = _create_user(db_conn, store_id=store.id, username="msg_user")
        ticket = _create_ticket(db_conn, store.id, user.id)
        db_conn.commit()

        repo = TicketMessageLogRepository(db_conn)
        log = TicketMessageLog(
            ticket_id=ticket.id, actor_user_id=user.id,
            message_body="Hello customer", contact_channel="logged_message",
            call_attempt_status="not_applicable",
        )
        created = repo.create(log)
        db_conn.commit()

        logs = repo.list_by_ticket(ticket.id)
        assert len(logs) == 1

    def test_pending_retries(self, db_conn):
        store = _create_store(db_conn)
        user = _create_user(db_conn, store_id=store.id, username="retry_user")
        ticket = _create_ticket(db_conn, store.id, user.id)
        db_conn.commit()

        repo = TicketMessageLogRepository(db_conn)
        repo.create(TicketMessageLog(
            ticket_id=ticket.id, actor_user_id=user.id,
            message_body="Call failed", contact_channel="phone_call",
            call_attempt_status="failed", retry_at="2026-01-01T00:00:00Z",
        ))
        db_conn.commit()

        retries = repo.list_pending_retries("2026-12-31T23:59:59Z")
        assert len(retries) == 1


# --- ClubOrganization ---

class TestClubOrganizationRepository:
    def test_create_and_list(self, db_conn):
        repo = ClubOrganizationRepository(db_conn)
        org = ClubOrganization(name="Green Club", department="Recycling")
        created = repo.create(org)
        db_conn.commit()

        assert created.id is not None
        orgs = repo.list_all()
        assert len(orgs) == 1


# --- Member ---

class TestMemberRepository:
    def test_create_and_list(self, db_conn):
        org_repo = ClubOrganizationRepository(db_conn)
        org = org_repo.create(ClubOrganization(name="Test Club"))
        db_conn.commit()

        repo = MemberRepository(db_conn)
        member = Member(
            club_organization_id=org.id, full_name="Alice Smith",
            status="active",
        )
        created = repo.create(member)
        db_conn.commit()

        assert created.id is not None
        members = repo.list_by_organization(org.id)
        assert len(members) == 1

    def test_list_by_status(self, db_conn):
        org_repo = ClubOrganizationRepository(db_conn)
        org = org_repo.create(ClubOrganization(name="Status Club"))
        db_conn.commit()

        repo = MemberRepository(db_conn)
        repo.create(Member(club_organization_id=org.id, full_name="A", status="active"))
        repo.create(Member(club_organization_id=org.id, full_name="B", status="left"))
        db_conn.commit()

        active = repo.list_all(status="active")
        assert len(active) >= 1


# --- MemberHistoryEvent ---

class TestMemberHistoryEventRepository:
    def test_create_and_list(self, db_conn):
        org_repo = ClubOrganizationRepository(db_conn)
        org = org_repo.create(ClubOrganization(name="Hist Club"))
        user = _create_user(db_conn, username="hist_user")
        member_repo = MemberRepository(db_conn)
        member = member_repo.create(Member(
            club_organization_id=org.id, full_name="Bob",
        ))
        db_conn.commit()

        repo = MemberHistoryEventRepository(db_conn)
        event = MemberHistoryEvent(
            member_id=member.id, actor_user_id=user.id,
            event_type="joined", after_json='{"status":"active"}',
        )
        created = repo.create(event)
        db_conn.commit()

        events = repo.list_by_member(member.id)
        assert len(events) == 1


# --- ExportRequest ---

class TestExportRequestRepository:
    def test_create_and_list(self, db_conn):
        store = _create_store(db_conn)
        user = _create_user(db_conn, store_id=store.id, username="exp_user")
        db_conn.commit()

        repo = ExportRequestRepository(db_conn)
        req = ExportRequest(
            store_id=store.id,
            requested_by_user_id=user.id, export_type="members",
            filter_json='{"status":"active"}',
        )
        created = repo.create(req)
        db_conn.commit()

        assert created.id is not None
        assert created.store_id == store.id
        pending = repo.list_by_status("pending")
        assert len(pending) == 1
        by_store = repo.list_by_store(store.id)
        assert len(by_store) == 1


# --- AuditLog ---

class TestAuditLogRepository:
    def test_create_and_get(self, db_conn):
        user = _create_user(db_conn, username="audit_user")
        db_conn.commit()

        repo = AuditLogRepository(db_conn)
        log = AuditLog(
            actor_user_id=user.id,
            actor_username_snapshot="audit_user",
            action_code="ticket.created",
            object_type="buyback_ticket", object_id="1",
            tamper_chain_hash="abc123",
        )
        created = repo.create(log)
        db_conn.commit()

        assert created.id is not None
        fetched = repo.get_by_id(created.id)
        assert fetched.action_code == "ticket.created"

    def test_list_by_object(self, db_conn):
        user = _create_user(db_conn, username="obj_user")
        db_conn.commit()

        repo = AuditLogRepository(db_conn)
        repo.create(AuditLog(
            actor_user_id=user.id, actor_username_snapshot="obj_user",
            action_code="ticket.updated", object_type="buyback_ticket",
            object_id="42", tamper_chain_hash="hash1",
        ))
        db_conn.commit()

        logs = repo.list_by_object("buyback_ticket", "42")
        assert len(logs) == 1

    def test_get_latest(self, db_conn):
        user = _create_user(db_conn, username="latest_user")
        db_conn.commit()

        repo = AuditLogRepository(db_conn)
        repo.create(AuditLog(
            actor_user_id=user.id, actor_username_snapshot="latest_user",
            action_code="first", object_type="test", object_id="1",
            tamper_chain_hash="h1",
        ))
        repo.create(AuditLog(
            actor_user_id=user.id, actor_username_snapshot="latest_user",
            action_code="second", object_type="test", object_id="2",
            tamper_chain_hash="h2",
        ))
        db_conn.commit()

        latest = repo.get_latest()
        assert latest.action_code == "second"

    def test_count(self, db_conn):
        user = _create_user(db_conn, username="count_user")
        db_conn.commit()

        repo = AuditLogRepository(db_conn)
        repo.create(AuditLog(
            actor_user_id=user.id, actor_username_snapshot="count_user",
            action_code="test", object_type="t", object_id="1",
            tamper_chain_hash="h",
        ))
        db_conn.commit()

        assert repo.count() >= 1


# --- Settings ---

class TestSettingsRepository:
    def test_create_global_and_get(self, db_conn):
        repo = SettingsRepository(db_conn)
        settings = Settings()
        created = repo.create(settings)
        db_conn.commit()

        assert created.id is not None
        global_settings = repo.get_global()
        assert global_settings is not None
        assert global_settings.variance_pct_threshold == 5.0
        assert global_settings.max_ticket_payout == 200.0
        assert global_settings.qc_sample_min_items == 3

    def test_store_override(self, db_conn):
        store = _create_store(db_conn)
        repo = SettingsRepository(db_conn)
        repo.create(Settings())
        repo.create(Settings(store_id=store.id, max_ticket_payout=150.0))
        db_conn.commit()

        effective = repo.get_effective(store.id)
        assert effective.max_ticket_payout == 150.0

    def test_effective_falls_back_to_global(self, db_conn):
        store = _create_store(db_conn)
        repo = SettingsRepository(db_conn)
        repo.create(Settings())
        db_conn.commit()

        effective = repo.get_effective(store.id)
        assert effective is not None
        assert effective.store_id is None

    def test_update(self, db_conn):
        repo = SettingsRepository(db_conn)
        settings = repo.create(Settings())
        db_conn.commit()

        settings.max_ticket_payout = 300.0
        repo.update(settings)
        db_conn.commit()

        fetched = repo.get_by_id(settings.id)
        assert fetched.max_ticket_payout == 300.0
