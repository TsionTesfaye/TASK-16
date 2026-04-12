"""Notification center service — offline message logging and contact attempts.

Logs in-order messages per ticket, tracks call attempts with retry
scheduling, and respects customer call-only preferences.
"""
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from ..enums.call_attempt_status import CallAttemptStatus
from ..enums.contact_channel import ContactChannel
from ..enums.user_role import UserRole
from ..models.notification_template import NotificationTemplate
from ..models.ticket_message_log import TicketMessageLog
from ..repositories.buyback_ticket_repository import BuybackTicketRepository
from ..repositories.notification_template_repository import NotificationTemplateRepository
from ..repositories.ticket_message_log_repository import TicketMessageLogRepository
from ._authz import enforce_store_access
from ._tx import atomic
from .audit_service import AuditService

logger = logging.getLogger(__name__)

PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


class NotificationService:
    def __init__(
        self,
        message_repo: TicketMessageLogRepository,
        template_repo: NotificationTemplateRepository,
        ticket_repo: BuybackTicketRepository,
        audit_service: AuditService,
    ):
        self.message_repo = message_repo
        self.template_repo = template_repo
        self.ticket_repo = ticket_repo
        self.audit_service = audit_service

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _render_template(self, body: str, context: dict) -> str:
        # Defensive: reject non-dict contexts at the service boundary so
        # the route is not the only thing preventing a TypeError from
        # bubbling out of the regex substitution below.
        if not isinstance(context, dict):
            raise ValueError("context must be a dict / JSON object")
        placeholders = PLACEHOLDER_RE.findall(body)
        for ph in placeholders:
            if ph not in context:
                raise ValueError(f"Missing template placeholder: {{{ph}}}")
        return PLACEHOLDER_RE.sub(lambda m: str(context.get(m.group(1), "")), body)

    def log_message(
        self,
        ticket_id: int,
        user_id: int,
        username: str,
        message_body: str,
        actor_store_id: Optional[int] = None,
        user_role: Optional[str] = None,
        contact_channel: str = ContactChannel.LOGGED_MESSAGE,
        template_id: Optional[int] = None,
        call_attempt_status: Optional[str] = None,
        retry_minutes: Optional[int] = None,
    ) -> TicketMessageLog:
        ticket = self.ticket_repo.get_by_id(ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")
        # Notifications are implicitly scoped to the ticket's store —
        # cross-store callers cannot leak customer messaging.
        enforce_store_access(
            entity_store_id=ticket.store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role or "",
            entity_name="ticket_message_log",
        )

        if not message_body or not message_body.strip():
            raise ValueError("Message body is required")

        if contact_channel not in (ContactChannel.LOGGED_MESSAGE, ContactChannel.PHONE_CALL):
            raise ValueError(f"Invalid contact channel: {contact_channel}")

        # Customer preference enforcement: when the customer asked to
        # be reached BY PHONE ONLY, every other channel must be
        # rejected. The previous code accepted phone calls but failed
        # to reject logged_message — leaving the preference cosmetic.
        if (
            ticket.customer_phone_preference == "calls_only"
            and contact_channel != ContactChannel.PHONE_CALL
        ):
            raise PermissionError(
                "Customer preference is calls_only — non-phone channels are not allowed"
            )

        if contact_channel == ContactChannel.PHONE_CALL:
            if call_attempt_status is None:
                raise ValueError("Call attempt status required for phone calls")
        else:
            call_attempt_status = CallAttemptStatus.NOT_APPLICABLE

        retry_at = None
        if call_attempt_status in (
            CallAttemptStatus.FAILED,
            CallAttemptStatus.NO_ANSWER,
            CallAttemptStatus.VOICEMAIL,
        ):
            minutes = retry_minutes or 30
            retry_time = datetime.now(timezone.utc) + timedelta(minutes=minutes)
            retry_at = retry_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        with atomic(self.message_repo.conn):
            log = TicketMessageLog(
                ticket_id=ticket_id,
                template_id=template_id,
                actor_user_id=user_id,
                message_body=message_body.strip(),
                contact_channel=contact_channel,
                call_attempt_status=call_attempt_status,
                retry_at=retry_at,
            )
            log = self.message_repo.create(log)

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="notification.message_logged",
                object_type="ticket_message_log",
                object_id=str(log.id),
                after={
                    "ticket_id": ticket_id,
                    "channel": contact_channel,
                    "call_status": call_attempt_status,
                    "has_retry": retry_at is not None,
                },
            )

        return log

    def log_from_template(
        self,
        ticket_id: int,
        template_code: str,
        store_id: int,
        user_id: int,
        username: str,
        context: dict,
        actor_store_id: Optional[int] = None,
        user_role: Optional[str] = None,
        contact_channel: str = ContactChannel.LOGGED_MESSAGE,
        call_attempt_status: Optional[str] = None,
    ) -> TicketMessageLog:
        template = self.template_repo.get_by_code(template_code, store_id)
        if not template:
            raise ValueError(f"Template not found: {template_code}")
        if not template.is_active:
            raise ValueError(f"Template is inactive: {template_code}")

        rendered_body = self._render_template(template.body, context)

        return self.log_message(
            ticket_id=ticket_id,
            user_id=user_id,
            username=username,
            message_body=rendered_body,
            actor_store_id=actor_store_id,
            user_role=user_role,
            contact_channel=contact_channel,
            template_id=template.id,
            call_attempt_status=call_attempt_status,
        )

    def get_pending_retries(
        self,
        actor_store_id: Optional[int] = None,
        user_role: Optional[str] = None,
    ) -> list:
        """List pending retries for the actor's store.

        Administrators see all stores; every other role is pinned to
        its own `actor_store_id`.
        """
        now = self._now_utc()
        if user_role == UserRole.ADMINISTRATOR:
            return self.message_repo.list_pending_retries(now)
        if actor_store_id is None:
            raise PermissionError(
                "Cross-store access denied on ticket_message_log: no store context"
            )
        return self.message_repo.list_pending_retries_by_store(
            actor_store_id, now
        )

    def get_ticket_messages(
        self,
        ticket_id: int,
        actor_store_id: Optional[int] = None,
        user_role: Optional[str] = None,
    ) -> list:
        # Cross-store read guard — loading a ticket's message log reveals
        # customer contact history and must not leak across stores.
        ticket = self.ticket_repo.get_by_id(ticket_id)
        if not ticket:
            raise ValueError("Ticket not found")
        enforce_store_access(
            entity_store_id=ticket.store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role or "",
            entity_name="ticket_message_log",
        )
        return self.message_repo.list_by_ticket(ticket_id)
