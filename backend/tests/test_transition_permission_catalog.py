"""Real PostgreSQL RLS/ACL checks in an exact disposable loopback database.

No hosted role, grant, policy, row or client configuration is changed.
"""
import copy
import os
import unittest
from uuid import uuid4
from urllib.parse import urlsplit, urlunsplit
import asyncpg
import runtime_permissions as runtime
import auxiliary_permissions as auxiliary
import db_auxiliary
import transition_permissions as transition
import test_hosted_native_install as installed
import hosted_install_preservation as preservation
import schema_reconciliation as reconciliation
import test_transition_permissions as records


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable loopback PostgreSQL required')
class OverlapCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await installed.NativeInstallTests.asyncSetUp(self)
        self.roles = []
        try:
            await installed.NativeInstallTests.run_install(self)
            self.pairs = {}
            for kind in transition.PROFILES:
                self.pairs[kind] = {}
                for phase in ('original', 'replacement'):
                    role = 'jaymax_build_' + kind + '_' + uuid4().hex[:12]
                    await self.admin.execute('CREATE ROLE ' + role + ' LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION CONNECTION LIMIT 6')
                    self.roles.append(role)
                    oid = await self.admin.fetchval('SELECT oid FROM pg_roles WHERE rolname=$1', role)
                    self.pairs[kind][phase] = {'name': role, 'oid': oid}
            # Parent fixture pins a unique loopback database. Keep the existing
            # native_runtime_test_ role-name guard intact; create this fixture's
            # generated build identities using the independently frozen matrix.
            reference = runtime.contract(runtime.manifest())
            async with self.conn.transaction(readonly=True):
                await self.conn.execute('SET LOCAL search_path=pg_catalog')
                self.assertEqual((await runtime.catalog_contracts(self.conn))['functions'], reference['functions'])
            for new in (value['name'] for value in self.pairs['inventory'].values()):
                for schema in ('public', *runtime.readiness.PRIVATE):
                    await self.conn.execute('GRANT USAGE ON SCHEMA ' + schema + ' TO ' + new)
                for name, verbs in runtime.table_privileges(runtime.manifest()).items():
                    await self.conn.execute('GRANT ' + ','.join(verbs) + ' ON ' + name + ' TO ' + new)
                for signature, value in reference['functions'].items():
                    if not value['securityDefiner'] and (value['name'].startswith('public.') or not value['trigger']):
                        await self.conn.execute('GRANT EXECUTE ON FUNCTION ' + signature + ' TO ' + new)
            for kind, pair in self.pairs.items():
                tables = runtime.PUBLIC if kind == 'inventory' else {name: auxiliary.VERBS for name in auxiliary.TABLES}
                prefix = 'runtime_candidate_' if kind == 'inventory' else 'auxiliary_candidate_'
                names = [p['name'] for p in pair.values()]
                if kind == 'accounts':
                    for role in names:
                        await self.conn.execute('GRANT USAGE ON SCHEMA public TO ' + role)
                        for table in tables:
                            await self.conn.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON public.' + table + ' TO ' + role)
                for table, verbs in tables.items():
                    for verb in verbs:
                        policy = prefix + verb.lower()
                        clauses = 'WITH CHECK(true)' if verb == 'INSERT' else 'USING(true) WITH CHECK(true)' if verb == 'UPDATE' else 'USING(true)'
                        await self.conn.execute('CREATE POLICY ' + policy + ' ON public.' + table + ' FOR ' + verb + ' TO ' + ','.join(names) + ' ' + clauses)
            self.context = records.verified(records.record(self.pairs), expected_pairs=copy.deepcopy(self.pairs))
        except BaseException:
            await self.asyncTearDown()
            raise

    async def asyncTearDown(self):
        await installed.NativeInstallTests.asyncTearDown(self)
        admin = await asyncpg.connect(os.environ['NATIVE_PURCHASE_TEST_DSN'])
        try:
            for role in reversed(self.roles):
                await admin.execute('DROP ROLE ' + role)
        finally:
            await admin.close()

    def url(self, kind, phase='replacement'):
        role = self.pairs[kind][phase]['name']
        uri = urlsplit(self.dsn)
        return urlunsplit(uri._replace(netloc=role + '@127.0.0.1:' + str(uri.port)))

    async def assess(self, kind, phase='replacement', overlap=True):
        role = self.pairs[kind][phase]['name']
        conn = await asyncpg.connect(self.url(kind, phase))
        try:
            self.assertEqual(dict(await conn.fetchrow('SELECT session_user AS login,current_user AS current')),
                             {'login': role, 'current': role})
            context = self.context if overlap else None
            report = (await runtime.inspect(conn, role, transition=context) if kind == 'inventory'
                      else await auxiliary.inspect(conn, transition=context))
            self.assertTrue(report['readOnly'])
            self.assertFalse(report['operationalReleaseApproved'])
            return report
        finally:
            await conn.close()

    async def test_exact_overlap_real_logins_default_holds_and_metadata_rows_ledger_survive(self):
        columns = await preservation.original_columns(self.conn)
        rows = await preservation.fingerprints(self.conn, columns)
        ledger = await preservation.ledger_fingerprints(self.conn)
        catalog = (await reconciliation.capture(self.conn))['catalog']
        for kind in transition.PROFILES:
            for phase in ('original', 'replacement'):
                with self.subTest(profile=kind, phase=phase):
                    report = await self.assess(kind, phase)
                    self.assertEqual(report['status'], 'passed_local_candidate' if kind == 'inventory' else 'passed', report)
                    self.assertEqual((await self.assess(kind, phase, overlap=False))['status'], 'held')
        # Actual startup retains the singleton check even when diagnostic overlap passes.
        with self.assertLogs('db_auxiliary', level='WARNING'):
            self.assertIsNone(await db_auxiliary._try_connect(self.url('accounts')))
        conn = await asyncpg.connect(self.url('accounts'))
        try:
            for query in ('SELECT count(*) FROM public.staff_pins', 'SELECT count(*) FROM purchasing.posting_batches'):
                with self.assertRaises(asyncpg.InsufficientPrivilegeError):
                    await conn.fetchval(query)
        finally:
            await conn.close()
        self.assertEqual((await reconciliation.capture(self.conn))['catalog'], catalog)
        self.assertEqual(await preservation.fingerprints(self.conn, columns), rows)
        self.assertEqual(await preservation.ledger_fingerprints(self.conn), ledger)
        # The normal singleton state remains accepted after overlap ends.
        for kind, pair in self.pairs.items():
            tables = runtime.PUBLIC if kind == 'inventory' else {name: auxiliary.VERBS for name in auxiliary.TABLES}
            prefix = 'runtime_candidate_' if kind == 'inventory' else 'auxiliary_candidate_'
            for table, verbs in tables.items():
                for verb in verbs:
                    await self.conn.execute('ALTER POLICY ' + prefix + verb.lower() + ' ON public.' + table + ' TO ' + pair['replacement']['name'])
            self.assertEqual((await self.assess(kind, overlap=False))['status'], 'passed_local_candidate' if kind == 'inventory' else 'passed')
        pool = await db_auxiliary._try_connect(self.url('accounts'))
        self.assertIsNotNone(pool)
        if pool is not None:
            await pool.close()

    async def test_real_public_cross_profile_extra_restrictive_acl_and_identity_drift_hold(self):
        account = self.pairs['accounts']; inventory = self.pairs['inventory']
        names = ','.join(p['name'] for p in account.values())
        for target in ('PUBLIC', account['original']['name'], names + ',' + inventory['replacement']['name']):
            with self.subTest(policy_roles=target):
                await self.conn.execute('ALTER POLICY auxiliary_candidate_select ON public.app_users TO ' + target)
                self.assertEqual((await self.assess('accounts'))['status'], 'held')
                await self.conn.execute('ALTER POLICY auxiliary_candidate_select ON public.app_users TO ' + names)
        for clauses in ('AS RESTRICTIVE FOR SELECT USING(false)', 'FOR ALL USING(true) WITH CHECK(true)'):
            # Place TO between FOR and the expressions.
            declaration, expression = clauses.split(' USING', 1)
            with self.subTest(extra_policy=declaration):
                await self.conn.execute('CREATE POLICY invented_extra ON public.app_users ' + declaration + ' TO ' + names + ' USING' + expression)
                self.assertEqual((await self.assess('accounts'))['status'], 'held')
                await self.conn.execute('DROP POLICY invented_extra ON public.app_users')
        for grant, revoke, kind in (
                ('GRANT SELECT ON public.staff_pins TO ', 'REVOKE SELECT ON public.staff_pins FROM ', 'accounts'),
                ('GRANT SELECT(pin) ON public.staff_pins TO ', 'REVOKE SELECT(pin) ON public.staff_pins FROM ', 'accounts'),
                ('GRANT DELETE ON purchasing.posting_batches TO ', 'REVOKE DELETE ON purchasing.posting_batches FROM ', 'inventory')):
            role = self.pairs[kind]['replacement']['name']
            with self.subTest(excess_grant=kind + ':' + grant):
                await self.conn.execute(grant + role)
                self.assertEqual((await self.assess(kind))['status'], 'held')
                await self.conn.execute(revoke + role)
        role = account['replacement']['name']
        for change, restore in (('NOLOGIN', 'LOGIN'), ('INHERIT', 'NOINHERIT'), ('CONNECTION LIMIT 7', 'CONNECTION LIMIT 6')):
            with self.subTest(role_attribute=change):
                await self.admin.execute('ALTER ROLE ' + role + ' ' + change)
                with self.assertRaises(transition.TransitionError):
                    await self.assess('inventory', 'original')
                await self.admin.execute('ALTER ROLE ' + role + ' ' + restore)
        await self.admin.execute('GRANT ' + account['original']['name'] + ' TO ' + role + ' WITH INHERIT FALSE, SET TRUE')
        with self.assertRaises(transition.TransitionError):
            await self.assess('inventory', 'original')
        await self.admin.execute('REVOKE ' + account['original']['name'] + ' FROM ' + role)
        for kind in transition.PROFILES:
            self.assertEqual((await self.assess(kind))['status'], 'passed_local_candidate' if kind == 'inventory' else 'passed')
