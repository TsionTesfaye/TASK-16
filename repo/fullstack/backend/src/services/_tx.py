"""Shared transaction helper for service-layer atomicity.

The `atomic` context manager guarantees that if any exception is raised
inside its block, the connection is rolled back BEFORE the exception
propagates out. This makes multi-step service writes truly atomic — their
atomicity no longer depends on Flask's teardown behavior.

Without this, a service that writes successfully to entity A, then raises
ValueError before writing entity B, would have the route catch the
ValueError and return 4xx. Flask's teardown sees `error=None` (because the
exception was caught by the route) and calls `commit()`, silently persisting
the partial state. Using this helper forces the rollback to happen at the
moment the exception leaves the service, before the route's except-clause
can catch it.

Usage:
    with atomic(self.ticket_repo.conn):
        # first write
        if not self.variance_repo.try_execute_approval(...):
            raise ValueError("...")
        # second write
        if not self.ticket_repo.try_transition_status(...):
            raise ValueError("...")  # ← rollback fires before this escapes
        self.audit_service.log(...)
"""
import logging
import threading
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_savepoint_counter = threading.local()


def _next_savepoint_name() -> str:
    n = getattr(_savepoint_counter, "n", 0) + 1
    _savepoint_counter.n = n
    return f"sp_{n}"


@contextmanager
def atomic(conn):
    """Roll back the connection on any exception raised inside the block.

    On normal exit, this helper does NOT commit — the enclosing request's
    teardown handler is still responsible for committing the full request.
    This preserves request-level atomicity while adding block-level
    rollback-on-error semantics.
    """
    try:
        yield
    except Exception:
        try:
            conn.rollback()
        except Exception as rollback_err:
            logger.error(
                "Rollback failed while handling another exception: %s",
                rollback_err,
            )
        raise


@contextmanager
def savepoint(conn):
    """Nested-transaction helper using SQLite SAVEPOINT.

    Unlike `atomic`, this rolls back ONLY the writes performed inside the
    block — prior writes in the same connection/request are preserved. Use
    this when a single request performs multiple independently-recoverable
    sub-operations (e.g. CSV row-by-row imports where one bad row must not
    poison previously successful rows).
    """
    name = _next_savepoint_name()
    conn.execute(f"SAVEPOINT {name}")
    try:
        yield
    except Exception:
        try:
            conn.execute(f"ROLLBACK TO SAVEPOINT {name}")
            conn.execute(f"RELEASE SAVEPOINT {name}")
        except Exception as rollback_err:
            logger.error(
                "Savepoint rollback failed while handling another exception: %s",
                rollback_err,
            )
        raise
    else:
        conn.execute(f"RELEASE SAVEPOINT {name}")
