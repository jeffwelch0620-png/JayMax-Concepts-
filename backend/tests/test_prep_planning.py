"""Invented prep planning, stale edits and restore on disposable PostgreSQL."""
import asyncio,os,unittest
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID,uuid4
import asyncpg
from pydantic import ValidationError
import server,prep_planning as planning,native_backup as backup
import test_order_commands as orders
import test_prep_mapping as definitions
import test_native_backup as recovery


class PrepPlanningValidationTests(unittest.TestCase):
    def test_units_numbers_and_recurring_fields_are_not_coerced_to_defaults(self):
        body=dict(action='save',recipe_version_id=uuid4(),unit_profile_id=uuid4(),track='daily',schedule='daily',weekday_par='0',weekend_par='3.123456789012',note='Reviewed',verified=True)
        self.assertEqual(planning.SavePlan(**body).weekend_par,Decimal('3.123456789012'))
        for changes in ({'weekday_par':'NaN'},{'weekday_par':'Infinity'},{'weekday_par':'-1'},{'weekend_par':None},{'note':' '},{'schedule':'recurring'},{'recur_days':[0]},{'fixed_quantity':'1'},{'schedule':'recurring','recur_days':[True],'fixed_quantity':'1'},{'schedule':'recurring','recur_days':[0,0],'fixed_quantity':'1'},{'schedule':'recurring','recur_days':[7],'fixed_quantity':'1'},{'verified':False},{'verified':1},{'vessel_capacity':9}):
            with self.assertRaises(ValidationError):planning.SavePlan(**{**body,**changes})
        recurring=planning.SavePlan(**{**body,'schedule':'recurring','recur_days':[6,0],'fixed_quantity':'2'})
        self.assertEqual(recurring.recur_days,[0,6])
        with patch.dict(os.environ,{'PREP_PLANNING_ENABLED':'true','PREP_SETUP_ENABLED':'false'}):
            with self.assertRaises(server.HTTPException):planning.enabled()


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PostgreSQL required')
class PrepPlanningTests(unittest.IsolatedAsyncioTestCase):
    target=orders.OrderCommandTests.target
    units=orders.OrderCommandTests.units
    pair=orders.OrderCommandTests.pair
    scope=orders.OrderCommandTests.scope
    count=orders.OrderCommandTests.count
    report=orders.OrderCommandTests.report
    save=definitions.PrepMappingTests.save
    product=definitions.PrepMappingTests.product
    profile=definitions.PrepMappingTests.profile
    recipe=definitions.PrepMappingTests.recipe
    plan=definitions.PrepMappingTests.plan
    promote=definitions.PrepMappingTests.promote

    async def asyncSetUp(self):
        await orders.OrderCommandTests.asyncSetUp(self)
        self.flag=patch.dict(os.environ,{'PREP_SETUP_ENABLED':'true','PREP_PLANNING_ENABLED':'true'});self.flag.start()
        async with self.pool.acquire() as c:
            await c.execute((recovery.counts.native.ROOT/'migrations/20261005_prep_mapping_foundation.sql').read_text())
            await c.execute("INSERT INTO stores(id,name) VALUES('comm','Invented commissary')")
            self.legacy_id=await c.fetchval("INSERT INTO prep_items(store_id,name,item_code,container,vessel_capacity,par_weekday,par_weekend,made_at) VALUES('comm','Invented legacy bags','test_food','bag',8,2,7,'comm') RETURNING id")
            await c.execute((recovery.counts.native.ROOT/'migrations/20261007_prep_planning.sql').read_text())
        self.assertEqual((await self.units('count'))[0].status_code,200)
        self.p=await self.product();self.u=await self.profile(self.p);self.r,_=await self.promote(self.recipe(self.p,self.u))

    async def asyncTearDown(self):
        self.flag.stop();await orders.OrderCommandTests.asyncTearDown(self)

    def payload(self,**changes):
        return dict(action='save',recipe_version_id=self.r['id'],unit_profile_id=self.u['id'],track='bulk',schedule='daily',weekday_par='2.123456789012',weekend_par='7',note='Invented planning quantities',verified=True)|changes

    async def edit(self,body=None,version=0,key=None,product=None,store='berts',client=None):
        return await (client or self.catalog).put(f"/api/pg/purchases/{store}/prep-planning/{product or self.p['product_id']}",json=body or self.payload(),headers={'If-Match':str(version),'Idempotency-Key':key or str(uuid4())})

    async def read(self,store='berts'):
        r=await (self.other if store=='comm' else self.catalog).get(f'/api/pg/purchases/{store}/prep-planning');self.assertEqual(r.status_code,200,r.text);return r.json()

    async def test_racing_edits_exact_retry_actor_and_required_version(self):
        key=str(uuid4());responses=await asyncio.gather(self.edit(key=key),self.edit(key=key))
        for r in responses:self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(responses[0].json()['plan'],responses[1].json()['plan'])
        self.assertEqual(responses[0].json()['plan']['actor'],'synthetic-catalog-reviewer')
        raced=await asyncio.gather(self.edit(self.payload(weekend_par='8'),version=1),self.edit(self.payload(weekend_par='9'),version=1))
        self.assertEqual(sorted(r.status_code for r in raced),[200,409])
        replay=await self.edit(key=key);self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json()['plan']['revision'],1);self.assertEqual(replay.json()['current_plan']['revision'],2)
        self.assertEqual((await self.edit(self.payload(weekend_par='99'),key=key)).status_code,409)
        self.assertEqual((await self.edit(key=key,client=self.other)).status_code,409)
        missing=await self.catalog.put(f"/api/pg/purchases/berts/prep-planning/{self.p['product_id']}",json=self.payload(),headers={'Idempotency-Key':str(uuid4())})
        self.assertEqual(missing.status_code,428)

    async def test_pars_tracks_recurring_retirement_and_restore_are_metadata_only(self):
        _,a,b=await self.pair();before=(await self.report(a,b)).json()
        body=self.payload(schedule='recurring',recur_days=[6,0],fixed_quantity='1.234567890123')
        saved=await self.edit(body);self.assertEqual(saved.status_code,200,saved.text)
        p=saved.json()['plan'];self.assertEqual(p['recur_days'],[0,6]);self.assertEqual(p['weekday_par'],'2.123456789012');self.assertEqual(p['weekend_par'],'7');self.assertEqual(p['track'],'bulk')
        retired=await self.edit(dict(action='retire',note='Temporarily remove from planning'),version=1);self.assertEqual(retired.status_code,200,retired.text)
        self.assertFalse(retired.json()['plan']['active']);self.assertEqual((await self.edit(dict(action='retire',note='Already retired'),version=2)).status_code,409)
        restored=await self.edit(self.payload(track='daily'),version=2);self.assertEqual(restored.status_code,200,restored.text)
        self.assertTrue(restored.json()['plan']['active']);self.assertEqual(before,(await self.report(a,b)).json())
        history=await self.catalog.get(f"/api/pg/purchases/berts/prep-planning/{self.p['product_id']}/history");self.assertEqual(len(history.json()),3)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_logs'),0)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_recipe_stock'),0)

    async def test_changed_sources_units_and_cross_store_are_held_but_retirement_remains_possible(self):
        self.assertEqual((await self.edit()).status_code,200)
        self.assertEqual((await self.edit(store='rudds')).status_code,422)
        other=await self.product('Other product');otherunit=await self.profile(other)
        self.assertEqual((await self.edit(self.payload(unit_profile_id=otherunit['id']),version=1)).status_code,422)
        await self.profile(self.p,'lb','1',self.u['id'])
        self.assertTrue((await self.read())['plans'][0]['reviewNeeded'])
        self.assertEqual((await self.edit(version=1)).status_code,409)
        retired=await self.edit(dict(action='retire',note='Hold obsolete setup'),version=1);self.assertEqual(retired.status_code,200,retired.text)
        self.assertEqual((await self.edit(version=2)).status_code,409)

    async def test_preserved_legacy_records_and_installed_flag_off_writes_stay_held(self):
        sources=(await self.read('comm'))['legacy_sources'];self.assertEqual(len(sources),1)
        self.assertEqual(sources[0]['raw_record']['par_weekday'],2);self.assertEqual(sources[0]['raw_record']['par_weekend'],7)
        self.assertEqual(sources[0]['raw_record']['made_at'],'comm')
        with patch.dict(os.environ,{'PREP_PLANNING_ENABLED':'false'}):
            self.assertEqual((await self.catalog.get('/api/pg/purchases/berts/prep-planning')).status_code,503)
            self.assertEqual((await self.other.delete(f'/api/pg/prep-items/comm/{self.legacy_id}')).status_code,409)
            body=dict(name='Unreviewed',sourceType='item',itemCode='test_food')
            self.assertEqual((await self.catalog.post('/api/pg/prep-items/berts',json=body)).status_code,409)
            self.assertEqual((await self.other.put(f'/api/pg/prep-items/comm/{self.legacy_id}',json=body)).status_code,409)
            async with self.pool.acquire() as c:
                for sql in ('DELETE FROM prep_items','UPDATE prep_items SET par_weekday=99','DELETE FROM prep_inventory.legacy_planning_sources'):
                    with self.assertRaises(asyncpg.PostgresError):await c.execute(sql)

    async def test_database_history_guards_and_store_revisions_rollback_atomically(self):
        async with self.pool.acquire() as c:
            before=await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'") or 0;other=await c.fetchval("SELECT revision FROM store_state WHERE store_id='rudds'")
        saved=await self.edit();self.assertEqual(saved.status_code,200,saved.text)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'"),before+1)
            self.assertEqual(await c.fetchval("SELECT revision FROM store_state WHERE store_id='rudds'"),other)
            for sql in ('DELETE FROM prep_inventory.planning_versions','UPDATE prep_inventory.planning_versions SET weekend_par=99'):
                with self.assertRaises(asyncpg.PostgresError):await c.execute(sql)
            await c.execute("""CREATE FUNCTION public.fail_planning_test() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Invented post-insert failure' USING ERRCODE='23514'; END $$;
                CREATE TRIGGER failed_planning_test AFTER INSERT ON prep_inventory.planning_versions FOR EACH ROW EXECUTE FUNCTION public.fail_planning_test();""")
        with self.assertRaises(asyncpg.CheckViolationError):await self.edit(version=1)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.planning_versions'),1)
            self.assertEqual(await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'"),before+1)
            await c.execute('DROP TRIGGER failed_planning_test ON prep_inventory.planning_versions')
            row=saved.json()['plan']
            for changes in ({'schedule':'recurring','recur_days':[0],'fixed_quantity':None},{'schedule':'recurring','recur_days':[0,0],'fixed_quantity':'1'},{'weekday_par':'NaN'},{'revision':4},{'store_id':'rudds'},{'active':False,'weekday_par':'99'}):
                candidate=row|dict(id=str(uuid4()),request_key=str(uuid4()),revision=2,predecessor_id=row['id'])|changes
                # bytea JSON input uses PostgreSQL hex syntax, not API serialization.
                candidate['request_fingerprint']='\\x'+('00'*32)
                with self.assertRaises(asyncpg.PostgresError):
                    await c.execute('INSERT INTO prep_inventory.planning_versions SELECT * FROM jsonb_populate_record(NULL::prep_inventory.planning_versions,$1)',candidate)
            self.assertEqual(await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'"),before+1)

    async def test_changed_purchased_ingredient_requires_recipe_review_before_replanning(self):
        self.assertEqual((await self.edit()).status_code,200)
        async with self.pool.acquire() as c:await c.execute("UPDATE items SET unit_qty=999 WHERE code='test_food'")
        result=await self.read();self.assertTrue(result['plans'][0]['reviewNeeded'])
        self.assertEqual((await self.edit(version=1)).status_code,409)

    async def test_prep_planning_and_exact_retry_survive_whole_sql_restore(self):
        key=str(uuid4());first=await self.edit(key=key);self.assertEqual(first.status_code,200,first.text)
        self.assertEqual((await self.edit(dict(action='retire',note='Retained retired version'),version=1)).status_code,200)
        before=await self.read();manifest=await backup.create_backup(self.source,recovery.PG_DUMP,self.directory)
        self.assertEqual(manifest['tables']['prep_inventory.planning_versions']['rows'],2)
        dsn=await self.target();self.assertEqual((await backup.verify_restore(dsn,self.directory))['status'],'verified')
        pool=await asyncpg.create_pool(dsn,min_size=1,max_size=2,init=recovery.db_pg._init_connection);old=server.db_pg._pool;server.db_pg._pool=pool
        try:
            self.assertEqual(await self.read(),before)
            replay=await self.edit(key=key);self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(replay.json()['current_plan']['revision'],2)
        finally:server.db_pg._pool=old;await pool.close()
