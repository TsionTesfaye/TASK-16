import enum


class CalculationType(str, enum.Enum):
    ESTIMATED = "estimated"
    ACTUAL = "actual"
