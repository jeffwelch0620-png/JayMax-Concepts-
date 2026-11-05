"""M2 Bulk daily pars, phase B (Jeff 2026-11-05): the quick daily Bulk count and the spot-prep check.
In daily par mode a night's count is compared with the daily pars for the days left before the next
Monday or Thursday run, less spot requests already on their way; the check only suggests."""
import os
import unittest
from datetime import date
from decimal import Decimal as D
from uuid import UUID, uuid4

import asyncpg
from pydantic import ValidationError

import bulk_quick_count as quick

PARS = ['1', '2', '3', '4', '5', '6', '7']


class QuickCountModelTests(unittest.TestCase):
    def test_days_left_before_the_next_run(self):
        # 2026-10-05 is a Monday. Sunday and Wednesday nights: the next morning's run covers the day.
        left = {date(2026, 10, 5 + d).strftime('%a'): quick.days_before_next_run(date(2026, 10, 5 + d)) for d in range(7)}
        self.assertEqual({k: v[0] for k, v in left.items()}, {'Mon': [1, 2], 'Tue': [2], 'Wed': [], 'Thu': [4, 5, 6], 'Fri': [5, 6], 'Sat': [6], 'Sun': []})
        self.assertEqual(left['Fri'][1], date(2026, 10, 12)); self.assertEqual(left['Wed'][1], date(2026, 10, 8))

    def test_spot_need_is_the_days_left_less_on_hand_and_on_the_way(self):
        friday = date(2026, 10, 9)  # Saturday and Sunday left: 6 + 7 = 13 par units
        need = quick.spot_need({'daily_pars': PARS}, D(2), friday, D(10), D(4))
        self.assertEqual((need['need_base_quantity'], need['short_base_quantity'], need['spot_quantity']), (D(26), D(12), D(6)))
        self.assertEqual(quick.spot_need({'daily_pars': PARS}, D(2), friday, D(30), D(0))['spot_quantity'], D(0))
        # Rounded up to the spot request's 12 decimal places, so the request covers the shortfall.
        self.assertEqual(quick.spot_need({'daily_pars': PARS}, D(3), friday, D(0), D(0))['spot_quantity'], D(13))
        self.assertEqual(quick.spot_need({'daily_pars': PARS}, D(3), friday, D(1), D(0))['spot_quantity'], D('12.666666666667'))
        self.assertIsNone(quick.spot_need({'daily_pars': None}, D(1), friday, D(0), D(0)))
        self.assertEqual(quick.spot_need({'daily_pars': PARS}, D(1), date(2026, 10, 7), D(0), D(0))['need_base_quantity'], D(0))  # Wednesday night

    def test_a_quick_count_is_for_the_night_it_was_taken(self):
        line = [dict(product_id=uuid4(), quantity='2')]
        quick.QuickCountIn(business_date='2026-10-09', performed_at='2026-10-09T22:00:00-04:00', note='Invented close', lines=line)
        quick.QuickCountIn(business_date='2026-10-09', performed_at='2026-10-10T01:30:00-04:00', note='After midnight', lines=line)
        for bad in (dict(performed_at='2026-10-11T09:00:00-04:00', lines=line), dict(performed_at='2026-10-09T22:00:00', lines=line),
                    dict(performed_at='2026-10-09T22:00:00-04:00', lines=line * 2),
                    dict(performed_at='2026-10-09T22:00:00-04:00', lines=[dict(product_id=uuid4(), quantity='-1')])):
            with self.assertRaises(ValidationError): quick.QuickCountIn(business_date='2026-10-09', note='Invented', **bad)


import test_bulk_daily_pars as daily_pars

FRIDAY, WEDNESDAY = '2026-10-09', '2026-10-07'
MIGRATION = 'migrations/20261105_bulk_quick_counts.sql'


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class QuickCountDatabaseTests(daily_pars.BulkDailyParDatabaseTests):
    for _name in [n for n in dir(daily_pars.BulkDailyParDatabaseTests) if n.startswith('test_')]:
        locals()[_name] = None
    del _name

    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with self.pool.acquire() as c:
            await c.execute((daily_pars.run_days.supply.day.recovery.counts.native.ROOT / MIGRATION).read_text(encoding='utf-8'))
        await self.pool.expire_connections()

    async def quick(self, quantity, night=FRIDAY, version=0, store='berts', product=None, key=None, at='22:00:00'):
        body = dict(business_date=night, performed_at=f'{night}T{at}-04:00', note='Invented quick Bulk count',
                    lines=[dict(product_id=str(product or self.p['product_id']), quantity=quantity)])
        return await self.catalog.post(f'/api/pg/purchases/{store}/bulk-quick-counts', json=body,
                                       headers={'If-Match': str(version), 'Idempotency-Key': key or str(uuid4())})

    async def read(self, night=FRIDAY, store='berts'):
        r = await self.catalog.get(f'/api/pg/purchases/{store}/bulk-quick-counts', params={'night': night})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    async def test_the_check_shows_the_spot_prep_needed_before_the_next_run(self):
        # Window mode: the count is kept, but there are no daily pars to check against.
        first = await self.quick('4'); self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual((first.json()['revision'], first.json()['par_mode'], first.json()['check']), (1, 'window', None))
        factor = D(first.json()['items'][0]['factor'])
        await self.daily_pars(); self.assertEqual((await self.switch('daily', 0)).status_code, 200)
        read = await self.read()
        self.assertTrue(read['check_complete'])
        # Friday night: Saturday and Sunday (6 + 7 par units) are left before Monday's run.
        line = read['check'][0]
        self.assertEqual((line['days'], line['next_run'], D(line['need_base_quantity']), D(line['counted_base_quantity'])), ([5, 6], '2026-10-12', 13 * factor, 4 * factor))
        self.assertEqual(D(line['short_base_quantity']), 13 * factor - 4 * factor)
        # A correction is a new revision; the original stays.
        key = str(uuid4())
        fixed = await self.quick('20', version=1, key=key); self.assertEqual(fixed.status_code, 200, fixed.text)
        self.assertEqual(([c['revision'] for c in fixed.json()['counts']], D(fixed.json()['check'][0]['spot_quantity'])), ([1, 2], D(0)))
        replay = await self.quick('20', version=1, key=key)
        self.assertEqual((replay.json()['replayed'], replay.json()['count_id']), (True, fixed.json()['count_id']))
        self.assertEqual((await self.quick('20', version=1)).status_code, 409)  # stale version
        # Wednesday night: Thursday's run covers Thursday, so nothing is needed.
        wednesday = await self.quick('0', night=WEDNESDAY); self.assertEqual(wednesday.status_code, 200, wednesday.text)
        self.assertEqual(D(wednesday.json()['check'][0]['short_base_quantity']), D(0))

    async def test_a_requesting_store_counts_spot_requests_on_their_way(self):
        # Rudd's own copy of the item gets daily pars of 10 a day and switches to daily pars (written directly).
        async with self.pool.acquire() as c, c.transaction():
            await c.execute('SET LOCAL session_replication_role = replica')
            plan = await c.fetchrow('SELECT * FROM prep_inventory.planning_versions WHERE id=$1', self.requester['plan'])
            await c.execute('''INSERT INTO prep_inventory.planning_versions SELECT (jsonb_populate_record(NULL::prep_inventory.planning_versions,
                to_jsonb(t) || $2::jsonb)).* FROM prep_inventory.planning_versions t WHERE id=$1''', plan['id'],
                {'id': str(uuid4()), 'revision': plan['revision'] + 1, 'predecessor_id': str(plan['id']), 'daily_pars': ['10'] * 7, 'request_key': str(uuid4())})
            await c.execute('''INSERT INTO prep_inventory.bulk_par_modes(store_id,revision,mode,note,actor,request_key,request_fingerprint)
                VALUES('rudds',1,'daily','Invented switch','synthetic-DB-probe',$1,$2)''', uuid4(), b'\x00' * 32)
        counted = await self.quick('12', store='rudds', product=self.requester['product']); self.assertEqual(counted.status_code, 200, counted.text)
        factor = D(counted.json()['items'][0]['factor'])
        self.assertEqual(D(counted.json()['check'][0]['short_base_quantity']), 20 * factor - 12 * factor)
        spot = await self.request(dict(run_date='2026-10-10', kind='spot', note='Busy weekend',
                                       lines=[dict(product_id=str(self.requester['product']), quantity='3', reason='Quick count short')]))
        self.assertEqual(spot.status_code, 200, spot.text)
        line = (await self.read(store='rudds'))['check'][0]
        self.assertEqual((D(line['incoming_base_quantity']), D(line['short_base_quantity'])), (3 * factor, 17 * factor - 12 * factor))
        # Once the maker signs off, only what it actually sent is on the way.
        sent = await self.step('berts', spot.json()['request']['id'], dict(action='fulfill', handoff='delivery', note='Made part of it',
                                                                          lines=[dict(ordinal=1, base_quantity=str(factor), packaging='1 x invented tub')]))
        self.assertEqual(sent.status_code, 200, sent.text)
        line = (await self.read(store='rudds'))['check'][0]
        self.assertEqual((D(line['incoming_base_quantity']), D(line['short_base_quantity'])), (factor, 19 * factor - 12 * factor))
        # Only active to-par Bulk items of this store can be counted here.
        self.assertEqual((await self.quick('1', store='rudds', product=self.p['product_id'])).status_code, 422)

    async def test_database_refuses_incomplete_or_changed_quick_counts(self):
        async def insert(c, revision=1, predecessor=None, lines=1, factor=None):
            ident = uuid4()
            await c.execute('''INSERT INTO prep_inventory.bulk_quick_counts(id,store_id,business_date,revision,predecessor_id,performed_at,timezone_name,
                note,actor,review_snapshot,request_key,request_fingerprint) VALUES($1,'berts',$2,$3,$4,'2026-10-09T22:00:00-04:00','America/New_York',
                'Forged','synthetic-DB-probe',$5,$6,$7)''', ident, date(2026, 10, 9), revision, predecessor, {'lines': [{}] * lines}, uuid4(), b'\x00' * 32)
            for n in range(lines):
                await c.execute('''INSERT INTO prep_inventory.bulk_quick_count_lines(count_id,store_id,line_number,product_id,product_version_id,profile_id,
                    base_unit,quantity,factor,base_quantity) VALUES($1,'berts',$2,$3,$4,$5,$6,2,$7::numeric,2*$7::numeric)''', ident, n + 1, UUID(self.p['product_id']),
                    UUID(self.u['product_version_id']), UUID(self.u['id']), self.p['base_unit'], factor or D(self.u['base_units_per_source_unit']))
            return ident
        async with self.pool.acquire() as c:
            with self.assertRaisesRegex(asyncpg.PostgresError, 'missing count is not zero'):
                async with c.transaction(): await insert(c, lines=0)
            with self.assertRaisesRegex(asyncpg.PostgresError, 'verified unit conversion'):
                async with c.transaction(): await insert(c, factor=D('123.5'))
            with self.assertRaisesRegex(asyncpg.PostgresError, 'refresh before correcting'):
                async with c.transaction(): await insert(c, revision=2)
            async with c.transaction(): first = await insert(c)
            with self.assertRaises(asyncpg.PostgresError):
                await c.execute("UPDATE prep_inventory.bulk_quick_count_lines SET quantity=3, base_quantity=3*factor WHERE count_id=$1", first)
            with self.assertRaisesRegex(asyncpg.PostgresError, 'cannot gain lines'):
                await c.execute('''INSERT INTO prep_inventory.bulk_quick_count_lines(count_id,store_id,line_number,product_id,product_version_id,profile_id,
                    base_unit,quantity,factor,base_quantity) VALUES($1,'berts',2,$2,$3,$4,$5,1,$6::numeric,$6::numeric)''', first, uuid4(),
                    UUID(self.u['product_version_id']), UUID(self.u['id']), self.p['base_unit'], D(self.u['base_units_per_source_unit']))
