"""Two real restricted LOGIN pools, invented loopback fixtures and HTTP routes."""
import os
import secrets
from types import SimpleNamespace
from unittest.mock import patch, Mock
from uuid import uuid4
from urllib.parse import urlsplit
import asyncpg
import server, db_pg, db_auxiliary, auxiliary_permissions
import hosted_staff_production as accounting
import test_runtime_login_workflows as logins
import test_runtime_planning_ai as planning


class AuxiliaryConnectionTests(logins.login_case('AuxiliaryFixture', planning.PlanningAITests, [])):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        try:
            await self.prepare_auxiliary()
        except BaseException:
            await self.asyncTearDown()
            raise

    async def prepare_auxiliary(self):
        self.aux_role = 'native_runtime_test_' + uuid4().hex
        self.aux_password = secrets.token_hex(32)
        await self.admin.execute('CREATE ROLE ' + self.aux_role + " LOGIN PASSWORD '" + self.aux_password +
            "' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT CONNECTION LIMIT 4")
        async def cleanup_role():
            conn = await asyncpg.connect(os.environ['NATIVE_PURCHASE_TEST_DSN'])
            try: await conn.execute('DROP ROLE ' + self.aux_role)
            finally: await conn.close()
        self.addAsyncCleanup(cleanup_role)
        source = os.environ['NATIVE_PURCHASE_TEST_DSN'].rsplit('/', 1)[0] + '/' + self.db
        owner = await asyncpg.connect(source)
        try:
            await owner.execute('GRANT USAGE ON SCHEMA public TO ' + self.aux_role)
            for table in auxiliary_permissions.TABLES:
                await owner.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON public.' + table + ' TO ' + self.aux_role)
                for verb in auxiliary_permissions.VERBS:
                    clauses = 'WITH CHECK (true)' if verb == 'INSERT' else 'USING (true) WITH CHECK (true)' if verb == 'UPDATE' else 'USING (true)'
                    await owner.execute('CREATE POLICY auxiliary_candidate_' + verb.lower() + ' ON public.' + table +
                                        ' FOR ' + verb + ' TO ' + self.aux_role + ' ' + clauses)
            await owner.execute("INSERT INTO staff_pins(store_id,pin) VALUES('berts','654321') ON CONFLICT(store_id) DO UPDATE SET pin=excluded.pin")
        finally: await owner.close()
        uri = urlsplit(source)
        def url(role, password):
            return 'postgresql://' + role + ':' + password + '@127.0.0.1:' + str(uri.port or 5432) + '/' + self.db
        self.connection_env = patch.dict(os.environ, {
            'DATABASE_URL': url(self.runtime_role, self.runtime_password),
            'AUXILIARY_DATABASE_URL': url(self.aux_role, self.aux_password)})
        self.connection_env.start(); self.addCleanup(self.connection_env.stop)
        self.addAsyncCleanup(db_auxiliary.close_pool)
        probe = await asyncpg.connect(os.environ['AUXILIARY_DATABASE_URL'])
        try:
            inspected = await auxiliary_permissions.inspect(probe)
            self.assertEqual(inspected['status'], 'passed', inspected['issues'])
        finally: await probe.close()
        await self.pool.close()
        self.pool = await db_pg.init_pool()
        self.assertIsNotNone(self.pool)
        self.assertIsNotNone(await db_auxiliary.init_pool())

    async def asyncTearDown(self):
        await db_auxiliary.close_pool()
        await db_pg.close_pool()
        await super().asyncTearDown()
        self.aux_password = None

    async def test_two_connections_account_push_and_accounting_boundaries(self):
        _, opening, closing = await self.pair()
        source, *_ = await self.capture()
        self.assertEqual((await self.post(source['documents'][0])).status_code, 200)
        report = (await self.report(opening, closing)).json()
        async with self.pool.acquire() as conn:
            await self.authenticated(conn)
            before = await accounting.accounting_fingerprints(conn, 'berts')
            with self.assertRaises(asyncpg.InsufficientPrivilegeError): await conn.fetchval('SELECT count(*) FROM app_users')
        async with db_auxiliary.pool().acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT session_user'), self.aux_role)
            self.assertEqual((await auxiliary_permissions.inspect(conn))['status'], 'passed')
            with self.assertRaises(asyncpg.InsufficientPrivilegeError): await conn.fetchval('SELECT count(*) FROM purchasing.posting_batches')
            with self.assertRaises(asyncpg.InsufficientPrivilegeError): await conn.fetchval('SELECT count(*) FROM staff_pins')
        with patch.object(server, 'BOOTSTRAP_TOKEN', 'synthetic-local-bootstrap-token'):
            result = await self.catalog.post('/api/auth/bootstrap', json={'bootstrapToken':'synthetic-local-bootstrap-token',
                'email':'owner@example.invalid','password':'invented-owner-password','role':'owner'})
        self.assertEqual(result.status_code, 200, result.text)
        owner_headers = {'Authorization':'Bearer ' + result.json()['token']}
        created = await self.catalog.post('/api/auth/users', headers=owner_headers, json={
            'email':'manager@example.invalid','password':'invented-manager-password','role':'manager','locations':['berts']})
        self.assertEqual(created.status_code, 200, created.text)
        user_id = created.json()['id']
        login = await self.catalog.post('/api/auth/login', json={'email':'manager@example.invalid','password':'invented-manager-password'})
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual((await self.catalog.get('/api/auth/users', headers=owner_headers)).status_code, 200)
        self.assertEqual((await self.catalog.put('/api/auth/users/' + user_id + '/password', headers=owner_headers,
            json={'password':'invented-new-manager-password'})).status_code, 200)
        self.assertEqual((await self.catalog.post('/api/auth/login', json={'email':'manager@example.invalid','password':'invented-manager-password'})).status_code, 401)
        self.assertEqual((await self.catalog.post('/api/auth/login', json={'email':'manager@example.invalid','password':'invented-new-manager-password'})).status_code, 200)
        body = {'endpoint':'https://invented.invalid/sub','keys':{'p256dh':'invented-key','auth':'invented-auth'}}
        for keys in (body['keys'], {'p256dh':'invented-replacement','auth':'invented-auth'}):
            response = await self.catalog.post('/api/pg/staff/berts/push/subscribe', headers=owner_headers, json={**body,'keys':keys})
            self.assertEqual(response.status_code, 200, response.text)
        class Stale(Exception): response = SimpleNamespace(status_code=410)
        with patch.object(server, 'PUSH_ENABLED', True), patch.object(server, 'WebPushException', Stale), patch.object(server, 'webpush', Mock(side_effect=Stale())) as send:
            await server._pg_notify_new_staff_task('berts', {'taskType':'prep','title':'Invented task','id':'invented-task'})
            send.assert_called_once()
        async with db_auxiliary.pool().acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM push_subscriptions'), 0)
        for pin, status in (('wrong-pin', 403), ('654321', 200)):
            response = await self.catalog.post('/api/pg/staff/berts/push/subscribe', headers={'Authorization':''}, json={**body,'pin':pin})
            self.assertEqual(response.status_code, status, response.text)
        response = await self.catalog.post('/api/pg/staff/berts/push/unsubscribe', headers={'Authorization':''}, json={'endpoint':body['endpoint'],'pin':'654321'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((await self.catalog.delete('/api/auth/users/' + user_id, headers=owner_headers)).status_code, 200)
        await db_auxiliary.close_pool()
        self.assertEqual((await self.catalog.post('/api/auth/login', json={'email':'owner@example.invalid','password':'invented-owner-password'})).status_code, 503)
        self.assertEqual((await self.catalog.get('/api/projections/berts')).status_code, 200)
        self.assertIsNotNone(await db_auxiliary.init_pool())
        self.assertEqual((await self.catalog.post('/api/auth/login', json={'email':'owner@example.invalid','password':'invented-owner-password'})).status_code, 200)
        self.assertEqual((await self.report(opening, closing)).json(), report)
        async with self.pool.acquire() as conn:
            self.assertEqual(await accounting.accounting_fingerprints(conn, 'berts'), before)

    async def test_auxiliary_inspector_holds_extra_table_column_schema_and_membership_grants(self):
        owner = await asyncpg.connect(os.environ['NATIVE_PURCHASE_TEST_DSN'].rsplit('/', 1)[0] + '/' + self.db)
        changes = [('GRANT SELECT ON purchasing.posting_batches TO ', 'REVOKE SELECT ON purchasing.posting_batches FROM '),
                   ('GRANT SELECT(name) ON public.items TO ', 'REVOKE SELECT(name) ON public.items FROM '),
                   ('GRANT USAGE ON SCHEMA purchasing TO ', 'REVOKE USAGE ON SCHEMA purchasing FROM '),
                   ('GRANT ' + self.runtime_role + ' TO ', 'REVOKE ' + self.runtime_role + ' FROM '),
                   ('GRANT SELECT ON public.app_users TO ', 'REVOKE GRANT OPTION FOR SELECT ON public.app_users FROM ')]
        try:
            for grant, revoke in changes:
                await owner.execute(grant + self.aux_role + (' WITH GRANT OPTION' if grant == changes[-1][0] else ''))
                try:
                    async with db_auxiliary.pool().acquire() as conn:
                        result = await auxiliary_permissions.inspect(conn)
                        self.assertEqual(result['status'], 'held', result)
                        self.assertFalse(result['operationalReleaseApproved'])
                finally: await owner.execute(revoke + self.aux_role)
            async with db_auxiliary.pool().acquire() as conn:
                self.assertEqual((await auxiliary_permissions.inspect(conn))['status'], 'passed')
        finally: await owner.close()
