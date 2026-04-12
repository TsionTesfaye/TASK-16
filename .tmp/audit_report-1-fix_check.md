# Reinspection Status Report (Final, Static-Only)
Date: 2026-04-12
Scope: Recheck of the four previously reported issues.
Method: Static analysis only (no runtime execution, no Docker run, no test run).

## Final Status Summary
1. TLS optional-by-default risk: **Closed**
2. UI not materially HTMX-driven / missing queue-board workflows: **Closed**
3. One-tap dialing implemented as retrieval-only: **Closed**
4. API-level sensitive authorization coverage gap: **Closed**

---

## 1) TLS optional by default
**Status: Closed**

Evidence:
- Secure-by-default TLS enforcement in app startup: `fullstack/backend/app.py:86-116`
- Secure cookie default set to true: `fullstack/backend/src/routes/auth_routes.py:14-16`
- Default compose enforces TLS + secure cookies: `docker-compose.yml:26-29`
- TLS Gunicorn startup with cert/key in entrypoint: `fullstack/backend/docker-entrypoint.sh:30-38`
- Docs reflect secure-by-default + explicit dev opt-out: `README.md:7-17`, `README.md:152-157`, `README.md:169-177`

## 2) HTMX-driven workflow coverage
**Status: Closed**

Evidence:
- HTMX partial blueprint registered: `fullstack/backend/src/routes/partials_routes.py:19`, `fullstack/backend/app.py:200-214`
- Ticket queue HTMX: `fullstack/backend/templates/tickets/index.html:37-45`, `fullstack/backend/src/routes/partials_routes.py:98-107`
- QC queue HTMX: `fullstack/backend/templates/qc/index.html:7-13`, `fullstack/backend/src/routes/partials_routes.py:360-362`
- Table board HTMX transitions: `fullstack/backend/templates/tables/index.html:19-27`, `fullstack/backend/src/routes/partials_routes.py:396-408`, `fullstack/backend/src/routes/partials_routes.py:417-419`

## 3) One-tap dialing
**Status: Closed**

Evidence:
- Queue dial trigger via HTMX: `fullstack/backend/src/routes/partials_routes.py:78-81`
- Dial partial auto-triggers `tel:` in response script: `fullstack/backend/src/routes/partials_routes.py:169-172`, `fullstack/backend/src/routes/partials_routes.py:191-195`
- Audited + authorized dial data access path: `fullstack/backend/src/services/ticket_service.py:727-786`

## 4) API sensitive auth coverage
**Status: Closed**

Evidence:
- Sensitive auth suites present (variance/refund/export/schedule): `API_tests/test_routes.py:753-884`
- HTMX partial auth tests present: `API_tests/test_routes.py:955-992`
- Price override API auth/control tests present: `API_tests/test_routes.py:1033-1148`
- Cross-store matrix present and QC case now strict 403:
  - `API_tests/test_routes.py:1277-1322`
  - strict assertion at `API_tests/test_routes.py:1322`

---

## Static Boundary
This report confirms static implementation and test-code evidence only. Runtime behavior (browser/OS dial handler, TLS handshake/trust chain, full test pass results) requires manual execution to validate operationally.
