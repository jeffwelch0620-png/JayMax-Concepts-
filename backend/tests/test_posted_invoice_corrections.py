"""Synthetic-only proof of linked invoice correction and accounting isolation."""
import asyncio
import os
import unittest
from decimal import Decimal
from uuid import UUID,uuid4
from unittest.mock import patch

import asyncpg
import purchase_api
import test_actual_inventory as counts
import test_actual_inventory_corrections as periods


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PG DSN required')
class PostedInvoiceCorrectionTests(unittest.IsolatedAsyncioTestCase):
    asyncTearDown=counts.ActualInventoryTests.asyncTearDown
    capture=counts.ActualInventoryTests.capture
    body=counts.ActualInventoryTests.body
    post=counts.ActualInventoryTests.post
    scope=counts.ActualInventoryTests.scope
    count=counts.ActualInventoryTests.count
    pair=counts.ActualInventoryTests.pair
    report=counts.ActualInventoryTests.report
    close=counts.ActualInventoryTests.close
    reopen=periods.CorrectionTests.reopen

    async def asyncSetUp(self):
        await counts.ActualInventoryTests.asyncSetUp(self)
        async with self.pool.acquire() as conn:
            await conn.execute((counts.native.ROOT/'migrations/20261004_posted_invoice_corrections.sql').read_text())

    async def initial(self,**kwargs):
        file,*_=await self.capture(**kwargs);doc=file['documents'][0]
        r=await self.post(doc);self.assertEqual(r.status_code,200,r.text)
        return doc,r.json()['batchId']

    async def plan(self,doc,**patches):
        body=self.body(doc,**patches);body['reason']='Verified synthetic invoice correction'
        return await self.client.post(f"/api/pg/purchases/berts/documents/{doc['id']}/correction-preview",json=body)

    async def correct(self,doc,plan,key=None,**patches):
        body={**plan['review'],'expected_plan_hash':plan['planHash'],'expected_initial_batch_id':plan['initialBatchId'],
              'expected_correction_id':plan['previousCorrectionId'],**patches}
        return await self.client.post(f"/api/pg/purchases/berts/documents/{doc['id']}/correct",json=body,headers={'Idempotency-Key':key or str(uuid4())})

    async def rows(self):
        async with self.pool.acquire() as conn:
            return [dict(r) for r in await conn.fetch('SELECT * FROM purchasing.actual_purchase_facts')]

    async def test_quantity_correction_and_successive_generations_cancel_exactly(self):
        _,a,b=await self.pair();doc,batch=await self.initial()
        old=(await self.report(a,b)).json();self.assertEqual(Decimal(old['rows'][0]['actualUsage']),50)
        plan=(await self.plan(doc,received_quantity='3')).json();self.assertEqual(plan['status'],'ready')
        first=await self.correct(doc,plan);self.assertEqual(first.status_code,200,first.text)
        next_plan=(await self.plan(doc,received_quantity='4')).json()
        self.assertEqual(next_plan['previousCorrectionId'],first.json()['correctionId'])
        second=await self.correct(doc,next_plan);self.assertEqual(second.status_code,200,second.text)
        rows=await self.rows();self.assertEqual(len(rows),5);self.assertEqual(sum(r['base_quantity'] for r in rows),80)
        self.assertEqual(sum(r['inventory_cost_amount'] for r in rows),40)
        result=(await self.report(a,b)).json();self.assertEqual(Decimal(result['rows'][0]['actualUsage']),90)
        self.assertEqual(Decimal(result['actualFoodCost']),55)
        self.assertEqual(len({r['fact_id'] for r in rows}),5)
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.posting_batches'),1)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.posting_lines WHERE batch_id=$1',UUID(batch)),1)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.current_purchase_facts'),1)
        history=(await self.client.get(f"/api/pg/purchases/berts/documents/{doc['id']}/corrections")).json()
        self.assertEqual(len(history),2);self.assertEqual(history[0]['reviewed_plan'],plan)

    async def test_balanced_supplier_reissue_changes_cost_without_destroying_source(self):
        _,a,b=await self.pair();old,batch=await self.initial(number='TEST-REISSUE',extra=True)
        file,*_=await self.capture(number='TEST-REISSUE',amounts=('80.00','20.00'),extra=True)
        new=file['documents'][0];self.assertEqual(new['status'],'held');self.assertTrue(new['correctionAvailable'])
        self.assertEqual((await self.post(new)).status_code,409)
        plan=(await self.plan(new)).json();self.assertEqual(len(plan['before']),1);self.assertEqual(len(plan['after']),2)
        r=await self.correct(new,plan);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['document']['status'],'posted')
        report=(await self.report(a,b)).json();self.assertEqual(Decimal(report['netPurchaseCost']),100)
        self.assertEqual(Decimal(report['actualFoodCost']),115)
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.import_files'),2)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.document_versions'),2)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.correction_lines'),3)
            self.assertEqual(await conn.fetchval('SELECT document_version_id FROM purchasing.posting_batches WHERE id=$1',UUID(batch)),UUID(old['id']))

    async def test_remapped_wrong_item_cancels_false_scope_hold(self):
        _,a,b=await self.pair();file,*_=await self.capture();doc=file['documents'][0]
        self.assertEqual((await self.post(doc,self.body(doc,item_code='other_food'))).status_code,200)
        self.assertEqual((await self.report(a,b)).json()['status'],'incomplete')
        plan=(await self.plan(doc)).json();r=await self.correct(doc,plan);self.assertEqual(r.status_code,200,r.text)
        report=(await self.report(a,b)).json();self.assertEqual(report['status'],'complete',report)
        self.assertEqual(Decimal(report['actualFoodCost']),55);self.assertEqual(len(report['purchaseLines']),3)

    async def test_food_to_nonfood_reversal_retains_separate_invoice_components(self):
        _,a,b=await self.pair();doc,_=await self.initial()
        plan=(await self.plan(doc,classification='nonfood',movement_kind='no_inventory',item_code=None,base_unit=None,
                              received_quantity=None,received_unit=None,base_units_per_received_unit=None)).json()
        r=await self.correct(doc,plan);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(Decimal((await self.report(a,b)).json()['actualFoodCost']),15)
        self.assertEqual(plan['separateComponents']['after']['fees_source'],'1')
        self.assertEqual(plan['separateComponents']['after']['tax_source'],'2')
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.current_posting_lines'),1)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.current_purchase_facts'),0)

    async def test_old_and_new_closed_dates_hold_then_reclose_preserves_original_reports(self):
        scope,a,b=await self.pair();doc,_=await self.initial()
        c,_=await self.count(scope,'2026-10-15',quantity='1',value='30');c=c.json()
        x=(await self.close((await self.report(a,b)).json())).json()['closure']
        y=(await self.close((await self.report(b,c)).json())).json()['closure']
        body=self.body(doc,received_quantity='3');body['received_date']='2026-10-09';body['reason']='Correct measured delivery date'
        url=f"/api/pg/purchases/berts/documents/{doc['id']}/correction-preview"
        plan=(await self.client.post(url,json=body)).json();self.assertEqual(plan['status'],'held')
        self.assertEqual([p['id'] for p in plan['affectedPeriods']],[x['id'],y['id']])
        self.assertEqual((await self.correct(doc,plan)).status_code,409)
        reopen_plan=(await self.client.get('/api/pg/actual-inventory/berts/reopen-preview/'+x['id'])).json()
        self.assertEqual((await self.reopen(reopen_plan)).status_code,200)
        self.assertEqual((await self.correct(doc,plan)).status_code,409) # Preview was stale after reopen.
        fresh=(await self.client.post(url,json=body)).json();self.assertEqual((await self.correct(doc,fresh)).status_code,200)
        self.assertEqual(Decimal((await self.report(a,b)).json()['actualFoodCost']),15)
        self.assertEqual(Decimal((await self.report(b,c)).json()['actualFoodCost']),55)
        self.assertEqual((await self.close((await self.report(a,b)).json())).status_code,200)
        self.assertEqual((await self.close((await self.report(b,c)).json())).status_code,200)
        async with self.pool.acquire() as conn:
            for original in (x,y):self.assertEqual(await conn.fetchval('SELECT report_snapshot FROM actual_inventory.period_closures WHERE id=$1',UUID(original['id'])),original['report_snapshot'])

    async def test_new_closed_date_and_old_food_reclassification_cannot_bypass_guards(self):
        _,a,b=await self.pair();doc,_=await self.initial()
        self.assertEqual((await self.close((await self.report(a,b)).json())).status_code,200)
        plan=(await self.plan(doc,classification='fee',movement_kind='no_inventory',item_code=None,base_unit=None,received_quantity=None)).json()
        self.assertEqual(plan['status'],'held');self.assertEqual((await self.correct(doc,plan)).status_code,409)
        self.assertEqual(len(await self.rows()),1)

    async def test_linked_price_credit_holds_receipt_but_credit_itself_can_be_corrected(self):
        doc,_=await self.initial();file,*_=await self.capture(amounts=('-5',),overrides={'document_type_raw':'Credit'})
        credit=file['documents'][0];body=self.body(credit,movement_kind='price_credit',received_quantity=None,
            base_units_per_received_unit=None,original_line_id=doc['lines'][0]['id'],movement_date='2026-10-05')
        r=await self.post(credit,body);self.assertEqual(r.status_code,200,r.text)
        held=(await self.plan(doc,received_quantity='3')).json();self.assertEqual(len(held['linkedDocuments']),1)
        self.assertEqual((await self.correct(doc,held)).status_code,409)
        body.update(reason='Move credit to its verified effective date');body['lines'][0]['movement_date']='2026-10-06'
        plan=(await self.client.post(f"/api/pg/purchases/berts/documents/{credit['id']}/correction-preview",json=body)).json()
        r=await self.correct(credit,plan);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(sum(row['inventory_cost_amount'] for row in await self.rows()),35)
        self.assertEqual(sum(row['base_quantity'] for row in await self.rows()),40)

    async def test_credits_after_reissue_require_effective_original_and_vendor(self):
        old,_=await self.initial(number='REISSUE-CREDIT');file,*_=await self.capture(number='REISSUE-CREDIT',amounts=('50',))
        new=file['documents'][0];plan=(await self.plan(new)).json();self.assertEqual((await self.correct(new,plan)).status_code,200)
        file,*_=await self.capture(amounts=('-5',),overrides={'document_type_raw':'Credit'});credit=file['documents'][0]
        body=self.body(credit,movement_kind='price_credit',received_quantity=None,base_units_per_received_unit=None,
                       original_line_id=old['lines'][0]['id'],movement_date='2026-10-05')
        self.assertEqual((await self.post(credit,body)).status_code,409)
        body['lines'][0]['original_line_id']=new['lines'][0]['id'];self.assertEqual((await self.post(credit,body)).status_code,200)
        history=(await self.client.get('/api/pg/purchases/berts/history')).json()
        active=[r for r in history if r['current_receipt']];self.assertEqual(len(active),1);self.assertEqual(active[0]['line_id'],new['lines'][0]['id'])

    async def test_concurrent_same_retry_and_competing_review_post_once(self):
        doc,_=await self.initial();plan=(await self.plan(doc,received_quantity='3')).json();key=str(uuid4())
        x,y=await asyncio.gather(self.correct(doc,plan,key),self.correct(doc,plan,key))
        self.assertEqual([x.status_code,y.status_code],[200,200]);self.assertEqual(x.json()['correctionId'],y.json()['correctionId'])
        changed=(await self.plan(doc,received_quantity='4')).json()
        x,y=await asyncio.gather(self.correct(doc,changed),self.correct(doc,changed))
        self.assertEqual(sorted([x.status_code,y.status_code]),[200,409]);self.assertEqual(len(await self.rows()),5)
        r=await self.correct(doc,plan,key);self.assertEqual(r.status_code,200,r.text);self.assertFalse(r.json()['isCurrent'])
        self.assertEqual((await self.correct(doc,changed,key)).status_code,409)

    async def test_close_after_preview_stale_source_and_legacy_periods_reject_without_writes(self):
        _,a,b=await self.pair();doc,_=await self.initial(number='STALE-REISSUE')
        plan=(await self.plan(doc,received_quantity='3')).json()
        file,*_=await self.capture(number='STALE-REISSUE',amounts=('50',))
        self.assertEqual((await self.correct(doc,plan)).status_code,409)
        new=file['documents'][0];plan=(await self.plan(new)).json()
        self.assertEqual((await self.close((await self.report(a,b)).json())).status_code,200)
        self.assertEqual((await self.correct(new,plan)).status_code,409)
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.corrections'),0)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.mapping_decisions'),1)

    async def test_strict_review_mapping_precision_and_noop_validation(self):
        doc,_=await self.initial()
        noop=(await self.plan(doc)).json();self.assertEqual(noop['status'],'held');self.assertEqual((await self.correct(doc,noop)).status_code,409)
        numeric_noop=(await self.plan(doc,received_quantity='2.000')).json();self.assertEqual(numeric_noop['status'],'held')
        equivalent=(await self.plan(doc,received_quantity='40',received_unit='lb',base_units_per_received_unit='1')).json()
        self.assertEqual(equivalent['status'],'ready');r=await self.correct(doc,equivalent);self.assertEqual(r.status_code,200,r.text)
        for patches in ({'received_quantity':'-2'},{'base_units_per_received_unit':'0'},{'received_quantity':'1.0000000000001'},
                        {'received_quantity':'1e90'},{'base_unit':'each'},{'item_code':'unknown'},{'verified':False},{'note':'   '}):
            r=await self.plan(doc,**patches);self.assertIn(r.status_code,(422,409),(patches,r.text))
        body=self.body(doc,received_quantity='3');body['reason']='  '
        r=await self.client.post(f"/api/pg/purchases/berts/documents/{doc['id']}/correction-preview",json=body);self.assertEqual(r.status_code,422)
        self.assertEqual(len(await self.rows()),3)

    async def test_replacement_validation_failure_rolls_back_all_mapping_and_ledger_changes(self):
        doc,_=await self.initial();plan=(await self.plan(doc,received_quantity='3')).json()
        async with self.pool.acquire() as conn:
            await conn.execute("CREATE FUNCTION purchasing.synthetic_fail() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic forced fault'; END $$")
            await conn.execute('CREATE TRIGGER synthetic_fault BEFORE INSERT ON purchasing.correction_lines FOR EACH ROW EXECUTE FUNCTION purchasing.synthetic_fail()')
        r=await self.correct(doc,plan);self.assertEqual(r.status_code,409,r.text)
        async with self.pool.acquire() as conn:
            for table,n in [('corrections',0),('correction_lines',0),('mapping_decisions',1),('reconciliation_checks',1)]:
                self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.'+table),n)
        self.assertEqual(len(await self.rows()),1)

    async def test_correction_history_immutable_and_location_feature_gates(self):
        doc,_=await self.initial();plan=(await self.plan(doc,received_quantity='3')).json();r=await self.correct(doc,plan)
        self.assertEqual(r.status_code,200,r.text)
        async with self.pool.acquire() as conn:
            for table in ('corrections','correction_lines'):
                with self.assertRaises(asyncpg.RaiseError):await conn.execute('DELETE FROM purchasing.'+table)
        for suffix in ('correction-preview','correct'):
            body=plan['review'] if suffix=='correction-preview' else {**plan['review'],'expected_plan_hash':plan['planHash'],
                'expected_initial_batch_id':plan['initialBatchId'],'expected_correction_id':None}
            url=f"/api/pg/purchases/rudds/documents/{doc['id']}/{suffix}"
            r=await self.client.post(url,json=body,headers={'Idempotency-Key':str(uuid4())});self.assertEqual(r.status_code,404)
        with patch.dict(os.environ,{'PURCHASE_IMPORT_ENABLED':'false'}):self.assertEqual((await self.plan(doc,received_quantity='4')).status_code,503)

    async def test_upgrade_preserves_existing_posted_facts_and_frozen_report(self):
        # The test fixture installed migration five before any source; repeat against a fresh pre-upgrade database.
        await self.asyncTearDown();await counts.ActualInventoryTests.asyncSetUp(self)
        _,a,b=await self.pair();doc,_=await self.initial();closed=(await self.close((await self.report(a,b)).json())).json()['closure']
        before=await self.rows()
        async with self.pool.acquire() as conn:
            await conn.execute((counts.native.ROOT/'migrations/20261004_posted_invoice_corrections.sql').read_text())
            self.assertEqual(await conn.fetchval('SELECT report_snapshot FROM actual_inventory.period_closures WHERE id=$1',UUID(closed['id'])),closed['report_snapshot'])
            after=[dict(r) for r in await conn.fetch('SELECT * FROM purchasing.actual_purchase_facts')]
            self.assertEqual([{k:r[k] for k in before[0]} for r in after],before)
        self.assertTrue((await self.client.get(f"/api/pg/purchases/berts/documents/{doc['id']}")).json()['correctionAvailable'])

    async def test_database_rejects_incomplete_correction_and_later_line_additions(self):
        doc,batch=await self.initial()
        async with self.pool.acquire() as conn:
            reconciliation=await conn.fetchval('SELECT reconciliation_id FROM purchasing.posting_batches WHERE id=$1',UUID(batch))
            with self.assertRaises(asyncpg.RaiseError):
                async with conn.transaction():
                    await conn.execute('''INSERT INTO purchasing.corrections(initial_batch_id,replacement_version_id,reconciliation_id,
                        idempotency_key,request_fingerprint,reviewed_plan,reason,corrected_by)
                        VALUES($1,$2,$3,$4,$5,'{}','synthetic incomplete correction','synthetic')''',UUID(batch),UUID(doc['id']),reconciliation,str(uuid4()),b'0'*32)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.corrections'),0)
        plan=(await self.plan(doc,received_quantity='3')).json();r=await self.correct(doc,plan);self.assertEqual(r.status_code,200,r.text)
        async with self.pool.acquire() as conn:
            mapping=await conn.fetchval('SELECT mapping_id FROM purchasing.posting_lines WHERE batch_id=$1',UUID(batch))
            with self.assertRaises(asyncpg.RaiseError):await conn.execute('INSERT INTO purchasing.correction_lines(correction_id,polarity,line_id,mapping_id) VALUES($1,1,$2,$3)',UUID(r.json()['correctionId']),UUID(doc['lines'][0]['id']),mapping)

    async def test_database_checks_new_closed_date_even_for_preexisting_review_mapping(self):
        _,a,b=await self.pair();file,*_=await self.capture();doc=file['documents'][0]
        original=self.body(doc);original['received_date']='2026-09-30'
        r=await self.post(doc,original);self.assertEqual(r.status_code,200,r.text);batch=UUID(r.json()['batchId'])
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                header=await purchase_api.load_version(conn,'berts',UUID(doc['id']),lock=True)
                lines={r['id']:dict(r) for r in await conn.fetch('SELECT * FROM purchasing.document_lines WHERE document_version_id=$1',UUID(doc['id']))}
                await purchase_api.append_review_mappings(conn,'berts','synthetic',header,purchase_api.PostDocument(**self.body(doc)),lines)
        self.assertEqual((await self.close((await self.report(a,b)).json())).status_code,200)
        async with self.pool.acquire() as conn:
            with self.assertRaises(asyncpg.RaiseError):await conn.fetchval('SELECT purchasing.correct_document($1,$2,$3,$4,$5,$6,$7,$8)',UUID(doc['id']),str(uuid4()),'synthetic',b'0'*32,batch,None,{},'synthetic moved date')
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.corrections'),0)
        self.assertEqual(len(await self.rows()),1)

    async def test_source_namespace_changes_and_unbalanced_reissues_stay_held(self):
        doc,_=await self.initial(number='SOURCE-HOLDS')
        file,*_=await self.capture(number='SOURCE-HOLDS',amounts=('50',),overrides={'total_source':'999'})
        held=file['documents'][0];self.assertFalse(held['correctionAvailable']);self.assertEqual((await self.plan(held)).status_code,409)
        file,*_=await self.capture(number='SOURCE-HOLDS',amounts=('60',),overrides={'customer_number':'different-account'})
        held=file['documents'][0];self.assertFalse(held['correctionAvailable']);self.assertEqual((await self.plan(held)).status_code,409)
        self.assertEqual(len(await self.rows()),1)
