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
        if self._testMethodName.startswith('test_review_corrections_') and 'upgrade' not in self._testMethodName:
            await self.correction_migration()

    async def correction_migration(self):
        async with self.pool.acquire() as c:
            await c.execute((fixtures.recovery.counts.native.ROOT/'migrations/20261008_container_waste_corrections.sql').read_text())

    async def test_review_corrections_waste_after_transfer_and_transfer_undo_restores_pair(self):
        _, a, b = await self.pair()
        actual = (await self.report(a,b)).json()
        await self.prepare()
        fill = await self.fill()
        first = await self.command(self.loss(fill,'2'))
        self.assertEqual(first.status_code,200,first.text)
        sent = await self.command(self.move(fill,'send','1',performed_at='2026-10-05T14:00:00-04:00'))
        self.assertEqual(sent.status_code,200,sent.text)
        reverse = await self.command(self.move(fill,'undo',target_move_id=sent.json()['result']['id'],performed_at='2026-10-05T14:00:00-04:00'))
        self.assertEqual(reverse.status_code,200,reverse.text)
        correction = self.move(fill,'undo_waste',target_move_id=first.json()['result']['id'])
        restored = await self.command(correction)
        self.assertEqual(restored.status_code,200,restored.text)
        self.assertEqual((restored.json()['current']['storage'],restored.json()['current']['service']),('10','0'))
        self.assertEqual(restored.json()['waste_event']['predecessor_id'],first.json()['waste_event']['id'])
        self.assertEqual((await self.preview_container(correction)).status_code,409)
        self.assertEqual((await self.report(a,b)).json(),actual)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT sum(quantity) FROM prep_inventory.waste_movements'),0)
            self.assertEqual(await c.fetchval('SELECT prep_inventory.lot_used($1)',UUID(self.lot['id'])),10)

    async def test_review_corrections_waste_quantity_dependencies_and_stale_reviews_are_held(self):
        await self.prepare()
        fill = await self.fill()
        first = await self.command(self.loss(fill,'2'))
        correction = self.move(fill,'undo_waste',target_move_id=first.json()['result']['id'])
        p = await self.preview_container(correction)
        self.assertEqual(p.status_code,200,p.text)
        await self.command(self.move(fill,'send','1',performed_at='2026-10-05T14:00:00-04:00'))
        before = await self.container_state()
        stale = await self.command(payload=dict(body=correction,expected_review_hash=p.json()['reviewHash'],reviewed=True))
        self.assertEqual(stale.status_code,409,stale.text)
        self.assertEqual(await self.container_state(),before)
        await self.command(self.move(fill,'unpack','1',performed_at='2026-10-05T15:00:00-04:00'))
        held = await self.preview_container(correction)
        self.assertEqual(held.status_code,409,held.text)
        self.assertIn('dependencies',held.json()['detail'])
        async with self.pool.acquire() as c:
            self.assertFalse(await c.fetchval('SELECT prep_inventory.can_reverse_container_waste($1,$2)',UUID(fill['id']),UUID(first.json()['result']['id'])))

    async def test_review_corrections_waste_cross_module_key_rolls_back_contents_and_journal(self):
        await self.prepare()
        fill = await self.fill()
        raw = self.stamp() | dict(source_kind='raw',raw_item_code='test_food',quantity='1',source_unit='lb',factor='1',
            measurement_basis='measured',already_included_in_batch=False,category='other')
        p = await self.client.post('/api/pg/purchases/berts/prep-observations/waste/preview',json=raw)
        self.assertEqual(p.status_code,200,p.text)
        key = str(uuid4())
        recorded = await self.save('prep-observations/waste',dict(body=raw,expected_review_hash=p.json()['reviewHash'],reviewed=True),key)
        self.assertEqual(recorded.status_code,200,recorded.text)
        before = await self.container_state()
        lost = await self.command(self.loss(fill),key=key)
        self.assertEqual(lost.status_code,409,lost.text)
        self.assertEqual(await self.container_state(),before)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.container_moves'),0)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.container_waste_links'),0)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.observations'),1)

    async def test_workflow_reads_batched_fills_preserve_pairs_and_pending_hash(self):
        from purchase_api import serial
        await self.prepare()
        first = await self.fill()
        second = await self.fill('2')
        loss = await self.command(self.loss(first,'1.000000000001'))
        self.assertEqual(loss.status_code,200,loss.text)
        async def original(conn,store,ident):
            row = await conn.fetchrow('SELECT * FROM prep_inventory.container_fills WHERE id=$1 AND store_id=$2',ident,store)
            moves = [containers.move_record(r) for r in await conn.fetch('SELECT * FROM prep_inventory.container_moves WHERE fill_id=$1 ORDER BY revision',ident)]
            history = []
            for link in await conn.fetch('''SELECT l.* FROM prep_inventory.container_waste_links l JOIN prep_inventory.container_moves m ON m.id=l.move_id
                WHERE m.fill_id=$1 ORDER BY m.revision''',ident):
                event = await conn.fetchrow('SELECT * FROM prep_inventory.observations WHERE id=$1',link['observation_id'])
                history.append(dict(link=dict(link),event=dict(event)))
            storage = containers.batches.exact_sum([row['base_quantity']]+[m['storage_delta'] for m in moves])
            service = containers.batches.exact_sum(m['service_delta'] for m in moves)
            result = dict(fill=dict(row),moves=moves,storage=storage,service=service,allocated=containers.batches.exact_sum([storage,service]),revision=len(moves),voided=any(m['action']=='void_fill' for m in moves))
            if history:result['waste_history']=history
            return serial(result)
        async with self.pool.acquire() as c,c.transaction(isolation='repeatable_read',readonly=True):
            expected = [await original(c,'berts',UUID(fill['id'])) for fill in (second,first)]
            self.assertEqual(await containers.fill_states(c,'berts'),expected)
            self.assertEqual(await containers.fill_states(c,'rudds'),[])
            with self.assertRaises(server.HTTPException) as held:await containers.fill_state(c,'rudds',UUID(first['id']))
            self.assertEqual(held.exception.status_code,404)
        body = self.move(first,'send','1')
        with patch.object(containers,'fill_state',side_effect=original):
            pending = await self.preview_container(body)
        fresh = await self.preview_container(body)
        self.assertEqual(fresh.status_code,200,fresh.text)
        self.assertEqual(fresh.json(),pending.json())
        committed = await self.command(payload=dict(body=body,expected_review_hash=pending.json()['reviewHash'],reviewed=True))
        self.assertEqual(committed.status_code,200,committed.text)

    async def test_review_corrections_waste_upgrade_preserves_preview_retry_and_restored_function(self):
        await self.prepare()
        fill = await self.fill()
        loss = self.loss(fill)
        preview = await self.preview_container(loss)
        payload = dict(body=loss,expected_review_hash=preview.json()['reviewHash'],reviewed=True)
        key = str(uuid4())
        first = await self.command(payload=payload,key=key)
        self.assertEqual(first.status_code,200,first.text)
        undo = self.move(fill,'undo_waste',target_move_id=first.json()['result']['id'])
        pending = await self.preview_container(undo)
        self.assertEqual(pending.status_code,200,pending.text)
        await self.correction_migration()
        await self.pool.expire_connections()
        self.assertEqual((await self.preview_container(undo)).json(),pending.json())
        result = await self.command(payload=dict(body=undo,expected_review_hash=pending.json()['reviewHash'],reviewed=True))
        self.assertEqual(result.status_code,200,result.text)
        before = await self.container_state()
        await backup.create_backup(self.source,fixtures.recovery.PG_DUMP,self.directory)
        dsn = await self.target()
        self.assertEqual((await backup.verify_restore(dsn,self.directory))['status'],'verified')
        client,pool = await self.restored_client(dsn)
        original = self.client
        self.client = client
        try:
            self.assertEqual(await self.container_state(),before)
            replay = await self.command(payload=payload,key=key)
            self.assertEqual(replay.status_code,200,replay.text)
            self.assertEqual(replay.json()['waste_event'],first.json()['waste_event'])
            async with pool.acquire() as c:
                self.assertTrue(await c.fetchval("SELECT to_regprocedure('prep_inventory.can_reverse_container_waste(uuid,uuid)') IS NOT NULL"))
                self.assertFalse(await c.fetchval("SELECT EXISTS(SELECT 1 FROM pg_proc p,aclexplode(p.proacl) a WHERE p.oid='prep_inventory.can_reverse_container_waste(uuid,uuid)'::regprocedure AND a.grantee<>p.proowner)"))
        finally:
            self.client = original
            await client.aclose()
            await pool.close()

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
