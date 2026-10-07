"""Invented physical container measurements on isolated PostgreSQL databases."""
import asyncio, os, unittest
from decimal import Decimal
from uuid import UUID, uuid4
from unittest.mock import patch
import asyncpg, httpx
from pydantic import ValidationError
import server, prep_containers as containers, native_backup as backup
import test_prep_observations as fixtures
import test_native_backup as recovery


class ContainerValidationTests(unittest.TestCase):
    def test_capacity_types_quantities_and_review_are_explicit(self):
        base=dict(action='definition',name='Invented pan',capacity_unit='l',evidence='Measured reference')
        self.assertIsNone(containers.DefinitionIn(**base).usable_capacity)
        for change in ({'usable_capacity':'0'},{'stated_capacity':'NaN'},{'brimful_capacity':'2','usable_capacity':'3'},{'capacity_unit':'qt'},{'size':32}):
            with self.assertRaises(ValidationError): containers.DefinitionIn(**(base|change))
        for value in (False,1,'true'):
            with self.assertRaises(ValidationError): containers.CommandIn(body=base,expected_review_hash='a'*64,reviewed=value)


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PostgreSQL required')
class PrepContainerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await fixtures.PrepObservationTests.asyncSetUp(self)
        flag=patch.dict(os.environ,{'PREP_CONTAINERS_ENABLED':'true'});flag.start();self.addCleanup(flag.stop)
        async with self.pool.acquire() as c:
            self.legacy_dish=await c.fetchval("INSERT INTO dishes(store_id,name,recipe_type) VALUES('berts','Invented retained prep','prep') RETURNING id")
            await c.execute("INSERT INTO prep_recipe_stock(store_id,dish_id,on_hand,containers) VALUES('berts',$1,12,'[{\"label\":\"Unverified pan\",\"size\":32,\"count\":2,\"original_extra\":\"retain\"}]')",self.legacy_dish)
            await c.execute((recovery.counts.native.ROOT/'migrations/20261007_prep_containers.sql').read_text())

    def stamp(self,instant='2026-10-05T12:00:00-04:00'):
        return dict(performed_at=instant,business_date=instant[:10],timezone_name='America/New_York',calendar_date_confirmed=True,note='Invented measured internal movement')

    async def preview_container(self,body,store='berts'):
        return await self.client.post(f'/api/pg/purchases/{store}/prep-containers/preview',json=body)

    async def command(self,body=None,key=None,payload=None,store='berts'):
        if payload is None:
            p=await self.preview_container(body,store);self.assertEqual(p.status_code,200,p.text)
            payload=dict(body=body,expected_review_hash=p.json()['reviewHash'],reviewed=True)
        return await self.save('prep-containers/commands',payload,key,store)

    async def prepare(self,qty='10',factor='1'):
        d=await self.command(dict(action='definition',name='Invented container',capacity_unit='l',stated_capacity='8',brimful_capacity='8.5',usable_capacity='7',evidence='Invented capacity measurement; not food density'))
        self.assertEqual(d.status_code,200,d.text);self.definition=d.json()['result']
        if factor!='1': self.u=await self.profile(self.p,'measured bag',factor)
        p=await self.command(dict(action='profile',definition_id=self.definition['id'],product_version_id=self.p['id'],unit_profile_id=self.u['id'],usable_quantity=qty,evidence='Measured product-specific fill, mass is not vessel volume',product_fill_measured=True))
        self.assertEqual(p.status_code,200,p.text);self.fill_profile=p.json()['result']
        source,_=await self.record(await self.entry());self.lot=source
        return source

    def fill_body(self,quantity='10',**changes):
        return self.stamp()|dict(action='fill',profile_id=self.fill_profile['id'],source_batch_id=self.lot['id'],label='Invented batch pan A',quantity=quantity,contents_measured=True)|changes

    async def fill(self,quantity='10'):
        r=await self.command(self.fill_body(quantity));self.assertEqual(r.status_code,200,r.text)
        return r.json()['result']

    def move(self,fill,action,quantity=None,**changes):
        return self.stamp('2026-10-05T13:00:00-04:00')|dict(action=action,fill_id=fill['id'],quantity=quantity)|changes

    async def container_state(self):
        r=await self.client.get('/api/pg/purchases/berts/prep-containers');self.assertEqual(r.status_code,200,r.text);return r.json()

    async def test_partial_transfers_returns_and_unpack_preserve_accounting_and_total(self):
        _,a,b=await self.pair();before=(await self.report(a,b)).json()
        await self.prepare();fill=await self.fill()
        send=await self.command(self.move(fill,'send','3'));self.assertEqual(send.status_code,200,send.text)
        self.assertEqual((send.json()['current']['storage'],send.json()['current']['service']),('7','3'))
        returned=await self.command(self.move(fill,'return','1'));self.assertEqual(returned.status_code,200,returned.text)
        unpack=await self.command(self.move(fill,'unpack','8'));self.assertEqual(unpack.status_code,200,unpack.text)
        state=await self.container_state();self.assertEqual(state['lots'][0]['remainingRecordedQuantity'],'46')
        self.assertEqual((state['lots'][0]['containerStorage'],state['lots'][0]['containerService'],state['lots'][0]['totalRemainingRecordedQuantity']),('0','2','48'))
        self.assertEqual((state['fills'][0]['storage'],state['fills'][0]['service']),('0','2'))
        self.assertEqual((await self.report(a,b)).json(),before)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_logs'),0)
            self.assertEqual(await c.fetchval('SELECT on_hand FROM prep_recipe_stock LIMIT 1'),12)
            self.assertEqual(await c.fetchval("SELECT sum(quantity) FROM prep_inventory.batch_movements WHERE kind='raw_input'"),-60)

    async def test_nominal_capacity_is_not_actual_fill_and_unknown_cannot_become_zero(self):
        await self.prepare();f=await self.fill('2.123456789012')
        self.assertEqual(f['base_quantity'],'2.123456789012')
        for change,status in (({'quantity':None},422),({'quantity':'0'},422),({'quantity':'11'},422),({'source_batch_id':str(uuid4())},422),({'performed_at':'2026-10-05T09:00:00-04:00'},422)):
            r=await self.preview_container(self.fill_body()|change);self.assertEqual(r.status_code,status,r.text)
        r=await self.preview_container(self.move(f,'send','2.123456789013'));self.assertEqual(r.status_code,409)

    async def test_exact_retry_races_stale_movement_and_key_body_binding(self):
        await self.prepare();body=self.fill_body();p=await self.preview_container(body);payload=dict(body=body,expected_review_hash=p.json()['reviewHash'],reviewed=True);key=str(uuid4())
        race=await asyncio.gather(self.command(key=key,payload=payload),self.command(key=key,payload=payload))
        self.assertTrue(all(r.status_code==200 for r in race),[r.text for r in race]);self.assertEqual(race[0].json()['result']['id'],race[1].json()['result']['id'])
        f=race[0].json()['result'];move=self.move(f,'send','7');p=await self.preview_container(move);mp=dict(body=move,expected_review_hash=p.json()['reviewHash'],reviewed=True)
        race=await asyncio.gather(self.command(payload=mp),self.command(payload=mp));self.assertEqual(sorted(r.status_code for r in race),[200,409])
        replay=await self.command(key=key,payload=payload);self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(replay.json()['current']['service'],'7')
        self.assertEqual((await self.command(key=key,payload=payload|{'body':body|{'label':'Different'}})).status_code,409)

    async def test_container_reservations_share_limits_with_prep_and_waste(self):
        await self.prepare('40');body=self.fill_body('30');p=await self.preview_container(body);payload=dict(body=body,expected_review_hash=p.json()['reviewHash'],reviewed=True)
        waste=await self.waste(self.lot,'30');wp=(await self.plan_obs('waste',waste)).json()
        race=await asyncio.gather(self.command(payload=payload),self.save('prep-observations/waste',dict(body=waste,expected_review_hash=wp['reviewHash'],reviewed=True)))
        self.assertEqual(sorted(r.status_code for r in race),[200,409])
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT prep_inventory.lot_remaining($1)',UUID(self.lot['id'])),18)

    async def test_void_unused_fill_and_undo_latest_movement_preserve_history(self):
        await self.prepare();f=await self.fill();s=await self.command(self.move(f,'send','4'));self.assertEqual(s.status_code,200,s.text)
        undo=self.move(f,'undo',target_move_id=s.json()['result']['id']);r=await self.command(undo);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual((r.json()['current']['storage'],r.json()['current']['service']),('10','0'))
        self.assertEqual((await self.preview_container(undo)).status_code,409)
        self.assertEqual((await self.preview_container(self.move(f,'void_fill',performed_at=f['performed_at']))).status_code,409)
        fresh=await self.fill('5');r=await self.command(self.move(fresh,'void_fill',performed_at=fresh['performed_at']));self.assertEqual(r.status_code,200,r.text)
        self.assertTrue(r.json()['current']['voided']);self.assertEqual(r.json()['current']['allocated'],'0')

    async def test_unpacked_contents_cannot_be_undone_after_reallocation(self):
        await self.prepare('48');f=await self.fill('48');r=await self.command(self.move(f,'unpack','20'));self.assertEqual(r.status_code,200,r.text)
        await self.save_obs('waste',await self.waste(self.lot,'20',performed_at='2026-10-05T14:00:00-04:00'))
        self.assertEqual((await self.preview_container(self.move(f,'undo',target_move_id=r.json()['result']['id']))).status_code,409)

    async def test_profile_revision_holds_new_fills_but_pins_existing_contents(self):
        await self.prepare();f=await self.fill()
        d=await self.command(dict(action='definition',predecessor_id=self.definition['id'],name='Measured pan revised',capacity_unit='l',usable_capacity='6',evidence='New physical measurement'))
        self.assertEqual(d.status_code,200,d.text);self.assertEqual((await self.preview_container(self.fill_body())).status_code,409)
        move=await self.command(self.move(f,'send','2'));self.assertEqual(move.status_code,200,move.text)
        p=await self.command(dict(action='profile',predecessor_id=self.fill_profile['id'],definition_id=d.json()['result']['id'],product_version_id=self.p['id'],unit_profile_id=self.u['id'],usable_quantity='5',evidence='Re-measured product-specific fill',product_fill_measured=True))
        self.assertEqual(p.status_code,200,p.text);self.assertEqual(move.json()['current']['fill']['profile_id'],self.fill_profile['id'])

    async def test_dependencies_block_batch_correction_and_flags_off_hold_legacy(self):
        await self.prepare();f=await self.fill()
        r=await self.command(self.move(f,'send','1'));self.assertEqual(r.status_code,200,r.text)
        p=await self.client.post(f"/api/pg/purchases/berts/prep-batches/{self.lot['id']}/change-preview",json=dict(kind='void',reason='Has container contents'));self.assertEqual(p.status_code,409)
        with patch.dict(os.environ,{'PREP_CONTAINERS_ENABLED':'false','PREP_BATCHES_ENABLED':'false'}):
            old=server.db_pg._pool;server.db_pg._pool=self.pool
            try:
                token=server._token({'id':'synthetic-owner','role':'owner','email':'owner@example.invalid'})
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://test',headers={'Authorization':'Bearer '+token}) as client:
                    for path,body in (('use-container',{'recipeId':str(self.legacy_dish),'containerId':'legacy'}),('apply-sales',{'dishSales':{}}),('complete',{'recipeId':str(self.legacy_dish),'batches':1,'containers':[]})):
                        r=await client.post('/api/pg/prep/berts/'+path,json=body)
                        self.assertEqual(r.status_code,409,r.text)
            finally:server.db_pg._pool=old
        async with self.pool.acquire() as c:
            raw=await c.fetchval("SELECT raw_record FROM prep_inventory.legacy_container_sources WHERE source_table='prep_recipe_stock'")
            self.assertEqual(raw['containers'][0]['original_extra'],'retain')
            for table in ('container_commands','container_fills','container_moves','container_profiles','container_definitions','legacy_container_sources'):
                with self.assertRaises(asyncpg.PostgresError):await c.execute('DELETE FROM prep_inventory.'+table)
            with self.assertRaises(asyncpg.PostgresError):await c.execute('UPDATE prep_recipe_stock SET on_hand=0')

    async def test_failure_rolls_back_command_children_and_store_revision(self):
        await self.prepare()
        async with self.pool.acquire() as c:
            before=await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'")
            await c.execute("CREATE FUNCTION public.fail_container_test() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Synthetic fill failure'; END $$; CREATE TRIGGER fail_container_test AFTER INSERT ON prep_inventory.container_fills FOR EACH ROW EXECUTE FUNCTION public.fail_container_test();")
        with self.assertRaises(asyncpg.PostgresError):await self.command(self.fill_body())
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.container_commands'),2)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.container_fills'),0)
            self.assertEqual(await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'"),before)

    async def test_whole_sql_restore_retains_contents_history_and_exact_retry(self):
        await self.prepare();f=await self.fill();body=self.move(f,'send','3');p=await self.preview_container(body);payload=dict(body=body,expected_review_hash=p.json()['reviewHash'],reviewed=True);key=str(uuid4())
        r=await self.command(key=key,payload=payload);self.assertEqual(r.status_code,200,r.text);before=await self.container_state()
        await backup.create_backup(self.source,recovery.PG_DUMP,self.directory);dsn=await self.target();self.assertEqual((await backup.verify_restore(dsn,self.directory))['status'],'verified')
        pool=await asyncpg.create_pool(dsn,min_size=1,max_size=2,init=recovery.db_pg._init_connection);old=self.pool;self.pool=pool
        try:
            self.assertEqual(await self.container_state(),before)
            replay=await self.command(key=key,payload=payload);self.assertEqual(replay.status_code,200,replay.text);self.assertTrue(replay.json()['replayed']);self.assertEqual(replay.json()['result'],r.json()['result'])
        finally:self.pool=old;await pool.close()

    async def test_direct_sql_rejects_forged_balanced_quantity_and_orphan_command(self):
        await self.prepare();f=await self.fill();body=self.move(f,'send','3');plan=(await self.preview_container(body)).json()['review']
        plan['facts']['storage_delta']='-2';plan['facts']['service_delta']='2'
        async with self.pool.acquire() as c:
            before=await c.fetchval('SELECT count(*) FROM prep_inventory.container_commands')
            for child in (False,True):
                with self.assertRaises(asyncpg.PostgresError):
                    async with c.transaction():
                        command_id,child_id=uuid4(),uuid4()
                        await c.execute("INSERT INTO prep_inventory.container_commands(id,store_id,action,result_id,review_snapshot,review_hash,recorded_by,request_key,request_fingerprint) VALUES($1,'berts','send',$2,$3,$4,'sql-test',$5,$4)",command_id,child_id,plan,b'x'*32,uuid4())
                        if child:
                            facts=plan['facts']|dict(id=str(child_id),command_id=str(command_id),store_id='berts',recorded_at='2026-10-05T17:00:00+00:00')
                            await c.execute('INSERT INTO prep_inventory.container_moves SELECT (jsonb_populate_record(NULL::prep_inventory.container_moves,$1)).*',facts)
                self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.container_commands'),before)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.container_moves'),0)

    async def test_tiny_contents_and_movements_remain_exact_below_input_scale(self):
        await self.prepare(factor='0.000000000001');f=await self.fill('0.000000000001')
        self.assertEqual(Decimal(f['base_quantity']),Decimal('0.000000000000000000000001'))
        r=await self.command(self.move(f,'send','0.000000000001'));self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(Decimal(r.json()['current']['service']),Decimal('0.000000000000000000000001'))
        r=await self.command(self.move(f,'return','0.000000000001'));self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(Decimal(r.json()['current']['storage']),Decimal('0.000000000000000000000001'))

    async def test_verified_capacity_dimensions_and_manager_location_boundaries(self):
        await self.prepare();d=await self.command(dict(action='definition',name='Small measured pan',capacity_unit='lb',usable_capacity='2',evidence='Measured same-dimension capacity'))
        self.assertEqual(d.status_code,200,d.text)
        body=dict(action='profile',definition_id=d.json()['result']['id'],product_version_id=self.p['id'],unit_profile_id=self.u['id'],usable_quantity='3',evidence='Exceeds known measured capacity',product_fill_measured=True)
        self.assertEqual((await self.preview_container(body)).status_code,422)
        self.assertEqual((await self.preview_container(self.fill_body(),store='rudds')).status_code,422)
        old=server.db_pg._pool;server.db_pg._pool=self.pool
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://test') as client:
                path='/api/pg/purchases/berts/prep-containers/preview'
                for role,locations,status in [('staff',['berts'],403),('readonly',['berts'],403),('manager',['rudds'],403),('manager',['berts'],200)]:
                    token=server._token(dict(id='invented-'+role,email='test@example.invalid',role=role,locations=locations))
                    r=await client.post(path,json=self.fill_body(),headers={'Authorization':'Bearer '+token});self.assertEqual(r.status_code,status,r.text)
        finally:server.db_pg._pool=old

    async def test_future_unpack_cannot_fund_backdated_waste_prep_or_fill(self):
        await self.prepare('48');f=await self.fill('48')
        r=await self.command(self.move(f,'unpack','20'));self.assertEqual(r.status_code,200,r.text)
        old_waste=await self.waste(self.lot,'20');self.assertEqual((await self.plan_obs('waste',old_waste)).status_code,409)
        self.assertEqual((await self.preview_container(self.fill_body('20'))).status_code,409)
        nested=await self.nested(self.lot,'20');self.assertEqual((await self.preview_batch(nested)).status_code,409)
        future=await self.waste(self.lot,'20',performed_at='2026-10-05T14:00:00-04:00')
        async with self.pool.acquire() as c:
            plan=await containers.observations.preview(c,'berts','waste',containers.observations.WasteIn(**future))
            plan['review']['performed_at']=old_waste['performed_at'];plan['review']['body']['performed_at']=old_waste['performed_at']
            with self.assertRaises(asyncpg.PostgresError):
                async with c.transaction():await containers.observations.persist(c,'berts',plan,uuid4(),b'x'*32,'sql-temporal-test')
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.waste_movements'),0)
        await self.save_obs('waste',future)

    async def test_count_derived_opening_output_keeps_container_dependencies(self):
        async with self.pool.acquire() as c:
            await c.execute((recovery.counts.native.ROOT/'migrations/20261005_prep_opening_sources.sql').read_text())
        count_body=await fixtures.PrepObservationTests.count_body(self,'48',performed_at='2026-10-05T09:00:00-04:00')
        count,_=await self.save_obs('count',count_body)
        body=dict(count_id=count['id'],before_activity_confirmed=True,note='Invented complete measured opening before activity')
        p=await self.client.post('/api/pg/purchases/berts/prep-openings/preview',json=body);self.assertEqual(p.status_code,200,p.text)
        r=await self.save('prep-openings',dict(opening=body,expected_review_hash=p.json()['reviewHash'],reviewed=True));self.assertEqual(r.status_code,200,r.text)
        decision=r.json()['event'];await self.prepare()
        async with self.pool.acquire() as c:
            opening_id=await c.fetchval("SELECT id FROM prep_inventory.batch_events WHERE source_kind='opening'")
        self.lot={'id':str(opening_id)};f=await self.fill('10')
        self.assertEqual(f['source_batch_id'],str(opening_id))
        p=await self.client.post(f"/api/pg/purchases/berts/prep-openings/{decision['id']}/void-preview",json={'reason':'Reserved by container'})
        self.assertEqual(p.status_code,409,p.text)
        p=await self.client.post(f"/api/pg/purchases/berts/prep-observations/count/{count['id']}/change-preview",json={'kind':'void','reason':'Opening has container contents'})
        self.assertEqual(p.status_code,409,p.text)


for _name in ['asyncTearDown','units','pair','scope','count','capture','body','post','report','target','restored_client','save','product','profile','recipe','plan','promote','entry','preview_batch','record','change','nested','waste','plan_obs','save_obs']:
    setattr(PrepContainerTests,_name,getattr(fixtures.PrepObservationTests,_name))
