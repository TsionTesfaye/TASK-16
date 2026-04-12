import enum


class MemberHistoryEventType(str, enum.Enum):
    JOINED = "joined"
    LEFT = "left"
    TRANSFERRED = "transferred"
    REACTIVATED = "reactivated"
    IMPORTED = "imported"
