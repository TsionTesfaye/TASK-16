import enum


class QuarantineDisposition(str, enum.Enum):
    RETURN_TO_CUSTOMER = "return_to_customer"
    SCRAP = "scrap"
    CONCESSION_ACCEPTANCE = "concession_acceptance"
