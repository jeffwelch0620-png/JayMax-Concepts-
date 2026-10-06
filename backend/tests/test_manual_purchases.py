"""Invented manual receipts only; shares disposable database safety checks."""
import asyncio
import json
import os
import unittest
from decimal import Decimal
from uuid import UUID,uuid4

import asyncpg
import native_backup as backup
import test_native_backup as recovery


def record(number='MANUAL-TEST',amount='40',**patches):
    return {'vendor_id':'synthetic_other','document_type':'invoice',
        'documents':{'document_number':number,'invoice_date':'2026-09-29','subtotal_source':amount,
                     'fees_source':'1','tax_source':'2','discount_source':'0','total_source':str(Decimal(amount)+3)},
        'parties':{'bill_to':{'name_snapshot':'Synthetic Buyer','address_line_1':'001 First Street','address_line_2':''}},
        'lines':[{'fields':{'vendor_sku_snapshot':'00001','description_snapshot':'Invented manual food',
                    'shipped_quantity_source':'2','extended_amount_source':amount,'pack_description_raw':'4 / 5 LB'},
                  'extra_fields':[{'label':'Future batch code','value':'00045'},{'label':'Repeated','value':''},{'label':'Repeated','value':'line\nsecond'}]}],
        'extra_fields':[{'label':'Unmapped invoice note','value':'retained, "exactly"'}],
        'attachment_ids':[],'verified_source':True,'evidence_note':'Invented test record; branch/customer not stated',**patches}


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PG DSN required')
class ManualPurchaseTests(unittest.IsolatedAsyncioTestCase):
    # Reuse setup helpers without inheriting/re-running their test methods.
    asyncTearDown=recovery.NativeBackupTests.asyncTearDown
    target=recovery.NativeBackupTests.target
    restored_client=recovery.NativeBackupTests.restored_client
    body=recovery.NativeBackupTests.body
    post=recovery.NativeBackupTests.post
    pair=recovery.NativeBackupTests.pair
    scope=recovery.NativeBackupTests.scope
    count=recovery.NativeBackupTests.count
    report=recovery.NativeBackupTests.report
    close=recovery.NativeBackupTests.close
    capture=recovery.NativeBackupTests.capture
    plan=recovery.NativeBackupTests.plan
    correct=recovery.NativeBackupTests.correct
    reopen=recovery.NativeBackupTests.reopen

    async def asyncSetUp(self):
        await recovery.NativeBackupTests.asyncSetUp(self)
        async with self.pool.acquire() as conn:
            await conn.execute((recovery.counts.native.ROOT/'migrations/20261005_manual_purchase_sources.sql').read_text())
            await conn.execute("INSERT INTO public.vendors(id,name) VALUES('synthetic_other','Invented supplier'),('another_supplier','Another invented supplier')")

    async def manual(self,body=None,key=None):
        return await self.client.post('/api/pg/purchases/berts/manual-records',json=body or record(),headers={'Idempotency-Key':key or str(uuid4())})

    async def attachment(self):
        source=b'%PDF-1.4\nInvented receipt only\x00\xff'
        r=await self.client.post('/api/pg/purchases/berts/sources',files={'file':('synthetic.pdf',source,'application/pdf')},headers={'Idempotency-Key':str(uuid4())})
        self.assertEqual(r.status_code,200,r.text)
        return r.json()['id'],source

    async def test_source_attachment_full_fields_and_received_date_accounting(self):
        _,a,b=await self.pair();file_id,source=await self.attachment()
        body=record(attachment_ids=[file_id]);r=await self.manual(body);self.assertEqual(r.status_code,200,r.text)
        captured=r.json();doc=captured['documents'][0];self.assertEqual(doc['status'],'awaiting_review')
        self.assertEqual(captured['manualRecord'],body)
        self.assertEqual(doc['lines'][0]['vendor_sku_snapshot'],'00001')
        self.assertEqual((await self.client.get(f"/api/pg/purchases/berts/files/{file_id}/source")).content,source)
        self.assertEqual(json.loads((await self.client.get(f"/api/pg/purchases/berts/files/{captured['id']}/source")).content),body)
        reopened=(await self.client.get(f"/api/pg/purchases/berts/files/{captured['id']}")).json()
        self.assertEqual(reopened['manualRecord'],body);self.assertEqual(reopened['attachments'][0]['id'],file_id)
        async with self.pool.acquire() as conn:self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.actual_purchase_facts'),0)
        self.assertEqual((await self.post(doc)).status_code,200)
        report=(await self.report(a,b)).json();self.assertEqual(Decimal(report['netPurchaseCost']),40)
        self.assertEqual(Decimal(report['actualFoodCost']),55);self.assertEqual(Decimal(report['rows'][0]['actualUsage']),50)
        self.assertEqual(report['purchaseLines'][0]['inventory_record_date'],'2026-10-04')

    async def test_missing_and_invalid_values_are_retained_and_held(self):
        for field,value in [('fees_source',''),('invoice_date','wrong date'),('total_source','42'),('discount_source','1')]:
            body=record(number=uuid4().hex);body['documents'][field]=value
            r=await self.manual(body);self.assertEqual(r.status_code,200,r.text);doc=r.json()['documents'][0]
            self.assertEqual(doc['status'],'held');self.assertEqual((await self.post(doc)).status_code,409)
            self.assertEqual(r.json()['manualRecord'],body)
        body=record();body['lines'][0]['fields']['extended_amount_source']='NaN'
        r=await self.manual(body);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['documents'][0]['status'],'held')
        r=await self.manual(record(number=''));self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['documents'],[])
        self.assertIn('Missing',r.json()['parse_errors'][0])

    async def test_capture_retry_and_parallel_post_cannot_duplicate_purchases(self):
        key=str(uuid4());body=record();first=await self.manual(body,key);self.assertEqual(first.status_code,200,first.text)
        second=await self.manual(body,key);third=await self.manual(body)
        self.assertEqual(first.json()['id'],second.json()['id']);self.assertEqual(first.json()['documents'],third.json()['documents'])
        self.assertEqual((await self.manual(record(amount='50'),key)).status_code,409)
        doc=first.json()['documents'][0];post_key=str(uuid4())
        replies=await asyncio.gather(self.post(doc,key=post_key),self.post(doc,key=post_key))
        self.assertTrue(all(r.status_code==200 for r in replies),[r.text for r in replies])
        self.assertEqual(replies[0].json()['batchId'],replies[1].json()['batchId'])
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.actual_purchase_facts'),1)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.import_files'),1)

    async def test_cross_store_unknown_supplier_and_unverified_source_refused(self):
        file_id,_=await self.attachment()
        body=record(attachment_ids=[file_id])
        r=await self.client.post('/api/pg/purchases/rudds/manual-records',json=body,headers={'Idempotency-Key':str(uuid4())})
        self.assertEqual(r.status_code,422)
        for patches in ({'vendor_id':'unregistered'},{'verified_source':False}):
            self.assertEqual((await self.manual(record(**patches))).status_code,422)
        async with self.pool.acquire() as conn:self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.document_versions'),0)

    async def test_manual_csv_identity_requires_correction_and_namespace_collision_is_held(self):
        file,*_=await self.capture(number='SHARED-IDENTITY');old=file['documents'][0]
        self.assertEqual((await self.post(old)).status_code,200)
        body=record(number='SHARED-IDENTITY',vendor_id='pfg')
        body['documents'].update({k:old['header'].get(k) or '' for k in ('customer_number','account_number','vendor_branch_reference')})
        r=await self.manual(body);self.assertEqual(r.status_code,200,r.text);doc=r.json()['documents'][0]
        self.assertEqual(doc['header']['document_id'],old['header']['document_id']);self.assertTrue(doc['correctionAvailable'])
        self.assertEqual((await self.post(doc)).status_code,409)
        body['documents']['vendor_branch_reference']='DIFFERENT'
        collided=(await self.manual(body)).json()['documents'][0]
        self.assertEqual(collided['status'],'held');self.assertFalse(collided['correctionAvailable'])
        self.assertEqual((await self.post(collided)).status_code,409)
        body['documents']['customer_number']=''
        missing=(await self.manual(body)).json()['documents'][0];self.assertEqual(missing['status'],'held')

    async def test_nonfood_and_line_fees_do_not_enter_food_cost(self):
        body=record(amount='40');body['lines'] += [{'fields':{'description_snapshot':'Paper supplies','extended_amount_source':'5'}},
            {'fields':{'description_snapshot':'Printed line fee','extended_amount_source':'1'}}]
        body['documents'].update(subtotal_source='46',total_source='49')
        r=await self.manual(body);doc=r.json()['documents'][0];self.assertEqual(doc['status'],'awaiting_review')
        posting=self.body(doc)
        for row,classification in zip(posting['lines'][1:],('nonfood','fee')):
            row.update(classification=classification,movement_kind='no_inventory')
        r=await self.post(doc,posting);self.assertEqual(r.status_code,200,r.text)
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT sum(inventory_cost_amount) FROM purchasing.actual_purchase_facts'),40)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.current_posting_lines'),3)

    async def test_manual_credit_and_return_share_signed_ledger(self):
        doc=(await self.manual()).json()['documents'][0];self.assertEqual((await self.post(doc)).status_code,200)
        for amount,movement,quantity in [('-5','price_credit',None),('-10','physical_return','-1')]:
            body=record(number=uuid4().hex,amount=amount,document_type='credit')
            body['documents'].update(fees_source='0',tax_source='0',total_source=amount)
            credit=(await self.manual(body)).json()['documents'][0]
            posting=self.body(credit,movement_kind=movement,received_quantity=quantity,movement_date='2026-10-05',original_line_id=doc['lines'][0]['id'])
            r=await self.post(credit,posting);self.assertEqual(r.status_code,200,r.text)
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT sum(inventory_cost_amount) FROM purchasing.actual_purchase_facts'),25)
            self.assertEqual(await conn.fetchval('SELECT sum(base_quantity) FROM purchasing.actual_purchase_facts'),20)

    async def test_closed_periods_hold_manual_post_and_correction_preserves_source(self):
        _,a,b=await self.pair();r=await self.manual();captured=r.json();old=captured['documents'][0]
        self.assertEqual((await self.post(old)).status_code,200)
        report=(await self.report(a,b)).json();self.assertEqual((await self.close(report)).status_code,200)
        late=(await self.manual(record(number='LATE'))).json()['documents'][0]
        self.assertEqual((await self.post(late)).status_code,409)
        new=(await self.manual(record(amount='50'))).json()['documents'][0]
        plan=(await self.plan(new)).json();self.assertEqual(plan['status'],'held')
        closed=(await self.client.get('/api/pg/actual-inventory/berts/closed-periods')).json()
        reopen_plan=(await self.client.get('/api/pg/actual-inventory/berts/reopen-preview/'+closed[0]['id'])).json()
        r=await self.reopen(reopen_plan);self.assertEqual(r.status_code,200,r.text)
        plan=(await self.plan(new)).json();self.assertEqual(plan['status'],'ready')
        result=await self.correct(new,plan);self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(Decimal((await self.report(a,b)).json()['netPurchaseCost']),50)
        self.assertEqual(json.loads((await self.client.get(f"/api/pg/purchases/berts/files/{captured['id']}/source")).content),record())

    async def test_attachment_constraints_and_history_are_immutable(self):
        file_id,_=await self.attachment();r=await self.manual(record(attachment_ids=[file_id]));captured=r.json()
        another,_=await self.attachment()  # Same original bytes deduplicate.
        self.assertEqual(another,file_id)
        async with self.pool.acquire() as conn:
            with self.assertRaises(asyncpg.RaiseError):await conn.execute('DELETE FROM purchasing.manual_attachments')
            orphan=(await self.manual(record(number='NO-ATTACHMENT'))).json()['id']
            with self.assertRaises(asyncpg.RaiseError):
                await conn.execute('INSERT INTO purchasing.manual_attachments VALUES($1,$2,$3)',UUID(orphan),UUID(file_id),'berts')
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.manual_attachments'),1)

    async def test_manual_sources_and_posting_survive_native_recovery(self):
        file_id,source=await self.attachment();_,a,b=await self.pair()
        r=await self.manual(record(attachment_ids=[file_id]));captured=r.json();doc=captured['documents'][0]
        self.assertEqual((await self.post(doc)).status_code,200)
        before=(await self.report(a,b)).json()
        manifest=await backup.create_backup(self.source,recovery.PG_DUMP,self.directory)
        self.assertEqual(manifest['tables']['purchasing.manual_attachments']['rows'],1)
        dsn=await self.target();self.assertEqual((await backup.verify_restore(dsn,self.directory))['status'],'verified')
        client,pool=await self.restored_client(dsn)
        self.assertEqual((await client.get(f"/api/pg/purchases/berts/files/{captured['id']}")).json(),
                         (await self.client.get(f"/api/pg/purchases/berts/files/{captured['id']}")).json())
        self.assertEqual((await client.get(f"/api/pg/purchases/berts/files/{file_id}/source")).content,source)
        restored=(await client.get('/api/pg/actual-inventory/berts/report',params={'opening':a['header']['id'],'closing':b['header']['id']})).json()
        self.assertEqual(restored,before)
        (self.directory/'manual-api-verification.json').write_text(json.dumps({'status':'verified','actualFoodCost':restored['actualFoodCost'],
            'reportHashMatched':True,'sourceFilesMatched':2,'manualRecordAndAttachmentsMatched':True},indent=2))
