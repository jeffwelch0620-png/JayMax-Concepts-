"""Invented manager commands and exactly-once evidence references on disposable PG."""
import asyncio, os, unittest
from unittest.mock import patch
from uuid import UUID, uuid4
import asyncpg
from pydantic import ValidationError
import prep_execution as execution, server, native_backup as backup
import test_prep_day_tasks as fixtures
import test_prep_batches as batches


class ExecutionValidationTests(unittest.TestCase):
    def test_strict_review_and_action_evidence(self):
        command=dict(action='release',draft_version_id=uuid4(),reason='Reviewed service')
        self.assertEqual(execution.Command(**command).action,'release')
        for changes in ({'task_id':uuid4()},{'action':'complete'},{'reason':' '},{'actor':'forged'}):
            with self.assertRaises(ValidationError):execution.Command(**(command|changes))
        for reviewed in (False,1,'true'):
            with self.assertRaises(ValidationError):execution.Commit(command=command,expected_review_hash='a'*64,reviewed=reviewed)
        with patch.dict(os.environ,{'PREP_EXECUTION_ENABLED':'true','PREP_DAY_TASKS_ENABLED':'false'}):
            with self.assertRaises(server.HTTPException):execution.enabled()


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PG required')
class PrepExecutionTests(fixtures.PrepDayTaskTests):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        flag=patch.dict(os.environ,{'PREP_EXECUTION_ENABLED':'true'});flag.start();self.addCleanup(flag.stop)
        async with self.pool.acquire() as c:
            await c.execute((fixtures.recovery.counts.native.ROOT/'migrations/20261005_prep_opening_sources.sql').read_text())
            await c.execute((fixtures.recovery.counts.native.ROOT/'migrations/20261007_prep_execution.sql').read_text())

    entry=batches.PrepBatchTests.entry
    async def production(self,**changes):
        body=await self.entry(performed_at='2026-10-08T10:00:00-04:00',business_date='2026-10-08',**changes)
        p=await self.catalog.post('/api/pg/purchases/berts/prep-batches/preview',json=body);self.assertEqual(p.status_code,200,p.text)
        r=await self.catalog.post('/api/pg/purchases/berts/prep-batches',json={'batch':body,'expected_review_hash':p.json()['reviewHash'],'reviewed':True},headers={'Idempotency-Key':str(uuid4())});self.assertEqual(r.status_code,200,r.text)
        return r.json()['event']

    async def known_draft(self,version=0):
        override=dict(planning_version_id=self.standing['id'],kind='fixed_quantity',quantity='4',reason='Reviewed planned output')
        r=await self.write_day(self.draft_body(overrides=[override]),version=version);self.assertEqual(r.status_code,200,r.text)
        return r.json()['draft']

    def command(self,draft,action='release',**changes):return dict(action=action,draft_version_id=draft['id'],reason='Manager reviewed quantities and measured production')|changes
    async def preview_execution(self,command,version=0,store='berts',track='daily'):
        return await self.catalog.post(f'/api/pg/purchases/{store}/prep-execution/2026-10-08/preview',params={'track':track},json=command,headers={'If-Match':str(version)})
    async def write_execution(self,command=None,version=0,key=None,payload=None,track='daily'):
        if payload is None:
            p=await self.preview_execution(command,version,track=track);self.assertEqual(p.status_code,200,p.text)
            payload=dict(command=command,expected_review_hash=p.json()['reviewHash'],reviewed=True)
        return await self.catalog.post('/api/pg/purchases/berts/prep-execution/2026-10-08/commands',params={'track':track},json=payload,headers={'If-Match':str(version),'Idempotency-Key':key or str(uuid4())})
    async def execution_state(self):
        r=await self.catalog.get('/api/pg/purchases/berts/prep-execution/2026-10-08');self.assertEqual(r.status_code,200,r.text);return r.json()

    async def test_release_reopen_edits_and_exact_retry_retain_history(self):
        d=await self.known_draft();key=str(uuid4());command=self.command(d)
        p=await self.preview_execution(command);payload=dict(command=command,expected_review_hash=p.json()['reviewHash'],reviewed=True)
        raced=await asyncio.gather(self.write_execution(key=key,payload=payload),self.write_execution(key=key,payload=payload))
        self.assertEqual([r.status_code for r in raced],[200,200]);self.assertEqual(raced[0].json()['event'],raced[1].json()['event'])
        self.assertEqual((await self.preview_day(version=1)).status_code,409)
        reopened=await self.write_execution(self.command(d,'reopen'),version=1);self.assertEqual(reopened.status_code,200,reopened.text)
        new=await self.known_draft(version=1);self.assertNotEqual(new['id'],d['id'])
        replay=await self.write_execution(key=key,payload=payload);self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json()['current']['status'],'draft');self.assertEqual(replay.json()['current']['revision'],2)
        self.assertEqual((await self.write_execution(key=key,payload=payload|{'command':command|{'reason':'Changed'}})).status_code,409)
        self.assertEqual((await self.preview_execution(self.command(d),2)).status_code,409)
        self.assertEqual((await self.write_execution(self.command(new),2)).status_code,200)

    async def test_release_rejects_unknown_quantities_and_changed_counts_or_plans(self):
        r=await self.write_day();self.assertEqual(r.status_code,200,r.text)
        self.assertEqual((await self.preview_execution(self.command(r.json()['draft']))).status_code,409)
        count=await self.prep_count();r=await self.write_day(self.draft_body(count_event_id=count['id']),version=1);d=r.json()['draft']
        await self.prep_count('3',stamp='2026-10-07T23:00:00-04:00')
        self.assertEqual((await self.preview_execution(self.command(d))).status_code,409)
        d=await self.known_draft(version=2);p=await self.preview_execution(self.command(d));self.assertEqual(p.status_code,200,p.text)
        self.assertEqual((await self.edit(self.payload(track='daily',weekday_par='9'),version=1)).status_code,200)
        r=await self.write_execution(payload=dict(command=self.command(d),expected_review_hash=p.json()['reviewHash'],reviewed=True));self.assertEqual(r.status_code,409,r.text)

    async def test_completion_is_reference_only_and_actual_output_can_differ_from_plan(self):
        _,a,b=await self.pair();accounting=(await self.report(a,b)).json()
        d=await self.known_draft();r=await self.write_execution(self.command(d));self.assertEqual(r.status_code,200,r.text)
        task=r.json()['current']['tasks'][0];batch=await self.production(output_quantity='3')
        async with self.pool.acquire() as c:before=await c.fetchval('SELECT count(*) FROM prep_inventory.batch_movements')
        command=self.command(d,'complete',task_id=task['id'],batch_event_id=batch['id']);key=str(uuid4())
        p=await self.preview_execution(command,1);payload=dict(command=command,expected_review_hash=p.json()['reviewHash'],reviewed=True)
        raced=await asyncio.gather(self.write_execution(version=1,key=key,payload=payload),self.write_execution(version=1,key=key,payload=payload))
        self.assertEqual([r.status_code for r in raced],[200,200]);self.assertEqual(len(raced[0].json()['current']['completions']),1)
        self.assertEqual((await self.preview_execution(command,2)).status_code,409)
        self.assertEqual((await self.preview_execution(self.command(d,'reopen'),2)).status_code,409)
        self.assertEqual(accounting,(await self.report(a,b)).json())
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.batch_events'),1)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.batch_movements'),before)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_logs'),0)
        self.assertEqual(raced[0].json()['event']['review_snapshot']['batch']['review_snapshot']['usableBaseOutput'],'3')
        self.assertEqual(task['planned_quantity'],'4')

    async def test_concurrent_completion_keys_stale_batch_and_cross_location_are_held(self):
        d=await self.known_draft();r=await self.write_execution(self.command(d));task=r.json()['current']['tasks'][0]
        batch=await self.production();command=self.command(d,'complete',task_id=task['id'],batch_event_id=batch['id'])
        self.assertEqual((await self.preview_execution(command,1,store='rudds')).status_code,409)
        p=await self.preview_execution(command,1);payload=dict(command=command,expected_review_hash=p.json()['reviewHash'],reviewed=True)
        raced=await asyncio.gather(self.write_execution(version=1,payload=payload),self.write_execution(version=1,payload=payload))
        self.assertEqual(sorted(r.status_code for r in raced),[200,409])
        change={'kind':'void','reason':'Erroneous measured production'}
        path=f"/api/pg/purchases/berts/prep-batches/{batch['id']}"
        p=await self.catalog.post(path+'/change-preview',json=change);self.assertEqual(p.status_code,200,p.text)
        r=await self.catalog.post(path+'/changes',json=dict(change=change,expected_review_hash=p.json()['reviewHash'],reviewed=True),headers={'Idempotency-Key':str(uuid4())});self.assertEqual(r.status_code,200,r.text)
        s=await self.execution_state();self.assertTrue(s['completions'][0]['needs_review']);self.assertEqual(s['completions'][0]['effective_batch']['kind'],'void')
        self.assertEqual((await self.preview_execution(command,2)).status_code,409)

    async def test_linked_batch_cannot_complete_another_track_task(self):
        d=await self.known_draft();r=await self.write_execution(self.command(d));task=r.json()['current']['tasks'][0];batch=await self.production()
        self.assertEqual((await self.write_execution(self.command(d,'complete',task_id=task['id'],batch_event_id=batch['id']),1)).status_code,200)
        r=await self.edit(self.payload(track='bulk',schedule='recurring',recur_days=[3],fixed_quantity='4'),version=1);self.assertEqual(r.status_code,200,r.text)
        bulk=await self.write_day(self.draft_body(track='bulk'));self.assertEqual(bulk.status_code,200,bulk.text);d=bulk.json()['draft']
        r=await self.write_execution(self.command(d),track='bulk');self.assertEqual(r.status_code,200,r.text)
        command=self.command(d,'complete',task_id=r.json()['current']['tasks'][0]['id'],batch_event_id=batch['id'])
        self.assertEqual((await self.preview_execution(command,1,track='bulk')).status_code,409)

    async def test_execution_guards_atomic_rollback_immutability_and_flag_off_draft_hold(self):
        d=await self.known_draft();command=self.command(d);p=await self.preview_execution(command)
        async with self.pool.acquire() as c:
            before=await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'")
            await c.execute("""CREATE FUNCTION public.fail_execution_test() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Invented execution failure' USING ERRCODE='23514'; END $$;
                CREATE TRIGGER failed_execution_test AFTER INSERT ON prep_inventory.execution_events FOR EACH ROW EXECUTE FUNCTION public.fail_execution_test();""")
        with self.assertRaises(asyncpg.CheckViolationError):await self.write_execution(payload=dict(command=command,expected_review_hash=p.json()['reviewHash'],reviewed=True))
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.execution_events'),0)
            self.assertEqual(await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'"),before)
            await c.execute('DROP TRIGGER failed_execution_test ON prep_inventory.execution_events')
        r=await self.write_execution(command);self.assertEqual(r.status_code,200,r.text)
        with patch.dict(os.environ,{'PREP_EXECUTION_ENABLED':'false'}):self.assertEqual((await self.preview_day(version=1)).status_code,409)
        async with self.pool.acquire() as c:
            for sql in ('DELETE FROM prep_inventory.execution_events',"UPDATE prep_inventory.execution_events SET action='reopen'"):
                with self.assertRaises(asyncpg.RaiseError):await c.execute(sql)

    async def test_execution_history_and_linked_production_survive_whole_sql_restore(self):
        d=await self.known_draft();r=await self.write_execution(self.command(d));task=r.json()['current']['tasks'][0];batch=await self.production()
        command=self.command(d,'complete',task_id=task['id'],batch_event_id=batch['id']);p=await self.preview_execution(command,1)
        payload=dict(command=command,expected_review_hash=p.json()['reviewHash'],reviewed=True);key=str(uuid4())
        r=await self.write_execution(version=1,key=key,payload=payload);self.assertEqual(r.status_code,200,r.text);before=await self.execution_state()
        manifest=await backup.create_backup(self.source,fixtures.recovery.PG_DUMP,self.directory)
        self.assertEqual(manifest['tables']['prep_inventory.execution_events']['rows'],2)
        dsn=await self.target();self.assertEqual((await backup.verify_restore(dsn,self.directory))['status'],'verified')
        pool=await asyncpg.create_pool(dsn,min_size=1,max_size=2,init=fixtures.recovery.db_pg._init_connection);old=server.db_pg._pool;server.db_pg._pool=pool
        try:
            self.assertEqual(await self.execution_state(),before)
            replay=await self.write_execution(version=1,key=key,payload=payload);self.assertEqual(replay.status_code,200,replay.text);self.assertTrue(replay.json()['replayed'])
        finally:server.db_pg._pool=old;await pool.close()

    async def test_direct_database_guards_reject_unknown_release_and_forged_production(self):
        r=await self.write_day();d=r.json()['draft']
        async def insert(c,review,action,revision,prior=None,release_id=None,task=None,batch=None,root=None):
            return await c.fetchval('''INSERT INTO prep_inventory.execution_events(list_id,store_id,revision,predecessor_id,action,draft_version_id,
                release_event_id,task_id,batch_event_id,batch_root_id,reason,actor,review_snapshot,review_hash,request_key,request_fingerprint)
                VALUES($1,'berts',$2,$3,$4,$5,$6,$7,$8,$9,$10,'synthetic-DB-probe',$11,$12,$13,$12) RETURNING id''',
                UUID(d['list_id']),revision,prior,action,UUID(d['id']),release_id,task,batch,root,review['command']['reason'],review,bytes(32),uuid4())
        review=dict(store_id='berts',prep_date='2026-10-08',track='daily',base_revision=0,command=self.command(d,task_id=None,batch_event_id=None),
                    draft_review_hash=d['review_hash'],release_event_id=None,task=None,batch=None,status_after='released')
        async with self.pool.acquire() as c:
            with self.assertRaises(asyncpg.RaiseError) as unknown:await insert(c,review,'release',1)
            self.assertIn('Unresolved dated draft',str(unknown.exception))
        d=await self.known_draft(version=1);r=await self.write_execution(self.command(d));s=r.json()['current'];event=r.json()['event']
        task=s['tasks'][0];batch=await self.production();command=self.command(d,'complete',task_id=task['id'],batch_event_id=batch['id'])
        p=await self.preview_execution(command,1);self.assertEqual(p.status_code,200,p.text);review=p.json()['review']
        async with self.pool.acquire() as c:
            before=await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'")
            forged=review|{'batch':review['batch']|{'review_snapshot':review['batch']['review_snapshot']|{'usableBaseOutput':'999'}}}
            with self.assertRaises(asyncpg.RaiseError) as mismatch:
                await insert(c,forged,'complete',2,UUID(event['id']),UUID(event['id']),UUID(task['id']),UUID(batch['id']),UUID(batch['root_id']))
            self.assertIn('matching current measured production evidence',str(mismatch.exception))
            snap=d['review_snapshot']|{'base_revision':2}
            with self.assertRaises(asyncpg.RaiseError) as held:
                await c.execute('''INSERT INTO prep_inventory.day_list_versions(list_id,store_id,revision,predecessor_id,day_group,note,actor,review_snapshot,review_hash,request_key,request_fingerprint)
                    VALUES($1,'berts',3,$2,'weekday',$3,'synthetic-DB-probe',$4,$5,$6,$5)''',UUID(d['list_id']),UUID(d['id']),snap['inputs']['note'],snap,bytes(32),uuid4())
            self.assertIn('Reopen the released draft',str(held.exception))
            self.assertEqual(await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'"),before)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.execution_events'),1)
