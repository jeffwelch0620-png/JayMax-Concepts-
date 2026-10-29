"""Salad Bar prep track: Bert's only, enforced by the API and the database."""
import os
import unittest
from typing import get_args

import asyncpg
from fastapi import HTTPException

import deployment_readiness as readiness
import prep_tracks
import test_prep_planning as planning_tests

MIGRATION = 'migrations/20261029_salad_prep_track.sql'


class SaladTrackRuleTests(unittest.TestCase):
    def test_salad_is_a_track_and_allowed_only_at_berts(self):
        self.assertEqual(get_args(prep_tracks.Track), ('daily', 'bulk', 'salad'))
        for store in ('berts', 'rudds', 'papa', 'comm'):
            for track in ('daily', 'bulk'):
                self.assertEqual(prep_tracks.check(store, track), track)
        self.assertEqual(prep_tracks.check('berts', 'salad'), 'salad')
        for store in ('rudds', 'papa', 'comm', 'papa_leonis'):
            with self.subTest(store=store), self.assertRaises(HTTPException) as held:
                prep_tracks.check(store, 'salad')
            self.assertEqual(held.exception.status_code, 422)

    def test_migration_is_registered_last_and_matches_the_rule(self):
        self.assertEqual(readiness.MIGRATIONS[-1], '20261029_salad_prep_track.sql')
        text = (readiness.ROOT / MIGRATION).read_text(encoding='utf-8')
        for name in ('planning_versions_salad_store_check', 'day_lists_salad_store_check', 'handoff_notes_salad_store_check'):
            self.assertIn(name, text)
        self.assertEqual(text.count("store_id = 'berts'"), 3)


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class SaladTrackDatabaseTests(planning_tests.PrepPlanningTests):
    # Reuse the planning fixture without re-running its own tests here.
    for _name in [n for n in dir(planning_tests.PrepPlanningTests) if n.startswith('test_')]:
        locals()[_name] = None
    del _name

    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with self.pool.acquire() as c:
            await c.execute((readiness.ROOT / MIGRATION).read_text(encoding='utf-8'))

    async def test_salad_plan_saves_at_berts_and_is_refused_elsewhere(self):
        saved = await self.edit(self.payload(track='salad'))
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()['plan']['track'], 'salad')
        self.assertEqual([p['track'] for p in (await self.read())['plans']], ['salad'])
        refused = await self.edit(self.payload(track='salad'), store='comm', client=self.other)
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("only at Bert's", refused.text)

    async def test_database_refuses_salad_outside_berts_even_without_the_api(self):
        saved = await self.edit()  # an ordinary Bulk plan at Bert's to copy
        self.assertEqual(saved.status_code, 200, saved.text)
        copy = """INSERT INTO prep_inventory.planning_versions SELECT (jsonb_populate_record(
            NULL::prep_inventory.planning_versions, to_jsonb(p) || jsonb_build_object(
            'id', gen_random_uuid(), 'predecessor_id', NULL, 'store_id', $1::text, 'track', 'salad'))).*
            FROM prep_inventory.planning_versions p LIMIT 1"""
        async with self.pool.acquire() as c:
            # Bypass the app entirely: triggers (and foreign keys) off, CHECK constraints still apply.
            async with c.transaction():
                await c.execute('SET LOCAL session_replication_role = replica')
                with self.assertRaises(asyncpg.CheckViolationError) as held:
                    await c.execute(copy, 'rudds')
                self.assertIn('planning_versions_salad_store_check', str(held.exception))
