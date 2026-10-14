"""Hosted adapter guards and fictional loopback integration, never hosted DDL."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/ops'))
import hosted_additive_index as hosted
from test_apply_additive_migration import AdditiveDatabaseTests, FaultConnection, receipt
import actual_inventory_api as actual
from uuid import UUID

PROJECT = 'a' * 20
TARGET = {'projectRef': PROJECT, 'actor': 'postgres', 'connectionMode': 'session_pooler',
          'host': 'fictional.pooler.supabase.com', 'port': 5432, 'database': 'postgres', 'caSha256': 'a' * 64}


def review():
    now = datetime.now(timezone.utc)
    return {'format': hosted.REVIEW_FORMAT, 'projectRef': PROJECT,
            'deliveryVersion': '20261014010000', 'clientRoles': ['anon', 'authenticated'],
            'budgets': dict(hosted.BUDGETS), 'maintenance': {
                'startsAt': (now - timedelta(minutes=5)).isoformat(),
                'endsAt': (now + timedelta(minutes=20)).isoformat(),
                'allWritersStopped': True, 'inFlightDrained': True,
                'reference': 'TEST ONLY fictional reviewed window'}}


def core_plan():
    raw = hosted.engine.source_bytes()
    return {'format': hosted.engine.FORMAT, 'originalInstallation': receipt({'20260929135736': 'a' * 64}),
            'clientRoles': ['anon', 'authenticated'], 'baseline': {'identity': {'actor': 'postgres'},
                'ledger': {'20261008190029': 'b' * 64}},
            'migration': {'sourceFile': 'migrations/' + hosted.engine.SOURCE,
                'sha256': hosted.sha(raw), 'bodySha256': hosted.sha(hosted.engine.sql_body(raw).encode()),
                'name': hosted.engine.SOURCE.split('_', 1)[1].removesuffix('.sql'),
                'deliveryVersion': '20261014010000'}}


def envelope(spec, core, binding):
    return {'format': hosted.FORMAT, 'target': dict(TARGET), 'reviewSha256': hosted.fingerprint(spec),
            'backup': binding, 'budgets': dict(hosted.BUDGETS), 'maintenance': spec['maintenance'], 'core': core}


class HostedAdapterGuards(unittest.TestCase):
    def test_target_retains_session_pooler_and_certificate_validation_without_credentials(self):
        dsn = 'postgresql://postgres.' + PROJECT + ':fictional-secret@fictional.pooler.supabase.com:5432/postgres'
        result = hosted.target(dsn, PROJECT)
        self.assertEqual(result['connectionMode'], 'session_pooler')
        self.assertEqual(result['actor'], 'postgres')
        self.assertNotIn('fictional-secret', json.dumps(result))
        for value, project in ((dsn.replace(':5432/', ':6543/'), PROJECT), (dsn, 'b' * 20),
                               (dsn + '?sslmode=disable', PROJECT),
                               ('postgresql://postgres:secret@127.0.0.1:5432/postgres', PROJECT)):
            with self.subTest(project=project, endpoint=value.replace('fictional-secret', 'redacted')):
                with self.assertRaises(ValueError): hosted.target(value, project)

    def test_mandatory_client_roles_cannot_be_skipped_or_duplicated(self):
        for value in ([], ['anon'], ['authenticated'], ['anon', 'authenticated', 'anon'],
                      ['anon', 'authenticated', 1], ['anon', 'authenticated', 'unsafe-role']):
            with self.subTest(roles=value):
                with self.assertRaises(hosted.Held): hosted.roles({'clientRoles': value})
        self.assertEqual(hosted.roles(review()), ['anon', 'authenticated'])

    def test_window_requires_all_writers_drained_active_and_bounded(self):
        spec = review()
        hosted.maintenance(spec)
        for field, value in (('allWritersStopped', False), ('inFlightDrained', False), ('reference', ''),
                             ('endsAt', spec['maintenance']['startsAt']), ('startsAt', '2026-10-13')):
            changed = deepcopy(spec)
            changed['maintenance'][field] = value
            with self.subTest(field=field):
                with self.assertRaises(hosted.Held): hosted.maintenance(changed)
        expired = datetime.now(timezone.utc) + timedelta(days=2)
        with self.assertRaises(hosted.Held): hosted.maintenance(spec, now=expired)
        hosted.maintenance(spec, now=expired, active=False)

    def test_reviewed_plan_refuses_local_plan_wrong_target_roles_version_and_budget(self):
        spec, binding = review(), {'encryptedSha256': 'a' * 64}
        plan = envelope(spec, core_plan(), binding)
        hosted.validate(plan, spec, TARGET, binding)
        changes = [('format', hosted.engine.FORMAT), ('target', TARGET | {'projectRef': 'b' * 20}),
                   ('budgets', hosted.BUDGETS | {'probeSeconds': 60}), ('reviewSha256', '0' * 64)]
        for field, value in changes:
            with self.subTest(field=field), self.assertRaises(hosted.Held):
                hosted.validate(plan | {field: value}, spec, TARGET, binding)
        for field, value in (('clientRoles', []), ('format', 'jaymax-additive-source-index-plan-v1')):
            changed = deepcopy(plan)
            changed['core'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                hosted.validate(changed, spec, TARGET, binding)
        with self.assertRaises(hosted.Held): hosted.validate(plan, spec, TARGET, {})

    def test_artifact_checksum_refuses_changed_bytes_before_deserializing(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'review.json'
            path.write_bytes(b'{"fictional":true}')
            self.assertEqual(hosted.checked_json(path, hosted.sha(path.read_bytes())), {'fictional': True})
            with self.assertRaises(hosted.Held): hosted.checked_json(path, '0' * 64)

    def test_private_inputs_refuse_external_paths_and_require_acl_verification(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {'LOCALAPPDATA': directory}):
            root = Path(directory)
            outside = root / 'outside.json'; outside.write_text('{}')
            inside = root / 'JayMaxBuild' / 'review.json'
            inside.parent.mkdir(); inside.write_text('{}')
            with patch.object(hosted, 'verify_acl') as acl:
                with self.assertRaises(hosted.Held): hosted.private_file(outside)
                acl.assert_not_called()
                self.assertEqual(hosted.private_file(inside), inside)
                acl.assert_called_once_with(inside)
            with patch.object(hosted, 'verify_acl', side_effect=hosted.Held('Private input ownership or ACL verification held')):
                with self.assertRaises(hosted.Held): hosted.private_file(inside)

    def test_acl_failure_does_not_print_security_diagnostics(self):
        failed = SimpleNamespace(returncode=2, stdout=b'private user detail', stderr=b'private path')
        with patch.object(hosted.shutil, 'which', return_value='pwsh'),\
             patch.object(hosted.subprocess, 'run', return_value=failed):
            with self.assertRaises(hosted.Held) as error: hosted.verify_acl('TEST ONLY file')
        self.assertNotIn('private path', str(error.exception))
        self.assertNotIn('private user detail', str(error.exception))

    def test_private_input_acl_accepts_protected_windows_file_and_refuses_broad_grant(self):
        if os.name != 'nt':
            with patch.object(hosted.shutil, 'which', return_value=None), self.assertRaises(hosted.Held):
                hosted.verify_acl('TEST ONLY unsupported platform')
            return
        with TemporaryDirectory() as directory, patch.dict(os.environ, {'LOCALAPPDATA': directory}):
            root = Path(directory).resolve()
            protected = hosted.backup.private_directory(root / 'JayMaxBuild/backups' / ('backup-' + uuid4().hex), 'backups')
            item = protected / 'TEST_ONLY_review.json'; item.write_text('{}')
            self.assertEqual(hosted.private_file(item), item)
            script = """$ErrorActionPreference='Stop'; $p=$env:JAYMAX_ADDITIVE_PRIVATE;
                $acl=Get-Acl -LiteralPath $p;
                $identity=[Security.Principal.SecurityIdentifier]::new('S-1-1-0');
                $rule=[Security.AccessControl.FileSystemAccessRule]::new($identity,'Read','Allow');
                $acl.AddAccessRule($rule); Set-Acl -LiteralPath $p -AclObject $acl"""
            result = hosted.subprocess.run([hosted.shutil.which('pwsh'), '-NoProfile', '-NonInteractive', '-Command', script],
                env={**os.environ, 'JAYMAX_ADDITIVE_PRIVATE': str(item)}, capture_output=True, timeout=20,
                creationflags=hosted.backup.FLAGS)
            self.assertEqual(result.returncode, 0)
            with self.assertRaises(hosted.Held): hosted.private_file(item)

    def test_encrypted_backup_is_bound_to_fresh_restore_and_original_history(self):
        from cryptography.fernet import Fernet
        import base64
        with TemporaryDirectory() as directory:
            root = Path(directory)
            key, archive = Fernet.generate_key(), b'TEST ONLY adapter evidence fixture; not a database dump'
            key_path = root / 'key'; key_path.write_bytes(key)
            encrypted, restored, original = root / 'backup', root / 'restore.json', root / 'original.json'
            spec = review()
            manifest = {'format': hosted.backup.FORMAT, 'projectRef': PROJECT,
                        'schemas': list(hosted.backup.SCHEMAS), 'rowFingerprintAlgorithm': hosted.backup.ROW_ALGORITHM,
                        'serverVersionNum': '170006',
                        'archiveSha256': hosted.sha(archive), 'archiveBytes': len(archive),
                        'createdAt': datetime.now(timezone.utc).isoformat(),
                        'migrationFileHashes': {'migrations/' + name: hosted.sha((hosted.engine.readiness.ROOT / 'migrations' / name).read_bytes())
                            for name in hosted.engine.readiness.MIGRATIONS},
                        'tables': {hosted.LEDGER: {'rows': 30, 'sha256': 'a' * 64, 'kind': 'r'}}, 'catalog': {}}
            original.write_text(json.dumps(receipt({'20260929135736': 'a' * 64})))
            def save(restore_changes=None, manifest_changes=None):
                payload = {'manifest': manifest | (manifest_changes or {}), 'archive': base64.b64encode(archive).decode()}
                encrypted.write_bytes(Fernet(key).encrypt(json.dumps(payload).encode()))
                restored.write_text(json.dumps({'status': 'verified_application_restore', 'archiveSha256': hosted.sha(archive),
                    'majorVersionMatched': True, 'tablesMatched': 1, 'catalogGroupsMatched': 0} | (restore_changes or {})))
                spec['backup'] = {'encryptedFile': str(encrypted), 'encryptedSha256': hosted.sha(encrypted.read_bytes()),
                    'keyFile': str(key_path), 'restoreReceipt': str(restored), 'restoreReceiptSha256': hosted.sha(restored.read_bytes())}
                spec.update(originalReceipt=str(original), originalReceiptSha256=hosted.sha(original.read_bytes()))
            save()
            self.assertEqual(hosted.load_evidence(spec)[2]['archiveSha256'], hosted.sha(archive))
            for changes in ({'archiveSha256': '0' * 64}, {'status': 'exported_not_restore_verified'},
                            {'majorVersionMatched': False}, {'tablesMatched': 2}):
                save(restore_changes=changes)
                with self.subTest(changes=changes), self.assertRaises(hosted.Held): hosted.load_evidence(spec)
            for changes in ({'createdAt': (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()},
                            {'migrationFileHashes': {}}, {'rowFingerprintAlgorithm': None}):
                save(manifest_changes=changes)
                with self.subTest(changes=changes), self.assertRaises(hosted.Held): hosted.load_evidence(spec)
            save()
            encrypted.write_bytes(encrypted.read_bytes() + b'changed')
            with self.assertRaises(hosted.Held): hosted.load_evidence(spec)


class HostedReceiptGuards(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_and_lost_ack_receipts_retain_unknown_without_resending(self):
        await self.exercise(asyncio.TimeoutError(), 'apply_in_progress_outcome_unknown', None)
        await self.exercise(hosted.engine.AdditiveFailure({'status': 'commit_outcome_unknown',
            'commitAttempted': True, 'sqlCommitted': None, 'automaticRetry': False}), 'commit_outcome_unknown', None)

    async def test_fresh_connection_failure_retains_known_commit_and_plan_hash(self):
        await self.exercise(None, 'committed_verification_held', True, fresh_failure=True)

    async def test_failed_reconciliation_never_claims_the_original_sql_was_unapplied(self):
        await self.exercise(None, 'held', None, mode='reconcile', connect_failure=True, expected_sends=0)

    async def exercise(self, error, status, committed, fresh_failure=False, mode='apply',
                       connect_failure=False, expected_sends=1):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            spec, binding = review(), {'encryptedSha256': 'a' * 64}
            spec.update(originalReceipt=str(root / 'original'), backup={k: str(root / k) for k in ('encryptedFile', 'keyFile', 'restoreReceipt')})
            plan = envelope(spec, core_plan(), binding)
            review_path, plan_path = root / 'review.json', root / 'plan.json'
            review_path.write_text(json.dumps(spec)); plan_path.write_text(json.dumps(plan))
            args = SimpleNamespace(mode=mode, owner_config=str(root / 'owner.env'), expected_project=PROJECT,
                review=str(review_path), review_sha256=hosted.sha(review_path.read_bytes()),
                plan=str(plan_path), plan_sha256=hosted.sha(plan_path.read_bytes()),
                approve_plan_sha256=hosted.sha(plan_path.read_bytes()), output_directory=str(root / 'output'))
            output = root / 'output'; output.mkdir()
            conn = SimpleNamespace(close=AsyncMock())
            connect = AsyncMock(side_effect=OSError('private driver detail') if connect_failure else
                               [conn, OSError('private driver detail')] if fresh_failure else [conn])
            send = AsyncMock(side_effect=error, return_value={'status': 'committed_requires_independent_verification',
                'sqlCommitted': True, 'commitAttempted': True})
            with patch.object(hosted.backup, 'private_directory', return_value=output),\
                 patch.object(hosted, 'private_file', side_effect=Path),\
                 patch.object(hosted, 'dotenv_values', return_value={'DATABASE_URL': 'TEST ONLY mocked URL'}),\
                 patch.object(hosted, 'target', return_value=TARGET), patch.object(hosted, 'connection_tls', return_value=True),\
                 patch.object(hosted, 'load_evidence', return_value=({}, {}, binding)),\
                 patch.object(hosted.asyncpg, 'connect', connect), patch.object(hosted, 'apply', send):
                self.assertEqual(await hosted.run(args), 2)
            result = json.loads((output / 'receipt.json').read_text())
            self.assertEqual(result['status'], status)
            self.assertEqual(result['sqlCommitted'], committed)
            if mode == 'apply': self.assertEqual(result['planSha256'], args.plan_sha256)
            self.assertFalse(result['automaticRetry'])
            self.assertNotIn('private driver detail', json.dumps(result))
            self.assertEqual(send.await_count, expected_sends)


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class HostedAdapterDatabaseTests(AdditiveDatabaseTests):
    @classmethod
    def setUpClass(cls):
        # Fictional ordinary roles are removed only if this class created them.
        import asyncpg
        async def provision():
            conn = await asyncpg.connect(os.environ['NATIVE_PURCHASE_TEST_DSN'])
            created = []
            try:
                for name in ('anon', 'authenticated'):
                    if not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=$1)', name):
                        await conn.execute('CREATE ROLE ' + name + ' NOLOGIN')
                        created.append(name)
                return created
            finally: await conn.close()
        cls.created_roles = asyncio.run(provision())
        try: super().setUpClass()
        except Exception:
            cls.remove_roles()
            raise

    @classmethod
    def remove_roles(cls):
        import asyncpg
        async def cleanup():
            conn = await asyncpg.connect(os.environ['NATIVE_PURCHASE_TEST_DSN'])
            try:
                for name in cls.created_roles: await conn.execute('DROP ROLE ' + name)
            finally: await conn.close()
        asyncio.run(cleanup())

    @classmethod
    def tearDownClass(cls):
        try: super().tearDownClass()
        finally: cls.remove_roles()

    async def hosted_plan(self):
        self.spec = review()
        # The public CLI refuses this loopback identity. Only library helpers are
        # exercised against the explicitly disposable fixture, with no hosted DSN.
        self.target = TARGET | {'actor': 'purchase_implementation_test', 'host': '127.0.0.1'}
        async with self.conn.transaction(isolation='repeatable_read', readonly=True):
            self.facts = await hosted.backup.fingerprint(self.conn)
        self.binding = {'factsSha256': hosted.fingerprint(self.facts), 'TEST_ONLY': True,
                        'serverVersionNum': await self.conn.fetchval('SHOW server_version_num')}
        return await hosted.prepare(self.conn, self.original, self.spec, self.target, self.facts, self.binding)

    async def independent(self, plan):
        import asyncpg
        conn = await asyncpg.connect(self.dsn, server_settings={'default_transaction_read_only': 'on'})
        try: return await hosted.reconcile(conn, plan, self.spec, self.target, self.facts, self.binding)
        finally: await conn.close()

    async def test_hosted_wrapper_is_readonly_then_preserves_exact_food_cost(self):
        plan = await self.hosted_plan()
        self.assertEqual((await self.independent(plan))['status'], 'verified_not_applied')
        result = await hosted.apply(self.conn, plan, self.spec, self.target, self.facts, self.binding)
        self.assertTrue(result['sqlCommitted'])
        self.assertEqual((await self.independent(plan))['status'], 'verified_applied')
        params = self.workflow['actualReportParams']
        report = await actual.period_report(self.conn, self.workflow['temporaryStore'],
            UUID(params['opening']), UUID(params['closing']))
        self.assertEqual(report['actualFoodCost'], '55.00')

    async def test_hosted_permission_checks_reject_client_private_access(self):
        await self.conn.execute('GRANT USAGE ON SCHEMA purchasing TO anon')
        with self.assertRaises(ValueError): await self.hosted_plan()
        self.assertFalse(await self.conn.fetchval('SELECT to_regclass($1) IS NOT NULL', hosted.engine.INDEX))

    async def test_changed_ledger_defaults_permissions_and_uniqueness_hold_before_ddl(self):
        plan = await self.hosted_plan()
        for change, undo in (
            ("ALTER TABLE supabase_migrations.schema_migrations ALTER COLUMN name SET DEFAULT 'TEST ONLY'",
             'ALTER TABLE supabase_migrations.schema_migrations ALTER COLUMN name DROP DEFAULT'),
            ('GRANT SELECT ON supabase_migrations.schema_migrations TO anon',
             'REVOKE SELECT ON supabase_migrations.schema_migrations FROM anon'),
            ('GRANT SELECT(version) ON supabase_migrations.schema_migrations TO anon',
             'REVOKE SELECT(version) ON supabase_migrations.schema_migrations FROM anon'),
            ('ALTER TABLE supabase_migrations.schema_migrations DROP CONSTRAINT schema_migrations_pkey',
             'ALTER TABLE supabase_migrations.schema_migrations ADD PRIMARY KEY(version)')):
            await self.conn.execute(change)
            try:
                with self.subTest(change=change), self.assertRaises(hosted.engine.AdditiveFailure) as failure:
                    await hosted.apply(self.conn, plan, self.spec, self.target, self.facts, self.binding)
                self.assertFalse(failure.exception.report['commitAttempted'])
                self.assertFalse(await self.conn.fetchval('SELECT to_regclass($1) IS NOT NULL', hosted.engine.INDEX))
            finally: await self.conn.execute(undo)

    async def test_duplicate_versions_cannot_collapse_into_fingerprint_map(self):
        await self.conn.execute('ALTER TABLE supabase_migrations.schema_migrations DROP CONSTRAINT schema_migrations_pkey')
        await self.conn.execute("INSERT INTO supabase_migrations.schema_migrations SELECT * FROM supabase_migrations.schema_migrations LIMIT 1")
        with self.assertRaises(ValueError): await hosted.engine.preservation.ledger_fingerprints(self.conn)
        with self.assertRaises(ValueError): await self.hosted_plan()

    async def test_hosted_permission_checks_refuse_initial_ledger_column_exposure(self):
        await self.conn.execute('GRANT SELECT(version) ON supabase_migrations.schema_migrations TO anon')
        with self.assertRaises(hosted.Held): await self.hosted_plan()
        self.assertFalse(await self.conn.fetchval('SELECT to_regclass($1) IS NOT NULL', hosted.engine.INDEX))

    async def test_backup_sequence_drift_is_refused_inside_locked_apply(self):
        await self.conn.execute('CREATE SEQUENCE public.test_only_adapter_sequence')
        plan = await self.hosted_plan()
        await self.conn.execute("SELECT nextval('public.test_only_adapter_sequence')")
        with self.assertRaises(hosted.engine.AdditiveFailure) as failure:
            await hosted.apply(self.conn, plan, self.spec, self.target, self.facts, self.binding)
        self.assertTrue(failure.exception.report['rollbackCompleted'])
        self.assertFalse(failure.exception.report['commitAttempted'])
        self.assertFalse(await self.conn.fetchval('SELECT to_regclass($1) IS NOT NULL', hosted.engine.INDEX))

    async def test_precommit_backup_guard_failure_rolls_back_index_and_ledger(self):
        plan = await self.hosted_plan()
        original = hosted.backup_match
        async def check(conn, facts, *, after=False):
            if after: raise hosted.Held('TEST ONLY forced precommit failure')
            return await original(conn, facts)
        with patch.object(hosted, 'backup_match', side_effect=check), self.assertRaises(hosted.engine.AdditiveFailure) as failure:
            await hosted.apply(self.conn, plan, self.spec, self.target, self.facts, self.binding)
        self.assertTrue(failure.exception.report['rollbackCompleted'])
        self.assertEqual((await self.independent(plan))['status'], 'verified_not_applied')

    async def test_hosted_commit_ack_loss_reconciles_without_reapplication(self):
        plan = await self.hosted_plan()
        with self.assertRaises(hosted.engine.AdditiveFailure) as failure:
            await hosted.apply(FaultConnection(self.conn, commit_ack_loss=True), plan,
                               self.spec, self.target, self.facts, self.binding)
        self.assertIsNone(failure.exception.report['sqlCommitted'])
        self.assertEqual((await self.independent(plan))['status'], 'verified_applied')

    async def test_hosted_active_writer_prevents_false_unapplied_reconciliation(self):
        plan = await self.hosted_plan()
        import asyncpg
        writer = await asyncpg.connect(self.dsn)
        try:
            await writer.execute('SELECT pg_advisory_lock($1::bigint)', hosted.engine.INSTALLER_LOCK)
            with self.assertRaises(hosted.Held): await self.independent(plan)
        finally: await writer.close()
        self.assertEqual((await self.independent(plan))['status'], 'verified_not_applied')

    async def test_write_committing_during_lock_wait_is_seen_before_ddl(self):
        plan = await self.hosted_plan()
        import asyncpg
        writer = await asyncpg.connect(self.dsn)
        observer = await asyncpg.connect(self.dsn)
        tx = writer.transaction()
        await tx.start()
        task = None
        try:
            await writer.execute("UPDATE public.stores SET name='TEST ONLY changed during wait' WHERE id='berts'")
            pid = self.conn.get_server_pid()
            task = asyncio.create_task(hosted.apply(self.conn, plan, self.spec, self.target, self.facts, self.binding))
            for _ in range(100):
                if await observer.fetchval("SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=$1", pid):
                    break
                await asyncio.sleep(.02)
            else: self.fail('Installer did not enter the expected table-lock wait')
            await tx.commit()
            with self.assertRaises(hosted.engine.AdditiveFailure) as failure: await task
            self.assertFalse(failure.exception.report['commitAttempted'])
            self.assertTrue(failure.exception.report['rollbackCompleted'])
            self.assertFalse(await self.conn.fetchval('SELECT to_regclass($1) IS NOT NULL', hosted.engine.INDEX))
            self.assertEqual(await self.conn.fetchval('SELECT count(*) FROM supabase_migrations.schema_migrations'), 30)
        finally:
            if task is not None and not task.done():
                task.cancel()
                try: await task
                except asyncio.CancelledError: pass
            if writer.is_in_transaction(): await tx.rollback()
            await writer.close(); await observer.close()
