"""Standalone backup output preserves safe categories and excludes private text."""
from contextlib import redirect_stdout, redirect_stderr
import base64
import asyncio
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, AsyncMock
from cryptography.fernet import Fernet
import hosted_backup as backup
import hosted_backup_cli as cli


class BackupCliTests(unittest.TestCase):
    def test_operator_interrupt_keeps_safe_cancelled_export_artifact_evidence(self):
        cancelled=asyncio.CancelledError()
        cancelled.backupArtifacts={'privateKeyRetained':True,'finalBackupPresent':False}
        cancelled.backupDiagnostics={'format':'jaymax-backup-diagnostics-v1','exportReference':'c'*32}
        def stop(coroutine):
            coroutine.close()
            try:raise cancelled
            except asyncio.CancelledError:raise KeyboardInterrupt() from None
        output=io.StringIO()
        with patch.object(cli.asyncio,'run',side_effect=stop),redirect_stdout(output):
            self.assertEqual(cli.run(),130)
        result=json.loads(output.getvalue())
        self.assertEqual(result['backupArtifacts'],cancelled.backupArtifacts)
        self.assertEqual(result['backupDiagnostics']['exportReference'],'c'*32)

    def test_operator_interrupt_has_safe_held_exit(self):
        def stop(coroutine): coroutine.close();raise KeyboardInterrupt()
        output=io.StringIO()
        with patch.object(cli.asyncio,'run',side_effect=stop),redirect_stdout(output):
            self.assertEqual(cli.run(),130)
        self.assertEqual(json.loads(output.getvalue())['status'],'held')

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
                {'format':'jaymax-backup-diagnostics-v1','exportReference':'private secret'},
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

    def test_held_artifacts_and_limit_flag_are_boolean_only(self):
        error=ConnectionError('TEST ONLY private message')
        error.backupArtifacts={'privateKeyRetained':True,'encryptedPartialRetained':True,
            'rawPartialRetained':'private path','finalBackupPresent':False,
            'privateKey':'TEST ONLY secret','artifactInspectionHeld':True}
        error.backupDiagnostics={'format':'jaymax-backup-diagnostics-v1','limitReadHeld':True}
        result=cli.held_result(error)
        self.assertEqual(result['backupArtifacts'],{'privateKeyRetained':True,
            'encryptedPartialRetained':True,'finalBackupPresent':False,'artifactInspectionHeld':True})
        self.assertTrue(result['backupDiagnostics']['limitReadHeld'])
        self.assertNotIn('TEST ONLY',json.dumps(result))
        error.backupDiagnostics['limitReadHeld']='private'
        self.assertNotIn('limitReadHeld',cli.held_result(error)['backupDiagnostics'])


class CliAdapterBindingTests(unittest.IsolatedAsyncioTestCase):
    async def test_cli_migration_keys_bind_authenticated_archive_to_unchanged_adapter(self):
        import hosted_additive_index as adapter
        from test_hosted_additive_index import review, receipt, PROJECT
        captured={};progress_output=io.StringIO()
        async def capture(*args,**kwargs):
            captured.update(args[-1]);kwargs['progress']({'format':'jaymax-backup-progress-v1',
                'phase':'fingerprint','state':'running','elapsedSeconds':1})
            self.assertEqual(kwargs['timeout_seconds'],120)
            return {'status':'TEST ONLY collection boundary'}
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            argv=['hosted_backup_cli','export','--owner-config',str(root/'TEST_ONLY.env'),
                '--expected-project',PROJECT,'--pg-bin',str(root),'--timeout-seconds','120']
            with patch.object(sys,'argv',argv),patch.dict(os.environ,LOCALAPPDATA=str(root)),\
                 patch.object(cli,'dotenv_values',return_value={'DATABASE_URL':'TEST ONLY fictional DSN'}),\
                 patch.object(backup,'export_backup',side_effect=capture),redirect_stdout(io.StringIO()),redirect_stderr(progress_output):
                await cli.main()
            self.assertTrue(captured)
            self.assertTrue(all('\\' not in name for name in captured))
            repo=Path(cli.__file__).resolve().parents[1]
            for name,sha in captured.items(): self.assertEqual(sha,backup.digest((repo/name).read_bytes()))
            expected={p.relative_to(repo).as_posix():backup.digest(p.read_bytes())
                for folder in (repo/'migrations',repo/'supabase/migrations') for p in folder.glob('*.sql')}
            self.assertEqual(captured,expected)
            archive=b'TEST ONLY fictional adapter binding; not a database dump';key=Fernet.generate_key()
            manifest={'format':backup.FORMAT,'projectRef':PROJECT,'schemas':list(backup.SCHEMAS),
                'rowFingerprintAlgorithm':backup.ROW_ALGORITHM,'serverVersionNum':'170006',
                'archiveSha256':backup.digest(archive),'archiveBytes':len(archive),
                'createdAt':datetime.now(timezone.utc).isoformat(),'migrationFileHashes':captured,
                'tables':{adapter.LEDGER:{'rows':30,'sha256':'a'*64,'kind':'r'}},'catalog':{}}
            encrypted=root/'backup';key_file=root/'key';restored=root/'restored';original=root/'original'
            key_file.write_bytes(key)
            restored.write_text(json.dumps({'status':'verified_application_restore','archiveSha256':backup.digest(archive),
                'majorVersionMatched':True,'tablesMatched':1,'catalogGroupsMatched':0}))
            original.write_text(json.dumps(receipt({'20260929135736':'a'*64})))
            spec=review();spec.update(originalReceipt=str(original),originalReceiptSha256=backup.digest(original.read_bytes()))
            def save(hashes):
                encrypted.write_bytes(Fernet(key).encrypt(json.dumps({'manifest':manifest | {'migrationFileHashes':hashes},
                    'archive':base64.b64encode(archive).decode()}).encode()))
                spec['backup']={'encryptedFile':str(encrypted),'encryptedSha256':backup.digest(encrypted.read_bytes()),
                    'keyFile':str(key_file),'restoreReceipt':str(restored),'restoreReceiptSha256':backup.digest(restored.read_bytes())}
            save(captured)
            self.assertEqual(adapter.load_evidence(spec)[2]['archiveSha256'],backup.digest(archive))
            # Historical Windows archives and a changed SQL source remain held;
            # collection is fixed without normalizing or weakening authentication.
            for hashes in ({k.replace('/','\\'):v for k,v in captured.items()},
                           captured | {'migrations/'+adapter.engine.readiness.MIGRATIONS[0]:'0'*64}):
                save(hashes)
                with self.assertRaisesRegex(adapter.Held,'reviewed migration sources'):adapter.load_evidence(spec)
        self.assertNotIn('DSN',progress_output.getvalue())

    async def test_cli_collects_both_fictional_migration_roots_without_platform_separators(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'backend').mkdir();(root/'migrations').mkdir()
            (root/'supabase/migrations').mkdir(parents=True)
            (root/'migrations/TEST_ONLY_native.sql').write_bytes(b'SELECT 1;')
            (root/'supabase/migrations/TEST_ONLY_delivery.sql').write_bytes(b'SELECT 2;')
            export=AsyncMock(return_value={'status':'TEST ONLY capture'})
            with patch.object(cli,'__file__',str(root/'backend/hosted_backup_cli.py')),\
                 patch.object(sys,'argv',['backup','export','--owner-config','TEST_ONLY.env',
                     '--expected-project','a'*20,'--pg-bin',str(root)]),\
                 patch.dict(os.environ,LOCALAPPDATA=str(root)),patch.object(cli,'dotenv_values',return_value={}),\
                 patch.object(backup,'export_backup',export),redirect_stdout(io.StringIO()):
                await cli.main()
            self.assertEqual(export.await_args.args[-1],{'migrations/TEST_ONLY_native.sql':backup.digest(b'SELECT 1;'),
                'supabase/migrations/TEST_ONLY_delivery.sql':backup.digest(b'SELECT 2;')})
