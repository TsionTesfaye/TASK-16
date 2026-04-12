"""Tests that the SQLite schema is created correctly and all tables exist."""


EXPECTED_TABLES = [
    "stores",
    "users",
    "user_sessions",
    "buyback_tickets",
    "pricing_rules",
    "pricing_calculation_snapshots",
    "variance_approval_requests",
    "qc_inspections",
    "quarantine_records",
    "batches",
    "batch_genealogy_events",
    "recall_runs",
    "service_tables",
    "table_sessions",
    "table_activity_events",
    "notification_templates",
    "ticket_message_logs",
    "club_organizations",
    "members",
    "member_history_events",
    "export_requests",
    "audit_logs",
    "settings",
    "schedule_adjustment_requests",
    "schema_migrations",
]


def _get_tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0] for row in rows}


def _get_columns(conn, table):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1]: row[2] for row in rows}


def test_all_tables_exist(db_conn):
    tables = _get_tables(db_conn)
    for expected in EXPECTED_TABLES:
        assert expected in tables, f"Table '{expected}' missing from schema"


def test_stores_columns(db_conn):
    cols = _get_columns(db_conn, "stores")
    expected = [
        "id", "code", "name", "route_code",
        "address_ciphertext", "address_iv",
        "phone_ciphertext", "phone_iv",
        "is_active", "created_at", "updated_at",
    ]
    for col in expected:
        assert col in cols, f"Column 'stores.{col}' missing"


def test_users_columns(db_conn):
    cols = _get_columns(db_conn, "users")
    expected = [
        "id", "store_id", "username", "password_hash", "display_name",
        "role", "is_active", "is_frozen", "password_changed_at",
        "created_at", "updated_at",
    ]
    for col in expected:
        assert col in cols, f"Column 'users.{col}' missing"


def test_user_sessions_columns(db_conn):
    cols = _get_columns(db_conn, "user_sessions")
    expected = [
        "id", "user_id", "session_nonce", "cookie_signature_version",
        "csrf_secret", "client_device_id",
        "issued_at", "expires_at", "last_seen_at", "revoked_at",
    ]
    for col in expected:
        assert col in cols, f"Column 'user_sessions.{col}' missing"


def test_buyback_tickets_columns(db_conn):
    cols = _get_columns(db_conn, "buyback_tickets")
    expected = [
        "id", "store_id", "created_by_user_id", "customer_name",
        "customer_phone_ciphertext", "customer_phone_iv",
        "customer_phone_last4", "customer_phone_preference",
        "clothing_category", "condition_grade",
        "estimated_weight_lbs", "actual_weight_lbs",
        "estimated_base_rate", "estimated_bonus_pct",
        "estimated_payout", "estimated_cap_applied",
        "actual_base_rate", "actual_bonus_pct",
        "final_payout", "final_cap_applied",
        "variance_amount", "variance_pct",
        "status", "qc_result", "qc_notes",
        "current_batch_id",
        "created_at", "updated_at", "completed_at", "refunded_at",
        "refund_amount", "refund_initiated_by_user_id",
    ]
    for col in expected:
        assert col in cols, f"Column 'buyback_tickets.{col}' missing"


def test_pricing_rules_columns(db_conn):
    cols = _get_columns(db_conn, "pricing_rules")
    expected = [
        "id", "store_id", "category_filter", "condition_grade_filter",
        "base_rate_per_lb", "bonus_pct",
        "min_weight_lbs", "max_weight_lbs",
        "max_ticket_payout", "max_rate_per_lb",
        "eligibility_start_local", "eligibility_end_local",
        "is_active", "priority", "created_at", "updated_at",
    ]
    for col in expected:
        assert col in cols, f"Column 'pricing_rules.{col}' missing"


def test_pricing_calculation_snapshots_columns(db_conn):
    cols = _get_columns(db_conn, "pricing_calculation_snapshots")
    expected = [
        "id", "ticket_id", "calculation_type",
        "base_rate_per_lb", "input_weight_lbs",
        "gross_amount", "bonus_pct", "bonus_amount",
        "capped_amount", "cap_reason", "applied_rule_ids_json",
        "created_at",
    ]
    for col in expected:
        assert col in cols, f"Column 'pricing_calculation_snapshots.{col}' missing"


def test_variance_approval_requests_columns(db_conn):
    cols = _get_columns(db_conn, "variance_approval_requests")
    expected = [
        "id", "ticket_id", "requested_by_user_id", "approver_user_id",
        "variance_amount", "variance_pct",
        "threshold_amount", "threshold_pct",
        "confirmation_note", "status", "password_confirmation_used",
        "expires_at", "created_at", "approved_at", "rejected_at", "executed_at",
    ]
    for col in expected:
        assert col in cols, f"Column 'variance_approval_requests.{col}' missing"


def test_qc_inspections_columns(db_conn):
    cols = _get_columns(db_conn, "qc_inspections")
    expected = [
        "id", "ticket_id", "inspector_user_id",
        "actual_weight_lbs", "lot_size", "sample_size",
        "nonconformance_count", "inspection_outcome",
        "quarantine_required", "notes",
        "created_at", "updated_at",
    ]
    for col in expected:
        assert col in cols, f"Column 'qc_inspections.{col}' missing"


def test_quarantine_records_columns(db_conn):
    cols = _get_columns(db_conn, "quarantine_records")
    expected = [
        "id", "ticket_id", "batch_id", "created_by_user_id",
        "disposition", "concession_signed_by",
        "due_back_to_customer_at", "notes",
        "created_at", "resolved_at",
    ]
    for col in expected:
        assert col in cols, f"Column 'quarantine_records.{col}' missing"


def test_batches_columns(db_conn):
    cols = _get_columns(db_conn, "batches")
    expected = [
        "id", "store_id", "batch_code", "source_ticket_id",
        "status", "procurement_at", "receiving_at",
        "issued_at", "finished_goods_at",
        "created_at", "updated_at",
    ]
    for col in expected:
        assert col in cols, f"Column 'batches.{col}' missing"


def test_batch_genealogy_events_columns(db_conn):
    cols = _get_columns(db_conn, "batch_genealogy_events")
    expected = [
        "id", "batch_id", "parent_batch_id", "child_batch_id",
        "event_type", "actor_user_id", "location_context",
        "created_at", "metadata_json",
    ]
    for col in expected:
        assert col in cols, f"Column 'batch_genealogy_events.{col}' missing"


def test_recall_runs_columns(db_conn):
    cols = _get_columns(db_conn, "recall_runs")
    expected = [
        "id", "store_id", "requested_by_user_id",
        "batch_filter", "date_start", "date_end",
        "result_count", "output_path", "created_at",
    ]
    for col in expected:
        assert col in cols, f"Column 'recall_runs.{col}' missing"


def test_service_tables_columns(db_conn):
    cols = _get_columns(db_conn, "service_tables")
    expected = [
        "id", "store_id", "table_code", "area_type",
        "merged_into_id", "is_active",
        "created_at", "updated_at",
    ]
    for col in expected:
        assert col in cols, f"Column 'service_tables.{col}' missing"


def test_table_sessions_columns(db_conn):
    cols = _get_columns(db_conn, "table_sessions")
    expected = [
        "id", "store_id", "table_id", "opened_by_user_id",
        "current_state", "merged_group_code", "current_customer_label",
        "created_at", "updated_at", "closed_at",
    ]
    for col in expected:
        assert col in cols, f"Column 'table_sessions.{col}' missing"


def test_table_activity_events_columns(db_conn):
    cols = _get_columns(db_conn, "table_activity_events")
    expected = [
        "id", "table_session_id", "actor_user_id", "event_type",
        "before_state", "after_state", "notes", "created_at",
    ]
    for col in expected:
        assert col in cols, f"Column 'table_activity_events.{col}' missing"


def test_notification_templates_columns(db_conn):
    cols = _get_columns(db_conn, "notification_templates")
    expected = [
        "id", "store_id", "template_code", "name", "body",
        "event_type", "is_active", "created_at", "updated_at",
    ]
    for col in expected:
        assert col in cols, f"Column 'notification_templates.{col}' missing"


def test_ticket_message_logs_columns(db_conn):
    cols = _get_columns(db_conn, "ticket_message_logs")
    expected = [
        "id", "ticket_id", "template_id", "actor_user_id",
        "message_body", "contact_channel",
        "call_attempt_status", "retry_at", "created_at",
    ]
    for col in expected:
        assert col in cols, f"Column 'ticket_message_logs.{col}' missing"


def test_club_organizations_columns(db_conn):
    cols = _get_columns(db_conn, "club_organizations")
    expected = [
        "id", "name", "department", "route_code",
        "is_active", "created_at", "updated_at",
    ]
    for col in expected:
        assert col in cols, f"Column 'club_organizations.{col}' missing"


def test_members_columns(db_conn):
    cols = _get_columns(db_conn, "members")
    expected = [
        "id", "club_organization_id", "full_name", "status",
        "joined_at", "left_at", "transferred_at", "current_group",
        "created_at", "updated_at",
    ]
    for col in expected:
        assert col in cols, f"Column 'members.{col}' missing"


def test_member_history_events_columns(db_conn):
    cols = _get_columns(db_conn, "member_history_events")
    expected = [
        "id", "member_id", "actor_user_id", "event_type",
        "before_json", "after_json", "created_at",
    ]
    for col in expected:
        assert col in cols, f"Column 'member_history_events.{col}' missing"


def test_export_requests_columns(db_conn):
    cols = _get_columns(db_conn, "export_requests")
    expected = [
        "id", "store_id", "requested_by_user_id", "export_type", "filter_json",
        "watermark_enabled", "attribution_text",
        "approval_required", "approver_user_id", "status",
        "output_path", "created_at", "completed_at",
    ]
    for col in expected:
        assert col in cols, f"Column 'export_requests.{col}' missing"


def test_audit_logs_columns(db_conn):
    cols = _get_columns(db_conn, "audit_logs")
    expected = [
        "id", "actor_user_id", "actor_username_snapshot",
        "action_code", "object_type", "object_id",
        "before_json", "after_json", "client_device_id",
        "tamper_chain_hash", "created_at",
    ]
    for col in expected:
        assert col in cols, f"Column 'audit_logs.{col}' missing"


def test_settings_columns(db_conn):
    cols = _get_columns(db_conn, "settings")
    expected = [
        "id", "store_id", "business_timezone",
        "variance_pct_threshold", "variance_amount_threshold",
        "max_ticket_payout", "max_rate_per_lb",
        "qc_sample_pct", "qc_sample_min_items",
        "qc_escalation_nonconformances_per_day",
        "export_requires_supervisor_default",
        "file_upload_max_mb", "daily_capacity", "created_at", "updated_at",
    ]
    for col in expected:
        assert col in cols, f"Column 'settings.{col}' missing"


def test_foreign_keys_enabled(db_conn):
    row = db_conn.execute("PRAGMA foreign_keys").fetchone()
    assert row[0] == 1, "Foreign keys must be enabled"


def test_check_constraints_ticket_status(db_conn):
    """Verify that invalid ticket status values are rejected."""
    db_conn.execute(
        "INSERT INTO stores (code, name) VALUES ('S1', 'Store 1')"
    )
    db_conn.execute(
        """INSERT INTO users (username, password_hash, display_name, role)
           VALUES ('agent1', 'hash', 'Agent 1', 'front_desk_agent')"""
    )
    db_conn.commit()

    import sqlite3
    try:
        db_conn.execute(
            """INSERT INTO buyback_tickets (
                store_id, created_by_user_id, customer_name,
                clothing_category, condition_grade,
                estimated_weight_lbs, estimated_base_rate,
                estimated_bonus_pct, estimated_payout, status
            ) VALUES (1, 1, 'Test', 'shirts', 'A', 10.0, 1.5, 0, 15.0, 'INVALID_STATUS')"""
        )
        db_conn.commit()
        assert False, "Should have rejected invalid status"
    except sqlite3.IntegrityError:
        db_conn.rollback()


def test_check_constraints_user_role(db_conn):
    """Verify that invalid user roles are rejected."""
    import sqlite3
    try:
        db_conn.execute(
            """INSERT INTO users (username, password_hash, display_name, role)
               VALUES ('bad', 'hash', 'Bad', 'INVALID_ROLE')"""
        )
        db_conn.commit()
        assert False, "Should have rejected invalid role"
    except sqlite3.IntegrityError:
        db_conn.rollback()


def test_audit_log_immutable_no_delete(db_conn):
    """Verify that DELETE on audit_logs is blocked by trigger."""
    import sqlite3
    db_conn.execute(
        """INSERT INTO audit_logs (actor_username_snapshot, action_code,
           object_type, object_id, tamper_chain_hash)
           VALUES ('admin', 'test.action', 'test', '1', 'hash1')"""
    )
    db_conn.commit()
    try:
        db_conn.execute("DELETE FROM audit_logs WHERE id = 1")
        db_conn.commit()
        assert False, "Should have blocked DELETE on audit_logs"
    except sqlite3.IntegrityError:
        db_conn.rollback()


def test_audit_log_immutable_no_update(db_conn):
    """Verify that UPDATE on audit_logs is blocked by trigger."""
    import sqlite3
    db_conn.execute(
        """INSERT INTO audit_logs (actor_username_snapshot, action_code,
           object_type, object_id, tamper_chain_hash)
           VALUES ('admin', 'test.action', 'test', '1', 'hash2')"""
    )
    db_conn.commit()
    try:
        db_conn.execute("UPDATE audit_logs SET action_code = 'tampered' WHERE id = 1")
        db_conn.commit()
        assert False, "Should have blocked UPDATE on audit_logs"
    except sqlite3.IntegrityError:
        db_conn.rollback()


def test_audit_log_insert_still_works(db_conn):
    """Verify that INSERT on audit_logs still works despite triggers."""
    db_conn.execute(
        """INSERT INTO audit_logs (actor_username_snapshot, action_code,
           object_type, object_id, tamper_chain_hash)
           VALUES ('admin', 'test.insert', 'test', '99', 'hash3')"""
    )
    db_conn.commit()
    row = db_conn.execute(
        "SELECT * FROM audit_logs WHERE object_id = '99'"
    ).fetchone()
    assert row is not None
    assert row["action_code"] == "test.insert"
