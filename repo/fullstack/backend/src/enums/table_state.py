import enum


class TableState(str, enum.Enum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"
    PRE_CHECKOUT = "pre_checkout"
    CLEARED = "cleared"
