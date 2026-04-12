# design.md

## 1. System Overview

ReclaimOps Offline Operations Suite is a fully offline, role-based full-stack application for operating an in-store recyclable textiles buyback program with integrated receiving, quality control, batch traceability, customer-service intake, member administration, and operational reporting.

The system supports these primary roles:

- Front Desk Agent
- QC Inspector
- Host
- Shift Supervisor
- Operations Manager
- Administrator

The system uses:

- Frontend: server-rendered HTML with HTMX partial updates
- Backend: Flask decoupled REST-style and partial-render API
- Database: SQLite
- File storage: local disk for CSV imports/exports, generated reports, audit exports, local certificates, and runtime artifacts
- Background execution: local scheduler / Flask-side job runner
- Authentication: local username/password only
- Communication: in-order/local notification logging and workstation-assisted call tracking only

The platform must function without internet access. No external APIs, no third-party authentication, no SMS/email providers, no cloud queues, and no remote monitoring services are allowed.

Primary business capabilities:

- buyback ticket intake with instant estimated payout and promotional tier display
- receiving/QC workflow with actual weight capture and inspection outcomes
- variance confirmation and dual-control approval for sensitive payout adjustments
- table and private-room state management for intake/service areas
- offline notification center with templates, contact-attempt logging, call-preference handling, and retry reminders
- administrator management of departments, groups, club organizations, and member lifecycle
- operations dashboards for order volume, load factor, revenue, refund rate, and route/store filters
- supervisor approval for sensitive exports and sensitive operational actions
- quality sampling, quarantine, concession handling, and batch genealogy/recall reporting
- tamper-evident audit logging, masking, encryption-at-rest for sensitive fields, and signed session cookies with CSRF protection

---

## 2. Design Goals

- Full offline functionality with zero dependence on external services
- Clear separation between Flask routes, services, repositories, scheduler, storage, and HTMX templates
- Strict server-side validation, authorization, concurrency control, and payout correctness
- Deterministic workflows for tickets, QC, approvals, room/table state, member lifecycle, imports/exports, and recalls
- Strong traceability from procurement through QC, issuance, and finished goods
- Docker-first runtime that starts cleanly with `docker compose up`
- Explicit module boundaries so QA can measure implementation against the prompt
- No silent fallbacks, placeholder-only workflows, or UI-only enforcement
- Stable API and domain contracts so implementation, tests, templates, and docs remain aligned
- Future-proof structure so storage adapters or telephony integrations could evolve later without rewriting business rules

---

## 3. Scope, Deployment, and Trust Model

### 3.1 Deployment Modes

Supported deployment modes:

- single workstation
- local network deployment within one store or one operating environment

In both modes:

- Flask backend and SQLite DB run locally through Docker Compose
- the browser UI is served from the same local stack
- uploads, exports, reports, and traceability artifacts are stored on mounted local volumes
- all users authenticate against the local system
- backend time is the source of truth for eligibility windows, retry reminders, escalation checks, and audit timestamps

### 3.2 Trust Boundary

The system is offline, but browser clients are still treated as semi-trusted.

Trust rules:

- UI visibility is not security
- all business correctness is enforced in backend services
- all reads and writes must enforce role and store scope
- SQLite is never directly accessed by users
- client-supplied IDs, weights, payouts, statuses, dates, and permission assumptions are never trusted without backend verification

### 3.3 Time Standard

- all timestamps are stored in UTC
- UI renders dates/times in the configured business timezone and 12-hour time format
- pricing eligibility windows are stored and evaluated using explicit local business date/time rules
- scheduler jobs run relative to configured business-local time
- audit records store UTC plus sufficient local context for operator understanding where needed

### 3.4 Offline Operating Constraint

The system must remain usable with no internet connection.

Therefore:

- all authentication is local
- all call/contact tracking is local
- all notifications are local
- all exports/imports are local
- all reporting and traceability are local
- no core workflow may require remote connectivity

---

## 4. High-Level Architecture

### 4.1 Layered Architecture

```text
Browser UI (server-rendered HTML + HTMX)
    ↓
HTMX Endpoints / JSON API / CSRF Validation
    ↓
Flask Routes / Request DTO Parsing
    ↓
Application Services
    ↓
Repositories / Transaction + Locking Layer
    ↓
SQLite + Local File Storage
    ↓
Background Jobs / Scheduler / Export Generator / Recall Builder / QC Escalation Engine
```

### 4.2 Backend Modules

- auth
- users
- roles_permissions
- stores
- stations_and_tables
- tickets
- pricing_rules
- qc
- quarantine
- traceability
- notifications
- contact_attempts
- templates
- clubs_members
- imports_exports
- approvals
- audit
- reports
- settings
- scheduler
- storage
- crypto

### 4.3 Frontend / Template Modules

- login and session
- app shell / role-aware navigation
- front-desk ticket intake workspace
- receiving/QC workspace
- host table/room workspace
- notification center
- member and club administration workspace
- operations manager dashboards
- admin settings and security workspace
- shared partials, forms, badges, timelines, filters, tables, dialogs, and confirmation modals

### 4.4 Architecture Rules

Mandatory rules:

- routes only parse requests, invoke services, and return HTML partials or structured JSON responses
- services contain all business logic, validation, authorization, transitions, calculations, and approval rules
- repositories contain DB access only
- storage services contain file operations only
- every read path and write path enforces scope and masking rules
- all sensitive actions are auditable
- HTMX partials must reflect real backend state, not optimistic client assumptions
- tests must target service rules, API behavior, and end-to-end HTMX flows, not only happy-path form submissions

Forbidden:

- DB access in routes
- payout calculations in templates or browser-only code
- authorization enforced only in the UI
- service bypasses for “internal” use
- silent fallback from validated flow to permissive behavior
- partial completion of sensitive actions without explicit state/result

---

## 5. Repository and Package Layout

### 5.1 Required Root Structure

```text
prompt.md
questions.md
docs/
  design.md
  api-spec.md
fullstack/
  README.md
  docker-compose.yml
  run_tests.sh
  frontend/
  backend/
  unit_tests/
  API_tests/
  storage/
```

### 5.2 Backend Layout

```text
backend/
  app.py
  config/
  migrations/
  templates/
  static/
  src/
    routes/
    dto/
    models/
    enums/
    exceptions/
    repositories/
    services/
    scheduler/
    storage/
    audit/
    reporting/
    security/
    utils/
```

### 5.3 Frontend / Template Layout

```text
frontend/
  templates/
    layouts/
    partials/
    pages/
  static/
    css/
    js/
```

### 5.4 Project Structure Principles

- each module has clear ownership and API boundaries
- no giant mixed-responsibility files
- DTOs, services, partials, API tests, and docs must stay aligned
- runtime, tests, and README must use the same commands and ports
- storage directories must be explicit and Docker-mounted
- HTMX partial endpoints must correspond to real service flows and not exist as dead endpoints

---

## 6. Domain Model

### 6.1 Store

Fields:

- id
- code
- name
- route_code_nullable
- address_ciphertext
- address_iv
- phone_ciphertext
- phone_iv
- is_active
- created_at
- updated_at

Rules:

- every operational record belongs to one store
- inactive stores remain queryable for history and reporting but cannot receive new tickets or room/table activity
- phone/address are masked by default and encrypted at rest

### 6.2 User

Fields:

- id
- store_id_nullable
- username
- password_hash
- display_name
- role
- is_active
- is_frozen
- password_changed_at
- created_at
- updated_at

Rules:

- usernames are unique
- passwords are salted and hashed
- frozen users cannot authenticate or execute critical actions
- supervisor approval must always involve a different user than the initiating actor

### 6.3 UserSession

Fields:

- id
- user_id
- session_nonce
- cookie_signature_version
- csrf_secret
- client_device_id
- issued_at
- expires_at
- last_seen_at
- revoked_at_nullable

Rules:

- sessions use signed, time-limited cookies
- anti-replay nonce is bound to session
- CSRF protection applies to all state-changing requests
- expired or revoked sessions are terminal and must not be reused

### 6.4 BuybackTicket

Fields:

- id
- store_id
- created_by_user_id
- customer_name
- customer_phone_ciphertext_nullable
- customer_phone_iv_nullable
- customer_phone_last4_nullable
- customer_phone_preference
- clothing_category
- condition_grade
- estimated_weight_lbs
- actual_weight_lbs_nullable
- estimated_base_rate
- estimated_bonus_pct
- estimated_payout
- estimated_cap_applied
- actual_base_rate_nullable
- actual_bonus_pct_nullable
- final_payout_nullable
- final_cap_applied_nullable
- variance_amount_nullable
- variance_pct_nullable
- status
- qc_result_nullable
- qc_notes_nullable
- current_batch_id_nullable
- created_at
- updated_at
- completed_at_nullable
- refunded_at_nullable

Customer phone preference enum:

- calls_only
- standard_calls

Status enum:

- intake_open
- awaiting_qc
- variance_pending_confirmation
- variance_pending_supervisor
- completed
- refunded
- canceled

Rules:

- estimated payout is computed at intake
- final payout is computed after QC actual weight and inspection
- completion requires QC completion and any required variance approval
- refunded and canceled are terminal
- ticket completion and refund actions are audited with before/after values

### 6.5 PricingRule

Fields:

- id
- store_id_nullable
- category_filter_nullable
- condition_grade_filter_nullable
- base_rate_per_lb
- bonus_pct
- min_weight_lbs_nullable
- max_weight_lbs_nullable
- max_ticket_payout
- max_rate_per_lb
- eligibility_start_local
- eligibility_end_local
- is_active
- priority
- created_at
- updated_at

Rules:

- rules are evaluated by deterministic priority order
- overlapping rules are allowed only if priority resolves them deterministically
- eligibility windows use MM/DD/YYYY and 12-hour local time
- per-lb cap and per-ticket cap are enforced after bonus calculation
- inactive rules remain in history but are not used for new calculations

### 6.6 PricingCalculationSnapshot

Fields:

- id
- ticket_id
- calculation_type
- base_rate_per_lb
- input_weight_lbs
- gross_amount
- bonus_pct
- bonus_amount
- capped_amount
- cap_reason_nullable
- applied_rule_ids_json
- created_at

Calculation type enum:

- estimated
- actual

Rules:

- each ticket stores both estimated and actual calculation snapshots
- snapshots are immutable once written
- sensitive adjustments must reference a prior snapshot for auditability

### 6.7 VarianceApprovalRequest

Fields:

- id
- ticket_id
- requested_by_user_id
- approver_user_id_nullable
- variance_amount
- variance_pct
- threshold_amount
- threshold_pct
- confirmation_note
- status
- password_confirmation_used
- expires_at
- created_at
- approved_at_nullable
- rejected_at_nullable
- executed_at_nullable

Status enum:

- pending
- approved
- rejected
- expired
- executed

Rules:

- variance approval is required when payout change is more than 5% or $5.00, whichever is higher
- requester and approver must be different users
- approved requests are one-time-use only
- expired requests cannot be executed later
- approval cascade must unblock ticket completion exactly once

### 6.8 QCInspection

Fields:

- id
- ticket_id
- inspector_user_id
- actual_weight_lbs
- lot_size
- sample_size
- nonconformance_count
- inspection_outcome
- quarantine_required
- notes_nullable
- created_at
- updated_at

Inspection outcome enum:

- pass
- fail
- pass_with_concession

Rules:

- sample size = max(10% of lot size, 3) unless escalation to 100% applies
- two nonconformances in one business day escalate the day’s inspections to 100%
- pass_with_concession requires supervisor sign-off before ticket completion
- fail outcomes may create quarantine records

### 6.9 QuarantineRecord

Fields:

- id
- ticket_id
- batch_id
- created_by_user_id
- disposition
- concession_signed_by_nullable
- due_back_to_customer_at_nullable
- notes_nullable
- created_at
- resolved_at_nullable

Disposition enum:

- return_to_customer
- scrap
- concession_acceptance

Rules:

- return_to_customer must preserve a 7-day deadline
- concession_acceptance requires supervisor sign-off
- quarantine must resolve before associated material can move further in traceability chain

### 6.10 Batch

Fields:

- id
- store_id
- batch_code
- source_ticket_id_nullable
- status
- procurement_at_nullable
- receiving_at_nullable
- issued_at_nullable
- finished_goods_at_nullable
- created_at
- updated_at

Status enum:

- procured
- received
- quarantined
- issued
- finished
- recalled
- scrapped
- returned

Rules:

- batch traceability is append-only across lifecycle events
- quarantine or recall status blocks further issuance until disposition rules are satisfied
- a batch may be linked to one or more tickets through lineage records when operationally needed

### 6.11 BatchGenealogyEvent

Fields:

- id
- batch_id
- parent_batch_id_nullable
- child_batch_id_nullable
- event_type
- actor_user_id
- location_context_nullable
- created_at
- metadata_json_nullable

Event type enum:

- procured
- received
- inspected
- quarantined
- dispositioned
- issued
- transformed
- finished_goods
- recalled

Rules:

- genealogy is immutable
- enough data must exist to produce recall lists by batch and date
- events must preserve operator identity and operational context

### 6.12 RecallRun

Fields:

- id
- store_id_nullable
- requested_by_user_id
- batch_filter_nullable
- date_start_nullable
- date_end_nullable
- result_count
- output_path_nullable
- created_at

Rules:

- recall lists are generated from genealogy and date filters
- all recall runs are auditable
- exports respect authorization and optional watermark/attribution policy

### 6.13 ServiceTable

Fields:

- id
- store_id
- table_code
- area_type
- merged_into_id_nullable
- is_active
- created_at
- updated_at

Area type enum:

- intake_table
- private_room

Rules:

- inactive tables/rooms remain in history but cannot receive new activity
- merged tables become logically unavailable while merged
- transfer and merge operations are audited

### 6.14 TableSession

Fields:

- id
- store_id
- table_id
- opened_by_user_id
- current_state
- merged_group_code_nullable
- current_customer_label_nullable
- created_at
- updated_at
- closed_at_nullable

State enum:

- available
- occupied
- pre_checkout
- cleared

Rules:

- only valid state transitions are allowed
- clearing a session eventually returns the table to available through service logic
- state timeline is append-only for accountability

### 6.15 TableActivityEvent

Fields:

- id
- table_session_id
- actor_user_id
- event_type
- before_state_nullable
- after_state_nullable
- notes_nullable
- created_at

Event type enum:

- opened
- occupied
- merged
- transferred
- pre_checkout
- cleared
- reopened
- released

Rules:

- every visible table/room change creates an activity event
- events drive the accountability timeline shown in the UI

### 6.16 NotificationTemplate

Fields:

- id
- store_id_nullable
- template_code
- name
- body
- event_type
- is_active
- created_at
- updated_at

Template code examples:

- accepted
- rescheduled
- arrived
- completed
- refunded

Rules:

- templates are text-only and local
- template rendering must validate required placeholders before logging a message
- inactive templates remain queryable in history but cannot be used for new messages

### 6.17 TicketMessageLog

Fields:

- id
- ticket_id
- template_id_nullable
- actor_user_id
- message_body
- contact_channel
- call_attempt_status_nullable
- retry_at_nullable
- created_at

Contact channel enum:

- logged_message
- phone_call

Call attempt status enum:

- not_applicable
- succeeded
- failed
- voicemail
- no_answer

Rules:

- no SMS or email channels exist in the initial version
- failed contact attempts may schedule retry reminders
- all customer communication is logged against the ticket

### 6.18 ClubOrganization

Fields:

- id
- name
- department_nullable
- route_code_nullable
- is_active
- created_at
- updated_at

Rules:

- clubs and partner organizations are admin-managed
- inactive organizations remain in member history but cannot receive new assignments

### 6.19 Member

Fields:

- id
- club_organization_id
- full_name
- status
- joined_at_nullable
- left_at_nullable
- transferred_at_nullable
- current_group_nullable
- created_at
- updated_at

Status enum:

- active
- inactive
- transferred
- left

Rules:

- member lifecycle changes are append-only through history events
- bulk CSV import must preserve validation errors explicitly
- export respects scope and optional approval requirements

### 6.20 MemberHistoryEvent

Fields:

- id
- member_id
- actor_user_id
- event_type
- before_json_nullable
- after_json_nullable
- created_at

Event type enum:

- joined
- left
- transferred
- reactivated
- imported

Rules:

- member history is immutable
- lifecycle changes must always create history records

### 6.21 ExportRequest

Fields:

- id
- requested_by_user_id
- export_type
- filter_json
- watermark_enabled
- attribution_text_nullable
- approval_required
- approver_user_id_nullable
- status
- output_path_nullable
- created_at
- completed_at_nullable

Status enum:

- pending
- approved
- rejected
- completed
- expired

Rules:

- sensitive exports may require supervisor approval
- watermark and user attribution are applied at export generation time when enabled
- approved exports are one-time executable and auditable

### 6.22 AuditLog

Fields:

- id
- actor_user_id_nullable
- actor_username_snapshot
- action_code
- object_type
- object_id
- before_json_nullable
- after_json_nullable
- client_device_id_nullable
- tamper_chain_hash
- created_at

Rules:

- audit log is immutable
- tamper-evident chain hash must make deletion or mutation detectable
- security-sensitive, pricing-sensitive, and QC-sensitive actions must always be logged

### 6.23 Settings

Fields:

- id
- store_id_nullable
- business_timezone
- variance_pct_threshold
- variance_amount_threshold
- max_ticket_payout
- max_rate_per_lb
- qc_sample_pct
- qc_sample_min_items
- qc_escalation_nonconformances_per_day
- export_requires_supervisor_default
- file_upload_max_mb
- created_at
- updated_at

Defaults:

- variance percent threshold = 5
- variance amount threshold = 5.00
- max ticket payout = 200.00
- max rate per lb = 3.00
- qc sample percent = 10
- qc sample min items = 3
- qc escalation threshold = 2
- file upload max = 5 MB

Rules:

- store-level settings may override global defaults where permitted
- all calculations and validations must source settings from backend services, not templates

---

## 7. Role Model and Authorization

### 7.1 Roles

#### Front Desk Agent

Capabilities:

- create buyback tickets
- capture intake data
- view estimated payout
- log ticket messages and call attempts
- cannot approve sensitive variances or exports

#### QC Inspector

Capabilities:

- record actual weight
- complete inspections
- create quarantine records
- update batch genealogy events related to QC
- cannot complete variance-approved payouts without required approval chain

#### Host

Capabilities:

- open, merge, transfer, pre-checkout, and clear tables/rooms
- view table activity timelines
- cannot modify payout, QC, or export policies

#### Shift Supervisor

Capabilities:

- approve sensitive payout variance adjustments
- sign off on concession acceptance
- approve sensitive exports when required
- cannot self-approve own initiating actions

#### Operations Manager

Capabilities:

- view dashboards and reports
- export operational data within scope
- review refund rate, revenue, load factor, order volume
- may approve some export or schedule-sensitive actions if policy allows

#### Administrator

Capabilities:

- manage users, settings, stores, templates, clubs, member imports/exports, certificates, and security controls
- view audit logs and traceability artifacts
- run or review recall/export jobs
- cannot bypass audit or dual-control requirements

### 7.2 Authorization Rules

- all records are store-scoped unless explicitly global/admin-managed
- all reads enforce scope, not only writes
- sensitive data reveals require explicit permission and audited reveal path
- client-supplied store ownership filters are never trusted
- service layer is the final authorization authority

### 7.3 Permission Strategy

Authorization decisions combine:

- authenticated user role
- store scope
- object ownership where relevant
- current entity state
- approval policy requirements

Examples:

- Front Desk Agent can create ticket but cannot approve variance
- QC Inspector can record actual weight but cannot self-approve concession
- Shift Supervisor can approve sensitive adjustment only if they are not the requester
- Operations Manager can export within scope only when required approvals are satisfied

---

## 8. Authentication, Sessions, and Security

### 8.1 Authentication Model

- username/password only
- salted password hashing
- signed cookie-based sessions
- no OAuth, no SSO, no external identity provider

Password Policy:

- minimum length: 12 characters
- failed login attempts: 5
- lockout duration: 15 minutes
- passwords stored using bcrypt or equivalent

### 8.2 Session Rules

- signed, time-limited cookies
- anti-replay session nonce
- CSRF token required for all mutating requests
- session expiry and revocation enforced on backend

Session Lifetime:

- max duration: 8 hours
- idle timeout: 30 minutes
- configurable via Settings

### 8.3 Account Freeze Rules

- frozen users cannot log in
- frozen users cannot execute critical pricing, QC, export, or admin actions
- freeze/unfreeze actions are auditable

### 8.4 Sensitive Data and Encryption at Rest

Sensitive fields include:

- phone numbers
- addresses
- optionally partner/member contact details

Rules:

- masked by default in UI and exports unless explicitly revealed
- encrypted at rest using an application-managed key stored outside the SQLite database file
- secrets and keys must never be returned in API responses

### 8.4.1 Encryption Key Management

Rules:

- encryption key stored outside SQLite DB
- default path: `/run/secrets/reclaim_ops_key`
- mounted via Docker volume or secret

Startup behavior:

- if key file exists → load
- if not → generate 256-bit random key and persist

Constraints:

- key must never be stored in DB
- key must never be returned in API responses

Key Loss:

- loss of key results in permanent loss of encrypted fields
- system must log warning on startup if key regenerated

Rotation:

- not supported in v1 (explicitly)
- future extension possible

Docker Requirement:

- docker-compose must mount this path explicitly

### 8.5 TLS and Local Certificates

- TLS is required on the local network
- certificates are locally managed and stored outside application code
- certificate metadata may be admin-visible, but private material must remain protected

### 8.6 Security Boundaries

- backend is authoritative for all pricing, QC, and approval decisions
- route guards are not sufficient by themselves
- object-level checks are mandatory
- no “internal-only” endpoint may skip auth/authorization
- input validation must protect against XSS, injection, and malformed HTMX requests

---

## 9. Ticket Intake, Pricing, and Variance Design

### 9.1 Ticket Intake

Flow:

1. Front Desk Agent opens buyback ticket
2. captures category, condition grade, estimated weight
3. pricing engine computes estimated payout and promotional tier
4. ticket enters `awaiting_qc` once saved

Rules:

- estimated payout must show cap application clearly
- pricing display must be backed by persisted calculation snapshot
- estimated data cannot be silently overwritten without audit trail

### 9.2 Pricing Engine

Pricing evaluation order:

1. determine applicable rule set by priority and eligibility window
2. compute gross amount from base rate × weight
3. apply promotional bonus percentage
4. apply per-lb cap and ticket cap
5. persist calculation snapshot and rule references

Rules:

- all eligibility is evaluated in configured business-local time
- rule conflicts must fail loudly or resolve deterministically by priority
- both estimated and actual calculations are retained

### 9.3 Variance Threshold Rule

Variance approval is required when:

difference_amount > controlling_threshold

Where:

- difference_amount = |final_payout - estimated_payout|
- percentage_difference = difference_amount / estimated_payout

Compute:

- amount_threshold = configured amount threshold (default $5.00)
- percent_threshold_amount = estimated_payout * configured percent threshold (default 5%)

controlling_threshold = max(amount_threshold, percent_threshold_amount)

Approval is required if:

difference_amount > controlling_threshold

#### Example

If:
- estimated = $100
- actual = $108

Then:
- difference = $8
- percent threshold = $5
- amount threshold = $5

controlling threshold = $5

Since $8 > $5 → approval required

Rules:

- this is a single-threshold comparison (NOT OR logic)
- backend must compute and persist both thresholds and controlling threshold

### 9.4 Ticket State Machine

Allowed transitions:

- intake_open -> awaiting_qc
- awaiting_qc -> variance_pending_confirmation
- awaiting_qc -> completed
- variance_pending_confirmation -> variance_pending_supervisor
- variance_pending_supervisor -> completed
- completed -> refunded
- intake_open -> canceled
- awaiting_qc -> canceled

Forbidden:

- direct completion when QC or approval prerequisites are unmet
- self-approval on variance
- reuse of already executed approval

Additional transitions:

- variance_pending_confirmation → canceled
- variance_pending_supervisor → canceled

Rules:

- cancellation from variance states requires supervisor authorization
- cancellation must include reason note
- cancellation must not reuse approval tokens

### 9.5 Refund Workflow

Refunds are supported as a post-completion corrective action and are considered a sensitive operation requiring dual-control approval.

#### 9.5.1 Refund Initiation

Rules:

- Only completed tickets may be refunded
- Refunds can be:
  - full refund (default)
  - partial refund (explicitly specified amount)
- Only Front Desk Agent, Operations Manager, or Administrator may initiate
- Refund initiation creates a pending refund request (not immediately executed)

#### 9.5.2 Refund Amount Rules

- Full refund = final_payout
- Partial refund:
  - must be ≤ final_payout
  - must be ≥ 0
  - must include a mandatory reason note
- Refund amount must be explicitly stored

#### 9.5.3 Dual-Control Requirement

Refunds always require dual-control approval:

- initiating user != approving user
- Shift Supervisor (or higher role) must approve
- approval requires password re-entry
- approval is one-time-use only

#### 9.5.4 Ticket State Transition

Allowed:

- completed → refund_pending_supervisor
- refund_pending_supervisor → refunded

Rules:

- refund cannot bypass approval
- rejected refund returns ticket to completed

#### 9.5.5 Traceability Impact

- refund does NOT delete or mutate batch genealogy
- if material already entered batch:
  - system logs "financial reversal only"
- if material still in store:
  - optional quarantine/return flow may be triggered

#### 9.5.6 Audit Requirements

Refund must log:

- actor (initiator + approver)
- refund amount
- before: final_payout
- after: refunded_amount
- reason
- timestamp

### 9.6 Price Override Policy

Manual price overrides are NOT supported.

Rules:

- all payouts must be generated exclusively by the pricing engine
- operators cannot manually change base rate, bonus, or final payout
- any discrepancy must go through:
  - QC actual weight update
  - variance approval workflow

Rationale:

- ensures deterministic pricing
- eliminates need for separate override approval flow
- satisfies dual-control requirement via variance approval system

---

## 10. QC, Sampling, Quarantine, and Traceability Design

### 10.1 QC Sampling

Default rules:

- inspect 10% of lot size
- minimum 3 items per lot
- escalate to 100% when two nonconformances are found in one business day

Rules:

- escalation is store-local and business-day scoped
- escalation status is computed from persisted QC outcomes, not UI counters
- sample size must be persisted on inspection record for auditability

Escalation Scope:

- applies per store
- applies per business day

Reset Rule:

- resets automatically at start of next business day

Notes:

- concession acceptance does NOT reduce nonconformance count
### 10.2 QC Outcomes

Supported outcomes:

- pass
- fail
- pass_with_concession

Rules:

- `pass_with_concession` requires supervisor sign-off
- `fail` may trigger quarantine automatically
- all QC decisions are auditable and linked to ticket/batch genealogy

### 10.3 Quarantine Workflow

Flow:

1. QC creates quarantine record when needed
2. disposition selected:
   - return_to_customer
   - scrap
   - concession_acceptance
3. if concession acceptance, supervisor sign-off required
4. genealogy and ticket resolution updated accordingly

Rules:

- return-to-customer disposition must track 7-day deadline
- quarantined material cannot be issued until resolved
- all disposition outcomes create genealogy events

### 10.4 Batch Traceability

The system must support traceability from:

- procurement
- receiving
- inspection
- quarantine/disposition
- issuance
- finished goods

Rules:

- genealogy is append-only
- recall generation must work by batch and date
- all chain events preserve actor identity and context

---

## 11. Table / Room Operations Design

### 11.1 State Model

States:

- available
- occupied
- pre_checkout
- cleared

Allowed transitions:

- available -> occupied
- occupied -> pre_checkout
- occupied -> cleared
- pre_checkout -> cleared
- cleared -> available

Rules:

- invalid transitions must fail
- merged sessions must preserve visible state and accountability timeline
- transfer operations must keep event continuity

### 11.2 Merge and Transfer

Rules:

- only active sessions may be merged
- already merged tables cannot be merged again independently
- transfer preserves timeline and current logical state
- all operations are audited and shown in activity timeline

---

## 12. Notification Center and Contact Attempt Design

### 12.1 Offline Communication Model

The system supports:

- logged in-order messages
- workstation one-tap dialing assist
- call-preference tracking
- delivery-attempt logging
- retry reminders

Not supported:

- SMS
- email
- external push services

### 12.2 Templates

Supported examples:

- accepted
- rescheduled
- arrived
- completed
- refunded

Rules:

- template placeholder validation occurs server-side before logging
- template rendering failures must block message creation explicitly

### 12.3 Contact Attempt Lifecycle

Rules:

- failed attempt may create retry reminder
- retry reminders are scheduler-driven and idempotent
- customer “calls only” preference must influence available actions shown to staff
- all attempts are logged to ticket history

---

## 13. Club, Department, and Member Administration Design

### 13.1 Club / Department Scope

Administrators manage:

- club organizations
- departments
- groups
- member join/leave/transfer lifecycle

Rules:

- lifecycle changes are immutable through history events
- current status is derived from latest valid lifecycle event
- imports and exports must honor role/scope controls

### 13.2 CSV Import / Export

Rules:

- CSV only
- max 5 MB
- file type, extension, and hashing validated before processing
- import must produce explicit row-level validation results
- bulk operations are auditable
- exports may require supervisor approval and optional watermark/attribution

---

## 14. Reporting, Exports, and Operations Metrics

### 14.1 Core Reports

Operations Managers view:

- order volume
- load factor
- revenue
- refund rate

Filters:

- date range
- route
- store

Rules:

- filters must be scope-aware
- export uses same validated service-layer data as dashboard reads
- no report calculation may be reimplemented ad hoc in template code

Metric Definitions:

- order_volume = count(completed tickets)
- revenue = sum(final_payout for completed tickets)
- refund_rate = count(refunded tickets) / count(completed + refunded)
- load_factor = completed_tickets / configured_capacity_per_day

### 14.2 Export Approval

Sensitive exports may require:

- second-user supervisor approval
- watermark application
- per-user attribution

Rules:

- approved export requests are one-time executable
- exports are auditable
- unauthorized exports must fail before generation

### 14.3 Report Consistency

- dashboard, export, and printed/exported values must come from the same service-layer calculations
- out-of-scope filters must be rejected
- masked data remains masked unless explicit reveal permission is satisfied

---

## 15. Audit, Tamper Evidence, and Diagnostics

### 15.1 Audit Coverage

Audit logs must cover:

- authentication events
- ticket creation and completion
- payout adjustments
- QC results and quarantine decisions
- table/room lifecycle changes
- message logging and reveal actions
- member lifecycle changes
- imports/exports
- report generation
- settings changes
- recall generation

### 15.2 Tamper-Evident Logging

Rules:

- audit entries are append-only
- each entry stores a tamper-chain hash
- update/delete of audit rows is forbidden
- before/after values must be sufficient for operator review

### 15.3 Logging Rules

- structured logs only
- no raw passwords, encryption keys, or unmasked sensitive fields
- logs stored locally and exportable only within authorization rules

---

## 16. Backup, Storage, and Import/Export Safety

### 16.1 File Upload Rules

- CSV only
- max 5 MB
- extension, MIME, and content checks required
- cryptographic hash stored for integrity
- invalid files rejected before storage

Watermark Implementation:

- prepend CSV with comment rows:

# EXPORT_ID: <id>
# GENERATED_BY: <username>
# TIMESTAMP: <utc>
# CLASSIFICATION: CONFIDENTIAL

Attribution:

- include exporting user in metadata rows

### 16.2 Export / Generated Files

Local generated files may include:

- CSV exports
- report files
- audit exports
- recall outputs

Rules:

- file names must be application-generated and safe
- watermark/attribution applied during generation where configured
- file downloads must enforce authorization and object-level access

### 16.3 Backup and Restore

If backup/restore is included in initial implementation:

- backup scope includes SQLite DB and required local artifacts
- backup integrity must be explicit
- restore preview must be read-only if implemented
- restore actions must be authorized and audited
- unsafe archive paths must be rejected on extraction

---

## 17. Data Integrity and Concurrency Rules

### 17.1 Core Integrity Rules

- no cross-store references where not allowed
- no orphan approval records
- no orphan quarantine or genealogy records
- ticket, QC, and batch relationships must remain valid
- no sensitive action may partially mutate business state without explicit result

### 17.2 Concurrency Rules

To prevent duplicate execution and approval replay:

- approval execution must use atomic state transition
- critical actions must use DB transactions
- repeated form submission must be idempotent where appropriate
- merged/transfer room actions must fail cleanly under stale state

### 17.3 No Silent Conflict Handling

If an action fails because of:

- stale ticket state
- already-used approval
- invalid QC escalation context
- duplicate import/export request
- out-of-scope access
- conflicting room/table state

the system must return an explicit structured result rather than silently adjusting behavior

---

## 18. API Design Principles

### 18.1 API Style

- REST-style JSON APIs plus HTMX partial endpoints
- DTO-based request/response contracts
- standard HTTP status codes
- structured JSON errors for non-partial endpoints

Error shape:

```json
{
  "code": 403,
  "message": "Forbidden",
  "details": null
}
```

### 18.2 Security and Validation

- authenticated routes require valid signed session
- CSRF required on mutating endpoints
- service layer validates role, scope, and object access
- request DTO validation handles shape and format
- business rules are enforced in services
- controllers never trust client-supplied totals, statuses, or scope data

### 18.3 API Coverage Areas

- auth/session
- tickets/pricing/qc
- variance approvals
- tables/rooms
- notifications/contact attempts
- clubs/members/imports/exports
- reports/recalls
- audit/settings/security

### 18.4 Contract Stability

- DTOs are part of the contract
- schema drift across Flask routes, templates, tests, and docs is a defect
- no silent field additions/removals without coordinated update

---

## 19. Frontend UX and State Design

### 19.1 App Shell

Must provide:

- role-aware navigation
- current session/user context
- clear module separation
- loading and error boundaries
- confirmation modals for sensitive actions

### 19.2 Required States

All major views must support:

- loading
- empty
- validation feedback
- success feedback
- permission denied
- recoverable error state
- disabled/submitting state for critical actions

### 19.3 UI-Service Parity

Rules:

- UI should hide or disable impossible actions when state/permissions are already known
- backend remains the final authority
- estimated payout display is informational but must reflect persisted calculation output
- HTMX partial refreshes must always re-render from authoritative backend state

### 19.4 Accessibility

- semantic buttons and form controls
- keyboard support for dialogs and menus
- visible current-state indicators
- clear disabled/loading states
- no dead-end flows for core buyback or service-intake tasks

---

## 20. Scheduler and Background Jobs

### 20.1 Job Types

- retry reminder scheduling
- QC escalation day checks
- quarantine deadline reminders
- report generation
- export expiration cleanup
- audit/recall support jobs where needed

### 20.2 Startup Reconciliation

On startup, the system should:

- restore pending reminder schedule safely
- detect expired approval/export requests
- continue incomplete safe jobs idempotently
- report prior job failures explicitly

### 20.3 Job Idempotency

Jobs must not create duplicate business artifacts for the same logical window.

Examples:

- one retry reminder per failed contact attempt window
- one execution of an approved export request
- one QC escalation application per day/store threshold crossing

### 20.4 Scheduler Failure Rules

- job failure must be persisted and visible
- no background job may partially mutate sensitive state without explicit completion/failure status
- timezone handling must use configured business timezone accurately

### 20.5 Schedule Adjustment Control

Schedule adjustments refer to modifications of system-managed scheduled tasks, including:

- retry reminder timing
- quarantine deadline triggers
- report generation schedules

Rules:

- any manual modification of:
  - scheduled execution time
  - retry timing
  - deadline override
requires dual-control approval

Flow:

1. initiating user requests schedule change
2. system creates ScheduleAdjustmentRequest
3. second user (supervisor) approves with password
4. scheduler applies change atomically

Constraints:

- requester != approver
- approval is single-use
- all changes are audited with before/after schedule values

---

## 21. Error Handling Strategy

- validation failures return user-safe structured messages
- unauthorized and forbidden actions return 401/403
- missing records return 404 where appropriate
- conflicts and stale-state issues return 409 where appropriate
- pricing, QC, export, traceability, and storage failures surface explicit status and message

No silent fallbacks:

- no ticket completion without required QC/approval
- no export generated with missing approval when required
- no reveal action without audit trail
- no file import accepted without validation
- no unsafe archive or path extraction silently allowed

---

## 22. Testing Strategy

### 22.1 Unit Tests

Cover:

- pricing calculation order and cap logic
- variance threshold evaluation
- QC sample size calculation and escalation logic
- ticket state machine
- table/room state machine
- approval one-time-use logic
- tamper-chain hash generation
- masking and reveal helpers
- CSV validation and hashing
- timezone/eligibility window evaluation

### 22.2 API Tests

Cover:

- login success/failure/frozen-user handling
- HTMX partial and JSON endpoint auth
- ticket creation and payout estimation
- QC update and variance threshold behavior
- supervisor approval and self-approval rejection
- table merge/transfer/state transition rules
- notification logging and retry reminders
- member CSV import/export auth and validation
- report export approval gating
- recall generation and scope enforcement

### 22.3 Frontend / Integration Tests

Cover:

- role-aware navigation
- ticket intake form and instant estimate refresh
- QC variance approval flow
- host room/table interactions
- message logging and retry reminder display
- admin member import/export UI
- operations dashboard filters and export UI
- masked-field reveal flows
- error and permission-denied states

### 22.4 End-to-End Flows

Must include:

- first admin bootstrap
- Front Desk Agent creates ticket and sees estimated payout
- QC Inspector records actual weight and triggers variance approval
- Shift Supervisor approves variance with second-user password re-entry
- ticket completes and audit trail is generated
- Host opens, merges, transfers, and clears a table/room
- contact attempt fails and retry reminder is created
- member CSV import runs with row-level validation
- recall list generated by batch/date
- sensitive export runs with approval and watermark/attribution

### 22.5 Required Test Structure

At repository root:

- unit_tests/
- API_tests/
- run_tests.sh

Rules:

- tests are runnable through one command
- output must show clear pass/fail summary
- every regression fix must include a regression test
- tests must cover negative and authorization paths, not only happy flows

---

## 23. Docker and Runtime Design

### 23.1 Docker Compose Services

Required services:

- frontend/web
- backend
- sqlite-backed storage service or mounted DB volume

Optional mounts:

- exports volume
- uploads volume
- reports volume
- certificates volume
- logs volume

### 23.2 Canonical Startup

- `docker compose up`

Rules:

- no manual DB editing required
- no internet-required runtime setup
- no hidden environment assumptions
- runtime certificates/keys must be mounted or generated through documented bootstrap flow, not committed in repo

### 23.3 Bootstrap Path

On first clean startup:

- system checks Settings.bootstrap_completed flag

Bootstrap flow:

- executed only if bootstrap_completed = false
- uses atomic DB transaction:

  1. check no admin exists
  2. create admin user
  3. set bootstrap_completed = true

- commit transaction

Rules:

- if two requests race:
  - only one transaction succeeds
  - second fails due to constraint
- bootstrap route is permanently disabled once flag is true
- all bootstrap attempts are audited

---

## 24. Future Integration Readiness

The design is future-ready because:

- repositories isolate persistence
- services own workflows and calculations
- audit, pricing, QC, export, and recall modules are modular
- HTMX templates depend on DTOs and service output, not DB implementation
- local telephony or hardware integrations could be added later without rewriting ticket/QC core logic

---

## 25. Non-Negotiable Constraints

- no external APIs
- no mock-only production behavior
- all validation in services
- all reads enforce scope
- all writes enforce scope
- masking centralized and export-safe
- audit logs immutable and tamper-evident
- approval and export requests are one-time executable
- self-approval is forbidden
- sensitive fields encrypted at rest
- CSV only uploads/exports in allowed import/export flows
- file size max 5 MB where prompt requires
- HTMX partials must reflect real backend state
- Docker Compose is the canonical runtime path
