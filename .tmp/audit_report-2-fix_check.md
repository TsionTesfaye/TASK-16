# ReclaimOps Issue Recheck (From Scratch, Updated) — 2026-04-12

Scope: Static-only verification of the same five previously reported issues. No runtime execution, no Docker, no tests run, no code changes.

## Updated Verdict
- **5 / 5 issues are fixed.**
- The previously open item (partial-route cross-store test coverage) is now implemented.

## Issue-by-Issue Results

### 1) High — HTMX partial read endpoints bypass store isolation for unpinned non-admin users
- Status: **Fixed**
- Why:
  - Non-admin user creation now requires `store_id`.
  - Partial store resolution honors query `store_id` only for administrators.
  - Non-admin users with missing store context are denied.
- Evidence:
  - `fullstack/backend/src/services/auth_service.py:193`
  - `fullstack/backend/src/services/auth_service.py:195`
  - `fullstack/backend/src/routes/partials_routes.py:76`
  - `fullstack/backend/src/routes/partials_routes.py:87`
  - `fullstack/backend/src/routes/partials_routes.py:92`
  - `fullstack/backend/src/routes/partials_routes.py:169`
  - `fullstack/backend/src/routes/partials_routes.py:461`
  - `fullstack/backend/src/routes/partials_routes.py:521`
  - `fullstack/backend/src/routes/partials_routes.py:603`

### 2) Medium — Role-based least-privilege not enforced on UI pages and several read partials
- Status: **Fixed**
- Why:
  - UI pages now enforce per-page role allowlists.
  - Partial read endpoints now enforce per-endpoint role allowlists.
- Evidence:
  - `fullstack/backend/src/routes/ui_routes.py:9`
  - `fullstack/backend/src/routes/ui_routes.py:35`
  - `fullstack/backend/src/routes/ui_routes.py:80`
  - `fullstack/backend/src/routes/ui_routes.py:108`
  - `fullstack/backend/src/routes/ui_routes.py:128`
  - `fullstack/backend/src/routes/partials_routes.py:35`
  - `fullstack/backend/src/routes/partials_routes.py:63`
  - `fullstack/backend/src/routes/partials_routes.py:166`
  - `fullstack/backend/src/routes/partials_routes.py:458`
  - `fullstack/backend/src/routes/partials_routes.py:518`
  - `fullstack/backend/src/routes/partials_routes.py:600`
  - `fullstack/backend/src/routes/partials_routes.py:649`

### 3) Medium — `area_type` contract mismatch across README/API/schema
- Status: **Fixed**
- Why:
  - README, enum, route validation, and DB constraint are aligned on `intake_table` and `private_room`.
- Evidence:
  - `README.md:30`
  - `fullstack/backend/src/routes/admin_routes.py:154`
  - `fullstack/backend/src/routes/admin_routes.py:155`
  - `fullstack/backend/src/enums/area_type.py:4`
  - `fullstack/backend/migrations/001_initial_schema.sql:253`

### 4) Medium — CSV upload validation was not robust enough
- Status: **Fixed**
- Why:
  - Validation now rejects empty/binary files, checks UTF-8, validates CSV structure and required columns, and still computes SHA-256 hash.
- Evidence:
  - `fullstack/backend/src/routes/member_routes.py:196`
  - `fullstack/backend/src/routes/member_routes.py:200`
  - `fullstack/backend/src/services/member_service.py:270`
  - `fullstack/backend/src/services/member_service.py:289`
  - `fullstack/backend/src/services/member_service.py:295`
  - `fullstack/backend/src/services/member_service.py:302`
  - `fullstack/backend/src/services/member_service.py:305`
  - `fullstack/backend/src/services/member_service.py:314`
  - `fullstack/backend/src/services/member_service.py:323`
  - `fullstack/backend/src/services/member_service.py:344`

### 5) Low — Partial-route auth tests did not cover cross-store leakage scenarios
- Status: **Fixed**
- Why:
  - HTMX partial tests now include cross-store query override cases, admin cross-store access, null-store legacy non-admin denial, and role matrix assertions.
- Evidence:
  - `API_tests/test_routes.py:953`
  - `API_tests/test_routes.py:1034`
  - `API_tests/test_routes.py:1071`
  - `API_tests/test_routes.py:1085`
  - `API_tests/test_routes.py:1091`
  - `API_tests/test_routes.py:1097`
  - `API_tests/test_routes.py:1105`
  - `API_tests/test_routes.py:1122`
  - `API_tests/test_routes.py:1153`
  - `API_tests/test_routes.py:1162`
  - `API_tests/test_routes.py:1176`
  - `API_tests/test_routes.py:1214`

## Final Assessment
- All five previously reported issues are now resolved in the current codebase, based on static evidence.
- Residual boundary: runtime behavior is still not claimed here (by instruction), but code + test coverage for the previously open issue has been added.
