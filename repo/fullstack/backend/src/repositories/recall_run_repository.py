from typing import List, Optional

from ..models.recall_run import RecallRun
from .base_repository import BaseRepository


class RecallRunRepository(BaseRepository):
    def create(self, run: RecallRun) -> RecallRun:
        now = self._now_utc()
        cursor = self._execute(
            """INSERT INTO recall_runs (
               store_id, requested_by_user_id, batch_filter,
               date_start, date_end, result_count, result_json,
               output_path, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run.store_id, run.requested_by_user_id, run.batch_filter,
             run.date_start, run.date_end, run.result_count,
             run.result_json, run.output_path, now),
        )
        run.id = cursor.lastrowid
        run.created_at = now
        return run

    def get_by_id(self, run_id: int) -> Optional[RecallRun]:
        row = self._fetchone("SELECT * FROM recall_runs WHERE id = ?", (run_id,))
        return RecallRun.from_row(row) if row else None

    def list_by_store(self, store_id: int) -> List[RecallRun]:
        rows = self._fetchall(
            "SELECT * FROM recall_runs WHERE store_id = ? ORDER BY created_at DESC",
            (store_id,),
        )
        return [RecallRun.from_row(r) for r in rows]

    def list_all(self) -> List[RecallRun]:
        rows = self._fetchall(
            "SELECT * FROM recall_runs ORDER BY created_at DESC"
        )
        return [RecallRun.from_row(r) for r in rows]

    def delete(self, run_id: int) -> None:
        self._execute("DELETE FROM recall_runs WHERE id = ?", (run_id,))
