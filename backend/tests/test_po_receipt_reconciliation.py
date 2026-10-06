"""Invented invoices only; reconciliation must leave actual accounting unchanged."""
import asyncio
import json
import os
import unittest
from decimal import Decimal
from uuid import UUID,uuid4

import asyncpg
import native_backup as backup
import test_native_order_receiving as receiving
import test_native_backup as recovery


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PG DSN required')
class POReconciliationTests(unittest.IsolatedAsyncioTestCase):
    asyncTearDown=receiving.NativeOrderReceivingTests.asyncTearDown
    target=receiving.NativeOrderReceivingTests.target
    restored_client=receiving.NativeOrderReceivingTests.restored_client
    manual=receiving.NativeOrderReceivingTests.manual
    attachment=receiving.NativeOrderReceivingTests.attachment
    body=receiving.NativeOrderReceivingTests.body
    post=receiving.NativeOrderReceivingTests.post
    pair=receiving.NativeOrderReceivingTests.pair
    scope=receiving.NativeOrderReceivingTests.scope
    count=receiving.NativeOrderReceivingTests.count
    report=receiving.NativeOrderReceivingTests.report
    close=receiving.NativeOrderReceivingTests.close
    plan=receiving.NativeOrderReceivingTests.plan
    correct=receiving.NativeOrderReceivingTests.correct
    units=receiving.NativeOrderReceivingTests.units
    po=receiving.NativeOrderReceivingTests.po
    purchase=receiving.NativeOrderReceivingTests.purchase
    receipt_plan=receiving.NativeOrderReceivingTests.receipt_plan
    link=receiving.NativeOrderReceivingTests.link

    async def asyncSetUp(self):
        await receiving.NativeOrderReceivingTests.asyncSetUp(self)
        async with self.pool.acquire() as conn:
            await conn.execute((recovery.counts.native.ROOT/'migrations/20261005_po_receipt_reconciliation.sql').read_text())

    async def linked(self,complete=False):
        await self.units();ref,pid,line=await self.po();doc=await self.purchase()
        p=(await self.receipt_plan(ref,line,doc,complete)).json();result=await self.link(ref,p)
        self.assertEqual(result.status_code,200,result.text)
        return ref,pid,line,doc,result.json()['receipt']

    async def change(self,doc,**changes):
        response=await self.plan(doc,**changes);self.assertEqual(response.status_code,200,response.text)
        p=response.json();self.assertEqual(p['status'],'ready',p)
        r=await self.correct(doc,p);self.assertEqual(r.status_code,200,r.text)
        return r.json()

    async def setup(self,ref,rid):
        return await self.client.get(f'/api/pg/purchases/berts/orders/{ref}/receipts/{rid}/reconciliation-setup')

    async def recon_plan(self,ref,line,rid,doc_id=None,extra=False):
        response=await self.setup(ref,rid);self.assertEqual(response.status_code,200,response.text)
        document=response.json()['document']
        body={'document_version_id':doc_id or document['id'],'lines':[{'source_line_id':r['line_id'],
            'po_line_id':None if extra else str(line),'verified':True} for r in document['currentMappings']
            if r['classification']=='food' and r['movement_kind']=='receipt'],
            'variances_reviewed':True,'note':'Reviewed corrected physical receipt, extras and frozen order variance'}
        return await self.client.post(f'/api/pg/purchases/berts/orders/{ref}/receipts/{rid}/reconciliation-preview',json=body)

    async def reconcile(self,ref,rid,plan,key=None):
        return await self.client.post(f'/api/pg/purchases/berts/orders/{ref}/receipts/{rid}/reconciliations',
            json={**plan['review'],'expected_plan_hash':plan['planHash']},headers={'Idempotency-Key':key or str(uuid4())})

    async def facts(self):
        async with self.pool.acquire() as conn:
            return [dict(r) for r in await conn.fetch('SELECT * FROM purchasing.actual_purchase_facts ORDER BY fact_id')]

    async def test_replacement_restores_partial_receiving_without_counting_both_generations(self):
        _,a,b=await self.pair();ref,pid,line,doc,receipt=await self.linked()
        await self.change(doc,received_quantity='3');before=await self.facts();report=(await self.report(a,b)).json()
        async with self.pool.acquire() as conn:await conn.execute('UPDATE vendor_items SET unit_qty=6 WHERE id=$1',self.sku)
        await self.units(factor='24')
        p=(await self.recon_plan(ref,line,receipt['id'])).json();self.assertEqual(p['status'],'ready')
        self.assertEqual(Decimal(p['comparison'][0]['beforeReceivedBase']),40)
        self.assertEqual(Decimal(p['comparison'][0]['receivedBase']),60)
        self.assertEqual(p['orderedRows'][0]['factor'],'20')
        saved=await self.reconcile(ref,receipt['id'],p);self.assertEqual(saved.status_code,200,saved.text)
        self.assertEqual(await self.facts(),before);self.assertEqual((await self.report(a,b)).json(),report)
        new=await self.purchase();next_plan=(await self.receipt_plan(ref,line,new)).json()
        self.assertEqual(next_plan['status'],'ready');self.assertEqual(Decimal(next_plan['comparison'][0]['previousReceivedBase']),60)
        self.assertEqual(Decimal(next_plan['comparison'][0]['receivedBase']),100)
        self.assertEqual(Decimal(next_plan['comparison'][0]['differenceBase']),20)
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT current_stock FROM store_items WHERE item_code=$1 AND store_id=$2','test_food','berts'),0)
            root=await conn.fetchrow('SELECT * FROM purchasing.po_receipts WHERE id=$1',UUID(receipt['id']))
            self.assertEqual(root['reviewed_plan'],receipt['reviewed_plan'])

    async def test_same_key_concurrent_retry_replays_and_changed_review_conflicts(self):
        ref,_,line,doc,r=await self.linked();await self.change(doc,received_quantity='3')
        p=(await self.recon_plan(ref,line,r['id'])).json();key=str(uuid4())
        results=await asyncio.gather(self.reconcile(ref,r['id'],p,key),self.reconcile(ref,r['id'],p,key))
        self.assertTrue(all(s.status_code==200 for s in results),[s.text for s in results])
        self.assertEqual(results[0].json()['reconciliation']['id'],results[1].json()['reconciliation']['id'])
        altered={**p,'review':{**p['review'],'note':'Different review'}}
        self.assertEqual((await self.reconcile(ref,r['id'],altered,key)).status_code,409)
        async with self.pool.acquire() as conn:self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.po_receipt_reconciliations'),1)

    async def test_successive_corrections_and_competing_reviews_extend_only_one_chain(self):
        ref,_,line,doc,r=await self.linked();await self.change(doc,received_quantity='3')
        p=(await self.recon_plan(ref,line,r['id'])).json();first=await self.reconcile(ref,r['id'],p)
        self.assertEqual(first.status_code,200,first.text)
        await self.change(doc,received_quantity='1');p=(await self.recon_plan(ref,line,r['id'])).json()
        self.assertEqual(p['previousReconciliationId'],first.json()['reconciliation']['id'])
        outcomes=await asyncio.gather(self.reconcile(ref,r['id'],p),self.reconcile(ref,r['id'],p))
        self.assertEqual(sorted(s.status_code for s in outcomes),[200,409])
        setup=(await self.setup(ref,r['id'])).json();self.assertFalse(setup['receipt']['stale'])
        self.assertEqual(setup['receipt']['reconciliation_revision'],2)
        self.assertEqual(len(setup['receipt']['reconciliations']),2)
        self.assertEqual(Decimal(setup['receipt']['reviewed_plan']['comparison'][0]['receivedBase']),20)

    async def test_other_stale_invoice_stays_held_and_changes_invalidate_parallel_preview(self):
        ref,_,line,doc,r=await self.linked();other_doc=await self.purchase()
        initial=(await self.receipt_plan(ref,line,other_doc)).json();other=await self.link(ref,initial)
        self.assertEqual(other.status_code,200,other.text);other_receipt=other.json()['receipt']
        await self.change(doc,received_quantity='3');await self.change(other_doc,received_quantity='1')
        p=(await self.recon_plan(ref,line,r['id'])).json();q=(await self.recon_plan(ref,line,other_receipt['id'])).json()
        self.assertEqual(p['otherStaleReceiptIds'],[other_receipt['id']])
        self.assertEqual((await self.reconcile(ref,r['id'],p)).status_code,200)
        self.assertEqual((await self.reconcile(ref,other_receipt['id'],q)).status_code,409)
        new=await self.purchase();held=(await self.receipt_plan(ref,line,new)).json();self.assertEqual(held['status'],'held')
        q=(await self.recon_plan(ref,line,other_receipt['id'])).json();self.assertEqual((await self.reconcile(ref,other_receipt['id'],q)).status_code,200)
        ready=(await self.receipt_plan(ref,line,new)).json();self.assertEqual(ready['status'],'ready')

    async def test_new_invoice_correction_invalidates_review_before_any_reconciliation_write(self):
        ref,_,line,doc,r=await self.linked();await self.change(doc,received_quantity='3')
        p=(await self.recon_plan(ref,line,r['id'])).json();await self.change(doc,received_quantity='1')
        before=await self.facts();self.assertEqual((await self.reconcile(ref,r['id'],p)).status_code,409)
        self.assertEqual(await self.facts(),before)
        async with self.pool.acquire() as conn:self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.po_receipt_reconciliations'),0)

    async def test_reclassification_can_remove_food_delivery_without_removing_invoice_history(self):
        ref,_,line,doc,r=await self.linked();await self.change(doc,classification='nonfood',movement_kind='no_inventory',
            item_code=None,base_unit=None,received_quantity=None,base_units_per_received_unit=None,received_unit=None)
        before=await self.facts();p=(await self.recon_plan(ref,line,r['id'])).json()
        self.assertEqual(p['status'],'ready');self.assertEqual(p['receiptLines'],[]);self.assertTrue(p['warnings'])
        result=await self.reconcile(ref,r['id'],p);self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(await self.facts(),before)
        setup=(await self.setup(ref,r['id'])).json();self.assertFalse(setup['receipt']['stale'])
        self.assertEqual(Decimal(setup['receipt']['reviewed_plan']['comparison'][0]['receivedBase']),0)
        self.assertEqual(len(setup['receipt']['original_reviewed_plan']['receiptLines']),1)

    async def test_supplier_reissued_source_invalidates_old_preview_and_reconciles_new_line_ids(self):
        ref,_,line,doc,r=await self.linked();await self.change(doc,received_quantity='3')
        p=(await self.recon_plan(ref,line,r['id'])).json()
        source=receiving.fixtures.record(number=doc['header']['document_number'],amount='50')
        captured=await self.manual(source);self.assertEqual(captured.status_code,200,captured.text)
        new=captured.json()['documents'][0];self.assertNotEqual(new['id'],doc['id'])
        await self.change(new)
        self.assertEqual((await self.reconcile(ref,r['id'],p)).status_code,409)
        p=(await self.recon_plan(ref,line,r['id'])).json();self.assertEqual(p['sourceVersionId'],new['id'])
        self.assertNotEqual(p['receiptLines'][0]['source_line_id'],r['reviewed_plan']['receiptLines'][0]['source_line_id'])
        before=await self.facts();result=await self.reconcile(ref,r['id'],p);self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(await self.facts(),before)

    async def test_extras_and_completed_closed_period_keep_accounting_and_completion_unchanged(self):
        _,a,b=await self.pair();ref,pid,line,doc,r=await self.linked(True)
        await self.change(doc,received_quantity='3');report=(await self.report(a,b)).json()
        self.assertEqual((await self.close(report)).status_code,200)
        async with self.pool.acquire() as conn:before=dict(await conn.fetchrow('SELECT status,received_at FROM purchase_orders WHERE id=$1',pid))
        p=(await self.recon_plan(ref,line,r['id'],extra=True)).json();self.assertEqual(p['status'],'ready')
        self.assertEqual(Decimal(p['comparison'][0]['receivedBase']),0)
        result=await self.reconcile(ref,r['id'],p);self.assertEqual(result.status_code,200,result.text)
        self.assertEqual((await self.report(a,b)).json(),report)
        async with self.pool.acquire() as conn:self.assertEqual(dict(await conn.fetchrow('SELECT status,received_at FROM purchase_orders WHERE id=$1',pid)),before)

    async def test_other_invoice_order_location_and_current_comparison_cannot_be_substituted(self):
        ref,_,line,doc,r=await self.linked()
        p=(await self.recon_plan(ref,line,r['id'])).json();self.assertEqual(p['status'],'held')
        await self.change(doc,received_quantity='3');other=await self.purchase()
        self.assertEqual((await self.recon_plan(ref,line,r['id'],other['id'])).status_code,422)
        other_ref,_,other_line=await self.po()
        self.assertEqual((await self.setup(other_ref,r['id'])).status_code,404)
        self.assertEqual((await self.client.get(f"/api/pg/purchases/rudds/orders/{ref}/receipts/{r['id']}/reconciliation-setup")).status_code,404)
        self.assertEqual((await self.recon_plan(ref,other_line,r['id'])).status_code,422)
        good=(await self.recon_plan(ref,line,r['id'])).json();self.assertEqual((await self.reconcile(ref,r['id'],good)).status_code,200)
        other_plan=(await self.receipt_plan(other_ref,other_line,doc)).json();self.assertEqual(other_plan['status'],'held')

    async def test_reconciliation_history_and_child_rows_are_sealed_and_partial_insert_rolls_back(self):
        ref,_,line,doc,r=await self.linked();await self.change(doc,received_quantity='3')
        p=(await self.recon_plan(ref,line,r['id'])).json();saved=await self.reconcile(ref,r['id'],p)
        self.assertEqual(saved.status_code,200,saved.text)
        async with self.pool.acquire() as conn:
            for sql in ('DELETE FROM purchasing.po_receipt_reconciliations','UPDATE purchasing.po_receipt_reconciliations SET revision=999',
                'DELETE FROM purchasing.po_receipt_reconciliation_lines',
                'INSERT INTO purchasing.po_receipt_reconciliation_lines SELECT reconciliation_id,po_id,NULL,source_line_id,mapping_id,NULL,base_quantity,base_unit FROM purchasing.po_receipt_reconciliation_lines'):
                with self.assertRaises(asyncpg.RaiseError):await conn.execute(sql)
        await self.change(doc,received_quantity='1');p=(await self.recon_plan(ref,line,r['id'])).json()
        async with self.pool.acquire() as conn:
            with self.assertRaises(asyncpg.RaiseError):
                async with conn.transaction():
                    await conn.execute('''INSERT INTO purchasing.po_receipt_reconciliations
                        (receipt_id,po_id,store_id,document_id,initial_batch_id,revision,previous_reconciliation_id,source_version_id,
                        source_correction_id,reviewed_plan,plan_hash,request_key,request_fingerprint,confirmed_by,note)
                        SELECT receipt_id,po_id,store_id,document_id,initial_batch_id,revision+1,id,$1,$2,$3,$4,$5,request_fingerprint,confirmed_by,note
                        FROM purchasing.po_receipt_reconciliations WHERE id=$6''',UUID(p['sourceVersionId']),UUID(p['sourceCorrectionId']),p,
                        bytes.fromhex(p['planHash']),str(uuid4()),UUID(saved.json()['reconciliation']['id']))
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.po_receipt_reconciliations'),1)

    async def test_reconciled_history_units_source_bytes_and_report_survive_native_recovery(self):
        file_id,_=await self.attachment();_,a,b=await self.pair();await self.units('count')
        ref,pid,line,doc,r=await self.linked(True)
        await self.change(doc,received_quantity='3');p=(await self.recon_plan(ref,line,r['id'])).json()
        self.assertEqual((await self.reconcile(ref,r['id'],p)).status_code,200)
        await self.change(doc,received_quantity='1');p=(await self.recon_plan(ref,line,r['id'])).json()
        self.assertEqual((await self.reconcile(ref,r['id'],p)).status_code,200)
        paths=[f'/api/pg/purchases/berts/orders/{ref}/receipt-setup',
            f"/api/pg/purchases/berts/orders/{ref}/receipts/{r['id']}/reconciliation-setup",'/api/pg/purchases/berts/unit-setup',
            f'/api/pg/purchases/berts/files/{file_id}/source']
        before={p:(await self.client.get(p)).content for p in paths};report=(await self.report(a,b)).json()
        manifest=await backup.create_backup(self.source,recovery.PG_DUMP,self.directory)
        self.assertEqual(manifest['tables']['purchasing.po_receipt_reconciliations']['rows'],2)
        dsn=await self.target();verified=await backup.verify_restore(dsn,self.directory);self.assertEqual(verified['status'],'verified')
        client,_=await self.restored_client(dsn)
        for p in paths:self.assertEqual((await client.get(p)).content,before[p])
        restored=(await client.get('/api/pg/actual-inventory/berts/report',params={'opening':a['header']['id'],'closing':b['header']['id']})).json()
        self.assertEqual(restored,report)
        (self.directory/'reconciliation-api-verification.json').write_text(json.dumps({'status':'verified','actualFoodCost':restored['actualFoodCost'],
            'receiptRevisionsMatched':2,'receiptHistoryMatched':True,'originalSourceBytesMatched':True,'reportHashMatched':True},indent=2))
