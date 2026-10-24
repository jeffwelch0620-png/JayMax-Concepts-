"""Review runner must not inherit live connections or pass skipped checks."""
import importlib.util
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('review_runner',ROOT/'tools/run_review_tests.py')
runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)


class ReviewRunnerTests(unittest.TestCase):
    def test_n3_real_collector_cases_stay_in_database_selection(self):
        expected={('s1_observation_pg','S1CollectorDatabaseTests',name) for name in (
            'test_complete_collector_reads_real_metadata_ledger_and_audit_without_writes',
            'test_real_disposable_identity_without_adapter_is_refused_and_closed',
            'test_real_ledger_shape_failure_preserves_prefix_and_skips_audit',
            'test_seventy_ledger_rows_report_full_aggregate_and_keep_newest_sixty_four',
            'test_server_statement_timeout_has_sqlstate_and_label_before_client_deadline',
            'test_untruncated_coverage_and_newest_session_groups_use_one_observation')}
        self.assertEqual({case for case in runner.DATABASE_CASES if case[0]=='s1_observation_pg'},expected)
        self.assertNotIn('s1_observation_pg',runner.OFFLINE_MODULES)
        self.assertIn('s1_observation_pg::CollectorFixtureSafetyTests',runner.OFFLINE_CLASSES)

    def test_remote_and_non_disposable_connections_stop_before_any_process(self):
        for dsn in ('postgresql://purchase_implementation_test@remote.invalid:5432/native_purchase_test_control',
                    'postgresql://purchase_implementation_test@127.0.0.1:5432/postgres',
                    'postgresql://owner@127.0.0.1:5432/native_purchase_test_control',
                    'postgresql://purchase_implementation_test@127.0.0.1:5432/native_purchase_test_control?service=remote'):
            with self.subTest(dsn=dsn),TemporaryDirectory() as tmp,patch.dict(os.environ,{'NATIVE_PURCHASE_TEST_DSN':dsn}),\
                    patch('sys.argv',['runner','database','--report',str(Path(tmp)/'result.xml')]),patch.object(runner.subprocess,'run') as run:
                with self.assertRaises(SystemExit) as error: runner.main()
                self.assertEqual(error.exception.code,2); run.assert_not_called()

    def test_offline_scrubs_live_configuration_and_holds_skipped_evidence(self):
        with TemporaryDirectory() as tmp:
            report = Path(tmp)/'result.xml'; captured=[]
            def run(command,**kwargs):
                captured.append(kwargs['env'])
                if '-m' in command: report.write_text('<testsuites><testsuite tests="1" skipped="1" failures="0" errors="0"/></testsuites>')
                return SimpleNamespace(returncode=0)
            with patch.dict(os.environ,dict(DATABASE_URL='private-live',AUXILIARY_DATABASE_URL='private-account',
                    MAINTENANCE_DATABASE_URL='private-maintenance',NATIVE_PURCHASE_TEST_DSN='private-test',CATALOG_MAPPING_ENABLED='true',REACT_APP_USE_PG='true')),\
                    patch('sys.argv',['runner','offline','--report',str(report)]),patch.object(runner.subprocess,'run',side_effect=run):
                with self.assertRaises(SystemExit): runner.main()
            self.assertEqual(len(captured),2)
            for env in captured:
                self.assertEqual(env['DATABASE_URL'],''); self.assertEqual(env['AUXILIARY_DATABASE_URL'],'')
                self.assertEqual(env['PYTHON_DOTENV_DISABLED'],'1')
                self.assertNotIn('NATIVE_PURCHASE_TEST_DSN',env); self.assertNotIn('CATALOG_MAPPING_ENABLED',env)
                self.assertNotIn('REACT_APP_USE_PG',env)
                self.assertNotIn('MAINTENANCE_DATABASE_URL',env)
