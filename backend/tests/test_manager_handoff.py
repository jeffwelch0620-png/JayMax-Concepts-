"""Fictional manager journal: no hosted account, credential or business data."""
import asyncio
import json
import hashlib
import os
import subprocess
import tempfile
from datetime import date
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
from starlette.requests import Request
import manager_actor
import manager_handoff as handoff
import runtime_permissions
import manager_handoff_schema
from test_native_purchases import PurchaseIntegrationTests, ROOT


def body(**changes):
    return dict(action='create_draft', note_id=str(uuid4()), business_date='2026-10-25', prep_track='bulk',
                settings_revision=1, summary='TEST ONLY: batch summary 🍲', next_shift_note='Verify labelled portions',
                reported_readiness='not_assessed', correction_reason='') | changes


class HandoffValidationTests(unittest.TestCase):
    def test_strict_content_date_scope_and_revision_boundaries(self):
        self.assertEqual(handoff.Command(**body()).business_date, date(2026, 10, 25))
        self.assertEqual(len(handoff.Command(**body(summary='🍲'*6000)).summary), 6000)
        for change in ({'summary':' '}, {'summary':'x'*6001}, {'summary':'\ud800'}, {'summary':'\x00'}, {'next_shift_note':'x'*4001},
                       {'settings_revision':True}, {'settings_revision':2147483648}, {'business_date':0},
                       {'business_date':'2026-02-30'}, {'business_date':'2026-10-25T12:00:00Z'},
                       {'prep_track':'any'}, {'actor_id':'forged'}, {'correction_reason':'unsolicited'},
                       {'action':'correct'}):
            with self.subTest(change=repr(change)), self.assertRaises(ValidationError): handoff.Command(**body(**change))
        handoff.Command(**body(action='correct', correction_reason='Confirmed correction'))
        self.assertEqual(handoff.Command(**body(summary='\ufefftrim\ufeff')).summary,'trim')
        self.assertEqual(handoff.Command(**body(summary='\u0085preserve\u0085')).summary,'\u0085preserve\u0085')

    def test_expected_version_requires_ascii_and_refuses_unbounded_or_missing_headers(self):
        def request(v): return Request({'type':'http','headers':[(b'if-match',v.encode('latin1'))]})
        self.assertEqual(handoff.version(request('"0"')),0)
        self.assertEqual(handoff.version(request('2147483646')),2147483646)
        for invalid in ('','-1','2147483647','²','"1','1"','1.0','*','0'*13):
            with self.subTest(invalid=invalid),self.assertRaises(HTTPException):handoff.version(request(invalid))

    def test_exact_request_fingerprint_uses_unicode_and_all_identity_fields(self):
        value=handoff.Command(**body(note_id='11111111-1111-4111-8111-111111111111'))
        original=handoff.digest('berts','usr_test',value,0)
        self.assertEqual(original, '70b76d6717fca4232b19e2c26ac1ef8e3c444d587588664655ce4974dd371f72')
        variants=[handoff.digest('rudds','usr_test',value,0), handoff.digest('berts','usr_other',value,0),
                  handoff.digest('berts','usr_test',value,1),
                  handoff.digest('berts','usr_test',handoff.Command(**body(**(value.model_dump()|{'summary':'different'}))),0)]
        self.assertTrue(all(v!=original for v in variants))

    def test_default_off_and_no_live_seed_or_grants(self):
        with patch.dict(os.environ,{},clear=True): self.assertFalse(handoff.enabled())
        sql=(ROOT/'migrations/20261025_manager_handoff_notes.sql').read_text()
        self.assertNotIn('SECURITY DEFINER',sql.upper()); self.assertNotIn('GRANT ',sql.upper())
        self.assertNotIn('INSERT INTO',sql.upper())

    def test_business_day_uses_reviewed_timezone_across_midnight(self):
        from datetime import datetime, timezone
        with patch.object(handoff,'datetime') as clock:
            clock.now.return_value=datetime(2026,10,25,2,0,tzinfo=timezone.utc)
            self.assertEqual(handoff.business_today('America/New_York'),date(2026,10,24))
            self.assertEqual(handoff.business_today('UTC'),date(2026,10,25))

    def test_receiving_configuration_is_separate_from_sealed_native_installers(self):
        import deployment_readiness
        self.assertNotIn(manager_handoff_schema.MIGRATION,deployment_readiness.MIGRATIONS)
        self.assertEqual(len(deployment_readiness.MIGRATIONS),31)
        self.assertEqual(manager_handoff_schema.configuration({}, {})['status'],'passed')
        backend={'MANAGER_HANDOFF_NOTES_ENABLED':'true','USE_PG':'true','AUTH_SECRET':'fictional-private'}
        frontend={'REACT_APP_MANAGER_HANDOFF_NOTES':'true','REACT_APP_USE_PG':'true'}
        self.assertEqual(manager_handoff_schema.configuration(backend,frontend)['status'],'passed')
        for b,f in ((backend,{}), (backend|{'AUTH_SECRET':''},frontend),(backend|{'USE_PG':'false'},frontend)):
            result=manager_handoff_schema.configuration(b,f);self.assertEqual(result['status'],'held');self.assertNotIn('fictional-private',str(result))


class HandoffActorTests(unittest.IsolatedAsyncioTestCase):
    async def test_current_id_role_location_required_without_email_or_header_linking(self):
        accounts=Mock(); accounts.fetchrow=AsyncMock(return_value={'id':'usr_test','role':'manager','locations':['berts']})
        decode=Mock(return_value={'sub':'usr_test','role':'owner','email':'claimed@example.invalid'})
        def request(token=True):
            return Request({'type':'http','headers':[(b'authorization',b'Bearer fictional')] if token else [(b'oai-authenticated-user-id',b'usr_test')]})
        self.assertEqual(await manager_actor.resolve(request(),'berts',decode,lambda:accounts,True),'usr_test')
        self.assertEqual(accounts.fetchrow.call_args.args[1],'usr_test')
        for row in (None, {'id':'usr_test','role':'staff','locations':['berts']},
                    {'id':'usr_test','role':'readonly','locations':['berts']},
                    {'id':'usr_test','role':'manager','locations':['rudds']}):
            accounts.fetchrow.return_value=row
            with self.subTest(row=row),self.assertRaises(HTTPException) as error:
                await manager_actor.resolve(request(),'berts',decode,lambda:accounts,True)
            self.assertEqual(error.exception.status_code,403)
        accounts.fetchrow.reset_mock()
        for configured, store, signed in ((False,'berts',True),(True,'comm',True),(True,'berts',False)):
            with self.assertRaises(HTTPException): await manager_actor.resolve(request(signed),store,decode,lambda:accounts,configured)
        accounts.fetchrow.assert_not_called()
        decode.return_value={'email':'same@example.invalid'}
        with self.assertRaises(HTTPException): await manager_actor.resolve(request(),'berts',decode,lambda:accounts,True)

    async def test_account_failure_is_sanitized_and_never_falls_back_to_claims(self):
        accounts=Mock(); accounts.fetchrow=AsyncMock(side_effect=RuntimeError('private DSN diagnostic'))
        request=Request({'type':'http','headers':[(b'authorization',b'Bearer fictional')]})
        with self.assertRaises(HTTPException) as error:
            await manager_actor.resolve(request,'berts',lambda t:{'sub':'usr_test'},lambda:accounts,True)
        self.assertEqual(error.exception.status_code,503); self.assertNotIn('DSN',error.exception.detail)

    async def test_server_adapter_requires_actual_signed_personal_subject_even_when_auth_is_optional(self):
        import server
        accounts=Mock(); accounts.fetchrow=AsyncMock(return_value={'id':'usr_test','role':'owner','locations':[]})
        def request(token=None):
            return Request({'type':'http','headers':[(b'authorization',('Bearer '+token).encode())] if token else [(b'oai-authenticated-user-id',b'usr_test')]})
        with patch.object(server,'AUTH_SECRET','fictional-local-signing-key'),patch.object(server,'USE_PG',True),\
             patch.object(server,'AUTH_REQUIRED',False),patch.object(server.db_auxiliary,'pool',return_value=accounts):
            token=server._token({'id':'usr_test','email':'owner@example.invalid','role':'owner','locations':[]})
            self.assertEqual(await server._manager_handoff_actor(request(token),'berts'),'usr_test')
            with patch.object(server,'SESSION_TTL',-20): expired=server._token({'id':'usr_test','email':'owner@example.invalid','role':'owner'})
            for invalid in (None,token+'invalid',expired,server._token({'id':'','email':'owner@example.invalid','role':'owner'})):
                with self.assertRaises(HTTPException) as error: await server._manager_handoff_actor(request(invalid),'berts')
                self.assertEqual(error.exception.status_code,401)
            with patch.object(server,'AUTH_SECRET',''):
                with self.assertRaises(HTTPException) as error: await server._manager_handoff_actor(request(token),'berts')
                self.assertEqual(error.exception.status_code,503)
            self.assertIn('/api/pg/operations/{store}/handoff-notes/commands',{r.path for r in server.app.routes})


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable loopback PostgreSQL required')
class HandoffDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await PurchaseIntegrationTests.asyncSetUp(self)
        async with self.pool.acquire() as c:
            await c.execute((ROOT/'migrations/20261025_manager_handoff_notes.sql').read_text())
            await c.execute("INSERT INTO operations.store_settings VALUES ('berts','America/New_York',1),('rudds','America/New_York',1)")
            await c.execute("INSERT INTO public.app_users(id,email,password_hash,role,locations) VALUES ('usr_owner','owner@example.invalid','not-a-password','owner','{}'),('usr_manager','manager@example.invalid','not-a-password','manager',ARRAY['berts'])")
        async def authorize(request,store):
            return await manager_actor.resolve(request,store,lambda t:{'sub':t},lambda:self.pool,True)
        app=FastAPI(); app.include_router(handoff.create_router(lambda:self.pool,authorize))
        self.hclient=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers={'Authorization':'Bearer usr_manager'})
        self.hflag=patch.dict(os.environ,{'MANAGER_HANDOFF_NOTES_ENABLED':'true'}); self.hflag.start()
        self.clock=patch.object(handoff,'business_today',return_value=date(2026,10,25)); self.clock.start()

    async def asyncTearDown(self):
        await self.hclient.aclose(); self.hflag.stop(); self.clock.stop(); await PurchaseIntegrationTests.asyncTearDown(self)

    async def command(self,value,version=0,key=None,store='berts',status=False,actor='usr_manager'):
        return await self.hclient.post(f'/api/pg/operations/{store}/handoff-notes/'+('status' if status else 'commands'),
             content=json.dumps(value).encode('utf-8'),headers={'Content-Type':'application/json','If-Match':str(version),'Idempotency-Key':key or str(uuid4()),'Authorization':'Bearer '+actor})

    async def read(self,day='2026-10-25',track='bulk',store='berts'):
        return await self.hclient.get(f'/api/pg/operations/{store}/handoff-notes/days/{day}',params={'track':track})

    async def count(self):
        async with self.pool.acquire() as c:
            return [await c.fetchval(f'SELECT count(*) FROM operations.{t}') for t in handoff.TABLES[1:]]

    async def test_shared_draft_submit_correct_history_and_previous_are_stock_independent(self):
        async with self.pool.acquire() as c:
            before=await c.fetchval("SELECT row_to_json(x)::text FROM (SELECT array_agg(to_jsonb(s) ORDER BY store_id,item_code) a FROM public.store_items s) x")
        value=body(business_date='2026-10-23'); key=str(uuid4())
        result=await self.command(value,key=key); self.assertEqual(result.status_code,200,result.text)
        saved=result.json(); self.assertEqual(saved['current']['revision'],1)
        changed=value|{'action':'save_draft','summary':'TEST ONLY: owner edits shared draft'}
        result=await self.command(changed,1,actor='usr_owner'); self.assertEqual(result.status_code,200,result.text)
        result=await self.command(changed|{'action':'submit'},2); self.assertEqual(result.status_code,200,result.text)
        first=result.json()['current']['first_submitted_at']
        correction=changed|{'action':'correct','summary':'TEST ONLY corrected summary','correction_reason':'Measured discrepancy'}
        result=await self.command(correction,3,actor='usr_owner'); self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['current']['first_submitted_at'],first)
        replay=await self.command(value,key=key); self.assertTrue(replay.json()['replayed'])
        self.assertEqual(replay.json()['accepted']['revision'],1); self.assertEqual(replay.json()['current']['revision'],4)
        self.assertEqual((await self.command(body(business_date='2026-10-24',summary='Later unsubmitted draft'))).status_code,200)
        read=(await self.read()).json(); self.assertIsNone(read['current']); self.assertEqual(read['previous']['summary'],correction['summary'])
        self.assertIsNone((await self.read(track='daily')).json()['previous'])
        history=await self.hclient.get(f"/api/pg/operations/berts/handoff-notes/notes/{value['note_id']}/history")
        self.assertEqual([r['actor_id'] for r in history.json()['rows']],['usr_manager','usr_owner','usr_manager','usr_owner'])
        self.assertEqual([r['action'] for r in history.json()['rows']],['create_draft','save_draft','submit','correct'])
        async with self.pool.acquire() as c:
            after=await c.fetchval("SELECT row_to_json(x)::text FROM (SELECT array_agg(to_jsonb(s) ORDER BY store_id,item_code) a FROM public.store_items s) x")
            self.assertEqual(before,after); self.assertEqual(await c.fetchval('SELECT count(*) FROM purchasing.posting_batches'),0)

    async def test_before_after_commit_status_exact_retry_and_changed_key_conflicts(self):
        value=body(); key=str(uuid4()); before=await self.count()
        r=await self.command(value,key=key,status=True); self.assertEqual(r.json()['outcome'],'unconfirmed'); self.assertEqual(before,await self.count())
        r=await self.command(value,key=key); self.assertEqual(r.status_code,200,r.text)
        for _ in range(2):
            r=await self.command(value,key=key,status=True); self.assertEqual(r.json()['outcome'],'saved')
        r=await self.command(value,key=key); self.assertTrue(r.json()['replayed'])
        self.assertEqual(await self.count(),[1,1,1])
        r=await self.command(value|{'summary':'altered'},key=key); self.assertEqual(r.status_code,409)
        r=await self.command(value,key=key,status=True,actor='usr_owner'); self.assertEqual(r.json()['outcome'],'unconfirmed')

    async def test_parallel_creates_same_keys_and_stale_edits_never_overwrite(self):
        value=body(); key=str(uuid4())
        replies=await asyncio.gather(*(self.command(value,key=key) for _ in range(3)))
        self.assertEqual([r.status_code for r in replies],[200]*3); self.assertEqual(await self.count(),[1,1,1])
        r=await self.command(body()); self.assertEqual(r.status_code,409)
        changes=[value|{'action':'save_draft','summary':s} for s in ('Manager A','Manager B')]
        replies=await asyncio.gather(*(self.command(v,1) for v in changes))
        self.assertEqual(sorted(r.status_code for r in replies),[200,409]); self.assertEqual(await self.count(),[1,2,2])
        r=await self.command(value|{'action':'submit'},2); self.assertEqual(r.status_code,409)

    async def test_current_account_revocation_applies_to_reads_commands_and_saved_receipts(self):
        value=body(); key=str(uuid4()); self.assertEqual((await self.command(value,key=key)).status_code,200)
        for sql in ("UPDATE app_users SET role='staff' WHERE id='usr_manager'",
                    "UPDATE app_users SET role='manager',locations=ARRAY['rudds'] WHERE id='usr_manager'",
                    "DELETE FROM app_users WHERE id='usr_manager'"):
            async with self.pool.acquire() as c: await c.execute(sql)
            self.assertEqual((await self.read()).status_code,403)
            self.assertEqual((await self.command(value,key=key)).status_code,403)
            self.assertEqual((await self.command(value,key=key,status=True)).status_code,403)
        self.assertEqual(await self.count(),[1,1,1])

    async def test_feature_missing_timezone_inactive_store_future_date_and_foreign_scope_hold(self):
        value=body(); self.assertEqual((await self.command(value,store='rudds')).status_code,403)
        self.assertEqual((await self.command(value,store='comm',actor='usr_owner')).status_code,404)
        with patch.dict(os.environ,{'MANAGER_HANDOFF_NOTES_ENABLED':'false'}): self.assertEqual((await self.read()).status_code,503)
        async with self.pool.acquire() as c: await c.execute("UPDATE operations.store_settings SET timezone_name='invalid/timezone' WHERE store_id='berts'")
        self.assertEqual((await self.read()).status_code,503)
        async with self.pool.acquire() as c: await c.execute("DELETE FROM operations.store_settings WHERE store_id='berts'")
        self.assertEqual((await self.command(value)).status_code,503)
        async with self.pool.acquire() as c:
            await c.execute("INSERT INTO operations.store_settings VALUES ('berts','America/New_York',2)")
        self.assertEqual((await self.command(value)).status_code,409)
        self.assertEqual((await self.command(value|{'settings_revision':2,'business_date':'9999-12-31'})).status_code,422)
        async with self.pool.acquire() as c: await c.execute("UPDATE stores SET active=false WHERE id='berts'")
        self.assertEqual((await self.read()).status_code,404); self.assertEqual(await self.count(),[0,0,0])

    async def test_missing_storage_disabled_guards_and_malformed_requests_hold_without_writes(self):
        for change in ({'summary':'\ud800'},{'business_date':0},{'settings_revision':True},{'actor_id':'forged'},{'correction_reason':'unexpected'}):
            r=await self.command(body(**change)); self.assertEqual(r.status_code,422,r.text)
            self.assertNotIn('forged',r.text)
        r=await self.hclient.post('/api/pg/operations/berts/handoff-notes/commands',json=body())
        self.assertEqual(r.status_code,422)
        async with self.pool.acquire() as c: await c.execute('ALTER TABLE operations.handoff_notes DISABLE TRIGGER handoff_header_guard')
        self.assertEqual((await self.read()).status_code,503); self.assertEqual((await self.command(body())).status_code,503)
        async with self.pool.acquire() as c:
            await c.execute('ALTER TABLE operations.handoff_notes ENABLE TRIGGER handoff_header_guard')
            await c.execute('DROP TABLE operations.handoff_command_receipts')
        self.assertEqual((await self.read()).status_code,503)

    async def test_immutable_history_context_and_late_failure_rollback_all_three_relations(self):
        value=body(); self.assertEqual((await self.command(value)).status_code,200)
        async with self.pool.acquire() as c:
            for sql in ("DELETE FROM operations.handoff_notes", "DELETE FROM operations.handoff_note_revisions",
                        "UPDATE operations.handoff_note_revisions SET summary='rewrite'", "DELETE FROM operations.handoff_command_receipts",
                        "UPDATE operations.handoff_notes SET business_date=business_date-1,revision=revision+1"):
                with self.assertRaises(asyncpg.PostgresError): await c.execute(sql)
            await c.execute("CREATE FUNCTION public.test_receipt_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'fictional late failure'; END $$")
            await c.execute("CREATE TRIGGER test_fail BEFORE INSERT ON operations.handoff_command_receipts FOR EACH ROW EXECUTE FUNCTION public.test_receipt_failure()")
        r=await self.command(value|{'action':'save_draft','summary':'Must roll back'},1)
        self.assertEqual(r.status_code,503); self.assertNotIn('fictional late',r.text)
        self.assertEqual(await self.count(),[1,1,1]); self.assertEqual((await self.read()).json()['current']['revision'],1)

    async def test_history_pages_and_foreign_note_ids_never_return_other_store(self):
        value=body(); self.assertEqual((await self.command(value)).status_code,200)
        # Pagination fixture uses the real immutable guards, without 51 redundant HTTP edits.
        async with self.pool.acquire() as c, c.transaction():
            for revision in range(2,53):
                await c.execute('UPDATE operations.handoff_notes SET revision=$2,updated_at=clock_timestamp() WHERE id=$1',UUID(value['note_id']),revision)
                await c.execute("""INSERT INTO operations.handoff_note_revisions(store_id,note_id,revision,action,actor_id,status,summary,next_shift_note,reported_readiness)
                    SELECT store_id,id,revision,'save_draft','usr_manager','draft','TEST ONLY historical revision '||revision,'','not_assessed'
                    FROM operations.handoff_notes WHERE id=$1""",UUID(value['note_id']))
        path=f"/api/pg/operations/berts/handoff-notes/notes/{value['note_id']}/history"
        page=(await self.hclient.get(path)).json(); self.assertEqual(len(page['rows']),50); self.assertEqual(page['next_after'],50)
        tail=(await self.hclient.get(path,params={'after':50})).json(); self.assertEqual([r['revision'] for r in tail['rows']],[51,52]); self.assertIsNone(tail['next_after'])
        foreign=await self.hclient.get(path.replace('/berts/','/rudds/'),headers={'Authorization':'Bearer usr_owner'})
        self.assertEqual(foreign.status_code,404); self.assertNotIn('summary',foreign.text)
        self.assertEqual((await self.hclient.get(path,params={'after':2147483648})).status_code,422)

    async def test_disposable_dump_restore_preserves_context_history_and_exact_replay(self):
        value=body(); key=str(uuid4()); first=await self.command(value,key=key); self.assertEqual(first.status_code,200,first.text)
        self.assertEqual((await self.command(value|{'action':'submit'},1)).status_code,200)
        correction=value|{'action':'correct','summary':'TEST ONLY restored correction','correction_reason':'Later measurement'}
        self.assertEqual((await self.command(correction,2,actor='usr_owner')).status_code,200)
        target='native_purchase_test_restore_'+uuid4().hex
        base=os.environ['NATIVE_PURCHASE_TEST_DSN'].rsplit('/',1)[0]
        dump=Path(os.environ['NATIVE_BACKUP_PG_DUMP']);restore=dump.with_name('pg_restore'+dump.suffix)
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        await self.admin.execute(f'CREATE DATABASE {target}')
        try:
            with tempfile.TemporaryDirectory(prefix='fictional-handoff-') as directory:
                artifact=Path(directory)/'fictional.dump'
                for argv in ([str(dump),'-Fc','--no-owner','--no-acl','-f',str(artifact),base+'/'+self.db],
                             [str(restore),'--exit-on-error','--no-owner','--no-acl','--dbname='+base+'/'+target,str(artifact)]):
                    result=subprocess.run(argv,capture_output=True,text=True,timeout=60,creationflags=flags)
                    self.assertEqual(result.returncode,0,result.stderr)
                restored=await asyncpg.create_pool(base+'/'+target,min_size=1,max_size=1)
                try:
                    replay=await handoff.execute(restored,'berts','usr_manager',handoff.Command(**value),UUID(key),0)
                    self.assertTrue(replay['replayed']);self.assertEqual(replay['accepted']['revision'],1)
                    self.assertEqual(replay['current']['revision'],3);self.assertEqual(replay['current']['summary'],correction['summary'])
                    async with restored.acquire() as c:
                        self.assertEqual(await c.fetchval('SELECT count(*) FROM operations.handoff_note_revisions'),3)
                        self.assertEqual(await c.fetchval('SELECT count(*) FROM operations.handoff_command_receipts'),3)
                finally: await restored.close()
        finally: await self.admin.execute(f'DROP DATABASE {target}')

    async def test_disposable_role_matrix_and_catalog_snapshot(self):
        suffix=uuid4().hex[:10]; runtime='handoff_runtime_'+suffix; auxiliary='handoff_accounts_'+suffix; browser='handoff_browser_'+suffix
        roles=[runtime,auxiliary,browser]
        async with self.pool.acquire() as c:
            try:
                for role in roles: await c.execute(f'CREATE ROLE {role} NOLOGIN NOSUPERUSER NOBYPASSRLS')
                await c.execute(f'GRANT USAGE ON SCHEMA operations TO {runtime}')
                await c.execute(f'GRANT USAGE ON SCHEMA public TO {runtime},{auxiliary}')
                await c.execute(f'GRANT SELECT(id,active) ON public.stores TO {runtime}')
                await c.execute(f'CREATE POLICY fictional_store_read ON public.stores FOR SELECT TO {runtime} USING(true)')
                await c.execute(f'GRANT SELECT(id,role,locations) ON public.app_users TO {auxiliary}')
                await c.execute(f'CREATE POLICY fictional_accounts ON public.app_users TO {auxiliary} USING(true)')
                for table,verbs in {'store_settings':'SELECT','handoff_notes':'SELECT,INSERT,UPDATE','handoff_note_revisions':'SELECT,INSERT','handoff_command_receipts':'SELECT,INSERT'}.items():
                    await c.execute(f'GRANT {verbs} ON operations.{table} TO {runtime}')
                    await c.execute(f'CREATE POLICY fictional_backend ON operations.{table} TO {runtime} USING(true) WITH CHECK(true)')
                async def initialize(connection): await connection.execute(f'SET ROLE {runtime}')
                runtime_pool=await asyncpg.create_pool(os.environ['NATIVE_PURCHASE_TEST_DSN'].rsplit('/',1)[0]+'/'+self.db,min_size=1,max_size=1,init=initialize)
                try:
                    self.assertEqual(await runtime_pool.fetchval('SELECT current_user'),runtime)
                    value=handoff.Command(**body()); key=uuid4()
                    accepted=await handoff.execute(runtime_pool,'berts','usr_manager',value,key,0)
                    self.assertEqual(accepted['current']['revision'],1)
                    self.assertEqual(await runtime_pool.fetchval('SELECT current_user'),runtime)
                    self.assertEqual((await handoff.execute(runtime_pool,'berts','usr_manager',value,key,0))['replayed'],True)
                finally: await runtime_pool.close()
                for role in roles:
                    async with c.transaction():
                        await c.execute(f'SET LOCAL ROLE {role}')
                        if role==runtime:
                            self.assertEqual(await c.fetchval('SELECT count(*) FROM operations.store_settings'),2)
                            with self.assertRaises(asyncpg.InsufficientPrivilegeError):
                                async with c.transaction(): await c.execute('DELETE FROM operations.handoff_notes')
                        else:
                            with self.assertRaises(asyncpg.InsufficientPrivilegeError):
                                async with c.transaction(): await c.fetch('SELECT * FROM operations.handoff_notes')
                            if role==auxiliary:
                                self.assertEqual(await c.fetchval("SELECT id FROM public.app_users WHERE id='usr_manager'"),'usr_manager')
                                with self.assertRaises(asyncpg.InsufficientPrivilegeError):
                                    async with c.transaction(): await c.fetch('SELECT password_hash FROM public.app_users')
                    for table in handoff.TABLES:
                        self.assertFalse(await c.fetchval('SELECT has_table_privilege($1,$2,$3)',role,'operations.'+table,'DELETE'))
                self.assertTrue(await handoff.installed(c))
                self.assertFalse(await c.fetchval('SELECT has_table_privilege($1,$2,$3)',runtime,'operations.store_settings','UPDATE'))
                self.assertFalse(await c.fetchval("SELECT bool_or(prosecdef) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='operations'"))
            finally:
                await c.execute('DROP POLICY IF EXISTS fictional_store_read ON public.stores')
                await c.execute('DROP POLICY IF EXISTS fictional_accounts ON public.app_users')
                for table in handoff.TABLES: await c.execute(f'DROP POLICY IF EXISTS fictional_backend ON operations.{table}')
                for role in roles:
                    await c.execute(f'DROP OWNED BY {role}'); await c.execute(f'DROP ROLE {role}')
            async with c.transaction(readonly=True):
                await c.execute('SET LOCAL search_path=pg_catalog')
                actual=await runtime_permissions.catalog_contracts(c,schemas=('operations',))
            manifest=json.loads((ROOT/'supabase/manager_handoff.manifest.json').read_text())
            self.assertEqual(actual,manifest['catalog'])
            self.assertEqual(hashlib.sha256((ROOT/'migrations/20261025_manager_handoff_notes.sql').read_bytes()).hexdigest(),manifest['migrationSha256'])
            self.assertEqual(hashlib.sha256((ROOT/'supabase/manager_handoff.schema.sql').read_bytes()).hexdigest(),manifest['snapshotSha256'])
