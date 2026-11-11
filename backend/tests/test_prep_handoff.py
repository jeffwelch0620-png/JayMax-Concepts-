"""AM-to-PM manager prep handoff (Jeff 2026-11-11) with invented managers and prep on disposable PostgreSQL."""
import asyncio, json, os, unittest
from datetime import date
from unittest.mock import patch
from uuid import uuid4

import asyncpg, httpx
from fastapi import FastAPI
from pydantic import ValidationError

import manager_actor, manager_handoff, prep_handoff
import test_staff_prep_tasks as staff

ROOT = staff.fixtures.fixtures.fixtures.recovery.counts.native.ROOT
DAY = '2026-10-08'


def body(**over):
    b = dict(action='send', handoff_id=str(uuid4()), business_date=DAY, prep_track='daily', task_id=str(uuid4()),
             prep_hash='a' * 64, recipient_id='usr_pm', remaining_base_quantity='2', ready_by='16:30', note='Invented note')
    return {**b, **over}


class PrepHandoffValidationTests(unittest.TestCase):
    def test_each_action_takes_only_its_fields(self):
        prep_handoff.Command(**body())
        reasoned = dict(recipient_id='', remaining_base_quantity=None, ready_by='', note='')
        prep_handoff.Command(**body(action='accept', **reasoned))
        prep_handoff.Command(**body(action='take_over', reason='PM called out', **reasoned))
        prep_handoff.Command(**body(action='correct', reason='Two tubs, not three'))
        for bad in (body(ready_by='4pm'), body(remaining_base_quantity='-1'), body(prep_track='lunch'), body(prep_hash='x'),
                    body(action='accept'), body(action='take_over', **reasoned), body(action='withdraw', **reasoned),
                    body(action='accept', reason='not needed', **reasoned), body(action='correct'), body(recipient_id='bad id'),
                    body(business_date='2026-13-01'), body(extra='field'), body(note='\x00')):
            with self.assertRaises(ValidationError): prep_handoff.Command(**bad)

    def test_amounts_have_one_spelling(self):
        self.assertEqual([prep_handoff.qty(v) for v in ('256.000000000000', '256.00', '0E-12', '1.50', '1E+2')], ['256', '256', '0', '1.5', '100'])

    def test_unresolved_draft_task_reads_as_not_carryable(self):
        # A par item still waiting for its count has no planned amount (prep_day_tasks); the day read must not fail.
        row = dict(id=uuid4(), version_id=uuid4(), included=True, planned_base_quantity=None, task_snapshot={'name': 'Invented item', 'base_unit': 'lb'},
                   list_id=uuid4(), prep_date=date(2026, 10, 8), track='daily', superseded=False, phase_version=None, phase_action=None, phase_event=None,
                   progress={'planned_base_quantity': None, 'effective_base_quantity': '0', 'reviewed_base_quantity': '0',
                             'status': 'open', 'closed': False, 'needs_review': False},
                   assignment_revision=None, staff_member_id=None, staff_name=None)

        class Conn:
            async def fetchrow(self, *_): return row
        facts = asyncio.run(prep_handoff.task_facts(Conn(), 'berts', row['id']))
        self.assertEqual((facts['planned_base_quantity'], facts['remaining_base_quantity'], facts['available']), (None, None, False))
        self.assertRegex(facts['prep_hash'], '^[a-f0-9]{64}$')

    def test_manager_accounts_are_read_through_the_accounts_connection(self):
        class Accounts:
            def __init__(self, fail=False): self.fail, self.queries = fail, []
            async def fetchrow(self, sql, *args):
                if self.fail: raise RuntimeError('restricted login')
                self.queries.append(sql); return {'id': 'usr_am', 'email': 'am@example.invalid', 'role': 'manager', 'position': 'KM'}
            async def fetch(self, sql, *args):
                if self.fail: raise RuntimeError('restricted login')
                self.queries.append(sql); return []
        ok = Accounts()
        self.assertEqual(asyncio.run(prep_handoff.account(lambda: ok, 'usr_am'))['position'], 'KM')
        self.assertEqual(asyncio.run(prep_handoff.managers(lambda: ok, 'papa')), [])
        self.assertTrue(all('public.app_users' in q for q in ok.queries))
        for call in (lambda a: prep_handoff.account(a, 'usr_am'), lambda a: prep_handoff.managers(a, 'berts')):
            with self.assertRaises(prep_handoff.HTTPException) as held:
                asyncio.run(call(lambda: Accounts(fail=True)))
            self.assertEqual(held.exception.status_code, 503); self.assertNotIn('restricted', held.exception.detail)

    def test_digest_is_stable_and_order_free(self):
        self.assertEqual(prep_handoff.digest({'a': 1, 'b': [1, 2]}), prep_handoff.digest({'b': [1, 2], 'a': 1}))
        self.assertNotEqual(prep_handoff.digest({'a': 1}), prep_handoff.digest({'a': 2}))

    def test_migration_is_append_only_and_seeds_nothing(self):
        sql = (ROOT / 'migrations/20261111_prep_task_handoffs.sql').read_text()
        self.assertNotIn('INSERT INTO', sql.upper())
        for guard in ('prep_handoff_guard', 'prep_handoff_revision_guard', 'prep_handoff_receipt_guard', 'no_truncate'):
            self.assertIn(guard, sql)


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class PrepHandoffTests(staff.StaffTaskTests):
    for _name in [n for n in dir(staff.StaffTaskTests) if n.startswith('test_')]:
        locals()[_name] = None
    del _name

    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with self.pool.acquire() as c:
            await c.execute((ROOT / 'migrations/20261025_manager_handoff_notes.sql').read_text())
            await c.execute((ROOT / 'migrations/20261111_prep_task_handoffs.sql').read_text())
            await c.execute("INSERT INTO operations.store_settings VALUES ('berts','America/New_York',1),('rudds','America/New_York',1)")
            await c.execute('ALTER TABLE public.app_users ADD COLUMN IF NOT EXISTS position text')
            await c.execute("""INSERT INTO public.app_users(id,email,password_hash,role,locations,position) VALUES
                ('usr_am','am@example.invalid','not-a-password','manager',ARRAY['berts'],'KM'),
                ('usr_pm','pm@example.invalid','not-a-password','manager',ARRAY['berts'],'SL-BOH'),
                ('usr_backup','backup@example.invalid','not-a-password','manager',ARRAY['berts'],'KM'),
                ('usr_gm','gm@example.invalid','not-a-password','manager',ARRAY['berts'],'GM'),
                ('usr_rudds','rudds@example.invalid','not-a-password','manager',ARRAY['rudds'],'KM')""")

        async def authorize(request, store):
            return await manager_actor.resolve(request, store, lambda t: {'sub': t}, lambda: self.pool, True)
        app = FastAPI(); app.include_router(prep_handoff.create_router(lambda: self.pool, authorize, lambda: self.pool))
        self.h = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')
        self.addAsyncCleanup(self.h.aclose)
        for p in (patch.dict(os.environ, {'MANAGER_HANDOFF_NOTES_ENABLED': 'true'}),
                  patch.object(manager_handoff, 'business_today', return_value=date(2026, 10, 8))):
            p.start(); self.addCleanup(p.stop)
        self.draft, self.task = await self.start()

    async def day(self, actor='usr_am', store='berts', track='daily'):
        r = await self.h.get(f'/api/pg/operations/{store}/prep-handoffs/days/{DAY}', params={'track': track}, headers={'Authorization': 'Bearer ' + actor})
        return r

    async def facts(self, actor='usr_am'):
        r = await self.day(actor); self.assertEqual(r.status_code, 200, r.text)
        return next(t for t in r.json()['tasks'] if t['task_id'] == str(self.task['id']))

    async def cmd(self, payload, actor='usr_am', version=0, key=None, store='berts'):
        return await self.h.post(f'/api/pg/operations/{store}/prep-handoffs/commands', content=json.dumps(payload),
                                 headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + actor,
                                          'If-Match': str(version), 'Idempotency-Key': key or str(uuid4())})

    async def send(self, **over):
        f = await self.facts()
        r = await self.cmd(body(task_id=f['task_id'], prep_hash=f['prep_hash'], **over))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()['handoff']

    def act(self, h, action, prep_hash, **over):
        b = dict(action=action, handoff_id=h['id'], business_date=DAY, prep_track='daily', task_id=h['task_id'], prep_hash=prep_hash)
        return {**b, **over}

    async def counts(self):
        async with self.pool.acquire() as c:
            return [await c.fetchval(f'SELECT count(*) FROM prep_inventory.{t}') for t in
                    ('batch_events', 'batch_movements', 'execution_events', 'task_assignments', 'day_tasks')]

    async def test_send_accept_then_changed_prep_needs_acceptance_again_and_writes_no_prep(self):
        before = await self.counts()
        h = await self.send()
        self.assertEqual((h['status'], h['effective_status'], h['recipient'], h['ready_by']), ('waiting', 'waiting', 'pm@example.invalid', '16:30'))
        self.assertIsNone(h['current_prep']['assignee'])
        f = await self.facts('usr_pm')
        accepted = await self.cmd(self.act(h, 'accept', f['prep_hash']), 'usr_pm', 1)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()['handoff']['effective_status'], 'accepted')
        self.assertEqual(await self.counts(), before)  # responsibility only

        # The morning manager assigns a cook after acceptance: the handoff needs acceptance again.
        self.assertEqual((await self.assign(self.assignment_body(self.task))).status_code, 200)
        state = (await self.day('usr_pm')).json()['handoffs'][0]
        self.assertEqual((state['status'], state['effective_status'], state['prep_changed']), ('accepted', 'needs_acceptance', True))
        self.assertEqual(state['current_prep']['assignee']['name'], 'Invented cook A')
        stale = await self.cmd(self.act(h, 'accept', f['prep_hash']), 'usr_pm', 2)
        self.assertEqual(stale.status_code, 409, stale.text)
        fresh = await self.facts('usr_pm')
        again = await self.cmd(self.act(h, 'accept', fresh['prep_hash']), 'usr_pm', 2)
        self.assertEqual(again.json()['handoff']['effective_status'], 'accepted')
        twice = await self.cmd(self.act(h, 'accept', fresh['prep_hash']), 'usr_pm', 3)
        self.assertEqual(twice.status_code, 409)

    async def test_backup_and_same_person_take_over_need_a_reason_and_are_recorded(self):
        h = await self.send()
        f = await self.facts()
        self.assertEqual((await self.cmd(self.act(h, 'take_over', f['prep_hash'], reason='PM is covering a call-out'), 'usr_pm', 1)).status_code, 409)
        backup = await self.cmd(self.act(h, 'take_over', f['prep_hash'], reason='Invented: PM called out'), 'usr_backup', 1)
        self.assertEqual(backup.status_code, 200, backup.text)
        self.assertEqual((backup.json()['handoff']['recipient'], backup.json()['handoff']['effective_status']), ('backup@example.invalid', 'accepted'))
        # Jeff 2026-11-11: the morning manager may take over their own handoff with a reason.
        mine = await self.cmd(self.act(h, 'take_over', f['prep_hash'], reason='Invented: covering the evening myself'), 'usr_am', 2)
        self.assertEqual(mine.json()['handoff']['recipient'], 'am@example.invalid')
        history = await self.h.get(f"/api/pg/operations/berts/prep-handoffs/handoffs/{h['id']}/history", headers={'Authorization': 'Bearer usr_gm'})
        self.assertEqual([(r['action'], r['actor'], r['reason']) for r in history.json()['rows']], [
            ('send', 'am@example.invalid', ''), ('take_over', 'backup@example.invalid', 'Invented: PM called out'),
            ('take_over', 'am@example.invalid', 'Invented: covering the evening myself')])

    async def test_correction_returns_to_waiting_and_only_sender_or_gm_corrects_or_withdraws(self):
        h = await self.send()
        f = await self.facts()
        self.assertEqual((await self.cmd(self.act(h, 'accept', f['prep_hash']), 'usr_pm', 1)).status_code, 200)
        fix = dict(recipient_id='usr_pm', remaining_base_quantity='1.5', ready_by='17:00', note='Invented: one tub done', reason='Invented: less left')
        self.assertEqual((await self.cmd(self.act(h, 'correct', f['prep_hash'], **fix), 'usr_backup', 2)).status_code, 403)
        corrected = await self.cmd(self.act(h, 'correct', f['prep_hash'], **fix), 'usr_am', 2)
        self.assertEqual(corrected.status_code, 200, corrected.text)
        self.assertEqual((corrected.json()['handoff']['status'], corrected.json()['handoff']['remaining_base_quantity'], corrected.json()['handoff']['ready_by']),
                         ('waiting', '1.5', '17:00'))
        self.assertEqual((await self.cmd(self.act(h, 'withdraw', f['prep_hash'], reason='Invented'), 'usr_pm', 3)).status_code, 403)
        withdrawn = await self.cmd(self.act(h, 'withdraw', f['prep_hash'], reason='Invented: finished at lunch'), 'usr_gm', 3)
        self.assertEqual(withdrawn.json()['handoff']['effective_status'], 'withdrawn')
        self.assertEqual((await self.cmd(self.act(h, 'accept', f['prep_hash']), 'usr_pm', 4)).status_code, 409)
        # A withdrawn handoff stays as history and the task can be carried again.
        again = await self.send()
        self.assertNotEqual(again['id'], h['id'])
        self.assertEqual(len((await self.day()).json()['handoffs']), 2)

    async def test_refusals_store_role_recipient_duplicate_stale_and_replay(self):
        f = await self.facts()
        ok = body(task_id=f['task_id'], prep_hash=f['prep_hash'])
        self.assertEqual((await self.cmd(ok, 'usr_rudds')).status_code, 403)
        self.assertEqual((await self.day('usr_rudds')).status_code, 403)
        self.assertEqual((await self.day(track='salad', store='rudds', actor='usr_rudds')).status_code, 422)
        self.assertEqual((await self.cmd({**ok, 'recipient_id': 'usr_rudds'})).status_code, 422)
        self.assertEqual((await self.cmd({**ok, 'recipient_id': 'usr_am'})).status_code, 422)
        self.assertEqual((await self.cmd({**ok, 'prep_hash': 'b' * 64})).status_code, 409)
        self.assertEqual((await self.cmd({**ok, 'business_date': '2026-10-09'})).status_code, 422)  # future
        key = str(uuid4())
        first = await self.cmd(ok, key=key)
        self.assertEqual(first.status_code, 200, first.text)
        replay = await self.cmd(ok, key=key)
        self.assertEqual((replay.status_code, replay.json()['replayed']), (200, True))
        self.assertEqual((await self.cmd({**ok, 'note': 'Different'}, key=key)).status_code, 409)
        self.assertEqual((await self.cmd({**ok, 'handoff_id': str(uuid4())})).status_code, 409)  # one open per task
        self.assertEqual((await self.cmd(self.act(first.json()['handoff'], 'accept', f['prep_hash']), 'usr_pm', 0)).status_code, 409)  # old revision

    async def test_commands_hold_the_prep_writers_store_lock_through_the_write(self):
        # The prep writers lock public.store_state; a handoff command takes the same lock before reading facts.
        h = await self.send()
        f = await self.facts('usr_pm')
        seen = []
        lock, read = prep_handoff.lock_store, prep_handoff.task_facts
        async def locked(conn, store):
            await lock(conn, store); seen.append(('lock', store))
        async def facts(conn, store, task):
            seen.append(('facts', store)); return await read(conn, store, task)
        with patch.object(prep_handoff, 'lock_store', locked), patch.object(prep_handoff, 'task_facts', facts):
            self.assertEqual((await self.cmd(self.act(h, 'accept', f['prep_hash']), 'usr_pm', 1)).status_code, 200)
        self.assertEqual(seen[:2], [('lock', 'berts'), ('facts', 'berts')])

    async def test_reopen_blocks_take_over_and_a_re_release_still_needs_acceptance_again(self):
        h = await self.send()
        f = await self.facts('usr_pm')
        self.assertEqual((await self.cmd(self.act(h, 'accept', f['prep_hash']), 'usr_pm', 1)).status_code, 200)
        reopened = await self.write_execution(self.command(self.draft, "reopen"), version=1)
        self.assertEqual(reopened.status_code, 200, reopened.text)
        closed = await self.facts('usr_backup')
        self.assertFalse(closed['available'])
        refused = await self.cmd(self.act(h, 'take_over', closed['prep_hash'], reason='Invented: covering'), 'usr_backup', 2)
        self.assertEqual(refused.status_code, 409, refused.text)
        # Releasing the same unchanged draft again does not bring the earlier acceptance back.
        released = await self.write_execution(self.command(self.draft), version=2)
        self.assertEqual(released.status_code, 200, released.text)
        again = await self.facts('usr_pm')
        self.assertTrue(again['available']); self.assertNotEqual(again['prep_hash'], f['prep_hash'])
        state = (await self.day('usr_pm')).json()['handoffs'][0]
        self.assertEqual(state['effective_status'], 'needs_acceptance')
        self.assertEqual((await self.cmd(self.act(h, 'accept', f['prep_hash']), 'usr_pm', 2)).status_code, 409)
        self.assertEqual((await self.cmd(self.act(h, 'accept', again['prep_hash']), 'usr_pm', 2)).status_code, 200)

    async def test_one_small_shared_pool_serves_concurrent_reads_and_commands(self):
        # Without a separate accounts database both factories are the same small pool; account reads happen
        # before the inventory connection is taken, so concurrent requests never wait on each other.
        dsn = os.environ['NATIVE_PURCHASE_TEST_DSN'].rsplit('/', 1)[0] + '/' + self.db
        small = await asyncpg.create_pool(dsn, min_size=1, max_size=1)
        self.addAsyncCleanup(small.close)

        async def authorize(request, store):
            return await manager_actor.resolve(request, store, lambda t: {'sub': t}, lambda: small, True)
        app = FastAPI(); app.include_router(prep_handoff.create_router(lambda: small, authorize, lambda: small))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            def get(actor):
                return client.get(f'/api/pg/operations/berts/prep-handoffs/days/{DAY}', params={'track': 'daily'}, headers={'Authorization': 'Bearer ' + actor})
            reads = await asyncio.wait_for(asyncio.gather(*(get(a) for a in ('usr_am', 'usr_pm', 'usr_backup'))), 30)
            self.assertEqual([r.status_code for r in reads], [200, 200, 200])
            f = next(t for t in reads[0].json()['tasks'] if t['task_id'] == str(self.task['id']))
            sent = await asyncio.wait_for(client.post('/api/pg/operations/berts/prep-handoffs/commands',
                content=json.dumps(body(task_id=f['task_id'], prep_hash=f['prep_hash'])),
                headers={'Content-Type': 'application/json', 'Authorization': 'Bearer usr_am', 'If-Match': '0', 'Idempotency-Key': str(uuid4())}), 30)
            self.assertEqual(sent.status_code, 200, sent.text)

    async def test_history_cannot_be_rewritten(self):
        h = await self.send()
        async with self.pool.acquire() as c:
            for sql in ("UPDATE operations.prep_handoff_revisions SET note='x'", 'DELETE FROM operations.prep_handoff_revisions',
                        'DELETE FROM operations.prep_handoffs', 'DELETE FROM operations.prep_handoff_receipts',
                        'TRUNCATE operations.prep_handoff_revisions CASCADE',
                        f"UPDATE operations.prep_handoffs SET sender_id='usr_pm' WHERE id='{h['id']}'"):
                with self.assertRaises(asyncpg.PostgresError, msg=sql):
                    async with c.transaction(): await c.execute(sql)
