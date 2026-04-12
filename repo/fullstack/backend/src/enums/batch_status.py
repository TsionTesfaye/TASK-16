import enum


class BatchStatus(str, enum.Enum):
    PROCURED = "procured"
    RECEIVED = "received"
    QUARANTINED = "quarantined"
    ISSUED = "issued"
    FINISHED = "finished"
    RECALLED = "recalled"
    SCRAPPED = "scrapped"
    RETURNED = "returned"
