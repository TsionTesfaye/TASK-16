-- ReclaimOps Offline Operations Suite - Initial Schema
-- All timestamps stored in UTC
-- Encrypted fields use _ciphertext/_iv pattern
-- Audit log is append-only with tamper_chain_hash

CREATE TABLE IF NOT EXISTS stores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    route_code TEXT,
    address_ciphertext BLOB,
    address_iv BLOB,
    phone_ciphertext BLOB,
    phone_iv BLOB,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN (
        'front_desk_agent', 'qc_inspector', 'host',
        'shift_supervisor', 'operations_manager', 'administrator'
    )),
    is_active INTEGER NOT NULL DEFAULT 1,
    is_frozen INTEGER NOT NULL DEFAULT 0,
    password_changed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (store_id) REFERENCES stores(id)
);

CREATE TABLE IF NOT EXISTS user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    session_nonce TEXT NOT NULL UNIQUE,
    cookie_signature_version TEXT NOT NULL,
    csrf_secret TEXT NOT NULL,
    client_device_id TEXT,
    issued_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    revoked_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- batches before buyback_tickets so current_batch_id FK resolves forward
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER NOT NULL,
    batch_code TEXT NOT NULL,
    source_ticket_id INTEGER,
    status TEXT NOT NULL DEFAULT 'procured' CHECK (status IN (
        'procured', 'received', 'quarantined', 'issued',
        'finished', 'recalled', 'scrapped', 'returned'
    )),
    procurement_at TEXT,
    receiving_at TEXT,
    issued_at TEXT,
    finished_goods_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(store_id, batch_code),
    FOREIGN KEY (store_id) REFERENCES stores(id)
);

CREATE TABLE IF NOT EXISTS buyback_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER NOT NULL,
    created_by_user_id INTEGER NOT NULL,
    customer_name TEXT NOT NULL,
    customer_phone_ciphertext BLOB,
    customer_phone_iv BLOB,
    customer_phone_last4 TEXT,
    customer_phone_preference TEXT NOT NULL DEFAULT 'standard_calls' CHECK (
        customer_phone_preference IN ('calls_only', 'standard_calls')
    ),
    clothing_category TEXT NOT NULL,
    condition_grade TEXT NOT NULL,
    estimated_weight_lbs REAL NOT NULL,
    actual_weight_lbs REAL,
    estimated_base_rate REAL NOT NULL,
    estimated_bonus_pct REAL NOT NULL,
    estimated_payout REAL NOT NULL,
    estimated_cap_applied INTEGER NOT NULL DEFAULT 0,
    actual_base_rate REAL,
    actual_bonus_pct REAL,
    final_payout REAL,
    final_cap_applied INTEGER,
    variance_amount REAL,
    variance_pct REAL,
    status TEXT NOT NULL DEFAULT 'intake_open' CHECK (status IN (
        'intake_open', 'awaiting_qc', 'variance_pending_confirmation',
        'variance_pending_supervisor', 'completed',
        'refund_pending_supervisor', 'refunded', 'canceled'
    )),
    qc_result TEXT,
    qc_notes TEXT,
    current_batch_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    completed_at TEXT,
    refunded_at TEXT,
    refund_amount REAL,
    refund_initiated_by_user_id INTEGER,
    FOREIGN KEY (store_id) REFERENCES stores(id),
    FOREIGN KEY (created_by_user_id) REFERENCES users(id),
    FOREIGN KEY (refund_initiated_by_user_id) REFERENCES users(id),
    FOREIGN KEY (current_batch_id) REFERENCES batches(id)
);

CREATE TABLE IF NOT EXISTS pricing_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER,
    category_filter TEXT,
    condition_grade_filter TEXT,
    base_rate_per_lb REAL NOT NULL,
    bonus_pct REAL NOT NULL DEFAULT 0,
    min_weight_lbs REAL,
    max_weight_lbs REAL,
    max_ticket_payout REAL NOT NULL,
    max_rate_per_lb REAL NOT NULL,
    eligibility_start_local TEXT,
    eligibility_end_local TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (store_id) REFERENCES stores(id)
);

CREATE TABLE IF NOT EXISTS pricing_calculation_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    calculation_type TEXT NOT NULL CHECK (calculation_type IN ('estimated', 'actual')),
    base_rate_per_lb REAL NOT NULL,
    input_weight_lbs REAL NOT NULL,
    gross_amount REAL NOT NULL,
    bonus_pct REAL NOT NULL,
    bonus_amount REAL NOT NULL,
    capped_amount REAL NOT NULL,
    cap_reason TEXT,
    applied_rule_ids_json TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (ticket_id) REFERENCES buyback_tickets(id)
);

CREATE TABLE IF NOT EXISTS variance_approval_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    requested_by_user_id INTEGER NOT NULL,
    approver_user_id INTEGER,
    variance_amount REAL NOT NULL,
    variance_pct REAL NOT NULL,
    threshold_amount REAL NOT NULL,
    threshold_pct REAL NOT NULL,
    confirmation_note TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'approved', 'rejected', 'expired', 'executed'
    )),
    password_confirmation_used INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    approved_at TEXT,
    rejected_at TEXT,
    executed_at TEXT,
    FOREIGN KEY (ticket_id) REFERENCES buyback_tickets(id),
    FOREIGN KEY (requested_by_user_id) REFERENCES users(id),
    FOREIGN KEY (approver_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS qc_inspections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    inspector_user_id INTEGER NOT NULL,
    actual_weight_lbs REAL NOT NULL,
    lot_size INTEGER NOT NULL,
    sample_size INTEGER NOT NULL,
    nonconformance_count INTEGER NOT NULL DEFAULT 0,
    inspection_outcome TEXT NOT NULL CHECK (inspection_outcome IN (
        'pass', 'fail', 'pass_with_concession'
    )),
    quarantine_required INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (ticket_id) REFERENCES buyback_tickets(id),
    FOREIGN KEY (inspector_user_id) REFERENCES users(id)
);

-- quarantine_records after both buyback_tickets and batches
CREATE TABLE IF NOT EXISTS quarantine_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    batch_id INTEGER NOT NULL,
    created_by_user_id INTEGER NOT NULL,
    disposition TEXT CHECK (disposition IN (
        'return_to_customer', 'scrap', 'concession_acceptance'
    )),
    concession_signed_by INTEGER,
    due_back_to_customer_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    resolved_at TEXT,
    FOREIGN KEY (ticket_id) REFERENCES buyback_tickets(id),
    FOREIGN KEY (batch_id) REFERENCES batches(id),
    FOREIGN KEY (created_by_user_id) REFERENCES users(id),
    FOREIGN KEY (concession_signed_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS batch_genealogy_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL,
    parent_batch_id INTEGER,
    child_batch_id INTEGER,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'procured', 'received', 'inspected', 'quarantined',
        'dispositioned', 'issued', 'transformed', 'finished_goods', 'recalled'
    )),
    actor_user_id INTEGER NOT NULL,
    location_context TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    metadata_json TEXT,
    FOREIGN KEY (batch_id) REFERENCES batches(id),
    FOREIGN KEY (parent_batch_id) REFERENCES batches(id),
    FOREIGN KEY (child_batch_id) REFERENCES batches(id),
    FOREIGN KEY (actor_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS recall_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER,
    requested_by_user_id INTEGER NOT NULL,
    batch_filter TEXT,
    date_start TEXT,
    date_end TEXT,
    result_count INTEGER NOT NULL DEFAULT 0,
    output_path TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (store_id) REFERENCES stores(id),
    FOREIGN KEY (requested_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS service_tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER NOT NULL,
    table_code TEXT NOT NULL,
    area_type TEXT NOT NULL CHECK (area_type IN ('intake_table', 'private_room')),
    merged_into_id INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (store_id) REFERENCES stores(id),
    FOREIGN KEY (merged_into_id) REFERENCES service_tables(id)
);

CREATE TABLE IF NOT EXISTS table_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER NOT NULL,
    table_id INTEGER NOT NULL,
    opened_by_user_id INTEGER NOT NULL,
    current_state TEXT NOT NULL DEFAULT 'available' CHECK (current_state IN (
        'available', 'occupied', 'pre_checkout', 'cleared'
    )),
    merged_group_code TEXT,
    current_customer_label TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    closed_at TEXT,
    FOREIGN KEY (store_id) REFERENCES stores(id),
    FOREIGN KEY (table_id) REFERENCES service_tables(id),
    FOREIGN KEY (opened_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS table_activity_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_session_id INTEGER NOT NULL,
    actor_user_id INTEGER NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'opened', 'occupied', 'merged', 'transferred',
        'pre_checkout', 'cleared', 'reopened', 'released'
    )),
    before_state TEXT,
    after_state TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (table_session_id) REFERENCES table_sessions(id),
    FOREIGN KEY (actor_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS notification_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER,
    template_code TEXT NOT NULL,
    name TEXT NOT NULL,
    body TEXT NOT NULL,
    event_type TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(store_id, template_code),
    FOREIGN KEY (store_id) REFERENCES stores(id)
);

CREATE TABLE IF NOT EXISTS ticket_message_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    template_id INTEGER,
    actor_user_id INTEGER NOT NULL,
    message_body TEXT NOT NULL,
    contact_channel TEXT NOT NULL CHECK (contact_channel IN (
        'logged_message', 'phone_call'
    )),
    call_attempt_status TEXT CHECK (call_attempt_status IN (
        'not_applicable', 'succeeded', 'failed', 'voicemail', 'no_answer'
    )),
    retry_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (ticket_id) REFERENCES buyback_tickets(id),
    FOREIGN KEY (template_id) REFERENCES notification_templates(id),
    FOREIGN KEY (actor_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS club_organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    department TEXT,
    route_code TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    club_organization_id INTEGER NOT NULL,
    full_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN (
        'active', 'inactive', 'transferred', 'left'
    )),
    joined_at TEXT,
    left_at TEXT,
    transferred_at TEXT,
    current_group TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (club_organization_id) REFERENCES club_organizations(id)
);

CREATE TABLE IF NOT EXISTS member_history_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    actor_user_id INTEGER NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'joined', 'left', 'transferred', 'reactivated', 'imported'
    )),
    before_json TEXT,
    after_json TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (member_id) REFERENCES members(id),
    FOREIGN KEY (actor_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS export_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER NOT NULL,
    requested_by_user_id INTEGER NOT NULL,
    export_type TEXT NOT NULL,
    filter_json TEXT,
    watermark_enabled INTEGER NOT NULL DEFAULT 0,
    attribution_text TEXT,
    approval_required INTEGER NOT NULL DEFAULT 0,
    approver_user_id INTEGER,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'approved', 'rejected', 'completed', 'expired'
    )),
    output_path TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    completed_at TEXT,
    FOREIGN KEY (store_id) REFERENCES stores(id),
    FOREIGN KEY (requested_by_user_id) REFERENCES users(id),
    FOREIGN KEY (approver_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER,
    actor_username_snapshot TEXT NOT NULL,
    action_code TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT,
    client_device_id TEXT,
    tamper_chain_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (actor_user_id) REFERENCES users(id)
);

CREATE TRIGGER IF NOT EXISTS prevent_audit_log_delete
BEFORE DELETE ON audit_logs
BEGIN
    SELECT RAISE(ABORT, 'audit logs are immutable');
END;

CREATE TRIGGER IF NOT EXISTS prevent_audit_log_update
BEFORE UPDATE ON audit_logs
BEGIN
    SELECT RAISE(ABORT, 'audit logs are immutable');
END;

CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER,
    business_timezone TEXT NOT NULL DEFAULT 'America/New_York',
    variance_pct_threshold REAL NOT NULL DEFAULT 5.0,
    variance_amount_threshold REAL NOT NULL DEFAULT 5.00,
    max_ticket_payout REAL NOT NULL DEFAULT 200.00,
    max_rate_per_lb REAL NOT NULL DEFAULT 3.00,
    qc_sample_pct REAL NOT NULL DEFAULT 10.0,
    qc_sample_min_items INTEGER NOT NULL DEFAULT 3,
    qc_escalation_nonconformances_per_day INTEGER NOT NULL DEFAULT 2,
    export_requires_supervisor_default INTEGER NOT NULL DEFAULT 0,
    file_upload_max_mb INTEGER NOT NULL DEFAULT 5,
    daily_capacity INTEGER NOT NULL DEFAULT 50,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (store_id) REFERENCES stores(id)
);

CREATE TABLE IF NOT EXISTS schedule_adjustment_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER NOT NULL,
    requested_by_user_id INTEGER NOT NULL,
    approver_user_id INTEGER,
    adjustment_type TEXT NOT NULL,
    target_entity_type TEXT NOT NULL,
    target_entity_id TEXT NOT NULL,
    before_value TEXT NOT NULL,
    after_value TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'approved', 'rejected', 'executed'
    )),
    password_confirmation_used INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    approved_at TEXT,
    rejected_at TEXT,
    executed_at TEXT,
    FOREIGN KEY (store_id) REFERENCES stores(id),
    FOREIGN KEY (requested_by_user_id) REFERENCES users(id),
    FOREIGN KEY (approver_user_id) REFERENCES users(id)
);

-- Indexes for common query patterns

CREATE INDEX IF NOT EXISTS idx_users_store_id ON users(store_id);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_session_nonce ON user_sessions(session_nonce);

CREATE INDEX IF NOT EXISTS idx_batches_store_id ON batches(store_id);
CREATE INDEX IF NOT EXISTS idx_batches_batch_code ON batches(batch_code);
CREATE INDEX IF NOT EXISTS idx_batches_status ON batches(status);

CREATE INDEX IF NOT EXISTS idx_buyback_tickets_store_id ON buyback_tickets(store_id);
CREATE INDEX IF NOT EXISTS idx_buyback_tickets_status ON buyback_tickets(status);
CREATE INDEX IF NOT EXISTS idx_buyback_tickets_created_by ON buyback_tickets(created_by_user_id);
CREATE INDEX IF NOT EXISTS idx_buyback_tickets_created_at ON buyback_tickets(created_at);

CREATE INDEX IF NOT EXISTS idx_pricing_rules_store_id ON pricing_rules(store_id);
CREATE INDEX IF NOT EXISTS idx_pricing_rules_active_priority ON pricing_rules(is_active, priority);

CREATE INDEX IF NOT EXISTS idx_pricing_snapshots_ticket_id ON pricing_calculation_snapshots(ticket_id);

CREATE INDEX IF NOT EXISTS idx_variance_requests_ticket_id ON variance_approval_requests(ticket_id);
CREATE INDEX IF NOT EXISTS idx_variance_requests_status ON variance_approval_requests(status);

CREATE INDEX IF NOT EXISTS idx_qc_inspections_ticket_id ON qc_inspections(ticket_id);
CREATE INDEX IF NOT EXISTS idx_qc_inspections_inspector ON qc_inspections(inspector_user_id);
CREATE INDEX IF NOT EXISTS idx_qc_inspections_created_at ON qc_inspections(created_at);

CREATE INDEX IF NOT EXISTS idx_quarantine_records_ticket_id ON quarantine_records(ticket_id);
CREATE INDEX IF NOT EXISTS idx_quarantine_records_batch_id ON quarantine_records(batch_id);

CREATE INDEX IF NOT EXISTS idx_batch_genealogy_batch_id ON batch_genealogy_events(batch_id);
CREATE INDEX IF NOT EXISTS idx_batch_genealogy_event_type ON batch_genealogy_events(event_type);
CREATE INDEX IF NOT EXISTS idx_batch_genealogy_created_at ON batch_genealogy_events(created_at);

CREATE INDEX IF NOT EXISTS idx_recall_runs_store_id ON recall_runs(store_id);

CREATE INDEX IF NOT EXISTS idx_service_tables_store_id ON service_tables(store_id);

CREATE INDEX IF NOT EXISTS idx_table_sessions_store_id ON table_sessions(store_id);
CREATE INDEX IF NOT EXISTS idx_table_sessions_table_id ON table_sessions(table_id);
CREATE INDEX IF NOT EXISTS idx_table_sessions_state ON table_sessions(current_state);

CREATE INDEX IF NOT EXISTS idx_table_activity_session_id ON table_activity_events(table_session_id);

CREATE INDEX IF NOT EXISTS idx_notification_templates_store_id ON notification_templates(store_id);
CREATE INDEX IF NOT EXISTS idx_notification_templates_code ON notification_templates(template_code);

CREATE INDEX IF NOT EXISTS idx_ticket_messages_ticket_id ON ticket_message_logs(ticket_id);
CREATE INDEX IF NOT EXISTS idx_ticket_messages_retry_at ON ticket_message_logs(retry_at);

CREATE INDEX IF NOT EXISTS idx_members_org_id ON members(club_organization_id);
CREATE INDEX IF NOT EXISTS idx_members_status ON members(status);

CREATE INDEX IF NOT EXISTS idx_member_history_member_id ON member_history_events(member_id);

CREATE INDEX IF NOT EXISTS idx_export_requests_store_id ON export_requests(store_id);
CREATE INDEX IF NOT EXISTS idx_export_requests_status ON export_requests(status);
CREATE INDEX IF NOT EXISTS idx_export_requests_user ON export_requests(requested_by_user_id);

CREATE INDEX IF NOT EXISTS idx_audit_logs_action_code ON audit_logs(action_code);
CREATE INDEX IF NOT EXISTS idx_audit_logs_object ON audit_logs(object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON audit_logs(actor_user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);

CREATE INDEX IF NOT EXISTS idx_settings_store_id ON settings(store_id);
