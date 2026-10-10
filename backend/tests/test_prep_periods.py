"""Count-aligned synthetic depletion, corrections, boundaries and recovery."""
import json
import os
import unittest
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4
from unittest.mock import patch

import prep_periods as periods
import test_prep_observations as fixtures


class PeriodBoundaryTests(unittest.TestCase):
    def test_explicit_cutoffs_and_distinct_counts_are_required(self):
        body={'opening_count_id':uuid4(),'closing_count_id':uuid4(),'opening_cutoff':'after_all','closing_cutoff':'before_all','cutoffs_confirmed':True}
        self.assertEqual(periods.PeriodIn(**body).opening_cutoff,'after_all')
        for change in [{'cutoffs_confirmed':False},{'opening_cutoff':'mid_delivery'},{'closing_count_id':body['opening_count_id']}]:
            with self.assertRaises(ValueError):periods.PeriodIn(**(body|change))
        with self.assertRaises(ValueError):periods.PeriodIn(**{k:v for k,v in body.items() if k!='opening_cutoff'})

    def test_exact_sum_retains_small_amounts_beside_large_values(self):
        large=Decimal('9'*140);small=Decimal('0.'+'0'*139+'1')
        total=periods.exact_sum([large,small,large.copy_negate()])
        self.assertEqual(total,small)

    def test_adjacent_count_cutoffs_assign_tied_events_once(self):
        a,b,c=[datetime.fromisoformat(x) for x in ['2026-10-05T09:00:00+00:00','2026-10-05T12:00:00+00:00','2026-10-05T15:00:00+00:00']]
        for cutoff in ['before_all','after_all']:
            left=periods.in_period(b,a,b,'after_all',cutoff)
            right=periods.in_period(b,b,c,cutoff,'before_all')
            self.assertEqual(int(left)+int(right),1)


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PG required')
class PrepPeriodTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.PrepObservationTests.asyncSetUp

    async def count_at(self,time,quantity='0',quantities=None):
        body=await self.count_body(quantity,performed_at=f'2026-10-05T{time}:00-04:00')
        if quantities:
            for l in body['lines']:l['quantity']=quantities.get(l['product_version_id'],quantity)
        return (await self.save_obs('count',body))[0]

    def query(self,a,b,**changes):
        return {'opening_count_id':a['id'],'closing_count_id':b['id'],'opening_cutoff':'after_all','closing_cutoff':'before_all','cutoffs_confirmed':True,**changes}

    async def comparison(self,a,b,**changes):
        return await self.client.post('/api/pg/purchases/berts/prep-periods/preview',json=self.query(a,b,**changes))

    async def test_nested_waste_depletion_and_restore_keep_accounting_independent(self):
        _,x,y=await self.pair();accounting=(await self.report(x,y)).json()
        producer,_=await self.record(await self.entry())
        nested=await self.nested(producer)
        opening=await self.count_at('09:00',quantities={self.p['id']:'10'})
        await self.record(nested)
        await self.save_obs('waste',await self.waste(producer,'5'))
        await self.save_obs('waste',await self.waste(quantity='3'))
        closing=await self.count_at('13:00','20',quantities={self.p['id']:'23'})
        response=await self.comparison(opening,closing);self.assertEqual(response.status_code,200,response.text)
        result=response.json();r=result['report'];row=next(p for p in r['prepared'] if p['product_id']==self.p['product_id'])
        self.assertEqual([row[k] for k in ['recordedProduction','observedDepletion','recordedNestedUseMeasured','recordedWaste','serviceUseOrUnrecordedLoss']],['48','35','20','5','10'])
        self.assertIsNone(row['expectedClosingQuantity']);self.assertIsNone(row['unexplainedVariance'])
        raw=r['rawExplanations'][0];self.assertEqual(raw['recordedRawExplanation'],'63');self.assertEqual(raw['annotatedIncludedTrim'],'12')
        self.assertEqual(len(r['includedEvents']),4);self.assertFalse(r['coverage']['finalVarianceAvailable'])
        self.assertEqual((await self.report(x,y)).json(),accounting)
        async with self.pool.acquire() as c:
            before=await c.fetchval('SELECT count(*) FROM prep_inventory.observations')
        self.assertEqual((await self.comparison(opening,closing)).json(),result)
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.observations'),before)
        recovery=fixtures.fixtures.foundation.recovery
        manifest=await fixtures.backup.create_backup(self.source,recovery.PG_DUMP,self.directory)
        target=await self.target();proof=await fixtures.backup.verify_restore(target,self.directory);self.assertEqual(proof['status'],'verified')
        client,pool=await self.restored_client(target)
        restored=await client.post('/api/pg/purchases/berts/prep-periods/preview',json=self.query(opening,closing));self.assertEqual(restored.json(),result)
        evidence={'status':'verified','backup_directory':str(self.directory),'tables':{k:v for k,v in manifest['tables'].items() if k.startswith('prep_inventory.')},
            'dump':manifest['dump'],'source_equals_restored':True,'reportHash':result['reportHash'],'observations':4,'batch_events':2,'operational_data':False}
        (recovery.counts.native.ROOT.parent/'prep-periods-restore-evidence.json').write_text(json.dumps(evidence,indent=2))

    async def test_same_instant_activity_requires_cutoff_and_adjacent_periods_are_additive(self):
        await self.record(await self.entry())
        await self.save_obs('waste',await self.waste(quantity='3'))
        a=await self.count_at('10:00');b=await self.count_at('12:00');c=await self.count_at('14:00')
        for first in ['before_all','after_all']:
            for last in ['before_all','after_all']:
                r=(await self.comparison(a,b,opening_cutoff=first,closing_cutoff=last)).json()['report']
                self.assertEqual(r['prepared'][0]['recordedProduction'],'48' if first=='before_all' else '0')
                self.assertEqual(len(r['boundaryEvents']['opening']),1);self.assertEqual(len(r['boundaryEvents']['closing']),1)
                self.assertEqual(len(r['rawExplanations']),int(first=='before_all' or last=='after_all'))
        left=(await self.comparison(a,b,opening_cutoff='before_all',closing_cutoff='after_all')).json()['report']
        right=(await self.comparison(b,c,opening_cutoff='after_all')).json()['report']
        whole=(await self.comparison(a,c,opening_cutoff='before_all')).json()['report']
        self.assertEqual(Decimal(left['prepared'][0]['observedDepletion'])+Decimal(right['prepared'][0]['observedDepletion']),Decimal(whole['prepared'][0]['observedDepletion']))
        self.assertEqual(left['rawExplanations'][0]['recordedRawExplanation'],whole['rawExplanations'][0]['recordedRawExplanation'])
        self.assertEqual(right['rawExplanations'],[])

    async def test_backfill_corrections_and_void_refresh_effective_generations(self):
        a=await self.count_at('09:00');b=await self.count_at('13:00','23')
        original=(await self.comparison(a,b)).json();self.assertEqual(original['report']['prepared'][0]['observedDepletion'],'-23')
        self.assertIn('closing_exceeds_opening_plus_recorded_production',original['report']['prepared'][0]['flags'])
        batch,_=await self.record(await self.entry());backfilled=(await self.comparison(a,b)).json()
        self.assertNotEqual(original['reportHash'],backfilled['reportHash'])
        replaced,_=await self.change(batch,{'kind':'replacement','replacement':await self.entry(output_quantity='40'),'reason':'Invented output transcription fixed'})
        new=(await self.comparison(a,b)).json();self.assertEqual(new['report']['prepared'][0]['recordedProduction'],'40')
        self.assertEqual(new['report']['includedEvents'][0]['id'],replaced['id'])
        await self.change(replaced,{'kind':'void','reason':'Invented erroneous producer'})
        self.assertEqual((await self.comparison(a,b)).json(),original)
        body=await self.count_body('22',performed_at='2026-10-05T13:00:00-04:00')
        corrected,_=await self.change_obs(b,{'kind':'replacement','replacement':body,'reason':'Correct original count transcription'})
        self.assertEqual((await self.comparison(a,b)).status_code,409)
        self.assertEqual((await self.comparison(a,corrected)).json()['report']['prepared'][0]['closingQuantity'],'22')
        await self.change_obs(corrected,{'kind':'void','reason':'Erroneous closing observation'})
        self.assertEqual((await self.comparison(a,corrected)).status_code,409)

    async def test_scope_foreign_counts_reversed_times_and_feature_gate_are_held(self):
        a=await self.count_at('09:00');b=await self.count_at('13:00')
        self.assertEqual((await self.comparison(b,a)).status_code,422)
        self.assertEqual((await self.comparison(a,b,closing_count_id=str(uuid4()))).status_code,404)
        self.assertEqual((await self.comparison(a,b,cutoffs_confirmed=False)).status_code,422)
        foreign=await self.client.post('/api/pg/purchases/rudds/prep-periods/preview',json=self.query(a,b));self.assertIn(foreign.status_code,[403,404])
        with patch.dict(os.environ,{'PREP_OBSERVATIONS_ENABLED':'false'}):
            self.assertEqual((await self.comparison(a,b)).status_code,503)
            self.assertEqual((await self.client.get('/api/pg/purchases/berts/prep-periods/counts')).status_code,503)
        product=await self.product('New prepared scope item');await self.profile(product)
        c=await self.count_at('14:00')
        self.assertEqual((await self.comparison(a,c)).status_code,409)
        listing=(await self.client.get('/api/pg/purchases/berts/prep-periods/counts')).json()
        self.assertEqual([v['id'] for v in listing['counts']],[a['id'],b['id'],c['id']])

    async def test_waste_replacement_and_void_are_not_summed_twice(self):
        source,_=await self.record(await self.entry());a=await self.count_at('09:00')
        w,_=await self.save_obs('waste',await self.waste(source,'8'))
        current,_=await self.change_obs(w,{'kind':'replacement','replacement':await self.waste(source,'5'),'reason':'Invented measured correction'})
        b=await self.count_at('13:00','46')
        r=(await self.comparison(a,b)).json()['report']['prepared'][0]
        self.assertEqual(r['recordedWaste'],'5');self.assertEqual(r['serviceUseOrUnrecordedLoss'],'-3')
        self.assertIn('recorded_use_exceeds_observed_depletion',r['flags'])
        await self.change_obs(current,{'kind':'void','reason':'Invented incorrect disposal entry'})
        self.assertEqual((await self.comparison(a,b)).json()['report']['prepared'][0]['recordedWaste'],'0')

    async def test_measured_and_estimated_inputs_remain_distinct_and_units_do_not_reprice(self):
        a=await self.count_at('09:00');await self.record(await self.entry())
        estimated=await self.entry(performed_at='2026-10-05T11:00:00-04:00')
        estimated['inputs'][0].update(measurement_basis='recipe_estimate',included_loss_quantity=None,loss_evidence=None)
        await self.record(estimated);b=await self.count_at('13:00')
        r=(await self.comparison(a,b)).json();raw=r['report']['rawExplanations'][0]
        self.assertEqual([raw[k] for k in ['recordedGrossPrepUseMeasured','recordedGrossPrepUseEstimated','recordedRawExplanation','annotatedIncludedTrim']],['60','60','120','12'])
        self.assertEqual(raw['unannotatedInputs'],1)
        async with self.pool.acquire() as c:await c.execute("UPDATE public.items SET name='Later catalog name' WHERE code='test_food'")
        self.assertEqual((await self.comparison(a,b)).json(),r)


for _name in ['asyncTearDown','units','pair','scope','count','capture','body','post','report','target','restored_client','save','product','profile','recipe','plan','promote','entry','preview_batch','record','change','nested','waste','count_body','plan_obs','save_obs','change_obs','state']:
    setattr(PrepPeriodTests,_name,getattr(fixtures.PrepObservationTests,_name))
