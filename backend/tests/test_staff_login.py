"""Personal staff sign-in: own name and PIN; the store PIN is retired (Jeff 2026-10-30 and 2026-10-31)."""
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import asyncpg
from pydantic import ValidationError

import deployment_readiness
import positions
import server
import staff_login


class StaffLoginModelTests(unittest.TestCase):
    def test_pins_are_four_or_five_digits(self):
        for pin in ('1234', '12345'):
            staff_login.SignIn(staff_member_id=uuid4(), pin=pin)
            staff_login.IssuePin(pin=pin)
        for bad in ('123', '123456', '12a4', ''):
            with self.assertRaises(ValidationError): staff_login.SignIn(staff_member_id=uuid4(), pin=bad)
            with self.assertRaises(ValidationError): staff_login.IssuePin(pin=bad)
        with self.assertRaises(ValidationError): staff_login.SignIn(staff_member_id=uuid4(), pin='1234', name='forged')

    def test_pins_are_stored_salted_and_hashed(self):
        first, second = staff_login.pin_hash('4821'), staff_login.pin_hash('4821')
        self.assertNotEqual(first, second)
        self.assertRegex(first, r'^pbkdf2\$[A-Za-z0-9_-]+\$[0-9a-f]{64}$')
        self.assertTrue(staff_login.pin_ok('4821', first))
        self.assertFalse(staff_login.pin_ok('4822', first))
        self.assertFalse(staff_login.pin_ok('4821', 'not-a-hash'))

    def test_owners_and_the_ops_lead_issue_pins_and_managers_unlock(self):
        for code in ('OWN', 'OPS'):
            self.assertTrue(positions.can({'role': 'owner', 'position': code}, 'issue_pins'))
        for code in ('GM', 'KM', 'FOHM', 'BPM'):
            self.assertFalse(positions.can({'role': 'manager', 'position': code}, 'issue_pins'))
            self.assertTrue(positions.can({'role': 'manager', 'position': code}, 'unlock_pins'))
        for code in ('SL-BOH', 'SL-FOH'):
            self.assertFalse(positions.can({'role': 'manager', 'position': code}, 'unlock_pins'))
        self.assertTrue(positions.can({'role': 'manager'}, 'unlock_pins'))      # managers without a position
        self.assertFalse(positions.can({'role': 'manager'}, 'issue_pins'))

    def test_sign_in_routes_are_reachable_without_a_login_and_pin_management_is_not(self):
        self.assertTrue(server._is_pin_optional('/api/pg/staff/berts/sign-in'))
        self.assertTrue(server._is_pin_optional('/api/pg/staff/berts/sign-in/names'))
        self.assertFalse(server._is_pin_optional('/api/pg/staff/berts/members/sign-in'))
        self.assertFalse(server._is_pin_optional(f'/api/pg/staff/berts/members/{uuid4()}/pin'))

    def test_a_staff_session_reaches_the_employee_screens_only(self):
        for path in ('/staff/berts/sign-out', '/staff/berts/tasks', f'/staff/berts/tasks/{uuid4()}/complete', '/staff/berts/prep-task-plan',
                     '/staff/berts/station', '/staff/berts/prep-production/2026-10-08/submissions', '/staff/berts/push/subscribe'):
            self.assertTrue(server.PERSONAL_STAFF_ROUTE.fullmatch(path), path)
        for path in ('/invoices/berts', '/items/berts', '/staff/berts/members', f'/staff/berts/members/{uuid4()}/pin',
                     '/staff/berts/pin', '/staff/berts/verify', '/purchases/berts/stations/board/2026-10-08'):
            self.assertFalse(server.PERSONAL_STAFF_ROUTE.fullmatch(path), path)

    def test_readiness_holds_a_backend_only_switch(self):
        base = {'USE_PG': 'true'}, {'REACT_APP_USE_PG': 'true'}
        self.assertNotIn('STAFF_PERSONAL_LOGIN', str(deployment_readiness.configuration(*base)['problems']))
        held = deployment_readiness.configuration(base[0] | {'STAFF_PERSONAL_LOGIN_ENABLED': 'true'}, base[1])
        self.assertIn('STAFF_PERSONAL_LOGIN', str(held['problems']))
        both = deployment_readiness.configuration(base[0] | {'STAFF_PERSONAL_LOGIN_ENABLED': 'true'}, base[1] | {'REACT_APP_STAFF_PERSONAL_LOGIN': 'true'})
        self.assertNotIn('STAFF_PERSONAL_LOGIN', str(both['problems']))


import test_staff_prep_tasks as staff

MIGRATION = 'migrations/20261101_staff_personal_login.sql'


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class StaffLoginDatabaseTests(staff.StaffTaskTests):
    # Reuse the staff-task fixture without re-running its own tests here.
    for _name in [n for n in dir(staff.StaffTaskTests) if n.startswith('test_')]:
        locals()[_name] = None
    del _name

    async def asyncSetUp(self):
        await super().asyncSetUp()
        flag = patch.dict(os.environ, {'STAFF_PERSONAL_LOGIN_ENABLED': 'true'}); flag.start(); self.addCleanup(flag.stop)
        async with self.pool.acquire() as c:
            await c.execute((staff.fixtures.fixtures.fixtures.recovery.counts.native.ROOT / MIGRATION).read_text(encoding='utf-8'))
        self.ops = server._token({'id': 'invented-ops', 'email': 'ops@example.invalid', 'role': 'owner', 'position': 'OPS'})

    def manager(self, position):
        return server._token({'id': f'invented-{position}', 'email': f'{position}@example.invalid', 'role': 'manager',
                              'position': position, 'locations': ['berts']})

    async def issue(self, member, pin, token=None, key=None):
        return await self.portal.put(f'/api/pg/staff/berts/members/{member}/pin', json={'pin': pin},
                                     headers={'Authorization': 'Bearer ' + (token or self.ops), 'Idempotency-Key': key or str(uuid4())})

    async def sign_in(self, member, pin, new_pin=None, store='berts'):
        body = {'staff_member_id': str(member), 'pin': pin} | ({'new_pin': new_pin} if new_pin else {})
        return await self.portal.post(f'/api/pg/staff/{store}/sign-in', json=body)

    async def signed_in(self, member, temporary='4821', own='7350'):
        self.assertEqual((await self.issue(member, temporary)).status_code, 200)
        done = await self.sign_in(member, temporary, own)
        self.assertEqual(done.status_code, 200, done.text)
        return done.json()['token']

    async def test_an_owner_issues_the_first_pin_and_the_employee_replaces_it(self):
        self.assertEqual((await self.issue(self.member, '4821', token=self.manager('GM'))).status_code, 403)
        names = await self.portal.get('/api/pg/staff/berts/sign-in/names', params={'q': 'inv'})
        self.assertEqual({n['name'] for n in names.json()['names']}, {'Invented cook A', 'Invented cook B'})   # never other stores
        self.assertEqual((await self.portal.get('/api/pg/staff/berts/sign-in/names', params={'q': 'i'})).json()['names'], [])
        self.assertEqual((await self.sign_in(self.member, '4821')).status_code, 403)          # no PIN yet
        self.assertEqual((await self.issue(self.member, '4821')).status_code, 200)
        first = await self.sign_in(self.member, '4821')
        self.assertEqual((first.status_code, first.json()['detail']['code']), (409, 'pin_change_required'))
        self.assertEqual((await self.sign_in(self.member, '4821', '4821')).status_code, 422)
        done = await self.sign_in(self.member, '4821', '7350')
        self.assertEqual(done.status_code, 200, done.text)
        self.assertEqual(done.json()['name'], 'Invented cook A')
        self.assertEqual((await self.sign_in(self.member, '4821')).status_code, 401)          # the temporary PIN is gone
        self.assertEqual((await self.sign_in(self.member, '7350')).status_code, 200)
        # The session works on staff screens; the shared store PIN no longer does.
        plan = await self.staff_plan(member=self.member, pin='', token=done.json()['token'])
        self.assertEqual(plan.status_code, 200, plan.text)
        self.assertEqual((await self.staff_plan(member=self.member)).status_code, 403)
        self.assertEqual((await self.portal.post('/api/pg/staff/berts/verify', json={'pin': '4826'})).status_code, 410)
        async with self.pool.acquire() as c:
            hashes = await c.fetch('SELECT pin_hash FROM prep_inventory.staff_member_pins')
        for h in hashes:
            self.assertRegex(h['pin_hash'], r'^pbkdf2\$[A-Za-z0-9_-]+\$[0-9a-f]{64}$')

    async def test_five_wrong_pins_lock_the_person_until_a_manager_unlocks_them(self):
        await self.signed_in(self.member)
        for _ in range(4):
            self.assertEqual((await self.sign_in(self.member, '1111')).status_code, 401)
        self.assertEqual((await self.sign_in(self.member, '1111')).status_code, 423)
        self.assertEqual((await self.sign_in(self.member, '7350')).status_code, 423)          # even the right PIN waits
        self.assertEqual((await self.sign_in(self.other_member, '7350')).status_code, 403)    # others aren't locked (no PIN yet)
        readonly = server._token({'id': 'invented-readonly', 'email': 'ro@example.invalid', 'role': 'readonly', 'locations': ['berts']})
        self.assertEqual((await self.portal.get('/api/pg/staff/berts/members/sign-in', headers={'Authorization': 'Bearer ' + readonly})).status_code, 403)
        roster = (await self.portal.get('/api/pg/staff/berts/members/sign-in', headers={'Authorization': 'Bearer ' + self.manager('KM')})).json()['staff']
        self.assertTrue(next(s for s in roster if s['staff_member_id'] == str(self.member))['locked_until'])
        url = f'/api/pg/staff/berts/members/{self.member}/unlock'
        self.assertEqual((await self.portal.post(url, headers={'Authorization': 'Bearer ' + self.manager('SL-BOH')})).status_code, 403)
        self.assertEqual((await self.portal.post(url, headers={'Authorization': 'Bearer ' + self.manager('KM')})).status_code, 200)
        self.assertEqual((await self.sign_in(self.member, '7350')).status_code, 200)

    async def test_a_session_ends_on_sign_out_idle_new_pin_or_inactive(self):
        token = await self.signed_in(self.member)
        use = lambda t: self.staff_plan(member=self.member, pin='', token=t)
        self.assertEqual((await use(token)).status_code, 200)
        out = await self.portal.post('/api/pg/staff/berts/sign-out', headers={'Authorization': 'Bearer ' + token})
        self.assertEqual(out.status_code, 200)
        self.assertEqual((await use(token)).status_code, 401)
        token = (await self.sign_in(self.member, '7350')).json()['token']
        with patch.object(staff_login, 'IDLE_MINUTES', 0):
            self.assertEqual((await use(token)).status_code, 401)
        token = (await self.sign_in(self.member, '7350')).json()['token']
        self.assertEqual((await self.issue(self.member, '5096')).status_code, 200)          # a new PIN ends the session
        self.assertEqual((await use(token)).status_code, 401)
        token = (await self.sign_in(self.member, '5096', '6610')).json()['token']
        roster = lambda active: self.portal.put(f'/api/pg/staff/berts/members/{self.member}', headers={'Authorization': 'Bearer ' + self.owner},
                                                json={'name': 'Invented cook A', 'role': 'cook', 'active': active})
        self.assertEqual((await roster(False)).status_code, 200)
        self.assertEqual((await use(token)).status_code, 401)
        self.assertEqual((await self.sign_in(self.member, '6610')).status_code, 401)
        self.assertEqual((await roster(True)).status_code, 200)
        self.assertEqual((await use(token)).status_code, 401)        # reactivation needs a fresh sign-in
        self.assertEqual((await self.sign_in(self.member, '6610')).status_code, 200)

    async def test_a_session_is_for_one_store_and_never_a_manager(self):
        token = await self.signed_in(self.member)
        other = await self.portal.post('/api/pg/staff/rudds/prep-task-plan', headers={'Authorization': 'Bearer ' + token},
                                       json=dict(pin='', day='2026-10-08', track='daily', staff_member_id=str(self.foreign_member)))
        self.assertEqual(other.status_code, 403)
        self.assertEqual((await self.issue(self.other_member, '4821', token=token)).status_code, 403)
        for path in ('/api/pg/invoices/berts', '/api/pg/items/berts', '/api/pg/staff/berts/members'):
            self.assertEqual((await self.portal.get(path, headers={'Authorization': 'Bearer ' + token})).status_code, 403, path)
        self.assertEqual((await self.sign_in(self.foreign_member, '7350')).status_code, 401)   # Rudd's person at Bert's
        # The database keeps PINs and sign-in events as written.
        async with self.pool.acquire() as c, c.transaction():
            with self.assertRaises(asyncpg.PostgresError):
                await c.execute('UPDATE prep_inventory.staff_member_pins SET temporary=false')

    async def test_a_retried_pin_issue_replays(self):
        key = str(uuid4())
        self.assertEqual((await self.issue(self.member, '4821', key=key)).json()['replayed'], False)
        self.assertEqual((await self.issue(self.member, '4821', key=key)).json()['replayed'], True)
        self.assertEqual((await self.issue(self.member, '9999', key=key)).status_code, 409)       # same key, different PIN
        self.assertEqual((await self.issue(self.other_member, '4821', key=key)).status_code, 409)

    async def test_pins_can_be_issued_before_sign_in_is_switched_on(self):
        with patch.dict(os.environ, {'STAFF_PERSONAL_LOGIN_ENABLED': 'false'}):
            self.assertEqual((await self.issue(self.member, '4821')).status_code, 200)
            listed = await self.portal.get('/api/pg/staff/berts/members/sign-in', headers={'Authorization': 'Bearer ' + self.ops})
            self.assertEqual((listed.status_code, listed.json()['switched_on']), (200, False))
            self.assertEqual((await self.sign_in(self.member, '4821', '7350')).status_code, 503)
            self.assertEqual((await self.staff_plan(member=self.member)).status_code, 200)       # the store PIN still works
        self.assertEqual((await self.sign_in(self.member, '4821', '7350')).status_code, 200)
