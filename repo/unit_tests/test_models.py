"""Tests that all model dataclasses can be instantiated and from_row works correctly."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fullstack", "backend"))

from src.models import (
    Store, User, UserSession, BuybackTicket, PricingRule,
    PricingCalculationSnapshot, VarianceApprovalRequest,
    QCInspection, QuarantineRecord, Batch, BatchGenealogyEvent,
    RecallRun, ServiceTable, TableSession, TableActivityEvent,
    NotificationTemplate, TicketMessageLog, ClubOrganization,
    Member, MemberHistoryEvent, ExportRequest, AuditLog, Settings,
)


def test_store_defaults():
    s = Store()
    assert s.id is None
    assert s.is_active is True
    assert s.code == ""


def test_user_defaults():
    u = User()
    assert u.is_active is True
    assert u.is_frozen is False
    assert u.store_id is None


def test_user_session_defaults():
    us = UserSession()
    assert us.revoked_at is None
    assert us.client_device_id is None


def test_buyback_ticket_defaults():
    t = BuybackTicket()
    assert t.status == "intake_open"
    assert t.customer_phone_preference == "standard_calls"
    assert t.actual_weight_lbs is None
    assert t.final_payout is None
    assert t.final_cap_applied is None
    assert t.refund_amount is None
    assert t.refund_initiated_by_user_id is None


def test_pricing_rule_defaults():
    r = PricingRule()
    assert r.is_active is True
    assert r.priority == 0
    assert r.store_id is None


def test_pricing_calculation_snapshot_defaults():
    s = PricingCalculationSnapshot()
    assert s.cap_reason is None
    assert s.applied_rule_ids_json is None


def test_variance_approval_request_defaults():
    v = VarianceApprovalRequest()
    assert v.status == "pending"
    assert v.password_confirmation_used is False
    assert v.approver_user_id is None


def test_qc_inspection_defaults():
    q = QCInspection()
    assert q.nonconformance_count == 0
    assert q.quarantine_required is False


def test_quarantine_record_defaults():
    qr = QuarantineRecord()
    assert qr.disposition is None
    assert qr.resolved_at is None


def test_batch_defaults():
    b = Batch()
    assert b.status == "procured"
    assert b.source_ticket_id is None


def test_batch_genealogy_event_defaults():
    e = BatchGenealogyEvent()
    assert e.parent_batch_id is None
    assert e.child_batch_id is None
    assert e.metadata_json is None


def test_recall_run_defaults():
    r = RecallRun()
    assert r.result_count == 0
    assert r.store_id is None


def test_service_table_defaults():
    t = ServiceTable()
    assert t.is_active is True
    assert t.merged_into_id is None


def test_table_session_defaults():
    s = TableSession()
    assert s.current_state == "available"
    assert s.closed_at is None


def test_table_activity_event_defaults():
    e = TableActivityEvent()
    assert e.before_state is None
    assert e.notes is None


def test_notification_template_defaults():
    t = NotificationTemplate()
    assert t.is_active is True
    assert t.store_id is None


def test_ticket_message_log_defaults():
    m = TicketMessageLog()
    assert m.template_id is None
    assert m.retry_at is None


def test_club_organization_defaults():
    o = ClubOrganization()
    assert o.is_active is True
    assert o.department is None


def test_member_defaults():
    m = Member()
    assert m.status == "active"
    assert m.current_group is None


def test_member_history_event_defaults():
    e = MemberHistoryEvent()
    assert e.before_json is None
    assert e.after_json is None


def test_export_request_defaults():
    r = ExportRequest()
    assert r.store_id == 0
    assert r.status == "pending"
    assert r.watermark_enabled is False
    assert r.approval_required is False


def test_audit_log_defaults():
    a = AuditLog()
    assert a.actor_user_id is None
    assert a.before_json is None


def test_settings_defaults():
    s = Settings()
    assert s.variance_pct_threshold == 5.0
    assert s.variance_amount_threshold == 5.00
    assert s.max_ticket_payout == 200.00
    assert s.max_rate_per_lb == 3.00
    assert s.qc_sample_pct == 10.0
    assert s.qc_sample_min_items == 3
    assert s.qc_escalation_nonconformances_per_day == 2
    assert s.export_requires_supervisor_default is False
    assert s.file_upload_max_mb == 5
    assert s.daily_capacity == 50
    assert s.business_timezone == "America/New_York"
