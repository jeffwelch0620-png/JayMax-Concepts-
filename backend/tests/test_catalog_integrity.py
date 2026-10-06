"""Invented catalog edits on the dedicated disposable PostgreSQL cluster."""
import os
import unittest
from decimal import Decimal
from unittest.mock import patch
import httpx
from pydantic import ValidationError
import server
import test_native_order_receiving as fixtures
import test_native_backup as recovery


class CatalogValidationTests(unittest.TestCase):
    def test_invalid_numeric_catalog_metadata_is_rejected_and_missing_price_is_unknown(self):
        for field in ('par', 'pack_count', 'unit_qty', 'portion_size', 'base_per_count_unit'):
            for value in (-1, float('nan'), float('inf')):
                with self.assertRaises(ValidationError):
                    server.ItemIn(code='SYNTHETIC', name='Invented', **{field: value})
        for field in ('price', 'pack_count', 'unit_qty', 'base_per_purchase_unit'):
            for value in (-1, 'NaN', 'Infinity'):
                with self.assertRaises(ValidationError):
                    server.VendorSkuIn(vendor_id='pfg', vendor_sku='00001', **{field: value})
        self.assertIsNone(server.VendorSkuIn(vendor_id='pfg', vendor_sku='00001').price)
        self.assertEqual(server.VendorSkuIn(vendor_id='pfg', vendor_sku='00001', price='12345678901234567890.000000000001').price, Decimal('12345678901234567890.000000000001'))


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Dedicated disposable PG required')
class CatalogIntegrityTests(unittest.IsolatedAsyncioTestCase):
    units = fixtures.NativeOrderReceivingTests.units
    pair = fixtures.NativeOrderReceivingTests.pair
    scope = fixtures.NativeOrderReceivingTests.scope
    count = fixtures.NativeOrderReceivingTests.count
    report = fixtures.NativeOrderReceivingTests.report
    capture = recovery.NativeBackupTests.capture
    post = fixtures.NativeOrderReceivingTests.post
    body = fixtures.NativeOrderReceivingTests.body
    target = fixtures.NativeOrderReceivingTests.target

    async def asyncSetUp(self):
        await fixtures.NativeOrderReceivingTests.asyncSetUp(self)
        self.previous = server.db_pg._pool; server.db_pg._pool = self.pool
        token = server._token({'id':'synthetic-catalog-reviewer', 'email':'catalog@example.invalid', 'role':'manager', 'locations':['berts','rudds']})
        self.catalog = httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url='http://test', headers={'Authorization':'Bearer '+token})

    async def asyncTearDown(self):
        await self.catalog.aclose(); server.db_pg._pool = self.previous
        await fixtures.NativeOrderReceivingTests.asyncTearDown(self)

    def entry(self, **changes):
        value = {'code':'test_food', 'name':'Invented catalog name', 'base_unit':'lb',
            'count_unit':'case', 'base_per_count_unit':20, 'counted_nightly':True,
            'active':True, 'order_enabled':True, 'sales_tracked':True,
            'vendor_skus':[{'vendor_id':'synthetic_other','vendor_sku':'00001', 'vendor_description':'  Original description — 4 / 5 LB  ',
                'purchase_unit':'case','base_per_purchase_unit':20,'pack_count':4,'unit_qty':5,'unit_uom':'lb',
                'price':'99.100000000000000001','preferred':True}]}
        return {**value, **changes}

    async def put(self, body, revision, store='berts'):
        return await self.catalog.put('/api/pg/items/'+store, json=body, headers={'If-Match':str(revision)})

    async def test_ordinary_edits_preserve_exact_price_provenance_description_and_count_actor(self):
        async with self.pool.acquire() as c:
            await c.execute("UPDATE vendor_items SET price=99.100000000000000001, price_updated_at='2026-10-01T12:00:00Z',price_source='invoice',vendor_description='  Original description — 4 / 5 LB  ' WHERE id=$1",self.sku)
            await c.execute("UPDATE store_items SET last_counted='2026-10-01',last_counted_by='Invented counter' WHERE item_code='test_food'")
        first=(await self.catalog.get('/api/pg/items/berts')).json()
        self.assertEqual(next(i for i in first if i['code']=='test_food')['vendorSkus'][0]['price'],'99.100000000000000001')
        response=await self.put([self.entry(counted_nightly=False, par=4)],0)
        self.assertEqual(response.status_code,200,response.text)
        with patch.dict(os.environ, {'ACTUAL_INVENTORY_ENABLED':'false'}):
            after=next(i for i in (await self.catalog.get('/api/pg/items/berts')).json() if i['code']=='test_food')
        self.assertTrue(after['active']); self.assertFalse(after['countActive'])
        self.assertEqual(after['lastCountedBy'],'Invented counter')
        self.assertEqual(after['vendorSkus'][0]['vendorDescription'],'  Original description — 4 / 5 LB  ')
        self.assertEqual(after['vendorSkus'][0]['priceSource'],'invoice')
        self.assertEqual(after['vendorSkus'][0]['priceUpdatedAt'],'2026-10-01T12:00:00+00:00')

    async def test_manual_price_change_and_clear_have_real_provenance_but_unknown_is_not_zero(self):
        response=await self.put([self.entry()],0);self.assertEqual(response.status_code,200,response.text)
        changed=self.entry();changed['vendor_skus'][0]['price']='100.000000000000000009'
        self.assertEqual((await self.put([changed],1)).status_code,200)
        async with self.pool.acquire() as c:
            row=await c.fetchrow('SELECT * FROM vendor_items WHERE id=$1',self.sku)
            self.assertEqual(row['price'],Decimal('100.000000000000000009'));self.assertEqual(row['price_source'],'manual')
            timestamp=row['price_updated_at']
        self.assertEqual((await self.put([changed],2)).status_code,200)
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT price_updated_at FROM vendor_items WHERE id=$1',self.sku),timestamp)
        changed['vendor_skus'][0]['price']=None
        self.assertEqual((await self.put([changed],3)).status_code,200)
        after=next(i for i in (await self.catalog.get('/api/pg/items/berts')).json() if i['code']=='test_food')
        self.assertIsNone(after['vendorSkus'][0]['price']);self.assertEqual(after['vendorSkus'][0]['priceSource'],'manual')

    async def test_retirement_preserves_actual_periods_physical_scope_and_other_store(self):
        _,a,b=await self.pair();file,*_=await self.capture();self.assertEqual((await self.post(file['documents'][0])).status_code,200)
        before=(await self.report(a,b)).json()
        async with self.pool.acquire() as c:
            await c.execute("INSERT INTO store_items(store_id,item_code,count_unit,base_per_count_unit,counted_nightly) VALUES('rudds','test_food','case',20,true)")
            await c.execute("UPDATE store_items SET current_stock=7,counted_nightly=true WHERE store_id='berts' AND item_code='test_food'")
            revision=await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'")
        response=await self.catalog.delete('/api/pg/items/berts/test_food',headers={'If-Match':str(revision)})
        self.assertEqual(response.status_code,200,response.text);self.assertTrue(response.json()['retired']);self.assertFalse(response.json()['deleted'])
        after=(await self.report(a,b)).json();self.assertEqual(before,after)
        async with self.pool.acquire() as c:
            row=await c.fetchrow("SELECT * FROM store_items WHERE store_id='berts' AND item_code='test_food'")
            self.assertFalse(row['active']);self.assertFalse(row['order_enabled']);self.assertTrue(row['counted_nightly']);self.assertEqual(row['current_stock'],7)
            self.assertTrue(await c.fetchval("SELECT active FROM store_items WHERE store_id='rudds' AND item_code='test_food'"))
            self.assertEqual(await c.fetchval('SELECT count(*) FROM vendor_items WHERE id=$1',self.sku),1)
            vendor=await c.fetchval("SELECT name FROM vendors WHERE id='synthetic_other'")
        order=await self.catalog.post('/api/orders/berts',json={'vendor':vendor,'lines':[{'itemCode':'test_food','controlNumber':'test_food','name':'Invented food','vendorSku':'00001','qty':1,'unitCost':99,'purchaseUnit':'case'}]})
        self.assertEqual(order.status_code,422,order.text)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval("SELECT count(*) FROM purchase_orders WHERE store_id='berts'"),0)
        stale=await self.put([self.entry()],revision);self.assertEqual(stale.status_code,409,stale.text)

    async def test_omission_retires_but_never_deletes_supplier_or_recipe_references(self):
        async with self.pool.acquire() as c:
            dish=await c.fetchval("INSERT INTO dishes(store_id,name,recipe_type) VALUES('berts','Invented recipe','menu') RETURNING id")
            await c.execute("INSERT INTO dish_lines(dish_id,source_type,item_code,qty) VALUES($1,'item','test_food',1)",dish)
        response=await self.put([],0);self.assertEqual(response.status_code,200,response.text)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval("SELECT count(*) FROM items WHERE code='test_food'"),1)
            self.assertEqual(await c.fetchval("SELECT count(*) FROM dish_lines WHERE item_code='test_food'"),1)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM vendor_items WHERE id=$1',self.sku),1)
            self.assertFalse(await c.fetchval("SELECT active FROM store_items WHERE store_id='berts' AND item_code='test_food'"))
        # Removed supplier choices retain identity and recorded prices as unavailable.
        response=await self.put([self.entry(vendor_skus=[])],1);self.assertEqual(response.status_code,200,response.text)
        async with self.pool.acquire() as c:self.assertFalse(await c.fetchval('SELECT available FROM vendor_items WHERE id=$1',self.sku))

    async def test_invalid_later_item_rolls_back_catalog_and_revision(self):
        bad=self.entry(code='bad_food', vendor_skus=[{'vendor_id':'missing_supplier','vendor_sku':'bad'}])
        response=await self.put([self.entry(),bad],0);self.assertEqual(response.status_code,400,response.text)
        async with self.pool.acquire() as c:
            self.assertNotEqual(await c.fetchval("SELECT name FROM items WHERE code='test_food'"),'Invented catalog name')
            self.assertFalse(await c.fetchval("SELECT EXISTS(SELECT 1 FROM items WHERE code='bad_food')"))
            self.assertEqual(await c.fetchval("SELECT COALESCE((SELECT revision FROM store_state WHERE store_id='berts'),0)"),0)

    async def test_granular_creation_invalidates_stale_collection_save(self):
        body=self.entry(code='fresh_item',vendor_skus=[])
        response=await self.catalog.post('/api/pg/items/berts',json=body,headers={'If-Match':'0'})
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['revision'],1)
        response=await self.put([],0);self.assertEqual(response.status_code,409,response.text)
