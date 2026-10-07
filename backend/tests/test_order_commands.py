"""Synthetic order intent and races on disposable PostgreSQL, no supplier sends."""
import asyncio, os, unittest
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID,uuid4
import asyncpg,httpx
from pydantic import ValidationError
import server,order_commands as commands
import test_supplier_prices as prices
import test_shared_catalog as shared
import test_native_backup as recovery
import native_backup as backup


class OrderCommandValidationTests(unittest.TestCase):
    def test_finite_positive_units_and_unknown_price_are_distinct(self):
        base=dict(itemCode='food',controlNumber='F01',vendorSku='00001',qty='1',purchaseUnit='case')
        self.assertIsNone(commands.OrderLine(**base).unitCost)
        self.assertEqual(commands.OrderLine(**base,unitCost='0').unitCost,0)
        for key,value in [('qty','0'),('qty','NaN'),('qty','Infinity'),('unitCost','-1'),('unitCost','NaN')]:
            with self.assertRaises(ValidationError):commands.OrderLine(**{**base,key:value})


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PostgreSQL required')
class OrderCommandTests(unittest.IsolatedAsyncioTestCase):
    payload=prices.SupplierPriceTests.payload
    put=prices.SupplierPriceTests.put
    units=prices.SupplierPriceTests.units
    pair=prices.SupplierPriceTests.pair
    scope=prices.SupplierPriceTests.scope
    count=prices.SupplierPriceTests.count
    report=prices.SupplierPriceTests.report
    body=prices.SupplierPriceTests.body
    post=prices.SupplierPriceTests.post
    target=prices.SupplierPriceTests.target
    capture=prices.SupplierPriceTests.capture
    receipt=prices.SupplierPriceTests.receipt

    async def asyncSetUp(self):
        await prices.SupplierPriceTests.asyncSetUp(self)
        async with self.pool.acquire() as c:await c.execute((recovery.counts.native.ROOT/'migrations/20261006_order_commands.sql').read_text())
        self.command_flag=patch.dict(os.environ,{'ORDER_WORKFLOW_ENABLED':'true'});self.command_flag.start()
        token=server._token({'id':'synthetic-independent-owner','role':'owner','email':'owner@example.invalid'})
        self.other=httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://test',headers={'Authorization':'Bearer '+token})

    async def asyncTearDown(self):
        await self.other.aclose();self.command_flag.stop();await shared.SharedCatalogTests.asyncTearDown(self)

    def draft(self,price='99.100000000000000001',qty='2',**changes):
        return {**dict(vendor='Invented supplier',vendorId='synthetic_other',createdBy='Forged browser person',note='Reviewed invented food only',
            lines=[dict(itemCode='test_food',controlNumber='test_food',name='Untrusted display name',vendorSku='00001',qty=qty,purchaseUnit='case',unitCost=price)]),**changes}

    async def create(self,body=None,key=None,store='berts',client=None):
        return await (client or self.catalog).post(f'/api/pg/purchases/{store}/order-drafts',json=body or self.draft(),headers={'Idempotency-Key':key or str(uuid4())})

    async def command(self,po,action,key=None,client=None,note='Reviewed transition',version=None):
        return await (client or self.catalog).post(f"/api/pg/purchases/berts/orders/{po['id']}/commands",json={'action':action,'note':note},headers={'Idempotency-Key':key or str(uuid4()),'If-Match':str(po['orderVersion'] if version is None else version)})

    async def edit(self,po,body=None,key=None):
        return await self.catalog.put(f"/api/pg/purchases/berts/order-drafts/{po['id']}",json=body or self.draft(qty='3'),headers={'Idempotency-Key':key or str(uuid4()),'If-Match':str(po['orderVersion'])})

    async def saved(self,response):
        self.assertEqual(response.status_code,200,response.text);return response.json()['order']

    async def test_parallel_create_retry_preserves_exact_unknown_zero_and_accounting(self):
        _,a,b=await self.pair();before=(await self.report(a,b)).json();key=str(uuid4())
        responses=await asyncio.gather(self.create(self.draft(price=None),key),self.create(self.draft(price=None),key))
        a_po=await self.saved(responses[0]);b_po=await self.saved(responses[1]);self.assertEqual(a_po,b_po)
        self.assertIsNone(a_po['total']);self.assertIsNone(a_po['lines'][0]['unitCost']);self.assertEqual(a_po['createdBy'],'synthetic-catalog-reviewer')
        exact=await self.saved(await self.create());self.assertEqual(exact['lines'][0]['unitCost'],'99.100000000000000001')
        zero=await self.saved(await self.create(self.draft(price='0')));self.assertEqual(Decimal(zero['total']),0)
        self.assertEqual((await self.create(self.draft(price='5'),key)).status_code,409)
        self.assertEqual((await self.create(self.draft(price=None),key,client=self.other)).status_code,409)
        self.assertEqual(before,(await self.report(a,b)).json())
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT count(*) FROM purchasing.order_commands'),3)

    async def test_racing_edit_and_submit_cannot_change_submitted_content(self):
        po=await self.saved(await self.create())
        responses=await asyncio.gather(self.edit(po),self.command(po,'submit'))
        self.assertEqual(sorted(r.status_code for r in responses),[200,409],[r.text for r in responses])
        latest=(await self.catalog.get('/api/orders/berts')).json()[0]
        if latest['status']=='draft':latest=await self.saved(await self.command(latest,'submit'))
        self.assertEqual((await self.edit(latest)).status_code,409)
        self.assertEqual((await self.command(latest,'approve')).status_code,403)
        approved=await self.saved(await self.command(latest,'approve',client=self.other))
        self.assertEqual(approved['approvedBy'],'synthetic-independent-owner')
        self.assertEqual((await self.command(latest,'reject',client=self.other)).status_code,409)
        sent=await self.saved(await self.command(approved,'send'))
        self.assertEqual(sent['status'],'sent');self.assertGreater(sent['orderVersion'],approved['orderVersion'])
        async with self.pool.acquire() as c:
            with self.assertRaises(asyncpg.PostgresError):await c.execute('UPDATE purchase_order_lines SET qty=999 WHERE po_id=(SELECT id FROM purchase_orders WHERE ref=$1)',po['id'])

    async def test_approve_reject_race_and_missing_versions_do_not_duplicate_history(self):
        po=await self.saved(await self.create());submit_key=str(uuid4());pending=await self.saved(await self.command(po,'submit',submit_key))
        url=f"/api/pg/purchases/berts/orders/{po['id']}/commands"
        missing=await self.other.post(url,json={'action':'approve'},headers={'Idempotency-Key':str(uuid4())});self.assertEqual(missing.status_code,428)
        responses=await asyncio.gather(self.command(pending,'approve',client=self.other),self.command(pending,'reject',client=self.other))
        self.assertEqual(sorted(r.status_code for r in responses),[200,409])
        latest=(await self.catalog.get('/api/orders/berts')).json()[0]
        self.assertEqual(len(latest['history']),3)
        replay=await self.command(po,'submit',submit_key);self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json()['order']['status'],'pending')
        self.assertEqual(replay.json()['current_order'],{**latest,'restaurantId':'berts'})
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT count(*) FROM purchasing.order_commands'),3)

    async def test_archive_replay_retains_lines_and_reorder_keeps_canonical_identity(self):
        po=await self.saved(await self.create(self.draft(price=None)));key=str(uuid4())
        copied=await self.saved(await self.command(po,'reorder'));self.assertNotEqual(copied['id'],po['id'])
        self.assertEqual(copied['lines'][0]['itemCode'],'test_food');self.assertIsNone(copied['lines'][0]['unitCost'])
        archived=await self.saved(await self.command(po,'archive',key));self.assertTrue(archived['archivedAt'])
        self.assertEqual(await self.saved(await self.command(po,'archive',key)),archived)
        listed=(await self.catalog.get('/api/orders/berts')).json();self.assertEqual([p['id'] for p in listed],[copied['id']])
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM purchase_order_lines'),2)
            for sql in ('DELETE FROM purchase_orders WHERE ref=$1','UPDATE purchase_order_lines SET qty=0 WHERE po_id=(SELECT id FROM purchase_orders WHERE ref=$1)'):
                with self.assertRaises(asyncpg.PostgresError):await c.execute(sql,po['id'])
            with self.assertRaises(asyncpg.PostgresError):await c.execute('DELETE FROM purchasing.order_commands')

    async def test_global_supplier_metadata_versions_invalidate_store_snapshots_and_hold_retired_orders(self):
        async with self.pool.acquire() as c:
            await c.execute("UPDATE vendors SET order_email='supplier@example.invalid',rep_name='Invented rep',rep_phone='000-000-0000' WHERE id='synthetic_other'")
            supplier_version=await c.fetchval("SELECT catalog_version FROM vendors WHERE id='synthetic_other'")
        po=await self.saved(await self.create());old_body=await self.payload('berts')
        async with self.pool.acquire() as c:
            revision=await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'")
            rudds=await c.fetchval("SELECT revision FROM store_state WHERE store_id='rudds'") or 0
        body=dict(id='synthetic_other',name='Invented supplier',active=False)
        changed=await self.other.put('/api/pg/vendors/synthetic_other',json=body,headers={'If-Match':str(supplier_version)})
        self.assertEqual(changed.status_code,200,changed.text);self.assertEqual(changed.json()['catalog_version'],supplier_version+1)
        self.assertEqual(changed.json()['order_email'],'supplier@example.invalid');self.assertEqual(changed.json()['rep_name'],'Invented rep')
        self.assertEqual((await self.other.put('/api/pg/vendors/synthetic_other',json={**body,'active':True},headers={'If-Match':str(supplier_version)})).status_code,409)
        self.assertEqual((await self.put(old_body,revision,'berts')).status_code,409)
        self.assertEqual((await self.command(po,'submit')).status_code,422)
        async with self.pool.acquire() as c:self.assertGreater(await c.fetchval("SELECT revision FROM store_state WHERE store_id='rudds'"),rudds)
        self.assertEqual((await self.catalog.put('/api/pg/vendors/synthetic_other',json=body,headers={'If-Match':str(supplier_version+1)})).status_code,403)

    async def test_installed_workflow_holds_legacy_and_flag_off_writes_before_side_effects(self):
        po=await self.saved(await self.create())
        for method,url,body in [('post','/api/orders/berts',self.draft()),('put','/api/orders/berts/'+po['id'],self.draft()),('delete','/api/orders/berts/'+po['id'],None),('post',f"/api/orders/berts/{po['id']}/email",{'email':'synthetic@example.invalid'})]:
            response=await self.catalog.request(method,url,json=body);self.assertEqual(response.status_code,409,response.text)
        with patch.dict(os.environ,{'ORDER_WORKFLOW_ENABLED':'false'}):
            self.assertEqual((await self.create()).status_code,503)
            self.assertEqual((await self.catalog.post('/api/orders/berts',json=self.draft())).status_code,409)
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT count(*) FROM purchase_orders'),1)

    async def test_native_receiving_advances_order_version_and_preserves_purchase_cost(self):
        self.assertEqual((await self.units())[0].status_code,200)
        po=await self.saved(await self.create());po=await self.saved(await self.command(po,'submit'));po=await self.saved(await self.command(po,'approve',client=self.other));po=await self.saved(await self.command(po,'send'))
        doc=await self.receipt()
        async with self.pool.acquire() as c:
            line=await c.fetchval('SELECT id FROM purchase_order_lines WHERE po_id=(SELECT id FROM purchase_orders WHERE ref=$1)',po['id'])
            cost=await c.fetchval('SELECT sum(inventory_cost_amount) FROM purchasing.actual_purchase_facts')
        review=dict(document_version_id=doc['id'],lines=[dict(source_line_id=l['id'],po_line_id=str(line),verified=True) for l in doc['lines']],complete_order=True,variances_reviewed=True,note='Reviewed invented delivery')
        preview=await self.client.post(f"/api/pg/purchases/berts/orders/{po['id']}/receipt-preview",json=review);self.assertEqual(preview.status_code,200,preview.text)
        confirm=await self.client.post(f"/api/pg/purchases/berts/orders/{po['id']}/receipts",json={**review,'expected_plan_hash':preview.json()['planHash']},headers={'Idempotency-Key':str(uuid4())})
        self.assertEqual(confirm.status_code,200,confirm.text)
        latest=(await self.catalog.get('/api/orders/berts')).json()[0];self.assertEqual(latest['status'],'received');self.assertGreater(latest['orderVersion'],po['orderVersion'])
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT sum(inventory_cost_amount) FROM purchasing.actual_purchase_facts'),cost)

    async def test_order_commands_and_versions_survive_whole_sql_restore(self):
        po=await self.saved(await self.create(self.draft(price=None)));await self.command(po,'submit')
        before=(await self.catalog.get('/api/orders/berts')).json()
        manifest=await backup.create_backup(self.source,recovery.PG_DUMP,self.directory);self.assertEqual(manifest['tables']['purchasing.order_commands']['rows'],2)
        dsn=await self.target();self.assertEqual((await backup.verify_restore(dsn,self.directory))['status'],'verified')
        pool=await asyncpg.create_pool(dsn,min_size=1,max_size=2,init=recovery.db_pg._init_connection)
        old=server.db_pg._pool;server.db_pg._pool=pool
        try:self.assertEqual((await self.catalog.get('/api/orders/berts')).json(),before)
        finally:server.db_pg._pool=old;await pool.close()
