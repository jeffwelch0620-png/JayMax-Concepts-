"""Synthetic-only integration tests. Requires an explicitly disposable local PG.

NATIVE_PURCHASE_TEST_DSN must use loopback and a native_purchase_test_* database.
No real supplier files, credentials or operational data are read.
"""
import asyncio
import csv
import io
import os
import sys
from pathlib import Path
import unittest
from decimal import Decimal
from uuid import UUID, uuid4
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException

import db_pg
import purchase_api as purchases
from purchase_parser import FIELD_MAP, parse_csv, typed, document_totals

def sample(vendor='PFG', number='TEST-001', amounts=('40.00',), overrides=None, extra=False):
    specs = [s for s in FIELD_MAP if s['vendor'] == vendor]
    headers = [s['header'] for s in specs] + (['FutureField'] if extra else [])
    rows = []
    total = sum(float(v) for v in amounts)
    for index, amount in enumerate(amounts):
        cells = []
        for spec in specs:
            target = spec['target'].split('.')[-1]
            value = '0' if spec['type'] == 'numeric' else '2026-10-01' if spec['type'] == 'date' else ''
            values = {'document_number': number, 'document_type_raw': 'Invoice',
                'customer_number': '00123', 'vendor_branch_reference': 'TEST-BRANCH', 'account_number': '00008',
                'extended_amount_source': amount, 'subtotal_source': str(total), 'total_source': str(total + 3),
                'fees_source': '1', 'tax_source': '2', 'net_after_adjustment_source': str(total),
                'net_before_adjustment_source': str(total), 'vendor_sku_snapshot': f'000{index+1}',
                'description_snapshot': f'Synthetic food {index+1}', 'shipped_quantity_source': '2',
                'ordered_quantity_source': '2', 'pack_description_raw': '4 / 5 LB',
                'postal_code': '00123', 'phone_text': '0005551234', 'gtin_text': '000000000001',
                'address_line_1': 'FIRST STREET', 'address_line_2': 'SECOND STREET'}
            value = values.get(target, value)
            value = (overrides or {}).get(target, value)
            cells.append(value)
        rows.append(cells + (['unmapped, retained "exactly"'] if extra else []))
    output = io.StringIO(newline=''); writer = csv.writer(output); writer.writerow(headers); writer.writerows(rows)
    return output.getvalue().encode('utf-8'), headers, rows


class ParserTests(unittest.TestCase):
    def test_total_reconciliation_does_not_round_large_exact_amounts(self):
        amount=Decimal('9999999999999999999999999999')
        header={'total_source':Decimal('9999999999999999999999999999.01'),
                'fees_source':Decimal(0),'tax_source':Decimal(0),'discount_source':Decimal(0)}
        result=document_totals(header,[{'extended_amount_source':amount},{'extended_amount_source':Decimal('.01')}])
        self.assertEqual(result['status'],'balanced');self.assertEqual(result['lineTotal'],header['total_source'])
        header['total_source']=amount
        self.assertEqual(document_totals(header,[{'extended_amount_source':amount},{'extended_amount_source':Decimal('.01')}])['difference'],Decimal('-.01'))
    def test_complete_field_contract_and_duplicate_streets(self):
        self.assertEqual(len(FIELD_MAP), 97)
        for vendor in ('PFG', 'US Foods'):
            source, headers, rows = sample(vendor, extra=True)
            parsed = parse_csv(source)
            self.assertEqual(parsed['headers'], headers)
            self.assertEqual(parsed['rows'][0]['values'], rows[0])
            doc = parsed['documents'][0]
            self.assertFalse(doc['errors'])
            if vendor == 'US Foods':
                self.assertEqual(doc['parties']['bill_to']['address_line_1'], 'FIRST STREET')
                self.assertEqual(doc['parties']['bill_to']['address_line_2'], 'SECOND STREET')
            self.assertEqual(doc['lines'][0]['fields']['vendor_sku_snapshot'], '0001')

    def test_reordered_rows_reuse_fingerprint_but_keep_multiplicity(self):
        source, headers, rows = sample(amounts=('40.00', '40.00'))
        out = io.StringIO(newline=''); w=csv.writer(out); w.writerow(headers); w.writerows(rows[::-1])
        self.assertEqual(parse_csv(source)['documents'][0]['fingerprint'], parse_csv(out.getvalue().encode())['documents'][0]['fingerprint'])
        self.assertEqual(len(parse_csv(source)['documents'][0]['lines']), 2)
        repeated = io.StringIO(newline=''); w = csv.writer(repeated); w.writerow(headers); w.writerows([rows[0], rows[0]])
        identical_lines = parse_csv(repeated.getvalue().encode())['documents'][0]['lines']
        self.assertEqual(len(identical_lines), 2)
        self.assertEqual([l['fields']['vendor_sku_snapshot'] for l in identical_lines], ['0001','0001'])

    def test_blank_invalid_and_nonfinite_are_not_zero(self):
        self.assertIsNone(typed('', 'numeric'))
        for value in ('NaN', 'Infinity', '1e5', '1,2', '12abc'):
            with self.assertRaises(ValueError): typed(value, 'numeric')


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PG DSN required')
class PurchaseIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        dsn = os.environ['NATIVE_PURCHASE_TEST_DSN']
        from urllib.parse import urlparse
        uri = urlparse(dsn)
        if uri.hostname not in ('127.0.0.1','localhost') or not uri.path.startswith('/native_purchase_test_'):
            raise RuntimeError('Refusing non-disposable/non-loopback test database')
        self.db = f'native_purchase_test_{uuid4().hex}'
        self.admin = await asyncpg.connect(dsn)
        await self.admin.execute(f'CREATE DATABASE {self.db}')
        self.pool = await asyncpg.create_pool(dsn.rsplit('/', 1)[0] + '/' + self.db, min_size=1,max_size=5,init=db_pg._init_connection)
        async with self.pool.acquire() as conn:
            await conn.execute((ROOT/'supabase/schema.sql').read_text(encoding='utf-8'))
            await conn.execute((ROOT/'migrations/20261004_native_purchase_import.sql').read_text(encoding='utf-8'))
            await conn.execute("INSERT INTO stores(id,name) VALUES('berts','Test Berts'),('rudds','Test Rudds')")
            await conn.execute("INSERT INTO items(code,name,base_unit) VALUES('test_food','Synthetic Food','portion'),('other_food','Other Food','portion')")
            await conn.execute("INSERT INTO store_items(store_id,item_code,count_unit,base_per_count_unit) VALUES('berts','test_food','portion',1),('berts','other_food','portion',1)")
        app=FastAPI()
        def check(store):
            if store not in ('berts','rudds'):raise HTTPException(404,'Unknown store')
        def actor(request,store,write):
            if request.headers.get('authorization')!='Bearer synthetic-manager':raise HTTPException(401,'Authentication required')
            return 'synthetic-manager'
        app.include_router(purchases.create_router(lambda:self.pool,check,actor))
        self.flag=patch.dict(os.environ,{'PURCHASE_IMPORT_ENABLED':'true'});self.flag.start()
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers={'Authorization':'Bearer synthetic-manager'})

    async def asyncTearDown(self):
        await self.client.aclose();self.flag.stop();await self.pool.close()
        await self.admin.execute(f'DROP DATABASE {self.db}');await self.admin.close()

    async def capture(self, vendor='PFG', number=None, amounts=('40.00',), overrides=None, extra=False, key=None):
        source,headers,rows=sample(vendor,number or uuid4().hex,amounts,overrides,extra)
        result=await self.client.post('/api/pg/purchases/berts/files',files={'file':('synthetic.csv',source,'text/csv')},headers={'Idempotency-Key':key or str(uuid4())})
        self.assertEqual(result.status_code,200,result.text)
        return result.json(),source,headers,rows

    def body(self, document, **patches):
        return {'confirmed_currency':'USD','received_date':'2026-10-04','lines':[{'line_id':line['id'],'classification':'food','movement_kind':'receipt',
            'item_code':'test_food','base_unit':'lb','received_quantity':'2','received_unit':'case',
            'base_units_per_received_unit':'20','verified':True,'note':'Synthetic confirmed mapping',**patches}
            for line in document['lines']]}

    async def post(self, doc, body=None, key=None):
        return await self.client.post(f"/api/pg/purchases/berts/documents/{doc['id']}/post",json=body or self.body(doc),headers={'Idempotency-Key':key or str(uuid4())})

    async def test_capture_roundtrip_all_raw_and_typed_fields(self):
        for vendor in ('PFG','US Foods'):
            file,source,headers,rows=await self.capture(vendor,extra=True)
            result=await self.client.get(f"/api/pg/purchases/berts/files/{file['id']}/source")
            self.assertEqual(result.content,source)
            result=await self.client.get(f"/api/pg/purchases/berts/files/{file['id']}/rows")
            self.assertEqual(result.json()['headers'],headers)
            self.assertEqual(result.json()['rows'][0]['raw_values'],rows[0])
            doc=file['documents'][0]
            async with self.pool.acquire() as conn:
                parties={r['party_role']:dict(r) for r in await conn.fetch('SELECT * FROM purchasing.document_parties WHERE document_version_id=$1',UUID(doc['id']))}
            for spec,raw in zip([s for s in FIELD_MAP if s['vendor']==vendor],rows[0]):
                parts=spec['target'].split('.')
                target=doc['header'] if parts[0]=='documents' else doc['lines'][0] if parts[0]=='lines' else parties[parts[1]]
                self.assertEqual(purchases.serial(target[parts[-1]]),purchases.serial(typed(raw,spec['type'])),spec['header'])

    async def test_received_date_cost_fee_tax_and_track_isolation(self):
        file,*_=await self.capture();doc=file['documents'][0]
        result=await self.post(doc);self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['document']['status'],'posted')
        async with self.pool.acquire() as conn:
            fact=await conn.fetchrow('SELECT * FROM purchasing.actual_purchase_facts')
            self.assertEqual(str(fact['base_quantity']),'40')
            self.assertEqual(str(fact['inventory_cost_amount']),'40.00')
            self.assertEqual(str(fact['inventory_record_date']),'2026-10-04')
            for table in ('invoices','prep_logs','prep_stock','sales_periods'):
                # Some baseline state is JSON; assert only real tables in this snapshot.
                if await conn.fetchval('SELECT to_regclass($1)',table):self.assertEqual(await conn.fetchval(f'SELECT count(*) FROM {table}'),0)

    async def test_retry_and_changed_payload_do_not_duplicate(self):
        file,*_=await self.capture();doc=file['documents'][0];key=str(uuid4());body=self.body(doc)
        a,b=await asyncio.gather(self.post(doc,body,key),self.post(doc,body,key))
        self.assertEqual(a.status_code,200,a.text);self.assertEqual(b.status_code,200,b.text)
        self.assertEqual(a.json()['batchId'],b.json()['batchId'])
        body['received_date']='2026-10-05';self.assertEqual((await self.post(doc,body,key)).status_code,409)
        async with self.pool.acquire() as conn:self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.posting_batches'),1)

    async def test_missing_received_date_and_fixed_unit_changes_are_rejected(self):
        file,*_=await self.capture();doc=file['documents'][0];body=self.body(doc);body['received_date']=None
        self.assertEqual((await self.post(doc,body)).status_code,422)
        self.assertEqual((await self.post(doc)).status_code,200)
        file,*_=await self.capture();doc=file['documents'][0]
        self.assertEqual((await self.post(doc,self.body(doc,base_unit='each'))).status_code,409)
        async with self.pool.acquire() as conn:self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.posting_batches'),1)

    async def test_superseded_unposted_versions_and_legacy_reentry_are_rejected(self):
        number=uuid4().hex;a,*_=await self.capture(number=number);old=a['documents'][0]
        b,*_=await self.capture(number=number,amounts=('45',));latest=b['documents'][0]
        self.assertEqual((await self.post(old)).status_code,409)
        self.assertEqual((await self.post(latest)).status_code,200)
        async with self.pool.acquire() as conn:
            with self.assertRaises(asyncpg.RaiseError):
                await conn.execute("INSERT INTO invoices(store_id,vendor_id,invoice_number,invoice_date,total) VALUES('berts','pfg',$1,'2026-10-01',45)",number)

    async def test_credit_cannot_link_a_different_vendor_receipt(self):
        file,*_=await self.capture();original=file['documents'][0];self.assertEqual((await self.post(original)).status_code,200)
        file,*_=await self.capture('US Foods',amounts=('-5',),overrides={'document_type_raw':'Credit'})
        doc=file['documents'][0]
        body=self.body(doc,movement_kind='price_credit',received_quantity=None,base_units_per_received_unit=None,
            original_line_id=original['lines'][0]['id'],movement_date='2026-10-06')
        self.assertEqual((await self.post(doc,body)).status_code,409)

    async def test_disabled_or_mongo_mode_cannot_capture_purchases(self):
        for env in ({'PURCHASE_IMPORT_ENABLED':'false'},{'USE_PG':'false'}):
            with patch.dict(os.environ,env):
                result=await self.client.post('/api/pg/purchases/berts/files',files={'file':('synthetic.csv',sample()[0],'text/csv')},headers={'Idempotency-Key':str(uuid4())})
                self.assertEqual(result.status_code,503)
        async with self.pool.acquire() as conn:self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.import_files'),0)

    async def test_failed_second_line_rolls_back_mappings_units_and_batch(self):
        file,*_=await self.capture(amounts=('40','30'));doc=file['documents'][0];body=self.body(doc)
        body['lines'][1]['item_code']='unregistered_item'
        self.assertEqual((await self.post(doc,body)).status_code,422)
        async with self.pool.acquire() as conn:
            for table in ('mapping_decisions','item_bases','posting_batches','posting_lines','reconciliation_checks'):
                self.assertEqual(await conn.fetchval(f'SELECT count(*) FROM purchasing.{table}'),0,table)

    async def test_held_totals_and_invalid_fields_never_post(self):
        for overrides in ({'total_source':'44.23'},{'extended_amount_source':'bad'},{'tax_source':''},{'discount_source':'1','total_source':'42'}):
            file,*_=await self.capture(overrides=overrides);doc=file['documents'][0]
            self.assertEqual(doc['status'],'held');self.assertEqual((await self.post(doc)).status_code,409)

    async def test_changed_version_held_after_original_posted(self):
        number=uuid4().hex;file,*_=await self.capture(number=number);doc=file['documents'][0]
        self.assertEqual((await self.post(doc)).status_code,200)
        newer,*_=await self.capture(number=number,amounts=('45',))
        self.assertEqual(newer['documents'][0]['status'],'held')
        self.assertEqual((await self.post(newer['documents'][0])).status_code,409)

    async def test_account_or_branch_drift_does_not_bypass_duplicate_guard(self):
        number=uuid4().hex;file,*_=await self.capture(number=number);doc=file['documents'][0]
        self.assertEqual((await self.post(doc)).status_code,200)
        drifted,*_=await self.capture(number=number,overrides={'vendor_branch_reference':'DIFFERENT-BRANCH'})
        self.assertEqual(drifted['documents'][0]['status'],'held')
        self.assertEqual((await self.post(drifted['documents'][0])).status_code,409)

    async def test_upload_key_reuse_and_overlapping_files(self):
        number=uuid4().hex;key=str(uuid4());a,source,headers,rows=await self.capture(number=number,amounts=('40','30'),key=key)
        b,*_=await self.capture(number=number,amounts=('40','30'),key=key);self.assertEqual(a['id'],b['id'])
        out=io.StringIO(newline='');w=csv.writer(out);w.writerow(headers);w.writerows(rows[::-1])
        result=await self.client.post('/api/pg/purchases/berts/files',files={'file':('reordered.csv',out.getvalue().encode(),'text/csv')},headers={'Idempotency-Key':str(uuid4())})
        self.assertEqual(result.status_code,200,result.text);self.assertEqual(result.json()['documents'][0]['id'],a['documents'][0]['id'])
        conflict=await self.client.post('/api/pg/purchases/berts/files',files={'file':('different.csv',b'not same','text/csv')},headers={'Idempotency-Key':key})
        self.assertEqual(conflict.status_code,409)

    async def test_unknown_format_retained_and_store_boundary(self):
        source=b'Unknown,Future\r\n"blank",00123\r\n'
        result=await self.client.post('/api/pg/purchases/berts/files',files={'file':('unknown.csv',source,'text/csv')},headers={'Idempotency-Key':str(uuid4())})
        self.assertEqual(result.status_code,200);file=result.json();self.assertTrue(file['parse_errors']);self.assertFalse(file['documents'])
        self.assertEqual((await self.client.get(f"/api/pg/purchases/rudds/files/{file['id']}/source")).status_code,404)

    async def test_parser_crash_keeps_original_and_retry_completes(self):
        source,*_=sample(number='parser-retry');key=str(uuid4())
        with patch('purchase_api.parse_csv',side_effect=RuntimeError('synthetic parser failure')):
            with self.assertRaises(RuntimeError):await self.client.post('/api/pg/purchases/berts/files',files={'file':('retry.csv',source,'text/csv')},headers={'Idempotency-Key':key})
        async with self.pool.acquire() as conn:self.assertEqual(await conn.fetchval('SELECT source_bytes FROM purchasing.import_files'),source)
        result=await self.client.post('/api/pg/purchases/berts/files',files={'file':('retry.csv',source,'text/csv')},headers={'Idempotency-Key':key})
        self.assertEqual(result.status_code,200);self.assertEqual(len(result.json()['documents']),1)

    async def test_closed_period_and_legacy_collision(self):
        file,*_=await self.capture();doc=file['documents'][0]
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO reporting_periods(store_id,period_start,period_end,status,ref) VALUES('berts','2026-10-01','2026-10-31','closed','closed-test')")
        self.assertEqual((await self.post(doc)).status_code,409)
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM reporting_periods")
            await conn.execute("INSERT INTO invoices(store_id,vendor_id,invoice_number,invoice_date,total) VALUES('berts','pfg',$1,'2026-10-01',40)",doc['header']['document_number'])
        self.assertEqual((await self.post(doc)).status_code,409)

    async def test_credit_return_nonfood_and_immutable_facts(self):
        file,*_=await self.capture();doc=file['documents'][0];self.assertEqual((await self.post(doc)).status_code,200)
        credit,*_=await self.capture(amounts=('-5',),overrides={'document_type_raw':'Credit Memo'})
        cd=credit['documents'][0]
        body=self.body(cd,movement_kind='price_credit',received_quantity=None,base_units_per_received_unit=None,original_line_id=doc['lines'][0]['id'],movement_date='2026-10-06')
        result=await self.post(cd,body);self.assertEqual(result.status_code,200,result.text)
        returned,*_=await self.capture(amounts=('-20',),overrides={'document_type_raw':'Credit'})
        rd=returned['documents'][0];body=self.body(rd,movement_kind='physical_return',received_quantity='-1',movement_date='2026-10-07')
        self.assertEqual((await self.post(rd,body)).status_code,200)
        nonfood,*_=await self.capture();nd=nonfood['documents'][0]
        body=self.body(nd,classification='nonfood',movement_kind='no_inventory',received_quantity=None,base_units_per_received_unit=None,item_code=None,base_unit=None)
        self.assertEqual((await self.post(nd,body)).status_code,200)
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT sum(base_quantity) FROM purchasing.actual_purchase_facts'),20)
            self.assertEqual(await conn.fetchval('SELECT sum(inventory_cost_amount) FROM purchasing.actual_purchase_facts'),15)
            with self.assertRaises(asyncpg.RaiseError):await conn.execute('UPDATE purchasing.document_lines SET extended_amount_source=99')

    async def test_actual_server_role_location_and_legacy_writer_guard(self):
        # Exercise the app's existing signed-token and middleware contract.
        import server
        original=server.db_pg._pool;server.db_pg._pool=self.pool
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://test') as client:
                for role,locations,store,expected in [('staff',['berts'],'berts',403),('readonly',['berts'],'berts',403),('manager',['rudds'],'berts',403),('manager',['berts'],'berts',200),('owner',[],'berts',200)]:
                    token=server._token({'id':'synthetic-user','email':'test@example.invalid','role':role,'locations':locations})
                    result=await client.post(f'/api/pg/purchases/{store}/files',files={'file':('synthetic.csv',sample(number=uuid4().hex)[0],'text/csv')},headers={'Authorization':f'Bearer {token}','Idempotency-Key':str(uuid4())})
                    self.assertEqual(result.status_code,expected,result.text)
                token=server._token({'id':'synthetic-user','email':'test@example.invalid','role':'owner','locations':[]})
                result=await client.post('/api/pg/invoices/berts',json={'vendor_id':'pfg','invoice_number':'legacy','invoice_date':'2026-10-04','lines':[]},headers={'Authorization':f'Bearer {token}'})
                self.assertEqual(result.status_code,410,result.text)
        finally:server.db_pg._pool=original
