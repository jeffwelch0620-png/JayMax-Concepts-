"""Explicit shared catalog mapping using invented sources and disposable PG."""
import asyncio, json, os, unittest
import asyncpg
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4
from pydantic import ValidationError
import catalog_mapping as mapping
import native_backup as backup
import server
import test_catalog_integrity as catalog
import test_native_order_receiving as orders
import test_native_backup as recovery


class SharedCatalogValidationTests(unittest.TestCase):
    def test_feature_dependencies_and_link_numbers_are_held(self):
        with patch.dict(os.environ,{'CATALOG_MAPPING_ENABLED':'true','PURCHASE_IMPORT_ENABLED':'false'}):
            with self.assertRaises(server.HTTPException):mapping.enabled()
        base=dict(item_code='food',control_number='F01',count_unit='case',base_per_count_unit='20',vendor_item_ids=[uuid4()],verified=True,expected_catalog_hash='a'*64)
        for key,value in [('base_per_count_unit','0'),('base_per_count_unit','NaN'),('base_per_count_unit','Infinity'),('par','-1'),('control_number',' '),('count_unit',' '),('vendor_item_ids',[])]:
            with self.assertRaises(ValidationError):mapping.LinkItem(**{**base,key:value})


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PostgreSQL required')
class SharedCatalogTests(unittest.IsolatedAsyncioTestCase):
    units=orders.NativeOrderReceivingTests.units
    pair=orders.NativeOrderReceivingTests.pair
    scope=orders.NativeOrderReceivingTests.scope
    count=orders.NativeOrderReceivingTests.count
    report=orders.NativeOrderReceivingTests.report
    capture=recovery.NativeBackupTests.capture
    post=orders.NativeOrderReceivingTests.post
    body=orders.NativeOrderReceivingTests.body
    target=orders.NativeOrderReceivingTests.target
    restored_client=orders.NativeOrderReceivingTests.restored_client

    async def asyncSetUp(self):
        await catalog.CatalogIntegrityTests.asyncSetUp(self)
        async with self.pool.acquire() as c:
            await c.execute("UPDATE vendor_items SET price=99.100000000000000001,price_updated_at='2026-10-01T12:00:00Z',price_source='invoice',preferred=true WHERE id=$1",self.sku)
            await c.execute((recovery.counts.native.ROOT/'migrations/20261006_shared_catalog.sql').read_text())
        self.mapping_flag=patch.dict(os.environ,{'CATALOG_MAPPING_ENABLED':'true','ACTUAL_INVENTORY_ENABLED':'true'});self.mapping_flag.start()

    async def asyncTearDown(self):
        self.mapping_flag.stop();await catalog.CatalogIntegrityTests.asyncTearDown(self)

    async def link_body(self,control='R01'):
        response=await self.catalog.get('/api/pg/catalog/rudds');self.assertEqual(response.status_code,200,response.text)
        chosen=next(p for p in response.json()['products'] if p['item_code']=='test_food')
        return dict(item_code='test_food',control_number=control,count_unit='bag',base_per_count_unit='2',par='6',
            vendor_item_ids=[str(self.sku)],verified=True,expected_catalog_hash=chosen['catalog_hash'])

    async def link(self,body=None,revision=0):
        return await self.catalog.post('/api/pg/catalog/rudds/links',json=body or await self.link_body(),headers={'If-Match':str(revision)})

    async def payload(self,store='rudds',**changes):
        async with self.pool.acquire() as c:
            item=dict(await c.fetchrow("SELECT * FROM items WHERE code='test_food'"))
            si=dict(await c.fetchrow("SELECT * FROM store_items WHERE store_id=$1 AND item_code='test_food'",store))
            skus=await mapping.supplier_rows(c,store,'test_food')
        body={key:item[key] for key in ('name','base_unit','category','item_type','is_high_value','notes','costing_type','pack_count','unit_qty','unit_uom','portion_size','portion_uom')}
        body.update({key:si[key] for key in ('control_number','count_unit','base_per_count_unit','storage_area','counted_nightly','par','active','order_enabled','sales_tracked','needs_review')})
        body.update(code='test_food',vendor_skus=[{key:s[key] for key in ('vendor_id','vendor_sku','vendor_description','purchase_unit','base_per_purchase_unit','pack_count','unit_qty','unit_uom','price','preferred','available')} for s in skus])
        return server.purchase_api.serial({**body,**changes})

    async def put(self,body,revision,store='rudds'):
        return await self.catalog.put('/api/pg/items/'+store,json=[body],headers={'If-Match':str(revision)})

    async def test_explicit_link_reuses_one_identity_with_independent_alias_par_price_and_units(self):
        response=await self.link();self.assertEqual(response.status_code,200,response.text)
        a=(await self.catalog.get('/api/pg/items/berts')).json();b=(await self.catalog.get('/api/pg/items/rudds')).json()
        a=next(i for i in a if i['code']=='test_food');b=b[0]
        self.assertEqual(a['code'],b['code']);self.assertEqual(a['vendorSkus'][0]['id'],b['vendorSkus'][0]['id'])
        self.assertEqual(a['controlNumber'],'test_food');self.assertEqual(b['controlNumber'],'R01')
        self.assertEqual(b['par'],6);self.assertEqual(b['basePerCountUnit'],2);self.assertFalse(b['countActive'])
        self.assertEqual(a['vendorSkus'][0]['price'],'99.100000000000000001');self.assertEqual(a['vendorSkus'][0]['priceSource'],'invoice')
        self.assertIsNone(b['vendorSkus'][0]['price']);self.assertIsNone(b['vendorSkus'][0]['priceSource'])
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval("SELECT count(*) FROM vendor_items WHERE vendor_id='synthetic_other' AND vendor_sku='00001'"),1)
            self.assertEqual(await c.fetchval("SELECT count(*) FROM purchasing.item_bases WHERE store_id='rudds'"),0)
            self.assertEqual(await c.fetchval("SELECT current_stock FROM store_items WHERE store_id='rudds' AND item_code='test_food'"),0)

    async def test_location_supplier_edits_do_not_change_other_store_provenance_or_unit_profiles(self):
        self.assertEqual((await self.units())[0].status_code,200)
        self.assertEqual((await self.link()).status_code,200)
        body=await self.payload();body['vendor_skus'][0].update(price='80.000000000000000009',available=False,preferred=False)
        response=await self.put(body,1);self.assertEqual(response.status_code,200,response.text)
        async with self.pool.acquire() as c:
            a=await c.fetchrow("SELECT * FROM purchasing.store_vendor_items WHERE store_id='berts' AND vendor_item_id=$1",self.sku)
            b=await c.fetchrow("SELECT * FROM purchasing.store_vendor_items WHERE store_id='rudds' AND vendor_item_id=$1",self.sku)
            self.assertEqual(a['price'],Decimal('99.100000000000000001'));self.assertEqual(a['price_source'],'invoice');self.assertTrue(a['available']);self.assertTrue(a['preferred'])
            self.assertEqual(b['price'],Decimal('80.000000000000000009'));self.assertEqual(b['price_source'],'manual');timestamp=b['price_updated_at']
            self.assertEqual(await c.fetchval('SELECT price FROM vendor_items WHERE id=$1',self.sku),a['price'])
        self.assertEqual((await self.put(body,2)).status_code,200)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval("SELECT price_updated_at FROM purchasing.store_vendor_items WHERE store_id='rudds' AND vendor_item_id=$1",self.sku),timestamp)
            self.assertTrue((await mapping.supplier_rows(c,'berts','test_food'))[0]['available'])
        setup=(await self.client.get('/api/pg/purchases/berts/unit-setup')).json();self.assertFalse(setup['profiles'][0]['stale'])
        body['vendor_skus']=[];self.assertEqual((await self.put(body,3)).status_code,200)
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT count(*) FROM vendor_items WHERE id=$1',self.sku),1)

    async def test_shared_global_changes_and_conflicting_duplicate_sku_are_held_atomically(self):
        self.assertEqual((await self.link()).status_code,200)
        for change in ('name','pack'):
            body=await self.payload()
            if change=='name':body['name']='Accidental shared name change'
            else:body['vendor_skus'][0]['pack_count']=200
            response=await self.put(body,1);self.assertEqual(response.status_code,409,response.text)
        duplicate=await self.payload();duplicate.update(code='new_food',control_number='R02')
        response=await self.put(duplicate,1);self.assertEqual(response.status_code,409,response.text)
        async with self.pool.acquire() as c:
            self.assertFalse(await c.fetchval("SELECT EXISTS(SELECT 1 FROM items WHERE code='new_food')"))
            self.assertEqual(await c.fetchval("SELECT revision FROM store_state WHERE store_id='rudds'"),1)
            self.assertEqual(await c.fetchval('SELECT pack_count FROM vendor_items WHERE id=$1',self.sku),4)
            with self.assertRaises(asyncpg.ForeignKeyViolationError):
                await c.execute("UPDATE vendor_items SET item_code='other_food' WHERE id=$1",self.sku)

    async def test_stale_hash_unverified_wrong_sku_and_alias_collision_do_not_write(self):
        base=await self.link_body()
        for changes,status in [({'expected_catalog_hash':'0'*64},409),({'verified':False},422),({'vendor_item_ids':[str(uuid4())]},422),({'vendor_item_ids':[str(self.sku),str(self.sku)]},422)]:
            response=await self.link({**base,**changes});self.assertEqual(response.status_code,status,response.text)
        async with self.pool.acquire() as c:
            await c.execute("INSERT INTO store_items(store_id,item_code,control_number,count_unit,base_per_count_unit) VALUES('rudds','other_food','R01','lb',1)")
        response=await self.link(base);self.assertEqual(response.status_code,409,response.text)
        async with self.pool.acquire() as c:
            self.assertFalse(await c.fetchval("SELECT EXISTS(SELECT 1 FROM store_items WHERE store_id='rudds' AND item_code='test_food')"))
            self.assertEqual(await c.fetchval("SELECT COALESCE((SELECT revision FROM store_state WHERE store_id='rudds'),0)"),0)

    async def test_parallel_links_and_stale_replacements_cannot_overwrite_new_membership(self):
        body=await self.link_body();responses=await asyncio.gather(self.link(body),self.link(body))
        self.assertEqual(sorted(r.status_code for r in responses),[200,409])
        response=await self.catalog.put('/api/pg/items/rudds',json=[],headers={'If-Match':'0'});self.assertEqual(response.status_code,409)
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval("SELECT count(*) FROM store_items WHERE store_id='rudds' AND item_code='test_food'"),1)

    async def test_installed_schema_never_falls_back_to_legacy_global_settings(self):
        self.assertEqual((await self.link()).status_code,200)
        body=await self.payload();body['vendor_skus'][0]['price']='80';self.assertEqual((await self.put(body,1)).status_code,200)
        with patch.dict(os.environ,{'CATALOG_MAPPING_ENABLED':'false'}):
            self.assertEqual((await self.catalog.get('/api/pg/items/rudds')).status_code,503)
            self.assertEqual((await self.put(body,2)).status_code,503)
            response=await self.catalog.post('/api/orders/rudds',json={'vendor':'Invented supplier','lines':[]});self.assertEqual(response.status_code,503,response.text)
            with self.assertRaises(server.HTTPException) as held:
                await server._pg_apply_prices('rudds','Invented supplier',[])
            self.assertEqual(held.exception.status_code,503)
            with patch.dict(os.environ,{'PURCHASE_IMPORT_ENABLED':'false'}):
                response=await self.catalog.post('/api/pg/invoices/rudds',json={'vendor_id':'synthetic_other','invoice_date':'2026-10-06','lines':[{'vendor_item_id':str(self.sku),'qty':1,'unit_price':1}]})
                self.assertEqual(response.status_code,503,response.text)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval("SELECT revision FROM store_state WHERE store_id='rudds'"),2)
            self.assertEqual(await c.fetchval('SELECT price FROM vendor_items WHERE id=$1',self.sku),Decimal('99.100000000000000001'))

    async def test_store_availability_guards_orders_but_retirement_preserves_actual_report(self):
        _,a,b=await self.pair();file,*_=await self.capture();self.assertEqual((await self.post(file['documents'][0])).status_code,200)
        actual=(await self.report(a,b)).json();self.assertEqual((await self.link()).status_code,200)
        order=dict(vendor='Invented supplier',lines=[dict(itemCode='test_food',controlNumber='R01',name='Synthetic food',vendorSku='00001',qty=1,unitCost=0,purchaseUnit='case')])
        self.assertEqual((await self.catalog.post('/api/orders/rudds',json=order)).status_code,200)
        body=await self.payload();body['vendor_skus'][0]['available']=False;self.assertEqual((await self.put(body,1)).status_code,200)
        response=await self.catalog.post('/api/orders/rudds',json=order);self.assertEqual(response.status_code,422,response.text)
        self.assertEqual((await self.catalog.delete('/api/pg/items/rudds/test_food',headers={'If-Match':'2'})).status_code,200)
        self.assertEqual(actual,(await self.report(a,b)).json())
        async with self.pool.acquire() as c:
            self.assertTrue(await c.fetchval("SELECT active FROM store_items WHERE store_id='berts' AND item_code='test_food'"))
            self.assertEqual(await c.fetchval("SELECT count(*) FROM purchase_orders WHERE store_id='rudds'"),1)

    async def test_shared_aliases_settings_and_accounting_survive_whole_synthetic_restore(self):
        _,a,b=await self.pair();file,*_=await self.capture();self.assertEqual((await self.post(file['documents'][0])).status_code,200)
        self.assertEqual((await self.link()).status_code,200)
        paths=['/api/pg/items/berts','/api/pg/items/rudds']
        before={p:(await self.catalog.get(p)).json() for p in paths};actual=(await self.report(a,b)).json()
        manifest=await backup.create_backup(self.source,recovery.PG_DUMP,self.directory)
        self.assertEqual(manifest['tables']['purchasing.store_vendor_items']['rows'],2)
        dsn=await self.target();verified=await backup.verify_restore(dsn,self.directory);self.assertEqual(verified['status'],'verified')
        client,pool=await self.restored_client(dsn)
        previous=server.db_pg._pool;server.db_pg._pool=pool
        try:
            for p in paths:self.assertEqual(before[p],(await self.catalog.get(p)).json())
        finally:server.db_pg._pool=previous
        restored=(await client.get('/api/pg/actual-inventory/berts/report',params={'opening':a['header']['id'],'closing':b['header']['id']})).json();self.assertEqual(actual,restored)
        (self.directory/'shared-catalog-api-verification.json').write_text(json.dumps(dict(status='verified',aliasesAndSupplierSettingsEqual=True,actualReportEqual=True,fixture='Invented sources only'),indent=2))
