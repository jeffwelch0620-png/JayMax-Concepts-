"""Synthetic saved analytics, backfill drift, shared boundaries and safe recovery."""
import asyncio
import json
import os
import unittest
from uuid import UUID, uuid4
from unittest.mock import patch
import asyncpg
import prep_period_journal as journal
import test_prep_openings as fixtures

class JournalBoundaryTests(unittest.TestCase):
    def test_no_quantities_cost_or_unapproved_scope_additions(self):
        body={'product_id':uuid4(),'zero_at_opening_confirmed':True,'evidence':'Measured empty at boundary'}
        self.assertTrue(journal.ZeroAddition(**body).zero_at_opening_confirmed)
        for change in [{'zero_at_opening_confirmed':False},{'quantity':'2'},{'cost':'3'}]:
            with self.assertRaises(ValueError):journal.ZeroAddition(**(body|change))
        with self.assertRaises(ValueError):journal.ReopenIn(from_closure_id=uuid4(),reason=' ')

@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PG required')
class PrepJournalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await fixtures.PrepOpeningTests.asyncSetUp(self)
        async with self.pool.acquire() as c:await c.execute((fixtures.fixtures.fixtures.fixtures.foundation.recovery.counts.native.ROOT/'migrations/20261005_prep_period_journal.sql').read_text(encoding='utf-8'))
    def submission(self,a,b,**changes):
        return {'period':self.query(a,b), 'zero_additions':[], 'reason':'Reviewed synthetic incomplete analytical coverage', **changes}
    async def journal_preview(self,body,reopen=False):
        return await self.client.post('/api/pg/purchases/berts/prep-period-journal/'+('reopen-preview' if reopen else 'preview'),json=body)
    async def close(self,a,b,key=None,**changes):
        body=self.submission(a,b,**changes);r=await self.journal_preview(body);self.assertEqual(r.status_code,200,r.text)
        payload={'submission':body,'expected_review_hash':r.json()['reviewHash'],'reviewed':True}
        result=await self.save('prep-period-journal',payload,key);self.assertEqual(result.status_code,200,result.text)
        return result.json()['event'],payload
    async def reopen(self,event):
        body={'from_closure_id':event['id'],'reason':'Synthetic corrected evidence, preserve old reports'}
        r=await self.journal_preview(body,True);self.assertEqual(r.status_code,200,r.text)
        result=await self.save('prep-period-journal/reopen',{'submission':body,'expected_review_hash':r.json()['reviewHash'],'reviewed':True});self.assertEqual(result.status_code,200,result.text)
        return result.json()['event']
    async def journal_state(self):
        r=await self.client.get('/api/pg/purchases/berts/prep-period-journal');self.assertEqual(r.status_code,200,r.text);return r.json()

    async def test_adjacent_snapshots_keep_partial_coverage_and_accounting_independent(self):
        _,x,y=await self.pair();before=(await self.report(x,y)).json()
        a=await self.count_at('09:00');await self.record(await self.entry());b=await self.count_at('13:00','40');c=await self.count_at('16:00','20')
        first,_=await self.close(a,b);second,_=await self.close(b,c,period=self.query(b,c,opening_cutoff='before_all'))
        state=await self.journal_state();self.assertEqual([r['freshness']['status'] for r in state['closures']],['current','current'])
        self.assertEqual(second['previous_id'],first['id']);self.assertEqual(first['review_snapshot']['report']['prepared'][0]['recordedProduction'],'48')
        self.assertFalse(first['review_snapshot']['report']['coverage']['finalVarianceAvailable']);self.assertIsNone(first['review_snapshot']['report']['cost']['amount'])
        self.assertEqual((await self.report(x,y)).json(),before)
        self.assertEqual((await self.journal_preview(self.submission(a,c))).status_code,409)
        changed=self.submission(c,await self.count_at('17:00'));changed['period']['opening_cutoff']='after_all'
        self.assertEqual((await self.journal_preview(changed)).status_code,409) # prior closing was before_all

    async def test_backfill_void_and_suffix_reopen_preserve_original_results(self):
        a=await self.count_at('09:00');b=await self.count_at('13:00');c=await self.count_at('16:00')
        first,_=await self.close(a,b);second,_=await self.close(b,c,period=self.query(b,c,opening_cutoff='before_all'))
        batch,_=await self.record(await self.entry());state=await self.journal_state()
        self.assertEqual(state['closures'][0]['freshness']['status'],'stale');self.assertEqual(state['closures'][0]['review_snapshot'],first['review_snapshot'])
        await self.change(batch,{'kind':'void','reason':'Synthetic erroneous backfill'})
        self.assertEqual((await self.journal_state())['closures'][0]['freshness']['status'],'stale') # history changes even when totals return
        body={'from_closure_id':second['id'],'reason':'Must start earlier'};self.assertEqual((await self.journal_preview(body,True)).status_code,409)
        changed=await self.reopen(first);self.assertEqual(changed['closure_ids'],[first['id'],second['id']])
        replacement,_=await self.close(a,b);self.assertNotEqual(replacement['id'],first['id']);self.assertIsNone(replacement['previous_id'])
        state=await self.journal_state();self.assertEqual([r['freshness']['status'] for r in state['closures']],['reopened','reopened','current'])

    async def test_shared_count_correction_marks_both_periods_and_reopens_earliest(self):
        a=await self.count_at('09:00');b=await self.count_at('13:00');c=await self.count_at('16:00')
        first,_=await self.close(a,b);second,_=await self.close(b,c,period=self.query(b,c,opening_cutoff='before_all'))
        corrected,_=await self.change_obs(b,{'kind':'replacement','replacement':await self.count_body('2',performed_at='2026-10-05T13:00:00-04:00'),'reason':'Synthetic shared count correction'})
        self.assertEqual([r['freshness']['status'] for r in (await self.journal_state())['closures']],['stale','stale'])
        self.assertEqual((await self.journal_preview({'from_closure_id':second['id'],'reason':'Late only'},True)).status_code,409)
        await self.reopen(first);await self.close(a,corrected);await self.close(corrected,c,period=self.query(corrected,c,opening_cutoff='before_all'))

    async def test_zero_scope_addition_is_explicit_no_new_count_or_source(self):
        a=await self.count_at('09:00','10');b=await self.count_at('13:00','5');first,_=await self.close(a,b)
        added=await self.product('Synthetic new zero item');await self.profile(added);c=await self.count_at('16:00','0',quantities={self.p['id']:'3'})
        body=self.submission(b,c,period=self.query(b,c,opening_cutoff='before_all'))
        self.assertEqual((await self.journal_preview(body)).status_code,409)
        zeros=[{'product_id':added['product_id'],'zero_at_opening_confirmed':True,'evidence':'Measured empty at 13:00 before first use'}]
        closure,_=await self.close(b,c,period=body['period'],zero_additions=zeros)
        r=closure['review_snapshot']['report'];self.assertFalse(r['scopeHandoff']['createsStockSources'])
        self.assertEqual(next(x for x in r['prepared'] if x['product_id']==self.p['product_id'])['openingQuantity'],'5')
        self.assertEqual(next(x for x in r['prepared'] if x['product_id']==added['product_id'])['openingQuantity'],'0')
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM prep_inventory.observations'),3)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM prep_inventory.batch_events'),0)
        d=await self.count_at('17:00');await self.close(c,d,period=self.query(c,d,opening_cutoff='before_all'))
        # Scope additions never turn a later physical closing quantity into inferred opening stock.
        self.assertEqual(first['review_snapshot']['report']['prepared'][0]['openingQuantity'],'10')

    async def test_added_item_earlier_stock_blocks_zero_and_stales_saved_handoff(self):
        a=await self.count_at('09:00');b=await self.count_at('13:00');await self.close(a,b)
        added=await self.product('New scope');await self.profile(added);c=await self.count_at('16:00')
        zeros=[{'product_id':added['product_id'],'zero_at_opening_confirmed':True,'evidence':'Empty at boundary'}]
        saved,_=await self.close(b,c,period=self.query(b,c,opening_cutoff='before_all'),zero_additions=zeros)
        await self.count_at('12:00','1') # newly captured historical nonzero stock outside interval
        self.assertEqual((await self.journal_state())['closures'][-1]['freshness']['status'],'stale')
        await self.reopen(saved)
        self.assertEqual((await self.journal_preview(self.submission(b,c,period=self.query(b,c,opening_cutoff='before_all'),zero_additions=zeros))).status_code,409)

    async def test_concurrent_retry_stale_preview_atomic_rollback_and_db_guards(self):
        a=await self.count_at('09:00');b=await self.count_at('13:00');body=self.submission(a,b)
        plan=(await self.journal_preview(body)).json();payload={'submission':body,'expected_review_hash':plan['reviewHash'],'reviewed':True}
        original=journal.persist
        async def fail(*args):await original(*args);raise RuntimeError('Synthetic uncommitted failure')
        with patch.object(journal,'persist',side_effect=fail):
            with self.assertRaises(RuntimeError):await self.save('prep-period-journal',payload)
        self.assertEqual((await self.journal_state())['closures'],[])
        async with self.pool.acquire() as c:
            tampered=json.loads(json.dumps(plan));tampered['review']['report']['prepared'][0]['openingQuantity']='100'
            with self.assertRaises(asyncpg.RaiseError):
                async with c.transaction():await journal.persist(c,'berts',tampered,uuid4(),bytes(32),'synthetic-manager')
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.period_closures'),0)
        key=str(uuid4());responses=await asyncio.gather(self.save('prep-period-journal',payload,key),self.save('prep-period-journal',payload,key))
        self.assertEqual([r.status_code for r in responses],[200,200]);self.assertEqual(responses[0].json()['event']['id'],responses[1].json()['event']['id'])
        await self.record(await self.entry());self.assertEqual((await self.save('prep-period-journal',payload,key)).status_code,200) # original receipt
        self.assertEqual((await self.save('prep-period-journal',payload)).status_code,409)
        self.assertEqual((await self.save('prep-period-journal',{**payload,'submission':{**body,'reason':'Other'}},key)).status_code,409)
        async with self.pool.acquire() as c:
            with self.assertRaises(asyncpg.RaiseError):await c.execute('DELETE FROM prep_inventory.period_closures')
            tampered=json.loads(json.dumps(plan));tampered['review']['report']['prepared'][0]['openingQuantity']='100'
            with self.assertRaises(asyncpg.RaiseError):
                async with c.transaction():await journal.persist(c,'berts',tampered,uuid4(),bytes(32),'synthetic-manager')

    async def test_feature_store_and_approval_guards(self):
        a=await self.count_at('09:00');b=await self.count_at('13:00');body=self.submission(a,b)
        with patch.dict(os.environ,{'PREP_OBSERVATIONS_ENABLED':'false'}):
            self.assertEqual((await self.journal_preview(body)).status_code,503)
            self.assertEqual((await self.client.get('/api/pg/purchases/berts/prep-period-journal')).status_code,503)
        foreign=await self.client.post('/api/pg/purchases/rudds/prep-period-journal/preview',json=body);self.assertIn(foreign.status_code,[403,404])
        p=(await self.journal_preview(body)).json();self.assertEqual((await self.save('prep-period-journal',{'submission':body,'expected_review_hash':p['reviewHash'],'reviewed':False})).status_code,422)

    async def test_native_totals_seal_nested_waste_precision_and_reopening_suffix(self):
        nested=await self.nested({'id':str(uuid4())});a=await self.count_at('09:00',quantities={self.p['id']:'50.000000000001'})
        await self.opening(a);lot=await self.lot();nested['inputs'][0]['source_batch_id']=lot['id'];await self.record(nested)
        await self.save_obs('waste',await self.waste(lot,'5'));await self.save_obs('waste',await self.waste(quantity='3'))
        b=await self.count_at('13:00','20',quantities={self.p['id']:'25.000000000001'});body=self.submission(a,b)
        plan=(await self.journal_preview(body)).json()
        async with self.pool.acquire() as c:
            for field in ['recordedProduction','recordedNestedUseMeasured','recordedWaste','serviceUseOrUnrecordedLoss']:
                damaged=json.loads(json.dumps(plan));damaged['review']['report']['prepared'][0][field]='500'
                with self.assertRaises(asyncpg.RaiseError):
                    async with c.transaction():await journal.persist(c,'berts',damaged,uuid4(),bytes(32),'synthetic-manager')
        first,_=await self.close(a,b);c=await self.count_at('16:00');second,_=await self.close(b,c,period=self.query(b,c,opening_cutoff='before_all'))
        body={'from_closure_id':first['id'],'reason':'Resolve synthetic mistake'};plan=(await self.journal_preview(body,True)).json()
        damaged=json.loads(json.dumps(plan));damaged['review']['closure_ids']=[first['id']];damaged['review']['snapshots']=damaged['review']['snapshots'][:1]
        async with self.pool.acquire() as conn:
            with self.assertRaises(asyncpg.RaiseError):
                async with conn.transaction():await journal.persist(conn,'berts',damaged,uuid4(),bytes(32),'synthetic-manager',True)
        await self.reopen(first)
        # Reopening analytics cannot release the independent source-lot protection.
        changed=await self.client.post(f"/api/pg/purchases/berts/prep-observations/count/{a['id']}/change-preview",json={'kind':'replacement','replacement':await self.count_body('2',performed_at='2026-10-05T09:00:00-04:00'),'reason':'Cannot erase allocated opening'})
        self.assertEqual(changed.status_code,409)

    async def test_new_activity_invalidates_preview_before_first_save(self):
        a=await self.count_at('09:00');b=await self.count_at('13:00');body=self.submission(a,b);plan=(await self.journal_preview(body)).json()
        await self.record(await self.entry());result=await self.save('prep-period-journal',{'submission':body,'expected_review_hash':plan['reviewHash'],'reviewed':True})
        self.assertEqual(result.status_code,409);self.assertEqual((await self.journal_state())['closures'],[])

    async def test_deferred_seal_rejects_same_transaction_late_activity(self):
        a=await self.count_at('09:00');b=await self.count_at('13:00');plan=(await self.journal_preview(self.submission(a,b))).json()
        batch_body=await self.entry();batch_plan=(await self.preview_batch(batch_body)).json()
        async with self.pool.acquire() as c:
            with self.assertRaises(asyncpg.RaiseError):
                async with c.transaction():
                    await journal.persist(c,'berts',plan,uuid4(),bytes(32),'synthetic-manager')
                    await fixtures.fixtures.fixtures.fixtures.batches.persist(c,'berts',batch_plan,uuid4(),bytes(32),'synthetic-manager')
        self.assertEqual((await self.journal_state())['closures'],[])
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.batch_events'),0)

    async def test_restore_saved_handoff_reopening_and_original_reports(self):
        a=await self.count_at('09:00','50');await self.opening(a);await self.record(await self.entry());await self.save_obs('waste',await self.waste(await self.lot(),'5'))
        b=await self.count_at('13:00','30');first,_=await self.close(a,b)
        added=await self.product('Restored new scope');await self.profile(added);c=await self.count_at('16:00')
        second,_=await self.close(b,c,period=self.query(b,c,opening_cutoff='before_all'),zero_additions=[{'product_id':added['product_id'],'zero_at_opening_confirmed':True,'evidence':'Confirmed empty at handoff'}])
        await self.reopen(second)
        state=await self.journal_state();recovery=fixtures.fixtures.fixtures.fixtures.foundation.recovery
        manifest=await fixtures.fixtures.fixtures.backup.create_backup(self.source,recovery.PG_DUMP,self.directory)
        target=await self.target();proof=await fixtures.fixtures.fixtures.backup.verify_restore(target,self.directory);self.assertEqual(proof['status'],'verified')
        client,pool=await self.restored_client(target);r=await client.get('/api/pg/purchases/berts/prep-period-journal');self.assertEqual(r.json(),state)
        evidence={'status':'verified','backup_directory':str(self.directory),'tables':{k:v for k,v in manifest['tables'].items() if k.startswith('prep_inventory.')},
            'dump':manifest['dump'],'source_equals_restored':True,'closures':2,'reopenings':1,'opening_decisions':1,'batch_events':2,'observations':4,'operational_data':False}
        (recovery.counts.native.ROOT.parent/'prep-journal-restore-evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')

for _name in ['asyncTearDown','units','pair','scope','count','capture','body','post','report','target','restored_client','save','product','profile','recipe','plan','promote','entry','preview_batch','record','change','nested','waste','count_body','plan_obs','save_obs','change_obs','state','count_at','query','comparison','opening_preview','opening','opening_void','lot']:
    setattr(PrepJournalTests,_name,getattr(fixtures.PrepOpeningTests,_name))

@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PG required')
class JournalMigrationCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=PrepJournalTests.asyncSetUp

for _name in ['asyncTearDown','units','pair','scope','count','capture','body','post','report','target','restored_client','save','product','profile','recipe','plan','promote','entry','preview_batch','record','change','nested','waste','count_body','plan_obs','save_obs','change_obs','state','count_at','query','comparison','opening_preview','opening','opening_void','lot']:
    setattr(JournalMigrationCompatibilityTests,_name,getattr(PrepJournalTests,_name))
for _owner,_names in [
    (fixtures.PrepOpeningTests,['test_used_source_and_count_corrections_are_held_until_dependencies_resolved']),
    (fixtures.fixtures.fixtures.fixtures.PrepBatchTests,['test_lot_overdraw_stale_preview_and_parallel_allocation_are_held']),
    (fixtures.fixtures.PrepPeriodTests,['test_same_instant_activity_requires_cutoff_and_adjacent_periods_are_additive'])]:
    for _name in _names:setattr(JournalMigrationCompatibilityTests,_name,getattr(_owner,_name))
