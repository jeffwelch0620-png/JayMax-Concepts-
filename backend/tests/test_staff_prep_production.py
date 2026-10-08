"""Invented staff production, explicit manager decisions and atomic recovery."""
import asyncio,copy,os,unittest
from uuid import UUID,uuid4
from unittest.mock import patch
import asyncpg
from pydantic import ValidationError
import staff_prep_production as production,prep_execution as execution,server,native_backup as backup
from purchase_parser import fingerprint
import test_staff_prep_tasks as fixtures


class StaffProductionValidationTests(unittest.TestCase):
    def test_staff_production_strict_decision_identity_review_and_measurement(self):
        b=dict(root_id=uuid4(),expected_revision=0,task_id=uuid4(),staff_member_id=uuid4(),assignment_id=uuid4(),note='Measured',kind='withdraw')
        with self.assertRaises(ValidationError):production.Submission(**b)
        for change in ({'task_complete':1},{'task_complete':'true'},{'decision':'rejected','task_complete':True},{'note':' '},{'recorded_by':'forged'}):
            with self.assertRaises(ValidationError):production.Decision(**(dict(submission_id=uuid4(),decision='accepted',task_complete=False,note='Review')|change))
        for value in (False,1,'true'):
            with self.assertRaises(ValidationError):production.DecisionCommit(submission_id=uuid4(),decision='accepted',task_complete=False,note='Review',reviewed=value,expected_review_hash='a'*64)


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PostgreSQL required')
class StaffProductionTests(fixtures.StaffTaskTests):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        flag=patch.dict(os.environ,{'STAFF_PREP_PRODUCTION_ENABLED':'true'});flag.start();self.addCleanup(flag.stop)
        if self._testMethodName!='test_staff_production_additive_install_keeps_old_execution_preview_and_retry':
            async with self.pool.acquire() as c:await c.execute((fixtures.fixtures.fixtures.fixtures.recovery.counts.native.ROOT/'migrations/20261007_staff_prep_production.sql').read_text())
        self.staff_url='/api/pg/staff/berts/prep-production/2026-10-08'
        self.production_url='/api/pg/purchases/berts/staff-prep-production/2026-10-08'

    async def submission(self,quantity='2',**changes):
        d,t=await self.start();a=await self.assign(self.assignment_body(t));self.assertEqual(a.status_code,200,a.text)
        batch=await self.entry(performed_at='2026-10-08T10:00:00-04:00',business_date='2026-10-08',output_quantity=quantity)
        return dict(root_id=str(uuid4()),expected_revision=0,task_id=t['id'],staff_member_id=str(self.member),assignment_id=a.json()['assignment']['id'],kind='submit',batch=batch,note='Claimed staff measured production')|changes

    async def staff_preview(self,body,token=None,pin='4826',url=None):
        return await self.portal.post((url or self.staff_url)+'/preview',json=dict(pin=pin,submission=body),headers={'Authorization':'Bearer '+token} if token else {})
    async def submit(self,body=None,payload=None,key=None,token=None):
        if payload is None:
            p=await self.staff_preview(body,token);self.assertEqual(p.status_code,200,p.text)
            payload=dict(pin='4826',submission=body,expected_review_hash=p.json()['reviewHash'],reviewed=True)
        return await self.portal.post(self.staff_url+'/submissions',json=payload,headers=({'Authorization':'Bearer '+token} if token else {})|{'Idempotency-Key':key or str(uuid4())})
    def decision(self,event,accept=True,complete=False):return dict(submission_id=event['id'],decision='accepted' if accept else 'rejected',task_complete=complete,note='Manager inspected measured output')
    async def decision_preview(self,body,token=None):return await self.portal.post(self.production_url+'/preview',json=body,headers={'Authorization':'Bearer '+(token or self.owner)})
    async def decide(self,body=None,payload=None,key=None,token=None):
        if payload is None:
            p=await self.decision_preview(body,token);self.assertEqual(p.status_code,200,p.text);payload=body|dict(expected_review_hash=p.json()['reviewHash'],reviewed=True)
        return await self.portal.post(self.production_url+'/decisions',json=payload,headers={'Authorization':'Bearer '+(token or self.owner),'Idempotency-Key':key or str(uuid4())})

    async def test_review_corrections_production_author_and_claimed_roster_cannot_accept(self):
        body = await self.submission()
        first = await self.submit(body, token=self.owner)
        self.assertEqual(first.status_code, 200, first.text)
        first_event = first.json()['submission']
        revised = await self.submit(body | dict(expected_revision=1, note='Staff corrected measured evidence'))
        self.assertEqual(revised.status_code, 200, revised.text)
        decision = self.decision(revised.json()['submission'])
        self.assertEqual((await self.decision_preview(decision)).status_code, 403)
        roster = server._token(dict(id=str(self.member), email='roster@example.invalid', role='owner'))
        self.assertEqual((await self.decision_preview(decision, roster)).status_code, 403)
        reviewer = server._token(dict(id='independent-production-reviewer', email='reviewer@example.invalid', role='owner'))
        preview = await self.decision_preview(decision, reviewer)
        self.assertEqual(preview.status_code, 200, preview.text)
        payload = decision | dict(expected_review_hash=preview.json()['reviewHash'], reviewed=True)
        self.assertEqual((await self.decide(payload=payload)).status_code, 403)
        self.assertEqual((await self.decide(payload=payload, token=roster)).status_code, 403)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.batch_events'), 0)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.staff_production_decisions'), 0)
        accepted = await self.decide(payload=payload, token=reviewer)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()['history']['events'][0]['id'], first_event['id'])

    async def test_review_corrections_production_root_collision_across_stores_and_revision_ids(self):
        body = await self.submission()
        first = await self.submit(body)
        self.assertEqual(first.status_code, 200, first.text)
        revised = await self.submit(body | dict(expected_revision=1, note='New staff evidence'))
        self.assertEqual(revised.status_code, 200, revised.text)
        collision = body | dict(root_id=revised.json()['submission']['id'])
        self.assertEqual((await self.staff_preview(collision)).status_code, 409)
        payload = dict(pin='4826', submission=collision, expected_review_hash='a'*64, reviewed=True)
        self.assertEqual((await self.submit(payload=payload)).status_code, 409)
        foreign = self.staff_url.replace('/berts/', '/rudds/')
        self.assertEqual((await self.staff_preview(body, token=self.owner, url=foreign)).status_code, 409)
        command = await self.portal.post(foreign+'/submissions',json=payload | {'submission':body},
            headers={'Authorization':'Bearer '+self.owner,'Idempotency-Key':str(uuid4())})
        self.assertEqual(command.status_code,409,command.text)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.staff_production_submissions'), 2)

    async def test_review_corrections_production_cross_module_key_rolls_back_all_effects(self):
        body = await self.submission()
        measured = await self.production()
        submitted = await self.submit(body)
        self.assertEqual(submitted.status_code, 200, submitted.text)
        decision = self.decision(submitted.json()['submission'], complete=True)
        before = await self.execution_state()
        conflict = await self.decide(decision, key=measured['request_key'])
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertIn('retained history', conflict.json()['detail'])
        self.assertEqual(await self.execution_state(), before)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.batch_events'), 1)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.staff_production_decisions'), 0)
        accepted = await self.decide(decision)
        self.assertEqual(accepted.status_code, 200, accepted.text)

    async def test_staff_production_submission_posts_nothing_accepts_partial_once_and_actual_is_independent(self):
        _,a,b=await self.pair();actual=(await self.report(a,b)).json();body=await self.submission('2.000000000001');r=await self.submit(body);self.assertEqual(r.status_code,200,r.text)
        s=r.json()['submission'];self.assertFalse(s['review_snapshot']['identity_verified']);self.assertEqual(s['credential_kind'],'shared_pin')
        self.assertNotIn('pin',s['review_snapshot']);self.assertNotIn('pin',s['review_snapshot']['submission'])
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.batch_events'),0)
        r=await self.decide(self.decision(s));self.assertEqual(r.status_code,200,r.text);ack=r.json()
        self.assertEqual(ack['batch_event']['review_snapshot']['usableBaseOutput'],'2.000000000001')
        self.assertEqual(ack['current']['execution']['task_progress'][0]['status'],'in_progress');self.assertIsNone(ack['finish_event'])
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.batch_events'),1)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_logs'),0)
        self.assertEqual((await self.report(a,b)).json(),actual)
        other=body|dict(root_id=str(uuid4()),batch=body['batch']|dict(output_quantity='1',performed_at='2026-10-08T11:00:00-04:00'))
        r=await self.submit(other);self.assertEqual(r.status_code,200,r.text);r=await self.decide(self.decision(r.json()['submission'],complete=True));self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['current']['execution']['task_progress'][0]['status'],'complete');self.assertEqual(r.json()['finish_event']['action'],'finish')

    async def test_staff_production_reject_revise_withdraw_preserve_original_and_make_no_food(self):
        body=await self.submission();r=await self.submit(body);s=r.json()['submission'];r=await self.decide(self.decision(s,False));self.assertEqual(r.status_code,200,r.text)
        revised=body|dict(expected_revision=1,batch=body['batch']|dict(output_quantity='3'),note='Corrected measured output')
        r=await self.submit(revised);self.assertEqual(r.status_code,200,r.text);self.assertEqual(len(r.json()['history']['events']),2)
        r=await self.submit(revised|dict(expected_revision=2,kind='withdraw',batch=None,note='Withdraw erroneous submission'));self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(len(r.json()['history']['events']),3);self.assertEqual(len(r.json()['history']['decisions']),1)
        self.assertEqual((await self.staff_preview(revised|{'expected_revision':3})).status_code,409)
        self.assertEqual((await self.decision_preview(self.decision(s))).status_code,409)
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.batch_events'),0)

    async def test_staff_production_assignment_roster_scope_and_recipe_changes_hold_acceptance_rejection_stays_available(self):
        body=await self.submission();r=await self.submit(body);s=r.json()['submission'];d=self.decision(s);p=await self.decision_preview(d);payload=d|dict(expected_review_hash=p.json()['reviewHash'],reviewed=True)
        async with self.pool.acquire() as c:await c.execute('UPDATE staff_members SET name=$2 WHERE id=$1',self.member,'Changed claimed name')
        self.assertEqual((await self.decide(payload=payload)).status_code,409)
        self.assertEqual((await self.staff_preview(body|{'root_id':str(uuid4())})).status_code,409)
        r=await self.decide(self.decision(s,False));self.assertEqual(r.status_code,200,r.text)
        self.assertEqual((await self.staff_preview(body,url=self.staff_url.replace('2026-10-08','2026-10-09'))).status_code,409)

    async def test_staff_production_races_bind_actor_payload_root_and_decision_no_double_production(self):
        body=await self.submission();p=await self.staff_preview(body);payload=dict(pin='4826',submission=body,expected_review_hash=p.json()['reviewHash'],reviewed=True);key=str(uuid4())
        race=await asyncio.gather(self.submit(payload=payload,key=key),self.submit(payload=payload,key=key));self.assertEqual([r.status_code for r in race],[200,200]);s=race[0].json()['submission']
        self.assertEqual((await self.submit(payload=payload)).status_code,409)
        self.assertEqual((await self.submit(payload=payload|{'submission':body|{'note':'Changed'}},key=key)).status_code,409)
        other=server._token({'id':'different-staff','email':'different@example.invalid','role':'staff','locations':['berts']});self.assertEqual((await self.submit(payload=payload,key=key,token=other)).status_code,409)
        d=self.decision(s,complete=True);p=await self.decision_preview(d);dp=d|dict(expected_review_hash=p.json()['reviewHash'],reviewed=True);dk=str(uuid4())
        race=await asyncio.gather(self.decide(payload=dp,key=dk),self.decide(payload=dp,key=dk));self.assertEqual([r.status_code for r in race],[200,200]);self.assertEqual(race[0].json()['batch_event'],race[1].json()['batch_event'])
        self.assertEqual((await self.decide(payload=dp)).status_code,409)
        self.assertEqual((await self.staff_preview(body|{'expected_revision':1})).status_code,409)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.batch_events'),1)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.execution_events'),3)

    async def test_staff_production_permissions_flags_and_strict_booleans_never_grant_manager_access(self):
        body=await self.submission()
        for env in ('true','false'):
            with patch.dict(os.environ,{'AUTH_REQUIRED':env}):
                self.assertEqual((await self.staff_preview(body,pin='bad')).status_code,403)
                self.assertEqual((await self.staff_preview(body,token='invalid')).status_code,401)
                wrong=server._token({'id':'wrong-staff','email':'wrong@example.invalid','role':'staff','locations':['rudds']});self.assertEqual((await self.staff_preview(body,token=wrong)).status_code,403)
        for field in ('calendar_date_confirmed','single_output_confirmed'):
            self.assertEqual((await self.staff_preview(body|{'batch':body['batch']|{field:1}})).status_code,422)
        r=await self.submit(body);s=r.json()['submission'];staff=server._token({'id':'local-staff','email':'local@example.invalid','role':'staff','locations':['berts']})
        self.assertEqual((await self.decision_preview(self.decision(s),staff)).status_code,403)
        new=body|dict(root_id=str(uuid4()))
        p=await self.staff_preview(new,token=staff);self.assertEqual(p.status_code,200,p.text)
        r=await self.submit(payload=dict(pin='not-needed-with-valid-bearer',submission=new,expected_review_hash=p.json()['reviewHash'],reviewed=True),token=staff)
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['submission']['credential_kind'],'bearer')
        self.assertEqual(r.json()['submission']['submitted_by'],'local-staff')
        setup=await self.portal.post(self.staff_url+'/setup',params={'staff_member_id':str(self.member)},json={'pin':''},headers={'Authorization':'Bearer '+staff})
        self.assertEqual(setup.status_code,200,setup.text)
        self.assertEqual(len(setup.json()['submissions']),2)
        with patch.dict(os.environ,{'STAFF_PREP_TASKS_ENABLED':'false'}):self.assertEqual((await self.staff_preview(body)).status_code,503)

    async def test_staff_production_partial_failure_rolls_back_batch_link_finish_and_decision(self):
        body=await self.submission();s=(await self.submit(body)).json()['submission'];before=await self.execution_state()
        with patch.object(execution,'persist',side_effect=server.HTTPException(409,'Synthetic link failure')):
            r=await self.decide(self.decision(s,complete=True));self.assertEqual(r.status_code,409,r.text)
        self.assertEqual(await self.execution_state(),before)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.batch_events'),0)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.staff_production_decisions'),0)
            await c.execute("CREATE FUNCTION public.fail_staff_decision() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Synthetic decision failure'; END $$")
            await c.execute('CREATE TRIGGER decision_failure BEFORE INSERT ON prep_inventory.staff_production_decisions FOR EACH ROW EXECUTE FUNCTION public.fail_staff_decision()')
        with self.assertRaises(asyncpg.RaiseError):await self.decide(self.decision(s,complete=True))
        self.assertEqual(await self.execution_state(),before)
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.batch_movements'),0)

    async def test_staff_production_private_sql_rejects_forged_submissions_orphan_effects_and_history_changes(self):
        body=await self.submission();p=(await self.staff_preview(body)).json()['review']
        async with self.pool.acquire() as c:
            for path,value in ((('sources','progress','reviewed_base_quantity'),'999'),(('identity_verified',),True),(('submission','task_id'),str(uuid4()))):
                forged=copy.deepcopy(p);parent=forged
                for k in path[:-1]:parent=parent[k]
                parent[path[-1]]=value
                with self.assertRaises(asyncpg.RaiseError):
                    await c.execute('''INSERT INTO prep_inventory.staff_production_submissions(id,store_id,root_id,revision,task_id,staff_member_id,assignment_id,kind,note,submitted_by,credential_kind,review_snapshot,review_hash,request_key,request_fingerprint)
                        VALUES($1,'berts',$1,1,$2,$3,$4,'submit',$5,'shared-pin','shared_pin',$6,$7,$8,$7)''',UUID(body['root_id']),UUID(body['task_id']),self.member,UUID(body['assignment_id']),body['note'],forged,bytes(32),uuid4())
        s=(await self.submit(body)).json()['submission'];p=await self.decision_preview(self.decision(s))
        async with self.pool.acquire() as c:
            with self.assertRaises(asyncpg.RaiseError):
                async with c.transaction():await production.batches.persist(c,'berts',p.json()['review']['batch'],uuid4(),b'x'*32,'synthetic-direct')
            for sql in ('UPDATE prep_inventory.staff_production_submissions SET note=\'Changed\'','DELETE FROM prep_inventory.staff_production_submissions'):
                with self.assertRaises(asyncpg.RaiseError):await c.execute(sql)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.batch_events'),0)

    async def test_staff_production_additive_install_keeps_old_execution_preview_and_retry(self):
        d,t=await self.start();old=await self.execution_state();command=self.command(d,'reopen');p=await self.preview_execution(command,1);payload=dict(command=command,expected_review_hash=p.json()['reviewHash'],reviewed=True)
        async with self.pool.acquire() as c:await c.execute((fixtures.fixtures.fixtures.fixtures.recovery.counts.native.ROOT/'migrations/20261007_staff_prep_production.sql').read_text())
        await self.pool.expire_connections();self.assertEqual(await self.execution_state(),old)
        r=await self.write_execution(payload=payload,version=1);self.assertEqual(r.status_code,200,r.text);self.assertNotIn('created_xid',r.json()['event'])

    async def test_staff_production_whole_restore_retries_original_pair_after_batch_correction(self):
        body=await self.submission();s=(await self.submit(body)).json()['submission'];d=self.decision(s);p=await self.decision_preview(d);payload=d|dict(expected_review_hash=p.json()['reviewHash'],reviewed=True);key=str(uuid4())
        first=await self.decide(payload=payload,key=key);self.assertEqual(first.status_code,200,first.text)
        await self.correct(first.json()['batch_event'],'1');before=await self.execution_state()
        manifest=await backup.create_backup(self.source,fixtures.fixtures.fixtures.fixtures.recovery.PG_DUMP,self.directory)
        self.assertEqual(manifest['tables']['prep_inventory.staff_production_decisions']['rows'],1)
        dsn=await self.target();self.assertEqual((await backup.verify_restore(dsn,self.directory))['status'],'verified')
        pool=await asyncpg.create_pool(dsn,min_size=1,max_size=2,init=fixtures.fixtures.fixtures.fixtures.recovery.db_pg._init_connection);old=server.db_pg._pool;server.db_pg._pool=pool
        try:
            replay=await self.decide(payload=payload,key=key);self.assertEqual(replay.status_code,200,replay.text);self.assertTrue(replay.json()['replayed'])
            for field in ('decision','batch_event','execution_event'):self.assertEqual(replay.json()[field],first.json()[field])
            self.assertEqual(replay.json()['current']['execution'],before)
            async with pool.acquire() as c:
                for table in ('staff_production_submissions','staff_production_decisions'):
                    self.assertFalse(await c.fetchval("SELECT EXISTS(SELECT 1 FROM pg_class c,aclexplode(c.relacl) a WHERE c.oid=$1::regclass AND a.grantee<>c.relowner)",'prep_inventory.'+table))
        finally:server.db_pg._pool=old;await pool.close()
