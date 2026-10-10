"""Repeat the selected review checks; never use application/hosted connections."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OFFLINE_MODULES = ('catalog_reads db_auxiliary db_tls hosted_auxiliary_trial hosted_backup hosted_build_workflows '
 'managed_development rotate_build_connections provision_build_connections staff_response pg_routes pg_migrations '
 'connection_transition transition_permissions parallel_install_plan parallel_rotation_review credential_retirement_review '
 'client_handoff_review local_install_recovery local_supervisor_checkpoint local_parallel_install combined_rotation_rehearsal '
 'combined_rehearsal_result pooler_denial_contract pooler_drain_trial review_guards review_test_runner').split()
OFFLINE_CLASSES = ('deployment_readiness::ReadinessConfigurationTests runtime_permissions::RuntimeProfileTests '
 'runtime_permissions::RuntimeFixtureSafetyTests hosted_test_trial::HostedTrialGuards hosted_test_trial::TrialPoolTests '
 'schema_reconciliation::SchemaComparisonTests native_backup::BackupSafetyTests menu_contract::MenuModelTests '
 'menu_contract::MenuGraphValidationTests native_purchases::ParserTests').split()
DATABASE_CASES = (
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
 ('actual_inventory','ActualInventoryTests','test_explicit_value_usage_math_ignores_sales_flag_and_prep'),
 ('actual_inventory','ActualInventoryTests','test_prepared_items_excluded_and_fixed_unit_conflict_rolls_back'))


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
                'DATABASE_URL','AUXILIARY_DATABASE_URL','NATIVE_PURCHASE_TEST_DSN','TEST_PG_URL','BOOTSTRAP_TOKEN'):
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
    env['PYTHONPATH'] = os.pathsep.join([str(ROOT/'backend'),str(ROOT/'backend/tests'),str(ROOT),env.get('PYTHONPATH','')])
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
