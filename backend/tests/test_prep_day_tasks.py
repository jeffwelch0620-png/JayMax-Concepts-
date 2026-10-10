"""Invented dated drafts and count/definition drift on disposable PostgreSQL."""
import asyncio,os,unittest
from unittest.mock import patch
from uuid import uuid4,UUID
from pydantic import ValidationError
import asyncpg
import server,prep_day_tasks as tasks,native_backup as backup
import test_prep_planning as fixtures
import test_native_backup as recovery


class PrepDayValidationTests(unittest.TestCase):
    def test_overrides_are_explicit_finite_and_unique(self):
        ident=uuid4();base=dict(planning_version_id=ident,kind='fixed_quantity',quantity='0',reason='Reviewed empty demand')
        self.assertEqual(tasks.Override(**base).quantity,0)
        for changes in ({'quantity':None},{'quantity':'NaN'},{'quantity':'Infinity'},{'quantity':'-1'},{'kind':'omit'},{'reason':' '},{'item_code':'forged'}):
            with self.assertRaises(ValidationError):tasks.Override(**(base|changes))
        with self.assertRaises(ValidationError):tasks.DraftIn(track='daily',day_group='weekday',note='Reviewed',overrides=[base,base])
        with patch.dict(os.environ,{'PREP_DAY_TASKS_ENABLED':'true','PREP_PLANNING_ENABLED':'false'}):
            with self.assertRaises(server.HTTPException):tasks.enabled()


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PostgreSQL required')
class PrepDayTaskTests(unittest.IsolatedAsyncioTestCase):
    asyncTearDown=fixtures.PrepPlanningTests.asyncTearDown
    target=fixtures.PrepPlanningTests.target
    units=fixtures.PrepPlanningTests.units
    pair=fixtures.PrepPlanningTests.pair
    scope=fixtures.PrepPlanningTests.scope
    count=fixtures.PrepPlanningTests.count
    report=fixtures.PrepPlanningTests.report
    save=fixtures.PrepPlanningTests.save
    product=fixtures.PrepPlanningTests.product
    profile=fixtures.PrepPlanningTests.profile
    recipe=fixtures.PrepPlanningTests.recipe
    plan=fixtures.PrepPlanningTests.plan
    promote=fixtures.PrepPlanningTests.promote
    payload=fixtures.PrepPlanningTests.payload
    edit=fixtures.PrepPlanningTests.edit

    async def asyncSetUp(self):
        await fixtures.PrepPlanningTests.asyncSetUp(self)
        flag=patch.dict(os.environ,{'PREP_BATCHES_ENABLED':'true','PREP_OBSERVATIONS_ENABLED':'true','PREP_DAY_TASKS_ENABLED':'true'});flag.start();self.addCleanup(flag.stop)
        async with self.pool.acquire() as c:
            for name in ('20261005_prep_batch_events.sql','20261005_prep_observations.sql'):
                await c.execute((recovery.counts.native.ROOT/'migrations'/name).read_text())
            self.old_list=await c.fetchval("INSERT INTO prep_lists(store_id,prep_date,count_type) VALUES('berts','2026-10-08','nightly_prep') RETURNING id")
            await c.execute("INSERT INTO prep_list_lines(list_id,task_type,name,note) VALUES($1,'task','Retained legacy task','Original note')",self.old_list)
            await c.execute("INSERT INTO prep_overrides(store_id,date,type,custom_name,par,note) VALUES('berts','2026-10-08','par','Unmapped legacy source',9,'Original day override')")
            await c.execute((recovery.counts.native.ROOT/'migrations/20261007_prep_day_tasks.sql').read_text())
        p=await self.edit(self.payload(track='daily',weekday_par='5',weekend_par='7'));self.assertEqual(p.status_code,200,p.text);self.standing=p.json()['plan']

    def draft_body(self,**changes):return dict(track='daily',day_group='weekday',count_event_id=None,overrides=[],note='Reviewed invented service day')|changes

    async def preview_day(self,body=None,version=0,day='2026-10-08',store='berts'):
        return await self.catalog.post(f'/api/pg/purchases/{store}/prep-day-drafts/{day}/preview',json=body or self.draft_body(),headers={'If-Match':str(version)})

    async def write_day(self,body=None,version=0,key=None,day='2026-10-08',payload=None):
        if payload is None:
            body=body or self.draft_body();p=await self.preview_day(body,version,day);self.assertEqual(p.status_code,200,p.text)
            payload={'draft':body,'expected_review_hash':p.json()['reviewHash'],'reviewed':True}
        return await self.catalog.put(f'/api/pg/purchases/berts/prep-day-drafts/{day}',json=payload,headers={'If-Match':str(version),'Idempotency-Key':key or str(uuid4())})

    async def prep_count(self,quantity='2',stamp='2026-10-07T22:00:00-04:00'):
        body=dict(performed_at=stamp,business_date=stamp[:10],timezone_name='America/New_York',calendar_date_confirmed=True,note='Invented complete physical prep count',complete_scope_confirmed=True,
            lines=[dict(product_version_id=self.p['id'],profile_id=self.u['id'],quantity=quantity,evidence='Measured prep amount')])
        p=await self.catalog.post('/api/pg/purchases/berts/prep-observations/count/preview',json=body);self.assertEqual(p.status_code,200,p.text)
        r=await self.catalog.post('/api/pg/purchases/berts/prep-observations/count',json={'body':body,'expected_review_hash':p.json()['reviewHash'],'reviewed':True},headers={'Idempotency-Key':str(uuid4())});self.assertEqual(r.status_code,200,r.text)
        return r.json()['event']

    async def test_missing_count_is_unknown_explicit_zero_is_known_and_daily_par_is_exact(self):
        p=await self.preview_day();self.assertEqual(p.status_code,200,p.text);t=p.json()['review']['tasks'][0]
        self.assertIsNone(t['planned_quantity']);self.assertEqual(p.json()['review']['unresolved_tasks'],1)
        event=await self.prep_count('0');body=self.draft_body(count_event_id=event['id']);r=await self.write_day(body);self.assertEqual(r.status_code,200,r.text)
        t=r.json()['draft']['review_snapshot']['tasks'][0];self.assertEqual(t['planned_base_quantity'],'5.000000000000');self.assertEqual(t['counted_base_quantity'],'0')
        self.assertFalse(r.json()['draft']['review_snapshot']['execution_ready'])

    async def test_parallel_retry_edits_and_tracks_have_distinct_atomic_identity(self):
        key=str(uuid4());p=await self.preview_day();payload={'draft':self.draft_body(),'expected_review_hash':p.json()['reviewHash'],'reviewed':True}
        results=await asyncio.gather(self.write_day(key=key,payload=payload),self.write_day(key=key,payload=payload))
        for r in results:self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(results[0].json()['draft'],results[1].json()['draft'])
        p=await self.preview_day(version=1);changed={'draft':self.draft_body(),'expected_review_hash':p.json()['reviewHash'],'reviewed':True}
        raced=await asyncio.gather(self.write_day(version=1,payload=changed),self.write_day(version=1,payload=changed))
        self.assertEqual(sorted(r.status_code for r in raced),[200,409])
        replay=await self.write_day(key=key,payload=payload);self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(replay.json()['current_draft']['revision'],2)
        changed['draft']['note']='Another edit';self.assertEqual((await self.write_day(key=key,payload=changed)).status_code,409)
        bulk=await self.write_day(self.draft_body(track='bulk'));self.assertEqual(bulk.status_code,200,bulk.text)
        self.assertNotEqual(bulk.json()['draft']['list_id'],replay.json()['draft']['list_id'])
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.day_lists'),2)

    async def test_day_overrides_schedule_groups_and_history_do_not_change_accounting(self):
        _,a,b=await self.pair();before=(await self.report(a,b)).json();count=await self.prep_count('2')
        r=await self.write_day(self.draft_body(day_group='weekend',count_event_id=count['id']));self.assertEqual(r.status_code,200,r.text)
        t=r.json()['draft']['review_snapshot']['tasks'][0];self.assertEqual(t['needed_base_quantity'],'5');self.assertEqual(t['target_par'],'7')
        override=dict(planning_version_id=self.standing['id'],kind='fixed_quantity',quantity='1.123456789012',reason='Reviewed specific service demand')
        r=await self.write_day(self.draft_body(overrides=[override]),version=1);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['draft']['review_snapshot']['tasks'][0]['planned_quantity'],'1.123456789012')
        override.update(kind='omit',quantity=None);r=await self.write_day(self.draft_body(overrides=[override]),version=2);self.assertEqual(r.status_code,200,r.text)
        self.assertFalse(r.json()['draft']['review_snapshot']['tasks'][0]['included']);self.assertEqual(before,(await self.report(a,b)).json())
        history=await self.catalog.get('/api/pg/purchases/berts/prep-day-drafts/2026-10-08/history');self.assertEqual(len(history.json()),3)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.batch_events'),0);self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_logs'),0)

    async def test_stale_plans_counts_and_cross_store_overrides_are_held(self):
        count=await self.prep_count();body=self.draft_body(count_event_id=count['id']);p=await self.preview_day(body);payload={'draft':body,'expected_review_hash':p.json()['reviewHash'],'reviewed':True}
        newer=await self.prep_count('3',stamp='2026-10-07T23:00:00-04:00')
        self.assertEqual((await self.write_day(payload=payload)).status_code,409)
        wrong=self.draft_body(overrides=[dict(planning_version_id=self.standing['id'],kind='fixed_quantity',quantity='1',reason='Wrong location')])
        self.assertEqual((await self.preview_day(wrong,store='rudds')).status_code,409)
        p=await self.preview_day(self.draft_body(count_event_id=newer['id']));self.assertEqual(p.status_code,200,p.text)
        payload={'draft':self.draft_body(count_event_id=newer['id']),'expected_review_hash':p.json()['reviewHash'],'reviewed':True}
        self.assertEqual((await self.edit(self.payload(track='daily',weekday_par='9'),version=1)).status_code,200)
        self.assertEqual((await self.write_day(payload=payload)).status_code,409)

    async def test_nonterminating_unit_deficit_requires_a_reviewed_quantity_and_recurring_is_fixed(self):
        unit=await self.profile(self.p,'bag','3');r=await self.edit(self.payload(track='daily',unit_profile_id=unit['id'],weekday_par='1'),version=1);self.assertEqual(r.status_code,200,r.text)
        count=await self.prep_count('2');p=await self.preview_day(self.draft_body(count_event_id=count['id']));self.assertEqual(p.status_code,200,p.text)
        t=p.json()['review']['tasks'][0];self.assertEqual(t['needed_base_quantity'],'1');self.assertIsNone(t['planned_quantity']);self.assertIn('12 decimal',t['issue'])
        r=await self.edit(self.payload(track='daily',schedule='recurring',recur_days=[3],fixed_quantity='4'),version=2);self.assertEqual(r.status_code,200,r.text)
        p=await self.preview_day();self.assertEqual(p.status_code,200,p.text);self.assertEqual(p.json()['review']['tasks'][0]['planned_quantity'],'4')

    async def test_legacy_flag_off_holds_and_failed_task_insert_rollback_history_and_revision(self):
        with patch.dict(os.environ,{'PREP_DAY_TASKS_ENABLED':'false'}):
            for path,body in ((f'/api/pg/preplists/berts/generate',{'date':'2026-10-08'}),(f'/api/pg/preplists/berts/{self.old_list}/release',{}),('/api/pg/prep-overrides/berts',{'date':'2026-10-08','type':'add'})):
                self.assertEqual((await self.catalog.post(path,json=body)).status_code,409)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.legacy_day_sources'),3)
            before=await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'")
            for sql in ('DELETE FROM prep_lists','DELETE FROM prep_list_lines','DELETE FROM prep_overrides','DELETE FROM prep_inventory.legacy_day_sources'):
                with self.assertRaises(asyncpg.PostgresError):await c.execute(sql)
            await c.execute("""CREATE FUNCTION public.fail_day_task_test() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Invented task failure' USING ERRCODE='23514'; END $$;
                CREATE TRIGGER failed_task_test AFTER INSERT ON prep_inventory.day_tasks FOR EACH ROW EXECUTE FUNCTION public.fail_day_task_test();""")
        with self.assertRaises(asyncpg.CheckViolationError):await self.write_day()
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.day_lists'),0)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.day_list_versions'),0)
            self.assertEqual(await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'"),before)

    async def test_dated_drafts_overrides_and_exact_retry_survive_whole_sql_restore(self):
        key=str(uuid4());p=await self.preview_day();payload={'draft':self.draft_body(),'expected_review_hash':p.json()['reviewHash'],'reviewed':True}
        r=await self.write_day(key=key,payload=payload);self.assertEqual(r.status_code,200,r.text)
        before=(await self.catalog.get('/api/pg/purchases/berts/prep-day-drafts/2026-10-08')).json()
        manifest=await backup.create_backup(self.source,recovery.PG_DUMP,self.directory);self.assertEqual(manifest['tables']['prep_inventory.day_tasks']['rows'],1)
        dsn=await self.target();self.assertEqual((await backup.verify_restore(dsn,self.directory))['status'],'verified')
        pool=await asyncpg.create_pool(dsn,min_size=1,max_size=2,init=recovery.db_pg._init_connection);old=server.db_pg._pool;server.db_pg._pool=pool
        try:
            self.assertEqual((await self.catalog.get('/api/pg/purchases/berts/prep-day-drafts/2026-10-08')).json(),before)
            replay=await self.write_day(key=key,payload=payload);self.assertEqual(replay.status_code,200,replay.text)
            async with pool.acquire() as c:
                for sql in ('DELETE FROM prep_inventory.day_list_versions','DELETE FROM prep_inventory.day_tasks','UPDATE prep_inventory.day_lists SET track=\'bulk\''):
                    with self.assertRaises(asyncpg.PostgresError):await c.execute(sql)
                with self.assertRaises(asyncpg.PostgresError):
                    await c.execute('INSERT INTO prep_inventory.day_tasks SELECT gen_random_uuid(),version_id,store_id,ordinal+1,product_id,planning_version_id,recipe_version_id,unit_profile_id,included,planned_quantity,factor,planned_base_quantity,task_snapshot FROM prep_inventory.day_tasks')
        finally:server.db_pg._pool=old;await pool.close()

    async def test_voided_count_and_new_product_scope_never_supply_guessed_stock(self):
        count=await self.prep_count();body=self.draft_body(count_event_id=count['id']);r=await self.write_day(body);self.assertEqual(r.status_code,200,r.text)
        p=await self.product('New prepared product');u=await self.profile(p);recipe,_=await self.promote(self.recipe(p,u))
        response=await self.edit(self.payload(track='daily',recipe_version_id=recipe['id'],unit_profile_id=u['id']),product=p['product_id']);self.assertEqual(response.status_code,200,response.text)
        preview=await self.preview_day(body,version=1);self.assertEqual(preview.status_code,200,preview.text)
        new=next(t for t in preview.json()['review']['tasks'] if t['product_id']==p['product_id']);self.assertIsNone(new['planned_quantity']);self.assertIsNone(new['counted_base_quantity'])
        change=dict(kind='void',reason='Invented invalid closing measurement');path=f"/api/pg/purchases/berts/prep-observations/count/{count['id']}"
        review=await self.catalog.post(path+'/change-preview',json=change);self.assertEqual(review.status_code,200,review.text)
        void=await self.catalog.post(path+'/changes',json={'change':change,'expected_review_hash':review.json()['reviewHash'],'reviewed':True},headers={'Idempotency-Key':str(uuid4())});self.assertEqual(void.status_code,200,void.text)
        self.assertEqual((await self.preview_day(body,version=1)).status_code,409)
        saved=(await self.catalog.get('/api/pg/purchases/berts/prep-day-drafts/2026-10-08')).json()['current'];self.assertTrue(saved['source_changed'])

    async def test_database_seals_reject_partial_tasks_and_fabricated_zero_stock_calculation(self):
        r=await self.write_day();self.assertEqual(r.status_code,200,r.text);saved=r.json()['draft'];snapshot=saved['review_snapshot']|{'base_revision':1}
        async with self.pool.acquire() as c:
            before=await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'")
            async def insert_version(review):
                return await c.fetchval('''INSERT INTO prep_inventory.day_list_versions(list_id,store_id,revision,predecessor_id,day_group,note,actor,review_snapshot,review_hash,request_key,request_fingerprint)
                    VALUES($1,'berts',2,$2,'weekday',$3,'synthetic-DB-probe',$4,$5,$6,$5) RETURNING id''',UUID(saved['list_id']),UUID(saved['id']),review['inputs']['note'],review,bytes(32),uuid4())
            with self.assertRaises(asyncpg.RaiseError) as incomplete:
                async with c.transaction():await insert_version(snapshot)
            self.assertIn('task set is incomplete',str(incomplete.exception))
            t=snapshot['tasks'][0]|dict(planned_quantity='5',planned_base_quantity='5',issue=None)
            with self.assertRaises(asyncpg.RaiseError) as fabricated:
                async with c.transaction():
                    ident=await insert_version(snapshot|{'tasks':[t],'unresolved_tasks':0})
                    await c.execute('''INSERT INTO prep_inventory.day_tasks(version_id,store_id,ordinal,product_id,planning_version_id,recipe_version_id,unit_profile_id,included,planned_quantity,factor,planned_base_quantity,task_snapshot)
                        VALUES($1,'berts',1,$2,$3,$4,$5,true,5,1,5,$6)''',ident,UUID(self.p['product_id']),UUID(self.standing['id']),UUID(self.r['id']),UUID(self.u['id']),t)
            self.assertIn('Missing physical count cannot be treated as zero stock',str(fabricated.exception))
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.day_list_versions'),1)
            self.assertEqual(await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'"),before)
