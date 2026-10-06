"""Track 1 integration checks against disposable PostgreSQL with synthetic facts."""
import asyncio
import os
import unittest
from uuid import UUID,uuid4
from unittest.mock import patch

import asyncpg
import httpx
from fastapi import FastAPI,HTTPException

import test_native_purchases as native
import actual_inventory_api as actual
import purchase_api as purchases

class ConfigurationTests(unittest.TestCase):
    def test_actual_inventory_requires_postgres_and_native_purchases(self):
        for settings,expected in [({'USE_PG':'true','PURCHASE_IMPORT_ENABLED':'true','ACTUAL_INVENTORY_ENABLED':'true'},True),
            ({'USE_PG':'false','PURCHASE_IMPORT_ENABLED':'true','ACTUAL_INVENTORY_ENABLED':'true'},False),
            ({'USE_PG':'true','PURCHASE_IMPORT_ENABLED':'false','ACTUAL_INVENTORY_ENABLED':'true'},False),
            ({'USE_PG':'true','PURCHASE_IMPORT_ENABLED':'true','ACTUAL_INVENTORY_ENABLED':'false'},False)]:
            with patch.dict(os.environ,settings):self.assertEqual(actual.enabled(),expected)


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PG DSN required')
class ActualInventoryTests(unittest.IsolatedAsyncioTestCase):
    capture=native.PurchaseIntegrationTests.capture
    body=native.PurchaseIntegrationTests.body
    post=native.PurchaseIntegrationTests.post

    async def asyncSetUp(self):
        await native.PurchaseIntegrationTests.asyncSetUp(self)
        self.actual_flag=patch.dict(os.environ,{'ACTUAL_INVENTORY_ENABLED':'true'});self.actual_flag.start()
        async with self.pool.acquire() as conn:
            await conn.execute((native.ROOT/'migrations/20261004_actual_inventory_counts.sql').read_text())
            if getattr(self,'apply_corrections',True):
                await conn.execute((native.ROOT/'migrations/20261004_actual_inventory_corrections.sql').read_text())
                await conn.execute((native.ROOT/'migrations/20261004_actual_inventory_scope_bridges.sql').read_text())
            await conn.execute("INSERT INTO items(code,name,base_unit,item_type) VALUES('prep_sauce','Prepared Sauce','each','prep')")
            await conn.execute("INSERT INTO store_items(store_id,item_code,count_unit,base_per_count_unit,sales_tracked) VALUES('berts','prep_sauce','each',1,false)")
            await conn.execute("UPDATE store_items SET sales_tracked=false WHERE item_code='test_food'")
        await self.client.aclose()
        def check(store):
            if store not in ('berts','rudds'):raise HTTPException(404,'Unknown store')
        def actor(request,store,write):
            if request.headers.get('authorization')!='Bearer synthetic-manager':raise HTTPException(401,'Authentication required')
            return 'synthetic-manager'
        app=FastAPI()
        app.include_router(purchases.create_router(lambda:self.pool,check,actor))
        app.include_router(actual.create_router(lambda:self.pool,check,actor))
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers={'Authorization':'Bearer synthetic-manager'})

    async def asyncTearDown(self):
        self.actual_flag.stop();await native.PurchaseIntegrationTests.asyncTearDown(self)

    async def scope(self,codes=('test_food',),key=None,base='lb'):
        body={'scope_kind':'purchased_items_only','valuation_method':'explicit_count_values','note':'Synthetic full purchased-food scope',
              'items':[{'item_code':c,'base_unit':base,'location_notes':'All raw inventory storage locations'} for c in codes]}
        result=await self.client.post('/api/pg/actual-inventory/berts/scope',json=body,headers={'Idempotency-Key':key or str(uuid4())})
        return result,body

    async def count(self,scope,date,quantity='2',value='60',timing='before_receipts',confirmed=True,key=None,**extra):
        body={'scope_id':scope['header']['id'],'count_date':date,'timing':timing,'note':'Synthetic physical count',
              'lines':[{'item_code':i['item_code'],'counted_quantity':quantity,'counted_unit':'case',
                        'base_units_per_counted_unit':'20' if quantity is not None else None,'inventory_value':value,
                        'confirmed':confirmed,'note':'Verified measured quantity and explicit value'} for i in scope['items']],**extra}
        result=await self.client.post('/api/pg/actual-inventory/berts/counts',json=body,headers={'Idempotency-Key':key or str(uuid4())})
        return result,body

    async def report(self,opening,closing,store='berts'):
        return await self.client.get(f'/api/pg/actual-inventory/{store}/report',params={'opening':opening['header']['id'],'closing':closing['header']['id']})

    async def close(self,report,key=None,**extra):
        body={'opening_snapshot_id':report['openingSnapshotId'],'closing_snapshot_id':report['closingSnapshotId'],
              'expected_report_hash':report['reportHash'],'purchases_reviewed':True,'counts_reviewed':True,
              'supersedes_closure_id':report.get('supersedesClosureId'),'opening_bridge_id':report.get('openingBridgeId'),**extra}
        return await self.client.post('/api/pg/actual-inventory/berts/close',json=body,headers={'Idempotency-Key':key or str(uuid4())})

    async def pair(self,opening='2026-10-01',closing='2026-10-08'):
        r,_=await self.scope();self.assertEqual(r.status_code,200,r.text);scope=r.json()
        a,_=await self.count(scope,opening);b,_=await self.count(scope,closing,quantity='1.5',value='45')
        self.assertEqual(a.status_code,200,a.text);self.assertEqual(b.status_code,200,b.text)
        return scope,a.json(),b.json()

    async def purchase(self,received='2026-10-04',**patches):
        file,*_=await self.capture();doc=file['documents'][0];body=self.body(doc,**patches);body['received_date']=received
        r=await self.post(doc,body);return r,doc

    async def test_explicit_value_usage_math_ignores_sales_flag_and_prep(self):
        _,a,b=await self.pair();r,_=await self.purchase();self.assertEqual(r.status_code,200,r.text)
        report=(await self.report(a,b)).json();self.assertEqual(report['status'],'complete',report)
        row=report['rows'][0];self.assertEqual(row['actualUsage'],'50.0');self.assertEqual(row['actualFoodCost'],'55.00')
        self.assertEqual(report['actualFoodCost'],'55.00');self.assertEqual(report['netPurchaseCost'],'40.00')
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE items SET name='Changed',portion_size=99 WHERE code='test_food'")
            await conn.execute("UPDATE store_items SET current_stock=999,par=888,sales_tracked=true WHERE item_code='test_food'")
            await conn.execute("UPDATE store_state SET sales_period='{\"dishSales\":{\"fake\":999}}'::jsonb")
            await conn.execute("INSERT INTO vendor_items(vendor_id,vendor_sku,item_code,purchase_unit,price) VALUES('pfg','synthetic-PRICE','test_food','case',9999)")
            await conn.execute("INSERT INTO prep_logs(store_id,kind,name,produced,total_cost) VALUES('berts','batch','Synthetic batch',999,123)")
        after=(await self.report(a,b)).json();self.assertEqual(after,report)

    async def test_prepared_items_excluded_and_fixed_unit_conflict_rolls_back(self):
        setup=(await self.client.get('/api/pg/actual-inventory/berts/setup')).json()
        self.assertNotIn('prep_sauce',[i['code'] for i in setup['items']])
        r,_=await self.scope(('prep_sauce',));self.assertEqual(r.status_code,422)
        self.assertEqual((await self.scope())[0].status_code,200)
        r,_=await self.scope(base='each');self.assertEqual(r.status_code,409)
        async with self.pool.acquire() as conn:self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.scopes'),1)

    async def test_missing_counts_values_and_confirmations_do_not_become_zero(self):
        r,_=await self.scope();scope=r.json();a,_=await self.count(scope,'2026-10-01')
        for quantity,value in ((None,None),('1',None)):
            b,_=await self.count(scope,'2026-10-08',quantity=quantity,value=value,confirmed=False)
            self.assertEqual(b.status_code,200,b.text)
            report=(await self.report(a.json(),b.json())).json()
            self.assertEqual(report['status'],'incomplete');self.assertIsNone(report['actualFoodCost'])
            self.assertIsNone(report['rows'][0]['actualUsage'])
            self.assertEqual((await self.close(report)).status_code,409)
        b,_=await self.count(scope,'2026-10-08',quantity='0',value='0')
        report=(await self.report(a.json(),b.json())).json()
        self.assertEqual(report['status'],'complete');self.assertEqual(report['rows'][0]['closingQuantity'],'0')

    async def test_same_day_receipt_boundaries_and_adjacent_periods(self):
        r,_=await self.scope();scope=r.json()
        a,_=await self.count(scope,'2026-10-04',timing='before_receipts')
        b,_=await self.count(scope,'2026-10-04',timing='after_receipts',quantity='3',value='90')
        c,_=await self.count(scope,'2026-10-08',timing='before_receipts',quantity='2',value='60')
        r,_=await self.purchase();self.assertEqual(r.status_code,200)
        first=(await self.report(a.json(),b.json())).json();second=(await self.report(b.json(),c.json())).json()
        self.assertEqual(first['netPurchaseCost'],'40.00');self.assertEqual(second['netPurchaseCost'],'0')
        self.assertEqual((await self.close(first)).status_code,200)
        self.assertEqual((await self.close(second)).status_code,200)

    async def test_closed_report_retry_snapshot_and_late_purchase_guard(self):
        scope,a,b=await self.pair();self.assertEqual((await self.purchase())[0].status_code,200)
        report=(await self.report(a,b)).json();key=str(uuid4())
        x,y=await asyncio.gather(self.close(report,key),self.close(report,key))
        self.assertEqual(x.status_code,200,x.text);self.assertEqual(y.status_code,200,y.text)
        self.assertEqual(x.json()['closure']['id'],y.json()['closure']['id'])
        self.assertEqual(x.json()['closure']['report_snapshot'],report)
        self.assertEqual((await self.purchase())[0].status_code,409)
        r,_=await self.count(scope,'2026-10-08',corrects_snapshot_id=b['header']['id'])
        self.assertEqual(r.status_code,409)
        async with self.pool.acquire() as conn:
            for table in ('count_lines','count_snapshots','period_closures'):
                with self.assertRaises(asyncpg.RaiseError):await conn.execute(f'DELETE FROM actual_inventory.{table}')

    async def test_preview_hash_requires_refresh_after_new_purchase(self):
        _,a,b=await self.pair();old=(await self.report(a,b)).json()
        self.assertEqual((await self.purchase())[0].status_code,200)
        self.assertEqual((await self.close(old)).status_code,409)
        new=(await self.report(a,b)).json();self.assertNotEqual(old['reportHash'],new['reportHash'])
        self.assertEqual((await self.close(new)).status_code,200)

    async def test_overlap_continuity_and_scope_mismatch(self):
        scope,a,b=await self.pair();report=(await self.report(a,b)).json();self.assertEqual((await self.close(report)).status_code,200)
        c,_=await self.count(scope,'2026-10-15',quantity='1',value='30')
        wrong,_=await self.count(scope,'2026-10-08',quantity='1.5',value='45')
        wrong_report=(await self.report(wrong.json(),c.json())).json()
        self.assertEqual((await self.close(wrong_report)).status_code,409)
        right=(await self.report(b,c.json())).json();self.assertEqual((await self.close(right)).status_code,200)
        gap_open,_=await self.count(scope,'2026-10-17',quantity='1',value='30')
        gap_close,_=await self.count(scope,'2026-10-22',quantity='0.5',value='15')
        gap=(await self.report(gap_open.json(),gap_close.json())).json()
        self.assertEqual((await self.close(gap)).status_code,409)
        overlap=(await self.report(a,c.json())).json();self.assertEqual((await self.close(overlap)).status_code,409)
        newer,_=await self.scope(('test_food','other_food'));d,_=await self.count(newer.json(),'2026-10-22')
        self.assertEqual((await self.report(c.json(),d.json())).status_code,409)

    async def test_unscoped_food_purchase_blocks_total_and_closure(self):
        _,a,b=await self.pair();r,_=await self.purchase(item_code='other_food');self.assertEqual(r.status_code,200)
        report=(await self.report(a,b)).json();self.assertEqual(report['status'],'incomplete')
        self.assertIsNone(report['actualFoodCost']);self.assertEqual(report['netPurchaseCost'],'40.00')
        self.assertTrue(any('outside' in e for e in report['errors']));self.assertEqual((await self.close(report)).status_code,409)

    async def test_count_request_replay_and_changed_payload_conflict(self):
        r,_=await self.scope();scope=r.json();key=str(uuid4())
        a,body=await self.count(scope,'2026-10-01',key=key)
        b,_=await self.count(scope,'2026-10-01',key=key)
        self.assertEqual(a.json()['header']['id'],b.json()['header']['id'])
        body['lines'][0]['inventory_value']='61'
        r=await self.client.post('/api/pg/actual-inventory/berts/counts',json=body,headers={'Idempotency-Key':key})
        self.assertEqual(r.status_code,409)

    async def test_recount_supersedes_unclosed_snapshot_without_mutating_history(self):
        scope,a,b=await self.pair()
        newer,_=await self.count(scope,'2026-10-08',quantity='1',value='30',corrects_snapshot_id=b['header']['id'])
        self.assertEqual(newer.status_code,200,newer.text)
        self.assertEqual((await self.report(a,b)).status_code,409)
        self.assertEqual((await self.report(a,newer.json())).status_code,200)
        old=await self.client.get('/api/pg/actual-inventory/berts/counts/'+b['header']['id'])
        self.assertEqual(old.json(),b)

    async def test_purchase_return_and_price_credit_affect_quantity_and_cost_independently(self):
        _,a,b=await self.pair();r,original=await self.purchase();self.assertEqual(r.status_code,200)
        file,*_=await self.capture(amounts=('-5',),overrides={'document_type_raw':'Credit'})
        doc=file['documents'][0]
        body=self.body(doc,movement_kind='price_credit',received_quantity=None,base_units_per_received_unit=None,
            original_line_id=original['lines'][0]['id'],movement_date='2026-10-05')
        self.assertEqual((await self.post(doc,body)).status_code,200)
        report=(await self.report(a,b)).json()
        self.assertEqual(report['rows'][0]['actualUsage'],'50.0');self.assertEqual(report['actualFoodCost'],'50.00')

    async def test_negative_usage_requires_explicit_overage_acknowledgement(self):
        r,_=await self.scope();scope=r.json();a,_=await self.count(scope,'2026-10-01',quantity='1',value='30')
        b,_=await self.count(scope,'2026-10-08',quantity='2',value='60')
        report=(await self.report(a.json(),b.json())).json();self.assertTrue(report['warnings'])
        self.assertEqual((await self.close(report)).status_code,409)
        self.assertEqual((await self.close(report,acknowledge_overages=True)).status_code,200)

    async def test_real_server_roles_location_boundary_and_disabled_flag(self):
        import server
        previous=server.db_pg._pool;server.db_pg._pool=self.pool
        try:
            _,body=await self.scope()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://test') as client:
                for role,locations,expected in [('readonly',['berts'],403),('staff',['berts'],403),('manager',['rudds'],403),('owner',[],200)]:
                    token=server._token({'id':'synthetic-manager','email':'test@example.invalid','role':role,'locations':locations})
                    r=await client.post('/api/pg/actual-inventory/berts/scope',json=body,headers={'Authorization':f'Bearer {token}','Idempotency-Key':str(uuid4())})
                    self.assertEqual(r.status_code,expected,r.text)
            with patch.dict(os.environ,{'ACTUAL_INVENTORY_ENABLED':'false'}):
                self.assertEqual((await self.client.get('/api/pg/actual-inventory/berts/setup')).status_code,503)
            with patch.dict(os.environ,{'PURCHASE_IMPORT_ENABLED':'false'}):
                self.assertEqual((await self.client.get('/api/pg/actual-inventory/berts/setup')).status_code,503)
            capabilities=(await self.client.get('/api/pg/purchases/berts/capabilities')).json()
            self.assertTrue(capabilities['reportingReady'])
            _,a,b=await self.pair();self.assertEqual((await self.report(a,b,'rudds')).status_code,404)
        finally:server.db_pg._pool=previous
