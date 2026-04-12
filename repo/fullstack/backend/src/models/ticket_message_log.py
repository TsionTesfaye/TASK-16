from dataclasses import dataclass
from typing import Optional


@dataclass
class TicketMessageLog:
    id: Optional[int] = None
    ticket_id: int = 0
    template_id: Optional[int] = None
    actor_user_id: int = 0
    message_body: str = ""
    contact_channel: str = ""
    call_attempt_status: Optional[str] = None
    retry_at: Optional[str] = None
    created_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "TicketMessageLog":
        return TicketMessageLog(
            id=row["id"],
            ticket_id=row["ticket_id"],
            template_id=row["template_id"],
            actor_user_id=row["actor_user_id"],
            message_body=row["message_body"],
            contact_channel=row["contact_channel"],
            call_attempt_status=row["call_attempt_status"],
            retry_at=row["retry_at"],
            created_at=row["created_at"],
        )
