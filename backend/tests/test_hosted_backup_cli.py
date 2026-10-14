"""Standalone backup output preserves safe categories and excludes private text."""
from contextlib import redirect_stdout
import io
import json
import unittest
from unittest.mock import patch
import hosted_backup as backup
import hosted_backup_cli as cli


class BackupCliTests(unittest.TestCase):
    def test_real_error_handler_emits_original_sqlstate_and_cleanup_categories(self):
        error = ConnectionError('TEST ONLY private-password postgres://private')
        error.sqlstate = '08003'; error.snapshotCleanupErrorType = 'InterfaceError'
        error.connectionCloseErrorType = 'RuntimeError'
        error.backupDiagnostics = {'format':'jaymax-backup-diagnostics-v1',
            'phases':[{'phase':'fingerprint','elapsedSeconds':1.5,'outcome':'held','sql':'private-password'}],
            'serverLimits':{'statement_timeout':{'value':120000,'unit':'ms','private':'secret'}},
            'clientLimits':{'commandSeconds':60},'private':'postgres://private'}
        def fail(coroutine):
            coroutine.close()
            raise error
        output = io.StringIO()
        with patch.object(cli.asyncio,'run',side_effect=fail), redirect_stdout(output):
            self.assertEqual(cli.run(),2)
        result = json.loads(output.getvalue())
        self.assertEqual(result['status'],'held')
        self.assertEqual(result['errorType'],'ConnectionError')
        self.assertEqual(result['sqlState'],'08003')
        self.assertEqual(result['snapshotCleanupErrorType'],'InterfaceError')
        self.assertEqual(result['connectionCloseErrorType'],'RuntimeError')
        self.assertEqual(result['backupDiagnostics']['phases'],
                         [{'phase':'fingerprint','elapsedSeconds':1.5,'outcome':'held'}])
        self.assertFalse(result['operationalReleaseApproved'])
        self.assertNotIn('private-password',output.getvalue())
        self.assertNotIn('postgres://',output.getvalue())

    def test_malformed_diagnostics_cannot_hide_original_error_or_expose_values(self):
        error = ConnectionError('TEST ONLY private')
        error.sqlstate = '08003'
        for metadata in (None,'private',{'format':'untrusted','private':'secret'},
                {'format':'jaymax-backup-diagnostics-v1','phases':[
                    {'phase':{},'elapsedSeconds':1,'outcome':'held'},
                    {'phase':'fingerprint','elapsedSeconds':float('nan'),'outcome':'held'},
                    {'phase':'fingerprint','elapsedSeconds':10**1000,'outcome':'held'},
                    {'phase':'private secret','elapsedSeconds':1,'outcome':'held'}],
                 'serverLimits':{'statement_timeout':{'value':'private','unit':'ms'}},
                 'clientLimits':{'commandSeconds':True}, 'sql':'private secret'}):
            with self.subTest(kind=type(metadata).__name__):
                error.backupDiagnostics=metadata
                encoded=json.dumps(cli.held_result(error))
                self.assertNotIn('private',encoded)
                self.assertEqual(json.loads(encoded)['sqlState'],'08003')

    def test_success_keeps_zero_exit(self):
        def finish(coroutine): coroutine.close()
        with patch.object(cli.asyncio,'run',side_effect=finish):
            self.assertEqual(cli.run(),0)
