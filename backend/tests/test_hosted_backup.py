"""Backup authenticity, scope, restore boundary and secret-safe subprocess guards."""
import base64
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from cryptography.fernet import Fernet
import hosted_backup as backup

PROJECT = 'abcdefghijklmnopqrst'


class EncryptionTests(unittest.TestCase):
    def test_restore_list_keeps_public_acl_and_tables_but_skips_schema_recreation(self):
        toc = b'; header\n5; 2615 2200 SCHEMA - public pg_database_owner\n10; 0 0 ACL - SCHEMA public pg_database_owner\n11; 1259 12345 TABLE public app_users postgres\n12; 2615 12346 SCHEMA - purchasing postgres\n'
        result = backup.restore_list(toc)
        self.assertIn(b'; 5; 2615 2200 SCHEMA - public', result)
        self.assertIn(b'10; 0 0 ACL - SCHEMA public', result)
        self.assertIn(b'11; 1259 12345 TABLE public app_users', result)
        self.assertIn(b'12; 2615 12346 SCHEMA - purchasing', result)
        with self.assertRaises(backup.BackupError):
            backup.restore_list(b'; no public schema\n')
        with self.assertRaises(backup.BackupError):
            backup.restore_list(toc + b'13; 2615 2345 SCHEMA - public postgres\n')

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.key = root / 'key'
        self.key.write_bytes(Fernet.generate_key())
        self.archive = b'PGDMP\x00synthetic\r\ninvoice bytes\x00'
        self.manifest = {'format': backup.FORMAT, 'projectRef': PROJECT, 'schemas': list(backup.SCHEMAS),
            'archiveBytes': len(self.archive), 'archiveSha256': backup.digest(self.archive)}
        self.encrypted = root / 'backup.enc'
        self.save()

    def save(self):
        value = {'manifest': self.manifest, 'archive': base64.b64encode(self.archive).decode()}
        self.encrypted.write_bytes(Fernet(self.key.read_bytes()).encrypt(json.dumps(value).encode()))

    def test_roundtrip_preserves_binary_and_crlf(self):
        manifest, data = backup.open_backup(self.encrypted, self.key, PROJECT)
        self.assertEqual(data, self.archive)
        self.assertEqual(manifest, self.manifest)
        self.assertNotIn(b'invoice bytes', self.encrypted.read_bytes())

    def test_damage_wrong_key_and_wrong_project_are_rejected(self):
        for mode in ('damage', 'key', 'project'):
            self.key.write_bytes(Fernet.generate_key()); self.save()
            project = PROJECT
            if mode == 'damage':
                damaged = bytearray(self.encrypted.read_bytes()); damaged[-20] ^= 1
                self.encrypted.write_bytes(damaged)
            elif mode == 'key':
                self.key.write_bytes(Fernet.generate_key())
            else:
                project = 'differentprojectxxxx'
            with self.assertRaises(backup.BackupError):
                backup.open_backup(self.encrypted, self.key, project)

    def test_authenticated_but_partial_or_wrong_digest_manifest_is_rejected(self):
        for mode in ('schemas', 'digest', 'size'):
            original = dict(self.manifest)
            if mode == 'schemas': self.manifest['schemas'] = ['public']
            elif mode == 'digest': self.manifest['archiveSha256'] = 'bad'
            else: self.manifest['archiveBytes'] += 1
            self.save()
            with self.assertRaises(backup.BackupError):
                backup.open_backup(self.encrypted, self.key, PROJECT)
            self.manifest = original


class BoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_private_directory_acl_and_no_overwrite_boundary(self):
        path = Path(os.environ['LOCALAPPDATA']) / 'JayMaxBuild/backups' / ('backup-' + uuid4().hex)
        self.assertEqual(backup.private_directory(path, 'backups'), path)
        self.addCleanup(path.rmdir)
        with self.assertRaises(backup.BackupError):
            backup.private_directory(path, 'backups')
        with self.assertRaises(backup.BackupError):
            backup.private_directory(Path(self._testMethodName), 'backups')

    def test_expected_owner_project_session_endpoint_required(self):
        valid = 'postgresql://postgres.' + PROJECT + ':synthetic@aws-0.pooler.supabase.com:5432/postgres'
        self.assertEqual(backup.hosted_connection(valid, PROJECT)['database'], 'postgres')
        for url in (valid.replace(':5432', ':6543'), valid + '?host=elsewhere',
                    valid.replace(PROJECT, 'differentprojectxxxx'), valid.replace('/postgres', '/operational'),
                    valid.replace('aws-0.pooler.supabase.com', '127.0.0.1')):
            with self.assertRaises(backup.BackupError):
                backup.hosted_connection(url, PROJECT)

    async def test_remote_control_and_existing_style_destinations_refused_before_connect(self):
        for url in ('postgresql://test@example.com/native_purchase_test_backup_' + 'a' * 32,
                    'postgresql://test@127.0.0.1/native_purchase_test_control',
                    'postgresql://test@127.0.0.1/native_purchase_test_old'):
            with patch.object(backup.asyncpg, 'connect', AsyncMock()) as connect:
                with self.assertRaises((backup.BackupError, backup.native.BackupError)):
                    await backup.verify_restore(url, 'missing', 'missing', PROJECT, 'missing', 'missing')
                connect.assert_not_awaited()

    async def test_untrusted_backup_refused_before_connection_or_target_writes(self):
        dsn = 'postgresql://test@127.0.0.1/native_purchase_test_backup_' + 'a' * 32
        with patch.object(backup.asyncpg, 'connect', AsyncMock()) as connect:
            with self.assertRaises(backup.BackupError):
                await backup.verify_restore(dsn, 'missing', 'missing', PROJECT, 'missing', 'missing')
            connect.assert_not_awaited()

    def test_pg_service_indirection_removed_and_remote_tls_required(self):
        settings = {'host': 'example', 'port': 5432, 'user': 'role', 'password': 'synthetic-secret', 'database': 'db'}
        with patch.dict(os.environ, PGSERVICE='untrusted', PGSERVICEFILE='untrusted', PGSSLMODE='disable'):
            env = backup.process_env(settings, True)
        self.assertNotIn('PGSERVICE', env)
        self.assertNotIn('PGSERVICEFILE', env)
        self.assertEqual(env['PGSSLMODE'], 'verify-full')
        self.assertIn('default_transaction_read_only=on', env['PGOPTIONS'])

    async def test_dump_errors_do_not_expose_driver_text(self):
        result = type('Result', (), {'returncode': 1, 'stderr': b'synthetic-private-password', 'stdout': b''})()
        with patch.object(backup.subprocess, 'run', return_value=result):
            with self.assertRaises(backup.BackupError) as caught:
                await backup.tool('synthetic', [])
        self.assertNotIn('synthetic-private-password', str(caught.exception))


class ExportLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def connection(self, *, close_error=None, settings=None):
        tx=SimpleNamespace(start=AsyncMock(),commit=AsyncMock(),rollback=AsyncMock())
        async def fetch(sql,*args):
            if 'pg_settings' in sql:
                return settings if settings is not None else [
                    {'name':'statement_timeout','setting':'120000','unit':'ms'},
                    {'name':'idle_in_transaction_session_timeout','setting':'0','unit':'ms'},
                    {'name':'tcp_keepalives_idle','setting':'7200','unit':'s'}]
            if 'FROM pg_namespace WHERE nspname NOT' in sql:
                return [{'nspname':name} for name in backup.SCHEMAS]
            if 'pg_roles' in sql or 'pg_auth_members' in sql: return []
            if 'nspname,pg_get_userbyid' in sql:
                return [{'nspname':name,'owner':'TEST ONLY owner'} for name in backup.SCHEMAS]
            raise AssertionError('Unexpected fictional query')
        async def scalar(sql,*args):
            if 'pg_export_snapshot' in sql: return 'TEST ONLY exported snapshot'
            if 'server_version_num' in sql: return '170006'
            if 'last_value' in sql: return '{"last_value":2,"is_called":true}'
            if 'pg_get_userbyid(datdba)' in sql: return 'TEST ONLY owner'
            raise AssertionError('Unexpected fictional scalar')
        return SimpleNamespace(transaction=MagicMock(return_value=tx),fetch=AsyncMock(side_effect=fetch),
            fetchval=AsyncMock(side_effect=scalar),execute=AsyncMock(),close=AsyncMock(side_effect=close_error)),tx

    async def export(self, root, conn, *, fingerprint_error=None, facts=None,
                     cleanup_error=None, readback_error=None, publish_error=None):
        def directory(path,area): path.mkdir();return path
        async def tool(executable,args,*extra):
            filename=next((arg[7:] for arg in args if arg.startswith('--file=')),None)
            if filename: Path(filename).write_bytes(b'PGDMP TEST ONLY fictional archive')
            return b'; TEST ONLY archive list'
        with ExitStack() as patches:
            patches.enter_context(patch.object(backup,'private_directory',side_effect=directory))
            connect=patches.enter_context(patch.object(backup.asyncpg,'connect',AsyncMock(return_value=conn)))
            patches.enter_context(patch.object(backup,'connection_tls',return_value=True))
            patches.enter_context(patch.object(backup.native,'configure',AsyncMock()))
            patches.enter_context(patch.object(backup,'fingerprint',AsyncMock(side_effect=fingerprint_error,
                return_value=facts or {'tables':{},'catalog':{}})))
            patches.enter_context(patch.object(backup,'dependencies',AsyncMock(return_value={})))
            patches.enter_context(patch.object(backup,'tool',AsyncMock(side_effect=tool)))
            if cleanup_error:
                patches.enter_context(patch.object(backup,'remove_partial_files',AsyncMock(side_effect=cleanup_error)))
            if readback_error:
                patches.enter_context(patch.object(backup,'open_backup',side_effect=readback_error))
            if publish_error:
                patches.enter_context(patch.object(Path,'rename',side_effect=publish_error))
            result=await backup.export_backup('postgresql://postgres.'+PROJECT+':TEST_ONLY@aws-0.pooler.supabase.com:5432/postgres',
                PROJECT,'TEST ONLY dump','TEST ONLY restore',root/'archive',root/'key',{})
            self.assertEqual(connect.await_args.kwargs['timeout'],20)
            self.assertEqual(connect.await_args.kwargs['command_timeout'],60)
            self.assertNotIn('server_settings',connect.await_args.kwargs)
            return result

    async def test_success_publishes_only_after_close_and_cleanup_with_authenticated_archive(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);conn,tx=self.connection()
            def closed(): self.assertFalse((root/'archive/backup.jmax.enc').exists())
            conn.close.side_effect=closed
            result=await self.export(root,conn)
            self.assertEqual(result['status'],'exported_not_restore_verified')
            manifest,data=backup.open_backup(result['encryptedBackup'],result['privateKey'],PROJECT)
            self.assertEqual(data,b'PGDMP TEST ONLY fictional archive')
            self.assertEqual(result['archiveSha256'],manifest['archiveSha256'])
            self.assertFalse((root/'archive/archive.partial').exists())
            self.assertFalse((root/'archive/backup.partial.enc').exists())
            names=[phase['phase'] for phase in result['backupDiagnostics']['phases']]
            self.assertLess(names.index('connection_close'),names.index('partial_cleanup'))
            self.assertLess(names.index('partial_cleanup'),names.index('publish'))
            self.assertTrue(all(phase['outcome']=='passed' for phase in result['backupDiagnostics']['phases']))
            self.assertEqual(result['backupDiagnostics']['serverLimits']['statement_timeout'],{'value':120000,'unit':'ms'})
            self.assertEqual(result['backupDiagnostics']['clientLimits'],
                {'connectSeconds':20,'commandSeconds':60,'subprocessSeconds':240})
            conn.execute.assert_not_awaited();tx.commit.assert_awaited_once()

    async def test_close_only_failure_leaves_no_accepted_or_partial_archive(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);conn,tx=self.connection(close_error=ConnectionError('TEST ONLY private close'))
            with self.assertRaises(ConnectionError) as caught: await self.export(root,conn)
            self.assertEqual(caught.exception.connectionCloseErrorType,'ConnectionError')
            self.assertFalse((root/'archive/backup.jmax.enc').exists())
            self.assertFalse((root/'archive/backup.partial.enc').exists())
            self.assertFalse((root/'archive/archive.partial').exists())
            self.assertTrue((root/'key/backup.key').exists())
            from hosted_backup_cli import held_result
            self.assertEqual(held_result(caught.exception)['backupArtifacts'], {
                'privateKeyRetained':True, 'encryptedPartialRetained':False,
                'rawPartialRetained':False, 'finalBackupPresent':False})
            self.assertNotIn('publish',[p['phase'] for p in caught.exception.backupDiagnostics['phases']])
            tx.commit.assert_awaited_once()

    async def test_cleanup_and_publish_failures_cannot_leave_an_accepted_filename(self):
        for operation in ('cleanup','publish'):
            with self.subTest(operation=operation),TemporaryDirectory() as temporary:
                root=Path(temporary);conn,tx=self.connection()
                arguments={operation+'_error':OSError('TEST ONLY private file failure')}
                with self.assertRaises(OSError) as caught: await self.export(root,conn,**arguments)
                self.assertFalse((root/'archive/backup.jmax.enc').exists())
                self.assertTrue((root/'archive/backup.partial.enc').exists())
                self.assertTrue(caught.exception.backupArtifacts['privateKeyRetained'])
                self.assertTrue(caught.exception.backupArtifacts['encryptedPartialRetained'])
                self.assertFalse(caught.exception.backupArtifacts['finalBackupPresent'])
                phase='partial_cleanup' if operation=='cleanup' else 'publish'
                self.assertTrue(any(p['phase']==phase and p['outcome']=='held'
                    for p in caught.exception.backupDiagnostics['phases']))

    async def test_artifact_inspection_failure_preserves_original_close_error(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);original=ConnectionError('TEST ONLY private close')
            conn,tx=self.connection(close_error=original)
            with patch.object(Path,'exists',side_effect=PermissionError('TEST ONLY private path')):
                with self.assertRaises(ConnectionError) as caught: await self.export(root,conn)
            self.assertIs(caught.exception,original)
            from hosted_backup_cli import held_result
            self.assertEqual(held_result(original)['backupArtifacts'],{'artifactInspectionHeld':True})
            self.assertEqual(original.partialCleanupErrorType,'PermissionError')
            self.assertFalse((root/'archive/backup.jmax.enc').exists())

    async def test_fingerprint_disconnect_keeps_failed_phase_sqlstate_and_close_category(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);conn,tx=self.connection(close_error=RuntimeError('TEST ONLY private close'))
            tx.rollback.side_effect=RuntimeError('TEST ONLY private rollback')
            original=ConnectionError('TEST ONLY private password');original.sqlstate='08003'
            with self.assertRaises(ConnectionError) as caught:
                await self.export(root,conn,fingerprint_error=original)
            self.assertIs(caught.exception,original)
            from hosted_backup_cli import held_result
            receipt=held_result(original)
            self.assertEqual(receipt['sqlState'],'08003')
            self.assertEqual(receipt['snapshotCleanupErrorType'],'RuntimeError')
            self.assertEqual(receipt['connectionCloseErrorType'],'RuntimeError')
            self.assertTrue(any(p['phase']=='fingerprint' and p['outcome']=='held' for p in receipt['backupDiagnostics']['phases']))
            for sensitive in ('TEST ONLY', 'private password', 'private rollback', 'private close', str(root)):
                self.assertNotIn(sensitive,json.dumps(receipt))
            self.assertFalse((root/'archive/backup.jmax.enc').exists())

    async def test_readback_and_sequence_drift_hold_before_publication(self):
        for operation in ('readback','sequence'):
            with self.subTest(operation=operation),TemporaryDirectory() as temporary:
                root=Path(temporary);conn,tx=self.connection()
                arguments=({'readback_error':backup.BackupError('Encrypted readback mismatch')}
                    if operation=='readback' else {'facts':{'catalog':{},'tables':{
                        'public.test_only_sequence':{'kind':'S','sha256':'a'*64,'rows':1}}}})
                with self.assertRaises(backup.BackupError) as caught: await self.export(root,conn,**arguments)
                self.assertFalse((root/'archive/backup.jmax.enc').exists())
                self.assertFalse((root/'archive/backup.partial.enc').exists())
                phase='read_back' if operation=='readback' else 'sequence_recheck'
                self.assertTrue(any(p['phase']==phase and p['outcome']=='held'
                    for p in caught.exception.backupDiagnostics['phases']))

    async def test_unexpected_limit_metadata_does_not_abort_or_echo_values(self):
        for setting,unit in (('TEST ONLY private password','ms'),('120000','TEST ONLY unknown unit')):
            with self.subTest(setting=setting,unit=unit),TemporaryDirectory() as temporary:
                root=Path(temporary);conn,tx=self.connection(settings=[
                    {'name':'statement_timeout','setting':setting,'unit':unit},
                    {'name':'tcp_keepalives_count','setting':'10','unit':None}])
                result=await self.export(root,conn)
                self.assertEqual(result['status'],'exported_not_restore_verified')
                self.assertTrue((root/'archive/backup.jmax.enc').exists())
                self.assertTrue(result['backupDiagnostics']['limitReadHeld'])
                self.assertIn('statement_timeout',result['backupDiagnostics']['serverLimitsNotCaptured'])
                self.assertEqual(result['backupDiagnostics']['serverLimits']['tcp_keepalives_count'],{'value':10,'unit':None})
                self.assertNotIn('TEST ONLY',json.dumps(result['backupDiagnostics']))
                tx.commit.assert_awaited_once()

    async def test_limit_query_disconnect_still_holds_original_error(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);conn,tx=self.connection()
            original=ConnectionError('TEST ONLY private disconnect');original.sqlstate='08003'
            conn.fetch.side_effect=original
            with self.assertRaises(ConnectionError) as caught: await self.export(root,conn)
            self.assertIs(caught.exception,original)
            self.assertEqual(caught.exception.sqlstate,'08003')
            self.assertFalse((root/'archive/backup.jmax.enc').exists())
            tx.rollback.assert_awaited_once()
            tx.commit.assert_not_awaited()

    async def test_negative_socket_observation_is_retained_without_changing_settings(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);conn,tx=self.connection(settings=[
                {'name':'tcp_keepalives_idle','setting':'-1','unit':'s'}])
            result=await self.export(root,conn)
            self.assertEqual(result['backupDiagnostics']['serverLimits']['tcp_keepalives_idle'],
                             {'value':-1,'unit':'s'})
            self.assertIn('transaction_timeout',result['backupDiagnostics']['serverLimitsNotCaptured'])
            conn.execute.assert_not_awaited()
