"""Stations and station time: a cook's queue follows their station; every stint is kept (Jeff 2026-10-30)."""
import os
import unittest
from datetime import datetime
from uuid import uuid4

import asyncpg
from pydantic import ValidationError

import server
import stations


class StationModelTests(unittest.TestCase):
    def test_moves_and_defaults_are_explicit(self):
        stations.Move(staff_member_id=uuid4(), station_code='GRILL')
        stations.Move(staff_member_id=uuid4(), station_code=None, reason='shift_end')
        for bad in (dict(reason='lunch'), dict(station_code=''), dict(actor='forged')):
            with self.assertRaises(ValidationError): stations.Move(**(dict(staff_member_id=uuid4(), station_code='GRILL') | bad))
        with self.assertRaises(ValidationError): stations.ProductStation(station_code='PREP', note=' ')

    def test_moves_are_for_today_or_yesterday(self):
        today = datetime.now(stations.STORE_ZONE).date()
        stations.check_day(today)
        with self.assertRaises(server.HTTPException): stations.check_day(today.replace(year=today.year - 1))


import test_staff_prep_tasks as staff

MIGRATION = 'migrations/20261031_stations.sql'


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class StationDatabaseTests(staff.StaffTaskTests):
    # Reuse the staff-task fixture without re-running its own tests here.
    for _name in [n for n in dir(staff.StaffTaskTests) if n.startswith('test_')]:
        locals()[_name] = None
    del _name

    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with self.pool.acquire() as c:
            await c.execute((staff.fixtures.fixtures.fixtures.recovery.counts.native.ROOT / MIGRATION).read_text(encoding='utf-8'))
        self.today = str(datetime.now(stations.STORE_ZONE).date())

    def headers(self, token=None):
        return {'Authorization': 'Bearer ' + (token or self.owner), 'Idempotency-Key': str(uuid4())}

    async def move(self, member, station, reason='moved', token=None):
        return await self.portal.post(f'/api/pg/purchases/berts/stations/board/{self.today}/moves', headers=self.headers(token),
                                      json={'staff_member_id': str(member), 'station_code': station, 'reason': reason})

    async def test_a_cooks_queue_follows_their_station_and_named_assignments_win(self):
        _, task = await self.start()
        default = await self.portal.put(f"/api/pg/purchases/berts/stations/products/{task['product_id']}", headers=self.headers(),
                                        json={'station_code': 'PREP', 'note': 'Prep cook makes it'})
        self.assertEqual(default.status_code, 200, default.text)
        self.assertEqual((await self.move(self.member, 'PREP')).status_code, 200)
        plan = (await self.staff_plan(member=self.member)).json()
        self.assertEqual((plan['station'], [(t['id'], t['via']) for t in plan['tasks']]), ('PREP', [(task['id'], 'station')]))
        self.assertEqual((await self.staff_plan(member=self.other_member)).json()['tasks'], [])  # not on a station
        # Assigned by name to cook B: it leaves cook A's station queue and goes to B.
        self.assertEqual((await self.assign(self.assignment_body(task, member=self.other_member))).status_code, 200)
        self.assertEqual((await self.staff_plan(member=self.member)).json()['tasks'], [])
        self.assertEqual([t['via'] for t in (await self.staff_plan(member=self.other_member)).json()['tasks']], ['name'])

    async def test_every_stint_is_kept_and_one_station_at_a_time(self):
        self.assertEqual((await self.move(self.member, 'PREP')).status_code, 200)
        moved = await self.move(self.member, 'GRILL')
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertEqual((await self.move(self.member, 'GRILL')).status_code, 409)  # already there
        done = await self.move(self.member, None, reason='shift_end')
        self.assertEqual(done.status_code, 200, done.text)
        history = done.json()['board']['history']
        self.assertEqual([(h['station_code'], h['end_reason']) for h in history], [('PREP', 'moved'), ('GRILL', 'shift_end')])
        self.assertEqual(done.json()['board']['open'], [])
        # The database allows one open stint per person, even without the app.
        async with self.pool.acquire() as c, c.transaction():
            await c.execute("INSERT INTO workforce.station_stints(store_id,staff_member_id,station_code,business_date,source,assigned_by,request_key,request_fingerprint) VALUES('berts',$1,'FRY',$2,'board','tester',$3,$4)",
                            self.member, datetime.now(stations.STORE_ZONE).date(), uuid4(), b'\x00' * 32)
            with self.assertRaisesRegex(asyncpg.PostgresError, 'already on a station'):
                await c.execute("INSERT INTO workforce.station_stints(store_id,staff_member_id,station_code,business_date,source,assigned_by,request_key,request_fingerprint) VALUES('berts',$1,'EXPO',$2,'board','tester',$3,$4)",
                                self.member, datetime.now(stations.STORE_ZONE).date(), uuid4(), b'\x00' * 32)

    async def test_only_boh_shift_leaders_and_up_run_the_board(self):
        foh = server._token({'id': 'invented-sl-foh', 'email': 'slfoh@example.invalid', 'role': 'manager', 'position': 'SL-FOH', 'locations': ['berts']})
        boh = server._token({'id': 'invented-sl-boh', 'email': 'slboh@example.invalid', 'role': 'manager', 'position': 'SL-BOH', 'locations': ['berts']})
        self.assertEqual((await self.move(self.member, 'PREP', token=foh)).status_code, 403)
        self.assertEqual((await self.move(self.member, 'PREP', token=boh)).status_code, 200)
        # A BOH Shift Leader can't change which station normally makes an item; a KM can.
        _, task = await self.start()
        km = server._token({'id': 'invented-km', 'email': 'km@example.invalid', 'role': 'manager', 'position': 'KM', 'locations': ['berts']})
        url = f"/api/pg/purchases/berts/stations/products/{task['product_id']}"
        self.assertEqual((await self.portal.put(url, headers=self.headers(boh), json={'station_code': 'PREP', 'note': 'x'})).status_code, 403)
        self.assertEqual((await self.portal.put(url, headers=self.headers(km), json={'station_code': 'PREP', 'note': 'x'})).status_code, 200)
