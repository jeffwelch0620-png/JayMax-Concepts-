"""M2 Bulk run days (Jeff 2026-11-04): Bulk runs and scheduled requests on Monday or Thursday only,
and the par group follows the run day (Monday: weekday par; Thursday: weekend par)."""
import os
import unittest
from datetime import date
from uuid import UUID, uuid4

import asyncpg
from pydantic import ValidationError

import bulk_supply as bulk
import prep_day_tasks as tasks


class BulkRunDayModelTests(unittest.TestCase):
    def test_bulk_runs_on_monday_and_thursday_with_their_par_group(self):
        # 2026-10-05 is a Monday.
        groups = {date(2026, 10, 5 + d): tasks.bulk_day_group(date(2026, 10, 5 + d)) for d in range(7)}
        self.assertEqual([g for g in groups.values()], ['weekday', None, None, 'weekend', None, None, None])

    def test_the_server_sets_the_bulk_par_group_but_other_tracks_still_choose(self):
        tasks.DraftIn(track='bulk', note='Bulk run')
        tasks.DraftIn(track='daily', day_group='weekend', note='Daily list')
        with self.assertRaises(ValidationError): tasks.DraftIn(track='daily', note='No par group')
        bulk.RequestIn(run_date='2026-10-08', kind='scheduled', count_event_id=uuid4(), note='Wednesday count')


import test_bulk_supply as supply

MONDAY, TUESDAY, THURSDAY = '2026-10-12', '2026-10-06', supply.RUN
MIGRATION = 'migrations/20261104_bulk_run_days.sql'


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class BulkRunDayDatabaseTests(supply.BulkSupplyDatabaseTests):
    for _name in [n for n in dir(supply.BulkSupplyDatabaseTests) if n.startswith('test_')]:
        locals()[_name] = None
    del _name

    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with self.pool.acquire() as c:
            await c.execute((supply.day.recovery.counts.native.ROOT / MIGRATION).read_text(encoding='utf-8'))
        # Different weekday and weekend pars, so the par the server picks is visible.
        r = await self.edit(self.payload(track='bulk', weekday_par='5', weekend_par='9'), version=2); self.assertEqual(r.status_code, 200, r.text)
        self.maker_plan = r.json()['plan']

    async def test_bulk_runs_only_on_monday_or_thursday_and_spot_requests_any_day(self):
        count = await self.prep_count('2', stamp='2026-10-05T22:00:00-04:00')
        refused = await self.preview_day(self.bulk_body(count_event_id=count['id']), day=TUESDAY)
        self.assertEqual(refused.status_code, 422, refused.text); self.assertIn('Monday or Thursday', refused.text)
        asked = await self.catalog.post('/api/pg/purchases/rudds/bulk-requests/preview',
                                        json=dict(run_date=TUESDAY, kind='scheduled', count_event_id=str(await self.rudds_count('12', business_date='2026-10-05')), note='Monday count'))
        self.assertEqual(asked.status_code, 422, asked.text); self.assertIn('spot request', asked.text)
        spot = await self.request(dict(run_date=TUESDAY, kind='spot', note='Ran out early',
                                       lines=[dict(product_id=str(self.requester['product']), quantity='3', reason='Busy Monday')]))
        self.assertEqual(spot.status_code, 200, spot.text)

    async def test_the_par_group_follows_the_run_day(self):
        # Thursday: the weekend par (9), even when the screen sends "weekday".
        thursday = await self.write_day(self.bulk_body(day_group='weekday', count_event_id=(await self.prep_count('2'))['id']), day=THURSDAY)
        self.assertEqual(thursday.status_code, 200, thursday.text)
        snapshot = thursday.json()['draft']['review_snapshot']
        self.assertEqual((snapshot['inputs']['day_group'], snapshot['tasks'][0]['target_par']), ('weekend', '9'))
        # Monday: the weekday par (5), from Sunday night's count.
        monday = await self.write_day(self.bulk_body(day_group='weekend', count_event_id=(await self.prep_count('2', stamp='2026-10-11T22:00:00-04:00'))['id']), day=MONDAY)
        self.assertEqual(monday.status_code, 200, monday.text)
        snapshot = monday.json()['draft']['review_snapshot']
        self.assertEqual((snapshot['inputs']['day_group'], snapshot['tasks'][0]['target_par']), ('weekday', '5'))
        # A requester's Thursday request is stored with the weekend par group too.
        sent = await self.request(dict(run_date=THURSDAY, kind='scheduled', day_group='weekday', count_event_id=str(await self.rudds_count('12')), note='Wednesday count'))
        self.assertEqual(sent.status_code, 200, sent.text)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT day_group FROM prep_inventory.bulk_requests WHERE id=$1', UUID(sent.json()['request']['id'])), 'weekend')

    async def test_database_refuses_another_day_or_the_wrong_par_group(self):
        saved = await self.write_day(self.bulk_body(count_event_id=(await self.prep_count('2'))['id']), day=THURSDAY)
        self.assertEqual(saved.status_code, 200, saved.text); draft = saved.json()['draft']
        async with self.pool.acquire() as c:
            with self.assertRaisesRegex(asyncpg.PostgresError, 'Thursday run the weekend par'):
                async with c.transaction():
                    await c.execute('''INSERT INTO prep_inventory.day_list_versions(list_id,store_id,revision,predecessor_id,day_group,note,actor,review_snapshot,review_hash,request_key,request_fingerprint)
                        VALUES($1,'berts',2,$2,'weekday','Forged','synthetic-DB-probe',$3,$4,$5,$4)''',
                        UUID(draft['list_id']), UUID(draft['id']), draft['review_snapshot'], bytes(32), uuid4())
            count = await self.rudds_count('12', business_date='2026-10-05')
            for run, group, message in ((TUESDAY, 'weekday', 'Monday or Thursday'), (THURSDAY, 'weekday', 'Thursday run the weekend par')):
                with self.assertRaisesRegex(asyncpg.PostgresError, message):
                    async with c.transaction():
                        await c.execute('''INSERT INTO prep_inventory.bulk_requests(store_id,maker_store_id,run_date,kind,day_group,count_event_id,note,actor,
                            review_snapshot,request_key,request_fingerprint) VALUES('rudds','berts',$1,'scheduled',$2,$3,'Forged','tester','{"lines":[{}]}',$4,$5)''',
                            date.fromisoformat(run), group, count, uuid4(), b'\x00' * 32)
