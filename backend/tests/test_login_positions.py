"""Login positions (Jeff 2026-10-30): a position sets the access class and travels in the session."""
import os
import unittest
from unittest.mock import patch

import asyncpg

import server
import test_catalog_integrity as catalog
import test_native_backup as recovery

MIGRATION = 'migrations/20261031_login_positions.sql'


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class LoginPositionTests(catalog.CatalogIntegrityTests):
    # Reuse the catalog fixture (app, pool, owner client) without re-running its own tests here.
    for _name in [n for n in dir(catalog.CatalogIntegrityTests) if n.startswith('test_')]:
        locals()[_name] = None
    del _name

    async def asyncSetUp(self):
        await super().asyncSetUp()
        env = patch.dict(os.environ, {}, clear=False); env.start(); self.addCleanup(env.stop)
        os.environ.pop('AUXILIARY_DATABASE_URL', None)  # logins live in the same test database
        async with self.pool.acquire() as c:
            await c.execute((recovery.counts.native.ROOT / MIGRATION).read_text(encoding='utf-8'))

    async def test_a_position_sets_the_access_class_and_reaches_the_session(self):
        made = await self.owner_client.post('/api/auth/users', json={'email': 'km@example.invalid', 'password': 'invented-km-password',
                                                                     'role': 'readonly', 'position': 'KM', 'locations': ['berts']})
        self.assertEqual(made.status_code, 200, made.text)
        self.assertEqual((made.json()['role'], made.json()['position'], made.json()['locations']), ('manager', 'KM', ['berts']))
        login = await self.catalog.post('/api/auth/login', json={'email': 'km@example.invalid', 'password': 'invented-km-password'})
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(server._decode_token(login.json()['token'])['position'], 'KM')
        # The Ops Lead (an owner) moves them to Bulk Prep Manager across both stores.
        moved = await self.owner_client.put(f"/api/auth/users/{made.json()['id']}/access", json={'position': 'BPM', 'locations': ['berts', 'rudds']})
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertEqual((moved.json()['position'], moved.json()['locations']), ('BPM', ['berts', 'rudds']))
        listed = (await self.owner_client.get('/api/auth/users')).json()
        self.assertEqual([u['position'] for u in listed if u['email'] == 'km@example.invalid'], ['BPM'])
        # Only owners manage logins; unknown positions and store-less managers are refused.
        self.assertEqual((await self.catalog.put(f"/api/auth/users/{made.json()['id']}/access", json={'position': 'GM', 'locations': ['berts']})).status_code, 403)
        for body in ({'position': 'CHEF', 'locations': ['berts']}, {'position': 'GM', 'locations': []}):
            self.assertEqual((await self.owner_client.put(f"/api/auth/users/{made.json()['id']}/access", json=body)).status_code, 400)

    async def test_database_keeps_position_and_access_class_together(self):
        async with self.pool.acquire() as c:
            with self.assertRaises(asyncpg.CheckViolationError):
                await c.execute("INSERT INTO app_users(id,email,password_hash,role,locations,position) VALUES('usr_x','x@example.invalid','x','manager','{berts}','OPS')")
            await c.execute("INSERT INTO app_users(id,email,password_hash,role,locations) VALUES('usr_y','y@example.invalid','y','manager','{berts}')")
            self.assertIsNone(await c.fetchval("SELECT position FROM app_users WHERE id='usr_y'"))
