"""Schedule adjustment service — dual-control approval for schedule changes.

Any manual modification to scheduled execution time, retry timing, or deadline
overrides requires dual-control approval: requester != approver, password
re-entry, single-use execution.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from ..enums.user_role import UserRole
from ..models.schedule_adjustment_request import ScheduleAdjustmentRequest
from ..repositories.schedule_adjustment_request_repository import ScheduleAdjustmentRequestRepository
from ._authz import enforce_store_access
from ._tx import atomic
from .audit_service import AuditService
from .auth_service import AuthService

logger = logging.getLogger(__name__)

SUPERVISOR_ROLES = {
    UserRole.SHIFT_SUPERVISOR,
    UserRole.OPERATIONS_MANAGER,
    UserRole.ADMINISTRATOR,
}


class ScheduleService:
    def __init__(
        self,
        schedule_repo: ScheduleAdjustmentRequestRepository,
        audit_service: AuditService,
        auth_service: AuthService,
    ):
        if auth_service is None:
            raise ValueError("auth_service is required — approvals must verify passwords")
        self.schedule_repo = schedule_repo
        self.audit_service = audit_service
        self.auth_service = auth_service

    def _verify_approver_password(self, user_id: int, password: Optional[str]) -> None:
        if not password:
            raise ValueError("Password is required for approval")
        if not self.auth_service.verify_password_for_approval(user_id, password):
            raise PermissionError("Invalid password")

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def request_adjustment(
        self,
        store_id: int,
        user_id: int,
        username: str,
        adjustment_type: str,
        target_entity_type: str,
        target_entity_id: str,
        before_value: str,
        after_value: str,
        reason: str,
        actor_store_id: Optional[int] = None,
        user_role: Optional[str] = None,
    ) -> ScheduleAdjustmentRequest:
        enforce_store_access(
            entity_store_id=store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role or "",
            entity_name="schedule_adjustment",
        )
        if not adjustment_type or not adjustment_type.strip():
            raise ValueError("Adjustment type is required")
        if not target_entity_type or not target_entity_type.strip():
            raise ValueError("Target entity type is required")
        if not target_entity_id or not str(target_entity_id).strip():
            raise ValueError("Target entity ID is required")
        if not reason or not reason.strip():
            raise ValueError("Reason is required for schedule adjustments")
        if not before_value.strip() or not after_value.strip():
            raise ValueError("Before and after values are required")

        with atomic(self.schedule_repo.conn):
            request = ScheduleAdjustmentRequest(
                store_id=store_id,
                requested_by_user_id=user_id,
                adjustment_type=adjustment_type.strip(),
                target_entity_type=target_entity_type.strip(),
                target_entity_id=str(target_entity_id).strip(),
                before_value=before_value.strip(),
                after_value=after_value.strip(),
                reason=reason.strip(),
                status="pending",
            )
            request = self.schedule_repo.create(request)

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="schedule.adjustment_requested",
                object_type="schedule_adjustment_request",
                object_id=str(request.id),
                before={"value": before_value},
                after={"value": after_value, "reason": reason},
            )

        return request

    def approve_adjustment(
        self,
        request_id: int,
        approver_user_id: int,
        approver_username: str,
        approver_role: str,
        password: str,
        approver_store_id: Optional[int] = None,
    ) -> ScheduleAdjustmentRequest:
        if approver_role not in SUPERVISOR_ROLES:
            raise PermissionError("Insufficient role for schedule adjustment approval")

        request = self.schedule_repo.get_by_id(request_id)
        if not request:
            raise ValueError("Schedule adjustment request not found")
        enforce_store_access(
            entity_store_id=request.store_id,
            actor_store_id=approver_store_id,
            actor_role=approver_role,
            entity_name="schedule_adjustment",
        )
        if request.status != "pending":
            raise ValueError(f"Request is not pending, status: {request.status}")
        if request.requested_by_user_id == approver_user_id:
            raise PermissionError("Self-approval is forbidden")

        self._verify_approver_password(approver_user_id, password)

        now = self._now_utc()
        with atomic(self.schedule_repo.conn):
            # Atomic conditional execution — prevents double approval under races.
            if not self.schedule_repo.try_execute_approval(
                request_id, approver_user_id, now,
            ):
                raise ValueError(
                    "Schedule adjustment was already processed (concurrent or duplicate request)"
                )
            request = self.schedule_repo.get_by_id(request_id)

            self.audit_service.log(
                actor_user_id=approver_user_id,
                actor_username=approver_username,
                action_code="schedule.adjustment_approved",
                object_type="schedule_adjustment_request",
                object_id=str(request.id),
                before={"value": request.before_value},
                after={"value": request.after_value, "approver": approver_username},
            )

        logger.info(
            "Schedule adjustment executed: request=%d approver=%s",
            request.id, approver_username,
        )
        return request

    def reject_adjustment(
        self,
        request_id: int,
        approver_user_id: int,
        approver_username: str,
        approver_role: str,
        reason: str,
        approver_store_id: Optional[int] = None,
    ) -> ScheduleAdjustmentRequest:
        if approver_role not in SUPERVISOR_ROLES:
            raise PermissionError("Insufficient role to reject schedule adjustments")

        request = self.schedule_repo.get_by_id(request_id)
        if not request:
            raise ValueError("Schedule adjustment request not found")
        enforce_store_access(
            entity_store_id=request.store_id,
            actor_store_id=approver_store_id,
            actor_role=approver_role,
            entity_name="schedule_adjustment",
        )
        if request.status != "pending":
            raise ValueError("Request is not pending")
        if request.requested_by_user_id == approver_user_id:
            raise PermissionError("Cannot reject own request")

        request.approver_user_id = approver_user_id
        request.status = "rejected"
        request.rejected_at = self._now_utc()

        with atomic(self.schedule_repo.conn):
            self.schedule_repo.update(request)

            self.audit_service.log(
                actor_user_id=approver_user_id,
                actor_username=approver_username,
                action_code="schedule.adjustment_rejected",
                object_type="schedule_adjustment_request",
                object_id=str(request.id),
                after={"reason": reason},
            )

        return request

    def list_pending(
        self,
        store_id: Optional[int] = None,
        actor_store_id: Optional[int] = None,
        user_role: Optional[str] = None,
    ) -> List[ScheduleAdjustmentRequest]:
        """List pending schedule-adjustment requests.

        Restricted to supervisors and above — front-desk agents, QC
        inspectors, and hosts have no business seeing pending schedule
        adjustments.

        - Administrators see all stores unless they pass an explicit
          `store_id` filter.
        - Every other supervisor role is pinned to their own
          `actor_store_id`; passing a different `store_id` is rejected.
        """
        if user_role not in SUPERVISOR_ROLES:
            raise PermissionError(
                f"Role '{user_role}' is not authorized to view pending schedule adjustments"
            )

        requests = self.schedule_repo.list_by_status("pending")
        if user_role == UserRole.ADMINISTRATOR:
            if store_id is not None:
                return [r for r in requests if r.store_id == store_id]
            return requests
        # Non-admin: force the filter to the actor's store.
        if actor_store_id is None:
            raise PermissionError(
                "Cross-store access denied on schedule_adjustment: no store context"
            )
        if store_id is not None and store_id != actor_store_id:
            raise PermissionError(
                "Cross-store access denied on schedule_adjustment"
            )
        return [r for r in requests if r.store_id == actor_store_id]
