"""Atomic local install, fsync failures and independently reconciled commits."""
import os
import asyncio
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
import asyncpg
import local_parallel_install as installer
import test_hosted_native_install as fixture
import runtime_permissions as runtime
import auxiliary_permissions as auxiliary
import db_pg
import db_auxiliary


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable local PostgreSQL required')
class ParallelInstallerCatalog(unittest.IsolatedAsyncioTestCase):
    def save_evidence(self, actual_singleton_return):
        if not os.environ.get('LOCAL_PARALLEL_INSTALL_EVIDENCE_DIR'): return
        target = Path(os.environ['LOCAL_PARALLEL_INSTALL_EVIDENCE_DIR'])
        target.mkdir(exist_ok=True)
        receipt = {'format': 'jaymax-local-parallel-install-trial-v1', 'status': 'passed',
                   'test': self._testMethodName, 'journal': self.journal.rows(),
                   'preservationPins': self.controller.plan['preservationPins'],
                   'originalActualSingletonReturnPassed': actual_singleton_return,
                   'baselineProjectionPreserved': True, 'hostedChanges': False,
                   'passwordAuthenticationProved': False, 'processRestartRecoveryProved': False,
                   'hostedCapacityGatePassed': False, 'operationalReleaseApproved': False}
        (target / (self._testMethodName + '.json')).write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')

    async def asyncSetUp(self):
        await fixture.NativeInstallTests.asyncSetUp(self)
        self.roles = []
        try:
            await fixture.NativeInstallTests.run_install(self)
            self.originals = {kind: 'jaymax_build_' + kind + '_' + uuid4().hex[:12] for kind in ('inventory', 'accounts')}
            self.replacements = {kind: 'jaymax_build_' + kind + '_' + uuid4().hex[:12] for kind in self.originals}
            for kind, name in self.originals.items():
                await self.conn.execute('CREATE ROLE ' + name + ' LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION CONNECTION LIMIT 6')
                self.roles.append(name)
                schemas = ('public', *runtime.readiness.PRIVATE) if kind == 'inventory' else ('public',)
                for schema in schemas: await self.conn.execute('GRANT USAGE ON SCHEMA ' + schema + ' TO ' + name)
                tables = runtime.table_privileges(runtime.manifest()) if kind == 'inventory' else {'public.' + table: auxiliary.VERBS for table in auxiliary.TABLES}
                for table, verbs in tables.items(): await self.conn.execute('GRANT ' + ','.join(verbs) + ' ON ' + table + ' TO ' + name)
                if kind == 'inventory':
                    for signature, value in runtime.contract(runtime.manifest())['functions'].items():
                        if not value['securityDefiner'] and (value['name'].startswith('public.') or not value['trigger']):
                            await self.conn.execute('GRANT EXECUTE ON FUNCTION ' + signature + ' TO ' + name)
                public = runtime.PUBLIC if kind == 'inventory' else {table: auxiliary.VERBS for table in auxiliary.TABLES}
                prefix = 'runtime_candidate_' if kind == 'inventory' else 'auxiliary_candidate_'
                for table, verbs in public.items():
                    for verb in verbs:
                        clause = 'WITH CHECK(true)' if verb == 'INSERT' else 'USING(true) WITH CHECK(true)' if verb == 'UPDATE' else 'USING(true)'
                        await self.conn.execute('CREATE POLICY ' + prefix + verb.lower() + ' ON public.' + table + ' FOR ' + verb + ' TO ' + name + ' ' + clause)
            self.journal = installer.Journal(Path(self.temp.name) / 'install-journal.jsonl', self.name)
            self.controller = await installer.LocalInstaller.prepare(self.dsn, self.journal, self.originals, self.replacements)
        except BaseException:
            await self.asyncTearDown(); raise

    async def asyncTearDown(self):
        # Fixture-owned DB deletion removes only this unique database's grants.
        # Reconcile all actual generated role names before exact teardown DROP.
        actual = await self.admin.fetch('SELECT rolname FROM pg_roles WHERE rolname=ANY($1::text[])',
            self.roles + list(getattr(self, 'replacements', {}).values()))
        await fixture.NativeInstallTests.asyncTearDown(self)
        conn = await asyncpg.connect(os.environ['NATIVE_PURCHASE_TEST_DSN'])
        try:
            for row in actual: await conn.execute('DROP ROLE ' + row['rolname'])
        finally: await conn.close()

    async def test_failure_boundaries_unknown_commits_full_actual_pool_return_and_preservation(self):
        control = self.controller
        globals_before = (db_pg._pool, db_auxiliary._pool, db_pg._retry_task, db_auxiliary._retry_task)
        # Atomic statement failure does not leave one of the two created roles.
        with self.assertRaises(installer.RehearsalHeld): await control.step('create', _fault='mid_statement')
        self.assertEqual(await control.reconcile(), 'not_committed')
        self.assertEqual(await installer.snapshot(self.conn), control.baseline)
        with self.assertRaises(asyncio.CancelledError):
            await control.step('create', _fault='cancel_after_statement')
        self.assertTrue(control.held)
        self.assertEqual(await control.reconcile(), 'not_committed')
        # Failed durable expectation write rolls back before any COMMIT.
        append = self.journal.append
        def fail_expectation(event, data):
            if event == 'expected': raise OSError('Invented local journal failure')
            return append(event, data)
        with patch.object(self.journal, 'append', side_effect=fail_expectation):
            with self.assertRaises(installer.RehearsalHeld): await control.step('create')
        self.assertEqual(await control.reconcile(), 'not_committed')
        # Both possible outcomes of a missing COMMIT acknowledgement are held.
        for fault, state in (('lost_ack_not_committed', 'not_committed'), ('lost_ack_committed', 'committed')):
            with self.subTest(fault=fault), self.assertRaises(installer.RehearsalHeld):
                await control.step('create', _fault=fault)
            with self.assertRaises(installer.RehearsalHeld): await control.step('create')
            self.assertEqual(await control.reconcile(), state)
        self.assertEqual(len(control.oids), 2)
        for row in (await installer.snapshot(self.conn))['roles']:
            if row['rolname'] in self.replacements.values(): self.assertFalse(row['rolcanlogin'])
        # Atomic grant failure restores both ACLs and all original policy TOs.
        before = await installer.snapshot(self.conn)
        with self.assertRaises(installer.RehearsalHeld): await control.step('overlap', _fault='mid_statement')
        self.assertEqual(await control.reconcile(), 'not_committed')
        self.assertEqual(await installer.snapshot(self.conn), before)
        with self.assertRaises(installer.RehearsalHeld): await control.step('overlap', _fault='lost_ack_committed')
        self.assertEqual(await control.reconcile(), 'committed')
        await control.step('enable')
        # Failed actual peer closes the real primary pool; globals never change.
        with patch.object(db_auxiliary, '_try_connect', AsyncMock(return_value=None)):
            with self.assertRaises(installer.permissions.TransitionError): await control.verify_overlap()
        with self.assertRaises(installer.RehearsalHeld): await control.step('restore')
        self.assertEqual(await self.admin.fetchval('SELECT count(*) FROM pg_stat_activity WHERE usename=ANY($1::text[])',
            list(self.originals.values()) + list(self.replacements.values())), 0)
        await control.verify_overlap()
        for fault, state in (('lost_ack_not_committed', 'not_committed'), ('lost_ack_committed', 'committed')):
            with self.assertRaises(installer.RehearsalHeld): await control.step('restore', _fault=fault)
            self.assertEqual(await control.reconcile(), state)
        with self.assertRaises(installer.RehearsalHeld): await control.step('disable_revoke')
        await control.verify_original_singletons()
        with self.assertRaises(installer.RehearsalHeld): await control.step('disable_revoke', _fault='lost_ack_committed')
        self.assertEqual(await control.reconcile(), 'committed')
        final = await installer.snapshot(self.conn); control.preserve(final)
        self.assertEqual((db_pg._pool, db_auxiliary._pool, db_pg._retry_task, db_auxiliary._retry_task), globals_before)
        for row in final['roles']:
            if row['rolname'] in self.replacements.values():
                self.assertFalse(row['rolcanlogin']); self.assertEqual(row['oid'], control.oids[row['rolname']])
        self.assertFalse(any(row['grantee'] in control.oids.values() for row in final['access']))
        self.assertEqual(final['rows'], control.baseline['rows'])
        self.assertEqual(final['ledger'], control.baseline['ledger'])
        self.assertEqual(final['sequences'], control.baseline['sequences'])
        self.assertIn('commit_unknown', [row['event'] for row in self.journal.rows()])
        self.save_evidence(True)

    async def test_collision_unknown_session_and_ambiguous_column_acl_never_auto_repaired(self):
        control = self.controller
        await self.conn.execute('CREATE ROLE ' + self.replacements['inventory'] + ' NOLOGIN')
        with self.assertRaises(installer.RehearsalHeld):
            await installer.LocalInstaller.prepare(self.dsn, self.journal, self.originals, self.replacements)
        self.assertTrue(await self.conn.fetchval('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=$1)', self.replacements['inventory']))
        await self.conn.execute('DROP ROLE ' + self.replacements['inventory']) # Exact invented collision owned by this fixture.
        with self.assertRaises(installer.RehearsalHeld): await control.step('create', _fault='lost_ack_committed')
        # Independent concurrent column grant prevents inferring success or rollback.
        name = self.originals['accounts']
        await self.conn.execute('GRANT SELECT(pin) ON public.staff_pins TO ' + name)
        self.assertEqual(await control.reconcile(), 'ambiguous')
        with self.assertRaises(installer.RehearsalHeld): await control.step('overlap')
        self.assertTrue(await self.conn.fetchval('SELECT has_column_privilege($1,\'public.staff_pins\',\'pin\',\'SELECT\')', name))
        await self.conn.execute('REVOKE SELECT(pin) ON public.staff_pins FROM ' + name)
        self.assertEqual(await control.reconcile(), 'committed')
        await control.step('overlap'); await control.step('enable')
        # The controller does not terminate a client or accept a fabricated proof.
        await control.verify_overlap()
        peer = await asyncpg.connect(control.profile_urls('original')['accounts'])
        try:
            with self.assertRaises(installer.RehearsalHeld): await control.step('restore')
            self.assertFalse(peer.is_closed())
            self.assertEqual(await control.reconcile(), 'not_committed')
        finally: await peer.close()
        control.preserve(await installer.snapshot(self.conn))
        self.save_evidence(False)
