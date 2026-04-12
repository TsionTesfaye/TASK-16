import enum


class TicketStatus(str, enum.Enum):
    INTAKE_OPEN = "intake_open"
    AWAITING_QC = "awaiting_qc"
    VARIANCE_PENDING_CONFIRMATION = "variance_pending_confirmation"
    VARIANCE_PENDING_SUPERVISOR = "variance_pending_supervisor"
    COMPLETED = "completed"
    REFUND_PENDING_SUPERVISOR = "refund_pending_supervisor"
    REFUNDED = "refunded"
    CANCELED = "canceled"
