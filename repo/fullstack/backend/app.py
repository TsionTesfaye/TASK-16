import logging
import os
import sqlite3

from flask import Flask, g, jsonify

from src.database import get_connection, init_db
from src.scheduler import Scheduler, run_expiration_sweep


def _configure_logging():
    """Configure root logger with stdout + a rotating file handler.

    The file handler writes to `${LOG_DIR}/reclaim_ops.log`
    (default `/storage/logs`). README documents this path. If the
    directory cannot be created or written we degrade gracefully to
    stdout-only and emit a warning — this keeps the app bootable in
    constrained environments (CI, dev shell, tests).
    """
    log_dir = os.environ.get("LOG_DIR", "/storage/logs")
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%dT%H:%M:%S"

    handlers = [logging.StreamHandler()]
    try:
        os.makedirs(log_dir, exist_ok=True)
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "reclaim_ops.log"),
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
        )
        file_handler.setFormatter(logging.Formatter(fmt, datefmt))
        handlers.append(file_handler)
    except OSError as e:
        # Fall back to stdout-only — never let logging setup kill boot.
        logging.basicConfig(level=logging.INFO, format=fmt, datefmt=datefmt)
        logging.getLogger(__name__).warning(
            "File logging at %s unavailable (%s); using stdout only",
            log_dir, e,
        )
        return

    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt=datefmt,
        handlers=handlers,
    )


def get_db():
    if "db" not in g:
        g.db = get_connection(g.db_path)
    return g.db


def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        try:
            if error is None:
                db.commit()
            else:
                db.rollback()
        except Exception:
            pass  # connection may already be closed
        finally:
            db.close()


def _enforce_tls_first():
    """Refuse to start in production without TLS + secure cookies.

    "Production mode" is triggered by either of:
      - RECLAIM_OPS_REQUIRE_TLS=true   (explicit opt-in)
      - FLASK_ENV=production           (the canonical Flask flag)

    In that mode the process refuses to bind unless:
      - TLS_CERT_PATH and TLS_KEY_PATH point at readable PEM files, AND
      - SECURE_COOKIES=true

    Dev/CI deployments with neither flag set continue to allow plain
    HTTP, exactly as before.
    """
    # Secure-by-default: TLS is required unless explicitly disabled
    # with RECLAIM_OPS_DEV_MODE=true. This ensures the default
    # deployment path is always HTTPS. Dev mode is the exception,
    # not the default.
    dev_mode = os.environ.get("RECLAIM_OPS_DEV_MODE", "false").lower() == "true"
    require_tls = (
        os.environ.get("RECLAIM_OPS_REQUIRE_TLS", "true").lower() == "true"
        or os.environ.get("FLASK_ENV", "").lower() == "production"
    )
    if dev_mode or not require_tls:
        return

    cert_path = os.environ.get("TLS_CERT_PATH")
    key_path = os.environ.get("TLS_KEY_PATH")
    secure_cookies = os.environ.get("SECURE_COOKIES", "false").lower() == "true"

    missing = []
    if not cert_path or not os.path.isfile(cert_path):
        missing.append("TLS_CERT_PATH (readable PEM file)")
    if not key_path or not os.path.isfile(key_path):
        missing.append("TLS_KEY_PATH (readable PEM file)")
    if not secure_cookies:
        missing.append("SECURE_COOKIES=true")

    if missing:
        raise RuntimeError(
            "TLS-first mode is required (RECLAIM_OPS_REQUIRE_TLS=true or "
            "FLASK_ENV=production) but the following are missing: "
            + ", ".join(missing)
            + ". Refusing to start without TLS + secure cookies."
        )


def create_app(db_path=None):
    _configure_logging()
    logger = logging.getLogger(__name__)

    # Production-mode hard guard — refuse to bind without TLS.
    _enforce_tls_first()

    app = Flask(__name__)

    db_path = db_path or os.environ.get("RECLAIM_OPS_DB_PATH", "/data/reclaim_ops.db")

    # Fail loudly if the DB directory cannot be created — core guarantee.
    try:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    except OSError as e:
        logger.error("Cannot create database directory for %s: %s", db_path, e)
        raise RuntimeError(f"Cannot create database directory: {e}") from e

    # Run migrations once at startup with a temporary connection.
    # Fail loudly if migrations fail — core guarantee.
    try:
        startup_conn = init_db(db_path)
        startup_conn.close()
    except Exception as e:
        logger.error("Database initialization/migration failed: %s", e)
        raise

    # Startup reconciliation — idempotently expire stale approvals, detect overdue quarantines.
    # Failure here is non-fatal (logged) so the app still starts.
    try:
        reconciled = run_expiration_sweep(db_path)
        logger.info("Startup reconciliation complete: %s", reconciled)
    except Exception as e:
        logger.warning("Startup reconciliation failed (non-fatal): %s", e)

    logger.info("Application startup complete, serving on port 5000")

    app.config["DB_PATH"] = db_path

    @app.before_request
    def before_request():
        g.db_path = app.config["DB_PATH"]

    app.teardown_appcontext(close_db)

    # Convert any sqlite3.IntegrityError that escapes the service layer
    # into a structured 400 instead of an unhandled 500. The body uses
    # the same error envelope as `error_response` so clients see a
    # consistent shape regardless of which layer caught the failure.
    @app.errorhandler(sqlite3.IntegrityError)
    def handle_integrity_error(err):
        logger.warning("sqlite3 IntegrityError surfaced: %s", err)
        return jsonify({
            "error": {
                "code": 400,
                "message": "Invalid reference or constraint violation",
            }
        }), 400

    @app.errorhandler(sqlite3.OperationalError)
    def handle_operational_error(err):
        logger.warning("sqlite3 OperationalError surfaced: %s", err)
        return jsonify({
            "error": {
                "code": 400,
                "message": "Database operation failed",
            }
        }), 400

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

    # Register route blueprints
    from src.routes.auth_routes import auth_bp
    from src.routes.ticket_routes import ticket_bp
    from src.routes.qc_routes import qc_bp
    from src.routes.table_routes import table_bp
    from src.routes.notification_routes import notification_bp
    from src.routes.member_routes import member_bp
    from src.routes.export_routes import export_bp
    from src.routes.schedule_routes import schedule_bp
    from src.routes.settings_routes import settings_bp
    from src.routes.ui_routes import ui_bp
    from src.routes.price_override_routes import price_override_bp
    from src.routes.admin_routes import admin_bp
    from src.routes.partials_routes import partials_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(ticket_bp)
    app.register_blueprint(qc_bp)
    app.register_blueprint(table_bp)
    app.register_blueprint(notification_bp)
    app.register_blueprint(member_bp)
    app.register_blueprint(export_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(price_override_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(partials_bp)
    app.register_blueprint(ui_bp)

    # Root redirect to UI
    @app.route("/")
    def root():
        from flask import redirect
        return redirect("/ui/login")

    # Optional background scheduler (enabled via env in production)
    if os.environ.get("SCHEDULER_BACKGROUND", "false").lower() == "true":
        interval = int(os.environ.get("SCHEDULER_INTERVAL_SECONDS", "300"))
        scheduler = Scheduler(db_path=db_path, interval_seconds=interval)
        scheduler.start()
        app.config["SCHEDULER"] = scheduler

    return app


def _build_ssl_context():
    """Return an ssl.SSLContext if TLS env vars are set, else None.

    TLS_CERT_PATH and TLS_KEY_PATH must both point to readable PEM files.
    When enabled, the Flask dev server will serve HTTPS on port
    TLS_PORT (default 5443). Self-signed certs are acceptable for local
    deployments — see the README for generation instructions.
    """
    cert_path = os.environ.get("TLS_CERT_PATH")
    key_path = os.environ.get("TLS_KEY_PATH")
    if not cert_path or not key_path:
        return None
    if not os.path.isfile(cert_path) or not os.path.isfile(key_path):
        raise RuntimeError(
            f"TLS enabled but cert/key not found: "
            f"cert={cert_path} key={key_path}"
        )
    import ssl
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
    return ctx


if __name__ == "__main__":
    app = create_app()
    ssl_context = _build_ssl_context()
    if ssl_context is not None:
        port = int(os.environ.get("TLS_PORT", "5443"))
        logging.getLogger(__name__).info(
            "TLS enabled — serving HTTPS on port %d", port
        )
        # Warn loudly if SECURE_COOKIES is not set — session/CSRF
        # cookies MUST have the Secure flag when served over HTTPS.
        if os.environ.get("SECURE_COOKIES", "false").lower() != "true":
            logging.getLogger(__name__).warning(
                "TLS is enabled but SECURE_COOKIES=false — "
                "set SECURE_COOKIES=true for hardened cookies"
            )
        app.run(host="0.0.0.0", port=port, ssl_context=ssl_context)
    else:
        app.run(host="0.0.0.0", port=5000)
