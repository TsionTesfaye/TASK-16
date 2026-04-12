import enum


class TableActivityEventType(str, enum.Enum):
    OPENED = "opened"
    OCCUPIED = "occupied"
    MERGED = "merged"
    TRANSFERRED = "transferred"
    PRE_CHECKOUT = "pre_checkout"
    CLEARED = "cleared"
    REOPENED = "reopened"
    RELEASED = "released"
