"""Invented container loss, paired corrections and upgrade/restore checks."""
import asyncio, copy, os, unittest
from decimal import Decimal
from uuid import UUID, uuid4
from unittest.mock import patch
import asyncpg
from pydantic import ValidationError
import prep_containers as containers, prep_observations as observations, native_backup as backup, server
import test_prep_containers as fixtures


class ContainerWasteValidationTests(unittest.TestCase):
    def test_direct_container_waste_requires_measured_quantity_compartment_and_category(self):
        b=dict(action='waste',fill_id=uuid4(),quantity='1',compartment='storage',category='storage_spoilage',contents_measured=True,
            performed_at='2026-10-05T13:00:00-04:00',business_date='2026-10-05',timezone_name='America/New_York',calendar_date_confirmed=True,note='Measured loss')
        for change in ({'quantity':None},{'quantity':'0'},{'quantity':'NaN'},{'quantity':'-1'},{'quantity':'1.0000000000001'},{'contents_measured':1},{'calendar_date_confirmed':'true'},{'compartment':None},{'category':'service_discard'},{'source_batch_id':uuid4()}):
            with self.assertRaises(ValidationError):containers.WasteIn(**(b|change))
        self.assertEqual(containers.WasteIn(**b).quantity,1)
        with self.assertRaises(ValidationError):containers.MoveIn(**{k:v for k,v in b.items() if k not in ('compartment','category','contents_measured')}|{'action':'undo_waste'})


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PostgreSQL required')
class ContainerWasteTests(fixtures.PrepContainerTests):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        if self._testMethodName != 'test_direct_waste_additive_upgrade_preserves_old_commands_and_pending_preview':
            async with self.pool.acquire() as c:await c.execute((fixtures.recovery.counts.native.ROOT/'migrations/20261007_container_waste.sql').read_text())

    def loss(self,fill,quantity='2',compartment='storage',**changes):
        return self.stamp('2026-10-05T13:00:00-04:00')|dict(action='waste',fill_id=fill['id'],quantity=quantity,compartment=compartment,
            category='storage_spoilage' if compartment=='storage' else 'service_discard',contents_measured=True)|changes

    async def test_direct_waste_single_withdrawal_storage_service_and_food_cost_independent(self):
        _,a,b=await self.pair();actual=(await self.report(a,b)).json();await self.prepare('48');f=await self.fill('48')
        r=await self.command(self.loss(f,'8'));self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['current']['storage'],'40');self.assertEqual(r.json()['waste_event']['purpose'],'waste')
        await self.command(self.move(f,'send','10',performed_at='2026-10-05T14:00:00-04:00'))
        r=await self.command(self.loss(f,'3','service',performed_at='2026-10-05T15:00:00-04:00'));self.assertEqual(r.status_code,200,r.text)
        state=await self.container_state();l=state['lots'][0]
        self.assertEqual((l['remainingRecordedQuantity'],l['containerStorage'],l['containerService'],l['totalRemainingRecordedQuantity']),('0','30','7','37'))
        self.assertEqual((await self.report(a,b)).json(),actual)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT prep_inventory.lot_used($1)',UUID(self.lot['id'])),48)
            self.assertEqual(await c.fetchval('SELECT sum(quantity) FROM prep_inventory.waste_movements'),-11)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_logs'),0)

    async def test_direct_waste_exact_tiny_conversion_and_pinned_historical_unit(self):
        await self.prepare('20','2');f=await self.fill('10')
        await self.profile(self.p,'measured bag','3',self.u['id'])
        # Definition/profile display revisions do not invent new conversions for existing fills.
        d=await self.command(dict(action='definition',predecessor_id=self.definition['id'],name='Revised pan',capacity_unit='l',usable_capacity='4',evidence='Measured reference revision'))
        self.assertEqual(d.status_code,200,d.text)
        r=await self.command(self.loss(f,'0.000000000001'));self.assertEqual(r.status_code,200,r.text)
        event=r.json()['waste_event'];self.assertEqual(Decimal(event['review_snapshot']['baseQuantity']),Decimal('0.000000000002'))
        self.assertEqual(event['review_snapshot']['body']['profile_id'],self.u['id']);self.assertEqual(r.json()['current']['storage'],'19.999999999998')
        self.assertEqual((await self.preview_container(self.loss(f,'10.000000000001'))).status_code,409)

    async def test_direct_waste_paired_latest_reversal_restores_contents_and_journal_then_replacement(self):
        await self.prepare('48');f=await self.fill('48');r=await self.command(self.loss(f,'8'));self.assertEqual(r.status_code,200,r.text)
        target=r.json()['result'];undo=self.move(f,'undo_waste',target_move_id=target['id']);r=await self.command(undo);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['current']['storage'],'48');self.assertEqual(r.json()['waste_event']['kind'],'void')
        self.assertEqual(r.json()['waste_event']['predecessor_id'],r.json()['current']['waste_history'][0]['event']['id'])
        self.assertEqual(len(r.json()['current']['waste_history']),2)
        self.assertEqual((await self.preview_container(undo)).status_code,409)
        r=await self.command(self.loss(f,'5'));self.assertEqual(r.status_code,200,r.text)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT sum(quantity) FROM prep_inventory.waste_movements'),-5)
            self.assertEqual(await c.fetchval('SELECT prep_inventory.lot_used($1)',UUID(self.lot['id'])),48)

    async def test_direct_waste_rejects_late_reversal_wrong_time_generic_changes_and_overdraw(self):
        await self.prepare();f=await self.fill();r=await self.command(self.loss(f,'2'));self.assertEqual(r.status_code,200,r.text)
        move,event=r.json()['result'],r.json()['waste_event']
        self.assertEqual((await self.preview_container(self.move(f,'undo_waste',target_move_id=move['id'],performed_at='2026-10-05T14:00:00-04:00'))).status_code,422)
        self.assertEqual((await self.preview_container(self.loss(f,'1','service'))).status_code,409)
        self.assertEqual((await self.preview_container(self.loss(f,'1',performed_at='2026-10-05T12:00:00-04:00'))).status_code,422)
        p=await self.client.post(f"/api/pg/purchases/berts/prep-observations/waste/{event['id']}/change-preview",json={'kind':'void','reason':'Unpaired correction'})
        self.assertEqual(p.status_code,409,p.text)
        await self.command(self.move(f,'send','1',performed_at='2026-10-05T14:00:00-04:00'))
        self.assertEqual((await self.preview_container(self.move(f,'undo_waste',target_move_id=move['id']))).status_code,409)

    async def test_direct_waste_retry_races_binds_original_pair_actor_and_current_history(self):
        await self.prepare();f=await self.fill();body=self.loss(f,'2');p=await self.preview_container(body)
        payload=dict(body=body,expected_review_hash=p.json()['reviewHash'],reviewed=True);key=str(uuid4())
        race=await asyncio.gather(self.command(payload=payload,key=key),self.command(payload=payload,key=key))
        self.assertEqual([r.status_code for r in race],[200,200]);self.assertEqual(race[0].json()['waste_event'],race[1].json()['waste_event'])
        self.assertEqual((await self.command(payload=payload)).status_code,409)
        await self.command(self.move(f,'send','1'))
        replay=await self.command(payload=payload,key=key);self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json()['waste_event'],race[0].json()['waste_event']);self.assertEqual(replay.json()['current']['revision'],2)
        self.assertEqual((await self.command(payload=payload|{'body':body|{'quantity':'3'}},key=key)).status_code,409)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.container_waste_links'),1)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.waste_movements'),1)

    async def test_direct_waste_move_and_observation_failure_roll_back_entire_command(self):
        await self.prepare();f=await self.fill();before=await self.container_state()
        with patch.object(observations,'persist',side_effect=server.HTTPException(409,'Synthetic journal failure')):
            r=await self.command(self.loss(f));self.assertEqual(r.status_code,409,r.text)
        self.assertEqual(await self.container_state(),before)
        async with self.pool.acquire() as c:
            await c.execute("CREATE FUNCTION public.fail_loss_link() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Synthetic link failure'; END $$")
            await c.execute('CREATE TRIGGER loss_failure BEFORE INSERT ON prep_inventory.container_waste_links FOR EACH ROW EXECUTE FUNCTION public.fail_loss_link()')
        with self.assertRaises(asyncpg.RaiseError):await self.command(self.loss(f))
        self.assertEqual(await self.container_state(),before)
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.observations WHERE purpose=\'waste\''),0)

    async def test_direct_waste_database_seals_reject_orphan_movement_and_unpaired_void(self):
        await self.prepare();f=await self.fill();p=(await self.preview_container(self.loss(f))).json()['review']
        async with self.pool.acquire() as c:
            with self.assertRaises(asyncpg.RaiseError):
                async with c.transaction():
                    command,move=uuid4(),uuid4()
                    await c.execute('''INSERT INTO prep_inventory.container_commands(id,store_id,action,result_id,review_snapshot,review_hash,recorded_by,request_key,request_fingerprint)
                        VALUES($1,'berts','waste',$2,$3,$4,'synthetic-db',$5,$4)''',command,move,p,bytes(32),uuid4())
                    facts=p['facts']
                    await c.execute('''INSERT INTO prep_inventory.container_moves(id,command_id,store_id,fill_id,revision,action,quantity,storage_delta,service_delta,performed_at,business_date,timezone_name,note,compartment)
                        VALUES($1,$2,'berts',$3,1,'waste',2,-2,0,$4,$5,'America/New_York',$6,'storage')''',move,command,UUID(f['id']),containers.datetime.fromisoformat(facts['performed_at']),containers.date.fromisoformat(facts['business_date']),facts['note'])
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.container_moves'),0)
        r=await self.command(self.loss(f));self.assertEqual(r.status_code,200,r.text);event=r.json()['waste_event']
        async with self.pool.acquire() as c:
            plan=await observations.preview(c,'berts','waste',old_id=UUID(event['id']),change=observations.ChangeIn(kind='void',reason='Synthetic paired preview'),container_fill_id=UUID(f['id']))
            with self.assertRaises(asyncpg.RaiseError):
                async with c.transaction():await observations.persist(c,'berts',plan,uuid4(),b'x'*32,'synthetic-db')
            for sql in ('DELETE FROM prep_inventory.container_waste_links','UPDATE prep_inventory.container_waste_links SET observation_id=gen_random_uuid()'):
                with self.assertRaises(asyncpg.RaiseError):await c.execute(sql)

    async def test_direct_waste_additive_upgrade_preserves_old_commands_and_pending_preview(self):
        await self.prepare();f=await self.fill();old=await self.command(self.move(f,'send','3'));self.assertEqual(old.status_code,200,old.text)
        body=self.move(f,'return','1');p=await self.preview_container(body);payload=dict(body=body,expected_review_hash=p.json()['reviewHash'],reviewed=True)
        async with self.pool.acquire() as c:await c.execute((fixtures.recovery.counts.native.ROOT/'migrations/20261007_container_waste.sql').read_text())
        await self.pool.expire_connections()
        r=await self.command(payload=payload);self.assertEqual(r.status_code,200,r.text)
        self.assertNotIn('compartment',r.json()['result']);self.assertEqual(r.json()['current']['moves'][0],old.json()['result'])
        self.assertEqual(r.json()['current']['service'],'2')

    async def test_direct_waste_whole_restore_preserves_pair_and_original_retry_after_reversal(self):
        await self.prepare();f=await self.fill();body=self.loss(f);p=await self.preview_container(body);payload=dict(body=body,expected_review_hash=p.json()['reviewHash'],reviewed=True);key=str(uuid4())
        first=await self.command(payload=payload,key=key);self.assertEqual(first.status_code,200,first.text)
        r=await self.command(self.move(f,'undo_waste',target_move_id=first.json()['result']['id']));self.assertEqual(r.status_code,200,r.text)
        before=await self.container_state();manifest=await backup.create_backup(self.source,fixtures.recovery.PG_DUMP,self.directory)
        self.assertEqual(manifest['tables']['prep_inventory.container_waste_links']['rows'],2)
        dsn=await self.target();self.assertEqual((await backup.verify_restore(dsn,self.directory))['status'],'verified')
        client,pool=await self.restored_client(dsn)
        original=self.client;self.client=client
        try:
            self.assertEqual(await self.container_state(),before)
            replay=await self.command(payload=payload,key=key);self.assertEqual(replay.status_code,200,replay.text)
            self.assertEqual(replay.json()['waste_event'],first.json()['waste_event']);self.assertEqual(replay.json()['current']['storage'],'10')
            async with pool.acquire() as c:self.assertFalse(await c.fetchval("SELECT EXISTS(SELECT 1 FROM pg_class c,aclexplode(c.relacl) a WHERE c.oid='prep_inventory.container_waste_links'::regclass AND a.grantee<>c.relowner)"))
        finally:self.client=original;await client.aclose();await pool.close()
