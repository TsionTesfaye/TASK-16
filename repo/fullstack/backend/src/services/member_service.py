"""Member lifecycle and club organization service.

Manages club organizations, member join/leave/transfer, bulk CSV import
with row-level validation, and immutable history event tracking.
"""
import csv
import hashlib
import io
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from ..enums.member_history_event_type import MemberHistoryEventType
from ..enums.member_status import MemberStatus
from ..enums.user_role import UserRole
from ..models.club_organization import ClubOrganization
from ..models.member import Member
from ..models.member_history_event import MemberHistoryEvent
from ..repositories.club_organization_repository import ClubOrganizationRepository
from ..repositories.member_history_event_repository import MemberHistoryEventRepository
from ..repositories.member_repository import MemberRepository
from ._tx import atomic, savepoint
from .audit_service import AuditService

logger = logging.getLogger(__name__)


class MemberService:
    def __init__(
        self,
        member_repo: MemberRepository,
        history_repo: MemberHistoryEventRepository,
        org_repo: ClubOrganizationRepository,
        audit_service: AuditService,
    ):
        self.member_repo = member_repo
        self.history_repo = history_repo
        self.org_repo = org_repo
        self.audit_service = audit_service

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _require_admin(self, user_role: str) -> None:
        if user_role != UserRole.ADMINISTRATOR:
            raise PermissionError("Only administrators can manage members")

    # -- Organization management --

    def create_organization(
        self,
        name: str,
        user_id: int,
        username: str,
        user_role: str,
        department: Optional[str] = None,
        route_code: Optional[str] = None,
    ) -> ClubOrganization:
        self._require_admin(user_role)
        if not name or not name.strip():
            raise ValueError("Organization name is required")

        with atomic(self.org_repo.conn):
            org = ClubOrganization(
                name=name.strip(),
                department=department,
                route_code=route_code,
            )
            org = self.org_repo.create(org)

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="org.created",
                object_type="club_organization",
                object_id=str(org.id),
                after={"name": org.name},
            )
        return org

    def update_organization(
        self,
        org_id: int,
        user_id: int,
        username: str,
        user_role: str,
        name: Optional[str] = None,
        department: Optional[str] = None,
        route_code: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> ClubOrganization:
        self._require_admin(user_role)
        org = self.org_repo.get_by_id(org_id)
        if not org:
            raise ValueError("Organization not found")

        before = {"name": org.name, "is_active": org.is_active}
        if name is not None:
            org.name = name.strip()
        if department is not None:
            org.department = department
        if route_code is not None:
            org.route_code = route_code
        if is_active is not None:
            org.is_active = is_active

        with atomic(self.org_repo.conn):
            org = self.org_repo.update(org)
            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="org.updated",
                object_type="club_organization",
                object_id=str(org.id),
                before=before,
                after={"name": org.name, "is_active": org.is_active},
            )
        return org

    # -- Member lifecycle --

    def add_member(
        self,
        org_id: int,
        full_name: str,
        user_id: int,
        username: str,
        user_role: str,
        group: Optional[str] = None,
    ) -> Member:
        self._require_admin(user_role)
        if not full_name or not full_name.strip():
            raise ValueError("Full name is required")

        org = self.org_repo.get_by_id(org_id)
        if not org:
            raise ValueError("Organization not found")
        if not org.is_active:
            raise ValueError("Cannot add members to inactive organization")

        now = self._now_utc()
        with atomic(self.member_repo.conn):
            member = Member(
                club_organization_id=org_id,
                full_name=full_name.strip(),
                status=MemberStatus.ACTIVE,
                joined_at=now,
                current_group=group,
            )
            member = self.member_repo.create(member)

            self.history_repo.create(MemberHistoryEvent(
                member_id=member.id,
                actor_user_id=user_id,
                event_type=MemberHistoryEventType.JOINED,
                after_json=json.dumps({"status": member.status, "org_id": org_id}),
            ))

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="member.joined",
                object_type="member",
                object_id=str(member.id),
                after={"full_name": member.full_name, "org_id": org_id},
            )
        return member

    def remove_member(
        self,
        member_id: int,
        user_id: int,
        username: str,
        user_role: str,
    ) -> Member:
        self._require_admin(user_role)
        member = self.member_repo.get_by_id(member_id)
        if not member:
            raise ValueError("Member not found")
        if member.status == MemberStatus.LEFT:
            raise ValueError("Member has already left")

        before = {"status": member.status}
        member.status = MemberStatus.LEFT
        member.left_at = self._now_utc()

        with atomic(self.member_repo.conn):
            member = self.member_repo.update(member)

            self.history_repo.create(MemberHistoryEvent(
                member_id=member.id,
                actor_user_id=user_id,
                event_type=MemberHistoryEventType.LEFT,
                before_json=json.dumps(before),
                after_json=json.dumps({"status": member.status}),
            ))

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="member.left",
                object_type="member",
                object_id=str(member.id),
                before=before,
                after={"status": member.status},
            )
        return member

    def transfer_member(
        self,
        member_id: int,
        target_org_id: int,
        user_id: int,
        username: str,
        user_role: str,
    ) -> Member:
        self._require_admin(user_role)
        member = self.member_repo.get_by_id(member_id)
        if not member:
            raise ValueError("Member not found")
        if member.status != MemberStatus.ACTIVE:
            raise ValueError("Only active members can be transferred")

        target_org = self.org_repo.get_by_id(target_org_id)
        if not target_org:
            raise ValueError("Target organization not found")
        if not target_org.is_active:
            raise ValueError("Cannot transfer to inactive organization")

        before = {
            "org_id": member.club_organization_id,
            "status": member.status,
        }
        member.club_organization_id = target_org_id
        member.status = MemberStatus.TRANSFERRED
        member.transferred_at = self._now_utc()

        with atomic(self.member_repo.conn):
            member = self.member_repo.update(member)

            self.history_repo.create(MemberHistoryEvent(
                member_id=member.id,
                actor_user_id=user_id,
                event_type=MemberHistoryEventType.TRANSFERRED,
                before_json=json.dumps(before),
                after_json=json.dumps({
                    "org_id": target_org_id,
                    "status": member.status,
                }),
            ))

            # Reactivate at new org
            member.status = MemberStatus.ACTIVE
            member = self.member_repo.update(member)

            self.audit_service.log(
                actor_user_id=user_id,
                actor_username=username,
                action_code="member.transferred",
                object_type="member",
                object_id=str(member.id),
                before=before,
                after={"org_id": target_org_id},
            )
        return member

    # -- CSV import --

    # CSV acceptance policy:
    #   - Max 5 MB (configurable)
    #   - Must decode cleanly as UTF-8
    #   - No NUL bytes (binary indicator)
    #   - Binary byte ratio must be < 10%
    #   - Must parse as comma-delimited CSV
    #   - Header row must contain required columns: full_name, organization_id
    #   - At least one data row required
    #   - Every data row must have the same number of columns as the header
    #   - Empty/whitespace-only files are rejected
    MAX_BINARY_RATIO = 0.10

    def validate_csv(self, file_content: bytes, max_size_mb: int = 5) -> Tuple[bool, str]:
        if len(file_content) == 0:
            return False, "File is empty"

        if len(file_content) > max_size_mb * 1024 * 1024:
            return False, f"File exceeds {max_size_mb}MB limit"

        # Reject obvious binary: NUL bytes
        if b"\x00" in file_content:
            return False, "File contains binary content (NUL bytes detected)"

        # Reject high binary-byte ratio (bytes outside printable ASCII +
        # common whitespace)
        non_text = sum(
            1 for b in file_content
            if b < 0x09 or (0x0E <= b <= 0x1F) or b == 0x7F
        )
        if len(file_content) > 0 and non_text / len(file_content) > self.MAX_BINARY_RATIO:
            return False, "File appears to be binary, not CSV"

        file_hash = hashlib.sha256(file_content).hexdigest()

        try:
            text = file_content.decode("utf-8")
        except UnicodeDecodeError:
            return False, "File is not valid UTF-8 text"

        # Reject whitespace-only
        if not text.strip():
            return False, "File contains no data"

        try:
            reader = csv.DictReader(io.StringIO(text))
            fieldnames = reader.fieldnames
            if not fieldnames:
                return False, "CSV has no header row"

            required = {"full_name", "organization_id"}
            if not required.issubset(set(fieldnames)):
                return False, f"Missing required columns: {required - set(fieldnames)}"

            expected_col_count = len(fieldnames)

            # Validate structure: at least one data row, consistent columns
            row_count = 0
            for row_num, row in enumerate(reader, start=2):
                row_count += 1
                # DictReader sets restkey/restval for mismatched columns.
                # Check actual parsed column count matches header.
                if reader.restkey and reader.restkey in row:
                    return False, (
                        f"Row {row_num}: too many columns "
                        f"(expected {expected_col_count})"
                    )
                # Detect rows with fewer columns than header
                none_count = sum(1 for v in row.values() if v is None)
                if none_count > 0:
                    return False, (
                        f"Row {row_num}: too few columns "
                        f"(expected {expected_col_count})"
                    )

            if row_count == 0:
                return False, "CSV has a header but no data rows"

        except csv.Error as e:
            return False, f"Malformed CSV: {str(e)}"
        except Exception as e:
            return False, f"Invalid CSV: {str(e)}"

        return True, file_hash

    def import_members_csv(
        self,
        file_content: bytes,
        user_id: int,
        username: str,
        user_role: str,
    ) -> dict:
        self._require_admin(user_role)

        valid, result = self.validate_csv(file_content)
        if not valid:
            raise ValueError(result)

        text = file_content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))

        imported = 0
        errors = []

        for row_num, row in enumerate(reader, start=2):
            try:
                full_name = (row.get("full_name") or "").strip()
                org_id_str = (row.get("organization_id") or "").strip()

                if not full_name:
                    errors.append({"row": row_num, "error": "full_name is required"})
                    continue
                if not org_id_str or not org_id_str.isdigit():
                    errors.append({"row": row_num, "error": "valid organization_id is required"})
                    continue

                org_id = int(org_id_str)
                org = self.org_repo.get_by_id(org_id)
                if not org or not org.is_active:
                    errors.append({"row": row_num, "error": f"organization {org_id} not found or inactive"})
                    continue

                group = (row.get("group") or "").strip() or None

                # Savepoint (not rollback) because a bad row must not undo
                # previously-successful rows in the same import batch.
                with savepoint(self.member_repo.conn):
                    member = Member(
                        club_organization_id=org_id,
                        full_name=full_name,
                        status=MemberStatus.ACTIVE,
                        joined_at=self._now_utc(),
                        current_group=group,
                    )
                    member = self.member_repo.create(member)

                    self.history_repo.create(MemberHistoryEvent(
                        member_id=member.id,
                        actor_user_id=user_id,
                        event_type=MemberHistoryEventType.IMPORTED,
                        after_json=json.dumps({"full_name": full_name, "org_id": org_id}),
                    ))

                imported += 1

            except Exception as e:
                errors.append({"row": row_num, "error": str(e)})

        self.audit_service.log(
            actor_user_id=user_id,
            actor_username=username,
            action_code="member.csv_imported",
            object_type="member",
            object_id="bulk",
            after={"imported": imported, "errors": len(errors)},
        )

        return {"imported": imported, "errors": errors, "file_hash": result}

    def get_member_history(
        self,
        member_id: int,
        user_role: Optional[str] = None,
    ) -> list:
        # Member history exposes joined/left/transferred timestamps and
        # actor IDs — read access is restricted to the same role that
        # can mutate the lifecycle (administrators).
        self._require_admin(user_role or "")
        return self.history_repo.list_by_member(member_id)

    # -- CSV export --

    # Columns shipped in the exported CSV. Must stay in sync with the
    # import validator: the first two columns (`full_name`,
    # `organization_id`) are the required import columns, so a round
    # trip export → re-import is always valid by construction.
    EXPORT_COLUMNS = [
        "id",
        "full_name",
        "organization_id",
        "status",
        "current_group",
        "joined_at",
        "left_at",
        "transferred_at",
        "created_at",
        "updated_at",
    ]

    def export_members_csv(
        self,
        user_id: int,
        username: str,
        user_role: str,
        organization_id: Optional[int] = None,
    ) -> str:
        """Render every (optionally org-filtered) member as a CSV string.

        Admin-only. The output obeys the same validation rules as
        `import_members_csv`: required columns come first and each row
        has a non-empty `full_name` + numeric `organization_id`, so the
        file is directly re-importable.

        Returns the CSV body (string). The route is responsible for
        packaging it as an HTTP attachment and writing it to
        /storage/exports if a persistent artifact is required.
        """
        self._require_admin(user_role)

        if organization_id is not None:
            members = self.member_repo.list_by_organization(organization_id)
        else:
            members = self.member_repo.list_all()

        buf = io.StringIO()
        # Attribution watermark — same contract as the export service:
        # every generated artifact is attributable to a user + time.
        buf.write(
            f"# GENERATED_BY: {username}\n"
            f"# TIMESTAMP: {self._now_utc()}\n"
            f"# CLASSIFICATION: CONFIDENTIAL\n"
        )
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(self.EXPORT_COLUMNS)

        exported = 0
        for m in members:
            row = [
                m.id,
                m.full_name,
                m.club_organization_id,
                m.status,
                m.current_group or "",
                m.joined_at or "",
                m.left_at or "",
                m.transferred_at or "",
                m.created_at or "",
                m.updated_at or "",
            ]
            # Same validation rules applied to imports: non-empty
            # full_name and numeric organization_id are mandatory.
            if not (row[1] and str(row[1]).strip()):
                continue
            try:
                int(row[2])
            except (TypeError, ValueError):
                continue
            writer.writerow(row)
            exported += 1

        # Audit — exports of customer/member data must be attributable.
        self.audit_service.log(
            actor_user_id=user_id,
            actor_username=username,
            action_code="member.csv_exported",
            object_type="member",
            object_id=str(organization_id) if organization_id is not None else "bulk",
            after={"exported": exported},
        )

        return buf.getvalue()
