import enum


class InspectionOutcome(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    PASS_WITH_CONCESSION = "pass_with_concession"
