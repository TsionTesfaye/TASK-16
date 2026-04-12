import logging
import os
import sqlite3
from datetime import datetime, timezone


logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("RECLAIM_OPS_DB_PATH", "/data/reclaim_ops.db")
MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations")


def _apply_pragmas(conn):
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")


def _ensure_schema_migrations_table(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL
        )"""
    )
    conn.commit()


def _get_applied_migrations(conn):
    rows = conn.execute("SELECT filename FROM schema_migrations").fetchall()
    return {row[0] for row in rows}


def get_connection(db_path=None):
    path = db_path or DB_PATH
    try:
        conn = sqlite3.connect(path, check_same_thread=False)
    except sqlite3.OperationalError:
        logger.error("Failed to connect to database at %s", path)
        raise
    conn.row_factory = sqlite3.Row
    _apply_pragmas(conn)
    return conn


def run_migrations(conn):
    if not os.path.isdir(MIGRATIONS_DIR):
        logger.warning("Migrations directory not found: %s — skipping migrations", MIGRATIONS_DIR)
        return

    _ensure_schema_migrations_table(conn)
    applied = _get_applied_migrations(conn)

    migration_files = sorted(
        f for f in os.listdir(MIGRATIONS_DIR)
        if f.endswith(".sql")
    )

    for migration_file in migration_files:
        if migration_file in applied:
            continue
        logger.info("Applying migration: %s", migration_file)
        path = os.path.join(MIGRATIONS_DIR, migration_file)
        with open(path, "r") as f:
            sql = f.read()
        conn.executescript(sql)
        # executescript() may reset pragmas — re-apply after each migration
        _apply_pragmas(conn)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            "INSERT INTO schema_migrations (filename, applied_at) VALUES (?, ?)",
            (migration_file, now),
        )
        conn.commit()
        logger.info("Migration applied: %s", migration_file)


def init_db(db_path=None):
    path = db_path or DB_PATH
    logger.info("Initializing database at %s", path)
    conn = get_connection(path)
    run_migrations(conn)
    logger.info("Database ready")
    return conn
