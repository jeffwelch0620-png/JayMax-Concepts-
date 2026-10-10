"""Invented receipts and loopback disposable PG only; no operational writes."""
import asyncio, os, unittest
from decimal import Decimal
from uuid import UUID, uuid4
import asyncpg
import native_backup as backup
import test_shared_catalog as shared
import test_manual_purchases as manual
import test_native_backup as recovery
import supplier_prices
from pydantic import ValidationError


class SupplierPriceValidationTests(unittest.TestCase):
    def test_unknown_fields_and_blank_notes_are_held(self):
        body=dict(line_id=uuid4(),expected_plan_hash='a'*64,verified=True,note='Verified')
        for patch in ({'note':' '},{'price':'5'},{'received_date':'2026-10-01'},{'expected_plan_hash':'bad'}):
            with self.assertRaises(ValidationError):supplier_prices.AdoptPrice(**{**body,**patch})


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PostgreSQL required')
class SupplierPriceTests(unittest.IsolatedAsyncioTestCase):
    asyncTearDown=shared.SharedCatalogTests.asyncTearDown
    payload=shared.SharedCatalogTests.payload
    put=shared.SharedCatalogTests.put
    units=shared.SharedCatalogTests.units
    pair=shared.SharedCatalogTests.pair
    scope=shared.SharedCatalogTests.scope
    count=shared.SharedCatalogTests.count
    report=shared.SharedCatalogTests.report
    post=shared.SharedCatalogTests.post
    body=shared.SharedCatalogTests.body
    target=shared.SharedCatalogTests.target
    capture=shared.SharedCatalogTests.capture
    plan=recovery.NativeBackupTests.plan
    correct=recovery.NativeBackupTests.correct

    async def asyncSetUp(self):
        await shared.SharedCatalogTests.asyncSetUp(self)
        async with self.pool.acquire() as c:
            await c.execute((recovery.counts.native.ROOT/'migrations/20261006_supplier_price_history.sql').read_text())

    async def prices(self,store='berts',offset=0):
        return await self.catalog.get(f'/api/pg/purchases/{store}/supplier-prices/{self.sku}',params={'offset':offset})

    async def receipt(self,date='2026-10-04',amount='40',qty='2'):
        captured=await self.client.post('/api/pg/purchases/berts/manual-records',json=manual.record(number=uuid4().hex,amount=amount),headers={'Idempotency-Key':str(uuid4())})
        self.assertEqual(captured.status_code,200,captured.text);doc=captured.json()['documents'][0]
        body=self.body(doc,received_quantity=qty);body['received_date']=date
        response=await self.post(doc,body)
        self.assertEqual(response.status_code,200,response.text)
        return doc

    async def adopt(self,chosen,key=None,store='berts',**patches):
        body=dict(line_id=chosen['line_id'],expected_plan_hash=chosen['plan_hash'],verified=True,note='Reviewed invented receipt and physical case conversion')
        return await self.catalog.post(f'/api/pg/purchases/{store}/supplier-prices/{self.sku}/adoptions',json={**body,**patches},headers={'Idempotency-Key':key or str(uuid4())})

    async def test_baseline_manual_clear_zero_and_unchanged_edits_have_exact_history(self):
        baseline=(await self.prices()).json();self.assertEqual(len(baseline['history']),1)
        self.assertEqual(baseline['history'][0]['source'],'baseline');self.assertIsNone(baseline['current']['effective_date'])
        body=await self.payload('berts');revision=baseline['revision']
        response=await self.put(body,revision,'berts');self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(len((await self.prices()).json()['history']),1)
        for value in ('80.000000000000000009',None,'0'):
            body['vendor_skus'][0]['price']=value
            revision=response.json()['revision'];response=await self.put(body,revision,'berts')
            self.assertEqual(response.status_code,200,response.text)
        result=(await self.prices()).json();self.assertEqual(len(result['history']),4)
        self.assertEqual(result['history'][0]['price'],'0');self.assertIsNone(result['history'][1]['price'])
        self.assertEqual(result['history'][2]['price'],'80.000000000000000009')
        self.assertEqual(result['history'][0]['actor'],'synthetic-catalog-reviewer')
        self.assertEqual(result['history'][0]['source'],'manual')

    async def test_posting_is_independent_adoption_is_atomic_idempotent_and_store_scoped(self):
        _,a,b=await self.pair();self.assertEqual((await self.units())[0].status_code,200)
        await self.receipt();before=(await self.report(a,b)).json();review=(await self.prices()).json();chosen=review['candidates'][0]
        self.assertEqual(review['current']['price'],'99.100000000000000001');self.assertEqual(len(review['history']),1)
        self.assertEqual(Decimal(chosen['price']),20);self.assertEqual(chosen['goods_received_date'],'2026-10-04')
        key=str(uuid4());replies=await asyncio.gather(self.adopt(chosen,key),self.adopt(chosen,key))
        self.assertTrue(all(r.status_code==200 for r in replies),[r.text for r in replies])
        self.assertEqual(replies[0].json()['event']['id'],replies[1].json()['event']['id'])
        review=(await self.prices()).json();self.assertEqual(len(review['history']),2);self.assertEqual(Decimal(review['current']['price']),20)
        self.assertEqual(review['current']['price_source'],'invoice');self.assertEqual(review['current']['effective_date'],'2026-10-04')
        self.assertEqual((await self.report(a,b)).json(),before)
        self.assertEqual((await self.adopt(chosen,key,note='Changed retry')).status_code,409)
        self.assertEqual((await self.adopt(chosen,key,store='rudds')).status_code,409)
        self.assertEqual((await self.adopt(review['candidates'][0])).status_code,409)
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT price FROM vendor_items WHERE id=$1',self.sku),Decimal('99.100000000000000001'))

    async def test_old_received_dates_stale_previews_and_manual_overrides_are_held(self):
        self.assertEqual((await self.units())[0].status_code,200)
        await self.receipt('2026-10-03');await self.receipt('2026-10-04','60')
        review=(await self.prices()).json();old=review['candidates'][1];new=review['candidates'][0]
        self.assertEqual((await self.adopt(new)).status_code,200)
        self.assertEqual((await self.adopt(old)).status_code,409)
        review=(await self.prices()).json();self.assertIn('predates',' '.join(review['candidates'][1]['issues']))
        body=await self.payload('berts');body['vendor_skus'][0]['price']='100'
        self.assertEqual((await self.put(body,review['revision'],'berts')).status_code,200)
        self.assertEqual((await self.adopt(new)).status_code,409)
        self.assertEqual((await self.prices()).json()['current']['price'],'100')

    async def test_conversion_and_preview_changes_hold_without_price_or_revision_writes(self):
        await self.receipt();review=(await self.prices()).json();self.assertIn('conversion',' '.join(review['candidates'][0]['issues']))
        self.assertEqual((await self.adopt(review['candidates'][0])).status_code,409)
        self.assertEqual((await self.units())[0].status_code,200)
        chosen=(await self.prices()).json()['candidates'][0]
        self.assertEqual((await self.adopt(chosen,verified=False)).status_code,422)
        body=await self.payload('berts');body['vendor_skus'][0]['available']=False
        review=(await self.prices()).json();self.assertEqual((await self.put(body,review['revision'],'berts')).status_code,200)
        self.assertEqual((await self.adopt(chosen)).status_code,409)
        fresh=(await self.prices()).json();self.assertEqual(len(fresh['history']),1)
        async with self.pool.acquire() as c:await c.execute('UPDATE vendor_items SET unit_qty=10 WHERE id=$1',self.sku)
        fresh=(await self.prices()).json();self.assertTrue(fresh['current']['source_stale'])
        self.assertEqual((await self.adopt(fresh['candidates'][0])).status_code,409)
        listed=(await self.catalog.get('/api/pg/items/berts')).json();sku=next(i for i in listed if i['code']=='test_food')['vendorSkus'][0]
        self.assertIsNone(sku['price']);self.assertTrue(sku['priceIssues'])

    async def test_corrected_invoice_invalidates_planning_cost_until_reviewed_again(self):
        self.assertEqual((await self.units())[0].status_code,200);doc=await self.receipt()
        chosen=(await self.prices()).json()['candidates'][0];self.assertEqual((await self.adopt(chosen)).status_code,200)
        plan=(await self.plan(doc,received_quantity='3')).json();response=await self.correct(doc,plan)
        self.assertEqual(response.status_code,200,response.text)
        review=(await self.prices()).json();self.assertTrue(review['current']['source_stale']);self.assertEqual(len(review['history']),2)
        listed=(await self.catalog.get('/api/pg/items/berts')).json();self.assertIsNone(next(i for i in listed if i['code']=='test_food')['vendorSkus'][0]['price'])
        self.assertEqual((await self.adopt(review['candidates'][0])).status_code,200)
        review=(await self.prices()).json();self.assertFalse(review['current']['source_stale']);self.assertEqual(len(review['history']),3)

    async def test_history_and_provenance_are_immutable_and_pack_edits_do_not_reprice(self):
        review=(await self.prices()).json();event=UUID(review['history'][0]['id'])
        async with self.pool.acquire() as c:
            for sql in ('UPDATE purchasing.supplier_price_events SET price=0 WHERE id=$1','DELETE FROM purchasing.supplier_price_events WHERE id=$1'):
                with self.assertRaises(asyncpg.PostgresError):await c.execute(sql,event)
            with self.assertRaises(asyncpg.PostgresError):await c.execute("UPDATE purchasing.store_vendor_items SET price_source='manual' WHERE vendor_item_id=$1",self.sku)
        body=await self.payload('berts');body['vendor_skus'][0]['unit_qty']=10
        self.assertEqual((await self.put(body,review['revision'],'berts')).status_code,409)
        body['vendor_skus'][0]['price']=None
        response=await self.put(body,review['revision'],'berts');self.assertEqual(response.status_code,200,response.text)
        self.assertIsNone((await self.prices()).json()['current']['price'])

    async def test_native_snapshot_restore_preserves_price_events_and_candidates(self):
        self.assertEqual((await self.units())[0].status_code,200);await self.receipt()
        chosen=(await self.prices()).json()['candidates'][0];self.assertEqual((await self.adopt(chosen)).status_code,200)
        before=(await self.prices()).json();destination=await self.target()
        manifest=await backup.create_backup(self.source,recovery.PG_DUMP,self.directory)
        result=await backup.verify_restore(destination,self.directory)
        self.assertEqual(result['status'],'verified');self.assertIn('purchasing.supplier_price_events',manifest['tables'])
        pool=await asyncpg.create_pool(destination,min_size=1,max_size=2,init=recovery.db_pg._init_connection)
        try:
            async with pool.acquire() as c:self.assertEqual(await supplier_prices.review(c,'berts',self.sku),before)
        finally:await pool.close()

    async def test_new_conversion_invalidates_invoice_price_and_same_amount_adoption_keeps_new_provenance(self):
        self.assertEqual((await self.units())[0].status_code,200);await self.receipt()
        candidate=(await self.prices()).json()['candidates'][0]
        self.assertEqual((await self.adopt(candidate)).status_code,200)
        await self.receipt('2026-10-05')
        candidate=(await self.prices()).json()['candidates'][0]
        self.assertEqual((await self.adopt(candidate)).status_code,200)
        review=(await self.prices()).json();self.assertEqual(len(review['history']),3)
        self.assertEqual(Decimal(review['history'][0]['price']),Decimal(review['history'][1]['price']))
        self.assertNotEqual(review['history'][0]['basis_snapshot']['line_id'],review['history'][1]['basis_snapshot']['line_id'])
        self.assertEqual((await self.units(factor='25'))[0].status_code,200)
        review=(await self.prices()).json();self.assertTrue(review['current']['source_stale'])
        listed=(await self.catalog.get('/api/pg/items/berts')).json();self.assertIsNone(next(i for i in listed if i['code']=='test_food')['vendorSkus'][0]['price'])
        self.assertEqual((await self.adopt(review['candidates'][0])).status_code,200)
        review=(await self.prices()).json();self.assertFalse(review['current']['source_stale']);self.assertEqual(Decimal(review['current']['price']),25)
