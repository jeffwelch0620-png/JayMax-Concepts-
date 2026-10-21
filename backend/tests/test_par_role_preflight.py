"""Fictional permission observations; no hosted connection or configuration."""
import asyncio
import ast
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

import asyncpg
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/ops'))
import par_role_preflight as preflight
import test_reviewed_par_install as fixture


class Transaction:
    def __init__(self, conn): self.conn = conn
    async def start(self): self.conn.depth += 1
    async def commit(self):
        self.conn.depth -= 1
        if self.conn.fail_commit: raise OSError('TEST ONLY private commit text')
    async def rollback(self):
        self.conn.depth -= 1
        if self.conn.fail_rollback: raise OSError('TEST ONLY private rollback text')


class Connection:
    def __init__(self):
        self.depth = 0; self.options = []; self.statements = []
        self.fail_commit = self.fail_rollback = False
    def is_in_transaction(self): return self.depth != 0
    def transaction(self, **options):
        self.options.append(options)
        return Transaction(self)
    async def execute(self, sql): self.statements.append(sql)
    async def fetchval(self, sql, *args):
        self.statements.append(sql)
        return {'SHOW transaction_read_only':'on', 'SHOW transaction_isolation':'repeatable read',
                'SHOW search_path':'pg_catalog'}.get(sql, True)


class ParRolePreflightGuards(unittest.IsolatedAsyncioTestCase):
    async def run_report(self, *, rule=None, conn=None, ledger_held=False):
        conn = conn or Connection()
        async def backend(_, roles):
            if rule and roles == ['test_only_bad']:
                raise preflight.engine.BackendPermissionHeld(roles[0], rule)
        async def ledger(_, roles):
            if ledger_held and roles == ['anon']:
                raise preflight.Held('TEST ONLY private ledger text')
        observations = {'status': 'observed', 'schemas': [], 'globalPublicDefaultGrant': False}
        with patch.object(preflight.engine, 'backend_permissions', AsyncMock(side_effect=backend)) as check, \
             patch.object(preflight, 'ledger_clients', AsyncMock(side_effect=ledger)), \
             patch.object(preflight, 'managed_observations', AsyncMock(return_value=observations)):
            report = await preflight.collect(conn, ['anon', 'authenticated'], ['test_only_bad', 'test_only_good'])
        return report, conn, check

    async def test_first_refusal_leaves_later_rules_unvisited_and_other_roles_are_checked(self):
        for index, rule in enumerate(preflight.RULES):
            with self.subTest(rule=rule):
                report, conn, check = await self.run_report(rule=rule)
                self.assertEqual(list(report['backendRoles'][0]['checks'].values()),
                                 ['passed'] * index + ['held'] + ['not_evaluated'] * (5-index))
                self.assertEqual(set(report['backendRoles'][1]['checks'].values()), {'passed'})
                self.assertEqual(check.await_count, 2)
                self.assertEqual(conn.depth, 0)
                self.assertTrue(all(o == {'readonly': True, 'isolation': 'repeatable_read'} for o in conn.options))
                if rule == 'flags':
                    self.assertEqual(report['backendRoles'][0]['managedObservations']['status'], 'not_evaluated')

    async def test_ledger_denial_and_summary_never_echo_private_names_or_error_text(self):
        report, _, _ = await self.run_report(ledger_held=True)
        self.assertEqual(report['ledgerRoles'][0], {'role': 'anon', 'status': 'held'})
        summary = json.dumps(preflight.public_summary(report))
        self.assertNotIn('test_only_', summary)
        self.assertNotIn('private', summary)
        self.assertFalse(preflight.public_summary(report)['fullReadinessEvaluated'])
        self.assertFalse(report['automaticApply']); self.assertFalse(report['operationalReleaseApproved'])

    async def test_missing_backend_is_explicit_unvisited_and_never_ledger_success(self):
        roles = ['test_only_bad', 'test_only_good']
        for missing in [(roles[0],), (roles[1],), tuple(roles)]:
            with self.subTest(missing=missing):
                conn = Connection()
                original = conn.fetchval
                async def fetchval(sql, *args):
                    return False if args and args[0] in missing else await original(sql, *args)
                conn.fetchval = fetchval
                report, _, check = await self.run_report(conn=conn)
                for row in report['backendRoles']:
                    if row['role'] in missing:
                        self.assertEqual(row, {'role': row['role'],
                            'checks': dict.fromkeys(preflight.RULES, 'not_evaluated'),
                            'reason': 'missing_role', 'managedObservations': {'status': 'not_evaluated'}})
                        self.assertIn({'role': row['role'], 'status': 'held', 'reason': 'missing_role'},
                                      report['ledgerRoles'])
                    else:
                        self.assertEqual(set(row['checks'].values()), {'passed'})
                        self.assertNotIn('reason', row)
                present = [role for role in roles if role not in missing]
                self.assertEqual([entry.args[1][0] for entry in check.await_args_list], present)
                summary = preflight.public_summary(report)
                self.assertEqual(summary['checks'], {'passed': 7 * len(present) + 2,
                    'held': len(missing), 'not_evaluated': len(preflight.RULES) * len(missing)})
                self.assertEqual(summary['managedObservationRoles'], len(present))
                self.assertNotIn('test_only_', json.dumps(summary))
                self.assertNotIn('missing_role', json.dumps(summary))
                self.assertEqual(report['status'], 'observations_recorded')
                self.assertFalse(summary['fullReadinessEvaluated'])
                self.assertFalse(summary['automaticApply'])
                self.assertFalse(summary['operationalReleaseApproved'])
                self.assertEqual(conn.depth, 0)

    async def test_backend_existence_read_failure_propagates_and_rolls_back(self):
        conn = Connection()
        original = conn.fetchval
        async def fetchval(sql, *args):
            if args == ('test_only_bad',):
                raise ConnectionError('TEST ONLY private role lookup failure')
            return await original(sql, *args)
        conn.fetchval = fetchval
        with patch.object(preflight.engine, 'backend_permissions', AsyncMock()) as check:
            with self.assertRaises(ConnectionError):
                await preflight.collect(conn, ['anon','authenticated'], ['test_only_bad'])
        check.assert_not_awaited()
        self.assertEqual(conn.depth, 0)

    async def test_invalid_or_empty_classification_and_nested_transactions_refuse_before_sql(self):
        cases = [([], ['test_only_bad']), (['anon','authenticated'], []),
                 (['anon','authenticated'], ['anon']),
                 (['anon','authenticated'], ['bad;role']),
                 (['anon','authenticated'], ['test_only_bad'] * 2),
                 (['anon','authenticated'], ['test_only_' + str(i) for i in range(31)])]
        for clients, backends in cases:
            with self.subTest(clients=clients, backends=backends):
                conn = Connection()
                with self.assertRaises(ValueError): await preflight.collect(conn, clients, backends)
                self.assertEqual(conn.statements, []); self.assertEqual(conn.options, [])
        conn = Connection(); conn.depth = 1
        with self.assertRaises(ValueError):
            await preflight.collect(conn, ['anon','authenticated'], ['test_only_bad'])
        self.assertEqual(conn.statements, []); self.assertEqual(conn.options, [])

    async def test_read_or_cleanup_failure_propagates_instead_of_returning_a_success_receipt(self):
        for mode in ('read', 'rollback', 'not_readonly'):
            with self.subTest(mode=mode):
                conn = Connection()
                conn.fail_rollback = mode == 'rollback'
                if mode == 'not_readonly': conn.fetchval = AsyncMock(return_value='off')
                with patch.object(preflight.engine, 'backend_permissions',
                                  AsyncMock(side_effect=TimeoutError('TEST ONLY private driver text'))):
                    with self.assertRaises((TimeoutError, ValueError)):
                        await preflight.collect(conn, ['anon','authenticated'], ['test_only_bad'])
                self.assertEqual(conn.depth, 0)
        conn = Connection(); conn.fail_commit = True
        with self.assertRaises(OSError): await self.run_report(conn=conn)
        conn = Connection(); conn.fail_rollback = True
        with self.assertRaises(preflight.engine.BackendPermissionHeld):
            await self.run_report(conn=conn, rule='flags')

    async def test_operation_deadline_cancels_reads_and_rolls_back_without_a_report(self):
        conn = Connection()
        async def blocked(*_): await asyncio.Event().wait()
        with patch.object(preflight, 'OPERATION_SECONDS', 0.01), \
             patch.object(preflight.engine, 'backend_permissions', blocked):
            with self.assertRaises(TimeoutError):
                await preflight.collect(conn, ['anon','authenticated'], ['test_only_bad'])
        self.assertEqual(conn.depth, 0)

    async def test_deadline_keeps_the_bounded_cleanup_failure_after_timeout_translation(self):
        conn = Connection(); conn.fail_rollback = True
        async def blocked(*_): await asyncio.Event().wait()
        with patch.object(preflight, 'OPERATION_SECONDS', 0.01), \
             patch.object(preflight.engine, 'backend_permissions', blocked):
            with self.assertRaises(TimeoutError) as error:
                await preflight.collect(conn, ['anon','authenticated'], ['test_only_bad'])
        self.assertEqual(error.exception.snapshotCleanupErrorType, 'OSError')
        self.assertNotIn('private', json.dumps(preflight.error_details(error.exception)))
        self.assertEqual(conn.depth, 0)

    async def test_caller_search_path_or_isolation_cannot_masquerade_as_reviewed_settings(self):
        for setting in ('SHOW search_path','SHOW transaction_isolation'):
            with self.subTest(setting=setting):
                conn = Connection(); original = conn.fetchval
                async def fetchval(sql, *args):
                    return 'unreviewed' if sql == setting else await original(sql,*args)
                conn.fetchval = fetchval
                with self.assertRaises(ValueError): await self.run_report(conn=conn)
                self.assertEqual(conn.depth, 0)

    async def test_source_and_scope_are_bound_without_claiming_release_or_readiness(self):
        report, _, _ = await self.run_report()
        self.assertEqual(report['sourceHashes'], preflight.source_hashes())
        self.assertIn('tools/ops/par_role_preflight.py', report['sourceHashes'])
        for key in ('clientPrivateAccess','fullReadiness','writerDrain','backupAndRestore','runtimeRlsCutover'):
            self.assertEqual(report['scope'][key], 'not_evaluated')
        bad = deepcopy(report); bad['status'] = 'passed'
        with self.assertRaises(ValueError): preflight.public_summary(bad)

    async def test_prefix_mapping_matches_actual_installer_raise_order(self):
        tree = ast.parse(Path(preflight.engine.__file__).read_text(encoding='utf-8'))
        guard = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                     and node.name == 'backend_permissions')
        raises = sorted((node for node in ast.walk(guard) if isinstance(node, ast.Raise)), key=lambda n:n.lineno)
        self.assertEqual(tuple(node.exc.args[1].value for node in raises), preflight.RULES)
        conn = Connection()
        with patch.object(preflight.engine.BackendPermissionHeld, 'MESSAGES', {'unknown':'changed'}):
            with self.assertRaises(ValueError):
                await preflight.collect(conn, ['anon','authenticated'], ['test_only_bad'])
        self.assertEqual(conn.options, [])


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class ParRolePreflightDatabaseTests(unittest.IsolatedAsyncioTestCase):
    # Reuse only the fixture lifecycle; do not inherit another class's tests.
    build_template = fixture.ParInstallDatabaseTests.__dict__['build_template']
    setUpClass = fixture.ParInstallDatabaseTests.__dict__['setUpClass']
    remove_roles = fixture.ParInstallDatabaseTests.__dict__['remove_roles']
    tearDownClass = fixture.ParInstallDatabaseTests.__dict__['tearDownClass']
    asyncSetUp = fixture.ParInstallDatabaseTests.asyncSetUp
    asyncTearDown = fixture.ParInstallDatabaseTests.asyncTearDown
    backend_role = fixture.ParInstallDatabaseTests.backend_role

    async def report(self, backends):
        conn = await asyncpg.connect(self.dsn, server_settings={'default_transaction_read_only':'on',
                                                              'search_path':'public, pg_catalog'})
        pid = await conn.fetchval('SELECT pg_backend_pid()')
        try:
            async with asyncio.timeout(60):
                report = await preflight.collect(conn, ['anon','authenticated'], backends)
            self.assertEqual(report['snapshot'], {'readOnly':'on', 'isolation':'repeatable read',
                                                  'searchPath':'pg_catalog'})
            self.assertEqual(await conn.fetchval('SHOW search_path'), 'public, pg_catalog')
            return report
        finally:
            await asyncio.wait_for(conn.close(), 5)
            self.assertTrue(conn.is_closed())
            self.assertFalse(await self.conn.fetchval('SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE pid=$1)', pid))

    async def test_readonly_report_keeps_catalog_accounting_and_role_inventory_unchanged(self):
        role = await self.backend_role()
        before = await fixture.engine.snapshot(self.conn)
        async with self.conn.transaction(readonly=True):
            facts = await fixture.hosted.backup.fingerprint(self.conn)
        report = await self.report([role])
        self.assertEqual(set(report['backendRoles'][0]['checks'].values()), {'passed'})
        self.assertEqual(set(item['status'] for item in report['ledgerRoles']), {'passed'})
        self.assertEqual(await fixture.engine.snapshot(self.conn), before)
        async with self.conn.transaction(readonly=True):
            self.assertEqual(await fixture.hosted.backup.fingerprint(self.conn), facts)

    async def test_real_refusals_report_only_the_evaluated_prefix(self):
        role = await self.backend_role()
        owner = await self.conn.fetchval('SELECT current_user')
        changes = [
            ('flags', 'ALTER ROLE '+role+' NOLOGIN', 'ALTER ROLE '+role+' LOGIN'),
            ('membership', 'GRANT anon TO '+role, 'REVOKE anon FROM '+role),
            ('ddl', 'GRANT CREATE ON SCHEMA public TO '+role, 'REVOKE CREATE ON SCHEMA public FROM '+role),
            ('ownership', 'ALTER TABLE purchasing.item_bases OWNER TO '+role,
             'ALTER TABLE purchasing.item_bases OWNER TO '+owner),
            ('default_acl', 'ALTER DEFAULT PRIVILEGES GRANT SELECT ON TABLES TO '+role,
             'ALTER DEFAULT PRIVILEGES REVOKE SELECT ON TABLES FROM '+role),
            ('new_par_access', 'CREATE TABLE purchasing.inventory_par_versions(test_only integer); '
             'GRANT SELECT ON purchasing.inventory_par_versions TO '+role,
             'DROP TABLE purchasing.inventory_par_versions')]
        for index, (rule, change, undo) in enumerate(changes):
            with self.subTest(rule=rule):
                await self.conn.execute(change)
                try:
                    report = await self.report(['test_only_missing_preflight_role', role])
                    self.assertEqual(report['backendRoles'][0], {
                        'role': 'test_only_missing_preflight_role', 'reason': 'missing_role',
                        'checks': dict.fromkeys(preflight.RULES, 'not_evaluated'),
                        'managedObservations': {'status': 'not_evaluated'}})
                    self.assertIn({'role': 'test_only_missing_preflight_role', 'status': 'held',
                                   'reason': 'missing_role'}, report['ledgerRoles'])
                    self.assertEqual(list(report['backendRoles'][1]['checks'].values()),
                                     ['passed'] * index + ['held'] + ['not_evaluated'] * (5-index))
                finally: await self.conn.execute(undo)

    async def test_public_and_extensions_findings_are_observed_without_waiving_installer_rules(self):
        role = await self.backend_role()
        await self.conn.execute('CREATE SCHEMA IF NOT EXISTS extensions; GRANT CREATE ON SCHEMA extensions TO '+role)
        await self.conn.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO '+role)
        await self.conn.execute('ALTER DEFAULT PRIVILEGES GRANT SELECT ON TABLES TO PUBLIC')
        before = await fixture.engine.snapshot(self.conn)
        report = await self.report([role])
        self.assertEqual(set(report['backendRoles'][0]['checks'].values()), {'passed'})
        observations = report['backendRoles'][0]['managedObservations']
        self.assertTrue(observations['globalPublicDefaultGrant'])
        schemas = {item['schema']:item for item in observations['schemas']}
        self.assertTrue(schemas['extensions']['can_create'])
        self.assertTrue(schemas['public']['future_grant'])
        self.assertGreaterEqual(preflight.public_summary(report)['managedFindings'], 3)
        self.assertFalse(report['operationalReleaseApproved'])
        self.assertEqual(await fixture.engine.snapshot(self.conn), before)

    async def test_injected_write_is_refused_and_connection_is_closed_without_a_report(self):
        role = await self.backend_role()
        before = await fixture.engine.snapshot(self.conn)
        async def write(conn, _):
            await conn.execute('CREATE TABLE public.test_only_preflight_write(value integer)')
        with patch.object(preflight, 'managed_observations', write):
            with self.assertRaises(asyncpg.ReadOnlySQLTransactionError): await self.report([role])
        self.assertEqual(await fixture.engine.snapshot(self.conn), before)
