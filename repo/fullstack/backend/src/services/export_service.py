"""Export service — approval gating, watermarking, and report generation.

Handles export requests with optional supervisor approval, CSV watermarking
with user attribution, and core reporting metrics (order volume, revenue,
refund rate, load factor).
"""
import csv
import io
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import List, Optional

from ..enums.export_request_status import ExportRequestStatus
from ..enums.ticket_status import TicketStatus
from ..enums.user_role import UserRole
from ..models.export_request import ExportRequest
from ..repositories.buyback_ticket_repository import BuybackTicketRepository
from ..repositories.export_request_repository import ExportRequestRepository
from ..repositories.settings_repository import SettingsRepository
from ..repositories.store_repository import StoreRepository
from ._authz import enforce_store_access
from ._tx import atomic
from .audit_service import AuditService
from .auth_service import AuthService

logger = logging.getLogger(__name__)

# Where completed export files are written. Mounted as a docker volume
# in the canonical runtime (see docker-compose.yml).
EXPORT_OUTPUT_DIR = os.environ.get("EXPORT_OUTPUT_DIR", "/storage/exports")

# Ticket columns written to tickets-type exports. Sensitive fields
# (phone ciphertext/iv, customer_phone_last4) are intentionally omitted
# — exports are operator-facing artifacts and must not re-leak data
# already masked in the API layer.
TICKET_EXPORT_COLUMNS = [
    "id", "store_id", "created_by_user_id", "customer_name",
    "clothing_category", "condition_grade",
    "estimated_weight_lbs", "actual_weight_lbs",
    "estimated_payout", "final_payout",
    "variance_amount", "variance_pct",
    "status", "refund_amount", "refunded_at",
    "completed_at", "created_at", "updated_at",
]

_SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe_filename(s: str) -> str:
    """Replace unsafe characters so a value can be used in a file path."""
    return _SAFE_FILENAME_RE.sub("_", s) or "export"


class ExportService:
    def __init__(
        self,
        export_repo: ExportRequestRepository,
        ticket_repo: BuybackTicketRepository,
        settings_repo: SettingsRepository,
        audit_service: AuditService,
        auth_service: AuthService,
        store_repo: StoreRepository = None,
    ):
        if auth_service is None:
            raise ValueError("auth_service is required — approvals must verify passwords")
        self.export_repo = export_repo
        self.ticket_repo = ticket_repo
        self.settings_repo = settings_repo
        self.audit_service = audit_service
        self.auth_service = auth_service
        self.store_repo = store_repo

    def _verify_approver_password(self, user_id: int, password: Optional[str]) -> None:
        if not password:
            raise ValueError("Password is required for approval")
        if not self.auth_service.verify_password_for_approval(user_id, password):
            raise PermissionError("Invalid password")

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def create_export_request(
        self,
        store_id: int,
        user_id: int,
        username: str,
        user_role: str,
        export_type: str,
        actor_store_id: Optional[int] = None,
        filter_json: Optional[str] = None,
        watermark_enabled: bool = False,
        attribution_text: Optional[str] = None,
    ) -> ExportRequest:
        if user_role not in (
            UserRole.OPERATIONS_MANAGER, UserRole.ADMINISTRATOR,
            UserRole.SHIFT_SUPERVISOR,
        ):
            raise PermissionError("Insufficient role for exports")

        enforce_store_access(
            entity_store_id=store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role,
            entity_name="export_request",
        )

        if not export_type or not export_type.strip():
            raise ValueError("Export type is required")

        settings = self.settings_repo.get_effective(store_id)
        approval_required = settings.export_requires_supervisor_default if settings else False

        with atomic(self.export_repo.conn):
            request = ExportRequest(
                store_id=store_id,
                requested_by_user_id=user_id,
                export_type=export_type.strip(),
                filter_json=filter_json,
                watermark_enabled=watermark_enabled,
                attribution_text=attribution_text or username,
                approval_required=approval_required,
                status=ExportRequestStatus.PENDING if approval_required else ExportRequestStatus.APPROVED,
            )
            request = self.export_repo.create(request)

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="export.requested",
                object_type="export_request",
                object_id=str(request.id),
                after={
                    "export_type": export_type,
                    "approval_required": approval_required,
                    "status": request.status,
                },
            )

        return request

    def approve_export(
        self,
        request_id: int,
        approver_user_id: int,
        approver_username: str,
        approver_role: str,
        password: str,
        approver_store_id: Optional[int] = None,
    ) -> ExportRequest:
        if approver_role not in (
            UserRole.SHIFT_SUPERVISOR, UserRole.OPERATIONS_MANAGER,
            UserRole.ADMINISTRATOR,
        ):
            raise PermissionError("Insufficient role for export approval")

        request = self.export_repo.get_by_id(request_id)
        if not request:
            raise ValueError("Export request not found")
        enforce_store_access(
            entity_store_id=request.store_id,
            actor_store_id=approver_store_id,
            actor_role=approver_role,
            entity_name="export_request",
        )
        if request.status != ExportRequestStatus.PENDING:
            raise ValueError(f"Export request is not pending, status: {request.status}")
        if request.requested_by_user_id == approver_user_id:
            raise PermissionError("Self-approval of exports is forbidden")

        self._verify_approver_password(approver_user_id, password)

        with atomic(self.export_repo.conn):
            # Atomic conditional approval — prevents races and duplicate approvals.
            if not self.export_repo.try_approve(request_id, approver_user_id):
                raise ValueError(
                    "Export request was already processed (concurrent or duplicate request)"
                )
            request = self.export_repo.get_by_id(request_id)

            self.audit_service.log(
                actor_user_id=approver_user_id,
                actor_username=approver_username,
                action_code="export.approved",
                object_type="export_request",
                object_id=str(request.id),
                after={"approver": approver_username},
            )

        logger.info("Export approved: request=%d approver=%s", request.id, approver_username)
        return request

    def reject_export(
        self,
        request_id: int,
        approver_user_id: int,
        approver_username: str,
        approver_role: str,
        reason: str,
        approver_store_id: Optional[int] = None,
    ) -> ExportRequest:
        if approver_role not in (
            UserRole.SHIFT_SUPERVISOR, UserRole.OPERATIONS_MANAGER,
            UserRole.ADMINISTRATOR,
        ):
            raise PermissionError("Insufficient role to reject exports")

        request = self.export_repo.get_by_id(request_id)
        if not request:
            raise ValueError("Export request not found")
        enforce_store_access(
            entity_store_id=request.store_id,
            actor_store_id=approver_store_id,
            actor_role=approver_role,
            entity_name="export_request",
        )
        if request.status != ExportRequestStatus.PENDING:
            raise ValueError("Export request is not pending")

        with atomic(self.export_repo.conn):
            # Atomic conditional rejection
            if not self.export_repo.try_reject(request_id, approver_user_id):
                raise ValueError(
                    "Export request was already processed (concurrent or duplicate request)"
                )
            request = self.export_repo.get_by_id(request_id)

            self.audit_service.log(
                actor_user_id=approver_user_id,
                actor_username=approver_username,
                action_code="export.rejected",
                object_type="export_request",
                object_id=str(request.id),
                after={"reason": reason},
            )

        return request

    def execute_export(
        self,
        request_id: int,
        user_id: int,
        username: str,
        actor_store_id: Optional[int] = None,
        user_role: Optional[str] = None,
    ) -> ExportRequest:
        # Execution writes a customer-data file to disk and is the
        # final dual-control step. Restrict to supervisor+ roles —
        # operators below that level cannot trigger it even if they
        # somehow obtained an APPROVED request id.
        if user_role not in (
            UserRole.SHIFT_SUPERVISOR,
            UserRole.OPERATIONS_MANAGER,
            UserRole.ADMINISTRATOR,
        ):
            raise PermissionError(
                f"Role '{user_role}' is not authorized to execute exports"
            )

        request = self.export_repo.get_by_id(request_id)
        if not request:
            raise ValueError("Export request not found")
        enforce_store_access(
            entity_store_id=request.store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role or "",
            entity_name="export_request",
        )
        if request.completed_at is not None:
            raise ValueError("Export already executed (one-time only)")
        if request.status != ExportRequestStatus.APPROVED:
            raise ValueError(
                f"Export must be approved before execution, status: {request.status}"
            )

        # Render the dataset and write the file BEFORE the DB transition
        # so a write failure rolls the request back to APPROVED (the
        # atomic execute below will simply not be called). If the file
        # is written but the DB update later fails, the atomic() wrapper
        # rolls back the DB state; the orphan file on disk is harmless
        # because `output_path` is never persisted and the export stays
        # marked APPROVED for a retry.
        csv_text = self._render_csv(request, username)
        output_path = self._write_export_file(request, csv_text)
        row_count = csv_text.count("\n") - self._watermark_line_count(request, username) - 1  # minus header
        if row_count < 0:
            row_count = 0

        now = self._now_utc()
        with atomic(self.export_repo.conn):
            # Atomic one-time execution guard. The conditional UPDATE ensures
            # that exactly one caller succeeds even under a duplicate-click race.
            if not self.export_repo.try_execute(request_id, now):
                raise ValueError(
                    "Export was already executed (concurrent or duplicate request)"
                )
            request = self.export_repo.get_by_id(request_id)

            # Persist the file path now that the transition succeeded.
            request.output_path = output_path
            self.export_repo.update(request)

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="export.executed",
                object_type="export_request",
                object_id=str(request.id),
                after={
                    "completed_at": request.completed_at,
                    "output_path": output_path,
                    "row_count": row_count,
                },
            )

        logger.info(
            "Export executed: request=%d by=%s path=%s rows=%d",
            request.id, username, output_path, row_count,
        )
        return request

    # -- Real CSV rendering --

    def _render_csv(self, request: ExportRequest, username: str) -> str:
        """Build the exported CSV body as a string.

        The first lines are watermark/attribution metadata prefixed with
        `#` so downstream tools can skip them. The subsequent lines are
        standard RFC 4180 CSV.
        """
        buf = io.StringIO()
        if request.watermark_enabled:
            buf.write(self.generate_watermark_header(request, username))
        else:
            # Even when watermarking is disabled we still stamp the
            # export with the generator + timestamp so every file on
            # disk is attributable. Audit trail requirement.
            buf.write(
                f"# GENERATED_BY: {username}\n"
                f"# TIMESTAMP: {self._now_utc()}\n"
            )

        writer = csv.writer(buf, lineterminator="\n")

        export_type = (request.export_type or "").strip().lower()
        if export_type == "tickets":
            self._write_ticket_rows(request, writer)
        elif export_type == "metrics":
            self._write_metrics_rows(request, writer)
        else:
            raise ValueError(
                f"Unsupported export_type: {request.export_type!r} "
                "(supported: 'tickets', 'metrics')"
            )

        return buf.getvalue()

    def _watermark_line_count(self, request: ExportRequest, username: str) -> int:
        if request.watermark_enabled:
            # Same number of lines produced by generate_watermark_header.
            return 5 if request.attribution_text else 4
        return 2

    def _write_ticket_rows(self, request: ExportRequest, writer) -> None:
        writer.writerow(TICKET_EXPORT_COLUMNS)
        # Filter parsing — optional `date_start` / `date_end` from filter_json.
        date_start = "1970-01-01T00:00:00Z"
        date_end = "9999-12-31T23:59:59Z"
        if request.filter_json:
            try:
                flt = json.loads(request.filter_json)
                if isinstance(flt, dict):
                    date_start = self._normalize_date_start(flt.get("date_start") or date_start)
                    date_end = self._normalize_date_end(flt.get("date_end") or date_end)
            except (ValueError, TypeError):
                pass  # Malformed filter → treat as no-op, don't block the export

        tickets = self.ticket_repo.list_by_store_and_date_range(
            request.store_id, date_start, date_end,
        )
        for t in tickets:
            writer.writerow([getattr(t, col, "") or "" for col in TICKET_EXPORT_COLUMNS])

    def _write_metrics_rows(self, request: ExportRequest, writer) -> None:
        # Default range = all-time if not provided in filter_json.
        date_start = "1970-01-01"
        date_end = "9999-12-31"
        if request.filter_json:
            try:
                flt = json.loads(request.filter_json)
                if isinstance(flt, dict):
                    date_start = self._normalize_date_start(flt.get("date_start") or date_start)
                    date_end = self._normalize_date_end(flt.get("date_end") or date_end)
            except (ValueError, TypeError):
                pass

        # Internal call — role was already verified by execute_export.
        # Pass ADMINISTRATOR to satisfy the role gate since the export
        # execution path has already been role-gated to supervisor+.
        metrics = self.compute_metrics(
            request.store_id, date_start, date_end,
            actor_store_id=request.store_id,
            user_role=UserRole.ADMINISTRATOR,
        )
        writer.writerow(["metric", "value"])
        for k, v in metrics.items():
            writer.writerow([k, v])

    def _write_export_file(self, request: ExportRequest, csv_text: str) -> str:
        """Write the rendered CSV to /storage/exports and return the path."""
        os.makedirs(EXPORT_OUTPUT_DIR, exist_ok=True)
        filename = _safe_filename(
            f"export_{request.id}_{request.export_type}_{self._now_utc()}.csv"
        )
        full_path = os.path.join(EXPORT_OUTPUT_DIR, filename)
        with open(full_path, "w", encoding="utf-8", newline="") as f:
            f.write(csv_text)
        return full_path

    def generate_watermark_header(self, request: ExportRequest, username: str) -> str:
        now = self._now_utc()
        lines = [
            f"# EXPORT_ID: {request.id}",
            f"# GENERATED_BY: {username}",
            f"# TIMESTAMP: {now}",
            "# CLASSIFICATION: CONFIDENTIAL",
        ]
        if request.attribution_text:
            lines.append(f"# ATTRIBUTION: {request.attribution_text}")
        return "\n".join(lines) + "\n"

    # -- Reporting metrics --

    @staticmethod
    def _normalize_date_start(d: str) -> str:
        """Ensure a date string includes a time portion anchored at midnight."""
        if d and "T" not in d:
            return d + "T00:00:00Z"
        return d

    @staticmethod
    def _normalize_date_end(d: str) -> str:
        """Ensure a date string includes a time portion anchored at end-of-day."""
        if d and "T" not in d:
            return d + "T23:59:59Z"
        return d

    def compute_metrics(
        self,
        store_id: int,
        date_start: str,
        date_end: str,
        actor_store_id: Optional[int] = None,
        user_role: Optional[str] = None,
        clothing_category: Optional[str] = None,
        route_code: Optional[str] = None,
    ) -> dict:
        # Reporting access: only operations managers and administrators
        # may pull aggregate metrics. Front-desk / QC / host roles are
        # not allowed to see store-wide revenue/refund data.
        if user_role not in (
            UserRole.OPERATIONS_MANAGER,
            UserRole.ADMINISTRATOR,
        ):
            raise PermissionError(
                f"Role '{user_role}' is not authorized to view metrics"
            )
        # Cross-store guard: pin non-admins to their own store.
        enforce_store_access(
            entity_store_id=store_id,
            actor_store_id=actor_store_id,
            actor_role=user_role or "",
            entity_name="metrics",
        )
        date_start = self._normalize_date_start(date_start)
        date_end = self._normalize_date_end(date_end)

        # Determine which stores to aggregate. When route_code is
        # provided and a store_repo is available, collect all stores
        # sharing that route; otherwise use the single store_id.
        store_ids = [store_id]
        if route_code and self.store_repo:
            all_stores = self.store_repo.list_all(active_only=True)
            matched = [s.id for s in all_stores if s.route_code == route_code]
            if matched:
                store_ids = matched

        tickets: List = []
        for sid in store_ids:
            tickets.extend(
                self.ticket_repo.list_by_store_and_date_range(sid, date_start, date_end)
            )

        if clothing_category:
            tickets = [
                t for t in tickets
                if t.clothing_category == clothing_category
            ]

        completed = [t for t in tickets if t.status == TicketStatus.COMPLETED]
        refunded = [t for t in tickets if t.status == TicketStatus.REFUNDED]

        order_volume = len(completed)
        revenue = sum(t.final_payout or 0 for t in completed)
        total_terminal = len(completed) + len(refunded)
        refund_rate = (len(refunded) / total_terminal * 100) if total_terminal > 0 else 0.0

        settings = self.settings_repo.get_effective(store_id)
        daily_capacity = settings.daily_capacity if settings else 50

        # Count distinct business days in range
        day_set = set()
        for t in completed:
            if t.completed_at:
                day_set.add(t.completed_at[:10])
        num_days = len(day_set) if day_set else 1
        total_capacity = daily_capacity * num_days

        load_factor = round((order_volume / total_capacity * 100), 2) if total_capacity > 0 else 0.0

        result = {
            "order_volume": order_volume,
            "revenue": round(revenue, 2),
            "refund_rate": round(refund_rate, 2),
            "refund_count": len(refunded),
            "load_factor": load_factor,
            "date_start": date_start,
            "date_end": date_end,
            "store_id": store_id,
        }
        if route_code:
            result["route_code"] = route_code
            result["stores_in_route"] = store_ids
        return result
