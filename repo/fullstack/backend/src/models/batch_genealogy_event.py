from dataclasses import dataclass
from typing import Optional


@dataclass
class BatchGenealogyEvent:
    id: Optional[int] = None
    batch_id: int = 0
    parent_batch_id: Optional[int] = None
    child_batch_id: Optional[int] = None
    event_type: str = ""
    actor_user_id: int = 0
    location_context: Optional[str] = None
    created_at: Optional[str] = None
    metadata_json: Optional[str] = None

    @staticmethod
    def from_row(row) -> "BatchGenealogyEvent":
        return BatchGenealogyEvent(
            id=row["id"],
            batch_id=row["batch_id"],
            parent_batch_id=row["parent_batch_id"],
            child_batch_id=row["child_batch_id"],
            event_type=row["event_type"],
            actor_user_id=row["actor_user_id"],
            location_context=row["location_context"],
            created_at=row["created_at"],
            metadata_json=row["metadata_json"],
        )
