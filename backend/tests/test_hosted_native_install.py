"""Atomic install/ledger and uncertain-commit cases on disposable PostgreSQL."""
import os
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlparse
from uuid import uuid4
import asyncpg
import deployment_readiness as readiness
import hosted_native_install as installer
import hosted_install_preservation as preservation
import managed_development as delivery
import schema_reconciliation as reconciliation


class FaultConnection:
    def __init__(self,conn,migration_failure=False,commit_ack_loss=False):
        self.conn=conn;self.migration_failure=migration_failure;self.commit_ack_loss=commit_ack_loss
    def __getattr__(self,name):return getattr(self.conn,name)
    async def execute(self,query,*args):
        if self.migration_failure and 'CREATE SCHEMA actual_inventory' in query:
            raise RuntimeError('Invented mid-chain failure')
        return await self.conn.execute(query,*args)
    def transaction(self,*args,**kwargs):
        transaction=self.conn.transaction(*args,**kwargs)
        if self.conn.is_in_transaction() or not self.commit_ack_loss:return transaction
        class LostAcknowledgement:
            async def start(self):await transaction.start()
            async def rollback(self):await transaction.rollback()
            async def commit(self):
                await transaction.commit()
                raise ConnectionError('Invented lost COMMIT acknowledgement')
        return LostAcknowledgement()


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable local PostgreSQL required')
class NativeInstallTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        dsn=os.environ['NATIVE_PURCHASE_TEST_DSN'];uri=urlparse(dsn)
        if uri.hostname!='127.0.0.1' or not uri.path.startswith('/native_purchase_test_') or uri.query or uri.fragment:
            raise RuntimeError('Local installation test requires disposable loopback control')
        self.admin=await asyncpg.connect(dsn);self.name='native_purchase_test_'+uuid4().hex
        await self.admin.execute('CREATE DATABASE '+self.name)
        self.dsn=dsn.rsplit('/',1)[0]+'/'+self.name;self.conn=await asyncpg.connect(self.dsn)
        await self.conn.execute((readiness.ROOT/'supabase/schema.sql').read_bytes().decode())
        await self.conn.execute('''CREATE SCHEMA supabase_migrations;
            CREATE TABLE supabase_migrations.schema_migrations(version text PRIMARY KEY,name text,statements text[],created_by text,idempotency_key text,rollback text[]);
            INSERT INTO supabase_migrations.schema_migrations(version,name,statements) VALUES('20260929135736','invented_local_history',ARRAY['SELECT 1;']);
            INSERT INTO public.stores(id,name) VALUES('preserve_test','Invented local preservation test');
            INSERT INTO public.vendors(id,name) VALUES('pfg','PFG'),('us_foods','US Foods');
            INSERT INTO public.items(code,name,base_unit) VALUES('preserve_food','Invented food','lb');
            INSERT INTO public.store_items(store_id,item_code,count_unit,base_per_count_unit) VALUES('preserve_test','preserve_food','case',20);''')
        self.catalog=(await reconciliation.capture(self.conn))['catalog']
        self.columns=await preservation.original_columns(self.conn)
        self.rows=await preservation.fingerprints(self.conn,self.columns)
        self.ledger=await preservation.ledger_fingerprints(self.conn)
        self.temp=tempfile.TemporaryDirectory();self.bundle=Path(self.temp.name)/'delivery'
        delivery.prepare_bundle(self.bundle,'20261008190000')
    async def asyncTearDown(self):
        await self.conn.close();await self.admin.execute('DROP DATABASE '+self.name);await self.admin.close();self.temp.cleanup()
    async def run_install(self,conn=None,catalog=None,rows=None,ledger=None):
        return await installer.apply(conn or self.conn,self.bundle,catalog if catalog is not None else self.catalog,
            rows if rows is not None else self.rows,ledger if ledger is not None else self.ledger,client_roles=())

    async def test_commit_is_visible_to_new_connection_and_original_values_and_history_survive(self):
        report,columns=await self.run_install()
        self.assertTrue(report['sqlCommitted']);self.assertEqual(len(report['completedMigrations']),29)
        self.assertEqual(await self.conn.fetchval('SELECT count(*) FROM supabase_migrations.schema_migrations'),30)
        other=await asyncpg.connect(self.dsn)
        try:
            check=await installer.verify_install(other,report['delivery'],self.ledger,columns,self.rows,client_roles=())
            self.assertTrue(check['originalApplicationValuesPreserved'])
            self.assertTrue(check['appliedSqlBodyHashesVerified'])
        finally:await other.close()
        with self.assertRaises(installer.InstallFailure) as error:await self.run_install()
        self.assertFalse(error.exception.report['commitAttempted'])

    async def test_committed_concurrent_workflow_survives_pool_restart_and_original_stores_are_untouched(self):
        import hosted_committed_workflow as workflow
        await self.run_install()
        result=await workflow.run(self.dsn)
        self.assertEqual(result['actualFoodCost'],'55.00')
        self.assertTrue(result['concurrentPurchaseAndPrepRetryVerified'])
        self.assertTrue(all(result['independentReplay'].values()))
        self.assertTrue(result['track1UnchangedAfterPrepWasteAndSalesContext'])
        self.assertEqual(await self.conn.fetchval("SELECT name FROM public.stores WHERE id='preserve_test'"),'Invented local preservation test')

    async def test_failed_mid_chain_rolls_back_ddl_and_all_new_history(self):
        with self.assertRaises(installer.InstallFailure) as error:
            await self.run_install(FaultConnection(self.conn,migration_failure=True))
        self.assertFalse(error.exception.report['sqlCommitted'])
        self.assertTrue(error.exception.report['failedInstallRollbackCompleted'])
        self.assertFalse(await self.conn.fetchval("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='purchasing')"))
        self.assertEqual(await preservation.ledger_fingerprints(self.conn),self.ledger)
        self.assertEqual(await preservation.fingerprints(self.conn,self.columns),self.rows)

    async def test_actual_staff_routes_preserve_track1_and_require_independent_exact_count_review(self):
        import hosted_committed_workflow as workflow
        import hosted_staff_review as staff
        await self.run_install()
        fixture=await workflow.run(self.dsn)
        result=await staff.run(self.dsn,fixture['temporaryStore'],fixture['actualReportParams'])
        self.assertTrue(result['track1Unchanged'])
        self.assertTrue(result['independentAuthorReviewHeld'])
        self.assertEqual(result['actualFoodCost'],'55.00')
        self.assertEqual((result['submissions'],result['decisions']),(2,1))
        exclusion={('public','stores'):('id',fixture['temporaryStore']),
            ('public','items'):('code',fixture['inventedItemCode']),
            ('public','store_items'):('store_id',fixture['temporaryStore']),
            ('public','store_state'):('store_id',fixture['temporaryStore']),
            ('public','activity_log'):('user_id',result['activityActorIds'])}
        after=await preservation.fingerprints(self.conn,self.columns,exclude_synthetic=exclusion)
        self.assertEqual([name for name in self.rows if after[name]!=self.rows[name]],[])

    async def test_lost_commit_acknowledgement_is_unknown_until_independently_reconciled(self):
        with self.assertRaises(installer.InstallFailure) as error:
            await self.run_install(FaultConnection(self.conn,commit_ack_loss=True))
        report=error.exception.report
        self.assertEqual(report['status'],'commit_outcome_unknown');self.assertIsNone(report['sqlCommitted'])
        self.assertEqual(report['historicalLedgerFingerprints'],self.ledger)
        self.assertEqual(report['originalRows'],self.rows)
        self.assertEqual({(r['schema'],r['table']):r['columns'] for r in report['originalColumns']},self.columns)
        self.assertNotIn('failedInstallRollbackCompleted',report)
        other=await asyncpg.connect(self.dsn)
        try:
            result=await installer.verify_install(other,report['delivery'],self.ledger,self.columns,self.rows,client_roles=())
            self.assertTrue(result['historicalLedgerRowsPreserved'])
        finally:await other.close()

    async def test_stale_rows_or_historical_sql_hold_before_native_ddl(self):
        await self.conn.execute("UPDATE public.items SET name='Changed existing record'")
        with self.assertRaises(installer.InstallFailure):await self.run_install()
        await self.conn.execute("UPDATE public.items SET name='Invented food'")
        await self.conn.execute("UPDATE supabase_migrations.schema_migrations SET statements=ARRAY['SELECT 2;']")
        with self.assertRaises(installer.InstallFailure):await self.run_install()
        self.assertFalse(await self.conn.fetchval("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='purchasing')"))

    async def test_delivery_version_collision_and_unreviewed_catalog_hold(self):
        await self.conn.execute("INSERT INTO supabase_migrations.schema_migrations(version,name) VALUES('20261008190000','collision')")
        ledger=await preservation.ledger_fingerprints(self.conn)
        with self.assertRaises(installer.InstallFailure):await self.run_install(ledger=ledger)
        await self.conn.execute("DELETE FROM supabase_migrations.schema_migrations WHERE version='20261008190000'")
        await self.conn.execute('ALTER TABLE public.items ADD COLUMN unreviewed text')
        with self.assertRaises(installer.InstallFailure):await self.run_install()
        self.assertFalse(await self.conn.fetchval("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='purchasing')"))

    async def test_unreviewed_mandatory_ledger_field_and_edited_applied_body_hold(self):
        await self.conn.execute("ALTER TABLE supabase_migrations.schema_migrations ADD COLUMN new_mandatory text NOT NULL DEFAULT 'local'")
        await self.conn.execute('ALTER TABLE supabase_migrations.schema_migrations ALTER COLUMN new_mandatory DROP DEFAULT')
        with self.assertRaises(installer.InstallFailure):await self.run_install()
        await self.conn.execute('ALTER TABLE supabase_migrations.schema_migrations DROP COLUMN new_mandatory')
        report,columns=await self.run_install()
        await self.conn.execute("UPDATE supabase_migrations.schema_migrations SET statements=ARRAY['SELECT 999;'] WHERE version=$1",report['delivery'][0]['deliveryVersion'])
        with self.assertRaises(AssertionError):
            await installer.verify_install(self.conn,report['delivery'],self.ledger,columns,self.rows,client_roles=())
