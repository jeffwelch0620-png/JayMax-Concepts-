"""Synthetic commissioning sources, shared allocations, seals and recovery."""
import asyncio
import json
import os
import unittest
from uuid import UUID,uuid4
from unittest.mock import patch
import asyncpg
import prep_openings as openings
import test_prep_periods as fixtures

class OpeningBoundaryTests(unittest.TestCase):
    def test_opening_requires_confirmation_and_cannot_take_editable_quantities(self):
        body={'count_id':uuid4(),'before_activity_confirmed':True,'note':'Measured complete physical opening'}
        self.assertTrue(openings.OpeningIn(**body).before_activity_confirmed)
        for change in [{'before_activity_confirmed':False},{'quantity':'30'},{'current_price':'1.5'}]:
            with self.assertRaises(ValueError):openings.OpeningIn(**(body|change))

@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PG required')
class PrepOpeningTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await fixtures.PrepPeriodTests.asyncSetUp(self)
        async with self.pool.acquire() as c:
            await c.execute((fixtures.fixtures.fixtures.foundation.recovery.counts.native.ROOT/'migrations/20261005_prep_opening_sources.sql').read_text())
    async def opening_preview(self,count):
        body={'count_id':count['id'],'before_activity_confirmed':True,'note':'Invented full physical opening stock, before recorded activity'}
        return await self.client.post('/api/pg/purchases/berts/prep-openings/preview',json=body),body
    async def opening(self,count,key=None):
        response,body=await self.opening_preview(count);self.assertEqual(response.status_code,200,response.text)
        payload={'opening':body,'expected_review_hash':response.json()['reviewHash'],'reviewed':True}
        r=await self.save('prep-openings',payload,key);self.assertEqual(r.status_code,200,r.text);return r.json()['event'],payload
    async def opening_void(self,event):
        body={'reason':'Invented incorrect opening decision'};path=f"prep-openings/{event['id']}"
        r=await self.client.post('/api/pg/purchases/berts/'+path+'/void-preview',json=body);self.assertEqual(r.status_code,200,r.text)
        result=await self.save(path+'/void',{'change':body,'expected_review_hash':r.json()['reviewHash'],'reviewed':True});self.assertEqual(result.status_code,200,result.text)
        return result.json()['event']
    async def lot(self):
        return next(l for l in (await self.state())['lots'] if l['product_id']==self.p['product_id'])

    async def test_count_sources_feed_prep_and_waste_without_production_or_accounting_writeback(self):
        _,a,b=await self.pair();accounting=(await self.report(a,b)).json()
        nested=await self.nested({'id':str(uuid4())})
        count=await self.count_at('09:00',quantities={self.p['id']:'50'})
        decision,_=await self.opening(count);lot=await self.lot()
        self.assertEqual(lot['remainingRecordedQuantity'],'50');self.assertEqual(lot['sourceKind'],'opening');self.assertIsNone(lot['recipe_version_id'])
        self.assertEqual((await self.client.get('/api/pg/purchases/berts/prep-batches/setup')).json()['events'],[])
        nested['inputs'][0]['source_batch_id']=lot['id'];await self.record(nested)
        await self.save_obs('waste',await self.waste(lot,'5'))
        self.assertEqual((await self.lot())['remainingRecordedQuantity'],'25')
        end=await self.count_at('13:00','20',quantities={self.p['id']:'25'})
        report=(await self.comparison(count,end,opening_cutoff='before_all')).json()['report']
        row=next(r for r in report['prepared'] if r['product_id']==self.p['product_id'])
        self.assertEqual(row['recordedProduction'],'0');self.assertEqual(row['observedDepletion'],'25');self.assertEqual(row['serviceUseOrUnrecordedLoss'],'0')
        self.assertEqual(report['rawExplanations'],[])
        self.assertEqual((await self.report(a,b)).json(),accounting)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval("SELECT count(*) FROM prep_inventory.batch_movements WHERE kind='raw_input'"),0)
            self.assertEqual(await c.fetchval("SELECT current_stock FROM store_items WHERE store_id='berts' AND item_code='test_food'"),0)

    async def test_parallel_opening_exact_retry_and_duplicate_source_guards(self):
        count=await self.count_at('09:00','50');p,body=await self.opening_preview(count)
        payload={'opening':body,'expected_review_hash':p.json()['reviewHash'],'reviewed':True};key=str(uuid4())
        responses=await asyncio.gather(self.save('prep-openings',payload,key),self.save('prep-openings',payload,key))
        self.assertEqual([r.status_code for r in responses],[200,200]);self.assertEqual(responses[0].json()['event']['id'],responses[1].json()['event']['id'])
        self.assertEqual((await self.save('prep-openings',payload)).status_code,409)
        self.assertEqual((await self.opening_preview(count))[0].status_code,409)
        changed={**payload,'opening':{**body,'note':'Different invented decision'}}
        self.assertEqual((await self.save('prep-openings',changed,key)).status_code,409)
        self.assertEqual((await self.save('prep-openings',{**payload,'reviewed':False})).status_code,422)

    async def test_unused_count_correction_holds_stale_sources_until_void_and_reestablishment(self):
        count=await self.count_at('09:00','50');decision,_=await self.opening(count)
        body=await self.count_body('40',performed_at='2026-10-05T09:00:00-04:00')
        current,_=await self.change_obs(count,{'kind':'replacement','replacement':body,'reason':'Corrected opening measurement'})
        self.assertEqual((await self.state())['lots'],[])
        self.assertEqual((await self.preview_batch(await self.entry())).status_code,409)
        await self.opening_void(decision)
        await self.opening(current);self.assertEqual((await self.lot())['remainingRecordedQuantity'],'40')
        self.assertEqual((await self.client.post('/api/pg/purchases/berts/prep-batches/'+(await self.lot())['id']+'/change-preview',json={'kind':'void','reason':'Wrong workflow'})).status_code,422)

    async def test_used_source_and_count_corrections_are_held_until_dependencies_resolved(self):
        count=await self.count_at('09:00','50');decision,_=await self.opening(count);lot=await self.lot()
        body=await self.count_body('40',performed_at='2026-10-05T09:00:00-04:00')
        change={'kind':'replacement','replacement':body,'reason':'Count correction'}
        prepared=(await self.client.post(f"/api/pg/purchases/berts/prep-observations/count/{count['id']}/change-preview",json=change)).json()
        waste,_=await self.save_obs('waste',await self.waste(lot,'5'))
        async with self.pool.acquire() as c:
            with self.assertRaises(asyncpg.RaiseError):
                async with c.transaction():await fixtures.fixtures.observations.persist(c,'berts',prepared,uuid4(),bytes(32),'synthetic-manager')
        response=await self.client.post(f"/api/pg/purchases/berts/prep-openings/{decision['id']}/void-preview",json={'reason':'Correct opening'})
        self.assertEqual(response.status_code,409)
        self.assertEqual((await self.client.post(f"/api/pg/purchases/berts/prep-observations/count/{count['id']}/change-preview",json={'kind':'replacement','replacement':body,'reason':'Count correction'})).status_code,409)
        await self.change_obs(waste,{'kind':'void','reason':'Invented invalid dependent disposal'})
        await self.opening_void(decision)
        self.assertEqual((await self.opening_preview(count))[0].status_code,409)  # recorded activity history cannot be erased by void

    async def test_backdated_activity_old_scope_and_post_activity_commissioning_are_held(self):
        count=await self.count_at('09:00','50');decision,_=await self.opening(count)
        self.assertEqual((await self.preview_batch(await self.entry(performed_at='2026-10-05T08:00:00-04:00'))).status_code,409)
        self.assertEqual((await self.plan_obs('waste',await self.waste(performed_at='2026-10-05T08:00:00-04:00'))).status_code,409)
        foreign=await self.client.post('/api/pg/purchases/rudds/prep-openings/preview',json={'count_id':count['id'],'before_activity_confirmed':True,'note':'Foreign'});self.assertIn(foreign.status_code,[403,404])
        with patch.dict(os.environ,{'PREP_OBSERVATIONS_ENABLED':'false'}):self.assertEqual((await self.opening_preview(count))[0].status_code,503)
        await self.opening_void(decision)
        added=await self.product('Added after old count');await self.profile(added)
        self.assertEqual((await self.opening_preview(count))[0].status_code,409)

    async def test_all_zero_opening_is_complete_without_fake_sources_or_balance_resets(self):
        count=await self.count_at('09:00');decision,_=await self.opening(count);self.assertEqual((await self.state())['lots'],[])
        self.assertEqual(decision['review_snapshot']['lots'],[])
        await self.record(await self.entry());later=await self.count_at('13:00','30')
        self.assertEqual((await self.opening_preview(later))[0].status_code,409)
        self.assertEqual((await self.comparison(count,later)).json()['report']['prepared'][0]['recordedProduction'],'48')

    async def test_database_seals_full_count_sources_rollback_and_late_children(self):
        count=await self.count_at('09:00','50');response,body=await self.opening_preview(count);plan=response.json()
        async with self.pool.acquire() as c:
            damaged=json.loads(json.dumps(plan));damaged['review']['lots'][0]['quantity']='60'
            with self.assertRaises(asyncpg.RaiseError):
                async with c.transaction():await openings.persist(c,'berts',damaged,uuid4(),bytes(32),'invented-manager')
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.opening_decisions'),0)
        original=openings.persist
        async def fail(*args):await original(*args);raise RuntimeError('Invented failed acknowledgment before commit')
        with patch.object(openings,'persist',side_effect=fail):
            with self.assertRaises(RuntimeError):await self.save('prep-openings',{'opening':body,'expected_review_hash':plan['reviewHash'],'reviewed':True})
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.opening_decisions'),0)
        decision,_=await self.opening(count);lot=await self.lot()
        async with self.pool.acquire() as c:
            with self.assertRaises(asyncpg.RaiseError):await c.execute('DELETE FROM prep_inventory.opening_decisions')
            with self.assertRaises(asyncpg.RaiseError):await c.execute("INSERT INTO prep_inventory.batch_movements(event_id,store_id,ordinal,side,kind,product_id,base_unit,quantity) VALUES($1,'berts',2,'apply','output',$2,'lb',50)",UUID(lot['id']),UUID(self.p['product_id']))

    async def test_restore_preserves_opening_source_projection_and_period_without_double_production(self):
        nested=await self.nested({'id':str(uuid4())});count=await self.count_at('09:00',quantities={self.p['id']:'50'});await self.opening(count);lot=await self.lot()
        nested['inputs'][0]['source_batch_id']=lot['id'];await self.record(nested);await self.save_obs('waste',await self.waste(lot,'5'))
        closing=await self.count_at('13:00','20',quantities={self.p['id']:'25'})
        state=await self.state();comparison=(await self.comparison(count,closing)).json();setup=(await self.client.get('/api/pg/purchases/berts/prep-openings/setup')).json()
        recovery=fixtures.fixtures.fixtures.foundation.recovery
        manifest=await fixtures.fixtures.backup.create_backup(self.source,recovery.PG_DUMP,self.directory);target=await self.target();proof=await fixtures.fixtures.backup.verify_restore(target,self.directory);self.assertEqual(proof['status'],'verified')
        client,pool=await self.restored_client(target)
        self.assertEqual((await client.get('/api/pg/purchases/berts/prep-observations/setup')).json(),state)
        self.assertEqual((await client.get('/api/pg/purchases/berts/prep-openings/setup')).json(),setup)
        self.assertEqual((await client.post('/api/pg/purchases/berts/prep-periods/preview',json=self.query(count,closing))).json(),comparison)
        evidence={'status':'verified','backup_directory':str(self.directory),'tables':{k:v for k,v in manifest['tables'].items() if k.startswith('prep_inventory.')},'dump':manifest['dump'],
            'source_equals_restored':True,'opening_decisions':1,'observations':3,'batch_events':2,'reportHash':comparison['reportHash'],'operational_data':False}
        (recovery.counts.native.ROOT.parent/'prep-openings-restore-evidence.json').write_text(json.dumps(evidence,indent=2))

for _name in ['asyncTearDown','units','pair','scope','count','capture','body','post','report','target','restored_client','save','product','profile','recipe','plan','promote','entry','preview_batch','record','change','nested','waste','count_body','plan_obs','save_obs','change_obs','state','count_at','query','comparison']:
    setattr(PrepOpeningTests,_name,getattr(fixtures.PrepPeriodTests,_name))


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PG required')
class OpeningMigrationCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    """Earlier production/waste/period behaviors with the new migration applied."""
    asyncSetUp=PrepOpeningTests.asyncSetUp

for _name in ['asyncTearDown','units','pair','scope','count','capture','body','post','report','target','restored_client','save','product','profile','recipe','plan','promote','entry','preview_batch','record','change','nested','waste','count_body','plan_obs','save_obs','change_obs','state','count_at','query','comparison']:
    setattr(OpeningMigrationCompatibilityTests,_name,getattr(PrepOpeningTests,_name))
for _owner,_names in [
    (fixtures.fixtures.fixtures.PrepBatchTests,['test_trim_is_included_once_and_actual_food_cost_is_unchanged','test_lot_overdraw_stale_preview_and_parallel_allocation_are_held',
        'test_replacement_and_void_append_exact_reversals_and_preserve_history','test_sealed_children_immutable_facts_and_reviewed_movement_tampering_are_rejected',
        'test_old_producing_recipe_lot_remains_usable_under_current_standard_recipe','test_dst_repeated_hour_preserves_offset_and_large_exact_quantities_do_not_round',
        'test_restored_transaction_identifier_collision_cannot_append_old_batch_or_recipe_children']),
    (fixtures.fixtures.PrepObservationTests,['test_concurrent_prep_and_waste_share_one_allocation_limit','test_waste_replacement_releases_its_own_allocation_without_rewriting_history',
        'test_full_physical_count_requires_explicit_zero_complete_scope_and_frozen_profiles','test_tiny_quantities_and_profile_factors_seal_exactly_without_scientific_notation_conflicts']),
    (fixtures.PrepPeriodTests,['test_backfill_corrections_and_void_refresh_effective_generations','test_same_instant_activity_requires_cutoff_and_adjacent_periods_are_additive'])]:
    for _name in _names:setattr(OpeningMigrationCompatibilityTests,_name,getattr(_owner,_name))
