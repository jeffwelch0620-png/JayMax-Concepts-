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
                    NATIVE_PURCHASE_TEST_DSN='private-test',CATALOG_MAPPING_ENABLED='true',REACT_APP_USE_PG='true')),\
                    patch('sys.argv',['runner','offline','--report',str(report)]),patch.object(runner.subprocess,'run',side_effect=run):
                with self.assertRaises(SystemExit): runner.main()
            self.assertEqual(len(captured),2)
            for env in captured:
                self.assertEqual(env['DATABASE_URL'],''); self.assertEqual(env['AUXILIARY_DATABASE_URL'],'')
                self.assertEqual(env['PYTHON_DOTENV_DISABLED'],'1')
                self.assertNotIn('NATIVE_PURCHASE_TEST_DSN',env); self.assertNotIn('CATALOG_MAPPING_ENABLED',env)
                self.assertNotIn('REACT_APP_USE_PG',env)
