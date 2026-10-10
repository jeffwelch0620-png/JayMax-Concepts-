"""Synthetic legacy/native cutover on isolated PostgreSQL, flags off included."""
import os
import unittest
from unittest.mock import patch
from uuid import uuid4
import httpx
import server
import legacy_prep_views as views
import test_native_order_receiving as fixtures


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PG required')
class LegacyPrepCutoverTests(unittest.IsolatedAsyncioTestCase):
    asyncTearDown = fixtures.NativeOrderReceivingTests.asyncTearDown

    async def asyncSetUp(self):
        await fixtures.NativeOrderReceivingTests.asyncSetUp(self)
        for target, value in [('server.USE_PG', True), ('db_pg.pool', lambda: self.pool)]:
            current = patch(target, value); current.start(); self.addCleanup(current.stop)
        current = patch.dict(os.environ, {flag: 'false' for flag in
            ('PREP_BATCHES_ENABLED', 'PREP_CONTAINERS_ENABLED', 'PREP_OBSERVATIONS_ENABLED',
             'STAFF_PREP_COUNTS_ENABLED', 'PREP_PLANNING_ENABLED', 'PREP_DAY_TASKS_ENABLED')})
        current.start(); self.addCleanup(current.stop)
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO stores(id,name) VALUES('papa','Invented Papa')")
            self.dish = await conn.fetchval("INSERT INTO dishes(store_id,name,recipe_type,yield_qty,yield_uom,prep_par) VALUES('berts','Invented retained sauce','prep',4,'lb',15) RETURNING id")
            await conn.execute("INSERT INTO prep_recipe_stock(store_id,dish_id,on_hand,containers) VALUES('berts',$1,12,'[]')", self.dish)
        token = server._token({'id': 'invented-owner', 'email': 'owner@example.invalid', 'role': 'owner', 'locations': []})
        self.web = httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url='http://test', headers={'Authorization': 'Bearer ' + token})
        self.addAsyncCleanup(self.web.aclose)

    async def install(self):
        async with self.pool.acquire() as conn:
            for name in ('20261005_prep_mapping_foundation.sql', '20261005_prep_batch_events.sql'):
                await conn.execute((fixtures.recovery.counts.native.ROOT / 'migrations' / name).read_text())

    async def test_old_reads_work_before_cutover_then_flags_off_schema_holds_current_figures(self):
        old = await self.web.get('/api/pg/prep/berts/state')
        self.assertEqual(old.status_code, 200, old.text)
        self.assertEqual(old.json()['prepStock'][0]['onHand'], 12)
        self.assertTrue(old.json()['prepReadStatus']['available'])
        self.assertEqual((await self.web.get('/api/reports/berts/prep')).status_code, 200)
        await self.install()
        held = await self.web.get('/api/pg/prep/berts/state')
        self.assertEqual(held.status_code, 200, held.text)
        self.assertIsNone(held.json()['prepStock']); self.assertIsNone(held.json()['prepLogs'])
        self.assertFalse(held.json()['prepReadStatus']['available'])
        self.assertEqual((await self.web.get('/api/reports/berts/prep')).status_code, 410)
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT on_hand FROM prep_recipe_stock WHERE dish_id=$1', self.dish), 12)

    async def test_flags_off_writers_cannot_restart_parallel_stock_after_batch_schema(self):
        await self.install()
        for path, body in [('/api/pg/prep/berts/complete', {'recipeId': str(self.dish), 'batches': 1}),
                           ('/api/pg/prep/berts/apply-sales', {'dishSales': {}}),
                           ('/api/pg/prep/berts/use-container', {'recipeId': str(self.dish), 'containerId': 'invented'})]:
            result = await self.web.post(path, json=body)
            self.assertEqual(result.status_code, 409, result.text)
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT on_hand FROM prep_recipe_stock WHERE dish_id=$1', self.dish), 12)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM prep_logs'), 0)
            self.assertEqual(await conn.fetchval("SELECT current_stock FROM store_items WHERE store_id='berts' AND item_code='test_food'"), 0)

    async def test_owner_and_ai_do_not_reinterpret_retained_stock_or_empty_history_as_current(self):
        await self.install()
        summary = await self.web.get('/api/owner/prep-summary')
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertFalse(summary.json()['available'])
        for row in summary.json()['stores']:
            self.assertIsNone(row['tasksTotal']); self.assertIsNone(row['tasksDone']); self.assertIsNone(row['prepCost7d'])
        owner = await self.web.get('/api/owner/summary')
        self.assertEqual(owner.status_code, 200, owner.text)
        self.assertIsNone(next(row for row in owner.json()['stores'] if row['id'] == 'berts')['prepLow'])
        with patch('server._ai') as ai:
            self.assertEqual((await self.web.post('/api/ai/par-advisor/berts')).status_code, 410)
            self.assertEqual((await self.web.post(f'/api/ai/par-advisor/berts/{uuid4()}/apply')).status_code, 410)
            ai.assert_not_called()
        context = server.build_ai_context('berts', [], [], [{'id': 'invented', 'name': 'Sauce', 'recipeType': 'prep'}], [], None,
            {'count': None, 'countStatus': 'count_missing', 'scope': None, 'inventoryValue': None, 'netFoodPurchases30': '0', 'receivedFrom': '2026-10-01', 'receivedBefore': '2026-10-08'})
        self.assertIn('legacy prep on-hand is unavailable', context)
        self.assertNotIn('on-hand 0', context)

    async def test_requested_cutover_holds_reads_even_before_schema_and_planning_only_holds_reports(self):
        async with self.pool.acquire() as conn:
            with patch.dict(os.environ, {'PREP_BATCHES_ENABLED': 'true'}):
                self.assertTrue(await views.stock_retired(conn))
                self.assertTrue(await views.reporting_retired(conn))
            with patch.dict(os.environ, {'PREP_PLANNING_ENABLED': 'true'}):
                self.assertFalse(await views.stock_retired(conn))
                self.assertTrue(await views.reporting_retired(conn))
            self.assertFalse(await views.reporting_retired(conn))

    async def test_retired_count_list_and_override_reads_require_labeled_archive_and_do_not_create_sessions(self):
        async with self.pool.acquire() as conn:
            for kind in ('nightly_prep', 'commissary', 'full_inventory'):
                await conn.execute("INSERT INTO count_sessions(store_id,count_date,count_type) VALUES('berts','2026-10-08',$1)", kind)
            daily = await conn.fetchval("INSERT INTO prep_lists(store_id,prep_date,count_type) VALUES('berts','2026-10-08','nightly_prep') RETURNING id")
            bulk = await conn.fetchval("INSERT INTO prep_lists(store_id,prep_date,count_type) VALUES('berts','2026-10-09','commissary') RETURNING id")
            await conn.execute("INSERT INTO prep_overrides(store_id,date,type,custom_name) VALUES('berts','2026-10-08','add','Retained catering task')")
        await self.install()
        async with self.pool.acquire() as conn:
            for name in ('20261005_prep_observations.sql', '20261007_prep_planning.sql', '20261007_prep_day_tasks.sql', '20261007_staff_prep_counts.sql'):
                await conn.execute((fixtures.recovery.counts.native.ROOT/'migrations'/name).read_text())
        for path in ('/api/pg/prepcount/berts/history', '/api/pg/preplists/berts', '/api/pg/prep-overrides/berts'):
            self.assertEqual((await self.web.get(path)).status_code, 410)
        self.assertEqual((await self.web.get('/api/pg/prepcount/berts/session', params={'date':'2026-10-09'})).status_code, 409)
        self.assertEqual((await self.web.get('/api/pg/prepcount/berts/session', params={'date':'2026-10-09','track':'wrong'})).status_code, 422)
        history = (await self.web.get('/api/pg/prepcount/berts/history', params={'archive':'true'})).json()
        self.assertEqual({r['track'] for r in history}, {'daily','bulk'}); self.assertEqual(len(history),2)
        self.assertTrue(all(r['archived'] and not r['operational'] for r in history))
        for track, ident, day in (('daily',daily,'2026-10-08'), ('bulk',bulk,'2026-10-09')):
            response=await self.web.get('/api/pg/preplists/berts',params={'archive':'true','date':day,'track':track})
            self.assertEqual(response.status_code,200,response.text); self.assertEqual(response.json()['list']['id'],str(ident))
            self.assertTrue(response.json()['archived']); self.assertFalse(response.json()['operational'])
        self.assertIsNone((await self.web.get('/api/pg/preplists/berts',params={'archive':'true','date':'2026-10-08','track':'bulk'})).json()['list'])
        self.assertEqual((await self.web.get('/api/pg/preplists/berts',params={'archive':'true','track':'wrong'})).status_code,422)
        self.assertFalse((await self.web.get('/api/pg/prep-overrides/berts',params={'archive':'true'})).json()[0]['operational'])
        state=(await self.web.get('/api/pg/prep/berts/state')).json()
        self.assertEqual(state['prepCapabilities'],dict(countsAvailable=False,listsAvailable=False,reportingAvailable=False))
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM count_sessions'),3)
        foreign=server._token({'id':'invented-manager','email':'manager@example.invalid','role':'manager','locations':['rudds']})
        self.assertEqual((await self.web.get('/api/pg/prepcount/berts/history',params={'archive':'true'},headers={'Authorization':'Bearer '+foreign})).status_code,403)
