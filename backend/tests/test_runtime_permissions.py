"""Catalog/ACL drift and read-only verification on invented full-chain databases."""
import os
import unittest
import hashlib
from uuid import uuid4
from unittest.mock import AsyncMock, Mock, patch

import asyncpg
import runtime_permissions as candidate
import runtime_role_fixture as fixture
import test_hosted_native_install as installed
import schema_reconciliation as reconciliation
import hosted_install_preservation as preservation


class RuntimeProfileTests(unittest.TestCase):
    def test_profile_pins_source_matrix_and_catalog_reference(self):
        profile = candidate.manifest()
        reference = candidate.contract(profile)
        matrix = candidate.table_privileges(profile)
        self.assertEqual(len(profile['migrationSha256']),30)
        self.assertNotIn('20261018_reviewed_inventory_pars.sql',profile['migrationSha256'])
        self.assertNotIn('purchasing.inventory_par_versions',matrix)
        with patch.object(candidate.readiness,'RUNTIME_CANDIDATE_MIGRATIONS',candidate.readiness.MIGRATIONS):
            with self.assertRaisesRegex(ValueError,'migration list drift'):candidate.manifest()
        self.assertEqual(len(reference['functions']), 94)
        self.assertEqual(len(reference['relations']), 123)
        for name in candidate.READ_ONLY_TABLES:
            self.assertEqual(matrix[name], ['SELECT'])
        self.assertIn('INSERT', matrix['prep_inventory.legacy_crosswalks'])
        for name in profile['tables'] + profile['views']:
            self.assertNotIn('DELETE', matrix[name])
        with patch.object(candidate, 'PRIVATE_UPDATES', candidate.PRIVATE_UPDATES | {'purchasing.posting_batches'}):
            with self.assertRaisesRegex(ValueError, 'matrix drift'):
                candidate.contract(profile)


class RuntimeFixtureSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_loopback_probe_proves_native_and_docker_forwarded_targets(self):
        database='native_purchase_test_'+uuid4().hex
        for address in ('127.0.0.1/32','172.18.0.2/32'):
            with self.subTest(address=address):
                identity=dict(cluster_id='synthetic-cluster',database_id=12345,server_address=address,server_port=5432)
                conn=Mock(fetchval=AsyncMock(return_value=database),fetchrow=AsyncMock(return_value=identity))
                probe=Mock(fetchrow=AsyncMock(return_value=identity),close=AsyncMock(),transaction=Mock(return_value=AsyncMock()))
                with patch.dict(os.environ,NATIVE_PURCHASE_TEST_DSN='postgresql://purchase_implementation_test@127.0.0.1:55439/native_purchase_test_control'),patch.object(fixture.asyncpg,'connect',AsyncMock(return_value=probe)) as connect:
                    await fixture.verify_disposable_target(conn)
                connect.assert_awaited_once_with('postgresql://purchase_implementation_test@127.0.0.1:55439/'+database,timeout=5)
                probe.transaction.assert_called_once_with(readonly=True)
                probe.close.assert_awaited_once()

    async def test_loopback_probe_refuses_untrusted_configuration_and_non_disposable_names(self):
        local='postgresql://purchase_implementation_test@127.0.0.1:55439/native_purchase_test_control'
        for dsn in ('',local.replace('127.0.0.1','db.example.invalid'),local.replace('127.0.0.1','172.18.0.2'),
                    local.replace('purchase_implementation_test@','other@'),local.replace('native_purchase_test_control','operational'),
                    local+'?host=db.example.invalid',local+'#other'):
            with self.subTest(dsn=dsn),patch.dict(os.environ,NATIVE_PURCHASE_TEST_DSN=dsn),patch.object(fixture.asyncpg,'connect',AsyncMock()) as connect:
                with self.assertRaises(ValueError):await fixture.verify_disposable_target(Mock())
                connect.assert_not_awaited()
        for database in ('native_purchase_test_control','operational','native_purchase_test_'+('a'*31)):
            conn=Mock(fetchval=AsyncMock(return_value=database))
            with self.subTest(database=database),patch.dict(os.environ,NATIVE_PURCHASE_TEST_DSN=local),patch.object(fixture.asyncpg,'connect',AsyncMock()) as connect:
                with self.assertRaisesRegex(ValueError,'Unique disposable'):await fixture.verify_disposable_target(conn)
                connect.assert_not_awaited()

    async def test_loopback_probe_refuses_different_database_identity_and_closes_on_failure(self):
        identity=dict(cluster_id='synthetic-cluster',database_id=12345,server_address='172.18.0.2/32',server_port=5432)
        conn=Mock(fetchval=AsyncMock(return_value='native_purchase_test_'+uuid4().hex),fetchrow=AsyncMock(return_value=identity))
        for field,value in dict(cluster_id='other',database_id=54321,server_address='172.18.0.3/32',server_port=5433).items():
            probe=Mock(fetchrow=AsyncMock(return_value=identity|{field:value}),close=AsyncMock(),transaction=Mock(return_value=AsyncMock()))
            with self.subTest(field=field),patch.dict(os.environ,NATIVE_PURCHASE_TEST_DSN='postgresql://purchase_implementation_test@127.0.0.1:55439/native_purchase_test_control'),patch.object(fixture.asyncpg,'connect',AsyncMock(return_value=probe)):
                with self.assertRaisesRegex(ValueError,'differs from loopback'):await fixture.verify_disposable_target(conn)
            probe.close.assert_awaited_once()

    async def test_fixture_safety_preserves_exact_sql_and_cleans_failed_setup(self):
        source = candidate.readiness.ROOT / 'migrations' / candidate.readiness.MIGRATIONS[0]
        class Parent:
            async def asyncSetUp(self):
                self.sql = source.read_text(encoding='utf-8')
                self.cleanups = 0
            async def asyncTearDown(self):
                self.cleanups += 1
        class FailingFixture(fixture.RuntimeRoleMixin, Parent):
            async def prepare_runtime(self):
                raise RuntimeError('Invented failed permission preparation')
        test = FailingFixture()
        with self.assertRaisesRegex(RuntimeError, 'Invented failed'):
            await test.asyncSetUp()
        self.assertEqual(hashlib.sha256(test.sql.encode()).digest(), hashlib.sha256(source.read_bytes()).digest())
        self.assertEqual(test.cleanups, 1)


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class RuntimePermissionTests(unittest.IsolatedAsyncioTestCase):
    # Reuse fixture operations, not standalone installer test methods: this
    # suite already installs its candidate during setup before assessing ACLs.
    run_install=installed.NativeInstallTests.run_install
    asyncTearDown=installed.NativeInstallTests.asyncTearDown

    async def asyncSetUp(self):
        # This suite assesses the frozen candidate, not later feature grants.
        with patch.object(candidate.readiness,'MIGRATIONS',candidate.readiness.RUNTIME_CANDIDATE_MIGRATIONS):
            await installed.NativeInstallTests.asyncSetUp(self)
            await self.run_install()
        self.role = 'native_runtime_test_' + uuid4().hex
        await self.admin.execute('CREATE ROLE ' + self.role + ' NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION')
        self.roles = [self.role]
        async def cleanup():
            conn = await asyncpg.connect(os.environ['NATIVE_PURCHASE_TEST_DSN'])
            try:
                for role in reversed(self.roles):
                    await conn.execute('DROP ROLE ' + role)
            finally:
                await conn.close()
        self.addAsyncCleanup(cleanup)
        await fixture.apply(self.conn, self.role)

    async def report(self):
        return await candidate.inspect(self.conn, self.role)

    async def held(self, kind, name=None):
        report = await self.report()
        self.assertEqual(report['status'], 'held', report)
        self.assertTrue(any(i['kind'] == kind and (name is None or i['object'] == name) for i in report['issues']), report)
        self.assertTrue(report['readOnly'])
        self.assertFalse(report['operationalReleaseApproved'])
        return report

    async def test_permissions_readonly_baseline_preserves_catalog_rows_and_owner_gate(self):
        before = (await reconciliation.capture(self.conn))['catalog']
        columns = await preservation.original_columns(self.conn)
        rows = await preservation.fingerprints(self.conn, columns)
        ledger = await preservation.ledger_fingerprints(self.conn)
        report = await self.report()
        self.assertEqual(report['status'], 'passed_local_candidate', report['issues'])
        self.assertTrue(report['readOnly'])
        self.assertFalse(report['operationalReleaseApproved'])
        self.assertFalse(report['hostedRoleLoginVerified'])
        self.assertEqual(await self.report(), report)
        # A direct nonowner catalog read must also work; no SET ROLE inside inspector.
        runtime = await asyncpg.connect(self.dsn)
        try:
            await fixture.role_setup(runtime, self.role)
            other = await candidate.inspect(runtime, self.role)
            self.assertEqual(other['status'], 'passed_local_candidate', other['issues'])
            self.assertEqual(other['catalogReader'], self.role)
            owner_gate = await installed.readiness.inspect(runtime, client_roles=())
            self.assertTrue(any(i['kind'] == 'backend_owner_access_not_proven' for i in owner_gate['issues']))
        finally:
            await runtime.close()
        self.assertEqual((await reconciliation.capture(self.conn))['catalog'], before)
        self.assertEqual(await preservation.fingerprints(self.conn, columns), rows)
        self.assertEqual(await preservation.ledger_fingerprints(self.conn), ledger)
        async with self.conn.transaction():
            with self.assertRaisesRegex(ValueError, 'outside a transaction'):
                await self.report()

    async def test_later_par_schema_is_held_without_inheriting_candidate_access(self):
        self.assertEqual((await self.report())['status'],'passed_local_candidate')
        await self.conn.execute((candidate.readiness.ROOT/'migrations/20261018_reviewed_inventory_pars.sql').read_bytes().decode())
        report=await self.report()
        self.assertEqual(report['status'],'held')
        self.assertTrue(any(i['kind']=='catalog_relations_drift' and i['object']=='purchasing.inventory_par_versions' for i in report['issues']))
        self.assertFalse(await self.conn.fetchval("SELECT has_table_privilege($1,'purchasing.inventory_par_versions','SELECT,INSERT,UPDATE,DELETE')",self.role))
        self.assertFalse(await self.conn.fetchval("SELECT has_function_privilege($1,'purchasing.guard_inventory_par()','EXECUTE')",self.role))

    async def test_permissions_missing_and_excess_table_function_and_sequence_access(self):
        await self.conn.execute('REVOKE INSERT ON purchasing.posting_batches FROM ' + self.role)
        await self.held('missing_object_privilege', 'purchasing.posting_batches')
        await self.conn.execute('GRANT INSERT ON purchasing.posting_batches TO ' + self.role)
        await self.conn.execute('GRANT DELETE ON purchasing.posting_batches TO ' + self.role)
        await self.held('excess_object_privilege', 'purchasing.posting_batches')
        await self.conn.execute('REVOKE DELETE ON purchasing.posting_batches FROM ' + self.role)
        await self.conn.execute('GRANT SELECT ON purchasing.posting_batches TO ' + self.role + ' WITH GRANT OPTION')
        await self.held('object_grant_option', 'purchasing.posting_batches')
        await self.conn.execute('REVOKE GRANT OPTION FOR SELECT ON purchasing.posting_batches FROM ' + self.role)
        await self.conn.execute('REVOKE EXECUTE ON FUNCTION purchasing.text_cells(jsonb) FROM ' + self.role)
        await self.held('missing_function_execute')
        await self.conn.execute('GRANT EXECUTE ON FUNCTION purchasing.text_cells(jsonb) TO ' + self.role)
        await self.conn.execute('GRANT EXECUTE ON FUNCTION purchasing.text_cells(jsonb) TO ' + self.role + ' WITH GRANT OPTION')
        await self.held('function_grant_option')
        await self.conn.execute('REVOKE GRANT OPTION FOR EXECUTE ON FUNCTION purchasing.text_cells(jsonb) FROM ' + self.role)
        await self.conn.execute('GRANT EXECUTE ON FUNCTION public.jmax_toast_start_sync(text,date,date) TO ' + self.role)
        await self.held('excess_function_execute')
        await self.conn.execute('REVOKE EXECUTE ON FUNCTION public.jmax_toast_start_sync(text,date,date) FROM ' + self.role)
        await self.conn.execute('CREATE SEQUENCE purchasing.invented_sequence')
        await self.conn.execute('GRANT USAGE ON SEQUENCE purchasing.invented_sequence TO ' + self.role)
        await self.held('excess_object_privilege', 'purchasing.invented_sequence')
        await self.conn.execute('DROP SEQUENCE purchasing.invented_sequence')
        self.assertEqual((await self.report())['status'], 'passed_local_candidate')

    async def test_permissions_column_acl_and_inherited_or_assumable_role_access(self):
        await self.conn.execute('GRANT SELECT (email) ON public.app_users TO ' + self.role)
        self.assertFalse(await self.conn.fetchval("SELECT has_table_privilege($1,'public.app_users','SELECT')", self.role))
        await self.held('excess_column_privilege', 'public.app_users.email')
        await self.conn.execute('GRANT SELECT (email) ON public.app_users TO ' + self.role + ' WITH GRANT OPTION')
        await self.held('column_grant_option', 'public.app_users.email')
        await self.conn.execute('REVOKE SELECT (email) ON public.app_users FROM ' + self.role)
        group = 'native_runtime_test_' + uuid4().hex
        await self.admin.execute('CREATE ROLE ' + group + ' NOLOGIN')
        self.roles.append(group)
        await self.conn.execute('GRANT SELECT ON public.app_users TO ' + group)
        await self.admin.execute('GRANT ' + group + ' TO ' + self.role + ' WITH INHERIT TRUE, SET TRUE')
        report = await self.held('unreviewed_role_membership', group)
        self.assertTrue(any(i['kind'] == 'excess_object_privilege' and i['object'] == 'public.app_users' for i in report['issues']))
        await self.admin.execute('GRANT ' + group + ' TO ' + self.role + ' WITH INHERIT FALSE, SET TRUE')
        self.assertFalse(await self.conn.fetchval("SELECT has_table_privilege($1,'public.app_users','SELECT')", self.role))
        await self.held('unreviewed_role_membership', group)
        await self.admin.execute('REVOKE ' + group + ' FROM ' + self.role)
        self.assertEqual((await self.report())['status'], 'passed_local_candidate')

    async def test_permissions_function_body_overload_definer_and_trigger_drift(self):
        signature = 'purchasing.text_cells(jsonb)'
        definition = await self.conn.fetchval('SELECT pg_get_functiondef($1::regprocedure)', signature)
        await self.conn.execute('CREATE OR REPLACE FUNCTION purchasing.text_cells(value jsonb) RETURNS boolean LANGUAGE sql AS $$ SELECT true $$')
        await self.held('catalog_functions_drift', signature)
        await self.conn.execute(definition)
        await self.conn.execute('ALTER FUNCTION ' + signature + ' SECURITY DEFINER')
        await self.held('catalog_functions_drift', signature)
        await self.conn.execute('ALTER FUNCTION ' + signature + ' SECURITY INVOKER')
        await self.conn.execute('CREATE FUNCTION purchasing.text_cells(integer) RETURNS integer LANGUAGE sql AS $$ SELECT $1 $$')
        await self.held('catalog_functions_drift', 'purchasing.text_cells(integer)')
        with self.assertRaisesRegex(ValueError, 'signature/body drift'):
            await fixture.apply(self.conn, self.role)
        await self.conn.execute('DROP FUNCTION purchasing.text_cells(integer)')
        trigger = await self.conn.fetchrow("SELECT tgname FROM pg_trigger WHERE tgrelid='purchasing.import_files'::regclass AND NOT tgisinternal ORDER BY tgname LIMIT 1")
        await self.conn.execute('ALTER TABLE purchasing.import_files DISABLE TRIGGER ' + trigger['tgname'])
        await self.held('catalog_relations_drift', 'purchasing.import_files')
        await self.conn.execute('ALTER TABLE purchasing.import_files ENABLE TRIGGER ' + trigger['tgname'])
        self.assertEqual((await self.report())['status'], 'passed_local_candidate')

    async def test_permissions_rls_policy_schema_and_object_ownership_drift(self):
        await self.conn.execute('ALTER TABLE public.store_state DISABLE ROW LEVEL SECURITY')
        await self.held('catalog_relations_drift', 'public.store_state')
        await self.conn.execute('ALTER TABLE public.store_state ENABLE ROW LEVEL SECURITY')
        await self.conn.execute('DROP POLICY runtime_candidate_update ON public.store_state')
        await self.held('missing_backend_policy')
        await self.conn.execute('CREATE POLICY runtime_candidate_update ON public.store_state FOR UPDATE TO ' + self.role + ' USING(true) WITH CHECK(true)')
        await self.conn.execute('CREATE POLICY invented_extra ON public.store_state AS RESTRICTIVE FOR SELECT TO ' + self.role + ' USING(false)')
        await self.held('unreviewed_applicable_policy')
        await self.conn.execute('DROP POLICY invented_extra ON public.store_state')
        await self.conn.execute('GRANT CREATE ON SCHEMA purchasing TO ' + self.role)
        await self.held('schema_ddl_access', 'purchasing')
        await self.conn.execute('REVOKE CREATE ON SCHEMA purchasing FROM ' + self.role)
        await self.conn.execute('GRANT USAGE ON SCHEMA purchasing TO ' + self.role + ' WITH GRANT OPTION')
        await self.held('schema_grant_option', 'purchasing')
        await self.conn.execute('REVOKE GRANT OPTION FOR USAGE ON SCHEMA purchasing FROM ' + self.role)
        owner = await self.conn.fetchval('SELECT current_user')
        await self.conn.execute('ALTER FUNCTION purchasing.text_cells(jsonb) OWNER TO ' + self.role)
        await self.held('runtime_function_ownership', 'purchasing.text_cells(jsonb)')
        await self.conn.execute('ALTER FUNCTION purchasing.text_cells(jsonb) OWNER TO ' + owner)
        await self.conn.execute('ALTER TABLE purchasing.posting_batches OWNER TO ' + self.role)
        await self.held('runtime_object_ownership', 'purchasing.posting_batches')
        await self.conn.execute('ALTER TABLE purchasing.posting_batches OWNER TO ' + owner)
        # Restoring ownership changes the former owner's ACL; do not assert a
        # clean privilege baseline until the disposable fixture is torn down.
        await self.admin.execute('ALTER ROLE ' + self.role + ' BYPASSRLS')
        await self.held('privileged_runtime_role', self.role)
        await self.admin.execute('ALTER ROLE ' + self.role + ' NOBYPASSRLS')
        missing = await candidate.inspect(self.conn, 'native_runtime_test_' + uuid4().hex)
        self.assertEqual(missing['status'], 'held')
        self.assertTrue(any(i['kind'] == 'missing_runtime_role' for i in missing['issues']))
