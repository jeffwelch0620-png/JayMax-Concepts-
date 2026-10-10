"""Invented task archives; no text-to-roster inference or hosted changes."""
import os
from unittest.mock import patch, AsyncMock
import asyncpg
import server
import deployment_readiness as readiness
import runtime_permissions as candidate
import runtime_role_fixture as permissions
import hosted_staff_production as accounting
from test_runtime_manager_workflows import MenuHistoryFixture
from test_legacy_prep_cutover import LegacyPrepCutoverTests


class TaskHistoryFixture(MenuHistoryFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.tasks = []
        async with self.pool.acquire() as conn:
            # Preserve the inherited NULL-track history rather than inventing its
            # classification. Add a separate explicitly typed archive fixture.
            listing = await conn.fetchval("INSERT INTO prep_lists(store_id,prep_date,count_type,status) VALUES('berts','2026-10-02','nightly_prep','released') RETURNING id")
            await conn.execute("INSERT INTO prep_list_lines(list_id,recipe_id,name) VALUES($1,$2,'Invented typed historical list')", listing, self.retained['prep_list_lines'])
            for store, kind in [('berts', 'count'), ('berts', 'prep'), ('rudds', 'prep')]:
                row = await conn.fetchrow("""INSERT INTO staff_tasks
                    (store_id,task_type,title,due_date,recurrence,assigned_to)
                    VALUES($1,$2,'Invented historical task','2026-10-01','daily','Invented cook') RETURNING *""", store, kind)
                self.tasks.append(dict(row))


class RuntimeTaskCutoverTests(permissions.RuntimeRoleMixin, TaskHistoryFixture):
    async def test_task_cutover_owner_connection_cannot_restart_old_queue(self):
        _, opening, closing = await self.pair()
        source, *_ = await self.capture()
        self.assertEqual((await self.post(source['documents'][0])).status_code, 200)
        report = (await self.report(opening, closing)).json()
        async with self.pool.acquire() as conn:
            facts = await accounting.accounting_fingerprints(conn, 'berts')
        owner_pool = await asyncpg.create_pool(os.environ['NATIVE_PURCHASE_TEST_DSN'].rsplit('/', 1)[0] + '/' + self.db)
        original_headers = dict(self.catalog.headers)
        self.catalog.headers['Authorization'] = 'Bearer ' + server._token({'id':'invented-owner','email':'owner@example.invalid','role':'owner','locations':[]})
        try:
            with patch('db_pg.pool', lambda: owner_pool), patch.dict(os.environ, {flag + '_ENABLED': 'false' for flag in readiness.FEATURES}), patch('server._pg_notify_new_staff_task', new_callable=AsyncMock) as notify:
                for method, path, body, status in [
                    ('get', '/api/pg/staff-tasks/berts', None, 410),
                    ('post', '/api/pg/staff-tasks/berts', {'taskType':'prep','title':'Invented new task','dueDate':'2026-10-01'}, 409),
                    ('delete', '/api/pg/staff-tasks/berts/' + str(self.tasks[0]['id']), None, 409),
                    ('post', '/api/pg/staff/berts/tasks', {'pin':''}, 410),
                    ('post', '/api/pg/staff/berts/tasks/' + str(self.tasks[1]['id']) + '/complete', {'doneBy':'Invented cook'}, 409),
                ]:
                    result = await self.catalog.request(method, path, **({'json':body} if body is not None else {}))
                    self.assertEqual(result.status_code, status, result.text)
                notify.assert_not_called()
                async with owner_pool.acquire() as conn:
                    self.assertEqual([dict(r) for r in await conn.fetch('SELECT * FROM staff_tasks ORDER BY store_id,task_type')], sorted(self.tasks, key=lambda t: (t['store_id'], t['task_type'])))
                    self.assertEqual(await conn.fetchval('SELECT count(*) FROM prep_inventory.task_assignments'), 0)
                    self.assertEqual(await accounting.accounting_fingerprints(conn, 'berts'), facts)
        finally:
            self.catalog.headers = original_headers
            await owner_pool.close()
        self.assertEqual((await self.report(opening, closing)).json(), report)

    async def test_task_cutover_candidate_reads_labeled_store_scoped_archives(self):
        with patch.dict(os.environ, {flag + '_ENABLED': 'false' for flag in readiness.FEATURES}):
            for store, size in [('berts', 2), ('rudds', 1)]:
                self.assertEqual((await self.catalog.get('/api/pg/staff-tasks/' + store)).status_code, 410)
                result = await self.catalog.get('/api/pg/staff-tasks/' + store, params={'archive':'true'})
                self.assertEqual(result.status_code, 200, result.text)
                rows = result.json(); self.assertEqual(len(rows), size)
                for row in rows:
                    self.assertEqual(row['storeId'], store)
                    self.assertEqual(row['basis'], 'legacy_staff_task_archive')
                    self.assertEqual(row['identityBasis'], 'legacy_text')
                    self.assertTrue(row['archived']); self.assertFalse(row['operational'])
                    self.assertEqual(row['assignedTo'], 'Invented cook')
                    self.assertNotIn('staffId', row)
            for path in ('/api/pg/prepcount/berts/history', '/api/pg/prep-overrides/berts'):
                self.assertEqual((await self.catalog.get(path)).status_code, 410)
                result = await self.catalog.get(path, params={'archive':'true'})
                self.assertEqual(result.status_code, 200, result.text)
                self.assertTrue(result.json())
                self.assertTrue(all(row['archived'] and not row['operational'] for row in result.json()))
            listing = await self.catalog.get('/api/pg/preplists/berts', params={'date':'2026-10-02','archive':'true'})
            self.assertEqual(listing.status_code, 200, listing.text)
            self.assertEqual(listing.json()['basis'], 'legacy_prep_archive')
            self.assertTrue(listing.json()['archived']); self.assertFalse(listing.json()['operational'])
            self.assertEqual(listing.json()['list']['tasks'][0]['name'], 'Invented typed historical list')
            self.assertEqual((await self.catalog.get('/api/pg/preplists/berts')).status_code, 410)
            async with self.pool.acquire() as conn:
                self.assertIsNone(await conn.fetchval("SELECT count_type FROM prep_lists WHERE store_id='berts' AND prep_date='2026-10-01'"))
                self.assertEqual(await conn.fetchval('SELECT count(*) FROM prep_inventory.task_assignments'), 0)
                for table in ('staff_tasks', 'prep_lists'):
                    for verb in ('INSERT','UPDATE','DELETE'):
                        self.assertFalse(await conn.fetchval('SELECT has_table_privilege(current_user,$1,$2)', 'public.' + table, verb))
            for role, locations in [('manager',['rudds']), ('staff',['berts']), ('readonly',['berts'])]:
                token = server._token({'id':'invented-scoped-user','email':'scoped@example.invalid','role':role,'locations':locations})
                result = await self.catalog.get('/api/pg/staff-tasks/berts', params={'archive':'true'}, headers={'Authorization':'Bearer ' + token})
                self.assertEqual(result.status_code, 403, result.text)
            async with self.pool.acquire() as conn:
                pin = await server._pg_get_staff_pin(conn, 'berts')
            for provided, status in [(pin,410), ('invalid-synthetic-pin',403)]:
                result = await self.catalog.post('/api/pg/staff/berts/tasks', json={'pin':provided}, headers={'Authorization':''})
                self.assertEqual(result.status_code, status, result.text)

    async def test_task_cutover_prep_insert_denied_update_guard_and_share_lock_retained(self):
        async with self.pool.acquire() as conn:
            with self.assertRaises(asyncpg.InsufficientPrivilegeError):
                await conn.execute("INSERT INTO prep_items(store_id,name) VALUES('berts','Invented denied')")
            with self.assertRaises(asyncpg.RaiseError):
                await conn.execute("UPDATE prep_items SET name='Invented forbidden rewrite' WHERE store_id='berts'")
            async with conn.transaction():
                await conn.execute('LOCK TABLE public.prep_items IN SHARE MODE')
            self.assertEqual(candidate.PUBLIC['prep_items'], ('SELECT', 'UPDATE'))


class LegacyTaskCompatibilityTests(LegacyPrepCutoverTests):
    async def test_task_cutover_preinstallation_compatibility_and_requested_hold(self):
        with patch.dict(os.environ, {'ACTUAL_INVENTORY_ENABLED':'false', 'STAFF_PREP_TASKS_ENABLED':'false'}), patch('server._pg_notify_new_staff_task', new_callable=AsyncMock):
            created = await self.web.post('/api/pg/staff-tasks/berts', json={'taskType':'count','title':'Invented recurring count','dueDate':'2026-01-01','recurrence':'daily'})
            self.assertEqual(created.status_code, 200, created.text)
            identity = created.json()['id']
            self.assertEqual(len((await self.web.get('/api/pg/staff-tasks/berts')).json()), 1)
            self.assertEqual(len((await self.web.post('/api/pg/staff/berts/tasks', json={'pin':''})).json()['tasks']), 1)
            done = await self.web.post('/api/pg/staff/berts/tasks/' + identity + '/complete', json={'doneBy':'Invented cook'})
            self.assertEqual(done.status_code, 200, done.text)
            self.assertEqual(len((await self.web.get('/api/pg/staff-tasks/berts')).json()), 2)
            self.assertEqual((await self.web.delete('/api/pg/staff-tasks/berts/' + identity)).status_code, 200)
            for flag in ('ACTUAL_INVENTORY_ENABLED', 'STAFF_PREP_TASKS_ENABLED'):
                with patch.dict(os.environ, {flag:'true'}):
                    self.assertEqual((await self.web.get('/api/pg/staff-tasks/berts')).status_code, 410)
                    self.assertEqual((await self.web.post('/api/pg/staff-tasks/berts', json={'taskType':'prep','title':'Held','dueDate':'2026-01-01'})).status_code, 409)
