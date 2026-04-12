from dataclasses import dataclass
from typing import Optional

from ..enums.export_request_status import ExportRequestStatus


@dataclass
class ExportRequest:
    id: Optional[int] = None
    store_id: int = 0
    requested_by_user_id: int = 0
    export_type: str = ""
    filter_json: Optional[str] = None
    watermark_enabled: bool = False
    attribution_text: Optional[str] = None
    approval_required: bool = False
    approver_user_id: Optional[int] = None
    status: str = ExportRequestStatus.PENDING
    output_path: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None

    @staticmethod
    def from_row(row) -> "ExportRequest":
        return ExportRequest(
            id=row["id"],
            store_id=row["store_id"],
            requested_by_user_id=row["requested_by_user_id"],
            export_type=row["export_type"],
            filter_json=row["filter_json"],
            watermark_enabled=bool(row["watermark_enabled"]),
            attribution_text=row["attribution_text"],
            approval_required=bool(row["approval_required"]),
            approver_user_id=row["approver_user_id"],
            status=row["status"],
            output_path=row["output_path"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )
