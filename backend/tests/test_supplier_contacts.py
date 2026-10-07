"""Invented supplier contacts on disposable PostgreSQL; no mail delivery."""
import asyncio, os, unittest
from unittest.mock import patch
from uuid import uuid4
import asyncpg
from pydantic import ValidationError
import server,supplier_contacts as contacts,native_backup as backup
import test_order_commands as orders
import test_native_backup as recovery


class SupplierContactValidationTests(unittest.TestCase):
    def test_contact_validation_and_dependencies(self):
        base=dict(order_email=' orders@example.invalid ',expected_vendor_version=1,note=' Reviewed ')
        self.assertEqual(contacts.SaveContact(**base).order_email,'orders@example.invalid')
        self.assertEqual(contacts.SaveContact(**{**base,'order_email':''}).order_email,'')
        for changes in ({'note':' '},{'order_email':'a@b.invalid\r\nBcc: hidden@example.invalid'},{'order_email':'a@b.invalid,'},{'order_email':'a..b@example.invalid'},{'order_email':None},{'expected_vendor_version':0},{'expected_vendor_version':True},{'legacy_vendor':'Old supplier'},{'legacy_vendor':'Old supplier','verified':'true'},{'vendor_id':'forged'}):
            with self.assertRaises(ValidationError):contacts.SaveContact(**{**base,**changes})
        with patch.dict(os.environ,{'SUPPLIER_CONTACTS_ENABLED':'true','ORDER_WORKFLOW_ENABLED':'false'}):
            with self.assertRaises(server.HTTPException):contacts.enabled()


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PostgreSQL required')
class SupplierContactTests(unittest.IsolatedAsyncioTestCase):
    target=orders.OrderCommandTests.target
    async def asyncSetUp(self):
        await orders.OrderCommandTests.asyncSetUp(self)
        async with self.pool.acquire() as c:
            await c.execute('''CREATE TABLE IF NOT EXISTS public.store_vendor_contacts(store_id text NOT NULL REFERENCES stores(id),vendor text NOT NULL,order_email text NOT NULL DEFAULT '',updated_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(store_id,vendor));
                INSERT INTO store_vendor_contacts(store_id,vendor,order_email) VALUES('berts','Invented supplier','legacy@example.invalid'),('berts','Unmatched supplier','bad legacy text');''')
            await c.execute((recovery.counts.native.ROOT/'migrations/20261006_supplier_contacts.sql').read_text())
        self.contact_flag=patch.dict(os.environ,{'SUPPLIER_CONTACTS_ENABLED':'true'});self.contact_flag.start()

    async def asyncTearDown(self):
        self.contact_flag.stop();await orders.OrderCommandTests.asyncTearDown(self)

    async def read_contacts(self,store='berts'):
        response=await self.catalog.get(f'/api/pg/purchases/{store}/supplier-contacts')
        self.assertEqual(response.status_code,200,response.text);return response.json()

    async def edit_contact(self,email='orders@example.invalid',version=0,key=None,store='berts',vendor='synthetic_other',**changes):
        return await self.catalog.put(f'/api/pg/purchases/{store}/supplier-contacts/{vendor}',json=dict(order_email=email,expected_vendor_version=1,note='Reviewed invented contact',**changes),headers={'If-Match':str(version),'Idempotency-Key':key or str(uuid4())})

    async def test_contact_parallel_retry_stale_edits_and_exact_replay(self):
        key=str(uuid4());responses=await asyncio.gather(self.edit_contact(key=key),self.edit_contact(key=key))
        for r in responses:self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(responses[0].json()['contact'],responses[1].json()['contact'])
        raced=await asyncio.gather(self.edit_contact(email='first@example.invalid',version=1),self.edit_contact(email='second@example.invalid',version=1))
        self.assertEqual(sorted(r.status_code for r in raced),[200,409])
        replay=await self.edit_contact(key=key);self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json()['contact']['version'],1);self.assertEqual(replay.json()['current_contact']['version'],2)
        self.assertEqual((await self.edit_contact(email='wrong@example.invalid',key=key)).status_code,409)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM purchasing.supplier_contact_commands'),2)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM purchasing.supplier_contact_events'),2)
            self.assertEqual(await c.fetchval('SELECT actor FROM purchasing.supplier_contact_events LIMIT 1'),'synthetic-catalog-reviewer')

    async def test_legacy_contacts_are_preserved_and_explicitly_resolved_once(self):
        before=await self.read_contacts();self.assertEqual(len(before['legacy_contacts']),2)
        self.assertTrue(all(c['version']==0 for c in before['contacts']))
        first=await self.edit_contact(legacy_vendor='Invented supplier',verified=True);self.assertEqual(first.status_code,200,first.text)
        self.assertEqual((await self.edit_contact(version=1,legacy_vendor='Invented supplier',verified=True)).status_code,409)
        self.assertEqual(len((await self.read_contacts())['legacy_contacts']),1)
        self.assertEqual((await self.edit_contact(store='rudds',legacy_vendor='Unmatched supplier',verified=True)).status_code,404)
        # An invalid legacy address may be corrected only through an explicit reviewed mapping.
        corrected=await self.edit_contact(version=1,legacy_vendor='Unmatched supplier',verified=True)
        self.assertEqual(corrected.status_code,200,corrected.text)
        async with self.pool.acquire() as c:
            raw=await c.fetchval("SELECT raw_record FROM purchasing.legacy_supplier_contacts WHERE vendor='Unmatched supplier'")
            self.assertEqual(raw['order_email'],'bad legacy text')
            self.assertEqual(await c.fetchval('SELECT count(*) FROM purchasing.legacy_contact_resolutions'),2)
            for sql in ('DELETE FROM purchasing.supplier_contact_events','DELETE FROM purchasing.legacy_supplier_contacts','DELETE FROM purchasing.legacy_contact_resolutions','DELETE FROM purchasing.supplier_contact_commands','DELETE FROM purchasing.store_supplier_contacts',"UPDATE purchasing.store_supplier_contacts SET order_email='unreviewed@example.invalid'"):
                with self.assertRaises(asyncpg.PostgresError):await c.execute(sql)

    async def test_contact_clear_and_store_revision_are_independent_of_accounting(self):
        async with self.pool.acquire() as c:
            b=await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'") or 0;r=await c.fetchval("SELECT revision FROM store_state WHERE store_id='rudds'")
            before=await c.fetchval('SELECT count(*) FROM purchasing.actual_purchase_facts')
        self.assertEqual((await self.edit_contact()).status_code,200)
        self.assertEqual((await self.edit_contact(email='',version=1)).status_code,200)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'"),b+2)
            self.assertEqual(await c.fetchval("SELECT revision FROM store_state WHERE store_id='rudds'"),r)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM purchasing.actual_purchase_facts'),before)
            self.assertEqual(await c.fetchval('SELECT order_email FROM purchasing.store_supplier_contacts'),'')
        self.assertEqual((await self.edit_contact(store='rudds')).status_code,200)
        self.assertEqual(len((await self.read_contacts('rudds'))['legacy_contacts']),0)

    async def test_renaming_keeps_identity_and_stale_vendor_versions_are_held(self):
        self.assertEqual((await self.edit_contact()).status_code,200)
        response=await self.other.put('/api/pg/vendors/synthetic_other',json={'id':'synthetic_other','name':'Renamed invented supplier'},headers={'If-Match':'1'})
        self.assertEqual(response.status_code,200,response.text)
        row=next(c for c in (await self.read_contacts())['contacts'] if c['vendor_id']=='synthetic_other')
        self.assertEqual(row['vendor_name'],'Renamed invented supplier');self.assertEqual(row['order_email'],'orders@example.invalid')
        self.assertEqual((await self.edit_contact(version=1)).status_code,409)
        response=await self.catalog.put('/api/pg/purchases/berts/supplier-contacts/synthetic_other',json={'order_email':'changed@example.invalid','note':'Reviewed','expected_vendor_version':2},headers={'If-Match':'1','Idempotency-Key':str(uuid4())})
        self.assertEqual(response.status_code,200,response.text)

    async def test_missing_versions_and_legacy_flag_off_writes_are_held(self):
        missing=await self.catalog.put('/api/pg/purchases/berts/supplier-contacts/synthetic_other',json={'order_email':'','note':'Reviewed','expected_vendor_version':1},headers={'Idempotency-Key':str(uuid4())})
        self.assertEqual(missing.status_code,428)
        for verb in ('get','put'):
            response=await self.catalog.request(verb,'/api/vendor-contacts/berts',json={'vendor':'Invented supplier','orderEmail':'overwrite@example.invalid'} if verb=='put' else None)
            self.assertEqual(response.status_code,409,response.text)
        with patch.dict(os.environ,{'SUPPLIER_CONTACTS_ENABLED':'false'}):
            self.assertEqual((await self.edit_contact()).status_code,503)
            self.assertEqual((await self.catalog.put('/api/vendor-contacts/berts',json={'vendor':'Invented supplier','orderEmail':'overwrite@example.invalid'})).status_code,409)
        async with self.pool.acquire() as c:
            with self.assertRaises(asyncpg.PostgresError):await c.execute("UPDATE store_vendor_contacts SET order_email='overwrite@example.invalid'")
            self.assertEqual(await c.fetchval('SELECT count(*) FROM purchasing.supplier_contact_events'),0)

    async def test_supplier_contact_history_and_mapping_survive_whole_sql_restore(self):
        key=str(uuid4());self.assertEqual((await self.edit_contact(key=key,legacy_vendor='Invented supplier',verified=True)).status_code,200)
        self.assertEqual((await self.edit_contact(email='',version=1)).status_code,200)
        before=await self.read_contacts();manifest=await backup.create_backup(self.source,recovery.PG_DUMP,self.directory)
        self.assertEqual(manifest['tables']['purchasing.supplier_contact_events']['rows'],2)
        dsn=await self.target();self.assertEqual((await backup.verify_restore(dsn,self.directory))['status'],'verified')
        pool=await asyncpg.create_pool(dsn,min_size=1,max_size=2,init=recovery.db_pg._init_connection)
        old=server.db_pg._pool;server.db_pg._pool=pool
        try:
            self.assertEqual(await self.read_contacts(),before)
            replay=await self.edit_contact(key=key,legacy_vendor='Invented supplier',verified=True)
            self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(replay.json()['current_contact']['version'],2)
        finally:server.db_pg._pool=old;await pool.close()
