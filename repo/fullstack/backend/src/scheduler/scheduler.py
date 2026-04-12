"""Local scheduler — idempotent background job runner.

Runs entirely locally. No external services. No network.

Jobs handled:
1. Expire pending export requests older than the configured cutoff
   (prevents stale approval requests from accumulating forever).
2. Expire variance approval requests past their explicit expires_at time.
3. Expire schedule adjustment requests (defensive — no expires_at field yet,
   uses a fixed age cutoff similar to exports).
4. Detect and log overdue quarantine returns (7-day deadline) — cannot auto-
   resolve since disposition requires an operator, but makes them visible to
   ops for action.

Idempotency:
- All operations use conditional UPDATE ... WHERE status='pending' so running
  the sweep repeatedly has no effect after the first expiration.
- Overdue-quarantine detection is read-only and reports a count.

Startup reconciliation:
- run_expiration_sweep() is called once at application startup from app.py
  to bring the database back to a consistent state after downtime.

Background execution (optional):
- Set SCHEDULER_BACKGROUND=true to run a daemon thread that sweeps every
  SCHEDULER_INTERVAL_SECONDS (default 300). In tests and CI, leave disabled.
"""
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..database import get_connection

logger = logging.getLogger(__name__)

# Default expiration windows
EXPORT_PENDING_MAX_HOURS = int(os.environ.get("EXPORT_PENDING_MAX_HOURS", "24"))
SCHEDULE_PENDING_MAX_HOURS = int(os.environ.get("SCHEDULE_PENDING_MAX_HOURS", "48"))


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hours_ago_iso(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_expiration_sweep(db_path: str) -> dict:
    """Run one idempotent pass over time-sensitive state.

    Returns a dict of counts for each job action. Safe to call repeatedly.
    Safe at startup for reconciliation.
    """
    conn = get_connection(db_path)
    result = {
        "exports_expired": 0,
        "variance_expired": 0,
        "schedules_expired": 0,
        "quarantines_overdue": 0,
    }
    try:
        now = _now_utc_iso()

        # 1. Expire stale pending export requests
        export_cutoff = _hours_ago_iso(EXPORT_PENDING_MAX_HOURS)
        cursor = conn.execute(
            "UPDATE export_requests SET status = 'expired' "
            "WHERE status = 'pending' AND created_at < ?",
            (export_cutoff,),
        )
        result["exports_expired"] = cursor.rowcount

        # 2. Expire variance approval requests past their explicit expires_at
        cursor = conn.execute(
            "UPDATE variance_approval_requests SET status = 'expired', rejected_at = ? "
            "WHERE status = 'pending' "
            "AND expires_at IS NOT NULL AND expires_at < ?",
            (now, now),
        )
        result["variance_expired"] = cursor.rowcount

        # 3. Expire stale pending schedule adjustment requests
        schedule_cutoff = _hours_ago_iso(SCHEDULE_PENDING_MAX_HOURS)
        cursor = conn.execute(
            "UPDATE schedule_adjustment_requests SET status = 'rejected', rejected_at = ? "
            "WHERE status = 'pending' AND created_at < ?",
            (now, schedule_cutoff),
        )
        result["schedules_expired"] = cursor.rowcount

        # 4. Detect overdue quarantine returns (read-only — cannot auto-resolve).
        # A quarantine is overdue if it's still unresolved AND its SLA
        # deadline (set at creation time in qc_service.create_quarantine)
        # has passed. The previous filter required `disposition =
        # 'return_to_customer'`, which was impossible: `disposition` is
        # only ever set during `resolve_quarantine`, which also sets
        # `resolved_at` — so the query always returned zero rows.
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM quarantine_records "
            "WHERE resolved_at IS NULL "
            "AND due_back_to_customer_at IS NOT NULL "
            "AND due_back_to_customer_at < ?",
            (now,),
        ).fetchone()
        result["quarantines_overdue"] = row["cnt"] if row else 0

        if result["quarantines_overdue"] > 0:
            # Log each overdue record so operators can correlate in logs.
            overdue_rows = conn.execute(
                "SELECT id, ticket_id, batch_id, due_back_to_customer_at "
                "FROM quarantine_records "
                "WHERE resolved_at IS NULL "
                "AND due_back_to_customer_at IS NOT NULL "
                "AND due_back_to_customer_at < ? "
                "ORDER BY due_back_to_customer_at ASC",
                (now,),
            ).fetchall()
            for r in overdue_rows:
                logger.warning(
                    "overdue quarantine id=%d ticket_id=%d batch_id=%d deadline=%s",
                    r["id"], r["ticket_id"], r["batch_id"],
                    r["due_back_to_customer_at"],
                )

        conn.commit()

        if any(result[k] > 0 for k in ("exports_expired", "variance_expired", "schedules_expired")):
            logger.warning(
                "Scheduler sweep completed: exports_expired=%d variance_expired=%d "
                "schedules_expired=%d quarantines_overdue=%d",
                result["exports_expired"], result["variance_expired"],
                result["schedules_expired"], result["quarantines_overdue"],
            )
        elif result["quarantines_overdue"] > 0:
            # Overdue quarantines need human attention — log at warning level.
            logger.warning(
                "Scheduler sweep: %d overdue quarantine return(s) need attention",
                result["quarantines_overdue"],
            )
        else:
            # Nothing to do — debug level to avoid noise in background mode.
            logger.debug("Scheduler sweep: no-op")
        return result
    except Exception as e:
        logger.exception("Scheduler sweep failed: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


class Scheduler:
    """Optional background scheduler thread.

    Runs run_expiration_sweep() every `interval_seconds`. Fails safely:
    any exception in a sweep is logged but does not crash the thread.
    """

    def __init__(self, db_path: str, interval_seconds: int = 300):
        self.db_path = db_path
        self.interval_seconds = interval_seconds
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._started = False

    def start(self) -> None:
        if self._started:
            logger.warning("Scheduler already started — ignoring duplicate start()")
            return
        self._started = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="reclaim-scheduler",
        )
        self._thread.start()
        logger.info(
            "Scheduler background thread started (interval=%ds)",
            self.interval_seconds,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._started = False
        logger.info("Scheduler stopped")

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                run_expiration_sweep(self.db_path)
            except Exception as e:
                # Never let an exception kill the thread — just log it.
                logger.exception("Scheduler sweep raised an exception: %s", e)
            # Wait for either the interval to elapse or stop() to be called.
            self._stop_event.wait(self.interval_seconds)
