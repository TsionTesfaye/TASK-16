# Test Coverage Audit

## Project Type Detection
- README declares project type at top as `fullstack` (`README.md:3`).
- Effective audit type: **fullstack**.

## Backend Endpoint Inventory
- Endpoint extraction source: `fullstack/backend/app.py` + `fullstack/backend/src/routes/*_routes.py`.
- Unique endpoints (`METHOD + resolved PATH`): **91**.

## API Test Mapping Table
| Endpoint | Covered | Test type | Test file(s) | Evidence (file:function) | Route handler |
|---|---|---|---|---|---|
| `GET /` | yes | true no-mock HTTP | `API_tests/test_frontend_components.py` | `API_tests/test_frontend_components.py:test_get_root_returns_redirect` | `fullstack/backend/app.py:root` |
| `POST /api/admin/pricing_rules` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:_create_store_and_pricing` | `fullstack/backend/src/routes/admin_routes.py:create_pricing_rule` |
| `GET /api/admin/service_tables` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_service_table_create_and_list` | `fullstack/backend/src/routes/admin_routes.py:list_service_tables` |
| `POST /api/admin/service_tables` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_service_table_create_and_list` | `fullstack/backend/src/routes/admin_routes.py:create_service_table` |
| `GET /api/admin/stores` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_list_stores_returns_created` | `fullstack/backend/src/routes/admin_routes.py:list_stores` |
| `POST /api/admin/stores` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:_create_store_and_pricing` | `fullstack/backend/src/routes/admin_routes.py:create_store` |
| `POST /api/auth/bootstrap` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:_bootstrap_admin_and_login` | `fullstack/backend/src/routes/auth_routes.py:bootstrap` |
| `POST /api/auth/login` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:_bootstrap_admin_and_login` | `fullstack/backend/src/routes/auth_routes.py:login` |
| `POST /api/auth/logout` | yes | true no-mock HTTP | `API_tests/test_partial_auth.py` | `API_tests/test_partial_auth.py:_logout` | `fullstack/backend/src/routes/auth_routes.py:logout` |
| `POST /api/auth/users` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:_create_user` | `fullstack/backend/src/routes/auth_routes.py:create_user` |
| `POST /api/auth/users/<int:user_id>/freeze` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_freeze_unfreeze_cycle` | `fullstack/backend/src/routes/auth_routes.py:freeze_user` |
| `POST /api/auth/users/<int:user_id>/unfreeze` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_freeze_unfreeze_cycle` | `fullstack/backend/src/routes/auth_routes.py:unfreeze_user` |
| `GET /api/exports/metrics` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_metrics_requires_store_context` | `fullstack/backend/src/routes/export_routes.py:get_metrics` |
| `POST /api/exports/requests` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_request_missing_export_type` | `fullstack/backend/src/routes/export_routes.py:create_export_request` |
| `POST /api/exports/requests/<int:request_id>/approve` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_approve_requires_password` | `fullstack/backend/src/routes/export_routes.py:approve_export` |
| `POST /api/exports/requests/<int:request_id>/execute` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_request_unsupported_type_rejected_on_execute` | `fullstack/backend/src/routes/export_routes.py:execute_export` |
| `POST /api/exports/requests/<int:request_id>/reject` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_reject_requires_reason` | `fullstack/backend/src/routes/export_routes.py:reject_export` |
| `POST /api/members` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_add_member_and_history` | `fullstack/backend/src/routes/member_routes.py:add_member` |
| `GET /api/members/<int:member_id>/history` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_add_member_and_history` | `fullstack/backend/src/routes/member_routes.py:get_member_history` |
| `POST /api/members/<int:member_id>/remove` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_remove_member` | `fullstack/backend/src/routes/member_routes.py:remove_member` |
| `POST /api/members/<int:member_id>/transfer` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_transfer_member` | `fullstack/backend/src/routes/member_routes.py:transfer_member` |
| `GET /api/members/export` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_export_csv_empty` | `fullstack/backend/src/routes/member_routes.py:export_csv` |
| `POST /api/members/import` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_import_csv_requires_file` | `fullstack/backend/src/routes/member_routes.py:import_csv` |
| `POST /api/members/organizations` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_create_organization` | `fullstack/backend/src/routes/member_routes.py:create_organization` |
| `PUT /api/members/organizations/<int:org_id>` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_update_organization_fields` | `fullstack/backend/src/routes/member_routes.py:update_organization` |
| `POST /api/notifications/messages` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_log_message_success` | `fullstack/backend/src/routes/notification_routes.py:log_message` |
| `POST /api/notifications/messages/template` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_template_message_dict_context` | `fullstack/backend/src/routes/notification_routes.py:log_from_template` |
| `GET /api/notifications/retries/pending` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_pending_retries_endpoint` | `fullstack/backend/src/routes/notification_routes.py:get_pending_retries` |
| `GET /api/notifications/tickets/<int:ticket_id>/messages` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_get_ticket_messages` | `fullstack/backend/src/routes/notification_routes.py:get_ticket_messages` |
| `POST /api/price-overrides` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_request_missing_fields` | `fullstack/backend/src/routes/price_override_routes.py:request_override` |
| `POST /api/price-overrides/<int:request_id>/approve` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_approve_missing_password` | `fullstack/backend/src/routes/price_override_routes.py:approve_override` |
| `POST /api/price-overrides/<int:request_id>/execute` | yes | true no-mock HTTP | `API_tests/test_routes.py` | `API_tests/test_routes.py:test_execute_wrong_role` | `fullstack/backend/src/routes/price_override_routes.py:execute_override` |
| `POST /api/price-overrides/<int:request_id>/reject` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_reject_with_reason` | `fullstack/backend/src/routes/price_override_routes.py:reject_override` |
| `GET /api/price-overrides/pending` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_pending_list_as_supervisor` | `fullstack/backend/src/routes/price_override_routes.py:list_pending` |
| `POST /api/qc/batches` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_batch_create_and_lineage` | `fullstack/backend/src/routes/qc_routes.py:create_batch` |
| `GET /api/qc/batches/<int:batch_id>/lineage` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_batch_create_and_lineage` | `fullstack/backend/src/routes/qc_routes.py:get_batch_lineage` |
| `POST /api/qc/batches/<int:batch_id>/transition` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_batch_transition` | `fullstack/backend/src/routes/qc_routes.py:transition_batch` |
| `POST /api/qc/inspections` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_inspection_requires_fields` | `fullstack/backend/src/routes/qc_routes.py:create_inspection` |
| `POST /api/qc/quarantine` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_quarantine_requires_fields` | `fullstack/backend/src/routes/qc_routes.py:create_quarantine` |
| `POST /api/qc/quarantine/<int:quarantine_id>/resolve` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_quarantine_resolve_requires_disposition` | `fullstack/backend/src/routes/qc_routes.py:resolve_quarantine` |
| `POST /api/qc/recalls` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_recall_generate_and_get` | `fullstack/backend/src/routes/qc_routes.py:generate_recall` |
| `GET /api/qc/recalls/<int:run_id>` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_recall_generate_and_get` | `fullstack/backend/src/routes/qc_routes.py:get_recall` |
| `POST /api/schedules/adjustments` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_adjustment_missing_fields` | `fullstack/backend/src/routes/schedule_routes.py:request_adjustment` |
| `POST /api/schedules/adjustments/<int:request_id>/approve` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_approve_requires_password` | `fullstack/backend/src/routes/schedule_routes.py:approve_adjustment` |
| `POST /api/schedules/adjustments/<int:request_id>/reject` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_reject_with_reason` | `fullstack/backend/src/routes/schedule_routes.py:reject_adjustment` |
| `GET /api/schedules/adjustments/pending` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_list_pending_by_store_filter` | `fullstack/backend/src/routes/schedule_routes.py:list_pending` |
| `GET /api/settings` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_get_settings_as_admin_returns_global` | `fullstack/backend/src/routes/settings_routes.py:get_settings` |
| `PUT /api/settings` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_update_settings_as_admin` | `fullstack/backend/src/routes/settings_routes.py:update_settings` |
| `POST /api/tables/merge` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_merge_requires_two_plus_ids` | `fullstack/backend/src/routes/table_routes.py:merge_tables` |
| `POST /api/tables/open` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_open_requires_table_id` | `fullstack/backend/src/routes/table_routes.py:open_table` |
| `GET /api/tables/sessions/<int:session_id>/timeline` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_open_and_transition_and_timeline` | `fullstack/backend/src/routes/table_routes.py:get_timeline` |
| `POST /api/tables/sessions/<int:session_id>/transfer` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_transfer_requires_new_user` | `fullstack/backend/src/routes/table_routes.py:transfer_table` |
| `POST /api/tables/sessions/<int:session_id>/transition` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_open_and_transition_and_timeline` | `fullstack/backend/src/routes/table_routes.py:transition_table` |
| `POST /api/tickets` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:_setup_ticket_awaiting_qc` | `fullstack/backend/src/routes/ticket_routes.py:create_ticket` |
| `POST /api/tickets/<int:ticket_id>/cancel` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_cancel_requires_reason` | `fullstack/backend/src/routes/ticket_routes.py:cancel_ticket` |
| `POST /api/tickets/<int:ticket_id>/confirm-variance` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_confirm_variance_requires_note` | `fullstack/backend/src/routes/ticket_routes.py:confirm_variance` |
| `POST /api/tickets/<int:ticket_id>/dial` | yes | true no-mock HTTP | `API_tests/test_deep_coverage.py` | `API_tests/test_deep_coverage.py:test_api_dial_success_returns_decrypted_phone` | `fullstack/backend/src/routes/ticket_routes.py:dial_ticket_phone` |
| `POST /api/tickets/<int:ticket_id>/qc-final` | yes | true no-mock HTTP | `API_tests/test_deep_coverage.py` | `API_tests/test_deep_coverage.py:_completed_ticket` | `fullstack/backend/src/routes/ticket_routes.py:record_qc_final` |
| `POST /api/tickets/<int:ticket_id>/refund` | yes | true no-mock HTTP | `API_tests/test_deep_coverage.py` | `API_tests/test_deep_coverage.py:test_initiate_then_approve_refund` | `fullstack/backend/src/routes/ticket_routes.py:initiate_refund` |
| `POST /api/tickets/<int:ticket_id>/refund/approve` | yes | true no-mock HTTP | `API_tests/test_deep_coverage.py` | `API_tests/test_deep_coverage.py:test_initiate_then_approve_refund` | `fullstack/backend/src/routes/ticket_routes.py:approve_refund` |
| `POST /api/tickets/<int:ticket_id>/refund/reject` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_initiate_refund_success` | `fullstack/backend/src/routes/ticket_routes.py:reject_refund` |
| `POST /api/tickets/<int:ticket_id>/submit-qc` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:_setup_ticket_awaiting_qc` | `fullstack/backend/src/routes/ticket_routes.py:submit_for_qc` |
| `POST /api/tickets/variance/<int:request_id>/approve` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_variance_approve_missing_password` | `fullstack/backend/src/routes/ticket_routes.py:approve_variance` |
| `POST /api/tickets/variance/<int:request_id>/reject` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_variance_reject_missing_reason` | `fullstack/backend/src/routes/ticket_routes.py:reject_variance` |
| `GET /health` | yes | true no-mock HTTP | `API_tests/test_health.py` | `API_tests/test_health.py:test_health_endpoint` | `fullstack/backend/app.py:health` |
| `GET /ui/` | yes | true no-mock HTTP | `API_tests/test_frontend_components.py` | `API_tests/test_frontend_components.py:test_get_ui_slash_returns_redirect` | `fullstack/backend/src/routes/ui_routes.py:index` |
| `GET /ui/exports` | yes | true no-mock HTTP | `API_tests/test_frontend_components.py` | `API_tests/test_frontend_components.py:test_exports_page_blocked_for_front_desk` | `fullstack/backend/src/routes/ui_routes.py:exports_page` |
| `GET /ui/login` | yes | true no-mock HTTP | `API_tests/test_routes.py` | `API_tests/test_routes.py:test_login_page_is_public` | `fullstack/backend/src/routes/ui_routes.py:login_page` |
| `GET /ui/members` | yes | true no-mock HTTP | `API_tests/test_frontend_components.py` | `API_tests/test_frontend_components.py:test_members_page_blocked_for_supervisor` | `fullstack/backend/src/routes/ui_routes.py:members_page` |
| `GET /ui/notifications` | yes | true no-mock HTTP | `API_tests/test_ui_routes.py` | `API_tests/test_ui_routes.py:test_notifications_page_renders_for_operator` | `fullstack/backend/src/routes/ui_routes.py:notifications_page` |
| `POST /ui/partials/exports/<int:request_id>/approve` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_partial_export_approve_missing_password` | `fullstack/backend/src/routes/partials_routes.py:partial_export_approve` |
| `POST /ui/partials/exports/<int:request_id>/execute` | yes | true no-mock HTTP | `API_tests/test_deep_coverage.py` | `API_tests/test_deep_coverage.py:test_partial_export_execute_success` | `fullstack/backend/src/routes/partials_routes.py:partial_export_execute` |
| `POST /ui/partials/exports/<int:request_id>/reject` | yes | true no-mock HTTP | `API_tests/test_deep_coverage.py` | `API_tests/test_deep_coverage.py:test_partial_export_reject_success` | `fullstack/backend/src/routes/partials_routes.py:partial_export_reject` |
| `GET /ui/partials/exports/list` | yes | true no-mock HTTP | `API_tests/test_partial_auth.py` | `API_tests/test_partial_auth.py:test_front_desk_cannot_access_exports` | `fullstack/backend/src/routes/partials_routes.py:exports_list` |
| `GET /ui/partials/notifications/messages/<int:ticket_id>` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_partial_notification_messages_for_ticket` | `fullstack/backend/src/routes/partials_routes.py:notification_messages` |
| `GET /ui/partials/notifications/retries` | yes | true no-mock HTTP | `API_tests/test_partial_auth.py` | `API_tests/test_partial_auth.py:test_host_cannot_access_notifications` | `fullstack/backend/src/routes/partials_routes.py:notification_retries` |
| `GET /ui/partials/qc/queue` | yes | true no-mock HTTP | `API_tests/test_partial_auth.py` | `API_tests/test_partial_auth.py:test_front_desk_cannot_access_qc_queue` | `fullstack/backend/src/routes/partials_routes.py:qc_queue` |
| `POST /ui/partials/schedules/<int:request_id>/approve` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_partial_schedule_approve_missing_password` | `fullstack/backend/src/routes/partials_routes.py:partial_schedule_approve` |
| `POST /ui/partials/schedules/<int:request_id>/reject` | yes | true no-mock HTTP | `API_tests/test_deep_coverage.py` | `API_tests/test_deep_coverage.py:test_partial_schedule_approve_and_reject_branches` | `fullstack/backend/src/routes/partials_routes.py:partial_schedule_reject` |
| `GET /ui/partials/schedules/pending` | yes | true no-mock HTTP | `API_tests/test_partial_auth.py` | `API_tests/test_partial_auth.py:test_front_desk_cannot_access_schedules` | `fullstack/backend/src/routes/partials_routes.py:schedules_pending` |
| `POST /ui/partials/tables/<int:session_id>/transition` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_partial_table_transition_invalid_target` | `fullstack/backend/src/routes/partials_routes.py:partial_table_transition` |
| `GET /ui/partials/tables/board` | yes | true no-mock HTTP | `API_tests/test_partial_auth.py` | `API_tests/test_partial_auth.py:test_host_can_access_table_board` | `fullstack/backend/src/routes/partials_routes.py:table_board` |
| `POST /ui/partials/tickets/<int:ticket_id>/cancel` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_partial_cancel_success` | `fullstack/backend/src/routes/partials_routes.py:partial_cancel_ticket` |
| `POST /ui/partials/tickets/<int:ticket_id>/dial` | yes | true no-mock HTTP | `API_tests/test_deep_coverage.py` | `API_tests/test_deep_coverage.py:test_dial_on_completed_ticket` | `fullstack/backend/src/routes/partials_routes.py:partial_dial` |
| `POST /ui/partials/tickets/<int:ticket_id>/initiate-refund` | yes | true no-mock HTTP | `API_tests/test_deep_coverage.py` | `API_tests/test_deep_coverage.py:test_partial_initiate_refund_success_flow` | `fullstack/backend/src/routes/partials_routes.py:partial_initiate_refund` |
| `POST /ui/partials/tickets/<int:ticket_id>/submit-qc` | yes | true no-mock HTTP | `API_tests/test_coverage_closure.py` | `API_tests/test_coverage_closure.py:test_partial_submit_qc_success` | `fullstack/backend/src/routes/partials_routes.py:partial_submit_qc` |
| `GET /ui/partials/tickets/queue` | yes | true no-mock HTTP | `API_tests/test_deep_coverage.py` | `API_tests/test_deep_coverage.py:test_queue_renders_awaiting_qc_state` | `fullstack/backend/src/routes/partials_routes.py:ticket_queue` |
| `GET /ui/qc` | yes | true no-mock HTTP | `API_tests/test_frontend_components.py` | `API_tests/test_frontend_components.py:test_qc_page_blocked_for_front_desk` | `fullstack/backend/src/routes/ui_routes.py:qc_page` |
| `GET /ui/schedules` | yes | true no-mock HTTP | `API_tests/test_frontend_components.py` | `API_tests/test_frontend_components.py:test_schedules_page_blocked_for_front_desk` | `fullstack/backend/src/routes/ui_routes.py:schedules_page` |
| `GET /ui/tables` | yes | true no-mock HTTP | `API_tests/test_frontend_components.py` | `API_tests/test_frontend_components.py:test_tables_page_blocked_for_front_desk` | `fullstack/backend/src/routes/ui_routes.py:tables_page` |
| `GET /ui/tickets` | yes | true no-mock HTTP | `API_tests/test_routes.py` | `API_tests/test_routes.py:test_authenticated_ui_loads` | `fullstack/backend/src/routes/ui_routes.py:tickets_page` |

## API Test Classification
1. True No-Mock HTTP
- Flask app bootstrapped and HTTP exercised through test client (`API_tests/conftest.py:10-25`).
- Real route handlers are invoked via `client.get/post/put/...` across API/UI/partials test files.
- E2E uses real HTTP + browser (`E2E_tests/conftest.py`, `E2E_tests/tests/*.py`).

2. HTTP with Mocking
- **None detected** for transport/controller/service-path mocking in HTTP route tests.

3. Non-HTTP (unit/integration without HTTP)
- Extensive unit tests in `unit_tests/` for repositories/services/security/schema/models.

## Mock Detection
- Detected patching in HTTP suites is configuration override only:
  - `monkeypatch.setattr(_es, "EXPORT_OUTPUT_DIR", ...)` in
    - `API_tests/test_routes.py:36`
    - `API_tests/test_flow_coverage.py:28`
    - `API_tests/test_deep_coverage.py:37`
    - `API_tests/test_coverage_closure.py:48`
    - `API_tests/test_ui_routes.py:36`
    - `API_tests/test_frontend_components.py:63`
    - `API_tests/test_seed_verification.py:22,116`
- No evidence of mocking transport/controller/service execution paths for endpoint tests.

## Coverage Summary
- Total endpoints: **91**
- Endpoints with HTTP tests: **91**
- Endpoints with true no-mock HTTP tests: **91**
- HTTP coverage: **100.00%**
- True API coverage: **100.00%**

## Unit Test Summary
### Backend Unit Tests
- Present: **YES**
- Evidence files (examples):
  - `unit_tests/test_services.py`
  - `unit_tests/test_repositories.py`
  - `unit_tests/test_security.py`
  - `unit_tests/test_hardening.py`
  - `unit_tests/test_schema.py`
  - `unit_tests/test_models.py`
- Modules covered:
  - controllers/routes (via API tests)
  - services
  - repositories
  - auth/security/role gates/middleware behavior
- Important backend modules NOT tested: none obvious from static route coverage perspective; all registered endpoints have HTTP evidence.

### Frontend Unit Tests (STRICT)
- Frontend test files:
  - `API_tests/test_frontend_components.py`
  - `API_tests/test_ui_routes.py`
- Frameworks/tools detected:
  - `pytest` (`import pytest`)
- Components/modules covered:
  - login page and form contracts
  - shared base template wiring
  - UI page rendering contracts and role gates
  - HTMX/page-level component attributes
- Important frontend components/modules NOT tested:
  - no direct JS module unit tests for `fullstack/backend/static/js/*` (vendored HTMX files are not app-authored units)
- **Frontend unit tests: PRESENT**

### Cross-Layer Observation
- Backend and frontend coverage is more balanced than prior state.
- Backend remains deeper in branch/validation density; frontend now has substantial template/component-level assertions.

## API Observability Check
- Strong: tests include endpoint path, request payload/query, and response assertions across `API_tests/test_coverage_closure.py`, `API_tests/test_deep_coverage.py`, `API_tests/test_ui_routes.py`, `API_tests/test_frontend_components.py`.
- Weak pockets remain in some matrix-style redirect checks where assertion focus is status/location only.

## Test Quality & Sufficiency
- Success paths: strong coverage.
- Failure/edge/validation/auth paths: strong coverage.
- Integration boundaries: API + E2E present.
- `run_tests.sh` is Docker-based and compliant (`run_tests.sh:35-45`).

## Tests Check
- Static inspection only performed.
- No code/test/container execution performed.

## Test Coverage Score (0–100)
- **96/100**

## Score Rationale
- Full endpoint HTTP coverage with real route invocation.
- No significant HTTP-path mocking detected.
- Frontend testing gap is materially reduced with component/page contract tests.
- Minor deductions for some shallow assertion pockets and limited direct JS-unit granularity.

## Key Gaps
1. Some UI tests still prioritize status/redirect over deeper semantic payload assertions.
2. Frontend tests are template/page-contract heavy; minimal direct unit-level logic isolation for client-side scripts.

## Confidence & Assumptions
- Confidence: high for endpoint and README hard-gate mapping from static files.
- Assumption: Flask test client route calls represent real handler execution (fixture wiring confirms app bootstrap and client usage).

## Test Coverage Audit Verdict
- **PASS**

---

# README Audit

## High Priority Issues
- None.

## Medium Priority Issues
- None.

## Low Priority Issues
1. Minor terminology inconsistency: README body mentions both `docker-compose` and `docker compose` forms; both are valid but wording can be tightened for consistency (`README.md:57`, `README.md:73`).

## Hard Gate Failures
- None.

## README Verdict
- **PASS**

## Engineering Quality
- Tech stack clarity: strong (`README.md:7-13`).
- Architecture explanation: strong and structured (`README.md:15-45`).
- Testing instructions: clear Docker-only flow (`README.md:87-120`).
- Security and roles: clearly documented (`README.md:177-193`).
- Workflow and credentials: consistent with seeded-runtime behavior and role access (`README.md:77`, `README.md:122-176`; `docker-compose.yml:34`, `docker-compose.yml:68`; `fullstack/backend/app.py:155-158`).
- Verification method: explicit API + browser validation steps are present (`README.md:139-176`).

## README Audit Verdict
- **PASS**
