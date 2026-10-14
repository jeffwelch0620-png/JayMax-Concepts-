"""Fictional-only incremental migration and commit-recovery acceptance."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import sys
from unittest.mock import patch
from uuid import UUID, uuid4

import asyncpg
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/ops'))
import apply_additive_migration as additive
import deployment_readiness as readiness
import hosted_install_preservation as preservation
import hosted_test_trial as trial
import actual_inventory_api as actual
import hosted_committed_workflow as workflow


def receipt(history):
    entries = []
    for i, name in enumerate(readiness.MIGRATIONS[:-1], 1):
        version = f'202610081900{i:02}'
        raw = (readiness.ROOT / 'migrations' / name).read_bytes()
        entries.append({'order': i, 'sourceFile': 'migrations/' + name, 'deliveryVersion': version,
                        'deliveryFile': 'native-migrations/' + version + '_' + name.split('_', 1)[1],
                        'sha256': additive.digest(raw),
                        'bodySha256': additive.digest(additive.sql_body(raw).encode())})
    return {'status': 'passed_durable_native_install', 'sqlCommitted': True,
            'delivery': entries, 'historicalLedgerFingerprints': history}


class AdditivePlanGuards(unittest.TestCase):
    def test_changed_runtime_source_manifest_refuses_the_additive_file(self):
        self.assertTrue(additive.source_bytes())
        with patch.object(additive.json, 'loads', return_value={'migrationSha256': {additive.SOURCE: '0' * 64}}):
            with self.assertRaises(ValueError): additive.source_bytes()

    def test_local_cli_refuses_hosted_other_user_and_override_urls(self):
        additive.local_target('postgresql://purchase_implementation_test@127.0.0.1:55439/native_purchase_test_control')
        for value in ('postgresql://postgres:secret@db.example.supabase.co:5432/postgres',
                      'postgresql://postgres@127.0.0.1:5432/native_purchase_test_control',
                      'postgresql://purchase_implementation_test@127.0.0.1:5432/postgres',
                      'postgresql://purchase_implementation_test@127.0.0.1:5432/native_purchase_test_control?options=unsafe',
                      'postgresql://purchase_implementation_test@127.0.0.1:bad/native_purchase_test_control'):
            with self.subTest(target=value):
                with self.assertRaises(ValueError): additive.local_target(value)

    def test_original_receipt_has_distinct_raw_and_executed_body_hashes(self):
        original = receipt({'20260929135736': 'a' * 64})
        checked, history = additive.checked_delivery(original)
        self.assertEqual(len(checked), 29)
        self.assertEqual(history, original['historicalLedgerFingerprints'])
        self.assertTrue(all(e['sha256'] != e['bodySha256'] for e in checked))

    def test_original_partial_remapped_or_changed_receipts_are_refused(self):
        original = receipt({'20260929135736': 'a' * 64})
        for field, value in (('sha256', 'b' * 64), ('bodySha256', 'b' * 64),
                             ('deliveryVersion', '20260101000001'), ('order', 30),
                             ('deliveryFile', 'wrong.sql'), ('sourceFile', 'migrations/wrong.sql')):
            changed = deepcopy(original)
            changed['delivery'][0][field] = value
            with self.subTest(field=field):
                with self.assertRaises(ValueError): additive.checked_delivery(changed)
        for key, value in (('delivery', original['delivery'][:-1]),
                           ('historicalLedgerFingerprints', {}), ('sqlCommitted', False)):
            with self.subTest(key=key):
                with self.assertRaises(ValueError): additive.checked_delivery(original | {key: value})

    def test_outer_transaction_is_removed_without_changing_sql_body(self):
        raw = (readiness.ROOT / 'migrations' / additive.SOURCE).read_bytes()
        body = trial.migration_body(raw)
        self.assertIn("SET LOCAL lock_timeout = '5s';", body)
        self.assertIn('CREATE INDEX document_source_rows_version_run_idx', body)
        self.assertNotIn('COMMIT', body)
        self.assertNotIn('BEGIN', body)

    def test_body_cache_uses_bytes_and_cannot_hide_changed_source_content(self):
        first = b'BEGIN; SELECT 1; COMMIT;'
        changed = b'BEGIN; SELECT 2; COMMIT;'
        self.assertNotEqual(additive.sql_body(first), additive.sql_body(changed))
        self.assertEqual(additive.sql_body(first), trial.migration_body(first))


class FaultConnection:
    def __init__(self, conn, *, ledger_failure=False, commit_ack_loss=False, drop_before_commit=False):
        self.conn = conn
        self.ledger_failure = ledger_failure
        self.commit_ack_loss = commit_ack_loss
        self.drop_before_commit = drop_before_commit

    def __getattr__(self, name):
        return getattr(self.conn, name)

    async def execute(self, query, *args):
        if self.ledger_failure and query.startswith('INSERT INTO supabase_migrations.schema_migrations'):
            raise RuntimeError('Fictional ledger-insert failure after index creation')
        return await self.conn.execute(query, *args)

    def transaction(self, *args, **kwargs):
        tx = self.conn.transaction(*args, **kwargs)
        if self.conn.is_in_transaction() or kwargs.get('readonly') or not self.commit_ack_loss:
            return tx
        drop_before_commit = self.drop_before_commit
        class LostAcknowledgement:
            async def start(self): await tx.start()
            async def rollback(self): await tx.rollback()
            async def commit(self):
                if drop_before_commit:
                    raise ConnectionError('Fictional connection failure before commit transmission')
                await tx.commit()
                raise ConnectionError('Fictional commit acknowledgement lost')
        return LostAcknowledgement()


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class AdditiveDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_readonly_nested_failure_rolls_back_savepoint_and_keeps_outer_transaction(self):
        from readonly_snapshot import readonly_snapshot
        async with self.conn.transaction(isolation='repeatable_read'):
            with self.assertRaises(asyncpg.DivisionByZeroError):
                async with readonly_snapshot(self.conn):
                    await self.conn.fetchval('SELECT 1/0')
            self.assertTrue(self.conn.is_in_transaction())
            self.assertEqual(await self.conn.fetchval('SELECT 42'), 42)
        self.assertFalse(self.conn.is_in_transaction())
        # Retain the prior contract: incompatible outer isolation is refused.
        async with self.conn.transaction(isolation='read_committed'):
            with self.assertRaises(asyncpg.InterfaceError):
                async with readonly_snapshot(self.conn): pass
            self.assertEqual(await self.conn.fetchval('SELECT 42'), 42)

    @classmethod
    def setUpClass(cls):
        cls.control = os.environ['NATIVE_PURCHASE_TEST_DSN']
        additive.local_target(cls.control)
        cls.template = 'native_purchase_test_additive_template_' + uuid4().hex
        cls.original = asyncio.run(cls.build_template())

    @classmethod
    async def build_template(cls):
        admin = await asyncpg.connect(cls.control)
        conn = None
        try:
            await admin.execute('CREATE DATABASE ' + cls.template)
            conn = await asyncpg.connect(cls.control.rsplit('/', 1)[0] + '/' + cls.template)
            await conn.execute((readiness.ROOT / 'supabase/schema.sql').read_bytes().decode())
            await conn.execute('''CREATE SCHEMA supabase_migrations;
                CREATE TABLE supabase_migrations.schema_migrations(version text PRIMARY KEY,name text,statements text[]);
                INSERT INTO supabase_migrations.schema_migrations VALUES('20260929135736','fictional_history',ARRAY['SELECT 1;']);
                INSERT INTO public.stores(id,name) VALUES('berts','TEST ONLY Additive Baseline');
                INSERT INTO public.store_state(store_id,revision) VALUES('berts',0);''')
            original = receipt(await preservation.ledger_fingerprints(conn))
            for entry in original['delivery']:
                body = additive.sql_body((readiness.ROOT / entry['sourceFile']).read_bytes())
                await conn.execute(body)
                name = Path(entry['deliveryFile']).name.split('_', 1)[1].removesuffix('.sql')
                await conn.execute('INSERT INTO supabase_migrations.schema_migrations VALUES($1,$2,$3)',
                                   entry['deliveryVersion'], name, [body])
            cls.workflow = await workflow.run(cls.control.rsplit('/', 1)[0] + '/' + cls.template)
            if cls.workflow['actualFoodCost'] != '55.00':
                raise AssertionError('Fictional Track 1 baseline is incorrect')
            return original
        except Exception:
            if conn:
                await conn.close()
                conn = None
            await admin.execute('DROP DATABASE ' + cls.template)
            raise
        finally:
            if conn: await conn.close()
            await admin.close()

    @classmethod
    def tearDownClass(cls):
        async def cleanup():
            admin = await asyncpg.connect(cls.control)
            try: await admin.execute('DROP DATABASE ' + cls.template)
            finally: await admin.close()
        asyncio.run(cleanup())

    async def asyncSetUp(self):
        self.admin = await asyncpg.connect(self.control)
        self.name = 'native_purchase_test_additive_' + uuid4().hex
        await self.admin.execute('CREATE DATABASE ' + self.name + ' TEMPLATE ' + self.template)
        self.dsn = self.control.rsplit('/', 1)[0] + '/' + self.name
        self.conn = await asyncpg.connect(self.dsn)

    async def asyncTearDown(self):
        await self.conn.close()
        await self.admin.execute('DROP DATABASE ' + self.name)
        await self.admin.close()

    async def plan(self):
        return await additive.prepare(self.conn, self.original, '20261014010000', client_roles=())

    async def fresh_verify(self, plan):
        other = await asyncpg.connect(self.dsn, server_settings={'default_transaction_read_only': 'on'})
        try: return await additive.verify_outcome(other, plan)
        finally: await other.close()

    async def test_dry_run_is_readonly_and_success_is_durable_without_business_changes(self):
        before = await additive.snapshot(self.conn)
        params = self.workflow['actualReportParams']
        before_report = await actual.period_report(self.conn, self.workflow['temporaryStore'],
                                                  UUID(params['opening']), UUID(params['closing']))
        plan = await self.plan()
        self.assertEqual(await additive.snapshot(self.conn), before)
        self.assertFalse(await self.conn.fetchval('SELECT to_regclass($1) IS NOT NULL', additive.INDEX))
        self.assertEqual((await self.fresh_verify(plan))['status'], 'verified_not_applied')
        result = await additive.apply(self.conn, plan)
        self.assertTrue(result['sqlCommitted'])
        checked = await self.fresh_verify(plan)
        self.assertEqual(checked['status'], 'verified_applied')
        self.assertTrue(checked['historicalLedgerPreserved'])
        self.assertTrue(checked['originalRowsAndCatalogPreserved'])
        self.assertEqual(len(await preservation.ledger_fingerprints(self.conn)), 31)
        self.assertEqual((await additive.snapshot(self.conn))['rows'], before['rows'])
        self.assertEqual(await actual.period_report(self.conn, self.workflow['temporaryStore'],
                                                   UUID(params['opening']), UUID(params['closing'])), before_report)

    async def test_failed_ledger_insert_rolls_back_the_index_and_all_history(self):
        plan = await self.plan()
        with self.assertRaises(additive.AdditiveFailure) as error:
            await additive.apply(FaultConnection(self.conn, ledger_failure=True), plan)
        self.assertTrue(error.exception.report['rollbackCompleted'])
        self.assertFalse(error.exception.report['commitAttempted'])
        self.assertEqual(await additive.snapshot(self.conn), plan['baseline'])
        self.assertEqual((await self.fresh_verify(plan))['status'], 'verified_not_applied')

    async def test_lost_commit_ack_is_unknown_until_fresh_read_and_never_blindly_reapplied(self):
        plan = await self.plan()
        with self.assertRaises(additive.AdditiveFailure) as error:
            await additive.apply(FaultConnection(self.conn, commit_ack_loss=True), plan)
        self.assertEqual(error.exception.report['status'], 'commit_outcome_unknown')
        self.assertIsNone(error.exception.report['sqlCommitted'])
        self.assertFalse(error.exception.report['automaticRetry'])
        self.assertEqual((await self.fresh_verify(plan))['status'], 'verified_applied')
        with self.assertRaises(additive.AdditiveFailure) as second:
            await additive.apply(self.conn, plan)
        self.assertFalse(second.exception.report['commitAttempted'])
        self.assertEqual(len(await preservation.ledger_fingerprints(self.conn)), 31)

    async def test_partial_or_changed_native_body_and_changed_older_history_are_refused(self):
        for query in (
            "DELETE FROM supabase_migrations.schema_migrations WHERE version='20261008190001'",
            "UPDATE supabase_migrations.schema_migrations SET statements=ARRAY['SELECT 2;'] WHERE version='20261008190001'",
            "UPDATE supabase_migrations.schema_migrations SET name='changed' WHERE version='20260929135736'",
        ):
            tx = self.conn.transaction(isolation='repeatable_read')
            await tx.start()
            try:
                await self.conn.execute(query)
                with self.assertRaises(ValueError): await self.plan()
            finally: await tx.rollback()

    async def test_changed_checksum_or_database_rows_hold_before_ddl(self):
        plan = await self.plan()
        changed = deepcopy(plan)
        changed['migration']['sha256'] = '0' * 64
        with self.assertRaises(ValueError): await additive.apply(self.conn, changed)
        await self.conn.execute("UPDATE public.stores SET name='TEST ONLY Concurrent Change' WHERE id='berts'")
        with self.assertRaises(additive.AdditiveFailure) as error:
            await additive.apply(self.conn, plan)
        self.assertFalse(error.exception.report['commitAttempted'])
        self.assertFalse(await self.conn.fetchval('SELECT to_regclass($1) IS NOT NULL', additive.INDEX))

    async def test_existing_or_wrong_index_without_ledger_is_refused(self):
        for columns in ('document_version_id,parse_run_id', 'parse_run_id,document_version_id'):
            await self.conn.execute('CREATE INDEX document_source_rows_version_run_idx '
                                    'ON purchasing.document_source_rows(' + columns + ')')
            with self.assertRaises(ValueError): await self.plan()
            await self.conn.execute('DROP INDEX ' + additive.INDEX)

    async def test_unrelated_readiness_failure_is_refused(self):
        await self.conn.execute('ALTER TABLE purchasing.document_versions DISABLE TRIGGER ALL')
        with self.assertRaises(ValueError): await self.plan()

    async def test_lock_contention_times_out_without_recording_or_index_creation(self):
        plan = await self.plan()
        other = await asyncpg.connect(self.dsn)
        tx = other.transaction()
        await tx.start()
        try:
            await other.execute('LOCK TABLE purchasing.document_source_rows IN ROW EXCLUSIVE MODE')
            with self.assertRaises(additive.AdditiveFailure) as error:
                await additive.apply(self.conn, plan)
            self.assertEqual(error.exception.report['errorType'], 'LockNotAvailableError')
            self.assertTrue(error.exception.report['rollbackCompleted'])
            self.assertEqual(await additive.snapshot(self.conn), plan['baseline'])
        finally:
            await tx.rollback()
            await other.close()

    async def test_wrong_database_identity_and_nested_application_are_refused(self):
        plan = await self.plan()
        changed = deepcopy(plan)
        changed['baseline']['identity']['database_oid'] += 1
        with self.assertRaises(additive.AdditiveFailure): await additive.apply(self.conn, changed)
        async with self.conn.transaction():
            with self.assertRaises(ValueError): await additive.apply(self.conn, plan)

    async def test_reconcile_refuses_partial_index_and_forged_additive_history(self):
        plan = await self.plan()
        await additive.apply(self.conn, plan)
        await self.conn.execute("UPDATE supabase_migrations.schema_migrations SET statements=ARRAY['SELECT 99;'] WHERE version='20261014010000'")
        with self.assertRaises(ValueError): await self.fresh_verify(plan)

    async def test_unresolved_writer_holds_reconciliation_until_disconnect_proves_rollback(self):
        plan = await self.plan()
        with self.assertRaises(additive.AdditiveFailure) as error:
            await additive.apply(FaultConnection(self.conn, commit_ack_loss=True, drop_before_commit=True), plan)
        self.assertEqual(error.exception.report['status'], 'commit_outcome_unknown')
        with self.assertRaises(ValueError): await self.fresh_verify(plan)
        # Release the original server transaction before judging visibility.
        await self.conn.close()
        self.conn = await asyncpg.connect(self.dsn)
        self.assertEqual((await self.fresh_verify(plan))['status'], 'verified_not_applied')
        self.assertEqual(await additive.snapshot(self.conn), plan['baseline'])

    async def test_cli_modes_require_reviewed_plan_hash_and_keep_existing_receipts(self):
        before = await additive.snapshot(self.conn)
        with TemporaryDirectory() as directory, patch.dict(os.environ, {'NATIVE_PURCHASE_TEST_DSN': self.dsn}):
            root = Path(directory)
            original = root / 'original.json'
            original.write_text(json.dumps(self.original), encoding='utf-8')
            plan_file = root / 'plan.json'
            args = SimpleNamespace(mode='dry-run', output=str(plan_file), original_install_receipt=str(original),
                                   delivery_version='20261014010000', plan=None, plan_sha256=None)
            self.assertEqual(await additive.main(args), 0)
            self.assertEqual(await additive.snapshot(self.conn), before)
            plan_hash = additive.digest(plan_file.read_bytes())
            args.mode = 'apply'
            args.plan = str(plan_file)
            args.plan_sha256 = '0' * 64
            args.output = str(root / 'wrong-hash.json')
            self.assertEqual(await additive.main(args), 2)
            self.assertEqual(await additive.snapshot(self.conn), before)
            args.plan_sha256 = plan_hash
            args.output = str(root / 'applied.json')
            self.assertEqual(await additive.main(args), 0)
            result = json.loads(Path(args.output).read_text())
            self.assertEqual(result['status'], 'passed_local_additive_install')
            self.assertEqual(result['independentVerification']['status'], 'verified_applied')
            saved = Path(args.output).read_bytes()
            with self.assertRaises(ValueError): await additive.main(args)
            self.assertEqual(Path(args.output).read_bytes(), saved)
            args.mode = 'reconcile'
            args.output = str(root / 'reconciled.json')
            self.assertEqual(await additive.main(args), 0)
            self.assertEqual(json.loads(Path(args.output).read_text())['status'], 'verified_applied')
