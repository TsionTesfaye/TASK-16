import enum


class BatchGenealogyEventType(str, enum.Enum):
    PROCURED = "procured"
    RECEIVED = "received"
    INSPECTED = "inspected"
    QUARANTINED = "quarantined"
    DISPOSITIONED = "dispositioned"
    ISSUED = "issued"
    TRANSFORMED = "transformed"
    FINISHED_GOODS = "finished_goods"
    RECALLED = "recalled"
