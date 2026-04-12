# Business Logic Questions Log — ReclaimOps Offline Operations Suite

---

## 1. Ticket Ownership & Scope

Question:  
Who owns a buyback ticket and how is access scoped across roles?

My Understanding:  
Tickets are store-scoped entities. Staff can only access tickets within their assigned store or operational scope.

Solution:  
- Add `store_id` to tickets
- Enforce scope filtering in all read/write endpoints
- Reject cross-store access at service layer
- Do not trust client-provided store identifiers

---

## 2. Pricing Rule Evaluation Order

Question:  
How are pricing rules applied when multiple rules (tiers, caps, promotions) exist?

My Understanding:  
Pricing is evaluated deterministically in this order:
1. Base rate per lb
2. Tier bonus (weight-based)
3. Promotional adjustments
4. Apply per-ticket cap and per-lb cap

Solution:  
- Implement pricing engine with strict evaluation pipeline
- Store both estimated and actual calculation breakdown
- Reject ambiguous or conflicting rule configurations

---

## 3. Estimated vs Actual Payout

Question:  
How is the relationship between estimated payout and final payout enforced?

My Understanding:  
Estimated payout is advisory. Final payout is determined after QC inspection.

Solution:  
- Store both `estimated_payout` and `final_payout`
- Prevent ticket completion without QC input
- Log both values for audit comparison

---

## 4. Variance Threshold Enforcement

Question:  
What triggers variance approval between estimated and actual payout?

My Understanding:  
Variance approval is required when:

difference_amount > max($5.00, 5% of estimated payout)

Solution:  
- compute both thresholds
- take the larger threshold
- compare difference against it
- require approval only if difference exceeds that value

---

## 5. Dual-Control Approval Model

Question:  
How is dual-control approval enforced?

My Understanding:  
Critical actions require:
- initiating user
- second authorized user (different identity)

Solution:  
- Require second user password re-entry
- Validate `approver_user_id != actor_user_id`
- Use atomic approval record with single-use enforcement
- Log approval with before/after state

---

## 6. Ticket Completion Rules

Question:  
When can a ticket be marked completed?

My Understanding:  
A ticket can only be completed when:
- QC inspection is recorded
- variance approval (if required) is completed

Solution:  
- Enforce completion guard in service layer
- Reject completion if any dependency is unmet
- Record completion timestamp and actor

---

## 7. Table/Room State Machine

Question:  
What are the valid states and transitions for tables/rooms?

My Understanding:  
States:
- available → occupied → pre_checkout → cleared → available

Solution:  
- Implement strict state machine
- Reject invalid transitions
- Log all transitions in timeline
- Ensure atomic updates to prevent race conditions

---

## 8. Table Merge & Transfer Rules

Question:  
How are merge and transfer operations handled?

My Understanding:  
- Merge combines multiple active tables into one logical unit
- Transfer moves a table between areas/owners

Solution:  
- Store merge relationships explicitly
- Prevent merge of already merged tables
- Ensure transfer preserves activity history
- Log all operations

---

## 9. Notification Delivery Model

Question:  
How are notifications handled without external messaging?

My Understanding:  
All communication is internal:
- messages logged per ticket
- optional call attempts recorded

Solution:  
- Store message log per ticket
- track `delivery_attempts`
- support retry scheduling
- enforce "calls only" preference

---

## 10. Contact Attempt Tracking

Question:  
How are failed contact attempts handled?

My Understanding:  
Failed attempts must trigger retry reminders.

Solution:  
- Store attempt status (success/failure)
- schedule retry using local scheduler
- log all attempts for audit

---

## 11. QC Sampling Rules

Question:  
How is sampling enforced during quality control?

My Understanding:  
- default: inspect 10% of items
- minimum: 3 items per lot
- escalation: 100% inspection if 2 failures in one day

Solution:  
- compute sample size dynamically
- track daily nonconformance count
- switch to full inspection mode when threshold met

---

## 12. Nonconformance Handling

Question:  
What happens when QC fails?

My Understanding:  
Items can be:
- returned
- scrapped
- accepted with concession

Solution:  
- enforce disposition selection
- require supervisor approval for concessions
- track disposition with timestamp and actor

---

## 13. Quarantine Workflow

Question:  
How is quarantine enforced?

My Understanding:  
Failed items are isolated until disposition decision is made.

Solution:  
- mark items as `quarantined`
- block further processing
- enforce resolution before closure

---

## 14. Traceability Model

Question:  
How is batch traceability maintained?

My Understanding:  
Every item must be traceable through:
- procurement → receiving → QC → issuance → final state

Solution:  
- assign batch IDs
- track all transitions
- maintain immutable trace log

---

## 15. Recall Generation

Question:  
How are recalls generated?

My Understanding:  
Recall lists are generated based on batch or date range.

Solution:  
- query traceability records
- return affected batches/items
- ensure full lineage visibility

---

## 16. Security Model (Offline)

Question:  
How is security enforced without external systems?

My Understanding:  
All security is local but must still be strict.

Solution:  
- hashed passwords (bcrypt or equivalent)
- AES encryption for sensitive fields
- signed session cookies with expiry
- CSRF protection on all mutations

---

## 17. Sensitive Data Masking

Question:  
When is sensitive data revealed?

My Understanding:  
Sensitive fields are masked by default.

Solution:  
- mask phone/address in responses
- require explicit reveal endpoint
- log all reveal actions

---

## 18. File Upload Validation

Question:  
How are imports/exports secured?

My Understanding:  
Only CSV files are allowed.

Solution:  
- enforce MIME + extension validation
- max size 5MB
- compute file hash
- reject invalid files before processing

---

## 19. Export Approval Workflow

Question:  
When is supervisor approval required for export?

My Understanding:  
Sensitive exports require approval.

Solution:  
- enforce approval grant
- require second user authorization
- optionally watermark exported files

---

## 20. Audit Logging Requirements

Question:  
What actions must be logged?

My Understanding:  
All critical actions must be logged.

Solution:  
- log actor, timestamp, before/after values
- make logs immutable
- include device identifier

---

## 21. Scheduler Responsibilities

Question:  
What tasks must be scheduled?

My Understanding:  
Scheduler handles:
- retry notifications
- QC escalation checks
- recall readiness
- report generation

Solution:  
- implement periodic job runner
- ensure idempotent execution
- persist job state

---

## 22. Data Retention Policy

Question:  
How long is data retained?

My Understanding:  
Operational data is retained locally unless manually cleared.

Solution:  
- define retention config
- prevent silent deletion
- allow admin-controlled cleanup only

---

## 23. RBAC Enforcement Layer

Question:  
Where is RBAC enforced?

My Understanding:  
Service layer is authoritative.

Solution:  
- enforce permissions in services
- use UI only for visibility
- reject unauthorized actions at backend

---

## 24. Concurrency Control

Question:  
How are race conditions prevented?

My Understanding:  
Critical operations must be atomic.

Solution:  
- use DB transactions
- apply row-level locking where needed
- prevent duplicate execution

---

## 25. System Runnability Constraint

Question:  
How should the system run?

My Understanding:  
The system must run locally with one command.

Solution:  
- provide Docker Compose setup
- ensure backend + DB + frontend start together
- no manual steps required

---

## 26. Refund Workflow

Question:  
How should refunds behave?

My Understanding:  
Refunds require dual-control approval and may be full or partial.

Solution:  
- enforce approval workflow  
- prevent refund without approval  
- log all refund operations  

---

## 27. Price Override Policy

Question:  
Can operators override pricing manually?

My Understanding:  
No — pricing must be deterministic.

Solution:  
- disallow manual overrides  
- enforce variance approval instead  

---

## 28. Schedule Adjustment Control

Question:  
What are schedule adjustments?

My Understanding:  
Changes to system-managed scheduler tasks.

Solution:  
- treat as sensitive action  
- require dual-control approval  

---