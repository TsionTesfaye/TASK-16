# ReclaimOps Offline Operations Suite

A fully offline, HTMX-driven Flask + SQLite system for running an in-store recyclable-textiles buyback program — buyback ticket intake, QC & traceability, table/room management, offline notifications, member administration, and operational reporting.

Everything runs locally: no internet, no external APIs, no cloud services. One `docker compose up` command brings the entire stack online.

## Quick Start (Secure by Default)

```bash
docker compose up
```

The default deployment enables **HTTPS with TLS**. On first boot, a self-signed certificate is auto-generated. Open **`https://localhost:5443/ui/login`** (accept the self-signed cert warning once). Health endpoint: `https://localhost:5443/health`.

> **Production certificates:** Replace the auto-generated cert by mounting real PEM files at the paths configured in `TLS_CERT_PATH` / `TLS_KEY_PATH`. The system refuses to start without valid TLS in the default profile.

> **Dev-only mode (no TLS):** For local development without TLS, use the explicit dev profile — this mode is **not compliant for acceptance deployment**:
> ```bash
> docker compose --profile dev up backend-dev
> ```
> Then open `http://localhost:5000/ui/login`.

> **First admin:** A brand-new deployment has no users. Create the initial administrator by POSTing to `/api/auth/bootstrap` with `username`, `password`, and `display_name`. This endpoint is unauthenticated by design and **locks itself permanently** after the first successful call — subsequent requests return `403`. All later users must be created through `/api/auth/users` by an administrator.

> **Fresh install → working intake** (full 0→1 sequence):
> 1. `POST /api/auth/bootstrap` — create the first admin
> 2. `POST /api/auth/login` — log in as admin
> 3. `POST /api/admin/stores` — create a store (`code`, `name`, optional `route_code`). Settings are auto-created.
> 4. `POST /api/admin/pricing_rules` — create a pricing rule (`store_id`, `base_rate_per_lb`, optional `bonus_pct`, `max_ticket_payout`, `eligibility_start_local`, `eligibility_end_local` in `MM/DD/YYYY hh:mm AM/PM` format)
> 5. `POST /api/admin/service_tables` — create tables (`store_id`, `table_code`, `area_type`: `intake_table` / `private_room`)
> 6. `POST /api/auth/users` — create operator accounts (`store_id`, `role`)
> 7. Log in as an operator → create tickets, manage tables, run QC via the UI

> **Overdue quarantines:** The startup reconciliation sweep surfaces overdue quarantine returns via **logs only** (look for `overdue quarantine` entries in `/storage/logs`). There is no in-app alert — operators are expected to watch the log stream.

**First startup does the following automatically:**

1. Creates the data directory and runs schema migrations (tracked in a `schema_migrations` table — idempotent).
2. Generates a fresh AES-256 encryption key at `/run/secrets/reclaim_ops_key` plus an `.initialized` marker. **Back up this key.** If it is lost after initial setup, the system refuses to regenerate — it raises `KeyFileMissingError` rather than silently orphaning all existing encrypted data.
3. Runs a startup reconciliation sweep (expires stale pending approvals and exports, surfaces overdue quarantine returns).

## Run Tests

```bash
./run_tests.sh
```

This builds a test container and runs all unit and API tests inside Docker using pytest. Current suite: **250+ tests** across schema, models, enums, repositories, services, security, hardening, and API layers.

You can also run locally:

```bash
cd fullstack/backend
pip install -r requirements.txt
cd ../..
python -m pytest unit_tests/ API_tests/ -v
```

## Project Structure

```
repo/
  docker-compose.yml              # Backend + test runner services
  run_tests.sh                    # One-command test runner
  README.md
  fullstack/
    backend/
      app.py                      # Flask entry point, startup reconciliation, DI
      Dockerfile
      requirements.txt            # flask, gunicorn, pytest, bcrypt, cryptography
      migrations/
        001_initial_schema.sql    # Full SQLite schema (migration-tracked)
      templates/                  # Jinja2 + HTMX templates
      static/css/                 # Minimal operational CSS
      src/
        database.py               # Connection + migration runner
        enums/                    # 17 enum types
        models/                   # 23 dataclass models
        repositories/             # 24 repositories (CRUD + conditional updates)
        services/                 # 13 services (all business logic)
        routes/                   # 10 route blueprints (API + UI)
        security/                 # crypto (AES-256-GCM), masking
        scheduler/                # Idempotent sweep + optional background runner
    storage/
      exports/ uploads/ reports/ logs/    # Mounted volumes
  unit_tests/                     # Schema, models, repos, services, security, hardening
  API_tests/                      # API endpoint tests
```

## Architecture

**Layered — strict separation:**

```
HTMX Browser UI
    ↓
Flask Routes (thin controllers)
    ↓
Services (all business logic)
    ↓
Repositories (raw SQL, parameterized)
    ↓
SQLite (WAL mode, FKs enforced)
```

- **Backend**: Flask 3.x on Python 3.11
- **Database**: SQLite with WAL mode, foreign keys ON, audit log immutability triggers, migration tracking
- **Auth**: Username + bcrypt password hashing; signed session cookies with anti-replay nonces; CSRF token on every mutating request
- **Crypto**: AES-256-GCM for phone numbers / sensitive fields; key lives outside the DB at `/run/secrets/reclaim_ops_key`
- **Scheduler**: Local-only idempotent sweep, runs at startup for reconciliation; optional background thread

## Core Flows Exposed via UI & API

- Buyback ticket intake → QC → variance confirmation → supervisor approval → completion
- Refund initiation → supervisor approval (with password re-entry) → refund
- QC inspection, quarantine, concession sign-off, batch traceability, recall generation
- Table/room state machine (available → occupied → pre_checkout → cleared) with merge/transfer
- Notification center (logged messages + call attempts + retry reminders)
- Member lifecycle + CSV import
- Operations metrics (order volume, revenue, refund rate, load factor)
- Export requests with supervisor approval and watermarks
- Schedule adjustment requests (dual-control)

## Security Guarantees

| Control | Implementation |
|---|---|
| Password hashing | bcrypt (12 rounds) with PBKDF2 backward-compatibility |
| Session management | httponly, SameSite=Strict, time-limited cookies with nonces |
| CSRF | X-CSRF-Token header validated on all POST/PUT/PATCH/DELETE |
| Encryption at rest | AES-256-GCM on sensitive fields (phone, etc.) |
| Data masking | Sensitive fields masked by default in API responses |
| Audit log | Append-only, tamper-chain hashed, DB-level DELETE/UPDATE triggers |
| Dual-control | Variance, refund, export, schedule adjustments — atomic conditional UPDATE prevents replay |
| Key loss protection | Post-init key loss raises `KeyFileMissingError` — NO silent regeneration |
| CSV upload | CSV-only, 5MB max, UTF-8, no binary (NUL/high-binary-ratio rejected), header + column-count validated, at least one data row required |

## Operational Hardening

- **Startup reconciliation** — idempotent sweep on every boot expires stale pending approvals, expires stale export requests, and surfaces overdue quarantine returns.
- **Transaction safety** — request-scoped connection commits on success, rolls back on any exception. Critical approval paths use conditional UPDATE + rowcount check for atomic execution.
- **Idempotency** — duplicate approval / execution attempts fail with an explicit error; no partial state possible.
- **Concurrency** — approvals, refunds, exports, and schedule adjustments all use `UPDATE ... WHERE status='pending'` patterns that survive concurrent requests.
- **Audit immutability** — DB triggers prevent DELETE/UPDATE on `audit_logs`.
- **Migration tracking** — `schema_migrations` table prevents re-running applied migrations.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `RECLAIM_OPS_DB_PATH` | `/data/reclaim_ops.db` | SQLite database file path |
| `RECLAIM_OPS_KEY_PATH` | `/run/secrets/reclaim_ops_key` | Encryption key file path |
| `SECURE_COOKIES` | `true` | Secure-by-default. Set `false` only in dev mode. |
| `TLS_CERT_PATH` | _(unset)_ | PEM certificate path. Docker entrypoint auto-generates a self-signed cert if missing. |
| `TLS_KEY_PATH`  | _(unset)_ | PEM private key path. Docker entrypoint auto-generates if missing. |
| `TLS_PORT` | `5443` | HTTPS listen port |
| `RECLAIM_OPS_REQUIRE_TLS` | `true` | **Secure-by-default.** App refuses to start without TLS certs and secure cookies. Set `false` with `RECLAIM_OPS_DEV_MODE=true` for local dev only. |
| `RECLAIM_OPS_DEV_MODE` | `false` | Set `true` to disable TLS enforcement. **Dev only — not for acceptance/production.** |
| `SESSION_KEY_PATH` | `/run/secrets/reclaim_ops_session_key` | HMAC key used to sign the `session_nonce` cookie. Auto-generated on first start (mode 0600) — back it up alongside the encryption key. |
| `EXPORT_OUTPUT_DIR` | `/storage/exports` | Directory where completed export CSVs are written |
| `LOG_DIR` | `/storage/logs` | Directory for the rotating `reclaim_ops.log` file (10 MB × 5 backups). Falls back to stdout-only if the directory is not writable. |
| `SCHEDULER_BACKGROUND` | `false` | Set `true` to run the sweep in a daemon thread |
| `SCHEDULER_INTERVAL_SECONDS` | `300` | Background sweep interval |
| `EXPORT_PENDING_MAX_HOURS` | `24` | Export request pending-expiry window |
| `SCHEDULE_PENDING_MAX_HOURS` | `48` | Schedule adjustment pending-expiry window |
| `FLASK_ENV` | `production` | Flask environment |

## TLS (HTTPS)

ReclaimOps is **secure-by-default**: the app requires TLS and will refuse to start without valid certificate paths and `SECURE_COOKIES=true`. The Docker entrypoint auto-generates a self-signed cert on first boot — no manual steps needed for `docker compose up`.

**Custom certificates:** Replace the auto-generated cert by mounting real PEM files at `TLS_CERT_PATH` / `TLS_KEY_PATH`. Gunicorn terminates TLS directly via `--certfile`/`--keyfile` on port 5443.

**Dev-only (no TLS):** To run without TLS for local development, explicitly opt out:
```bash
docker compose --profile dev up backend-dev
```
Or set `RECLAIM_OPS_DEV_MODE=true` + `RECLAIM_OPS_REQUIRE_TLS=false` + `SECURE_COOKIES=false`.

## Docker Volumes

The canonical runtime uses these mounts:

| Mount | Purpose |
|---|---|
| `db-data:/data` | SQLite database (persistent) |
| `./fullstack/storage/exports:/storage/exports` | CSV exports |
| `./fullstack/storage/uploads:/storage/uploads` | CSV imports |
| `./fullstack/storage/reports:/storage/reports` | Generated reports |
| `./fullstack/storage/logs:/storage/logs` | Log output |

**Production note**: Mount the encryption key file (or Docker secret) at `/run/secrets/reclaim_ops_key` and back it up separately — the system refuses to regenerate it after initial setup.

## Key File Lifecycle

| State | Behavior |
|---|---|
| No key, no marker | **First init** — generates key + marker, logs warning |
| Key present, marker present | **Normal startup** — loads key |
| Key present, marker missing | **Pre-marker install** — loads key and backfills marker |
| **No key, marker present** | **POST-INIT LOSS** — raises `KeyFileMissingError`, refuses to start crypto operations |
| Corrupt key | Raises `CorruptKeyError`, does NOT overwrite the bad file |

If the encryption key is ever lost in production:
1. Restore from backup (preferred).
2. Or accept total loss of encrypted data: manually delete the `.initialized` marker file to force re-initialization.

## Entity Catalog

| Entity | Table |
|--------|-------|
| Store | stores |
| User | users |
| UserSession | user_sessions |
| BuybackTicket | buyback_tickets |
| PricingRule | pricing_rules |
| PricingCalculationSnapshot | pricing_calculation_snapshots |
| VarianceApprovalRequest | variance_approval_requests |
| QCInspection | qc_inspections |
| QuarantineRecord | quarantine_records |
| Batch | batches |
| BatchGenealogyEvent | batch_genealogy_events |
| RecallRun | recall_runs |
| ServiceTable | service_tables |
| TableSession | table_sessions |
| TableActivityEvent | table_activity_events |
| NotificationTemplate | notification_templates |
| TicketMessageLog | ticket_message_logs |
| ClubOrganization | club_organizations |
| Member | members |
| MemberHistoryEvent | member_history_events |
| ExportRequest | export_requests |
| ScheduleAdjustmentRequest | schedule_adjustment_requests |
| AuditLog | audit_logs |
| Settings | settings |
