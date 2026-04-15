# ReclaimOps — Offline Operations Suite

A fully offline, HTMX-driven buyback operations platform for in-store recyclable-textile programs. Handles ticket intake, QC & traceability, table/room state, notifications, member administration, and operational reporting. No internet, no external APIs, no cloud services — one `docker compose up` brings the entire stack online.

## Architecture & Tech Stack

* **Frontend:** Jinja2 server-rendered templates + HTMX (vendored — no CDN)
* **Backend:** Flask 3.1 on Python 3.11, Gunicorn with threaded workers
* **Database:** SQLite in WAL mode, foreign keys enforced, migration-tracked schema, DB-level immutability triggers on audit log
* **Security:** bcrypt password hashing, AES-256-GCM at rest, HMAC-signed session cookies, CSRF tokens, TLS-first secure-by-default
* **Containerization:** Docker & Docker Compose

## Project Structure

```text
.
├── fullstack/
│   ├── backend/
│   │   ├── app.py                  # Flask entry point
│   │   ├── Dockerfile
│   │   ├── docker-entrypoint.sh    # Auto-generates TLS cert on first boot
│   │   ├── requirements.txt
│   │   ├── migrations/             # SQL migrations (tracked)
│   │   ├── templates/              # Jinja2 + HTMX templates
│   │   ├── static/                 # CSS + vendored HTMX
│   │   └── src/
│   │       ├── enums/              # 17 enum types
│   │       ├── models/             # Dataclass models
│   │       ├── repositories/       # Raw-SQL CRUD
│   │       ├── services/           # All business logic
│   │       ├── routes/             # Flask blueprints (API + UI + HTMX partials)
│   │       ├── security/           # Crypto, masking, session cookies
│   │       └── scheduler/          # Idempotent reconciliation sweep
│   └── storage/                    # Docker-mounted volumes (exports, uploads, logs, reports)
├── unit_tests/                     # Schema, models, repos, services, security, hardening
├── API_tests/                      # API + HTMX partial + cross-store matrix tests
├── docs/
│   └── api-spec.md                 # Full API specification
├── .gitignore
├── docker-compose.yml
├── run_tests.sh
└── README.md
```

## Prerequisites

* Docker
* Docker Compose (v2 plugin, `docker compose ...`)

## Running the Application

Default profile (secure-by-default, TLS on port 5443):

```bash
docker compose up --build -d
```

A self-signed TLS certificate is auto-generated on first boot. The database, encryption key, and session signing key persist in Docker named volumes.

Dev profile (plain HTTP on port 5000 — **not for production**):

```bash
docker compose --profile dev up --build -d backend-dev
```

## Access

* **Frontend (TLS):** https://localhost:5443/ui/login (accept self-signed cert once)
* **Frontend (dev):** http://localhost:5000/ui/login
* **Backend API:** https://localhost:5443/api/ (or http://localhost:5000/api/ in dev)
* **API docs:** [`docs/api-spec.md`](docs/api-spec.md) — 87 endpoints across 14 groups
* **Health check:** https://localhost:5443/health

## First-run Bootstrap

A fresh deployment has zero users. Create the initial administrator once:

```bash
curl -k -X POST https://localhost:5443/api/auth/bootstrap \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"ChangeMeNow123!","display_name":"Admin"}'
```

The bootstrap endpoint locks itself permanently after first success. All subsequent users are created via `POST /api/auth/users` by an administrator.

## Stop

```bash
docker compose down -v
```

(`-v` also removes the `db-data` and `key-data` volumes — a full reset.)

## Testing

All tests run inside Docker against a fresh database. No local Python or system dependencies are required.

```bash
chmod +x run_tests.sh
./run_tests.sh
```

The script runs two stages and exits `0` only when both pass, non-zero on any failure or coverage shortfall.

**Stage 1 — pytest (908 tests, 93.64% line coverage, gate ≥ 90%):**

| Layer | Tests |
|-------|-------|
| Schema + models + enums | 70 |
| Repositories (CRUD + conditional updates) | 66 |
| Services (business logic) | 159 |
| Security (crypto, CSRF, sessions, masking) | 29 |
| Hardening (transactions, idempotency, audit immutability) | 13 |
| Coverage expansion (branches, validation, role gates) | 261 |
| API endpoints (routes, auth, role gates, validation) | 109 |
| API coverage + flow + deep tests | 157 |
| HTMX partials (cross-store matrix, RBAC, null-store) | 26 |
| Health | 2 |

**Stage 2 — Playwright E2E (16 tests, 6 roles, real browser):**

Browser-driven tests run against a live backend container over plain HTTP. Covers operator, QC inspector, host, shift supervisor (×2 for dual-control approval), and administrator workflows — including HTMX partial state transitions, hx-prompt dialogs, and role-based page redirects.

## Seeded Credentials

The system intentionally ships **with no seeded users** — an empty-credentials deployment is a security requirement for the acceptance profile. Create the first administrator with the bootstrap call above; use that admin to provision operator accounts.

| Role | Username | Password |
|------|----------|----------|
| Administrator | _(create via `/api/auth/bootstrap`)_ | _(your choice, 12+ chars)_ |
| Operators (front desk, QC, host, supervisor, ops manager) | _(create via `/api/auth/users` as admin)_ | _(admin-issued, 12+ chars)_ |

**Password policy:** 12-character minimum. 5 failed attempts lock the account for 15 minutes.

## Security Guarantees

| Control | Implementation |
|---------|----------------|
| Password hashing | bcrypt (12 rounds) |
| Session management | HttpOnly, Secure, SameSite=Strict, HMAC-signed nonce, 8h max / 30m idle |
| CSRF | `X-CSRF-Token` header required on all POST/PUT/PATCH/DELETE |
| Encryption at rest | AES-256-GCM on phone numbers and sensitive fields |
| Data masking | Sensitive fields masked by default in API responses |
| Audit log | Append-only, tamper-chain hashed, DB triggers block DELETE/UPDATE |
| Dual-control | Variance, refund, export, schedule, price-override approvals use atomic conditional UPDATE |
| Store isolation | Non-admin users cannot access cross-store data; query-param overrides rejected |
| Role gates | Least-privilege on UI pages, API endpoints, and HTMX partials |
| CSV upload | 5MB max, UTF-8, no binary (NUL/high-ratio rejected), header + column-count validated |
| Key loss protection | Post-init key loss raises `KeyFileMissingError` — no silent regeneration |
| TLS-first | Refuses to start without valid certs + `SECURE_COOKIES=true` (unless explicit dev mode) |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RECLAIM_OPS_DB_PATH` | `/data/reclaim_ops.db` | SQLite database file |
| `RECLAIM_OPS_KEY_PATH` | `/run/secrets/reclaim_ops_key` | AES-256 encryption key |
| `SESSION_KEY_PATH` | `/run/secrets/reclaim_ops_session_key` | HMAC session-cookie key |
| `TLS_CERT_PATH` / `TLS_KEY_PATH` | _(auto-generated)_ | PEM cert + key |
| `SECURE_COOKIES` | `true` | Secure cookie flag |
| `RECLAIM_OPS_REQUIRE_TLS` | `true` | Refuse start without TLS |
| `RECLAIM_OPS_DEV_MODE` | `false` | Set `true` to disable TLS enforcement (dev only) |
| `EXPORT_OUTPUT_DIR` | `/storage/exports` | Where generated CSV exports are written |
| `LOG_DIR` | `/storage/logs` | Rotating log file directory |
| `SCHEDULER_BACKGROUND` | `false` | Run reconciliation sweep in background thread |
| `SCHEDULER_INTERVAL_SECONDS` | `300` | Background sweep interval |
