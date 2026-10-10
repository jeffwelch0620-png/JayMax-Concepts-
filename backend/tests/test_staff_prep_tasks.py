"""Invented roster assignments and staff reads on disposable PostgreSQL."""
import asyncio, copy, os, unittest
from uuid import UUID, uuid4
from unittest.mock import patch
import asyncpg, httpx
from pydantic import ValidationError
import server, staff_prep_tasks as tasks, native_backup as backup
import test_prep_progress as fixtures


class StaffTaskValidationTests(unittest.TestCase):
    def test_staff_tasks_strict_assignment_and_read_boundary(self):
        b=dict(task_id=uuid4(),expected_revision=0,staff_member_id=uuid4(),note='Reviewed assignment')
        for change in ({'note':' '},{'expected_revision':True},{'expected_revision':-1},{'actor':'forged'},{'staff_member_id':'name'}):
            with self.assertRaises(ValidationError):tasks.Assignment(**(b|change))
        for value in (False,1,'true'):
            with self.assertRaises(ValidationError):tasks.Commit(assignment=b,expected_review_hash='a'*64,reviewed=value)
        with self.assertRaises(ValidationError):tasks.ReadIn(pin='1234',track='daily')
        with patch.dict(os.environ,{'STAFF_PREP_TASKS_ENABLED':'true','PREP_EXECUTION_ENABLED':'false'}):
            with self.assertRaises(server.HTTPException):tasks.enabled()


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PostgreSQL required')
class StaffTaskTests(fixtures.PrepProgressTests):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        flag=patch.dict(os.environ,{'STAFF_PREP_TASKS_ENABLED':'true'});flag.start();self.addCleanup(flag.stop)
        async with self.pool.acquire() as c:
            self.member=await c.fetchval("INSERT INTO staff_members(store_id,name) VALUES('berts','Invented cook A') RETURNING id")
            self.other_member=await c.fetchval("INSERT INTO staff_members(store_id,name) VALUES('berts','Invented cook B') RETURNING id")
            self.foreign_member=await c.fetchval("INSERT INTO staff_members(store_id,name) VALUES('rudds','Other location') RETURNING id")
            await c.execute("INSERT INTO staff_pins(store_id,pin) VALUES('berts','4826')")
            await c.execute((fixtures.fixtures.fixtures.recovery.counts.native.ROOT/'migrations/20261007_staff_prep_tasks.sql').read_text())
        self.owner=server._token({'id':'synthetic-task-owner','role':'owner','email':'owner@example.invalid'})
        self.portal=httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://test')
        self.addAsyncCleanup(self.portal.aclose)
        self.task_url='/api/pg/purchases/berts/staff-prep-tasks/2026-10-08'

    def assignment_body(self,task,revision=0,member=None):
        return dict(task_id=task['id'],expected_revision=revision,staff_member_id=str(member or self.member),note='Invented reviewed assignment')

    async def assignment_preview(self,body,path=None,token=None):
        return await self.portal.post((path or self.task_url)+'/preview',json=body,headers={'Authorization':'Bearer '+(token or self.owner)})

    async def assign(self,body=None,payload=None,key=None,token=None):
        if payload is None:
            p=await self.assignment_preview(body);self.assertEqual(p.status_code,200,p.text)
            payload=dict(assignment=body,expected_review_hash=p.json()['reviewHash'],reviewed=True)
        return await self.portal.post(self.task_url+'/assignments',json=payload,headers={'Authorization':'Bearer '+(token or self.owner),'Idempotency-Key':key or str(uuid4())})

    async def staff_plan(self,day='2026-10-08',member=None,track='daily',pin='4826',token=None,store='berts'):
        return await self.portal.post(f'/api/pg/staff/{store}/prep-task-plan',json=dict(pin=pin,day=day,track=track,staff_member_id=str(member) if member else None),headers={'Authorization':'Bearer '+token} if token else {})

    async def test_history_review_missing_task_progress_or_assignment_returns_conflict(self):
        _, task = await self.start()
        assigned = await self.assign(self.assignment_body(task))
        self.assertEqual(assigned.status_code,200,assigned.text)
        async with self.pool.acquire() as c:
            state = await tasks.state(c,'berts',tasks.date(2026,10,8),'daily')
        for missing in ('progress','assignment'):
            incomplete = copy.deepcopy(state)
            if missing=='progress':
                incomplete['execution']['task_progress'] = []
            else:
                incomplete['assignments'] = []
            with patch.object(tasks,'state',return_value=incomplete):
                held = await self.staff_plan(member=self.member)
            self.assertEqual(held.status_code,409,held.text)
        self.assertEqual((await self.staff_plan(member=self.member)).status_code,200)

    async def test_staff_tasks_assignment_reassignment_unassignment_preserve_actual_and_production(self):
        _,a,b=await self.pair();accounting=(await self.report(a,b)).json();d,t=await self.start()
        async with self.pool.acquire() as c:before=await c.fetchval('SELECT count(*) FROM prep_inventory.batch_movements')
        first=await self.assign(self.assignment_body(t));self.assertEqual(first.status_code,200,first.text)
        second=await self.assign(self.assignment_body(t,1,self.other_member));self.assertEqual(second.status_code,200,second.text)
        third=await self.assign(self.assignment_body(t,2)|{'staff_member_id':None});self.assertEqual(third.status_code,200,third.text)
        astate=third.json()['current']['assignments'][0]
        self.assertEqual(len(astate['history']),3);self.assertIsNone(astate['current']['staff_member_id'])
        self.assertEqual((await self.report(a,b)).json(),accounting)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.batch_movements'),before)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.execution_events'),1)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.batch_events'),0)

    async def test_staff_tasks_exact_retry_races_stale_revision_and_actor_binding(self):
        d,t=await self.start();body=self.assignment_body(t);p=await self.assignment_preview(body)
        payload=dict(assignment=body,expected_review_hash=p.json()['reviewHash'],reviewed=True);key=str(uuid4())
        race=await asyncio.gather(self.assign(payload=payload,key=key),self.assign(payload=payload,key=key))
        self.assertEqual([r.status_code for r in race],[200,200]);self.assertEqual(race[0].json()['assignment'],race[1].json()['assignment'])
        self.assertEqual((await self.assign(payload=payload)).status_code,409)
        newer=await self.assign(self.assignment_body(t,1,self.other_member));self.assertEqual(newer.status_code,200,newer.text)
        replay=await self.assign(payload=payload,key=key);self.assertEqual(replay.json()['assignment']['revision'],1)
        self.assertEqual(replay.json()['current']['assignments'][0]['current']['revision'],2)
        self.assertEqual((await self.assign(payload=payload|{'assignment':body|{'note':'Different'}},key=key)).status_code,409)
        other=server._token({'id':'synthetic-other-owner','role':'owner','email':'other@example.invalid'})
        self.assertEqual((await self.assign(payload=payload,key=key,token=other)).status_code,409)
        fresh=self.assignment_body(t,2);p=await self.assignment_preview(fresh);payload=dict(assignment=fresh,expected_review_hash=p.json()['reviewHash'],reviewed=True)
        race=await asyncio.gather(self.assign(payload=payload),self.assign(payload=payload));self.assertEqual(sorted(r.status_code for r in race),[200,409])

    async def test_staff_tasks_explicit_date_track_and_claimed_identity_never_fall_back(self):
        d,t=await self.start();await self.assign(self.assignment_body(t))
        r=await self.staff_plan(member=self.member);self.assertEqual(r.status_code,200,r.text)
        s=r.json();self.assertFalse(s['identity_verified']);self.assertEqual(s['credential_kind'],'shared_pin');self.assertEqual(s['tasks'][0]['id'],t['id'])
        for kwargs in ({'day':'2026-10-09'},{'track':'bulk'},{'member':self.other_member}):
            r=await self.staff_plan(**kwargs);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['tasks'],[])
        await self.write_execution(self.command(d,'reopen'),1)
        self.assertEqual((await self.staff_plan()).json()['tasks'],[])

    async def test_staff_tasks_roles_location_and_no_staff_writes_even_auth_disabled(self):
        d,t=await self.start();body=self.assignment_body(t)
        tokens={role:server._token({'id':'synthetic-'+role,'role':role,'email':role+'@example.invalid','locations':['berts']}) for role in ('staff','readonly','manager')}
        wrong=server._token({'id':'synthetic-wrong','role':'staff','email':'wrong@example.invalid','locations':['rudds']})
        for env in ('true','false'):
            with patch.dict(os.environ,{'AUTH_REQUIRED':env}):
                self.assertEqual((await self.staff_plan(pin='bad')).status_code,403)
                self.assertEqual((await self.staff_plan(pin='4826',token='invalid')).status_code,401)
                self.assertEqual((await self.staff_plan(token=wrong)).status_code,403)
                self.assertEqual((await self.staff_plan(token=tokens['readonly'])).status_code,403)
                r=await self.staff_plan(token=tokens['staff']);self.assertEqual(r.status_code,200,r.text)
                self.assertEqual((await self.assignment_preview(body,token=tokens['staff'])).status_code,403)
                self.assertEqual((await self.assignment_preview(body,token=tokens['readonly'])).status_code,403)
        self.assertEqual((await self.staff_plan(member=self.foreign_member)).status_code,422)
        self.assertEqual((await self.assignment_preview(body,path=self.task_url.replace('berts','rudds'))).status_code,409)
        self.assertEqual((await self.assignment_preview(body|{'staff_member_id':str(self.foreign_member)})).status_code,422)

    async def test_staff_tasks_roster_change_and_deactivation_hold_preview_retain_history(self):
        d,t=await self.start();body=self.assignment_body(t);p=await self.assignment_preview(body)
        payload=dict(assignment=body,expected_review_hash=p.json()['reviewHash'],reviewed=True)
        async with self.pool.acquire() as c:await c.execute('UPDATE staff_members SET name=$2 WHERE id=$1',self.member,'Invented changed name')
        self.assertEqual((await self.assign(payload=payload)).status_code,409)
        r=await self.assign(body);self.assertEqual(r.status_code,200,r.text)
        async with self.pool.acquire() as c:await c.execute('UPDATE staff_members SET active=false WHERE id=$1',self.member)
        s=(await self.staff_plan()).json();self.assertTrue(s['tasks'][0]['roster_changed']);self.assertFalse(s['tasks'][0]['assigned_member']['active'])
        self.assertEqual((await self.staff_plan(member=self.member)).status_code,422)
        self.assertEqual((await self.assignment_preview(self.assignment_body(t,1))).status_code,422)
        r=await self.portal.delete(f'/api/pg/staff/berts/members/{self.member}',headers={'Authorization':'Bearer '+self.owner});self.assertEqual(r.status_code,409,r.text)
        async with self.pool.acquire() as c:
            with self.assertRaises(asyncpg.ForeignKeyViolationError):await c.execute('DELETE FROM staff_members WHERE id=$1',self.member)

    async def test_staff_tasks_execution_change_holds_assignment_and_completed_progress_is_visible(self):
        d,t=await self.start();body=self.assignment_body(t);p=await self.assignment_preview(body)
        payload=dict(assignment=body,expected_review_hash=p.json()['reviewHash'],reviewed=True)
        batch=await self.production(output_quantity='2');await self.link(d,t,batch,1)
        self.assertEqual((await self.assign(payload=payload)).status_code,409)
        r=await self.assign(body);self.assertEqual(r.status_code,200,r.text)
        await self.write_execution(self.command(d,'finish',task_id=t['id']),2)
        self.assertEqual((await self.assignment_preview(self.assignment_body(t,1))).status_code,409)
        s=(await self.staff_plan()).json();self.assertEqual(s['tasks'][0]['progress']['status'],'complete')
        self.assertEqual(s['tasks'][0]['progress']['reviewed_base_quantity'],'2')

    async def test_staff_tasks_database_guards_forged_scope_progress_and_immutable_history(self):
        d,t=await self.start();body=self.assignment_body(t);p=(await self.assignment_preview(body)).json()['review']
        async def direct(c,review):
            return await c.execute('''INSERT INTO prep_inventory.task_assignments(store_id,task_id,revision,staff_member_id,note,recorded_by,review_snapshot,review_hash,request_key,request_fingerprint)
                VALUES('berts',$1,1,$2,$3,'synthetic-direct',$4,$5,$6,$5)''',UUID(t['id']),self.member,body['note'],review,bytes(32),uuid4())
        async with self.pool.acquire() as c:
            for path,value in ((('progress','reviewed_base_quantity'),'999'),(('member','name'),'Forged name'),(('assignment','task_id'),str(uuid4())),(('track',),'bulk'),(('execution_revision',),999)):
                forged=copy.deepcopy(p);parent=forged
                for k in path[:-1]:parent=parent[k]
                parent[path[-1]]=value
                with self.assertRaises(asyncpg.RaiseError):await direct(c,forged)
        r=await self.assign(body);self.assertEqual(r.status_code,200,r.text)
        async with self.pool.acquire() as c:
            for sql in ('UPDATE prep_inventory.task_assignments SET note=\'changed\'','DELETE FROM prep_inventory.task_assignments'):
                with self.assertRaises(asyncpg.RaiseError):await c.execute(sql)
            self.assertFalse(await c.fetchval("SELECT EXISTS(SELECT 1 FROM pg_class c,aclexplode(c.relacl) a WHERE c.oid='prep_inventory.task_assignments'::regclass AND a.grantee<>c.relowner)"))

    async def test_staff_tasks_flags_off_hold_legacy_reads_and_completion_before_mutation(self):
        d,t=await self.start()
        with patch.dict(os.environ,{'STAFF_PREP_TASKS_ENABLED':'false'}):
            self.assertEqual((await self.staff_plan()).status_code,503)
            for path,body in (('prepsheet',{'pin':'4826','track':'daily'}),('prepsheet/complete',{'pin':'4826','listId':str(self.old_list),'taskId':str(uuid4()),'batches':1,'doneBy':'Invented cook'})):
                r=await self.portal.post('/api/pg/staff/berts/'+path,json=body);self.assertEqual(r.status_code,409,r.text)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_logs'),0)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.task_assignments'),0)

    async def test_staff_tasks_restore_preserves_exact_retry_and_private_history(self):
        d,t=await self.start();body=self.assignment_body(t);p=await self.assignment_preview(body)
        payload=dict(assignment=body,expected_review_hash=p.json()['reviewHash'],reviewed=True);key=str(uuid4())
        r=await self.assign(payload=payload,key=key);self.assertEqual(r.status_code,200,r.text)
        before=(await self.staff_plan()).json()
        manifest=await backup.create_backup(self.source,fixtures.fixtures.fixtures.recovery.PG_DUMP,self.directory)
        self.assertEqual(manifest['tables']['prep_inventory.task_assignments']['rows'],1)
        dsn=await self.target();self.assertEqual((await backup.verify_restore(dsn,self.directory))['status'],'verified')
        pool=await asyncpg.create_pool(dsn,min_size=1,max_size=2,init=fixtures.fixtures.fixtures.recovery.db_pg._init_connection)
        old=server.db_pg._pool;server.db_pg._pool=pool
        try:
            self.assertEqual((await self.staff_plan()).json(),before)
            replay=await self.assign(payload=payload,key=key);self.assertEqual(replay.status_code,200,replay.text);self.assertTrue(replay.json()['replayed'])
            self.assertEqual(replay.json()['assignment'],r.json()['assignment'])
            async with pool.acquire() as c:self.assertFalse(await c.fetchval("SELECT EXISTS(SELECT 1 FROM pg_class c,aclexplode(c.relacl) a WHERE c.oid='prep_inventory.task_assignments'::regclass AND a.grantee<>c.relowner)"))
        finally:server.db_pg._pool=old;await pool.close()

    async def test_staff_tasks_retry_after_reopen_and_new_draft_confirms_original_assignment(self):
        d,t=await self.start();b=self.assignment_body(t);p=await self.assignment_preview(b)
        payload=dict(assignment=b,expected_review_hash=p.json()['reviewHash'],reviewed=True);key=str(uuid4())
        first=await self.assign(payload=payload,key=key);self.assertEqual(first.status_code,200,first.text)
        await self.write_execution(self.command(d,'reopen'),1);new=await self.known_draft(version=1)
        replay=await self.assign(payload=payload,key=key);self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json()['assignment'],first.json()['assignment'])
        self.assertEqual(replay.json()['assignment_history'],first.json()['assignment_history'])
        self.assertEqual(replay.json()['current']['execution']['draft_version_id'],new['id'])
        self.assertIsNone(replay.json()['current']['assignments'][0]['current'])
