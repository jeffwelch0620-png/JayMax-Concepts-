"""Shared-state cutover on invented loopback databases; no hosted writes."""
import os
from unittest.mock import patch
import asyncpg
import httpx
import server
import purchase_api
import hosted_staff_production as accounting
import deployment_readiness as readiness
import runtime_role_fixture as permissions
from test_runtime_manager_workflows import MenuHistoryFixture
from test_hosted_native_install import NativeInstallTests


class SharedStateFixture(MenuHistoryFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""INSERT INTO adjustments(store_id,item_code,date,reason,qty,direction,ref,control_number)
                    VALUES('berts','test_food','2026-09-01','waste',123456789012345.000000000001,'remove','invented-adjustment','test_food')""")
                await conn.execute("""INSERT INTO reporting_periods(store_id,period_start,period_end,name,status,ref,dish_sales,item_counts)
                    VALUES('berts','2026-09-01','2026-09-07','Invented retained close','closed','invented-period','{"invented":2}','{"test_food":3}')""")
        except BaseException:
            await super().asyncTearDown()
            raise


class SharedStateTests(permissions.RuntimeRoleMixin,SharedStateFixture):
    async def retained_state(self):
        async with self.pool.acquire() as conn:
            return {table:purchase_api.serial([dict(r) for r in await conn.fetch('SELECT * FROM public.'+table+' ORDER BY id')]) for table in ('adjustments','reporting_periods')}

    async def test_shared_state_candidate_loads_labeled_history_without_accounting_drift(self):
        _,opening,closing=await self.pair()
        source,*_=await self.capture();self.assertEqual((await self.post(source['documents'][0])).status_code,200)
        report=(await self.report(opening,closing)).json()
        async with self.pool.acquire() as conn:before=await accounting.accounting_fingerprints(conn,'berts')
        history=await self.retained_state()
        with patch.dict(os.environ,{flag+'_ENABLED':'false' for flag in readiness.FEATURES}):
            result=await self.catalog.get('/api/state/berts')
        self.assertEqual(result.status_code,200,result.text)
        data=result.json();self.assertEqual(data['adjustments'][0]['id'],'invented-adjustment')
        self.assertEqual(data['adjustments'][0]['qty'],'123456789012345.000000000001')
        self.assertEqual(data['reportingPeriods'][0]['status'],'closed')
        self.assertEqual(data['legacyStateCapabilities'],{'inventoryRetired':True,'adjustmentsAvailable':False,'reportingPeriodsAvailable':False})
        self.assertTrue(all(r['archived'] and not r['operational'] for r in data['legacyStateBasis'].values()))
        self.assertEqual((await self.catalog.get('/api/state/rudds')).json()['adjustments'],[])
        self.assertEqual(await self.retained_state(),history)
        async with self.pool.acquire() as conn:
            self.assertEqual(await accounting.accounting_fingerprints(conn,'berts'),before)
            for table in ('adjustments','reporting_periods'):
                for verb in ('INSERT','UPDATE','DELETE'):
                    self.assertFalse(await conn.fetchval('SELECT has_table_privilege(current_user,$1,$2)','public.'+table,verb))
        self.assertEqual((await self.report(opening,closing)).json(),report)

    async def test_shared_state_owner_and_candidate_cannot_replace_history_or_bump_revision(self):
        history=await self.retained_state()
        for collection in ('adjustments','reportingPeriods'):
            result=await self.catalog.put('/api/state/berts/'+collection,json=[],headers={'If-Match':'0'})
            self.assertEqual(result.status_code,409,result.text)
        owner=await asyncpg.create_pool(os.environ['NATIVE_PURCHASE_TEST_DSN'].rsplit('/',1)[0]+'/'+self.db,
            init=server.db_pg._init_connection)
        try:
            with patch('server.db_pg._pool',owner),patch.dict(os.environ,{flag+'_ENABLED':'false' for flag in readiness.FEATURES}):
                for collection in ('adjustments','reportingPeriods'):
                    result=await self.catalog.put('/api/state/berts/'+collection,json=[],headers={'If-Match':'0'})
                    self.assertEqual(result.status_code,409,result.text)
                for method in (server._pg_replace_adjustments,server._pg_replace_reporting_periods):
                    with self.assertRaises(server.HTTPException) as held:await method('berts',[])
                    self.assertEqual(held.exception.status_code,409)
            async with owner.acquire() as conn:
                self.assertEqual(await conn.fetchval("SELECT count(*) FROM reporting_periods WHERE ref='invented-period'"),1)
                self.assertEqual(await conn.fetchval("SELECT coalesce((SELECT revision FROM store_state WHERE store_id='berts'),0)"),0)
        finally:await owner.close()
        self.assertEqual(await self.retained_state(),history)

    async def test_shared_state_area_and_sales_drafts_are_scoped_versioned_and_independent(self):
        _,opening,closing=await self.pair();report=(await self.report(opening,closing)).json()
        async with self.pool.acquire() as conn:before=await accounting.accounting_fingerprints(conn,'berts')
        history=await self.retained_state()
        revision=(await self.catalog.get('/api/state/berts')).json()['revision']
        area=await self.catalog.put('/api/state/berts/areas',json=['Invented cooler'],headers={'If-Match':str(revision)})
        self.assertEqual(area.status_code,200,area.text);self.assertEqual(area.json()['revision'],revision+1)
        draft={'periodStart':'2026-10-01','periodEnd':'2026-10-07','dishSales':{'invented':99},'itemCounts':{'test_food':1000000}}
        saved=await self.catalog.put('/api/state/berts/salesPeriod',json=draft,headers={'If-Match':str(revision+1)})
        self.assertEqual(saved.status_code,200,saved.text);self.assertEqual(saved.json()['revision'],revision+2)
        self.assertEqual((await self.catalog.put('/api/state/berts/areas',json=['Stale'],headers={'If-Match':str(revision+1)})).status_code,409)
        data=(await self.catalog.get('/api/state/berts')).json()
        self.assertEqual(data['areas'],['Invented cooler']);self.assertEqual(data['salesPeriod'],draft);self.assertEqual(data['revision'],revision+2)
        for role,locations in [('manager',['rudds']),('readonly',['berts']),('staff',['berts'])]:
            token=server._token({'id':'invented-scope','email':'scope@example.invalid','role':role,'locations':locations})
            self.assertEqual((await self.catalog.put('/api/state/berts/areas',json=['Forbidden'],headers={'Authorization':'Bearer '+token,'If-Match':str(revision+2)})).status_code,403)
        token=server._token({'id':'invented-scope','email':'scope@example.invalid','role':'manager','locations':['rudds']})
        self.assertEqual((await self.catalog.get('/api/state/berts',headers={'Authorization':'Bearer '+token})).status_code,403)
        self.assertEqual((await self.catalog.get('/api/state/berts',headers={'Authorization':''})).status_code,401)
        self.assertEqual(await self.retained_state(),history)
        async with self.pool.acquire() as conn:self.assertEqual(await accounting.accounting_fingerprints(conn,'berts'),before)
        self.assertEqual((await self.report(opening,closing)).json(),report)


class PreinstallSharedStateTests(NativeInstallTests):
    async def test_shared_state_public_only_compatibility_and_requested_cutover(self):
        await self.conn.execute("INSERT INTO stores(id,name) VALUES('berts','Invented Berts')")
        pool=await asyncpg.create_pool(self.dsn,init=server.db_pg._init_connection)
        token=server._token({'id':'invented-owner','email':'owner@example.invalid','role':'owner','locations':[]})
        try:
            with patch('server.USE_PG',True),patch('server.db_pg._pool',pool),patch.dict(os.environ,{flag+'_ENABLED':'false' for flag in readiness.FEATURES}):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://test',headers={'Authorization':'Bearer '+token}) as web:
                    adjustment=[{'id':'old','controlNumber':'preserve_food','date':'2026-09-01','reason':'waste','qty':7}]
                    period=[{'id':'old','periodStart':'2026-09-01','periodEnd':'2026-09-07','status':'closed'}]
                    for collection,body,version in [('adjustments',adjustment,0),('reportingPeriods',period,1)]:
                        result=await web.put('/api/state/berts/'+collection,json=body,headers={'If-Match':str(version)})
                        self.assertEqual(result.status_code,200,result.text)
                    data=(await web.get('/api/state/berts')).json()
                    self.assertEqual(data['revision'],2);self.assertTrue(data['legacyStateCapabilities']['adjustmentsAvailable'])
                    self.assertTrue(data['legacyStateCapabilities']['reportingPeriodsAvailable']);self.assertFalse(data['legacyStateCapabilities']['inventoryRetired'])
                    with patch.dict(os.environ,{'PURCHASE_IMPORT_ENABLED':'true'}):
                        for collection in ('adjustments','reportingPeriods'):
                            self.assertEqual((await web.put('/api/state/berts/'+collection,json=[],headers={'If-Match':'2'})).status_code,409)
                    with patch.dict(os.environ,{'PREP_BATCHES_ENABLED':'true'}):
                        status=(await web.get('/api/state/berts')).json()['legacyStateCapabilities']
                        self.assertFalse(status['adjustmentsAvailable']);self.assertTrue(status['reportingPeriodsAvailable'])
                        self.assertEqual((await web.put('/api/state/berts/adjustments',json=[],headers={'If-Match':'2'})).status_code,409)
                    self.assertEqual((await web.get('/api/state/berts')).json(),data)
        finally:await pool.close()
