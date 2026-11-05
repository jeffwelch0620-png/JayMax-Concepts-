"""M2 Bulk daily pars (Jeff 2026-11-04): each store chooses window pars (Monday run weekday par,
Thursday run weekend par) or daily pars (a run's target is the sum of the days it covers)."""
import os
import unittest
from datetime import date
from decimal import Decimal as D
from uuid import UUID, uuid4

import asyncpg
from pydantic import ValidationError

import prep_day_tasks as tasks
import prep_planning as planning

PLAN = {'weekday_par': '5', 'weekend_par': '9', 'daily_pars': ['1', '2', '3', '4', '5', '6', '7']}


class BulkDailyParModelTests(unittest.TestCase):
    def test_a_run_target_follows_the_store_par_mode(self):
        monday, tuesday, thursday = date(2026, 10, 12), date(2026, 10, 13), date(2026, 10, 15)
        self.assertEqual([tasks.bulk_run_target(PLAN, d, 'window') for d in (monday, thursday)], [D(5), D(9)])
        # Daily: Monday covers Monday to Wednesday (1+2+3), Thursday covers Thursday to Sunday (4+5+6+7).
        self.assertEqual([tasks.bulk_run_target(PLAN, d, 'daily') for d in (monday, thursday)], [D(6), D(22)])
        self.assertIsNone(tasks.bulk_run_target(PLAN, tuesday, 'window'))
        self.assertIsNone(tasks.bulk_run_target(PLAN | {'daily_pars': None}, monday, 'daily'))
        # Summed exactly, as SQL numeric does; Python's default 28 digits would round this.
        big = PLAN | {'daily_pars': ['9999999999999999.999999999999'] * 7}
        self.assertEqual(tasks.bulk_run_target(big, monday, 'daily'), D('29999999999999999.999999999997'))

    def test_only_to_par_bulk_items_take_seven_daily_pars(self):
        base = dict(action='save', recipe_version_id=uuid4(), unit_profile_id=uuid4(), weekday_par='5', weekend_par='9', note='Invented pars', verified=True)
        planning.SavePlan(track='bulk', schedule='daily', daily_pars=PLAN['daily_pars'], **base)
        planning.SavePlan(track='bulk', schedule='daily', **base)
        for bad in (dict(track='daily', schedule='daily', daily_pars=PLAN['daily_pars']),
                    dict(track='bulk', schedule='on_demand', daily_pars=PLAN['daily_pars']),
                    dict(track='bulk', schedule='daily', daily_pars=PLAN['daily_pars'][:6]),
                    dict(track='bulk', schedule='daily', daily_pars=['-1'] + PLAN['daily_pars'][1:]),
                    dict(track='bulk', schedule='daily', daily_pars=['NaN'] + PLAN['daily_pars'][1:])):
            with self.assertRaises(ValidationError): planning.SavePlan(**base, **bad)
        planning.ParModeIn(mode='daily', note='Switching to daily pars')
        with self.assertRaises(ValidationError): planning.ParModeIn(mode='weekly', note='No such mode')


import test_bulk_run_days as run_days

MONDAY, THURSDAY = run_days.MONDAY, run_days.THURSDAY
MIGRATION = 'migrations/20261105_bulk_daily_pars.sql'


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class BulkDailyParDatabaseTests(run_days.BulkRunDayDatabaseTests):
    for _name in [n for n in dir(run_days.BulkRunDayDatabaseTests) if n.startswith('test_')]:
        locals()[_name] = None
    del _name

    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with self.pool.acquire() as c:
            await c.execute((run_days.supply.day.recovery.counts.native.ROOT / MIGRATION).read_text(encoding='utf-8'))

    async def switch(self, mode, version, store='berts'):
        return await self.owner_client.put(f'/api/pg/purchases/{store}/bulk-par-mode', json=dict(mode=mode, note=f'Invented switch to {mode} pars'),
                                           headers={'If-Match': str(version), 'Idempotency-Key': str(uuid4())})

    async def daily_pars(self, version=3):
        r = await self.edit(self.payload(track='bulk', weekday_par='5', weekend_par='9', daily_pars=PLAN['daily_pars']), version=version)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()['plan']

    async def test_daily_mode_targets_the_sum_of_the_days_each_run_covers(self):
        refused = await self.switch('daily', 0)
        self.assertEqual(refused.status_code, 409, refused.text); self.assertIn('Enter daily pars', refused.text)
        await self.daily_pars()
        switched = await self.switch('daily', 0); self.assertEqual(switched.status_code, 200, switched.text)
        self.assertEqual((switched.json()['mode'], switched.json()['revision']), ('daily', 1))
        self.assertEqual((await self.switch('daily', 1)).status_code, 409)  # already daily
        self.assertEqual((await self.switch('window', 0)).status_code, 409)  # stale version
        # In daily mode a to-par Bulk item cannot be saved without its daily pars.
        self.assertEqual((await self.edit(self.payload(track='bulk', weekday_par='5', weekend_par='9'), version=4)).status_code, 422)
        thursday = await self.write_day(self.bulk_body(count_event_id=(await self.prep_count('2'))['id']), day=THURSDAY)
        self.assertEqual(thursday.status_code, 200, thursday.text)
        review = thursday.json()['draft']['review_snapshot']
        self.assertEqual((review['par_mode'], D(review['tasks'][0]['target_par'])), ('daily', D(22)))
        monday = await self.write_day(self.bulk_body(count_event_id=(await self.prep_count('2', stamp='2026-10-11T22:00:00-04:00'))['id']), day=MONDAY)
        self.assertEqual(monday.status_code, 200, monday.text)
        self.assertEqual(D(monday.json()['draft']['review_snapshot']['tasks'][0]['target_par']), D(6))
        # Back to window pars: the Thursday run uses the weekend par again.
        self.assertEqual((await self.switch('window', 1)).status_code, 200)
        read = (await self.catalog.get('/api/pg/purchases/berts/bulk-par-mode')).json()
        self.assertEqual(([h['mode'] for h in read['history']], read['mode'], read['revision']), (['daily', 'window'], 'window', 2))
        again = await self.preview_day(self.bulk_body(count_event_id=(await self.prep_count('2', stamp='2026-10-07T23:00:00-04:00'))['id']), version=1, day=THURSDAY)
        self.assertEqual(D(again.json()['review']['tasks'][0]['target_par']), D(9))

    async def test_switching_mode_flags_a_saved_run_and_each_store_keeps_its_own_mode(self):
        saved = await self.write_day(self.bulk_body(count_event_id=(await self.prep_count('2'))['id']), day=THURSDAY)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()['draft']['review_snapshot']['par_mode'], 'window')
        await self.daily_pars()
        self.assertEqual((await self.switch('daily', 0)).status_code, 200)
        read = (await self.catalog.get(f'/api/pg/purchases/berts/prep-day-drafts/{THURSDAY}', params={'track': 'bulk'})).json()
        self.assertTrue(read['current']['source_changed'])
        # Rudd's is still on window pars, so its request is par 30 minus 12 counted; it cannot go daily without daily pars.
        sent = await self.request(dict(run_date=THURSDAY, kind='scheduled', count_event_id=str(await self.rudds_count('12')), note='Wednesday count'))
        self.assertEqual(sent.status_code, 200, sent.text)
        self.assertEqual((D(sent.json()['request']['lines'][0]['target_par']), sent.json()['request']['review_snapshot']['par_mode']), (D(30), 'window'))
        refused = await self.switch('daily', 0, store='rudds')
        self.assertEqual(refused.status_code, 409, refused.text)
        missing = (await self.catalog.get('/api/pg/purchases/rudds/bulk-par-mode')).json()['missing_daily_pars']
        self.assertEqual(len(missing), 1); self.assertIn(missing[0], refused.text)

    async def test_database_refuses_daily_mode_without_pars_and_keeps_retired_pars(self):
        async with self.pool.acquire() as c:
            with self.assertRaisesRegex(asyncpg.PostgresError, 'Enter daily pars for every active Bulk item'):
                await c.execute('''INSERT INTO prep_inventory.bulk_par_modes(store_id,revision,mode,note,actor,request_key,request_fingerprint)
                    VALUES('berts',1,'daily','Forged','synthetic-DB-probe',$1,$2)''', uuid4(), b'\x00' * 32)
            with self.assertRaisesRegex(asyncpg.PostgresError, 'refresh before switching'):
                await c.execute('''INSERT INTO prep_inventory.bulk_par_modes(store_id,revision,mode,note,actor,request_key,request_fingerprint)
                    VALUES('berts',2,'window','Forged','synthetic-DB-probe',$1,$2)''', uuid4(), b'\x00' * 32)
        plan = await self.daily_pars()
        retired = await self.edit(dict(action='retire', note='Invented retirement'), version=plan['revision'])
        self.assertEqual(retired.status_code, 200, retired.text)
        self.assertEqual(retired.json()['plan']['daily_pars'], plan['daily_pars'])
        async with self.pool.acquire() as c:
            with self.assertRaises(asyncpg.PostgresError):
                await c.execute('UPDATE prep_inventory.planning_versions SET daily_pars=NULL WHERE id=$1', UUID(plan['id']))
