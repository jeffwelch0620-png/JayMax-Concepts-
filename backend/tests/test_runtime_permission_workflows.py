"""Selected native workflows under one nonowner candidate, invented local DBs only."""
import asyncio,os,unittest
from unittest.mock import patch
from uuid import UUID,uuid4
import asyncpg,httpx,db_pg,deployment_readiness as readiness
import runtime_role_fixture as permissions
import test_deployment_readiness as deployment
import test_hosted_native_install as installed
import test_order_commands as orders
import test_supplier_prices as prices
import test_supplier_contacts as contacts
import test_container_waste as waste
import test_prep_period_journal as analytics


class RuntimePhysicalTests(permissions.RuntimeRoleMixin,deployment.DeploymentReadinessTests):
    async def test_runtime_physical_history_corrections_closures_and_original_key_replay(self):
        self.assertTrue(self.permission_result['completeNativeObjectSet'])
        with patch.dict(os.environ,{name+'_ENABLED':'true' for name in readiness.FEATURES}):
            fixture=await self.rich_history()
            before=(await self.report(fixture['opening'],fixture['closing'])).json()
            self.assertEqual(before['actualFoodCost'],'21.00')
            self.assertEqual((await self.report(fixture['oldOpening'],fixture['oldClosing'])).json()['actualFoodCost'],'60.00')
            for file_id,source in fixture['sourceFiles']:
                self.assertEqual((await self.client.get('/api/pg/purchases/berts/files/'+file_id+'/source')).content,source)
            async with self.pool.acquire() as conn:
                self.assertFalse(await conn.fetchval("SELECT has_table_privilege(current_user,'actual_inventory.period_closures','DELETE')"))
                for sql,error in [("ALTER TABLE actual_inventory.count_snapshots ADD COLUMN forbidden text",asyncpg.InsufficientPrivilegeError),
                    ('DELETE FROM actual_inventory.period_closures',asyncpg.InsufficientPrivilegeError),
                    ("UPDATE purchasing.import_files SET captured_by='forbidden'",asyncpg.RaiseError),
                    ("UPDATE actual_inventory.count_snapshots SET counted_by='forbidden'",asyncpg.RaiseError)]:
                    with self.assertRaises(error):
                        async with conn.transaction():await conn.execute(sql)
                self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.period_closures'),5)
                self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.active_period_closures'),2)
            await self.pool.close()
            async def setup(conn):await permissions.role_setup(conn,self.runtime_role)
            self.pool=await asyncpg.create_pool(self.source,min_size=1,max_size=3,init=db_pg._init_connection,setup=setup)
            c=fixture['correction']['correction']
            body={**c['reviewed_plan']['review'],'expected_plan_hash':c['reviewed_plan']['planHash'],
                'expected_initial_batch_id':c['initial_batch_id'],'expected_correction_id':None}
            replay=await self.client.post('/api/pg/purchases/berts/documents/'+fixture['reissue']['id']+'/correct',json=body,
                headers={'Idempotency-Key':c['idempotency_key']})
            self.assertEqual(replay.status_code,200,replay.text)
            self.assertEqual(replay.json()['correctionId'],fixture['correction']['correctionId'])
            self.assertEqual((await self.report(fixture['opening'],fixture['closing'])).json(),before)


class RuntimeStaffTests(installed.NativeInstallTests):
    async def test_runtime_full_native_staff_counts_assignment_and_production(self):
        import hosted_committed_workflow as workflow,hosted_staff_review as counts,hosted_staff_production as production
        await self.run_install();fixture=await workflow.run(self.dsn)
        role='native_runtime_test_'+uuid4().hex
        await self.conn.execute('CREATE ROLE '+role+' NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT')
        async def cleanup():
            conn=await asyncpg.connect(os.environ['NATIVE_PURCHASE_TEST_DSN'])
            try:await conn.execute('DROP ROLE '+role)
            finally:await conn.close()
        self.addAsyncCleanup(cleanup)
        result=await permissions.apply(self.conn,role);self.assertTrue(result['completeNativeObjectSet'])
        async def setup(conn):await permissions.role_setup(conn,role)
        count=await counts.run(self.dsn,fixture['temporaryStore'],fixture['actualReportParams'],pool_setup=setup)
        self.assertTrue(count['freshPoolStaffAndReviewReplayVerified']);self.assertTrue(count['track1Unchanged'])
        prep=await production.run(self.dsn,fixture['temporaryStore'],fixture['actualReportParams'],pool_setup=setup)
        self.assertTrue(prep['freshPoolReplayAndPrivateStaffProjectionVerified']);self.assertTrue(prep['track1ReportAndAllFactsUnchanged'])
        async with self.conn.transaction():
            await self.conn.execute('SET LOCAL ROLE '+role)
            with self.assertRaises(asyncpg.InsufficientPrivilegeError):
                async with self.conn.transaction():await self.conn.execute('DELETE FROM prep_inventory.staff_production_decisions')
            with self.assertRaises(asyncpg.InsufficientPrivilegeError):
                async with self.conn.transaction():await self.conn.fetchval('SELECT count(*) FROM public.app_users')


class RuntimeOrderTests(permissions.RuntimeRoleMixin,orders.OrderCommandTests):
    async def test_runtime_order_independence_receiving_and_food_cost(self):
        await orders.OrderCommandTests.test_native_receiving_advances_order_version_and_preserves_purchase_cost(self)
        await orders.OrderCommandTests.test_order_editor_cannot_approve_even_after_another_editor_changes_content(self)


class RuntimePriceTests(permissions.RuntimeRoleMixin,prices.SupplierPriceTests):
    async def test_runtime_posting_and_reviewed_price_adoption_remain_separate(self):
        await prices.SupplierPriceTests.test_posting_is_independent_adoption_is_atomic_idempotent_and_store_scoped(self)


class RuntimeContactTests(permissions.RuntimeRoleMixin,contacts.SupplierContactTests):
    async def test_runtime_contact_parallel_retry_stale_edit_and_exact_replay(self):
        await contacts.SupplierContactTests.test_contact_parallel_retry_stale_edits_and_exact_replay(self)


class RuntimeWasteTests(permissions.RuntimeRoleMixin,waste.ContainerWasteTests):
    async def test_runtime_container_waste_correction_and_track1_separation(self):
        # The mixin installs the complete reviewed chain before selecting the role.
        await waste.ContainerWasteTests.test_review_corrections_waste_after_transfer_and_transfer_undo_restores_pair(self)


class RuntimeAnalyticsTests(permissions.RuntimeRoleMixin,analytics.PrepJournalTests):
    async def test_runtime_analytics_saved_periods_and_suffix_reopen(self):
        await analytics.PrepJournalTests.test_adjacent_snapshots_keep_partial_coverage_and_accounting_independent(self)
        # Reuse the adjacent snapshots to avoid duplicate fixed count times.
        state=await self.journal_state();closures=state['closures']
        original=[c['review_snapshot'] for c in closures]
        reopened=await self.reopen(closures[0])
        self.assertEqual(reopened['closure_ids'],[c['id'] for c in closures])
        after=await self.journal_state()
        self.assertEqual([c['review_snapshot'] for c in after['closures']],original)
