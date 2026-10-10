"""Synthetic-only physical-unit and invoice-linked PO receiving integration."""
import asyncio
import json
import os
import unittest
from decimal import Decimal
from uuid import UUID,uuid4

import asyncpg
import httpx
import native_backup as backup
import test_manual_purchases as fixtures
import test_native_backup as recovery


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PG DSN required')
class NativeOrderReceivingTests(unittest.IsolatedAsyncioTestCase):
    asyncTearDown=fixtures.ManualPurchaseTests.asyncTearDown
    target=fixtures.ManualPurchaseTests.target
    restored_client=fixtures.ManualPurchaseTests.restored_client
    manual=fixtures.ManualPurchaseTests.manual
    attachment=fixtures.ManualPurchaseTests.attachment
    body=fixtures.ManualPurchaseTests.body
    post=fixtures.ManualPurchaseTests.post
    pair=fixtures.ManualPurchaseTests.pair
    scope=fixtures.ManualPurchaseTests.scope
    count=fixtures.ManualPurchaseTests.count
    report=fixtures.ManualPurchaseTests.report
    close=fixtures.ManualPurchaseTests.close
    plan=fixtures.ManualPurchaseTests.plan
    correct=fixtures.ManualPurchaseTests.correct

    async def asyncSetUp(self):
        await fixtures.ManualPurchaseTests.asyncSetUp(self)
        async with self.pool.acquire() as conn:
            await conn.execute((recovery.counts.native.ROOT/'migrations/20261005_native_order_receiving.sql').read_text())
            await conn.execute("UPDATE public.store_items SET count_unit='case' WHERE store_id='berts' AND item_code='test_food'")
            self.sku=await conn.fetchval("INSERT INTO public.vendor_items(vendor_id,vendor_sku,item_code,purchase_unit,pack_count,unit_qty,unit_uom,base_per_purchase_unit) VALUES('synthetic_other','00001','test_food','case',4,5,'lb',8) RETURNING id")

    async def units(self,kind='purchase',factor='20',key=None):
        setup=(await self.client.get('/api/pg/purchases/berts/unit-setup')).json();item=next(i for i in setup['items'] if i['code']=='test_food')
        source=item['countSource'] if kind=='count' else item['supplierProducts'][0]
        body={'item_code':'test_food','profile_kind':kind,'vendor_item_id':str(self.sku) if kind=='purchase' else None,
            'base_unit':'lb','base_units_per_source_unit':factor,'expected_source_hash':source['hash'],'verified':True,'note':'Measured 20 physical pounds per case; not recipe portions'}
        result=await self.client.post('/api/pg/purchases/berts/unit-profiles',json=body,headers={'Idempotency-Key':key or str(uuid4())})
        return result,body

    async def po(self,qty='4',ref=None):
        ref=ref or 'po_synthetic_'+uuid4().hex[:10]
        async with self.pool.acquire() as conn:
            pid=await conn.fetchval("INSERT INTO public.purchase_orders(store_id,vendor_id,vendor_name,status,ref) VALUES('berts','synthetic_other','Invented supplier','sent',$1) RETURNING id",ref)
            line=await conn.fetchval("INSERT INTO public.purchase_order_lines(po_id,item_code,control_number,name,vendor_sku,qty,unit,unit_price,extended) VALUES($1,'test_food','test_food','Invented food','00001',$2,'case',99,396) RETURNING id",pid,Decimal(qty))
        return ref,pid,line

    async def purchase(self,number=None):
        captured=(await self.manual(fixtures.record(number=number or uuid4().hex))).json();doc=captured['documents'][0]
        r=await self.post(doc);self.assertEqual(r.status_code,200,r.text)
        return r.json()['document']

    async def receipt_plan(self,ref,line,doc,complete=False):
        body={'document_version_id':doc['id'],'lines':[{'source_line_id':l['id'],'po_line_id':str(line),'verified':True} for l in doc['lines']],
            'complete_order':complete,'variances_reviewed':True,'note':'Verified actual invoice receipt and order comparison'}
        return await self.client.post(f'/api/pg/purchases/berts/orders/{ref}/receipt-preview',json=body)

    async def link(self,ref,plan,key=None):
        return await self.client.post(f'/api/pg/purchases/berts/orders/{ref}/receipts',json={**plan['review'],'expected_plan_hash':plan['planHash']},headers={'Idempotency-Key':key or str(uuid4())})

    async def test_physical_unit_profiles_ignore_legacy_portion_factor_and_feed_suggestions(self):
        r,_=await self.units();self.assertEqual(r.status_code,200,r.text)
        r,_=await self.units('count');self.assertEqual(r.status_code,200,r.text)
        doc=(await self.manual()).json()['documents'][0];suggestion=doc['lines'][0]['unitProfileSuggestion']
        self.assertEqual(suggestion['base_units_per_source_unit'],'20');self.assertEqual(suggestion['base_unit'],'lb')
        self.assertEqual((await self.client.get('/api/pg/actual-inventory/berts/setup')).json()['unitProfiles'][0]['source_unit'],'case')
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT base_per_purchase_unit FROM vendor_items WHERE id=$1',self.sku),8)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.actual_purchase_facts'),0)

    async def test_profile_retry_staleness_and_fixed_base_unit_guards(self):
        key=str(uuid4());r,body=await self.units(key=key);self.assertEqual(r.status_code,200,r.text)
        async with self.pool.acquire() as conn:await conn.execute('UPDATE vendor_items SET unit_qty=10 WHERE id=$1',self.sku)
        again=await self.client.post('/api/pg/purchases/berts/unit-profiles',json=body,headers={'Idempotency-Key':key})
        self.assertEqual(again.json()['profile']['id'],r.json()['profile']['id'])
        fresh=(await self.client.get('/api/pg/purchases/berts/unit-setup')).json();self.assertTrue(fresh['profiles'][0]['stale'])
        rejected=await self.client.post('/api/pg/purchases/berts/unit-profiles',json=body,headers={'Idempotency-Key':str(uuid4())});self.assertEqual(rejected.status_code,409)
        body['expected_source_hash']=fresh['items'][next(i for i,r in enumerate(fresh['items']) if r['code']=='test_food')]['supplierProducts'][0]['hash'];body['base_unit']='oz'
        rejected=await self.client.post('/api/pg/purchases/berts/unit-profiles',json=body,headers={'Idempotency-Key':str(uuid4())});self.assertEqual(rejected.status_code,409)

    async def test_partial_deliveries_link_purchases_once_and_preserve_order_conversion(self):
        _,a,b=await self.pair();self.assertEqual((await self.units())[0].status_code,200)
        ref,pid,line=await self.po();doc=await self.purchase();before=(await self.report(a,b)).json()
        p=(await self.receipt_plan(ref,line,doc)).json();self.assertEqual(p['status'],'ready');self.assertEqual(Decimal(p['comparison'][0]['differenceBase']),-40)
        key=str(uuid4());replies=await asyncio.gather(self.link(ref,p,key),self.link(ref,p,key))
        self.assertTrue(all(r.status_code==200 for r in replies),[r.text for r in replies])
        self.assertEqual(replies[0].json()['receipt']['id'],replies[1].json()['receipt']['id'])
        self.assertEqual((await self.report(a,b)).json(),before)
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT current_stock FROM store_items WHERE item_code=$1 AND store_id=$2','test_food','berts'),0)
            self.assertEqual(await conn.fetchval('SELECT status FROM purchase_orders WHERE id=$1',pid),'receiving')
            await conn.execute('UPDATE vendor_items SET unit_qty=6 WHERE id=$1',self.sku)
        self.assertEqual((await self.units(factor='24'))[0].status_code,200)
        second=await self.purchase();p=(await self.receipt_plan(ref,line,second,True)).json()
        self.assertEqual(p['orderedRows'][0]['factor'],'20');self.assertEqual(Decimal(p['comparison'][0]['differenceBase']),0)
        r=await self.link(ref,p);self.assertEqual(r.status_code,200,r.text)
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT status FROM purchase_orders WHERE id=$1',pid),'received')
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.actual_purchase_facts'),2)

    async def test_invoice_cannot_link_twice_and_order_estimates_never_become_food_cost(self):
        await self.units();ref,_,line=await self.po(qty='1');doc=await self.purchase()
        p=(await self.receipt_plan(ref,line,doc,True)).json();self.assertEqual((await self.link(ref,p)).status_code,200)
        other,_,otherline=await self.po();p=(await self.receipt_plan(other,otherline,doc)).json();self.assertEqual(p['status'],'held')
        self.assertEqual((await self.link(other,p)).status_code,409)
        async with self.pool.acquire() as conn:self.assertEqual(await conn.fetchval('SELECT sum(inventory_cost_amount) FROM purchasing.actual_purchase_facts'),40)

    async def test_new_invoice_correction_marks_order_stale_without_blocking_accounting(self):
        await self.units();ref,_,line=await self.po();doc=await self.purchase()
        p=(await self.receipt_plan(ref,line,doc)).json();self.assertEqual((await self.link(ref,p)).status_code,200)
        plan=(await self.plan(doc,received_quantity='3')).json();self.assertEqual(plan['status'],'ready')
        corrected=await self.correct(doc,plan);self.assertEqual(corrected.status_code,200,corrected.text)
        setup=(await self.client.get(f'/api/pg/purchases/berts/orders/{ref}/receipt-setup')).json();self.assertTrue(setup['history'][0]['stale'])
        new=await self.purchase();p=(await self.receipt_plan(ref,line,new)).json();self.assertEqual(p['status'],'held')
        self.assertEqual((await self.link(ref,p)).status_code,409)
        async with self.pool.acquire() as conn:self.assertEqual(await conn.fetchval('SELECT sum(base_quantity) FROM purchasing.actual_purchase_facts'),100)

    async def test_receipt_preview_invalidates_on_concurrent_invoice_and_order_changes(self):
        await self.units();ref,pid,line=await self.po();doc=await self.purchase()
        p=(await self.receipt_plan(ref,line,doc)).json()
        async with self.pool.acquire() as conn:await conn.execute('UPDATE purchase_order_lines SET qty=5 WHERE id=$1',line)
        self.assertEqual((await self.link(ref,p)).status_code,409)
        p=(await self.receipt_plan(ref,line,doc)).json();correction=(await self.plan(doc,received_quantity='3')).json()
        self.assertEqual((await self.correct(doc,correction)).status_code,200)
        self.assertEqual((await self.link(ref,p)).status_code,409)
        async with self.pool.acquire() as conn:self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.po_receipts'),0)

    async def test_missing_unit_profile_wrong_supplier_and_cross_store_are_held(self):
        ref,pid,line=await self.po();doc=await self.purchase()
        self.assertEqual((await self.receipt_plan(ref,line,doc)).status_code,409)
        await self.units()
        async with self.pool.acquire() as conn:await conn.execute("UPDATE purchase_orders SET vendor_id='another_supplier' WHERE id=$1",pid)
        self.assertEqual((await self.receipt_plan(ref,line,doc)).status_code,409)
        r=await self.client.get(f'/api/pg/purchases/rudds/orders/{ref}/receipt-setup');self.assertEqual(r.status_code,404)

    async def test_linking_closed_period_purchase_does_not_change_frozen_accounting(self):
        _,a,b=await self.pair();await self.units();ref,_,line=await self.po();doc=await self.purchase()
        before=(await self.report(a,b)).json();self.assertEqual((await self.close(before)).status_code,200)
        p=(await self.receipt_plan(ref,line,doc,True)).json();r=await self.link(ref,p);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual((await self.report(a,b)).json(),before)

    async def test_received_order_history_and_lines_are_sealed(self):
        await self.units();ref,pid,line=await self.po();doc=await self.purchase();p=(await self.receipt_plan(ref,line,doc)).json()
        r=await self.link(ref,p);self.assertEqual(r.status_code,200,r.text)
        async with self.pool.acquire() as conn:
            for sql,args in [('DELETE FROM purchasing.po_receipts',()),('UPDATE public.purchase_order_lines SET qty=999 WHERE id=$1',(line,)),('DELETE FROM public.purchase_orders WHERE id=$1',(pid,))]:
                with self.assertRaises(asyncpg.RaiseError):await conn.execute(sql,*args)
            with self.assertRaises(asyncpg.RaiseError):
                await conn.execute('''INSERT INTO purchasing.po_receipt_lines SELECT receipt_id,po_id,NULL,source_line_id,mapping_id,NULL,base_quantity,base_unit FROM purchasing.po_receipt_lines''')
            with self.assertRaises(asyncpg.RaiseError):
                await conn.execute("INSERT INTO public.purchase_order_lines(po_id,name,qty,unit) VALUES($1,'late extra',1,'case')",pid)

    async def test_legacy_stock_and_price_routes_are_blocked_in_native_mode(self):
        import server
        previous=server.db_pg._pool;server.db_pg._pool=self.pool
        try:
            token=server._token({'id':'synthetic-manager','email':'manager@example.invalid','role':'manager','locations':['berts']})
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://test',headers={'Authorization':'Bearer '+token}) as client:
                self.assertEqual((await client.post('/api/orders/berts/nonexistent/receive',json={'lines':[]})).status_code,409)
                self.assertEqual((await client.post('/api/orders/berts/nonexistent/apply-prices',json={'lines':[]})).status_code,409)
        finally:server.db_pg._pool=previous

    async def test_missing_catalog_unit_holds_only_that_source_and_preserves_other_setup(self):
        await self.units();await self.units('count')
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE store_items SET count_unit='' WHERE store_id='berts' AND item_code='test_food'")
        response=await self.client.get('/api/pg/purchases/berts/unit-setup')
        self.assertEqual(response.status_code,200,response.text)
        item=next(i for i in response.json()['items'] if i['code']=='test_food')
        self.assertIsNone(item['countSource']);self.assertTrue(item['issues'])
        self.assertEqual(len(item['supplierProducts']),1)
        count_profile=next(p for p in response.json()['profiles'] if p['profile_kind']=='count')
        self.assertTrue(count_profile['stale'])

    async def test_native_order_creation_and_edits_resolve_the_unique_active_supplier(self):
        import server
        previous=server.db_pg._pool;server.db_pg._pool=self.pool
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("INSERT INTO vendors(id,name,active) VALUES('inactive_duplicate','Invented supplier',false)")
            ref='po_supplier_'+uuid4().hex
            await server._po_insert({'id':ref,'restaurantId':'berts','vendor':'Invented supplier','status':'draft','createdAt':'2026-10-04T12:00:00+00:00','lines':[]})
            self.assertTrue(await server._po_update('berts',ref,{'vendor':'Invented supplier'}))
            async with self.pool.acquire() as conn:
                self.assertEqual(await conn.fetchval('SELECT vendor_id FROM purchase_orders WHERE ref=$1',ref),'synthetic_other')
                await conn.execute("INSERT INTO vendors(id,name,active) VALUES('active_duplicate','Invented supplier',true)")
            with self.assertRaises(server.HTTPException) as failure:
                await server._po_update('berts',ref,{'vendor':'Invented supplier'})
            self.assertEqual(failure.exception.status_code,422)
        finally:server.db_pg._pool=previous

    async def test_order_receipts_and_profiles_survive_native_recovery(self):
        file_id,_=await self.attachment();_,a,b=await self.pair();await self.units();await self.units('count')
        ref,_,line=await self.po();captured=(await self.manual(fixtures.record(attachment_ids=[file_id]))).json()
        r=await self.post(captured['documents'][0]);self.assertEqual(r.status_code,200,r.text);doc=r.json()['document']
        p=(await self.receipt_plan(ref,line,doc,True)).json();self.assertEqual((await self.link(ref,p)).status_code,200)
        paths=[f'/api/pg/purchases/berts/orders/{ref}/receipt-setup','/api/pg/purchases/berts/unit-setup']
        before={p:(await self.client.get(p)).json() for p in paths};report=(await self.report(a,b)).json()
        manifest=await backup.create_backup(self.source,recovery.PG_DUMP,self.directory);self.assertEqual(manifest['tables']['purchasing.po_receipts']['rows'],1)
        dsn=await self.target();verified=await backup.verify_restore(dsn,self.directory);self.assertEqual(verified['status'],'verified')
        client,_=await self.restored_client(dsn)
        for p in paths:self.assertEqual((await client.get(p)).json(),before[p])
        restored=(await client.get('/api/pg/actual-inventory/berts/report',params={'opening':a['header']['id'],'closing':b['header']['id']})).json()
        self.assertEqual(restored,report)
        (self.directory/'order-api-verification.json').write_text(json.dumps({'status':'verified','actualFoodCost':restored['actualFoodCost'],
            'unitProfilesMatched':2,'orderReceiptHistoryMatched':True,'reportHashMatched':True},indent=2))
