"""Hosted-readiness probes run only against invented, disposable PostgreSQL."""
import os
import unittest
from uuid import uuid4
from unittest.mock import patch
from pathlib import Path
import asyncpg
import deployment_readiness as readiness
import native_backup as backup
import test_native_backup as fixtures


class ReadinessConfigurationTests(unittest.TestCase):
    def test_invalid_connection_is_held_without_echoing_connection_material(self):
        for dsn in ('','postgresql://owner:[YOUR-PASSWORD]@your-host/postgres','postgresql://owner:private-password@[bad-address]/db','postgresql://owner:private-password@host:bad/db'):
            self.assertFalse(readiness.connection_configured(dsn))
        self.assertTrue(readiness.connection_configured('postgresql://owner:private-password@host:5432/postgres'))
    def config(self,enabled=False):
        backend={'USE_PG':'true','DATABASE_URL':'postgresql://hidden:private-password@example.invalid/postgres'}
        frontend={'REACT_APP_USE_PG':'true'}
        for name,(browser,_) in readiness.FEATURES.items():
            backend[name+'_ENABLED']='true' if enabled else 'false'
            frontend['REACT_APP_'+browser]='true' if enabled else 'false'
        return backend,frontend

    def test_pg_modes_must_be_explicit_and_match_without_secret_output(self):
        backend,frontend=self.config()
        self.assertEqual(readiness.configuration(backend,frontend)['status'],'passed')
        self.assertTrue(readiness.configuration(backend,frontend)['allNativeFeaturesHeld'])
        for data,key in [(backend,'USE_PG'),(frontend,'REACT_APP_USE_PG')]:
            old=data.pop(key);self.assertEqual(readiness.configuration(backend,frontend)['status'],'held');data[key]=old
        backend['USE_PG']='false'
        report=readiness.configuration(backend,frontend)
        self.assertEqual(report['status'],'held');self.assertNotIn('private-password',str(report))

    def test_pair_mismatch_invalid_boolean_and_missing_prerequisite_are_held(self):
        backend,frontend=self.config(True)
        self.assertEqual(readiness.configuration(backend,frontend)['status'],'passed')
        backend['PREP_EXECUTION_ENABLED']='false';frontend['REACT_APP_PREP_EXECUTION']='false'
        self.assertIn('Requires PREP_EXECUTION',str(readiness.configuration(backend,frontend)['problems']))
        backend,frontend=self.config();frontend['REACT_APP_PREP_BATCHES']='true'
        self.assertIn('flags differ',str(readiness.configuration(backend,frontend)['problems']))
        backend['PREP_BATCHES_ENABLED']='yes';self.assertIn('explicit true/false',str(readiness.configuration(backend,frontend)['problems']))
        backend['PREP_BATCHES_ENABLED']=' true ';self.assertIn('explicit true/false',str(readiness.configuration(backend,frontend)['problems']))

    def test_plan_covers_native_files_once_and_excludes_already_applied_recurring_file(self):
        expected={p.name for p in (readiness.ROOT/'migrations').glob('*.sql')} - {'20260930_recurring_prep_items.sql'}
        plan=readiness.migration_plan();self.assertEqual({e['file'] for e in plan['migrations']},expected)
        self.assertEqual(len(readiness.MIGRATIONS),len(expected));self.assertEqual(len(set(readiness.MIGRATIONS)),len(expected))
        self.assertEqual(readiness.MIGRATIONS[-1],'20261007_native_private_access.sql')
        self.assertEqual(readiness.MIGRATIONS[-2],'20261008_container_waste_corrections.sql')
        for e in plan['migrations']:
            self.assertRegex(e['sha256'],r'^[a-f0-9]{64}$')
            for name,table in e['triggers']:self.assertNotIn('%',table)


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PostgreSQL required')
class DeploymentReadinessTests(fixtures.NativeBackupTests):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        # Existing legacy prep is carried through cutover; native guards reject later writes.
        await self.seed_excluded_prep()
        self.client_role='native_purchase_test_client_'+uuid4().hex
        self.group_role='native_purchase_test_group_'+uuid4().hex
        self.migrations=[e for e in readiness.MIGRATIONS if e not in (
            '20261004_native_purchase_import.sql','20261004_actual_inventory_counts.sql','20261004_actual_inventory_corrections.sql',
            '20261004_actual_inventory_scope_bridges.sql','20261004_posted_invoice_corrections.sql','20261007_native_private_access.sql')]
        await self.admin.execute('CREATE ROLE "'+self.client_role+'" NOLOGIN')
        await self.admin.execute('CREATE ROLE "'+self.group_role+'" NOLOGIN')
        await self.admin.execute('GRANT "'+self.group_role+'" TO "'+self.client_role+'"')
        async with self.pool.acquire() as conn:
            for name in self.migrations:await conn.execute((readiness.ROOT/'migrations'/name).read_text())
            with self.assertRaises(asyncpg.RaiseError):
                await conn.execute("INSERT INTO public.prep_logs(store_id,kind,name,produced,total_cost) VALUES('berts','batch','Rejected late legacy prep',1,1)")
            await conn.execute("INSERT INTO store_state(store_id,revision) VALUES('berts',0),('rudds',0) ON CONFLICT DO NOTHING")

    async def asyncTearDown(self):
        await super().asyncTearDown()
        admin=await asyncpg.connect(os.environ['NATIVE_PURCHASE_TEST_DSN'])
        try:
            await admin.execute('DROP ROLE "'+self.client_role+'"')
            await admin.execute('DROP ROLE "'+self.group_role+'"')
        finally:await admin.close()

    async def probe(self):
        async with self.pool.acquire() as conn:return await readiness.inspect(conn,(self.client_role,),('berts','rudds'))

    async def test_readiness_detects_function_exposure_then_hardens_full_chain_and_restores(self):
        # RLS alone never proves that PUBLIC cannot execute security-definer RPCs.
        initial=await self.probe()
        self.assertEqual(initial['status'],'held')
        self.assertTrue(any(i['kind']=='client_function_execute' and i['object'].startswith('public.jmax_toast') for i in initial['issues']))
        async with self.pool.acquire() as conn:
            await conn.execute((readiness.ROOT/'migrations/20261007_native_private_access.sql').read_text())
        report=await self.probe();self.assertEqual(report['status'],'passed',report['issues'])
        self.assertTrue(report['readOnly']);self.assertFalse(report['operationalReleaseApproved'])
        self.assertEqual(len(report['migrations']),29)
        # The inspector itself cannot write, and captures no operational row data.
        async with self.pool.acquire() as conn:
            before=await conn.fetchval('SELECT count(*) FROM purchasing.posting_batches')
        self.assertEqual(await self.probe(),report)
        async with self.pool.acquire() as conn:self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.posting_batches'),before)
        await backup.create_backup(self.source,fixtures.PG_DUMP,self.directory)
        target=await self.target();proof=await backup.verify_restore(target,self.directory)
        self.assertEqual(proof['status'],'verified')
        restored=await asyncpg.connect(target)
        try:self.assertEqual(await readiness.inspect(restored,(self.client_role,),('berts','rudds')),report)
        finally:await restored.close()

    async def test_readiness_catches_inherited_access_missing_roles_disabled_guards_and_later_ddl(self):
        async with self.pool.acquire() as conn:
            await conn.execute((readiness.ROOT/'migrations/20261007_native_private_access.sql').read_text())
            await conn.execute('GRANT USAGE ON SCHEMA purchasing TO "'+self.group_role+'"')
            await conn.execute('GRANT SELECT ON purchasing.posting_batches TO "'+self.group_role+'"')
            await conn.execute('ALTER TABLE prep_inventory.batch_events DISABLE TRIGGER staff_batch_acceptance_seal')
        report=await self.probe();self.assertEqual(report['status'],'held')
        self.assertTrue({'client_private_schema_access','client_private_object_access','disabled_trigger'}<={i['kind'] for i in report['issues']})
        async with self.pool.acquire() as conn:
            await conn.execute('REVOKE USAGE ON SCHEMA purchasing FROM "'+self.group_role+'"')
            await conn.execute('REVOKE SELECT ON purchasing.posting_batches FROM "'+self.group_role+'"')
            await conn.execute('ALTER TABLE prep_inventory.batch_events ENABLE TRIGGER staff_batch_acceptance_seal')
            await conn.execute('CREATE FUNCTION purchasing.invented_late_function() RETURNS integer LANGUAGE sql AS $$ SELECT 1 $$')
        report=await self.probe()
        self.assertTrue(any(i.get('object')=='purchasing.invented_late_function' for i in report['issues']))
        async with self.pool.acquire() as conn:
            await conn.execute((readiness.ROOT/'migrations/20261007_native_private_access.sql').read_text())
            await conn.execute('DROP FUNCTION purchasing.invented_late_function()')
            report=await readiness.inspect(conn,('missing_readiness_client',),('berts','rudds'))
        self.assertTrue(any(i['kind']=='client_role_not_checked' for i in report['issues']))
        with patch.dict(readiness.COLUMN_MARKERS,{'public.store_items':('invented_missing_column',)}):
            report=await self.probe()
        self.assertTrue(any(i['kind']=='partial_schema_column' for i in report['issues']))

    async def test_reconciled_waste_helper_denies_clients_and_nonowner_backend_is_held(self):
        async with self.pool.acquire() as conn:
            await conn.execute((readiness.ROOT/'migrations/20261007_native_private_access.sql').read_text())
            function='prep_inventory.can_reverse_container_waste(uuid,uuid)'
            self.assertFalse(await conn.fetchval('SELECT prosecdef FROM pg_proc WHERE oid=to_regprocedure($1)',function))
            self.assertFalse(await conn.fetchval("SELECT has_function_privilege($1,$2,'EXECUTE')",self.client_role,function))
            self.assertEqual((await self.probe())['status'],'passed')
            # USAGE alone cannot expose tables or an invoker function. Each failing
            # client statement runs in its own rolled-back local transaction.
            for sql,args in [('SELECT count(*) FROM prep_inventory.container_commands',()),
                             ('SELECT prep_inventory.can_reverse_container_waste($1,$2)',(uuid4(),uuid4()))]:
                with self.assertRaises(asyncpg.InsufficientPrivilegeError):
                    async with conn.transaction():
                        await conn.execute('GRANT USAGE ON SCHEMA prep_inventory TO "'+self.client_role+'"')
                        await conn.execute('SET LOCAL ROLE "'+self.client_role+'"')
                        await conn.fetchval(sql,*args)
            # The inspector must not mistake schema visibility for a usable
            # ordinary backend role. This is a hold check, not a grants design.
            for schema in readiness.PRIVATE:
                await conn.execute('GRANT USAGE ON SCHEMA '+schema+' TO "'+self.group_role+'"')
            try:
                await conn.execute('SET ROLE "'+self.group_role+'"')
                report=await readiness.inspect(conn,(),())
                self.assertEqual(report['status'],'held')
                self.assertTrue(any(i['kind']=='backend_owner_access_not_proven' for i in report['issues']))
            finally:
                await conn.execute('RESET ROLE')
                for schema in readiness.PRIVATE:
                    await conn.execute('REVOKE USAGE ON SCHEMA '+schema+' FROM "'+self.group_role+'"')
            self.assertEqual((await self.probe())['status'],'passed')
