"""Repeat the selected review checks; never use application/hosted connections."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OFFLINE_MODULES = ('s1_claim_gates s1_resources s1_failure s1_process s1_activation s1_request_transport s1_observation probe_reproducibility read_only_probe local_query_metrics par_qualification_packet maintenance_connection planning_numbers backend_planning_prices monetary_completeness catalog_reads db_auxiliary db_tls hosted_auxiliary_trial hosted_backup hosted_backup_cli hosted_build_workflows '
 'managed_development rotate_build_connections provision_build_connections staff_response staff_pin_security pg_routes pg_migrations '
 'connection_transition transition_permissions parallel_install_plan parallel_rotation_review credential_retirement_review '
 'client_handoff_review local_install_recovery local_supervisor_checkpoint local_parallel_install combined_rotation_rehearsal readonly_snapshot '
 'combined_rehearsal_result pooler_denial_contract pooler_drain_trial review_guards review_test_runner').split()
OFFLINE_CLASSES = ('inventory_pars::InventoryParValidationTests catalog_integrity::CatalogValidationTests backup_fingerprint::FingerprintGuards deployment_readiness::ReadinessConfigurationTests runtime_permissions::RuntimeProfileTests '
 'runtime_permissions::RuntimeFixtureSafetyTests hosted_test_trial::HostedTrialGuards hosted_test_trial::TrialPoolTests '
 'schema_reconciliation::SchemaComparisonTests native_backup::BackupSafetyTests menu_contract::MenuModelTests '
 'menu_contract::MenuGraphValidationTests native_purchases::ParserTests '
 'apply_additive_migration::AdditivePlanGuards hosted_additive_index::HostedAdapterGuards '
 'hosted_additive_index::HostedReceiptGuards hosted_additive_index::HostedWriterGuards').split()
OFFLINE_CLASSES += ['reviewed_par_install::ParInstallGuards','reviewed_par_install::ParInstallReceiptTests',
                    's1_observation_pg::CollectorFixtureSafetyTests',
                    'par_role_preflight::ParRolePreflightGuards','deployment_readiness::ReadinessBatchTests',
                    'batched_fingerprints::BatchedFingerprintGuards']
DATABASE_CASES = (
 ('s1_observation_pg','S1CollectorDatabaseTests','test_complete_collector_reads_real_metadata_ledger_and_audit_without_writes'),
 ('s1_observation_pg','S1CollectorDatabaseTests','test_real_disposable_identity_without_adapter_is_refused_and_closed'),
 ('s1_observation_pg','S1CollectorDatabaseTests','test_real_ledger_shape_failure_preserves_prefix_and_skips_audit'),
 ('s1_observation_pg','S1CollectorDatabaseTests','test_seventy_ledger_rows_report_full_aggregate_and_keep_newest_sixty_four'),
 ('s1_observation_pg','S1CollectorDatabaseTests','test_server_statement_timeout_has_sqlstate_and_label_before_client_deadline'),
 ('s1_observation_pg','S1CollectorDatabaseTests','test_untruncated_coverage_and_newest_session_groups_use_one_observation'),
 ('read_only_probe_pg','ReadOnlyProbeDatabaseTests','test_complete_two_families_preserve_rows_catalog_sequence_and_independent_hash_formats'),
 ('read_only_probe_pg','ReadOnlyProbeDatabaseTests','test_full_cursor_fallback_and_sequences_are_included_in_envelopes'),
 ('read_only_probe_pg','ReadOnlyProbeDatabaseTests','test_unknown_inventory_or_unapproved_discovery_refuses_before_hashing'),
 ('read_only_probe_pg','ReadOnlyProbeDatabaseTests','test_missing_original_and_backup_catalog_or_relation_results_fail_closed'),
 ('read_only_probe_pg','ReadOnlyProbeDatabaseTests','test_snapshot_enforces_readonly_and_refuses_every_mutation_and_sequence_advance'),
 ('read_only_probe_pg','ReadOnlyProbeDatabaseTests','test_timeout_cancel_and_resource_failure_rollback_without_retry'),
 ('read_only_probe_pg','ReadOnlyProbeDatabaseTests','test_observed_slow_query_holds_and_later_family_never_runs'),
 ('batched_fingerprints','BatchedFingerprintDatabaseTests','test_original_projection_oracle_exclusions_and_chunk_boundaries'),
 ('batched_fingerprints','BatchedFingerprintDatabaseTests','test_backup_oracle_fallback_sequences_and_path_counters'),
 ('batched_fingerprints','BatchedFingerprintDatabaseTests','test_late_rows_and_original_columns_detect_drift'),
 ('batched_fingerprints','BatchedFingerprintDatabaseTests','test_missing_duplicate_extra_malformed_positions_refuse_without_fallback'),
 ('batched_fingerprints','BatchedFingerprintDatabaseTests','test_timeout_fails_closed_and_recovers_same_connection'),
 ('batched_fingerprints','BatchedFingerprintDatabaseTests','test_new_metric_bindings_attribute_both_families'),
 ('batched_fingerprints','BatchedFingerprintDatabaseTests','test_snapshot_phases_do_not_reuse_digests'),
 ('local_query_metrics_pg','LocalQueryMetricsDatabaseTests','test_iteration_cached_uncached_empty_exact_batch_and_early_exit'),
 ('local_query_metrics_pg','LocalQueryMetricsDatabaseTests','test_awaited_cursor_manual_fetch_forward_and_driver_refusals'),
 ('local_query_metrics_pg','LocalQueryMetricsDatabaseTests','test_nested_context_and_manual_transactions_preserve_commit_and_rollback'),
 ('local_query_metrics_pg','LocalQueryMetricsDatabaseTests','test_timeout_and_cancellation_are_propagated_and_connection_recovers'),
 ('local_query_metrics_pg','LocalQueryMetricsDatabaseTests','test_actual_backup_sequence_and_fallback_match_unwrapped_results'),
 ('inventory_pars','InventoryParTests','test_recovery_status_is_readonly_and_exact_retries_preserve_accounting'),
 ('inventory_pars','InventoryParTests','test_recovery_distinguishes_saved_superseded_and_unsaved_fenced_requests'),
 ('inventory_pars','InventoryParTests','test_recovery_rejects_changed_identity_and_holds_changed_profiles'),
 ('inventory_pars','InventoryParTests','test_recovery_withdrawal_authorization_and_missing_storage'),
 ('runtime_permissions','RuntimePermissionTests','test_later_par_schema_is_held_without_inheriting_candidate_access'),
 ('inventory_pars','InventoryParTests','test_unconfirmed_legacy_default_and_missing_installation_are_not_zero_targets'),
 ('inventory_pars','InventoryParTests','test_exact_target_zero_withdrawal_and_actor_are_metadata_only'),
 ('inventory_pars','InventoryParTests','test_parallel_retries_and_stale_versions_never_replace_a_newer_target'),
 ('inventory_pars','InventoryParTests','test_changed_supplier_keeps_target_and_changed_count_conversion_requires_review'),
 ('inventory_pars','InventoryParTests','test_missing_units_wrong_location_access_and_missing_revision_are_refused'),
 ('inventory_pars','InventoryParTests','test_history_guards_and_failed_insert_roll_back_review_and_store_revision'),
 ('inventory_pars','InventoryParTests','test_review_history_exact_retry_and_accounting_survive_disposable_restore'),
 ('inventory_pars','InventoryParTests','test_small_and_large_exact_targets_roundtrip_without_float_rounding'),
 ('inventory_pars','InventoryParTests','test_fixed_decimal_save_replay_reads_and_history_preserve_exact_request_identity'),
 ('legacy_prep_atomicity','LegacyPrepAtomicityTests','test_single_item_extreme_quantities_refuse_before_any_stock_write'),
 ('legacy_prep_atomicity','LegacyPrepAtomicityTests','test_single_item_finite_completion_and_zero_price_preserve_actual_facts'),
 ('legacy_prep_atomicity','LegacyPrepAtomicityTests','test_single_item_late_database_failure_rolls_back_stock_and_progress'),
 ('legacy_prep_atomicity','LegacyPrepAtomicityTests','test_direct_item_missing_price_has_specific_message_without_any_stock_write'),
 ('legacy_prep_atomicity','LegacyPrepAtomicityTests','test_direct_missing_later_price_is_refused_before_any_stock_write'),
 ('legacy_prep_atomicity','LegacyPrepAtomicityTests','test_task_missing_later_price_is_refused_before_any_stock_write'),
 ('legacy_prep_atomicity','LegacyPrepAtomicityTests','test_unknown_supplier_conversion_is_refused_before_any_prep_write'),
 ('legacy_prep_atomicity','LegacyPrepAtomicityTests','test_legacy_helper_ignores_unavailable_supplier_and_keeps_selected_unknown'),
 ('shared_catalog','SharedCatalogTests','test_backend_planning_prices_use_location_alias_and_never_change_actual_report'),
 ('shared_catalog','SharedCatalogTests','test_monetary_reader_holds_preserve_adapter_evidence_and_actual_report'),
 ('legacy_prep_atomicity','LegacyPrepAtomicityTests','test_direct_later_invalid_cost_or_arithmetic_reaches_no_stock_writes'),
 ('legacy_prep_atomicity','LegacyPrepAtomicityTests','test_task_later_invalid_cost_or_arithmetic_reaches_no_stock_writes'),
 ('legacy_prep_atomicity','LegacyPrepAtomicityTests','test_direct_happy_path_deducts_both_and_writes_one_log'),
 ('legacy_prep_atomicity','LegacyPrepAtomicityTests','test_task_happy_path_deducts_both_and_updates_progress_once'),
 ('legacy_prep_atomicity','LegacyPrepAtomicityTests','test_direct_late_database_error_rolls_back_all_facts'),
 ('legacy_prep_atomicity','LegacyPrepAtomicityTests','test_task_late_database_error_rolls_back_all_facts_and_progress'),
 ('legacy_prep_atomicity','LegacyPrepAtomicityTests','test_unsafe_output_or_container_is_refused_before_any_stock_write'),
 ('shared_catalog','SharedCatalogTests','test_unsafe_planning_catalog_keeps_actual_report_and_reads_available'),
 ('legacy_prep_cutover','LegacyPrepCutoverTests','test_old_reads_work_before_cutover_then_flags_off_schema_holds_current_figures'),
 ('legacy_prep_cutover','LegacyPrepCutoverTests','test_flags_off_writers_cannot_restart_parallel_stock_after_batch_schema'),
 ('shared_catalog','SharedCatalogTests','test_catalog_supported_decimal_boundaries_roundtrip_without_rounding'),
 ('shared_catalog','SharedCatalogTests','test_catalog_extreme_decimals_are_422_without_changing_catalog_or_revision'),
 ('shared_catalog','SharedCatalogTests','test_exact_catalog_roundtrip_keeps_shared_metadata_profiles_and_actual_report'),
 ('manual_purchases','ManualPurchaseTests','test_capture_recovery_manual_absent_saved_and_partial_attachment_reads_are_readonly'),
 ('manual_purchases','ManualPurchaseTests','test_capture_recovery_rejects_changed_manual_body_foreign_scope_and_replay_actor'),
 ('manual_purchases','ManualPurchaseTests','test_capture_recovery_csv_requires_projection_and_raw_source_requires_only_bytes'),
 ('manual_purchases','ManualPurchaseTests','test_capture_recovery_filename_transport_matches_raw_probe_without_decoding_literals'),
 ('manual_purchases','ManualPurchaseTests','test_capture_recovery_status_requires_capture_role_and_location_without_writes'),
 ('backup_fingerprint','FingerprintDatabaseTests','test_server_cursor_fallback_and_legacy_fingerprints_are_equivalent'),
 ('apply_additive_migration','HostedBackupLocalDatabaseTests','test_export_deadline_and_operator_cancel_remove_only_owned_database_sessions'),
 ('apply_additive_migration','HostedBackupLocalDatabaseTests','test_direct_maintenance_export_restores_rows_and_closes_owned_transport'),
 ('apply_additive_migration','HostedBackupLocalDatabaseTests','test_encrypted_export_restore_and_close_failure_stay_disposable'),
 ('posted_invoice_corrections','PostedInvoiceCorrectionTests','test_recovery_identity_survives_same_version_correction_and_exact_retry'),
 ('posted_invoice_corrections','PostedInvoiceCorrectionTests','test_recovery_identity_survives_reissued_version_correction_and_exact_retry'),
 ('posted_invoice_corrections','PostedInvoiceCorrectionTests','test_competing_review_reads_winning_request_identity_without_another_posting'),
 ('posted_invoice_corrections','PostedInvoiceCorrectionTests','test_submitted_correction_status_before_and_after_commit_is_readonly_and_exact_retry_preserves_all_facts'),
 ('posted_invoice_corrections','PostedInvoiceCorrectionTests','test_submitted_correction_status_distinguishes_competitor_later_replacement_and_wrong_actor_or_body'),
 ('posted_invoice_corrections','PostedInvoiceCorrectionTests','test_submitted_correction_status_holds_changed_period_source_and_access_without_writes'),
 ('posted_invoice_corrections','PostedInvoiceCorrectionTests','test_submitted_correction_replay_requires_same_actor_version_and_body'),
 ('posted_invoice_corrections','PostedInvoiceCorrectionTests','test_submitted_correction_foreign_invoice_key_is_refused_without_returning_foreign_details'),
 ('posted_invoice_corrections','PostedInvoiceCorrectionTests','test_submitted_correction_discard_race_only_first_stale_predecessor_command_applies'),
 ('native_order_receiving','NativeOrderReceivingTests','test_unknown_catalog_factor_has_separate_confirmed_physical_profile'),
 ('native_order_receiving','NativeOrderReceivingTests','test_profile_retry_staleness_and_fixed_base_unit_guards'),
 ('combined_prep_cutover','CombinedPrepCutoverTests','test_combined_trial_counts_purchases_staff_containers_period_correction_and_restore'),
 ('owner_runtime_recovery','OwnerRuntimeRecoveryTests','test_ordinary_owner_inventory_transactions_and_restore_preserve_exact_replay'),
 ('prep_correction_review','PrepCorrectionReviewTests','test_dependency_review_uses_location_identity_and_feature_boundary'),
 ('prep_correction_review','PrepCorrectionReviewTests','test_dependency_graph_holds_current_use_but_keeps_released_descendants_as_history'),
 ('menu_contract','MenuContractTests','test_history_review_recipe_deletion_requires_revision_and_location'),
 ('menu_contract','MenuContractTests','test_history_review_cascading_stock_and_planning_references_are_retained'),
 ('menu_contract','MenuContractTests','test_definition_changes_leave_actual_report_and_purchase_facts_unchanged'),
 ('order_commands','OrderCommandTests','test_order_editor_cannot_approve_even_after_another_editor_changes_content'),
 ('order_commands','OrderCommandTests','test_installed_workflow_holds_legacy_and_flag_off_writes_before_side_effects'),
 ('staff_prep_counts','StaffPrepCountsTests','test_review_corrections_count_author_cannot_accept_after_staff_revision'),
 ('staff_prep_production','StaffProductionTests','test_review_corrections_production_author_and_claimed_roster_cannot_accept'),
 ('staff_prep_production','StaffProductionTests','test_review_corrections_production_root_collision_across_stores_and_revision_ids'),
 ('staff_prep_production','StaffProductionTests','test_review_corrections_production_cross_module_key_rolls_back_all_effects'),
 ('container_waste','ContainerWasteTests','test_review_corrections_waste_cross_module_key_rolls_back_contents_and_journal'),
 ('container_waste','ContainerWasteTests','test_direct_waste_single_withdrawal_storage_service_and_food_cost_independent'),
 ('native_purchases','PurchaseIntegrationTests','test_received_date_cost_fee_tax_and_track_isolation'),
 ('native_purchases','PurchaseIntegrationTests','test_capture_roundtrip_all_raw_and_typed_fields'),
 ('native_purchases','PurchaseIntegrationTests','test_current_source_follows_reissued_invoice_across_files_without_writes'),
 ('native_purchases','PurchaseIntegrationTests','test_source_lookup_index_preserves_reads_and_supports_selective_lookup'),
 ('deployment_readiness','DeploymentReadinessTests','test_readiness_holds_missing_or_wrong_source_lookup_index'),
 ('deployment_readiness','DeploymentReadinessTests','test_readiness_detects_function_exposure_then_hardens_full_chain_and_restores'),
 ('actual_inventory','ActualInventoryTests','test_explicit_value_usage_math_ignores_sales_flag_and_prep'),
 ('actual_inventory','ActualInventoryTests','test_prepared_items_excluded_and_fixed_unit_conflict_rolls_back'))
DATABASE_CASES += tuple(('apply_additive_migration', 'AdditiveDatabaseTests', name) for name in (
 'test_readonly_nested_failure_rolls_back_savepoint_and_keeps_outer_transaction',
 'test_dry_run_is_readonly_and_success_is_durable_without_business_changes',
 'test_failed_ledger_insert_rolls_back_the_index_and_all_history',
 'test_lost_commit_ack_is_unknown_until_fresh_read_and_never_blindly_reapplied',
 'test_partial_or_changed_native_body_and_changed_older_history_are_refused',
 'test_changed_checksum_or_database_rows_hold_before_ddl',
 'test_existing_or_wrong_index_without_ledger_is_refused',
 'test_unrelated_readiness_failure_is_refused',
 'test_lock_contention_times_out_without_recording_or_index_creation',
 'test_wrong_database_identity_and_nested_application_are_refused',
 'test_reconcile_refuses_partial_index_and_forged_additive_history',
 'test_unresolved_writer_holds_reconciliation_until_disconnect_proves_rollback',
 'test_cli_modes_require_reviewed_plan_hash_and_keep_existing_receipts'))
DATABASE_CASES += tuple(('hosted_additive_index', 'HostedAdapterDatabaseTests', name) for name in (
 'test_hosted_wrapper_is_readonly_then_preserves_exact_food_cost',
 'test_hosted_permission_checks_reject_client_private_access',
 'test_hosted_permission_checks_refuse_initial_ledger_column_exposure',
 'test_changed_ledger_defaults_permissions_and_uniqueness_hold_before_ddl',
 'test_duplicate_versions_cannot_collapse_into_fingerprint_map',
 'test_backup_sequence_drift_is_refused_inside_locked_apply',
 'test_precommit_backup_guard_failure_rolls_back_index_and_ledger',
 'test_hosted_commit_ack_loss_reconciles_without_reapplication',
 'test_hosted_active_writer_prevents_false_unapplied_reconciliation',
 'test_write_committing_during_lock_wait_is_seen_before_ddl',
 'test_reviewed_idle_login_holds_prepare_and_apply_before_table_locks',
 'test_unknown_login_write_transaction_holds_but_idle_observer_does_not',
 'test_activity_refresh_sees_new_session_in_same_transaction',
 'test_new_login_after_preflight_is_refused_by_locked_guard',
 'test_restricted_observer_cannot_claim_other_sessions_are_drained'))
DATABASE_CASES += tuple(('par_role_preflight', 'ParRolePreflightDatabaseTests', name) for name in (
 'test_readonly_report_keeps_catalog_accounting_and_role_inventory_unchanged',
 'test_real_refusals_report_only_the_evaluated_prefix',
 'test_public_and_extensions_findings_are_observed_without_waiving_installer_rules',
 'test_injected_write_is_refused_and_connection_is_closed_without_a_report'))
DATABASE_CASES += tuple(('reviewed_par_install', 'ParInstallDatabaseTests', name) for name in (
 'test_batched_readiness_matches_original_predicates_and_diagnostics',
 'test_direct_snapshot_retains_legacy_fields_without_discarded_capture',
 'test_outcome_reuses_only_current_validated_projection_and_reads_fresh',
 'test_explicit_backend_access_survives_prepare_apply_reconcile_without_new_par_access',
 'test_backend_classification_and_plan_bindings_cannot_be_omitted_or_relabelled',
 'test_backend_ledger_table_and_column_exposure_hold_before_plan',
 'test_backend_trust_never_waives_browser_private_access',
 'test_backend_authority_membership_and_future_defaults_are_held',
 'test_backend_hold_rules_classify_real_catalog_refusals',
 'test_new_par_access_and_late_backend_grants_stay_blocked',
 'test_classified_backend_still_holds_live_writers_and_changed_permissions',
 'test_browser_column_only_access_is_denied_with_a_classified_backend',
 'test_readonly_plan_atomic_install_exact_delta_and_food_cost_preserved',
 'test_changed_source_plan_reference_flags_or_backup_binding_are_refused',
 'test_prior_missing_changed_extra_history_and_wrong_index_are_held',
 'test_ledger_failure_rolls_back_table_function_and_store_state',
 'test_lost_commit_ack_reconciles_and_reapply_is_refused',
 'test_unresolved_transaction_blocks_false_unapplied_result_until_disconnect',
 'test_partial_object_and_postcommit_security_tampering_are_refused',
 'test_default_grant_and_unexpected_policy_cannot_hide_in_new_delta',
 'test_hosted_guards_preserve_backed_up_rows_and_new_empty_table',
 'test_drift_late_writer_and_precommit_guard_failure_roll_back',
 'test_known_and_unknown_writer_guards_and_hidden_activity_fail_closed',
 'test_write_committing_during_lock_wait_invalidates_plan',
 'test_real_encrypted_export_and_restore_retain_installed_par_history_and_food_cost'))

# Manager receiving journal: explicit local/CI selection, no hosted configuration.
OFFLINE_CLASSES += ['manager_handoff::HandoffValidationTests','manager_handoff::HandoffActorTests']
OFFLINE_CLASSES += ['manager_handoff_install::InstallGuards']
DATABASE_CASES += tuple(('manager_handoff_install','InstallDatabaseTests',name) for name in (
 'test_atomic_three_payloads_and_actual_restricted_logins',
 'test_namespace_version_source_and_changed_baseline_refuse',
 'test_ledger_late_failure_rolls_back_schema_permissions_and_settings',
 'test_unknown_commit_requires_readonly_reconciliation_and_no_retry',
 'test_policy_privilege_guard_and_owner_drift_hold',
 'test_encrypted_seven_schema_restore_preserves_history_acl_guards_and_exact_replay'))
DATABASE_CASES += tuple(('manager_handoff','HandoffDatabaseTests',name) for name in (
 'test_shared_draft_submit_correct_history_and_previous_are_stock_independent',
 'test_before_after_commit_status_exact_retry_and_changed_key_conflicts',
 'test_parallel_creates_same_keys_and_stale_edits_never_overwrite',
 'test_current_account_revocation_applies_to_reads_commands_and_saved_receipts',
 'test_feature_missing_timezone_inactive_store_future_date_and_foreign_scope_hold',
 'test_missing_storage_disabled_guards_and_malformed_requests_hold_without_writes',
 'test_immutable_history_context_and_late_failure_rollback_all_three_relations',
 'test_owner_truncate_refuses_each_journal_table_and_disabled_guard_holds',
 'test_historical_backfill_keeps_business_date_distinct_from_recording_time',
 'test_history_pages_and_foreign_note_ids_never_return_other_store',
 'test_disposable_dump_restore_preserves_context_history_and_exact_replay',
 'test_disposable_role_matrix_and_catalog_snapshot'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile',choices=('offline','database'))
    parser.add_argument('--report',type=Path,required=True,help='New JUnit XML evidence path')
    parser.add_argument('--list',action='store_true',help='List selected targets without running')
    args = parser.parse_args()
    targets = (['backend/tests/test_'+name+'.py' for name in OFFLINE_MODULES] +
               ['backend/tests/test_'+name.replace('::','.py::',1) for name in OFFLINE_CLASSES]
               if args.profile == 'offline' else
               ['backend/tests/test_' + file + '.py::' + cls + '::' + method for file,cls,method in DATABASE_CASES]
               + ['backend/tests/test_item_changes.py'])
    if args.list:
        print('\n'.join(targets)); return
    report = args.report.resolve()
    if report.exists(): parser.error('Use a new report path to preserve previous evidence')
    env = os.environ.copy()
    dsn = env.get('NATIVE_PURCHASE_TEST_DSN','')
    for key in list(env):
        if key.startswith('REACT_APP_') or key.endswith('_ENABLED') or key in (
                'DATABASE_URL','AUXILIARY_DATABASE_URL','MAINTENANCE_DATABASE_URL','NATIVE_PURCHASE_TEST_DSN','TEST_PG_URL','BOOTSTRAP_TOKEN'):
            env.pop(key)
    env.update(DATABASE_URL='',AUXILIARY_DATABASE_URL='',PYTHON_DOTENV_DISABLED='1',
               USE_PG='true',AUTH_REQUIRED='true',AUTH_SECRET='synthetic-review-test-secret-only',
               MONGO_URL='mongodb://127.0.0.1:27017',DB_NAME='synthetic_review_test')
    if args.profile == 'database':
        try:
            parsed = urlsplit(dsn)
            allowed = (parsed.scheme in ('postgres','postgresql') and parsed.hostname in ('127.0.0.1','localhost','::1')
                       and parsed.path == '/native_purchase_test_control' and parsed.username == 'purchase_implementation_test'
                       and not parsed.query and not parsed.fragment and parsed.port is not None)
        except ValueError: allowed = False
        if not allowed: parser.error('Database checks require the dedicated loopback disposable control database')
        dump = Path(env.get('NATIVE_BACKUP_PG_DUMP',''))
        if not dump.is_file(): parser.error('Set NATIVE_BACKUP_PG_DUMP to the local PostgreSQL pg_dump executable')
        env['NATIVE_PURCHASE_TEST_DSN'] = dsn
    env['PYTHONPATH'] = os.pathsep.join([str(ROOT/'tools/ops'),str(ROOT/'backend'),str(ROOT/'backend/tests'),str(ROOT),env.get('PYTHONPATH','')])
    report.parent.mkdir(parents=True,exist_ok=True)
    check = subprocess.run([sys.executable,str(ROOT/'tools/review_contracts.py'),'--check'],cwd=ROOT,env=env)
    if check.returncode: raise SystemExit(check.returncode)
    result = subprocess.run([sys.executable,'-m','pytest','--noconftest',*targets,'-q','--tb=short',
                            '-p','no:cacheprovider','--junitxml='+str(report)],cwd=ROOT,env=env)
    if result.returncode: raise SystemExit(result.returncode)
    suites = ET.parse(report).getroot().iter('testsuite')
    counts = {key:0 for key in ('tests','failures','errors','skipped')}
    for suite in suites:
        for key in counts: counts[key] += int(suite.get(key,'0'))
    if not counts['tests'] or any(counts[key] for key in ('failures','errors','skipped')):
        raise SystemExit('Selected review checks did not all execute and pass: '+str(counts))
    print('Selected review checks passed: '+str(counts))


if __name__ == '__main__': main()
