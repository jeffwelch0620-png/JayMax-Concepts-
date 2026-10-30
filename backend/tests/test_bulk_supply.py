"""M3 Bulk supply: request (par minus count), the maker's run, sign-off, acceptance, shortfall."""
import os
import unittest
from datetime import date, time
from decimal import Decimal as D
from unittest.mock import patch
from uuid import UUID, uuid4

import asyncpg
from pydantic import ValidationError

import bulk_supply as bulk
import prep_day_tasks as tasks


class BulkModelTests(unittest.TestCase):
    def test_scheduled_uses_the_count_and_spot_lists_items(self):
        ident = uuid4()
        bulk.RequestIn(run_date='2026-10-08', kind='scheduled', day_group='weekday', count_event_id=ident, note='Sunday count')
        for bad in (dict(kind='scheduled', day_group='weekday', note='No count'),
                    dict(kind='scheduled', day_group='weekday', count_event_id=ident, note='x', lines=[dict(product_id=ident, quantity='1', reason='r')]),
                    dict(kind='spot', note='Nothing listed'),
                    dict(kind='spot', note='Twice', lines=[dict(product_id=ident, quantity='1', reason='r')] * 2),
                    dict(kind='spot', note='Zero', lines=[dict(product_id=ident, quantity='0', reason='r')])):
            with self.assertRaises(ValidationError): bulk.RequestIn(run_date='2026-10-08', **bad)

    def test_sign_off_steps(self):
        line = dict(ordinal=1, base_quantity='3', packaging='2 x 4 qt deli')
        bulk.StepIn(action='fulfill', handoff='pickup', lines=[line], note='Made Monday')
        for bad in (dict(action='fulfill', lines=[line]),
                    dict(action='accept', lines=[line]),
                    dict(action='cancel', lines=[line]),
                    dict(action='accept', lines=[]),
                    dict(action='fulfill', handoff='delivery', lines=[line, line]),
                    dict(action='accept', lines=[dict(ordinal=1, base_quantity='-1')]),
                    dict(action='accept', lines=[dict(ordinal=1, base_quantity='1', held_base_quantity='1')])):
            with self.assertRaises(ValidationError): bulk.StepIn(note='x', **bad)

    def test_a_bulk_run_adds_other_stores_requests_before_rounding(self):
        # Rudd's own need 3, Bert's asked 18: 21 rounds up to one 48-unit batch.
        self.assertEqual(tasks.batch_plan(D(5), D(2), D(0), D(48), D(18)), {'need': D(21), 'batches': D(1), 'planned_base': D(48)})
        self.assertEqual(tasks.batch_plan(D(5), D(9), D(0), D(10), D(12))['batches'], D(2))

    def test_spot_prep_pays_down_a_shortfall_and_the_next_run_recounts_it(self):
        def req(i, run, short, accepted='5', kind='scheduled', held='0', asked=None):
            asked = asked or str(D(short) + D(accepted) + D(held))
            return {'id': i, 'run_date': run, 'created_at': run, 'store_id': 'berts', 'status': 'accepted', 'kind': kind,
                    'lines': [{'product_id': 'p', 'name': 'Chili', 'base_unit': 'oz', 'requested_base_quantity': asked, 'shortfall_base_quantity': short,
                               'accepted_base_quantity': accepted, 'held_base_quantity': held}]}
        owed = lambda *rs: [(s['request_id'], D(s['shortfall_base_quantity'])) for s in bulk.open_shortfalls(list(rs))]
        self.assertEqual(owed(req('a', '2026-10-05', '10')), [('a', D(10))])
        # A 3 oz spot delivery (2 sent + 1 held) leaves 7 oz still owed; a second spot of 7 clears it.
        self.assertEqual(owed(req('a', '2026-10-05', '10'), req('s', '2026-10-06', '0', accepted='2', kind='spot', held='1')), [('a', D(7))])
        self.assertEqual(owed(req('a', '2026-10-05', '10'), req('s', '2026-10-06', '0', accepted='3', kind='spot'), req('t', '2026-10-07', '0', accepted='7', kind='spot')), [])
        # A make-up spot request of 10 with only 3 delivered still leaves 7 owed in total, not 7 twice.
        self.assertEqual(owed(req('a', '2026-10-05', '10'), req('s', '2026-10-06', '7', accepted='3', kind='spot')), [('a', D(7))])
        self.assertEqual(owed(req('a', '2026-10-05', '10'), req('s', '2026-10-06', '7', accepted='3', kind='spot'), req('t', '2026-10-07', '0', accepted='7', kind='spot')), [])
        # Asking for more than was owed adds only the extra: owed 2, asked 5, got 1 -> 4 owed.
        self.assertEqual(sum(D(s['shortfall_base_quantity']) for s in bulk.open_shortfalls([req('a', '2026-10-05', '2'), req('s', '2026-10-06', '4', accepted='1', kind='spot')])), D(4))
        # A spot opened before the scheduled request but accepted after it still pays it down.
        early_spot = req('s', '2026-10-08', '0', accepted='10', kind='spot') | {'created_at': '2026-10-08T08:00', 'events': [{'action': 'accept', 'created_at': '2026-10-08T16:00'}]}
        run = req('b', '2026-10-08', '10') | {'created_at': '2026-10-08T09:00', 'events': [{'action': 'accept', 'created_at': '2026-10-08T12:00'}]}
        self.assertEqual(owed(early_spot, run), [])
        # Monday's run signed off late (after Thursday's) cannot bring back Monday's shortage.
        thursday = req('t', '2026-10-08', '0') | {'events': [{'action': 'accept', 'created_at': '2026-10-08T12:00'}]}
        monday = req('m', '2026-10-05', '10') | {'events': [{'action': 'accept', 'created_at': '2026-10-08T16:00'}]}
        self.assertEqual(owed(thursday, monday), [])
        # The next scheduled run is par minus a fresh count, so it replaces what was owed with its own result.
        self.assertEqual(owed(req('a', '2026-10-05', '10'), req('b', '2026-10-08', '2', accepted='0')), [('b', D(2))])
        self.assertEqual(owed(req('a', '2026-10-05', '10'), req('b', '2026-10-08', '0')), [])


import test_prep_day_tasks as day

MIGRATION = 'migrations/20261030_bulk_supply.sql'
RUN = '2026-10-08'


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class BulkSupplyDatabaseTests(day.PrepDayTaskTests):
    # Reuse the dated-draft fixture without re-running its own tests here.
    for _name in [n for n in dir(day.PrepDayTaskTests) if n.startswith('test_')]:
        locals()[_name] = None
    del _name

    async def asyncSetUp(self):
        await super().asyncSetUp()
        # The fixture's prepared item lives at Bert's, so here Bert's makes Rudd's Bulk.
        makers = patch.dict(bulk.MAKERS, {'rudds': 'berts'}, clear=True); makers.start(); self.addCleanup(makers.stop)
        async with self.pool.acquire() as c:
            await c.execute((day.recovery.counts.native.ROOT / MIGRATION).read_text(encoding='utf-8'))
        r = await self.edit(self.payload(track='bulk', weekday_par='5', weekend_par='5'), version=1); self.assertEqual(r.status_code, 200, r.text)
        self.maker_plan = r.json()['plan']
        self.requester = await self.copy_to_rudds(par='30')

    async def copy_to_rudds(self, par):
        """Rudd's own copy of the same prepared item, with a Bulk par, written directly."""
        ids = {k: uuid4() for k in ('product', 'version', 'profile', 'recipe', 'plan')}
        async with self.pool.acquire() as c, c.transaction():
            await c.execute('SET LOCAL session_replication_role = replica')

            async def copy(table, source_id, changes):
                await c.execute(f'''INSERT INTO prep_inventory.{table} SELECT (jsonb_populate_record(NULL::prep_inventory.{table},
                    to_jsonb(t) || $2::jsonb)).* FROM prep_inventory.{table} t WHERE id=$1''', source_id,
                    {'store_id': 'rudds', 'request_key': str(uuid4()), **{k: str(v) if isinstance(v, UUID) else v for k, v in changes.items()}})
            base = {'predecessor_id': None, 'revision': 1}
            await copy('products', UUID(self.p['product_id']), {'id': ids['product']})
            await copy('product_versions', UUID(self.p['id']), {'id': ids['version'], 'product_id': ids['product'], **base})
            await copy('unit_profiles', UUID(self.u['id']), {'id': ids['profile'], 'product_version_id': ids['version'], **base})
            await copy('recipe_versions', UUID(self.r['id']), {'id': ids['recipe'], 'product_id': ids['product'], 'product_version_id': ids['version'],
                                                              'output_profile_id': ids['profile'], **base})
            await copy('planning_versions', UUID(self.maker_plan['id']), {'id': ids['plan'], 'product_id': ids['product'], 'recipe_version_id': ids['recipe'],
                                                                         'unit_profile_id': ids['profile'], 'weekday_par': par, 'weekend_par': par, **base})
        return ids

    async def rudds_count(self, quantity, business_date='2026-10-07', at='22:00'):
        event = uuid4()
        async with self.pool.acquire() as c, c.transaction():
            await c.execute('SET LOCAL session_replication_role = replica')
            await c.execute('''INSERT INTO prep_inventory.observations(id,store_id,purpose,root_id,revision,kind,performed_at,business_date,timezone_name,
                reason,review_snapshot,review_hash,recorded_by,request_key,request_fingerprint)
                VALUES($1,'rudds','count',$1,1,'initial',($2::date + $5::time) AT TIME ZONE 'America/New_York',$2,'America/New_York',
                'Invented Rudd''s Bulk count','{}'::jsonb,$3,'tester',$4,$3)''', event, date.fromisoformat(business_date), b'\x01' * 32, uuid4(), time.fromisoformat(at))
            await c.execute('''INSERT INTO prep_inventory.count_observations(event_id,store_id,line_number,product_id,product_version_id,profile_id,base_unit,
                quantity,factor,base_quantity,evidence) VALUES($1,'rudds',1,$2,$3,$4,'lb',$5,1,$5,'Measured')''',
                event, self.requester['product'], self.requester['version'], self.requester['profile'], D(quantity))
        return event

    async def request(self, body, key=None):
        p = await self.catalog.post('/api/pg/purchases/rudds/bulk-requests/preview', json=body)
        if p.status_code != 200: return p
        return await self.catalog.post('/api/pg/purchases/rudds/bulk-requests', json={'request': body, 'expected_review_hash': p.json()['reviewHash'], 'reviewed': True},
                                       headers={'Idempotency-Key': key or str(uuid4())})

    async def scheduled(self, count):
        r = await self.request(dict(run_date=RUN, kind='scheduled', day_group='weekday', count_event_id=str(count), note='Sunday night Bulk count'))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()['request']

    async def step(self, store, request_id, body):
        return await self.catalog.post(f'/api/pg/purchases/{store}/bulk-requests/{request_id}/steps', json=body, headers={'Idempotency-Key': str(uuid4())})

    def bulk_body(self, **changes):
        return self.draft_body(track='bulk') | changes

    async def test_request_is_par_minus_count_and_feeds_the_makers_run(self):
        sent = await self.scheduled(await self.rudds_count('12'))
        line = sent['lines'][0]
        self.assertEqual((sent['status'], D(line['requested_base_quantity']), D(line['counted_base_quantity'])), ('requested', D(18), D(12)))
        # The making store sees which count was used, not the requester's whole count record.
        self.assertEqual(set(sent['review_snapshot']['count']), {'id', 'business_date', 'performed_at', 'timezone_name'})
        # The maker's Bulk run: its own need (5 - 2 = 3) plus Rudd's 18 = 21, one 48 lb batch.
        count = await self.prep_count('2')
        saved = await self.write_day(self.bulk_body(count_event_id=count['id']))
        self.assertEqual(saved.status_code, 200, saved.text)
        t = saved.json()['draft']['review_snapshot']['tasks'][0]
        self.assertEqual((D(t['requested_base_quantity']), D(t['needed_base_quantity']), D(t['batches']), D(t['planned_base_quantity'])), (D(18), D(21), D(1), D(48)))
        # Cancelling the request flags the saved run for a fresh review.
        self.assertEqual((await self.step('rudds', sent['id'], dict(action='cancel', note='Recounted'))).status_code, 200)
        read = (await self.catalog.get(f'/api/pg/purchases/berts/prep-day-drafts/{RUN}', params={'track': 'bulk'})).json()
        self.assertTrue(read['current']['source_changed'])

    async def test_sign_off_order_shortfall_and_one_request_per_run(self):
        sent = await self.scheduled(await self.rudds_count('12'))
        rid = sent['id']
        self.assertEqual((await self.step('rudds', rid, dict(action='accept', note='Too early', lines=[dict(ordinal=1, base_quantity='1')]))).status_code, 409)
        fulfill = dict(action='fulfill', handoff='pickup', note='Made Thursday', lines=[dict(ordinal=1, base_quantity='12', held_base_quantity='3', packaging='3 x 5 lb bags')])
        self.assertEqual((await self.step('rudds', rid, fulfill)).status_code, 403)
        self.assertEqual((await self.step('berts', rid, fulfill | {'lines': [dict(ordinal=1, base_quantity='0', held_base_quantity='3')]})).status_code, 422)
        done = await self.step('berts', rid, fulfill); self.assertEqual(done.status_code, 200, done.text)
        self.assertEqual(done.json()['request']['status'], 'sent')
        self.assertEqual((await self.step('rudds', rid, dict(action='cancel', note='Late'))).status_code, 409)
        self.assertEqual((await self.step('rudds', rid, dict(action='accept', note='Over', lines=[dict(ordinal=1, base_quantity='13')]))).status_code, 422)
        ok = await self.step('rudds', rid, dict(action='accept', note='Checked in', lines=[dict(ordinal=1, base_quantity='12')]))
        self.assertEqual(ok.status_code, 200, ok.text)
        line = ok.json()['request']['lines'][0]
        # One par, any location: 18 requested = 12 accepted at Rudd's own store + 3 held at the maker + 3 still owed.
        self.assertEqual((D(line['accepted_base_quantity']), D(line['held_base_quantity']), D(line['shortfall_base_quantity']), line['packaging']), (D(12), D(3), D(3), '3 x 5 lb bags'))
        # Still owed stays listed even when its run is older than the history window.
        supply = (await self.catalog.get('/api/pg/purchases/rudds/bulk-supply', params={'since': '2026-12-01'})).json()
        self.assertEqual([(s['request_id'], D(s['shortfall_base_quantity'])) for s in supply['open_shortfalls']], [(rid, D(3))])
        again = await self.request(dict(run_date=RUN, kind='scheduled', day_group='weekday', count_event_id=str(await self.rudds_count('20', at='23:00')), note='Second'))
        self.assertEqual(again.status_code, 409)
        spot = await self.request(dict(run_date=RUN, kind='spot', note='Make up the shortfall',
                                       lines=[dict(product_id=str(self.requester['product']), quantity='3', reason='Short on Thursday')]))
        self.assertEqual(spot.status_code, 200, spot.text)
        self.assertEqual(D(spot.json()['request']['lines'][0]['requested_base_quantity']), D(3))
        # The spot prep makes up the shortfall; it stays closed even once both runs are older than the window.
        sid = spot.json()['request']['id']
        made = await self.step('berts', sid, dict(action='fulfill', handoff='delivery', note='Spot prep', lines=[dict(ordinal=1, base_quantity='3', packaging='1 x 5 lb bag')]))
        self.assertEqual(made.status_code, 200, made.text)
        self.assertEqual((await self.step('rudds', sid, dict(action='accept', note='In', lines=[dict(ordinal=1, base_quantity='3')]))).status_code, 200)
        later = (await self.catalog.get('/api/pg/purchases/rudds/bulk-supply', params={'since': '2026-12-01'})).json()
        self.assertEqual((later['open_shortfalls'], later['requests']), ([], []))

    async def test_database_refuses_a_forged_request_line(self):
        count = await self.rudds_count('12')
        async with self.pool.acquire() as c:
            with self.assertRaisesRegex(asyncpg.PostgresError, 'par minus counted on hand'):
                async with c.transaction():
                    ident = await c.fetchval('''INSERT INTO prep_inventory.bulk_requests(store_id,maker_store_id,run_date,kind,day_group,count_event_id,note,actor,
                        review_snapshot,request_key,request_fingerprint) VALUES('rudds','berts',$1,'scheduled','weekday',$2,'Forged','tester','{"lines":[{}]}',$3,$4) RETURNING id''',
                        date.fromisoformat(RUN), count, uuid4(), b'\x00' * 32)
                    await c.execute('''INSERT INTO prep_inventory.bulk_request_lines(request_id,store_id,maker_store_id,ordinal,product_id,maker_product_id,base_unit,
                        planning_version_id,factor,target_par,counted_base_quantity,requested_base_quantity) VALUES($1,'rudds','berts',1,$2,$3,'lb',$4,1,30,12,40)''',
                        ident, self.requester['product'], UUID(self.p['product_id']), self.requester['plan'])

    async def test_run_cannot_be_released_while_a_request_is_uncovered(self):
        flag = patch.dict(os.environ, {'PREP_EXECUTION_ENABLED': 'true'}); flag.start(); self.addCleanup(flag.stop)
        async with self.pool.acquire() as c:
            for name in ('20261005_prep_opening_sources.sql', '20261007_prep_execution.sql', '20261030_bulk_release_coverage.sql'):
                await c.execute((day.recovery.counts.native.ROOT / 'migrations' / name).read_text(encoding='utf-8'))
        await self.scheduled(await self.rudds_count('12'))  # Rudd's asks for 18 lb
        count = await self.prep_count('2')

        async def release(version, override):
            body = self.bulk_body(count_event_id=count['id'], overrides=[dict(planning_version_id=self.maker_plan['id'], reason='Invented maker decision', **override)])
            saved = await self.write_day(body, version=version); self.assertEqual(saved.status_code, 200, saved.text)
            draft = saved.json()['draft']
            command = dict(action='release', draft_version_id=draft['id'], reason='Manager reviewed the Bulk run')
            return draft, await self.catalog.post(f'/api/pg/purchases/berts/prep-execution/{RUN}/preview', params={'track': 'bulk'}, json=command, headers={'If-Match': '0'})

        for version, override in ((0, dict(kind='omit', quantity=None)), (1, dict(kind='fixed_quantity', quantity='10'))):
            draft, refused = await release(version, override)
            self.assertEqual(draft['review_snapshot']['uncovered_requests'], [self.p['product_id']])
            self.assertEqual(refused.status_code, 409, refused.text)
            self.assertIn('not covered', refused.text)
        draft, ok = await release(2, dict(kind='fixed_quantity', quantity='20'))
        self.assertEqual((draft['review_snapshot']['uncovered_requests'], ok.status_code), ([], 200), ok.text)
        command = dict(action='release', draft_version_id=draft['id'], reason='Manager reviewed the Bulk run')
        done = await self.catalog.post(f'/api/pg/purchases/berts/prep-execution/{RUN}/commands', params={'track': 'bulk'}, headers={'If-Match': '0', 'Idempotency-Key': str(uuid4())},
                                       json=dict(command=command, expected_review_hash=ok.json()['reviewHash'], reviewed=True))
        self.assertEqual(done.status_code, 200, done.text)  # the database release guard lets a covering run through
