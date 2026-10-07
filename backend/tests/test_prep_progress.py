"""Invented partial production, correction review and immutable upgrade/restore."""
import asyncio,os,unittest
from datetime import date
from uuid import UUID,uuid4
from decimal import Decimal
import asyncpg
from pydantic import ValidationError
import server,prep_execution as execution,native_backup as backup
from purchase_parser import fingerprint
from purchase_api import serial
import test_prep_execution as fixtures


class ProgressValidationTests(unittest.TestCase):
    def test_partial_finish_and_reconcile_have_explicit_distinct_evidence(self):
        base=dict(action='link',draft_version_id=uuid4(),task_id=uuid4(),batch_event_id=uuid4(),reason='Measured progress')
        self.assertEqual(execution.Command(**base).action,'link')
        for changes in ({'batch_event_id':None},{'task_complete':False},{'link_event_id':uuid4()},{'action':'finish'},{'action':'reconcile'}):
            with self.assertRaises(ValidationError):execution.Command(**(base|changes))
        r=base|dict(action='reconcile',link_event_id=uuid4(),task_complete=False)
        self.assertFalse(execution.Command(**r).task_complete)
        for value in (0,1,'true','false'):
            with self.assertRaises(ValidationError):execution.Command(**(r|{'task_complete':value}))
        self.assertEqual(execution.Command(**(base|{'action':'finish','batch_event_id':None})).action,'finish')
        self.assertNotIn('link_event_id',execution.Command(action='release',draft_version_id=uuid4(),reason='Review').payload())


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PG required')
class PrepProgressTests(fixtures.PrepExecutionTests):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with self.pool.acquire() as c:await c.execute((fixtures.fixtures.recovery.counts.native.ROOT/'migrations/20261007_prep_progress.sql').read_text())

    async def start(self):
        d=await self.known_draft();r=await self.write_execution(self.command(d));self.assertEqual(r.status_code,200,r.text)
        return d,r.json()['current']['tasks'][0]

    async def link(self,d,task,batch,version,action='link',**changes):
        r=await self.write_execution(self.command(d,action,task_id=task['id'],batch_event_id=batch['id'],**changes),version)
        self.assertEqual(r.status_code,200,r.text);return r.json()

    async def correct(self,batch,quantity=None):
        if quantity is None:change={'kind':'void','reason':'Invented erroneous production'}
        else:
            body=await self.entry(output_quantity=quantity,performed_at=batch['performed_at'],business_date=batch['business_date'])
            change={'kind':'replacement','replacement':body,'reason':'Invented corrected measured output'}
        path=f"/api/pg/purchases/berts/prep-batches/{batch['id']}"
        p=await self.catalog.post(path+'/change-preview',json=change);self.assertEqual(p.status_code,200,p.text)
        r=await self.catalog.post(path+'/changes',json=dict(change=change,expected_review_hash=p.json()['reviewHash'],reviewed=True),headers={'Idempotency-Key':str(uuid4())});self.assertEqual(r.status_code,200,r.text)
        return r.json()['event']

    async def reconcile(self,d,task,batch,link,version,closed=False):
        return await self.link(d,task,batch,version,'reconcile',link_event_id=link['id'],task_complete=closed)

    async def test_multiple_partial_batches_accumulate_exactly_without_automatic_finish_or_accounting_writes(self):
        _,a,b=await self.pair();actual=(await self.report(a,b)).json();d,t=await self.start()
        first=await self.production(output_quantity='1.123456789012');second=await self.production(output_quantity='2.000000000001')
        async with self.pool.acquire() as c:movements=await c.fetchval('SELECT count(*) FROM prep_inventory.batch_movements')
        r=await self.link(d,t,first,1);self.assertEqual(r['current']['task_progress'][0]['status'],'in_progress')
        r=await self.link(d,t,second,2);p=r['current']['task_progress'][0]
        self.assertEqual(Decimal(p['reviewed_base_quantity']),Decimal('3.123456789013'));self.assertFalse(p['closed']);self.assertEqual(len(p['links']),2)
        command=self.command(d,'finish',task_id=t['id']);r=await self.write_execution(command,3);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['current']['task_progress'][0]['status'],'complete')
        self.assertEqual(actual,(await self.report(a,b)).json())
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.batch_movements'),movements)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.batch_events'),2)
        third=await self.production(output_quantity='1')
        self.assertEqual((await self.preview_execution(self.command(d,'link',task_id=t['id'],batch_event_id=third['id']),4)).status_code,409)

    async def test_changed_completion_requires_review_latest_version_and_can_remain_finished(self):
        d,t=await self.start();batch=await self.production(output_quantity='3');linked=await self.link(d,t,batch,1,'complete')
        corrected=await self.correct(batch,'2');s=await self.execution_state();p=s['task_progress'][0]
        self.assertEqual(p['status'],'needs_review');self.assertEqual(p['reviewed_base_quantity'],'0');self.assertEqual(p['effective_base_quantity'],'2')
        command=self.command(d,'reconcile',task_id=t['id'],batch_event_id=batch['id'],link_event_id=linked['event']['id'],task_complete=True)
        self.assertEqual((await self.preview_execution(command,2)).status_code,422)
        r=await self.reconcile(d,t,corrected,linked['event'],2,True);p=r['current']['task_progress'][0]
        self.assertEqual(p['status'],'complete');self.assertEqual(p['reviewed_base_quantity'],'2');self.assertFalse(p['needs_review'])
        self.assertEqual(r['current']['completions'][0]['linked_batch_event_id'],batch['id'])
        self.assertEqual(r['current']['completions'][0]['acknowledged_batch_event_id'],corrected['id'])
        corrected_again=await self.correct(corrected,'1');self.assertTrue((await self.execution_state())['task_progress'][0]['needs_review'])
        r=await self.reconcile(d,t,corrected_again,linked['event'],3,False);self.assertFalse(r['current']['task_progress'][0]['closed'])

    async def test_void_reconciliation_opens_task_replacement_production_finishes_without_root_reuse(self):
        d,t=await self.start();batch=await self.production();linked=await self.link(d,t,batch,1,'complete');void=await self.correct(batch)
        command=self.command(d,'reconcile',task_id=t['id'],batch_event_id=void['id'],link_event_id=linked['event']['id'],task_complete=True)
        self.assertEqual((await self.preview_execution(command,2)).status_code,409)
        r=await self.reconcile(d,t,void,linked['event'],2);p=r['current']['task_progress'][0]
        self.assertEqual(p['status'],'open');self.assertEqual(p['reviewed_base_quantity'],'0');self.assertFalse(p['needs_review'])
        self.assertEqual((await self.preview_execution(self.command(d,'finish',task_id=t['id']),3)).status_code,409)
        replacement=await self.production(output_quantity='3');await self.link(d,t,replacement,3)
        r=await self.write_execution(self.command(d,'finish',task_id=t['id']),4);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['current']['task_progress'][0]['reviewed_base_quantity'],'3')
        self.assertEqual((await self.preview_day(version=1)).status_code,409)
        self.assertEqual((await self.preview_execution(self.command(d,'reopen'),5)).status_code,409)

    async def test_reconciliation_cannot_hide_other_changed_links_or_select_an_unrelated_batch(self):
        d,t=await self.start();a=await self.production(output_quantity='1');b=await self.production(output_quantity='2')
        la=await self.link(d,t,a,1);lb=await self.link(d,t,b,2)
        ca=await self.correct(a,'1.5');cb=await self.correct(b,'2.5')
        command=self.command(d,'reconcile',task_id=t['id'],batch_event_id=ca['id'],link_event_id=la['event']['id'],task_complete=True)
        self.assertEqual((await self.preview_execution(command,3)).status_code,409)
        command.update(batch_event_id=cb['id'],task_complete=False);self.assertEqual((await self.preview_execution(command,3)).status_code,422)
        await self.reconcile(d,t,ca,la['event'],3)
        r=await self.reconcile(d,t,cb,lb['event'],4,True);self.assertEqual(r['current']['task_progress'][0]['reviewed_base_quantity'],'4.0')

    async def test_parallel_partial_and_finish_retry_stale_reconciliation_preview_and_actor_keys(self):
        d,t=await self.start();batch=await self.production(output_quantity='2');command=self.command(d,'link',task_id=t['id'],batch_event_id=batch['id'])
        p=await self.preview_execution(command,1);payload=dict(command=command,expected_review_hash=p.json()['reviewHash'],reviewed=True);key=str(uuid4())
        raced=await asyncio.gather(self.write_execution(version=1,key=key,payload=payload),self.write_execution(version=1,key=key,payload=payload))
        self.assertEqual([r.status_code for r in raced],[200,200]);linked=raced[0].json()['event']
        corrected=await self.correct(batch,'3');command=self.command(d,'reconcile',task_id=t['id'],batch_event_id=corrected['id'],link_event_id=linked['id'],task_complete=False)
        p=await self.preview_execution(command,2);payload2=dict(command=command,expected_review_hash=p.json()['reviewHash'],reviewed=True)
        await self.correct(corrected,'4');self.assertEqual((await self.write_execution(version=2,payload=payload2)).status_code,422)
        replay=await self.write_execution(version=1,key=key,payload=payload);self.assertEqual(replay.status_code,200,replay.text);self.assertTrue(replay.json()['current']['task_progress'][0]['needs_review'])

    async def test_original_command_digest_and_immutable_records_survive_additive_upgrade(self):
        d=await self.known_draft();command=self.command(d);p=await self.preview_execution(command);payload=dict(command=command,expected_review_hash=p.json()['reviewHash'],reviewed=True);key=str(uuid4())
        r=await self.write_execution(key=key,payload=payload);self.assertEqual(r.status_code,200,r.text)
        async with self.pool.acquire() as c:
            stored=await c.fetchval('SELECT request_fingerprint FROM prep_inventory.execution_events WHERE request_key=$1',UUID(key))
            self.assertEqual(stored,fingerprint(serial(dict(store='berts',day=date(2026,10,8),track='daily',actor='synthetic-catalog-reviewer',expected=0,body=execution.Commit(**payload).model_dump()|{'command':execution.Command(**command).payload()}))))
            self.assertNotIn('link_event_id',r.json()['event']['review_snapshot']['command'])
            for sql in ('DELETE FROM prep_inventory.execution_events','UPDATE prep_inventory.execution_events SET task_complete=false'):
                with self.assertRaises(asyncpg.RaiseError):await c.execute(sql)

    async def test_progress_and_reconciliation_restore_retains_exact_retry_and_measured_totals(self):
        d,t=await self.start();a=await self.production(output_quantity='1');b=await self.production(output_quantity='2')
        first=await self.link(d,t,a,1);await self.link(d,t,b,2);ca=await self.correct(a,'1.25')
        command=self.command(d,'reconcile',task_id=t['id'],batch_event_id=ca['id'],link_event_id=first['event']['id'],task_complete=True)
        p=await self.preview_execution(command,3);payload=dict(command=command,expected_review_hash=p.json()['reviewHash'],reviewed=True);key=str(uuid4())
        r=await self.write_execution(version=3,key=key,payload=payload);self.assertEqual(r.status_code,200,r.text);before=await self.execution_state()
        manifest=await backup.create_backup(self.source,fixtures.fixtures.recovery.PG_DUMP,self.directory);self.assertEqual(manifest['tables']['prep_inventory.execution_events']['rows'],4)
        dsn=await self.target();self.assertEqual((await backup.verify_restore(dsn,self.directory))['status'],'verified')
        pool=await asyncpg.create_pool(dsn,min_size=1,max_size=2,init=fixtures.fixtures.recovery.db_pg._init_connection);old=server.db_pg._pool;server.db_pg._pool=pool
        try:
            self.assertEqual(await self.execution_state(),before)
            replay=await self.write_execution(version=3,key=key,payload=payload);self.assertEqual(replay.status_code,200,replay.text);self.assertTrue(replay.json()['replayed'])
            self.assertEqual(replay.json()['current']['task_progress'][0]['reviewed_base_quantity'],'3.25')
        finally:server.db_pg._pool=old;await pool.close()

    async def test_database_rejects_empty_finish_fabricated_totals_and_void_closure(self):
        d,t=await self.start()
        async def direct(c,p):
            cmd=p['command'];uid=lambda value:UUID(value) if value else None
            return await c.fetchval('''INSERT INTO prep_inventory.execution_events(list_id,store_id,revision,predecessor_id,action,draft_version_id,
                release_event_id,task_id,batch_event_id,batch_root_id,reason,actor,review_snapshot,review_hash,request_key,request_fingerprint,link_event_id,task_complete)
                VALUES($1,'berts',$2,$3,$4,$5,$6,$7,$8,$9,$10,'synthetic-DB-probe',$11,$12,$13,$12,$14,$15) RETURNING id''',
                UUID(d['list_id']),p['base_revision']+1,await c.fetchval('SELECT id FROM prep_inventory.execution_events WHERE list_id=$1 ORDER BY revision DESC LIMIT 1',UUID(d['list_id'])),
                cmd['action'],UUID(d['id']),uid(p['release_event_id']),uid(cmd['task_id']),uid(cmd['batch_event_id']),uid(p['batch']['root_id']) if p['batch'] else None,
                cmd['reason'],p,bytes(32),uuid4(),uid(cmd['link_event_id']),cmd['task_complete'])
        s=await self.execution_state();review=dict(store_id='berts',prep_date='2026-10-08',track='daily',base_revision=1,
            command=serial(execution.Command(**self.command(d,'finish',task_id=t['id'])).payload()),draft_review_hash=d['review_hash'],release_event_id=s['release']['id'],
            task=t,batch=None,status_after='released',progress_before=s['task_progress'][0],original_link=None)
        async with self.pool.acquire() as c:
            with self.assertRaises(asyncpg.RaiseError) as zero:await direct(c,review)
            self.assertIn('Finish requires positive reviewed production',str(zero.exception))
        batch=await self.production(output_quantity='2');linked=await self.link(d,t,batch,1)
        p=await self.preview_execution(self.command(d,'finish',task_id=t['id']),2);self.assertEqual(p.status_code,200,p.text)
        forged=p.json()['review'];forged['progress_before']['reviewed_base_quantity']='999'
        async with self.pool.acquire() as c:
            with self.assertRaises(asyncpg.RaiseError) as fake:await direct(c,forged)
            self.assertIn('Reviewed task progress changed',str(fake.exception))
        void=await self.correct(batch);command=self.command(d,'reconcile',task_id=t['id'],batch_event_id=void['id'],link_event_id=linked['event']['id'],task_complete=False)
        p=await self.preview_execution(command,2);self.assertEqual(p.status_code,200,p.text);forged=p.json()['review'];forged['command']['task_complete']=True
        async with self.pool.acquire() as c:
            before=await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'")
            with self.assertRaises(asyncpg.RaiseError) as closed:await direct(c,forged)
            self.assertIn('Void or other changed production prevents closing',str(closed.exception))
            self.assertEqual(await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'"),before)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.execution_events'),2)

    async def test_different_key_partial_race_reserves_root_once_and_repeated_review_is_held(self):
        d,t=await self.start();batch=await self.production(output_quantity='2');command=self.command(d,'link',task_id=t['id'],batch_event_id=batch['id'])
        p=await self.preview_execution(command,1);payload=dict(command=command,expected_review_hash=p.json()['reviewHash'],reviewed=True)
        raced=await asyncio.gather(self.write_execution(version=1,payload=payload),self.write_execution(version=1,payload=payload))
        self.assertEqual(sorted(r.status_code for r in raced),[200,409]);link=next(r.json()['event'] for r in raced if r.status_code==200)
        self.assertEqual((await self.preview_execution(command,2)).status_code,409)
        corrected=await self.correct(batch,'3');r=await self.reconcile(d,t,corrected,link,2)
        cmd=self.command(d,'reconcile',task_id=t['id'],batch_event_id=corrected['id'],link_event_id=link['id'],task_complete=False)
        self.assertEqual((await self.preview_execution(cmd,3)).status_code,409)
        self.assertFalse(r['current']['task_progress'][0]['needs_review'])


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PG required')
class ProgressUpgradeTests(fixtures.PrepExecutionTests):
    async def test_actual_upgrade_preserves_old_completion_request_hashes_and_exact_retry(self):
        d=await self.known_draft();r=await self.write_execution(self.command(d));self.assertEqual(r.status_code,200,r.text)
        t=r.json()['current']['tasks'][0];batch=await self.production();command=self.command(d,'complete',task_id=t['id'],batch_event_id=batch['id'])
        p=await self.preview_execution(command,1);payload=dict(command=command,expected_review_hash=p.json()['reviewHash'],reviewed=True);key=str(uuid4())
        r=await self.write_execution(version=1,key=key,payload=payload);self.assertEqual(r.status_code,200,r.text);self.assertFalse(r.json()['current']['progress_supported'])
        async with self.pool.acquire() as c:
            before=await c.fetch('SELECT id,revision,recorded_at,review_snapshot,review_hash,request_fingerprint FROM prep_inventory.execution_events ORDER BY revision')
            await c.execute((fixtures.fixtures.recovery.counts.native.ROOT/'migrations/20261007_prep_progress.sql').read_text())
            self.assertEqual(await c.fetch('SELECT id,revision,recorded_at,review_snapshot,review_hash,request_fingerprint FROM prep_inventory.execution_events ORDER BY revision'),before)
        # The fixture caches statements, unlike db_pg's production pool. Recycle
        # its connections after DDL, as in a stopped-app migration/restart rehearsal.
        await self.pool.expire_connections()
        replay=await self.write_execution(version=1,key=key,payload=payload);self.assertEqual(replay.status_code,200,replay.text)
        self.assertTrue(replay.json()['replayed']);self.assertTrue(replay.json()['current']['progress_supported'])
        self.assertEqual(replay.json()['current']['task_progress'][0]['status'],'complete')
