"""Invented waste and counts only; every integration case has a disposable DB."""
import asyncio
import json
import os
import unittest
from decimal import Decimal
from uuid import UUID, uuid4
from unittest.mock import patch

import asyncpg
import prep_observations as observations
import native_backup as backup
import test_prep_batches as fixtures


class ObservationBoundaryTests(unittest.TestCase):
    def test_chained_maximum_supported_quantities_do_not_round_standard_usage(self):
        value=Decimal('9999999999999999.123456789012')
        result=observations.mapping.times(observations.mapping.times(value,value),value)
        from decimal import localcontext
        with localcontext() as context:
            context.prec=120;expected=value*value*value
        self.assertEqual(result,expected)

    def test_zero_count_is_valid_but_unknown_and_nonfinite_count_are_not_zero(self):
        row={'product_version_id':uuid4(),'profile_id':uuid4(),'quantity':'0','evidence':'Observed empty'}
        self.assertEqual(observations.CountLine(**row).quantity,Decimal(0))
        for value in [None,'','NaN','Infinity','-1']:
            with self.assertRaises(ValueError):observations.CountLine(**(row|{'quantity':value}))


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PG required')
class PrepObservationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await fixtures.PrepBatchTests.asyncSetUp(self)
        flag=patch.dict(os.environ,{'PREP_OBSERVATIONS_ENABLED':'true'});flag.start();self.addCleanup(flag.stop)
        async with self.pool.acquire() as c:
            await c.execute((fixtures.foundation.recovery.counts.native.ROOT/'migrations/20261005_prep_observations.sql').read_text())

    async def waste(self,source=None,quantity='5',**patches):
        return {'source_kind':'prepared' if source else 'raw','raw_item_code':None if source else 'test_food',
            'product_version_id':self.p['id'] if source else None,'profile_id':self.u['id'] if source else None,'source_batch_id':source['id'] if source else None,
            'quantity':quantity,'source_unit':'lb','factor':'1','measurement_basis':'measured','already_included_in_batch':False,'category':'storage_spoilage',
            'performed_at':'2026-10-05T12:00:00-04:00','business_date':'2026-10-05','timezone_name':'America/New_York','calendar_date_confirmed':True,
            'note':'Invented disposal measured separately from gross prep input',**patches}

    async def count_body(self,quantity='42',**patches):
        async with self.pool.acquire() as c:
            rows=await c.fetch('''SELECT DISTINCT ON(v.product_id) v.id,u.id AS profile_id FROM prep_inventory.product_versions v
                JOIN prep_inventory.unit_profiles u ON u.product_version_id=v.id WHERE v.store_id='berts' ORDER BY v.product_id,v.revision DESC,u.revision DESC''')
        return {'performed_at':'2026-10-05T13:00:00-04:00','business_date':'2026-10-05','timezone_name':'America/New_York','calendar_date_confirmed':True,
            'note':'Invented complete physical prep observation','complete_scope_confirmed':True,
            'lines':[{'product_version_id':str(r['id']),'profile_id':str(r['profile_id']),'quantity':quantity,'evidence':'Invented weighed observation'} for r in rows],**patches}

    async def plan_obs(self,purpose,body):
        return await self.client.post(f'/api/pg/purchases/berts/prep-observations/{purpose}/preview',json=body)

    async def save_obs(self,purpose,body,key=None):
        p=await self.plan_obs(purpose,body);self.assertEqual(p.status_code,200,p.text)
        payload={'body':body,'expected_review_hash':p.json()['reviewHash'],'reviewed':True}
        r=await self.save('prep-observations/'+purpose,payload,key);self.assertEqual(r.status_code,200,r.text)
        return r.json()['event'],payload

    async def change_obs(self,event,change,key=None):
        path=f"prep-observations/{event['purpose']}/{event['id']}"
        p=await self.client.post('/api/pg/purchases/berts/'+path+'/change-preview',json=change);self.assertEqual(p.status_code,200,p.text)
        payload={'change':change,'expected_review_hash':p.json()['reviewHash'],'reviewed':True}
        r=await self.save(path+'/changes',payload,key);self.assertEqual(r.status_code,200,r.text)
        return r.json()['event'],payload

    async def state(self):
        r=await self.client.get('/api/pg/purchases/berts/prep-observations/setup');self.assertEqual(r.status_code,200,r.text);return r.json()

    async def test_raw_waste_count_and_corrections_do_not_change_actual_food_cost_or_legacy_stock(self):
        _,a,b=await self.pair();before=(await self.report(a,b)).json()
        waste,_=await self.save_obs('waste',await self.waste())
        replacement,_=await self.change_obs(waste,{'kind':'replacement','replacement':await self.waste(quantity='3'),'reason':'Corrected waste scale'})
        await self.change_obs(replacement,{'kind':'void','reason':'Erroneous record; not physical waste'})
        count,_=await self.save_obs('count',await self.count_body('0'))
        replacement,_=await self.change_obs(count,{'kind':'replacement','replacement':await self.count_body('2'),'reason':'Recount at same instant'})
        await self.change_obs(replacement,{'kind':'void','reason':'Count record entered in error'})
        self.assertEqual((await self.report(a,b)).json(),before)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT current_stock FROM store_items WHERE item_code=$1 AND store_id=$2','test_food','berts'),0)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_logs'),0)

    async def test_prepared_waste_reduces_allocatable_output_and_count_does_not_reset_it(self):
        source,_=await self.record(await self.entry());waste,_=await self.save_obs('waste',await self.waste(source))
        self.assertEqual((await self.state())['lots'][0]['remainingRecordedQuantity'],'43')
        await self.save_obs('count',await self.count_body('30'))
        self.assertEqual((await self.state())['lots'][0]['remainingRecordedQuantity'],'43')
        batch=(await self.client.get('/api/pg/purchases/berts/prep-batches/setup')).json()
        self.assertEqual(batch['lots'][0]['remainingRecordedQuantity'],'43')
        denied=await self.client.post(f"/api/pg/purchases/berts/prep-batches/{source['id']}/change-preview",json={'kind':'void','reason':'Already wasted output'})
        self.assertEqual(denied.status_code,409)
        await self.change_obs(waste,{'kind':'void','reason':'Waste observation entered in error'})
        await self.change(source,{'kind':'void','reason':'Batch observation entered in error'})

    async def test_concurrent_prep_and_waste_share_one_allocation_limit(self):
        source,_=await self.record(await self.entry());nested=await self.nested(source,'30');waste=await self.waste(source,'30')
        bp=(await self.preview_batch(nested)).json();wp=(await self.plan_obs('waste',waste)).json()
        responses=await asyncio.gather(self.save('prep-batches',{'batch':nested,'expected_review_hash':bp['reviewHash'],'reviewed':True}),
            self.save('prep-observations/waste',{'body':waste,'expected_review_hash':wp['reviewHash'],'reviewed':True}))
        self.assertEqual(sorted(r.status_code for r in responses),[200,409])
        state=await self.state();self.assertEqual(next(l for l in state['lots'] if l['id']==source['id'])['remainingRecordedQuantity'],'18')

    async def test_included_trim_wrong_journal_and_future_or_foreign_source_are_held(self):
        source,_=await self.record(await self.entry());body=await self.waste(source)
        for patch_body in [{'already_included_in_batch':True},{'measurement_basis':'recipe_estimate'},{'quantity':'0'},{'performed_at':'2026-10-05T09:00:00-04:00'},{'source_batch_id':str(uuid4())}]:
            self.assertEqual((await self.plan_obs('waste',body|patch_body)).status_code,422)
        self.assertEqual((await self.plan_obs('waste',body|{'quantity':'49'})).status_code,409)
        self.assertEqual((await self.plan_obs('count',body)).status_code,422)
        self.assertEqual((await self.client.post('/api/pg/purchases/rudds/prep-observations/waste/preview',json=body)).status_code,422)

    async def test_waste_replacement_releases_its_own_allocation_without_rewriting_history(self):
        source,_=await self.record(await self.entry());first,_=await self.save_obs('waste',await self.waste(source,'40'))
        replacement,_=await self.change_obs(first,{'kind':'replacement','replacement':await self.waste(source,'45'),'reason':'Corrected disposal measurement'})
        self.assertEqual((await self.state())['lots'][0]['remainingRecordedQuantity'],'3')
        history=(await self.client.get(f"/api/pg/purchases/berts/prep-observations/waste/{first['root_id']}/history")).json()['events']
        self.assertEqual(history[0],first);self.assertEqual([r['revision'] for r in history],[1,2])
        await self.change_obs(replacement,{'kind':'void','reason':'Waste record entered in error'})
        self.assertEqual((await self.state())['lots'][0]['remainingRecordedQuantity'],'48')

    async def test_stale_waste_and_batch_previews_hold_even_with_sufficient_remaining_output(self):
        source,_=await self.record(await self.entry());body=await self.waste(source,'5');wp=(await self.plan_obs('waste',body)).json()
        nested=await self.nested(source,'10');bp=(await self.preview_batch(nested)).json()
        await self.save_obs('waste',body)
        self.assertEqual((await self.save('prep-observations/waste',{'body':body,'expected_review_hash':wp['reviewHash'],'reviewed':True})).status_code,409)
        self.assertEqual((await self.save('prep-batches',{'batch':nested,'expected_review_hash':bp['reviewHash'],'reviewed':True})).status_code,409)

    async def test_full_physical_count_requires_explicit_zero_complete_scope_and_frozen_profiles(self):
        p=await self.product('Second prepared item');await self.profile(p)
        body=await self.count_body('0')
        self.assertEqual((await self.plan_obs('count',body|{'lines':body['lines'][:1]})).status_code,422)
        missing=json.loads(json.dumps(body));missing['lines'][0]['quantity']=None
        self.assertEqual((await self.plan_obs('count',missing)).status_code,422)
        count,_=await self.save_obs('count',body)
        self.assertEqual([l['base_quantity'] for l in count['review_snapshot']['lines']],['0','0'])
        self.assertEqual((await self.plan_obs('count',body)).status_code,409)
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.batch_movements'),0)

    async def test_count_correction_retains_original_scope_after_new_prepared_identity_is_added(self):
        body=await self.count_body();original,_=await self.save_obs('count',body)
        p=await self.product('New item after count');await self.profile(p)
        body['lines'][0]['quantity']='40'
        corrected,_=await self.change_obs(original,{'kind':'replacement','replacement':body,'reason':'Corrected same-scope observation'})
        self.assertEqual(corrected['review_snapshot']['scope'],original['review_snapshot']['scope'])
        new_body=await self.count_body(performed_at='2026-10-05T14:00:00-04:00')
        later,_=await self.save_obs('count',new_body);self.assertEqual(len(later['review_snapshot']['scope']),2)

    async def test_profile_or_catalog_drift_invalidates_reviews_and_preserves_old_counts(self):
        body=await self.count_body();event,_=await self.save_obs('count',body)
        plan=(await self.plan_obs('count',body|{'performed_at':'2026-10-05T14:00:00-04:00'})).json()
        await self.profile(self.p,'lb','1',self.u['id'])
        r=await self.save('prep-observations/count',{'body':body|{'performed_at':'2026-10-05T14:00:00-04:00'},'expected_review_hash':plan['reviewHash'],'reviewed':True})
        self.assertEqual(r.status_code,409)
        history=(await self.client.get(f"/api/pg/purchases/berts/prep-observations/count/{event['root_id']}/history")).json()['events'];self.assertEqual(history[0],event)
        raw=await self.waste();wp=(await self.plan_obs('waste',raw)).json()
        async with self.pool.acquire() as c:await c.execute("UPDATE public.items SET unit_qty=999 WHERE code='test_food'")
        self.assertEqual((await self.save('prep-observations/waste',{'body':raw,'expected_review_hash':wp['reviewHash'],'reviewed':True})).status_code,409)

    async def test_parallel_replay_changed_payload_and_void_replay_are_safe(self):
        body=await self.waste();p=(await self.plan_obs('waste',body)).json();payload={'body':body,'expected_review_hash':p['reviewHash'],'reviewed':True};key=str(uuid4())
        replies=await asyncio.gather(self.save('prep-observations/waste',payload,key),self.save('prep-observations/waste',payload,key))
        self.assertTrue(all(r.status_code==200 for r in replies),[r.text for r in replies]);event=replies[0].json()['event']
        self.assertEqual(replies[1].json()['event']['id'],event['id'])
        await self.change_obs(event,{'kind':'void','reason':'Wrong waste record'})
        self.assertTrue((await self.save('prep-observations/waste',payload,key)).json()['replayed'])
        self.assertEqual((await self.save('prep-observations/waste',payload|{'body':body|{'quantity':'6'}},key)).status_code,409)

    async def test_parallel_corrections_do_not_fork_and_date_identity_moves_are_held(self):
        event,_=await self.save_obs('waste',await self.waste());change={'kind':'void','reason':'Record entered in error'}
        path=f"prep-observations/waste/{event['id']}";p=(await self.client.post('/api/pg/purchases/berts/'+path+'/change-preview',json=change)).json()
        payload={'change':change,'expected_review_hash':p['reviewHash'],'reviewed':True}
        result=await asyncio.gather(self.save(path+'/changes',payload),self.save(path+'/changes',payload));self.assertEqual(sorted(r.status_code for r in result),[200,409])
        count,_=await self.save_obs('count',await self.count_body())
        changed={'kind':'replacement','replacement':await self.count_body(performed_at='2026-10-05T14:00:00-04:00'),'reason':'Move date held'}
        self.assertEqual((await self.client.post(f"/api/pg/purchases/berts/prep-observations/count/{count['id']}/change-preview",json=changed)).status_code,422)

    async def test_timezone_policy_is_explicit_and_zero_counts_can_precede_first_batch(self):
        body=await self.count_body('0')
        for changes in [{'timezone_name':'Bad/Zone'},{'performed_at':'2026-10-05T13:00:00'},{'business_date':'2026-10-04'},{'complete_scope_confirmed':False}]:
            self.assertEqual((await self.plan_obs('count',body|changes)).status_code,422)
        await self.save_obs('count',body)
        self.assertEqual((await self.state())['policy']['timezone_name'],'America/New_York')
        self.assertEqual((await self.preview_batch((await self.entry())|{'timezone_name':'America/Chicago'})).status_code,409)

    async def test_atomic_failure_rolls_back_count_header_lines_and_first_policy(self):
        body=await self.count_body();p=(await self.plan_obs('count',body)).json();original=observations.persist
        async def failed(*args):await original(*args);raise RuntimeError('Invented failure before acknowledgment')
        with patch.object(observations,'persist',side_effect=failed):
            with self.assertRaises(RuntimeError):await self.save('prep-observations/count',{'body':body,'expected_review_hash':p['reviewHash'],'reviewed':True})
        async with self.pool.acquire() as c:
            for table in ['observations','count_observations','batch_policies']:self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.'+table),0)

    async def test_database_seals_immutability_wrong_quantity_and_late_count_lines(self):
        count,_=await self.save_obs('count',await self.count_body())
        async with self.pool.acquire() as c:
            for table in ['observations','count_observations']:
                with self.assertRaises(asyncpg.RaiseError):await c.execute('DELETE FROM prep_inventory.'+table)
            with self.assertRaises(asyncpg.RaiseError):
                await c.execute('''INSERT INTO prep_inventory.count_observations(event_id,store_id,line_number,product_id,product_version_id,profile_id,base_unit,quantity,factor,base_quantity,evidence)
                    VALUES($1,'berts',2,$2,$3,$4,'lb',1,1,1,'Late tamper')''',UUID(count['id']),UUID(self.p['product_id']),UUID(self.p['id']),UUID(self.u['id']))
            plan=await observations.preview(c,'berts','count',observations.CountIn(**await self.count_body(performed_at='2026-10-05T14:00:00-04:00')))
            plan['review']['lines'][0]['factor']='2'
            plan['review']['lines'][0]['base_quantity']='84'
            with self.assertRaises(asyncpg.RaiseError):
                async with c.transaction():await observations.persist(c,'berts',plan,uuid4(),bytes(32),'synthetic-manager')
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.observations'),1)

    async def test_disabling_observation_ui_does_not_hide_waste_from_batch_allocation(self):
        source,_=await self.record(await self.entry());await self.save_obs('waste',await self.waste(source,'40'))
        with patch.dict(os.environ,{'PREP_OBSERVATIONS_ENABLED':'false'}):
            self.assertEqual((await self.client.get('/api/pg/purchases/berts/prep-observations/setup')).status_code,503)
            self.assertEqual((await self.client.get('/api/pg/purchases/berts/prep-batches/setup')).json()['lots'][0]['remainingRecordedQuantity'],'8')

    async def test_fresh_restore_preserves_waste_count_generations_and_shared_allocations(self):
        source,_=await self.record(await self.entry());waste,_=await self.save_obs('waste',await self.waste(source,'8'))
        await self.change_obs(waste,{'kind':'replacement','replacement':await self.waste(source,'5'),'reason':'Disposal transcription corrected'})
        await self.record(await self.nested(source,'20'))
        body=await self.count_body('30');count,_=await self.save_obs('count',body);body['lines'][0]['quantity']='28'
        await self.change_obs(count,{'kind':'replacement','replacement':body,'reason':'Same-scope measured recount'})
        state=await self.state();batch=(await self.client.get('/api/pg/purchases/berts/prep-batches/setup')).json()
        self.assertEqual(next(l for l in state['lots'] if l['id']==source['id'])['remainingRecordedQuantity'],'23')
        recovery=fixtures.foundation.recovery
        manifest=await backup.create_backup(self.source,recovery.PG_DUMP,self.directory)
        dsn=await self.target();proof=await backup.verify_restore(dsn,self.directory);self.assertEqual(proof['status'],'verified')
        client,pool=await self.restored_client(dsn)
        self.assertEqual((await client.get('/api/pg/purchases/berts/prep-observations/setup')).json(),state)
        self.assertEqual((await client.get('/api/pg/purchases/berts/prep-batches/setup')).json(),batch)
        async with pool.acquire() as c:
            for table in ['observations','waste_movements','count_observations']:
                with self.assertRaises(asyncpg.RaiseError):await c.execute('DELETE FROM prep_inventory.'+table)
        evidence={'status':'verified','backup_directory':str(self.directory),'tables':{k:v for k,v in manifest['tables'].items() if k.startswith('prep_inventory.')},
            'dump':manifest['dump'],'source_equals_restored':True,'observations':4,'batch_events':2,'operational_data':False}
        (recovery.counts.native.ROOT.parent/'prep-observations-restore-evidence.json').write_text(json.dumps(evidence,indent=2))

    async def test_tiny_quantities_and_profile_factors_seal_exactly_without_scientific_notation_conflicts(self):
        body=await self.entry(output_quantity='0.000000000001')
        body['inputs'][0].update(quantity='0.000000000001',included_loss_quantity=None,loss_evidence=None)
        source,_=await self.record(body)
        self.assertEqual(source['review_snapshot']['movements'][0]['quantity'],'-0.000000000001')
        waste,_=await self.save_obs('waste',await self.waste(source,'0.000000000001'))
        self.assertEqual(waste['review_snapshot']['movements'][0]['quantity'],'-0.000000000001')
        await self.change_obs(waste,{'kind':'void','reason':'Tiny invented waste entered in error'})
        raw,_=await self.save_obs('waste',await self.waste(quantity='0.000000000001'))
        revised,_=await self.change_obs(raw,{'kind':'replacement','replacement':await self.waste(quantity='0.000000000002'),'reason':'Tiny invented transcription correction'})
        self.assertEqual(revised['review_snapshot']['movements'][1]['quantity'],'-0.000000000002')
        profile=await self.profile(self.p,'tiny verified measurement','0.000000000001')
        count_body=await self.count_body(lines=[{'product_version_id':self.p['id'],'profile_id':profile['id'],'quantity':'1','evidence':'Invented tiny verified fill'}])
        count,_=await self.save_obs('count',count_body)
        self.assertEqual(count['review_snapshot']['lines'][0]['factor'],'0.000000000001')
        self.assertEqual(count['review_snapshot']['lines'][0]['base_quantity'],'0.000000000001')
        await self.change(source,{'kind':'void','reason':'Tiny invented batch entered in error'})
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT sum(quantity) FROM prep_inventory.batch_movements'),0)


# Reuse fixture helpers without inheriting/re-running the earlier 21 batch tests.
for _name in ['asyncTearDown','units','pair','scope','count','capture','body','post','report','target','restored_client',
              'save','product','profile','recipe','plan','promote','entry','preview_batch','record','change','nested']:
    setattr(PrepObservationTests,_name,getattr(fixtures.PrepBatchTests,_name))
