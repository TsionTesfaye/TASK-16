"""Tests that all enums are defined with correct values matching the design."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fullstack", "backend"))

from src.enums import (
    UserRole,
    CustomerPhonePreference,
    TicketStatus,
    CalculationType,
    VarianceApprovalStatus,
    InspectionOutcome,
    QuarantineDisposition,
    BatchStatus,
    BatchGenealogyEventType,
    AreaType,
    TableState,
    TableActivityEventType,
    ContactChannel,
    CallAttemptStatus,
    MemberStatus,
    MemberHistoryEventType,
    ExportRequestStatus,
)


def test_user_role_values():
    assert UserRole.FRONT_DESK_AGENT.value == "front_desk_agent"
    assert UserRole.QC_INSPECTOR.value == "qc_inspector"
    assert UserRole.HOST.value == "host"
    assert UserRole.SHIFT_SUPERVISOR.value == "shift_supervisor"
    assert UserRole.OPERATIONS_MANAGER.value == "operations_manager"
    assert UserRole.ADMINISTRATOR.value == "administrator"
    assert len(UserRole) == 6


def test_customer_phone_preference_values():
    assert CustomerPhonePreference.CALLS_ONLY.value == "calls_only"
    assert CustomerPhonePreference.STANDARD_CALLS.value == "standard_calls"
    assert len(CustomerPhonePreference) == 2


def test_ticket_status_values():
    assert TicketStatus.INTAKE_OPEN.value == "intake_open"
    assert TicketStatus.AWAITING_QC.value == "awaiting_qc"
    assert TicketStatus.VARIANCE_PENDING_CONFIRMATION.value == "variance_pending_confirmation"
    assert TicketStatus.VARIANCE_PENDING_SUPERVISOR.value == "variance_pending_supervisor"
    assert TicketStatus.COMPLETED.value == "completed"
    assert TicketStatus.REFUND_PENDING_SUPERVISOR.value == "refund_pending_supervisor"
    assert TicketStatus.REFUNDED.value == "refunded"
    assert TicketStatus.CANCELED.value == "canceled"
    assert len(TicketStatus) == 8


def test_calculation_type_values():
    assert CalculationType.ESTIMATED.value == "estimated"
    assert CalculationType.ACTUAL.value == "actual"
    assert len(CalculationType) == 2


def test_variance_approval_status_values():
    assert VarianceApprovalStatus.PENDING.value == "pending"
    assert VarianceApprovalStatus.APPROVED.value == "approved"
    assert VarianceApprovalStatus.REJECTED.value == "rejected"
    assert VarianceApprovalStatus.EXPIRED.value == "expired"
    assert VarianceApprovalStatus.EXECUTED.value == "executed"
    assert len(VarianceApprovalStatus) == 5


def test_inspection_outcome_values():
    assert InspectionOutcome.PASS.value == "pass"
    assert InspectionOutcome.FAIL.value == "fail"
    assert InspectionOutcome.PASS_WITH_CONCESSION.value == "pass_with_concession"
    assert len(InspectionOutcome) == 3


def test_quarantine_disposition_values():
    assert QuarantineDisposition.RETURN_TO_CUSTOMER.value == "return_to_customer"
    assert QuarantineDisposition.SCRAP.value == "scrap"
    assert QuarantineDisposition.CONCESSION_ACCEPTANCE.value == "concession_acceptance"
    assert len(QuarantineDisposition) == 3


def test_batch_status_values():
    assert BatchStatus.PROCURED.value == "procured"
    assert BatchStatus.RECEIVED.value == "received"
    assert BatchStatus.QUARANTINED.value == "quarantined"
    assert BatchStatus.ISSUED.value == "issued"
    assert BatchStatus.FINISHED.value == "finished"
    assert BatchStatus.RECALLED.value == "recalled"
    assert BatchStatus.SCRAPPED.value == "scrapped"
    assert BatchStatus.RETURNED.value == "returned"
    assert len(BatchStatus) == 8


def test_batch_genealogy_event_type_values():
    assert BatchGenealogyEventType.PROCURED.value == "procured"
    assert BatchGenealogyEventType.RECEIVED.value == "received"
    assert BatchGenealogyEventType.INSPECTED.value == "inspected"
    assert BatchGenealogyEventType.QUARANTINED.value == "quarantined"
    assert BatchGenealogyEventType.DISPOSITIONED.value == "dispositioned"
    assert BatchGenealogyEventType.ISSUED.value == "issued"
    assert BatchGenealogyEventType.TRANSFORMED.value == "transformed"
    assert BatchGenealogyEventType.FINISHED_GOODS.value == "finished_goods"
    assert BatchGenealogyEventType.RECALLED.value == "recalled"
    assert len(BatchGenealogyEventType) == 9


def test_area_type_values():
    assert AreaType.INTAKE_TABLE.value == "intake_table"
    assert AreaType.PRIVATE_ROOM.value == "private_room"
    assert len(AreaType) == 2


def test_table_state_values():
    assert TableState.AVAILABLE.value == "available"
    assert TableState.OCCUPIED.value == "occupied"
    assert TableState.PRE_CHECKOUT.value == "pre_checkout"
    assert TableState.CLEARED.value == "cleared"
    assert len(TableState) == 4


def test_table_activity_event_type_values():
    assert TableActivityEventType.OPENED.value == "opened"
    assert TableActivityEventType.OCCUPIED.value == "occupied"
    assert TableActivityEventType.MERGED.value == "merged"
    assert TableActivityEventType.TRANSFERRED.value == "transferred"
    assert TableActivityEventType.PRE_CHECKOUT.value == "pre_checkout"
    assert TableActivityEventType.CLEARED.value == "cleared"
    assert TableActivityEventType.REOPENED.value == "reopened"
    assert TableActivityEventType.RELEASED.value == "released"
    assert len(TableActivityEventType) == 8


def test_contact_channel_values():
    assert ContactChannel.LOGGED_MESSAGE.value == "logged_message"
    assert ContactChannel.PHONE_CALL.value == "phone_call"
    assert len(ContactChannel) == 2


def test_call_attempt_status_values():
    assert CallAttemptStatus.NOT_APPLICABLE.value == "not_applicable"
    assert CallAttemptStatus.SUCCEEDED.value == "succeeded"
    assert CallAttemptStatus.FAILED.value == "failed"
    assert CallAttemptStatus.VOICEMAIL.value == "voicemail"
    assert CallAttemptStatus.NO_ANSWER.value == "no_answer"
    assert len(CallAttemptStatus) == 5


def test_member_status_values():
    assert MemberStatus.ACTIVE.value == "active"
    assert MemberStatus.INACTIVE.value == "inactive"
    assert MemberStatus.TRANSFERRED.value == "transferred"
    assert MemberStatus.LEFT.value == "left"
    assert len(MemberStatus) == 4


def test_member_history_event_type_values():
    assert MemberHistoryEventType.JOINED.value == "joined"
    assert MemberHistoryEventType.LEFT.value == "left"
    assert MemberHistoryEventType.TRANSFERRED.value == "transferred"
    assert MemberHistoryEventType.REACTIVATED.value == "reactivated"
    assert MemberHistoryEventType.IMPORTED.value == "imported"
    assert len(MemberHistoryEventType) == 5


def test_export_request_status_values():
    assert ExportRequestStatus.PENDING.value == "pending"
    assert ExportRequestStatus.APPROVED.value == "approved"
    assert ExportRequestStatus.REJECTED.value == "rejected"
    assert ExportRequestStatus.COMPLETED.value == "completed"
    assert ExportRequestStatus.EXPIRED.value == "expired"
    assert len(ExportRequestStatus) == 5
