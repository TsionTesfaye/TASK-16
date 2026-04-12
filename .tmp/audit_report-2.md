# ReclaimOps Static Delivery Acceptance + Architecture Audit (2026-04-12)

## 1. Verdict
- **Overall conclusion: Partial Pass**
- Basis: The repository is a real, substantial full-stack delivery with strong coverage of core offline workflows, security controls, and test assets; however, there are material authorization and requirement-fit gaps that prevent a clean pass.

## 2. Scope and Static Verification Boundary
- **What was reviewed**: README, project structure, Flask entrypoint/config, all route modules, core services/repositories/migrations, UI templates/CSS, and unit/API test files.
- **What was not reviewed**: Runtime behavior under real browser/network/container execution; performance under load; certificate deployment correctness in a live LAN; telephony behavior on workstation hardware.
- **Intentionally not executed**: App startup, Docker, tests, external services.
- **Claims requiring manual verification**:
  - End-to-end HTTPS certificate trust and browser UX on target LAN.
  - One-tap dialing behavior on actual workstation OS/device.
  - Real operator workflows across concurrent users and long-running sessions.

## 3. Repository / Requirement Mapping Summary
- **Prompt core goal mapped**: Offline HTMX + Flask + SQLite operations suite for textiles buyback with ticketing/pricing/QC/traceability/tables/notifications/members/reports/security.
- **Main implementation areas mapped**:
  - Intake/pricing/variance/refund/dial: `fullstack/backend/src/services/ticket_service.py`
  - QC/quarantine/sampling: `fullstack/backend/src/services/qc_service.py`
  - Batch genealogy/recall: `fullstack/backend/src/services/traceability_service.py`
  - Tables merge/transfer/timeline: `fullstack/backend/src/services/table_service.py`
  - Notifications + retries/templates: `fullstack/backend/src/services/notification_service.py`
  - Members + CSV import/export: `fullstack/backend/src/services/member_service.py`
  - Reports/exports/approval/watermark: `fullstack/backend/src/services/export_service.py`
  - Auth/session/CSRF/cookies/security primitives: `fullstack/backend/src/services/auth_service.py`, `fullstack/backend/src/routes/helpers.py`, `fullstack/backend/src/security/*`

## 4. Section-by-section Review

### 1. Hard Gates

#### 1.1 Documentation and static verifiability
- **Conclusion: Pass**
- **Rationale**: Clear startup, TLS profiles, bootstrap sequence, test commands, and architecture are documented; entry points and paths are statically discoverable.
- **Evidence**: `README.md:7`, `README.md:25`, `README.md:42`, `README.md:59`, `docker-compose.yml:1`, `fullstack/backend/app.py:119`

#### 1.2 Material deviation from Prompt
- **Conclusion: Partial Pass**
- **Rationale**: Core scenario is implemented, but there is a material authz gap in HTMX partial reads and a schema/API mismatch for table area types.
- **Evidence**: `fullstack/backend/src/routes/partials_routes.py:27`, `fullstack/backend/src/routes/partials_routes.py:98`, `fullstack/backend/src/services/auth_service.py:166`, `fullstack/backend/migrations/001_initial_schema.sql:253`, `fullstack/backend/src/routes/admin_routes.py:154`, `README.md:30`

### 2. Delivery Completeness

#### 2.1 Core prompt requirements coverage
- **Conclusion: Partial Pass**
- **Rationale**: Most core functional requirements are implemented (ticket pricing/caps/variance dual-control, QC escalation/quarantine, traceability, tables, notifications, members, reports/exports). Gaps are in authorization boundaries and strict file-type validation semantics.
- **Evidence**:
  - Pricing/caps/variance: `fullstack/backend/src/services/pricing_service.py:163`, `fullstack/backend/src/services/pricing_service.py:243`, `fullstack/backend/src/services/ticket_service.py:317`, `fullstack/backend/src/services/ticket_service.py:422`
  - QC escalation/quarantine: `fullstack/backend/src/services/qc_service.py:83`, `fullstack/backend/src/services/qc_service.py:95`, `fullstack/backend/src/services/qc_service.py:227`, `fullstack/backend/src/services/qc_service.py:317`
  - Traceability/recall: `fullstack/backend/src/services/traceability_service.py:138`, `fullstack/backend/src/services/traceability_service.py:220`
  - Tables: `fullstack/backend/src/services/table_service.py:82`, `fullstack/backend/src/services/table_service.py:206`, `fullstack/backend/src/services/table_service.py:268`, `fullstack/backend/src/services/table_service.py:330`
  - Notifications/retries/templates: `fullstack/backend/src/services/notification_service.py:67`, `fullstack/backend/migrations/004_seed_notification_templates.sql:7`
  - Members CSV: `fullstack/backend/src/routes/member_routes.py:177`, `fullstack/backend/src/services/member_service.py:270`
  - Reports/exports: `fullstack/backend/src/services/export_service.py:450`, `fullstack/backend/src/services/export_service.py:422`

#### 2.2 End-to-end 0→1 deliverable vs partial/demo
- **Conclusion: Pass**
- **Rationale**: Multi-module codebase with migrations, API/UI, security, and extensive tests; not a toy snippet.
- **Evidence**: `README.md:25`, `README.md:59`, `fullstack/backend/migrations/001_initial_schema.sql:1`, `API_tests/test_routes.py:579`, `unit_tests/test_services.py:1`

### 3. Engineering and Architecture Quality

#### 3.1 Structure and module decomposition
- **Conclusion: Pass**
- **Rationale**: Clear layered separation (routes/services/repos/models/security), with business logic concentrated in services.
- **Evidence**: `README.md:92`, `fullstack/backend/src/routes/helpers.py:109`, `fullstack/backend/src/services/ticket_service.py:58`, `fullstack/backend/src/repositories/user_session_repository.py:7`

#### 3.2 Maintainability and extensibility
- **Conclusion: Partial Pass**
- **Rationale**: Generally maintainable with good transaction guards and role/store authorization helpers; weakened by inconsistent area-type contract and partial-route authz bypass pattern.
- **Evidence**: `fullstack/backend/src/services/_authz.py:22`, `fullstack/backend/src/services/_tx.py:1`, `fullstack/backend/src/routes/partials_routes.py:27`, `fullstack/backend/src/routes/admin_routes.py:154`, `fullstack/backend/migrations/001_initial_schema.sql:253`

### 4. Engineering Details and Professionalism

#### 4.1 Error handling, logging, validation, API design
- **Conclusion: Partial Pass**
- **Rationale**: Strong structured error handling and logging strategy; key weakness is authorization correctness in specific HTMX read endpoints and incomplete file-type hardening semantics.
- **Evidence**: `fullstack/backend/app.py:168`, `fullstack/backend/app.py:178`, `fullstack/backend/app.py:11`, `fullstack/backend/src/routes/helpers.py:70`, `fullstack/backend/src/routes/partials_routes.py:98`, `fullstack/backend/src/routes/member_routes.py:184`, `fullstack/backend/src/services/member_service.py:274`

#### 4.2 Product-like vs demo-like
- **Conclusion: Pass**
- **Rationale**: Delivery has real data model breadth, migration history, role workflows, and operational features.
- **Evidence**: `fullstack/backend/migrations/001_initial_schema.sql:20`, `fullstack/backend/migrations/005_price_overrides.sql:1`, `fullstack/backend/src/services/export_service.py:241`, `fullstack/backend/src/services/schedule_service.py:107`

### 5. Prompt Understanding and Requirement Fit

#### 5.1 Business goal and constraints fit
- **Conclusion: Partial Pass**
- **Rationale**: The business process is understood and largely implemented; role/store authorization edge cases and contract mismatches show some requirement-fit drift.
- **Evidence**: `fullstack/backend/src/services/ticket_service.py:247`, `fullstack/backend/src/services/export_service.py:460`, `fullstack/backend/src/services/qc_service.py:3`, `fullstack/backend/src/routes/partials_routes.py:27`, `README.md:30`

### 6. Aesthetics (frontend)

#### 6.1 Visual/interaction quality
- **Conclusion: Pass**
- **Rationale**: Functional and consistent operator UI with clear hierarchy, feedback states, and HTMX-driven updates. Visual polish is modest but coherent.
- **Evidence**: `fullstack/backend/templates/base.html:82`, `fullstack/backend/static/css/style.css:9`, `fullstack/backend/static/css/style.css:57`, `fullstack/backend/templates/tickets/index.html:36`
- **Manual verification note**: Responsive behavior and interaction polish still require browser validation.

## 5. Issues / Suggestions (Severity-Rated)

### 5.1 High

1. **Severity: High**
- **Title**: HTMX partial read endpoints can bypass store isolation for unpinned non-admin users
- **Conclusion**: Fail
- **Evidence**: `fullstack/backend/src/routes/partials_routes.py:27`, `fullstack/backend/src/routes/partials_routes.py:33`, `fullstack/backend/src/routes/partials_routes.py:98`, `fullstack/backend/src/routes/partials_routes.py:360`, `fullstack/backend/src/routes/partials_routes.py:417`, `fullstack/backend/src/routes/partials_routes.py:493`, `fullstack/backend/src/services/auth_service.py:166`, `fullstack/backend/src/services/auth_service.py:201`, `fullstack/backend/migrations/001_initial_schema.sql:22`
- **Impact**: If a non-admin user exists with `store_id=NULL`, they can provide `store_id` query params and read queue/board/export partial data across stores.
- **Minimum actionable fix**:
  - Enforce `store_id` required for all non-admin users in `AuthService.create_user`.
  - In `_store_id_for_actor`, honor query `store_id` **only** for `administrator`; otherwise require session store.
  - Add service-layer or helper-level store checks for all partial read endpoints.

### 5.2 Medium

2. **Severity: Medium**
- **Title**: Role-based least-privilege not enforced on UI pages and several read partials
- **Conclusion**: Partial Fail
- **Evidence**: `fullstack/backend/src/routes/ui_routes.py:42`, `fullstack/backend/src/routes/ui_routes.py:60`, `fullstack/backend/src/routes/partials_routes.py:98`, `fullstack/backend/src/routes/partials_routes.py:360`, `fullstack/backend/src/routes/partials_routes.py:417`, `fullstack/backend/src/routes/partials_routes.py:493`
- **Impact**: Any authenticated user can access page shells and some store-scoped read views outside their business role, increasing unnecessary data exposure.
- **Minimum actionable fix**:
  - Add role gates per UI page and read partial endpoint (or route through service methods that enforce role checks).

3. **Severity: Medium**
- **Title**: `area_type` contract mismatch across README/API/schema
- **Conclusion**: Fail
- **Evidence**: `README.md:30`, `fullstack/backend/src/routes/admin_routes.py:154`, `fullstack/backend/migrations/001_initial_schema.sql:253`, `fullstack/backend/src/enums/area_type.py:4`
- **Impact**: API/docs advertise `processing_station` but DB constraint rejects it, causing operator/admin setup failures and inconsistent behavior.
- **Minimum actionable fix**:
  - Align schema, enum, route validation, and docs to one canonical set of `area_type` values.

4. **Severity: Medium**
- **Title**: CSV upload validation is only extension/MIME + parser-based, not robust file-type verification
- **Conclusion**: Partial Fail
- **Evidence**: `fullstack/backend/src/routes/member_routes.py:184`, `fullstack/backend/src/routes/member_routes.py:186`, `fullstack/backend/src/services/member_service.py:274`, `fullstack/backend/src/services/member_service.py:278`
- **Impact**: Client-controlled MIME/filename checks are spoofable; malformed non-CSV payloads may still reach parser path before rejection.
- **Minimum actionable fix**:
  - Add stricter sniffing/validation (byte-level heuristics + strict CSV dialect checks), and document the exact acceptance policy.

### 5.3 Low

5. **Severity: Low**
- **Title**: Partial-route auth tests do not cover cross-store leakage scenarios
- **Conclusion**: Partial Fail
- **Evidence**: `API_tests/test_routes.py:955`, `API_tests/test_routes.py:958`, `API_tests/test_routes.py:970`, `API_tests/test_routes.py:974`, `API_tests/test_routes.py:978`
- **Impact**: A serious authz regression in HTMX read paths could pass CI unnoticed.
- **Minimum actionable fix**:
  - Add partial-route cross-store tests with admin vs store-pinned vs store-null users.

## 6. Security Review Summary

- **Authentication entry points: Pass**
  - Evidence: signed session cookie and validation in `fullstack/backend/src/routes/helpers.py:257`, `fullstack/backend/src/security/session_cookie.py:91`, auth login/session creation in `fullstack/backend/src/services/auth_service.py:221`.
- **Route-level authorization: Partial Pass**
  - Evidence: `@require_auth` broadly applied (`fullstack/backend/src/routes/ticket_routes.py:12`, `fullstack/backend/src/routes/export_routes.py:12`), but some UI/partials lack role constraints (`fullstack/backend/src/routes/ui_routes.py:42`, `fullstack/backend/src/routes/partials_routes.py:98`).
- **Object-level authorization: Partial Pass**
  - Evidence: strong service checks via `enforce_store_access` (`fullstack/backend/src/services/_authz.py:22`, used widely in services), but direct repository reads in partial routes bypass service-level object checks (`fullstack/backend/src/routes/partials_routes.py:101`, `fullstack/backend/src/routes/partials_routes.py:367`, `fullstack/backend/src/routes/partials_routes.py:424`, `fullstack/backend/src/routes/partials_routes.py:500`).
- **Function-level authorization: Partial Pass**
  - Evidence: role gates in sensitive services (`fullstack/backend/src/services/ticket_service.py:422`, `fullstack/backend/src/services/export_service.py:153`, `fullstack/backend/src/services/schedule_service.py:116`, `fullstack/backend/src/services/price_override_service.py:140`); weaker read-side UI/partial role boundaries.
- **Tenant / user data isolation: Partial Pass**
  - Evidence: core isolation helper and API cross-store tests (`fullstack/backend/src/services/_authz.py:22`, `API_tests/test_routes.py:1215`), but HTMX partial store-resolution bug remains (`fullstack/backend/src/routes/partials_routes.py:27`, `fullstack/backend/src/services/auth_service.py:201`).
- **Admin / internal / debug protection: Pass**
  - Evidence: admin-only checks on admin routes (`fullstack/backend/src/routes/admin_routes.py:23`, `fullstack/backend/src/routes/admin_routes.py:77`, `API_tests/test_routes.py:643`); no exposed debug/internal route set found in reviewed code.

## 7. Tests and Logging Review

- **Unit tests: Pass (static presence and breadth)**
  - Evidence: broad unit suite over schema/repos/services/security/hardening (`unit_tests/test_services.py:1`, `unit_tests/test_schema.py:45`, `unit_tests/test_security.py:1`, `unit_tests/test_hardening.py:1`).
- **API / integration tests: Pass (with targeted gaps)**
  - Evidence: auth, RBAC, TLS guard, cross-store API matrix, HTMX auth tests (`API_tests/test_routes.py:96`, `API_tests/test_routes.py:338`, `API_tests/test_routes.py:412`, `API_tests/test_routes.py:1154`, `API_tests/test_routes.py:955`).
- **Logging categories / observability: Pass**
  - Evidence: central app logging setup + rotating file fallback (`fullstack/backend/app.py:11`), audit trail service (`fullstack/backend/src/services/audit_service.py:38`), immutable audit table triggers (`fullstack/backend/migrations/001_initial_schema.sql:405`).
- **Sensitive-data leakage risk in logs/responses: Partial Pass**
  - Evidence: serializer strips ciphertext/iv and secret fields (`fullstack/backend/src/routes/helpers.py:77`), test guard (`API_tests/test_routes.py:254`), but some error logging includes raw exception strings (acceptable but watch operational verbosity) (`fullstack/backend/src/security/crypto.py:177`).

## 8. Test Coverage Assessment (Static Audit)

### 8.1 Test Overview
- **Unit tests exist**: Yes (`unit_tests/*` with pytest).
- **API tests exist**: Yes (`API_tests/test_routes.py`, `API_tests/test_health.py`).
- **Framework**: `pytest` (`API_tests/test_routes.py:9`, `unit_tests/test_services.py:9`).
- **Test entry points documented**: Yes (`README.md:42`, `README.md:56`, `run_tests.sh:8`).

### 8.2 Coverage Mapping Table

| Requirement / Risk Point | Mapped Test Case(s) | Key Assertion / Fixture / Mock | Coverage Assessment | Gap | Minimum Test Addition |
|---|---|---|---|---|---|
| Bootstrap 0→1 flow | `API_tests/test_routes.py:579` | Full admin→store→pricing→user→ticket chain | sufficient | none major | keep regression test |
| Pricing caps + variance threshold (max($5,5%)) | `unit_tests/test_services.py:215`, `unit_tests/test_services.py:244`, `unit_tests/test_services.py:249` | cap applied and threshold semantics asserted | sufficient | none major | add boundary exactly equal to threshold |
| Dual-control variance approval + password | `API_tests/test_routes.py:753`, `unit_tests/test_services.py:367` | wrong password forbidden, supervisor approval path | basically covered | more race cases at API layer | add concurrent approve API test |
| Dual-control refund/export/schedule/price-override authz | `API_tests/test_routes.py:784`, `API_tests/test_routes.py:809`, `API_tests/test_routes.py:854`, `API_tests/test_routes.py:1033` | unauth/unauthorized/stale/duplicate cases | basically covered | limited mixed-role edge matrix | add table-driven matrix per role/action |
| CSRF enforcement | `unit_tests/test_security.py:291` | POST blocked without token; valid token path | sufficient | none major | add CSRF test for HTMX partial POSTs |
| Session cookie tamper rejection | `API_tests/test_routes.py:385`, `unit_tests/test_services.py:3071` | tampered/forged cookie returns 401/None | sufficient | none major | keep |
| Cross-store API isolation | `API_tests/test_routes.py:1154` | store A actor blocked from store B resources | sufficient | does not include HTMX partial reads | add cross-store tests for `/ui/partials/*` |
| HTMX partial auth | `API_tests/test_routes.py:955` | only unauthenticated 401 and basic authenticated read | insufficient | missing store/role isolation checks | add authz matrix for partial endpoints |
| Sensitive fields not leaked in API responses | `API_tests/test_routes.py:254` | no ciphertext/iv in response keys | basically covered | no check for address fields | extend to store payloads if added |
| CSV import validation + hash | `unit_tests/test_services.py:1274`, `unit_tests/test_services.py:1287` | valid import and row-level validation errors | insufficient | no tests for MIME spoof, size limit, malformed binary payload | add API tests for `member_routes.import_csv` with file fixtures |

### 8.3 Security Coverage Audit
- **Authentication**: **Pass** (login, cookie tamper, session behavior tests present).
- **Route authorization**: **Partial Pass** (many role checks tested; read-side UI/partials under-tested).
- **Object-level authorization**: **Partial Pass** (API matrix exists, HTMX read paths not covered).
- **Tenant/data isolation**: **Partial Pass** (service/API strong coverage, but severe partial-route defect could remain undetected).
- **Admin/internal protection**: **Pass** (admin route protections tested; no debug/internal endpoints found).

### 8.4 Final Coverage Judgment
- **Partial Pass**
- Major risks covered: core auth, CSRF, cookie tampering, many dual-control routes, cross-store API access.
- Major uncovered risks: HTMX partial cross-store/role leakage and robust file-upload validation hardening. Severe defects in those areas could still pass current tests.

## 9. Final Notes
- This report is strictly static and evidence-based.
- No runtime success claims are made.
- The most urgent acceptance blocker-to-fix for moving from Partial Pass toward Pass is the HTMX partial authorization/store-context flaw, then schema/API contract alignment for service table area types.
