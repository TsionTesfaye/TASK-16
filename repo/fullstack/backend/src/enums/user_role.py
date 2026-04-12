import enum


class UserRole(str, enum.Enum):
    FRONT_DESK_AGENT = "front_desk_agent"
    QC_INSPECTOR = "qc_inspector"
    HOST = "host"
    SHIFT_SUPERVISOR = "shift_supervisor"
    OPERATIONS_MANAGER = "operations_manager"
    ADMINISTRATOR = "administrator"
