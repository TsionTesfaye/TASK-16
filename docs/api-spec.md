# ReclaimOps API Specification

**Base URL:** `https://localhost:5443` (TLS) or `http://localhost:5000` (dev mode)

---

## Table of Contents

1. [Authentication & Security](#authentication--security)
2. [Response Envelope](#response-envelope)
3. [Enums & Constants](#enums--constants)
4. [Endpoints](#endpoints)
   - [Health](#health)
   - [Auth](#auth)
   - [Tickets](#tickets)
   - [QC & Traceability](#qc--traceability)
   - [Tables](#tables)
   - [Notifications](#notifications)
   - [Members](#members)
   - [Exports & Metrics](#exports--metrics)
   - [Schedules](#schedules)
   - [Settings](#settings)
   - [Price Overrides](#price-overrides)
   - [Admin](#admin)
   - [UI Pages](#ui-pages)
   - [HTMX Partials](#htmx-partials)

---

## Authentication & Security

### Session Model

All API endpoints (except `/health`, `/api/auth/bootstrap`, `/api/auth/login`) require a valid session.

| Mechanism | Details |
|-----------|---------|
| Session cookie | `session_nonce` — HttpOnly, Secure, SameSite=Strict, HMAC-signed, 8h max |
| CSRF token | `csrf_token` cookie (JS-readable) — must be echoed in `X-CSRF-Token` header on POST/PUT/PATCH/DELETE |
| Password policy | 12+ characters |
| Account lockout | 5 failed attempts, 15-minute lockout |
| Session idle timeout | 30 minutes |
| Session max lifetime | 8 hours |

### Store Isolation

- Non-admin users are pinned to one `store_id` at creation time.
- API requests always use the session-bound `store_id` for non-admins — any client-supplied `store_id` is silently ignored.
- Administrators have no pinned store and must supply `store_id` explicitly where required.

### Roles (least to most privileged)

| Role | Value |
|------|-------|
| Front Desk Agent | `front_desk_agent` |
| QC Inspector | `qc_inspector` |
| Host | `host` |
| Shift Supervisor | `shift_supervisor` |
| Operations Manager | `operations_manager` |
| Administrator | `administrator` |

---

## Response Envelope

### Success

```json
{
  "data": { ... }
}
```

### Error

```json
{
  "error": {
    "code": 400,
    "message": "Human-readable error description"
  }
}
```

### Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 302 | Redirect (UI pages) |
| 400 | Validation error / bad request |
| 401 | Not authenticated |
| 403 | Forbidden (wrong role / cross-store) |
| 404 | Not found |

---

## Enums & Constants

### `user_role`
`front_desk_agent` | `qc_inspector` | `host` | `shift_supervisor` | `operations_manager` | `administrator`

### `ticket_status`
`intake_open` | `awaiting_qc` | `variance_pending_confirmation` | `variance_pending_supervisor` | `completed` | `refund_pending_supervisor` | `refunded` | `canceled`

### `inspection_outcome`
`pass` | `fail` | `pass_with_concession`

### `quarantine_disposition`
`return_to_customer` | `scrap` | `concession_acceptance`

### `batch_status`
`procured` | `received` | `quarantined` | `issued` | `finished` | `recalled` | `scrapped` | `returned`

### `table_state`
`available` | `occupied` | `pre_checkout` | `cleared`

### `area_type`
`intake_table` | `private_room`

### `contact_channel`
`logged_message` | `phone_call`

### `call_attempt_status`
`not_applicable` | `succeeded` | `failed` | `voicemail` | `no_answer`

### `customer_phone_preference`
`calls_only` | `standard_calls`

### `member_status`
`active` | `inactive` | `transferred` | `left`

### `export_request_status`
`pending` | `approved` | `rejected` | `completed` | `expired`

### `variance_approval_status`
`pending` | `approved` | `rejected` | `expired` | `executed`

---

## Endpoints

---

### Health

#### `GET /health`

No auth required.

**Response** `200`
```json
{"status": "ok"}
```

---

### Auth

#### `POST /api/auth/bootstrap`

Create the first administrator. Unauthenticated. Locks after first successful call.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `username` | string | yes | |
| `password` | string | yes | 12+ chars |
| `display_name` | string | yes | |

**Response** `201`
```json
{
  "data": {
    "message": "Bootstrap complete",
    "user": { "id": 1, "username": "...", "role": "administrator", ... }
  }
}
```

**Errors:** `400` validation, `403` already bootstrapped

---

#### `POST /api/auth/login`

Authenticate and create session.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `username` | string | yes | |
| `password` | string | yes | |
| `client_device_id` | string | no | Optional device identifier for audit |

**Response** `200`
```json
{
  "data": {
    "user": { "id": 1, "username": "...", "role": "...", "store_id": 1, ... },
    "session_id": 1,
    "csrf_token": "..."
  }
}
```

Sets cookies: `session_nonce` (HttpOnly), `csrf_token` (JS-readable).

**Errors:** `400` missing fields, `401` invalid credentials / frozen / inactive

---

#### `POST /api/auth/logout`

**Auth:** session + CSRF | **Roles:** any

Revokes session, deletes cookies.

**Response** `200`
```json
{"data": {"message": "Logged out"}}
```

---

#### `POST /api/auth/users`

**Auth:** session + CSRF | **Roles:** administrator

Create a new user account.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `username` | string | yes | |
| `password` | string | yes | 12+ chars |
| `display_name` | string | yes | |
| `role` | string | yes | See `user_role` enum |
| `store_id` | integer | conditional | Required for non-admin roles; omit for administrator |

**Response** `201` — serialized user object

**Errors:** `400` validation / missing store_id for non-admin, `403` non-admin caller

---

#### `POST /api/auth/users/<user_id>/freeze`

**Auth:** session + CSRF | **Roles:** administrator

Freeze an account (locks out, revokes all sessions).

**Response** `200` — user object with `is_frozen: true`

**Errors:** `400` user not found, `403` non-admin caller

---

#### `POST /api/auth/users/<user_id>/unfreeze`

**Auth:** session + CSRF | **Roles:** administrator

Unfreeze a previously frozen account.

**Response** `200` — user object with `is_frozen: false`

**Errors:** `400` user not found, `403` non-admin caller

---

### Tickets

#### `POST /api/tickets`

**Auth:** session + CSRF | **Roles:** any (service-layer role check per action)

Create a buyback ticket at intake.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `customer_name` | string | yes | |
| `clothing_category` | string | yes | |
| `condition_grade` | string | yes | |
| `estimated_weight_lbs` | number | yes | |
| `store_id` | integer | admin only | Ignored for non-admins (session store used) |
| `customer_phone` | string | no | Encrypted at rest (AES-256-GCM) |
| `customer_phone_last4` | string | no | |
| `customer_phone_preference` | string | no | Default: `standard_calls` |
| `now_local` | string | no | Local timestamp for eligibility window check |

**Response** `201`
```json
{
  "data": {
    "id": 1,
    "store_id": 1,
    "customer_name": "...",
    "clothing_category": "...",
    "condition_grade": "...",
    "estimated_weight_lbs": 10.0,
    "status": "intake_open",
    "estimated_payout": 15.00,
    "final_payout": null,
    "customer_phone_last4": "****1234",
    "created_at": "..."
  }
}
```

**Errors:** `400` validation / no store context, `403` role restriction

---

#### `POST /api/tickets/<ticket_id>/submit-qc`

**Auth:** session + CSRF | **Roles:** any

Transition ticket from `intake_open` to `awaiting_qc`.

**Response** `200` — updated ticket object

---

#### `POST /api/tickets/<ticket_id>/qc-final`

**Auth:** session + CSRF | **Roles:** any

Record final QC and compute payout. May trigger variance approval if weight divergence is too high.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `actual_weight_lbs` | number | no | Cross-check against inspection; derived if omitted |
| `now_local` | string | no | |

**Response** `200`
```json
{
  "data": {
    "ticket": { ... },
    "approval_required": true,
    "variance_amount": 5.00,
    "variance_pct": 33.3
  }
}
```

---

#### `POST /api/tickets/<ticket_id>/confirm-variance`

**Auth:** session + CSRF | **Roles:** any

Confirm variance and create supervisor approval request.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `confirmation_note` | string | yes | |

**Response** `200` — variance approval request object

---

#### `POST /api/tickets/variance/<request_id>/approve`

**Auth:** session + CSRF | **Roles:** shift_supervisor, operations_manager, administrator (enforced in service)

Approve a variance. Requires re-authentication via password.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `password` | string | yes | Approver's own password |

**Response** `200` — updated ticket object

---

#### `POST /api/tickets/variance/<request_id>/reject`

**Auth:** session + CSRF | **Roles:** shift_supervisor, operations_manager, administrator (enforced in service)

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `reason` | string | yes | |

**Response** `200` — variance request object

---

#### `POST /api/tickets/<ticket_id>/refund`

**Auth:** session + CSRF | **Roles:** any (service checks)

Initiate a refund. Creates a pending supervisor approval.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `refund_amount` | number | no | |
| `reason` | string | no | |

**Response** `200` — updated ticket object

---

#### `POST /api/tickets/<ticket_id>/refund/approve`

**Auth:** session + CSRF | **Roles:** shift_supervisor, operations_manager, administrator

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `password` | string | yes | Approver's own password |

**Response** `200` — updated ticket object

---

#### `POST /api/tickets/<ticket_id>/refund/reject`

**Auth:** session + CSRF | **Roles:** shift_supervisor, operations_manager, administrator

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `reason` | string | yes | |

**Response** `200` — updated ticket object

---

#### `POST /api/tickets/<ticket_id>/dial`

**Auth:** session + CSRF | **Roles:** any (service-layer role check)

Decrypt customer phone and return for dialing. Audited.

**Response** `200`
```json
{
  "data": {
    "phone": "5551234567",
    "last4": "4567"
  }
}
```

**Errors:** `403` role not allowed to dial, `400` ticket not found or no phone

---

#### `POST /api/tickets/<ticket_id>/cancel`

**Auth:** session + CSRF | **Roles:** any

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `reason` | string | yes | |

**Response** `200` — updated ticket with `status: "canceled"`

---

### QC & Traceability

#### `POST /api/qc/inspections`

**Auth:** session + CSRF | **Roles:** qc_inspector+ (enforced in service)

Record a QC inspection.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `ticket_id` | integer | yes | |
| `actual_weight_lbs` | number | yes | |
| `lot_size` | integer | yes | |
| `nonconformance_count` | integer | yes | |
| `inspection_outcome` | string | yes | See `inspection_outcome` enum |
| `store_id` | integer | admin only | Non-admins use session store |
| `notes` | string | no | |

**Response** `201` — inspection object

---

#### `POST /api/qc/quarantine`

**Auth:** session + CSRF | **Roles:** qc_inspector+ (enforced in service)

Create a quarantine hold.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `ticket_id` | integer | yes | |
| `batch_id` | integer | yes | |
| `notes` | string | no | |

**Response** `201` — quarantine record

---

#### `POST /api/qc/quarantine/<quarantine_id>/resolve`

**Auth:** session + CSRF | **Roles:** qc_inspector+ (enforced in service)

Resolve a quarantine with disposition.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `disposition` | string | yes | See `quarantine_disposition` enum |
| `concession_supervisor_id` | integer | no | Required for `concession_acceptance` |
| `concession_supervisor_username` | string | no | Required for `concession_acceptance` |
| `concession_supervisor_password` | string | no | Required for `concession_acceptance` |
| `notes` | string | no | |

**Response** `200` — updated quarantine record

---

#### `POST /api/qc/batches`

**Auth:** session + CSRF | **Roles:** qc_inspector+ (enforced in service)

Create a batch for traceability.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `batch_code` | string | yes | |
| `store_id` | integer | admin only | |
| `source_ticket_id` | integer | no | |

**Response** `201` — batch object

---

#### `POST /api/qc/batches/<batch_id>/transition`

**Auth:** session + CSRF | **Roles:** qc_inspector+ (enforced in service)

Transition batch status.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `target_status` | string | yes | See `batch_status` enum |
| `location_context` | string | no | |
| `metadata` | object | no | |

**Response** `200` — updated batch object

---

#### `GET /api/qc/batches/<batch_id>/lineage`

**Auth:** session | **Roles:** qc_inspector+ (enforced in service)

Get full genealogy/lineage of a batch.

**Response** `200` — array of lineage event objects

---

#### `POST /api/qc/recalls`

**Auth:** session + CSRF | **Roles:** qc_inspector+ (enforced in service)

Generate a recall report.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `store_id` | integer | no | |
| `batch_filter` | object | no | |
| `date_start` | string | no | |
| `date_end` | string | no | |

**Response** `201` — recall run object

---

#### `GET /api/qc/recalls/<run_id>`

**Auth:** session | **Roles:** qc_inspector+ (enforced in service)

Get a recall report.

**Response** `200` — recall run object with `result_data` (parsed JSON)

---

### Tables

#### `POST /api/tables/open`

**Auth:** session + CSRF | **Roles:** host+ (enforced in service)

Open a new table session.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `table_id` | integer | yes | |
| `store_id` | integer | admin only | |
| `customer_label` | string | no | |

**Response** `201` — table session object with `current_state: "occupied"`

---

#### `POST /api/tables/sessions/<session_id>/transition`

**Auth:** session + CSRF | **Roles:** host+ (enforced in service)

Transition a table session state.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `target_state` | string | yes | See `table_state` enum. Valid transitions: occupied->pre_checkout, pre_checkout->cleared, cleared->available |
| `notes` | string | no | |

**Response** `200` — updated table session object

---

#### `POST /api/tables/merge`

**Auth:** session + CSRF | **Roles:** host+ (enforced in service)

Merge multiple table sessions into a group.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `session_ids` | integer[] | yes | At least 2 IDs |
| `store_id` | integer | admin only | |

**Response** `200`
```json
{"data": {"group_code": "GRP-..."}}
```

---

#### `POST /api/tables/sessions/<session_id>/transfer`

**Auth:** session + CSRF | **Roles:** host+ (enforced in service)

Transfer a table session to a different user.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `new_user_id` | integer | yes | |

**Response** `200` — updated table session object

---

#### `GET /api/tables/sessions/<session_id>/timeline`

**Auth:** session | **Roles:** host+ (enforced in service)

Get activity timeline for a table session.

**Response** `200` — array of timeline event objects

---

### Notifications

#### `POST /api/notifications/messages`

**Auth:** session + CSRF | **Roles:** any (store-scoped in service)

Log a message/communication for a ticket.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `ticket_id` | integer | yes | |
| `message_body` | string | yes | |
| `contact_channel` | string | no | Default: `logged_message`. See `contact_channel` enum |
| `template_id` | integer | no | |
| `call_attempt_status` | string | no | See `call_attempt_status` enum |
| `retry_minutes` | integer | no | Schedule a retry |

**Response** `201` — message log object

---

#### `POST /api/notifications/messages/template`

**Auth:** session + CSRF | **Roles:** any (store-scoped in service)

Log a message rendered from a template.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `ticket_id` | integer | yes | |
| `template_code` | string | yes | e.g. `accepted`, `rescheduled`, `arrived`, `completed`, `refunded` |
| `context` | object or JSON string | yes | Template variable substitution map |
| `store_id` | integer | admin only | |
| `contact_channel` | string | no | Default: `logged_message` |
| `call_attempt_status` | string | no | |

**Response** `201` — message log object

---

#### `GET /api/notifications/tickets/<ticket_id>/messages`

**Auth:** session | **Roles:** any (store-scoped in service)

Get all messages for a ticket.

**Response** `200` — array of message log objects

---

#### `GET /api/notifications/retries/pending`

**Auth:** session | **Roles:** any (store-scoped in service)

Get messages scheduled for retry.

**Response** `200` — array of pending retry objects

---

### Members

All member endpoints are **administrator only** (enforced in service layer).

#### `POST /api/members/organizations`

**Auth:** session + CSRF | **Roles:** administrator

Create a club organization.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | string | yes | |
| `department` | string | no | |
| `route_code` | string | no | |

**Response** `201` — organization object

---

#### `PUT /api/members/organizations/<org_id>`

**Auth:** session + CSRF | **Roles:** administrator

Update a club organization.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | string | no | |
| `department` | string | no | |
| `route_code` | string | no | |
| `is_active` | boolean | no | |

**Response** `200` — updated organization object

---

#### `POST /api/members`

**Auth:** session + CSRF | **Roles:** administrator

Add a member to an organization.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `org_id` | integer | yes | |
| `full_name` | string | yes | |
| `group` | string | no | |

**Response** `201` — member object

---

#### `POST /api/members/<member_id>/remove`

**Auth:** session + CSRF | **Roles:** administrator

Mark a member as left.

**Response** `200` — updated member with `status: "left"`

---

#### `POST /api/members/<member_id>/transfer`

**Auth:** session + CSRF | **Roles:** administrator

Transfer a member to a different organization.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `target_org_id` | integer | yes | |

**Response** `200` — updated member object

---

#### `GET /api/members/<member_id>/history`

**Auth:** session | **Roles:** administrator

Get member lifecycle history.

**Response** `200` — array of history event objects

---

#### `GET /api/members/export`

**Auth:** session | **Roles:** administrator

Export members as CSV file.

**Query Parameters**
| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `organization_id` | integer | no | Filter to single org |

**Response** `200` — `Content-Type: text/csv`, attachment download

---

#### `POST /api/members/import`

**Auth:** session + CSRF | **Roles:** administrator

Import members from CSV.

**Request Body** — `multipart/form-data`
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `file` | file | yes | `.csv` extension, `text/csv` or `application/csv` or `application/vnd.ms-excel` MIME, max 5MB, UTF-8, no binary content, must have `full_name` and `organization_id` columns, at least 1 data row, consistent column count |

**Response** `201`
```json
{
  "data": {
    "imported": 42,
    "errors": [{"row": 5, "error": "organization 99 not found or inactive"}],
    "file_hash": "sha256:..."
  }
}
```

---

### Exports & Metrics

#### `POST /api/exports/requests`

**Auth:** session + CSRF | **Roles:** shift_supervisor, operations_manager, administrator (enforced in service)

Create an export request (dual-control: needs separate approval).

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `export_type` | string | yes | `tickets` or `metrics` |
| `store_id` | integer | admin only | |
| `filter_json` | object | no | |
| `watermark_enabled` | boolean | no | Default: false |
| `attribution_text` | string | no | |

**Response** `201` — export request object with `status: "pending"`

---

#### `POST /api/exports/requests/<request_id>/approve`

**Auth:** session + CSRF | **Roles:** shift_supervisor, operations_manager, administrator (enforced in service)

Approve an export. Requires re-authentication.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `password` | string | yes | Approver's own password |

**Response** `200` — export request with `status: "approved"`

---

#### `POST /api/exports/requests/<request_id>/reject`

**Auth:** session + CSRF | **Roles:** shift_supervisor, operations_manager, administrator (enforced in service)

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `reason` | string | yes | |

**Response** `200` — export request with `status: "rejected"`

---

#### `POST /api/exports/requests/<request_id>/execute`

**Auth:** session + CSRF | **Roles:** shift_supervisor, operations_manager, administrator (enforced in service)

Execute an approved export. One-time only.

**Response** `200` — export request with `status: "completed"`

---

#### `GET /api/exports/metrics`

**Auth:** session | **Roles:** operations_manager, administrator (enforced in service; shift_supervisor gets 403)

Compute operational metrics.

**Query Parameters**
| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `date_start` | string | yes | ISO date or datetime |
| `date_end` | string | yes | ISO date or datetime |
| `clothing_category` | string | no | Filter by category |
| `route_code` | string | no | Filter by route code |

**Response** `200`
```json
{
  "data": {
    "order_volume": 123,
    ...
  }
}
```

---

### Schedules

#### `POST /api/schedules/adjustments`

**Auth:** session + CSRF | **Roles:** shift_supervisor, operations_manager, administrator (enforced in service)

Request a schedule adjustment (dual-control: needs separate approval).

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `adjustment_type` | string | yes | |
| `target_entity_type` | string | yes | |
| `target_entity_id` | string | yes | |
| `before_value` | string | yes | |
| `after_value` | string | yes | |
| `reason` | string | yes | |
| `store_id` | integer | admin only | |

**Response** `201` — schedule adjustment request object

---

#### `POST /api/schedules/adjustments/<request_id>/approve`

**Auth:** session + CSRF | **Roles:** shift_supervisor, operations_manager, administrator (enforced in service)

Approve a schedule adjustment. Requires re-authentication.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `password` | string | yes | |

**Response** `200` — updated adjustment request

---

#### `POST /api/schedules/adjustments/<request_id>/reject`

**Auth:** session + CSRF | **Roles:** shift_supervisor, operations_manager, administrator (enforced in service)

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `reason` | string | yes | |

**Response** `200` — updated adjustment request

---

#### `GET /api/schedules/adjustments/pending`

**Auth:** session | **Roles:** shift_supervisor, operations_manager, administrator (enforced in service)

List pending adjustments.

**Query Parameters**
| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `store_id` | integer | no | Filter by store |

**Response** `200` — array of pending adjustment objects

---

### Settings

#### `GET /api/settings`

**Auth:** session | **Roles:** any

Get effective settings. Returns store-specific settings for pinned users, global settings for admins.

**Response** `200` — settings object

---

#### `PUT /api/settings`

**Auth:** session + CSRF | **Roles:** administrator (enforced in service)

Update settings.

**Request Body** — key/value pairs for settings fields, plus optional:
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `store_id` | integer | no | Apply to specific store; omit for global |

**Response** `200` — updated settings object

---

### Price Overrides

#### `POST /api/price-overrides`

**Auth:** session + CSRF | **Roles:** any (service-layer role check)

Request a price override for a ticket.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `ticket_id` | integer | yes | |
| `proposed_payout` | number | yes | |
| `reason` | string | yes | |

**Response** `201` — price override request object

---

#### `POST /api/price-overrides/<request_id>/approve`

**Auth:** session + CSRF | **Roles:** shift_supervisor, operations_manager, administrator (enforced in service)

Approve a price override. Requires re-authentication.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `password` | string | yes | |

**Response** `200` — updated override request

---

#### `POST /api/price-overrides/<request_id>/reject`

**Auth:** session + CSRF | **Roles:** shift_supervisor, operations_manager, administrator (enforced in service)

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `reason` | string | yes | |

**Response** `200` — updated override request

---

#### `POST /api/price-overrides/<request_id>/execute`

**Auth:** session + CSRF | **Roles:** shift_supervisor, operations_manager, administrator (enforced in service)

Execute an approved override. One-time only.

**Response** `200` — updated override request

---

#### `GET /api/price-overrides/pending`

**Auth:** session | **Roles:** shift_supervisor, operations_manager, administrator (enforced in service)

List pending price override requests.

**Response** `200` — array of pending override objects

---

### Admin

All admin endpoints require **administrator** role.

#### `POST /api/admin/stores`

**Auth:** session + CSRF | **Roles:** administrator

Create a store. Auto-creates a settings record.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `code` | string | yes | Unique store code |
| `name` | string | yes | |
| `route_code` | string | no | |

**Response** `201` — store object

---

#### `GET /api/admin/stores`

**Auth:** session | **Roles:** administrator

List all stores.

**Response** `200` — array of store objects

---

#### `POST /api/admin/pricing_rules`

**Auth:** session + CSRF | **Roles:** administrator

Create a pricing rule for a store.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `store_id` | integer | yes | |
| `base_rate_per_lb` | number | yes | |
| `category_filter` | string | no | |
| `condition_grade_filter` | string | no | |
| `bonus_pct` | number | no | Default: 0 |
| `min_weight_lbs` | number | no | Default: 0.1 |
| `max_weight_lbs` | number | no | Default: 1000.0 |
| `max_ticket_payout` | number | no | Default: 200.0 |
| `max_rate_per_lb` | number | no | Default: 10.0 |
| `eligibility_start_local` | string | no | `MM/DD/YYYY hh:mm AM/PM` format |
| `eligibility_end_local` | string | no | Both start and end required if either is set |
| `priority` | integer | no | Default: 1 |

**Response** `201` — pricing rule object

---

#### `POST /api/admin/service_tables`

**Auth:** session + CSRF | **Roles:** administrator

Create a service table.

**Request Body**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `store_id` | integer | yes | |
| `table_code` | string | yes | Unique within store |
| `area_type` | string | yes | `intake_table` or `private_room` |

**Response** `201` — service table object

---

#### `GET /api/admin/service_tables`

**Auth:** session | **Roles:** administrator

List service tables.

**Query Parameters**
| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `store_id` | integer | no | Filter by store; omit for all stores |

**Response** `200` — array of service table objects

---

### UI Pages

Server-rendered Jinja2 templates. All pages (except login) require a valid session AND an appropriate role. Unauthorized users are redirected to `/ui/login`.

| Path | Template | Allowed Roles |
|------|----------|---------------|
| `GET /ui/login` | `login.html` | public |
| `GET /ui/` | redirect to `/ui/tickets` | — |
| `GET /ui/tickets` | `tickets/index.html` | front_desk_agent, qc_inspector, shift_supervisor, operations_manager, administrator |
| `GET /ui/qc` | `qc/index.html` | qc_inspector, shift_supervisor, operations_manager, administrator |
| `GET /ui/tables` | `tables/index.html` | host, shift_supervisor, operations_manager, administrator |
| `GET /ui/notifications` | `notifications/index.html` | front_desk_agent, shift_supervisor, operations_manager, administrator |
| `GET /ui/members` | `members/index.html` | administrator |
| `GET /ui/exports` | `exports/index.html` | shift_supervisor, operations_manager, administrator |
| `GET /ui/schedules` | `schedules/index.html` | shift_supervisor, operations_manager, administrator |

---

### HTMX Partials

Server-rendered HTML fragments returned for `hx-swap`. All partials require a valid session, CSRF token (on POST), and an appropriate role. Responses are HTML (not JSON). Errors return `<div class="msg msg-error">...</div>`.

Store scoping: non-admin users always use their session-bound store. Admins may pass `?store_id=N` as a query parameter.

#### Read Partials

| Path | Method | Allowed Roles |
|------|--------|---------------|
| `/ui/partials/tickets/queue` | GET | front_desk_agent, qc_inspector, shift_supervisor, operations_manager, administrator |
| `/ui/partials/qc/queue` | GET | qc_inspector, shift_supervisor, operations_manager, administrator |
| `/ui/partials/tables/board` | GET | host, shift_supervisor, operations_manager, administrator |
| `/ui/partials/exports/list` | GET | shift_supervisor, operations_manager, administrator |
| `/ui/partials/schedules/pending` | GET | shift_supervisor, operations_manager, administrator |
| `/ui/partials/notifications/messages/<ticket_id>` | GET | front_desk_agent, shift_supervisor, operations_manager, administrator |
| `/ui/partials/notifications/retries` | GET | front_desk_agent, shift_supervisor, operations_manager, administrator |

#### Action Partials (POST)

All POST partials require the `X-CSRF-Token` header.

| Path | Allowed Roles | Notes |
|------|---------------|-------|
| `/ui/partials/tickets/<id>/submit-qc` | ticket roles | Refreshes ticket queue |
| `/ui/partials/tickets/<id>/cancel` | ticket roles | Body: `reason` (form or JSON) |
| `/ui/partials/tickets/<id>/initiate-refund` | ticket roles | Refreshes ticket queue |
| `/ui/partials/tickets/<id>/dial` | ticket roles | Returns `tel:` auto-dial script |
| `/ui/partials/exports/<id>/approve` | export roles | Body: `password` (HX-Prompt header, form, or JSON) |
| `/ui/partials/exports/<id>/reject` | export roles | Body: `reason` |
| `/ui/partials/exports/<id>/execute` | export roles | One-time execution |
| `/ui/partials/schedules/<id>/approve` | schedule roles | Body: `password` |
| `/ui/partials/schedules/<id>/reject` | schedule roles | Body: `reason` |
| `/ui/partials/tables/<id>/transition` | table roles | Body: `target_state` |

---

## Endpoint Count Summary

| Group | Endpoints |
|-------|-----------|
| Health | 1 |
| Auth | 5 |
| Tickets | 9 |
| QC & Traceability | 8 |
| Tables | 5 |
| Notifications | 4 |
| Members | 8 |
| Exports & Metrics | 5 |
| Schedules | 4 |
| Settings | 2 |
| Price Overrides | 5 |
| Admin | 5 |
| UI Pages | 9 |
| HTMX Partials | 17 |
| **Total** | **87** |
