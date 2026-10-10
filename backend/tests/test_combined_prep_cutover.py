"""One synthetic restaurant day, immutable corrections and whole SQL recovery."""
import os
import unittest
from decimal import Decimal
from uuid import UUID, uuid4
from unittest.mock import patch
import asyncpg
import server
import native_backup as backup
import test_staff_prep_production as staff
import test_staff_prep_counts as counts
import test_native_backup as recovery
import test_supplier_prices as prices


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class CombinedPrepCutoverTests(staff.StaffProductionTests):
    receipt=prices.SupplierPriceTests.receipt
    body=prices.SupplierPriceTests.body
    post=prices.SupplierPriceTests.post
    async def asyncSetUp(self):
        await super().asyncSetUp()
        flag=patch.dict(os.environ,{'STAFF_PREP_COUNTS_ENABLED':'true','PREP_CONTAINERS_ENABLED':'true'})
        flag.start(); self.addCleanup(flag.stop)
        async with self.pool.acquire() as conn:
            for name in ('20261007_staff_prep_counts.sql','20261007_prep_containers.sql','20261007_container_waste.sql','20261005_prep_period_journal.sql',
                         '20261008_container_waste_corrections.sql','20261007_native_private_access.sql'):
                await conn.execute((recovery.counts.native.ROOT/'migrations'/name).read_text())
        self.count_url='/api/pg/purchases/berts/staff-prep-counts'

    issue_sheet=counts.StaffPrepCountsTests.issue_sheet
    accept=counts.StaffPrepCountsTests.accept

    async def physical_prep_count(self,stamp,quantity):
        sheet=dict(performed_at=stamp,business_date=stamp[:10],timezone_name='America/New_York',calendar_date_confirmed=True,
            note='Invented whole prep count; purchased items excluded',units=[dict(product_version_id=self.p['id'],profile_id=self.u['id'])])
        issued,_=await self.issue_sheet(sheet); self.assertEqual(issued.status_code,200,issued.text)
        review=issued.json()['current']
        body=dict(pin='',expected_review_hash=review['reviewHash'],counter_name='Invented claimed counter',note='Measured all prep storage',
            lines=[dict(product_id=i['product_id'],quantity=quantity,evidence='Invented scale observation') for i in review['sheet']['sheet_snapshot']['items']])
        counter=server._token(dict(id='synthetic-combined-count-counter',email='counter@example.invalid',role='staff',locations=['berts']))
        submitted=await self.portal.post('/api/pg/staff/berts/prep-count-drafts/'+review['sheet']['id']+'/submit',json=body,
            headers={'Idempotency-Key':str(uuid4()),'Authorization':'Bearer '+counter})
        self.assertEqual(submitted.status_code,200,submitted.text)
        accepted,_=await self.accept(submitted.json()['current']); self.assertEqual(accepted.status_code,200,accepted.text)
        return accepted.json()['observation']

    def stamp(self,clock):
        return dict(performed_at='2026-10-08T'+clock+':00-04:00',business_date='2026-10-08',timezone_name='America/New_York',
            calendar_date_confirmed=True,note='Invented measured physical activity')

    async def container_command(self,body):
        url='/api/pg/purchases/berts/prep-containers'
        preview=await self.catalog.post(url+'/preview',json=body); self.assertEqual(preview.status_code,200,preview.text)
        result=await self.catalog.post(url+'/commands',json=dict(body=body,expected_review_hash=preview.json()['reviewHash'],reviewed=True),headers={'Idempotency-Key':str(uuid4())})
        self.assertEqual(result.status_code,200,result.text); return result.json()

    async def period(self,a,b):
        body=dict(opening_count_id=a['id'],closing_count_id=b['id'],opening_cutoff='after_all',closing_cutoff='before_all',cutoffs_confirmed=True)
        result=await self.catalog.post('/api/pg/purchases/berts/prep-periods/preview',json=body)
        self.assertEqual(result.status_code,200,result.text); return body,result.json()

    async def test_combined_trial_counts_purchases_staff_containers_period_correction_and_restore(self):
        # Track 1 uses explicit values and received purchase facts, before Track 2 activity.
        _,actual_a,actual_b=await self.pair()
        await self.receipt(date='2026-10-04',amount='40')
        accounting=(await self.report(actual_a,actual_b)).json()
        self.assertEqual(accounting['actualFoodCost'],'55.00')
        opening=await self.physical_prep_count('2026-10-08T09:00:00-04:00','1')
        opening_body=dict(count_id=opening['id'],before_activity_confirmed=True,note='Invented commissioning count before prep activity')
        preview=await self.catalog.post('/api/pg/purchases/berts/prep-openings/preview',json=opening_body)
        self.assertEqual(preview.status_code,200,preview.text)
        result=await self.catalog.post('/api/pg/purchases/berts/prep-openings',json=dict(opening=opening_body,expected_review_hash=preview.json()['reviewHash'],reviewed=True),headers={'Idempotency-Key':str(uuid4())})
        self.assertEqual(result.status_code,200,result.text)
        submitted=await self.submission('2'); response=await self.submit(submitted)
        self.assertEqual(response.status_code,200,response.text)
        first=await self.decide(self.decision(response.json()['submission']))
        self.assertEqual(first.status_code,200,first.text); batch=first.json()['batch_event']
        self.assertEqual(first.json()['current']['execution']['task_progress'][0]['status'],'in_progress')
        definition=(await self.container_command(dict(action='definition',name='Invented two-pound prep pan',capacity_unit='l',usable_capacity='2',evidence='Measured vessel capacity')))['result']
        profile=(await self.container_command(dict(action='profile',definition_id=definition['id'],product_version_id=self.p['id'],unit_profile_id=self.u['id'],usable_quantity='2',product_fill_measured=True,evidence='Measured food fill; not inferred from liters')))['result']
        fill=(await self.container_command(self.stamp('10:15')|dict(action='fill',profile_id=profile['id'],source_batch_id=batch['id'],label='Invented service pan',quantity='2',contents_measured=True)))['result']
        path=f"/api/pg/purchases/berts/prep-batches/{batch['id']}/change-preview"
        self.assertEqual((await self.catalog.post(path,json=dict(kind='void',reason='Must resolve container dependency first'))).status_code,409)
        await self.container_command(self.stamp('10:20')|dict(action='send',fill_id=fill['id'],quantity='1'))
        await self.container_command(self.stamp('10:25')|dict(action='waste',fill_id=fill['id'],quantity='.25',compartment='service',category='service_discard',contents_measured=True))
        await self.container_command(self.stamp('10:30')|dict(action='return',fill_id=fill['id'],quantity='.75'))
        await self.container_command(self.stamp('10:35')|dict(action='unpack',fill_id=fill['id'],quantity='1.75'))
        second_body=submitted|dict(root_id=str(uuid4()),batch=submitted['batch']|dict(output_quantity='1',performed_at='2026-10-08T11:00:00-04:00'),note='Distinct second measured batch')
        response=await self.submit(second_body); self.assertEqual(response.status_code,200,response.text)
        decision=self.decision(response.json()['submission']); preview=await self.decision_preview(decision)
        payload=decision|dict(expected_review_hash=preview.json()['reviewHash'],reviewed=True); key=str(uuid4())
        second=await self.decide(payload=payload,key=key); self.assertEqual(second.status_code,200,second.text)
        closing=await self.physical_prep_count('2026-10-08T12:00:00-04:00','3.4')
        period_body,old_report=await self.period(opening,closing)
        close_body=dict(period=period_body,zero_additions=[],reason='Invented reviewed partial analytical coverage')
        preview=await self.catalog.post('/api/pg/purchases/berts/prep-period-journal/preview',json=close_body)
        self.assertEqual(preview.status_code,200,preview.text)
        closed=await self.catalog.post('/api/pg/purchases/berts/prep-period-journal',json=dict(submission=close_body,expected_review_hash=preview.json()['reviewHash'],reviewed=True),headers={'Idempotency-Key':str(uuid4())})
        self.assertEqual(closed.status_code,200,closed.text)
        corrected=await self.correct(second.json()['batch_event'],'.75')
        execution=await self.execution_state(); draft=execution['draft']; task=execution['tasks'][0]
        await self.reconcile(draft,task,corrected,second.json()['execution_event'],execution['revision'],False)
        execution=await self.execution_state()
        finished=await self.write_execution(self.command(draft,'finish',task_id=task['id']),execution['revision'])
        self.assertEqual(finished.status_code,200,finished.text)
        self.assertEqual(Decimal(finished.json()['current']['task_progress'][0]['reviewed_base_quantity']),Decimal('2.75'))
        _,report=await self.period(opening,closing); row=report['report']['prepared'][0]
        self.assertEqual([Decimal(row[k]) for k in ('openingQuantity','recordedProduction','closingQuantity','recordedWaste','observedDepletion','serviceUseOrUnrecordedLoss')],[Decimal(x) for x in ('1','2.75','3.4','.25','.35','.1')])
        self.assertFalse(report['report']['coverage']['finalVarianceAvailable']); self.assertIsNone(report['report']['cost']['amount'])
        journal=(await self.catalog.get('/api/pg/purchases/berts/prep-period-journal')).json()
        self.assertEqual(journal['closures'][0]['freshness']['status'],'stale')
        self.assertEqual(journal['closures'][0]['review_snapshot']['report'],closed.json()['event']['review_snapshot']['report'])
        self.assertEqual(journal['closures'][0]['review_snapshot']['report']['prepared'],old_report['report']['prepared'])
        self.assertEqual((await self.report(actual_a,actual_b)).json(),accounting)
        before=await self.execution_state()
        dependency_url=f"/api/pg/purchases/berts/prep-batches/{batch['id']}/correction-review"
        dependency_response=await self.catalog.get(dependency_url)
        self.assertEqual(dependency_response.status_code,200,dependency_response.text)
        dependencies=dependency_response.json()
        for role,locations in [('readonly',['berts']),('staff',['berts']),('manager',['rudds'])]:
            token=server._token(dict(id='synthetic-review-'+role,email='review@example.invalid',role=role,locations=locations))
            denied=await self.portal.get(dependency_url,headers={'Authorization':'Bearer '+token})
            self.assertEqual(denied.status_code,403,denied.text)
        self.assertEqual(dependencies['gate']['status'],'held')
        self.assertEqual(len(dependencies['containers']),1)
        self.assertEqual(dependencies['containers'][0]['nextPreviewAction'],'undo')
        self.assertEqual([m['action'] for m in dependencies['containers'][0]['moves']],['send','waste','return','unpack'])
        self.assertEqual(len(dependencies['wasteHistory']),1)
        self.assertEqual(len(dependencies['staffDecisions']),1)
        self.assertEqual(len(dependencies['taskLinks']),1)
        self.assertEqual(dependencies['savedPeriods'][0]['freshness']['status'],'stale')
        corrected_url=f"/api/pg/purchases/berts/prep-batches/{corrected['id']}/correction-review"
        corrected_dependencies=(await self.catalog.get(corrected_url)).json()
        self.assertEqual(corrected_dependencies['gate']['status'],'eligible_for_preview')
        self.assertFalse(corrected_dependencies['taskLinks'][0]['needsReconciliation'])
        self.assertEqual((await self.report(actual_a,actual_b)).json(),accounting)
        manifest=await backup.create_backup(self.source,recovery.PG_DUMP,self.directory)
        self.assertEqual(manifest['tables']['prep_inventory.staff_decisions']['rows'],2)
        target=await self.target(); self.assertEqual((await backup.verify_restore(target,self.directory))['status'],'verified')
        restored=await asyncpg.create_pool(target,min_size=1,max_size=2,init=recovery.db_pg._init_connection)
        original_pool=self.pool; original_server_pool=server.db_pg._pool
        self.pool=restored; server.db_pg._pool=restored
        try:
            self.assertEqual((await self.catalog.get(dependency_url)).json(),dependencies)
            self.assertEqual((await self.catalog.get(corrected_url)).json(),corrected_dependencies)
            self.assertEqual((await self.report(actual_a,actual_b)).json(),accounting)
            self.assertEqual((await self.period(opening,closing))[1],report)
            self.assertEqual(await self.execution_state(),before)
            replay=await self.decide(payload=payload,key=key); self.assertEqual(replay.status_code,200,replay.text)
            for field in ('decision','batch_event','execution_event'): self.assertEqual(replay.json()[field],second.json()[field])
            self.assertEqual(replay.json()['current']['execution'],before)
            with patch.dict(os.environ,{flag:'false' for flag in ('PREP_BATCHES_ENABLED','PREP_CONTAINERS_ENABLED','STAFF_PREP_COUNTS_ENABLED','PREP_OBSERVATIONS_ENABLED','PREP_DAY_TASKS_ENABLED','PREP_PLANNING_ENABLED')}):
                state=await self.catalog.get('/api/pg/prep/berts/state'); self.assertEqual(state.status_code,200,state.text)
                self.assertEqual(state.json()['prepCapabilities'],dict(countsAvailable=False,listsAvailable=False,reportingAvailable=False))
                self.assertIsNone(state.json()['prepStock'])
                self.assertEqual((await self.catalog.get('/api/pg/preplists/berts')).status_code,410)
                self.assertEqual((await self.catalog.get('/api/pg/prepcount/berts/session')).status_code,409)
            async with restored.acquire() as conn:
                self.assertEqual(await conn.fetchval('SELECT count(*) FROM prep_logs'),0)
                for name in ('staff_decisions','staff_production_decisions','container_waste_links'):
                    self.assertFalse(await conn.fetchval("SELECT EXISTS(SELECT 1 FROM pg_class c,aclexplode(c.relacl) a WHERE c.oid=$1::regclass AND a.grantee<>c.relowner)",'prep_inventory.'+name))
        finally:
            self.pool=original_pool; server.db_pg._pool=original_server_pool; await restored.close()
