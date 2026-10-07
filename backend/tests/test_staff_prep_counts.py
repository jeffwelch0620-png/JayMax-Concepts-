"""Invented staff prep measurements, conflicts, SQL guards and whole restore."""
import asyncio, os, unittest
from decimal import Decimal
from uuid import UUID, uuid4
from unittest.mock import patch
import asyncpg, httpx
from pydantic import ValidationError
import server, staff_prep_counts as counts, prep_observations as observations, native_backup as backup
import test_prep_day_tasks as fixtures


class StaffPrepValidationTests(unittest.TestCase):
    def test_strict_counts_and_review_preserve_unknown_zero_and_exact_numbers(self):
        base=dict(product_id=uuid4(),quantity='0',evidence='Empty')
        self.assertEqual(counts.Quantity(**base).quantity,0)
        self.assertIsNone(counts.Quantity(**(base|dict(quantity=None))).quantity)
        for value in ('','NaN','Infinity','-1','0.1234567890123'):
            with self.assertRaises(ValidationError):counts.Quantity(**(base|dict(quantity=value)))
        for value in (False,1,'true'):
            with self.assertRaises(ValidationError):counts.Decision(decision='accepted',note='Reviewed',reviewed=value)
        with self.assertRaises(ValidationError):counts.DecisionIn(decision='accepted',note='Reviewed',reviewed=True,expected_review_hash='a'*64)
        with patch.dict(os.environ,{'STAFF_PREP_COUNTS_ENABLED':'true','PREP_OBSERVATIONS_ENABLED':'false'}):
            with self.assertRaises(server.HTTPException):counts.enabled()


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PG required')
class StaffPrepCountsTests(unittest.IsolatedAsyncioTestCase):
    asyncTearDown=fixtures.PrepDayTaskTests.asyncTearDown
    target=fixtures.PrepDayTaskTests.target
    units=fixtures.PrepDayTaskTests.units
    pair=fixtures.PrepDayTaskTests.pair
    scope=fixtures.PrepDayTaskTests.scope
    count=fixtures.PrepDayTaskTests.count
    report=fixtures.PrepDayTaskTests.report
    save=fixtures.PrepDayTaskTests.save
    product=fixtures.PrepDayTaskTests.product
    profile=fixtures.PrepDayTaskTests.profile
    recipe=fixtures.PrepDayTaskTests.recipe
    plan=fixtures.PrepDayTaskTests.plan
    promote=fixtures.PrepDayTaskTests.promote
    payload=fixtures.PrepDayTaskTests.payload
    edit=fixtures.PrepDayTaskTests.edit
    draft_body=fixtures.PrepDayTaskTests.draft_body
    preview_day=fixtures.PrepDayTaskTests.preview_day
    write_day=fixtures.PrepDayTaskTests.write_day
    prep_count=fixtures.PrepDayTaskTests.prep_count

    async def asyncSetUp(self):
        await fixtures.PrepDayTaskTests.asyncSetUp(self)
        flag=patch.dict(os.environ,{'STAFF_PREP_COUNTS_ENABLED':'true'});flag.start();self.addCleanup(flag.stop)
        async with self.pool.acquire() as c:
            self.legacy_count=await c.fetchval("INSERT INTO count_sessions(store_id,count_date,count_type,status,counted_by_name) VALUES('berts','2026-10-06','nightly_prep','submitted','Original counter') RETURNING id")
            self.legacy_line=await c.fetchval("INSERT INTO count_lines(session_id,prep_item_id,status,qty,note) VALUES($1,$2,'counted',3,'Original untouched count') RETURNING id",self.legacy_count,self.legacy_id)
            await c.execute((fixtures.recovery.counts.native.ROOT/'migrations/20261007_staff_prep_counts.sql').read_text())
        self.count_url='/api/pg/purchases/berts/staff-prep-counts'

    def sheet_body(self,**changes):
        return dict(performed_at='2026-10-07T22:00:00-04:00',business_date='2026-10-07',timezone_name='America/New_York',calendar_date_confirmed=True,
                    note='Measure all prep storage; purchased items excluded',units=[dict(product_version_id=self.p['id'],profile_id=self.u['id'])])|changes

    async def issue_sheet(self,body=None,key=None,payload=None,client=None):
        if payload is None:
            body=body or self.sheet_body();p=await self.catalog.post(self.count_url+'/preview',json=body);self.assertEqual(p.status_code,200,p.text)
            payload=dict(sheet=body,expected_review_hash=p.json()['reviewHash'],reviewed=True)
        response=await (client or self.catalog).post(self.count_url,json=payload,headers={'Idempotency-Key':key or str(uuid4())})
        return response,payload

    def submission(self,review,quantity='2.123456789012',**changes):
        return dict(pin='',expected_review_hash=review['reviewHash'],counter_name='Claimed kitchen counter',note='Measured all listed storage',
                    lines=[dict(product_id=i['product_id'],quantity=quantity,evidence='Invented scale measurement') for i in review['sheet']['sheet_snapshot']['items']])|changes

    async def submit_sheet(self,review,quantity='2.123456789012',key=None,body=None,client=None):
        return await (client or self.catalog).post('/api/pg/staff/berts/prep-count-drafts/'+review['sheet']['id']+'/submit',json=body or self.submission(review,quantity),headers={'Idempotency-Key':key or str(uuid4())})

    async def accept(self,review,decision='accepted',key=None,body=None):
        if body is None:
            p=await self.catalog.post(self.count_url+'/'+review['sheet']['id']+'/decision-preview',json=dict(decision=decision,note='Reviewed physical prep evidence',reviewed=True))
            self.assertEqual(p.status_code,200,p.text);plan=p.json()
            body=plan['decision']|dict(expected_review_hash=plan['current']['reviewHash'],expected_observation_hash=plan['observation']['reviewHash'] if plan['observation'] else None)
        return await self.catalog.post(self.count_url+'/'+review['sheet']['id']+'/decision',json=body,headers={'Idempotency-Key':key or str(uuid4())}),body

    async def test_issue_submission_acceptance_are_analytical_and_feed_both_planning_tracks(self):
        _,a,b=await self.pair();before=(await self.report(a,b)).json()
        response,_=await self.issue_sheet();self.assertEqual(response.status_code,200,response.text);review=response.json()['current']
        submitted=await self.submit_sheet(review);self.assertEqual(submitted.status_code,200,submitted.text)
        accepted,_=await self.accept(submitted.json()['current']);self.assertEqual(accepted.status_code,200,accepted.text)
        event=accepted.json()['observation'];self.assertEqual(event['purpose'],'count')
        preview=await self.preview_day(self.draft_body(count_event_id=event['id']));self.assertEqual(preview.status_code,200,preview.text)
        self.assertEqual(Decimal(preview.json()['review']['tasks'][0]['counted_base_quantity']),Decimal('2.123456789012'))
        self.assertEqual((await self.report(a,b)).json(),before)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.waste_movements'),0)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.batch_movements'),0)
            self.assertEqual(await c.fetchval('SELECT quantity FROM prep_inventory.count_observations WHERE event_id=$1',UUID(event['id'])),Decimal('2.123456789012'))

    async def test_unknown_requires_new_complete_revision_and_measured_zero_is_valid(self):
        r,_=await self.issue_sheet();review=r.json()['current'];sub=await self.submit_sheet(review,quantity=None);self.assertEqual(sub.status_code,200,sub.text)
        path=self.count_url+'/'+review['sheet']['id']+'/decision-preview'
        p=await self.catalog.post(path,json=dict(decision='accepted',note='Reviewed',reviewed=True));self.assertEqual(p.status_code,422,p.text)
        sub=await self.submit_sheet(sub.json()['current'],quantity='0');self.assertEqual(sub.status_code,200,sub.text)
        result,_=await self.accept(sub.json()['current']);self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(len(result.json()['current']['history']),2)
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT base_quantity FROM prep_inventory.count_observations'),0)

    async def test_same_key_races_and_replay_return_original_submission_with_current_state(self):
        key=str(uuid4());first,payload=await self.issue_sheet(key=key);self.assertEqual(first.status_code,200,first.text)
        r=await self.issue_sheet(key=key,payload=payload);self.assertEqual(r[0].json()['sheet'],first.json()['sheet'])
        review=first.json()['current'];key=str(uuid4());body=self.submission(review)
        raced=await asyncio.gather(self.submit_sheet(review,key=key,body=body),self.submit_sheet(review,key=key,body=body))
        for r in raced:self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(raced[0].json()['submission'],raced[1].json()['submission'])
        newer=await self.submit_sheet(raced[0].json()['current'],quantity='3');self.assertEqual(newer.status_code,200,newer.text)
        replay=await self.submit_sheet(review,key=key,body=body);self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json()['submission']['revision'],1);self.assertEqual(replay.json()['current']['latest']['revision'],2)
        self.assertEqual((await self.submit_sheet(review,key=key,body=body|dict(note='Different action'))).status_code,409)
        self.assertEqual((await self.submit_sheet(review,key=key,body=body,client=self.other)).status_code,409)

    async def test_different_key_races_stale_review_and_once_only_manager_decision(self):
        r,_=await self.issue_sheet();review=r.json()['current']
        raced=await asyncio.gather(self.submit_sheet(review,quantity='1'),self.submit_sheet(review,quantity='2'))
        self.assertEqual(sorted(r.status_code for r in raced),[200,409]);current=next(r.json()['current'] for r in raced if r.status_code==200)
        p=await self.catalog.post(self.count_url+'/'+review['sheet']['id']+'/decision-preview',json=dict(decision='accepted',note='Reviewed',reviewed=True));self.assertEqual(p.status_code,200,p.text)
        body=p.json()['decision']|dict(expected_review_hash=current['reviewHash'],expected_observation_hash=p.json()['observation']['reviewHash'])
        key=str(uuid4());decisions=await asyncio.gather(self.accept(current,key=key,body=body),self.accept(current,key=key,body=body))
        for response,_ in decisions:self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(decisions[0][0].json()['decision'],decisions[1][0].json()['decision'])
        self.assertEqual((await self.submit_sheet(current)).status_code,409)
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.observations'),1)

    async def test_units_and_scope_drift_hold_submission_acceptance_but_allow_rejection(self):
        r,_=await self.issue_sheet();review=r.json()['current'];sub=await self.submit_sheet(review);self.assertEqual(sub.status_code,200,sub.text)
        await self.profile(self.p,predecessor=self.u['id'])
        self.assertEqual((await self.submit_sheet(sub.json()['current'])).status_code,409)
        p=await self.catalog.post(self.count_url+'/'+review['sheet']['id']+'/decision-preview',json=dict(decision='accepted',note='Reviewed',reviewed=True));self.assertEqual(p.status_code,409,p.text)
        rejected,_=await self.accept(review,decision='rejected');self.assertEqual(rejected.status_code,200,rejected.text);self.assertIsNone(rejected.json()['observation'])
        new=await self.profile(self.p,unit='oz',factor='0.0625');r,_=await self.issue_sheet(self.sheet_body(units=[dict(product_version_id=self.p['id'],profile_id=new['id'])]));self.assertEqual(r.status_code,200,r.text)
        await self.product('Another prepared item')
        self.assertEqual((await self.submit_sheet(r.json()['current'])).status_code,409)

    async def test_direct_manager_count_occupies_boundary_and_new_submission_invalidates_accept_preview(self):
        r,_=await self.issue_sheet();review=r.json()['current'];sub=await self.submit_sheet(review);current=sub.json()['current']
        p=await self.catalog.post(self.count_url+'/'+review['sheet']['id']+'/decision-preview',json=dict(decision='accepted',note='Reviewed',reviewed=True));self.assertEqual(p.status_code,200,p.text)
        payload=p.json()['decision']|dict(expected_review_hash=current['reviewHash'],expected_observation_hash=p.json()['observation']['reviewHash'])
        await self.submit_sheet(current,quantity='4');r,_=await self.accept(current,body=payload);self.assertEqual(r.status_code,409,r.text)
        await self.prep_count(stamp='2026-10-07T22:00:00-04:00')
        r,_=await self.accept(current,body=payload);self.assertEqual(r.status_code,409,r.text)
        r=await self.catalog.post(self.count_url+'/preview',json=self.sheet_body());self.assertEqual(r.status_code,409,r.text)

    async def test_acceptance_failure_rolls_back_observation_decision_policy_and_revision(self):
        r,_=await self.issue_sheet();sub=await self.submit_sheet(r.json()['current']);current=sub.json()['current']
        original=observations.persist
        async def fail(*args): await original(*args);raise RuntimeError('Invented interruption before decision')
        async with self.pool.acquire() as c:before=await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'")
        with patch.object(observations,'persist',side_effect=fail):
            with self.assertRaises(RuntimeError):await self.accept(current)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'"),before)
            for table in ('observations','count_observations','staff_decisions','batch_policies'):self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.'+table),0)

    async def test_access_pin_and_bearer_evidence_exclude_credentials_and_cross_location_writes(self):
        r,_=await self.issue_sheet();review=r.json()['current']
        async with self.pool.acquire() as c:await c.execute("INSERT INTO staff_pins(store_id,pin) VALUES('berts','4826') ON CONFLICT(store_id) DO UPDATE SET pin='4826'")
        guest=httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://test')
        try:
            body=self.submission(review)|dict(pin='wrong');self.assertEqual((await self.submit_sheet(review,body=body,client=guest)).status_code,403)
            body=self.submission(review)|dict(pin='4826');sub=await self.submit_sheet(review,body=body,client=guest);self.assertEqual(sub.status_code,200,sub.text)
            self.assertEqual(sub.json()['submission']['credential_kind'],'shared_pin');self.assertEqual(sub.json()['submission']['submitted_by'],'shared-pin')
            self.assertNotIn('4826',str(sub.json()));self.assertNotIn('pin',sub.json()['submission']['submitted_body'])
            self.assertEqual((await guest.post(self.count_url+'/preview',json=self.sheet_body())).status_code,401)
        finally:await guest.aclose()
        for role,locations,status in [('staff',['berts'],200),('readonly',['berts'],403),('staff',['rudds'],403)]:
            token=server._token(dict(id='verified-account',email='counter@example.invalid',role=role,locations=locations))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://test',headers={'Authorization':'Bearer '+token}) as client:
                response=await client.post('/api/pg/staff/berts/prep-count-drafts',json=dict(pin=''));self.assertEqual(response.status_code,status,response.text)
                if role=='staff' and status==200:
                    self.assertEqual((await client.post(self.count_url+'/preview',json=self.sheet_body())).status_code,403)
                    measured=await self.submit_sheet(sub.json()['current'],client=client);self.assertEqual(measured.status_code,200,measured.text)
                    self.assertEqual(measured.json()['submission']['credential_kind'],'bearer');self.assertEqual(measured.json()['submission']['submitted_by'],'verified-account')
        body=self.submission(sub.json()['current']);response=await self.catalog.post('/api/pg/staff/rudds/prep-count-drafts/'+review['sheet']['id']+'/submit',json=body,headers={'Idempotency-Key':str(uuid4())});self.assertEqual(response.status_code,404,response.text)

    async def test_sql_guards_immutability_complete_membership_and_legacy_freeze_with_flags_off(self):
        r,_=await self.issue_sheet();review=r.json()['current'];sub=await self.submit_sheet(review);self.assertEqual(sub.status_code,200,sub.text)
        async with self.pool.acquire() as c:
            for table in ('staff_sheets','staff_submissions'):
                with self.assertRaises(asyncpg.RaiseError):await c.execute('DELETE FROM prep_inventory.'+table)
            with self.assertRaises(asyncpg.RaiseError):await c.execute("UPDATE count_lines SET qty=99 WHERE id=$1",self.legacy_line)
            self.assertEqual(await c.fetchval("SELECT raw_record->>'note' FROM prep_inventory.legacy_count_sources WHERE source_id=$1",self.legacy_line),'Original untouched count')
            bad=self.submission(review);bad['lines'][0]['quantity']='-1'
            with self.assertRaises(asyncpg.RaiseError):
                await c.execute('''INSERT INTO prep_inventory.staff_submissions(sheet_id,store_id,revision,counter_name,credential_kind,submitted_by,note,quantities,submitted_body,request_key,request_fingerprint)
                    VALUES($1,'berts',2,$2,'bearer','DB probe',$3,$4,$5,$6,$7)''',UUID(review['sheet']['id']),bad['counter_name'],bad['note'],bad['lines'],{k:v for k,v in bad.items() if k!='pin'},uuid4(),bytes(32))
        with patch.dict(os.environ,{'STAFF_PREP_COUNTS_ENABLED':'false'}):
            legacy=await self.catalog.get('/api/pg/prepcount/berts/session');self.assertEqual(legacy.status_code,409,legacy.text)
            legacy=await self.catalog.post('/api/pg/prepcount/berts/session/'+str(self.legacy_count)+'/submit',json={});self.assertEqual(legacy.status_code,409,legacy.text)

    async def test_whole_restore_preserves_submissions_decisions_and_exact_acceptance_retry(self):
        r,_=await self.issue_sheet();review=r.json()['current'];sub=await self.submit_sheet(review);current=sub.json()['current'];key=str(uuid4())
        accepted,body=await self.accept(current,key=key);self.assertEqual(accepted.status_code,200,accepted.text)
        manifest=await backup.create_backup(self.source,fixtures.recovery.PG_DUMP,self.directory)
        self.assertEqual(manifest['tables']['prep_inventory.staff_decisions']['rows'],1)
        dsn=await self.target();self.assertEqual((await backup.verify_restore(dsn,self.directory))['status'],'verified')
        pool=await asyncpg.create_pool(dsn,min_size=1,max_size=3,init=server.db_pg._init_connection,statement_cache_size=0)
        old=server.db_pg._pool;server.db_pg._pool=pool
        try:
            replay,_=await self.accept(current,key=key,body=body);self.assertEqual(replay.status_code,200,replay.text)
            self.assertEqual(replay.json()['decision'],accepted.json()['decision']);self.assertEqual(replay.json()['observation'],accepted.json()['observation'])
            async with pool.acquire() as c:
                with self.assertRaises(asyncpg.RaiseError):await c.execute('DELETE FROM prep_inventory.staff_decisions')
        finally:server.db_pg._pool=old;await pool.close()

    async def test_database_acceptance_cannot_rewrite_staff_measurements_or_keep_orphan_observations(self):
        r,_=await self.issue_sheet();sub=await self.submit_sheet(r.json()['current']);current=sub.json()['current'];ident=UUID(current['sheet']['id'])
        body=counts.Decision(decision='accepted',note='Reviewed physical prep evidence',reviewed=True)
        async with self.pool.acquire() as c:
            plan=await counts.decision_preview(c,'berts',ident,body);before=await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'")
            with self.assertRaises(asyncpg.RaiseError) as refused:
                async with c.transaction():
                    await counts.lock_store(c,'berts')
                    wrong=observations.CountIn(**(current['sheet']['sheet_snapshot']['stamp']|dict(note=body.note)),complete_scope_confirmed=True,
                        lines=[observations.CountLine(product_version_id=self.p['id'],profile_id=self.u['id'],quantity='999',evidence='Invented scale measurement')])
                    plan['observation']=await observations.preview(c,'berts','count',wrong);key=uuid4()
                    event=(await observations.persist(c,'berts',plan['observation'],key,bytes(32),'synthetic-manager'))['event']
                    await c.execute('''INSERT INTO prep_inventory.staff_decisions(sheet_id,store_id,submission_id,decision,observation_id,note,review_snapshot,reviewed_by,request_key,request_fingerprint)
                        VALUES($1,'berts',$2,'accepted',$3,$4,$5,'synthetic-manager',$6,$7)''',ident,UUID(current['latest']['id']),UUID(event['id']),body.note,plan,key,bytes(32))
            self.assertIn('submitted measurements',str(refused.exception))
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.observations'),0)
            self.assertEqual(await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'"),before)

    async def test_racing_sheet_issuance_keeps_one_boundary_and_rejection_retains_history(self):
        body=self.sheet_body();p=await self.catalog.post(self.count_url+'/preview',json=body);self.assertEqual(p.status_code,200,p.text)
        payload=dict(sheet=body,expected_review_hash=p.json()['reviewHash'],reviewed=True)
        results=await asyncio.gather(self.issue_sheet(payload=payload),self.issue_sheet(payload=payload))
        self.assertEqual(sorted(r[0].status_code for r in results),[200,409]);review=next(r[0].json()['current'] for r in results if r[0].status_code==200)
        rejected,_=await self.accept(review,decision='rejected');self.assertEqual(rejected.status_code,200,rejected.text)
        r,_=await self.issue_sheet();self.assertEqual(r.status_code,200,r.text)
        self.assertNotEqual(r.json()['sheet']['id'],review['sheet']['id'])
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.staff_sheets'),2)
