"""Draft 0.7 daily/salad prep: N = max(0, T - H - I), rounded up to whole recipe batches."""
import unittest
from decimal import Decimal as D
from uuid import UUID, uuid4

import asyncpg

import prep_day_tasks as tasks


class BatchPlanTests(unittest.TestCase):
    def plan(self, target, carryover, incoming, batch):
        return tasks.batch_plan(D(target), D(carryover), D(incoming), D(batch))

    def test_need_rounds_up_to_whole_batches(self):
        # Target 10 quarter pans of 48 oz, 3 counted, batch makes 4 pans (192 oz): need 336 oz -> 2 batches.
        self.assertEqual(self.plan('480', '144', '0', '192'), {'need': D('336'), 'batches': D('2'), 'planned_base': D('384')})

    def test_exact_multiple_needs_no_extra_batch(self):
        self.assertEqual(self.plan('400', '0', '0', '200')['batches'], D('2'))

    def test_enough_on_hand_or_incoming_means_no_prep(self):
        self.assertEqual(self.plan('100', '120', '0', '50'), {'need': D('0'), 'batches': D('0'), 'planned_base': D('0')})
        self.assertEqual(self.plan('100', '40', '60', '50')['batches'], D('0'))

    def test_incoming_supply_reduces_need_before_rounding(self):
        self.assertEqual(self.plan('100', '20', '30', '40'), {'need': D('50'), 'batches': D('2'), 'planned_base': D('80')})

    def test_tiny_shortfall_still_makes_a_whole_batch(self):
        self.assertEqual(self.plan('100.000000000001', '100', '0', '25')['batches'], D('1'))


import os
import test_prep_day_tasks as day

MIGRATION = 'migrations/20261029_prep_batch_rounding.sql'


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class BatchPlanDatabaseTests(day.PrepDayTaskTests):
    # Reuse the dated-draft fixture without re-running its own tests here.
    for _name in [n for n in dir(day.PrepDayTaskTests) if n.startswith('test_')]:
        locals()[_name] = None
    del _name

    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with self.pool.acquire() as c:
            await c.execute((day.recovery.counts.native.ROOT / MIGRATION).read_text(encoding='utf-8'))

    async def test_saved_plan_is_the_fewest_whole_batches_covering_the_deficit(self):
        count = await self.prep_count('2')
        saved = await self.write_day(self.draft_body(count_event_id=count['id']))
        self.assertEqual(saved.status_code, 200, saved.text)
        t = saved.json()['draft']['review_snapshot']['tasks'][0]
        need, batch, planned = D(t['needed_base_quantity']), D(t['batch_base_yield']), D(t['planned_base_quantity'])
        self.assertEqual(planned, D(t['batches']) * batch)
        self.assertGreaterEqual(planned, need)
        self.assertLess(planned - batch, need)

    async def test_database_refuses_an_unrounded_or_oversized_plan(self):
        count = await self.prep_count('2')
        p = await self.preview_day(self.draft_body(count_event_id=count['id']))
        self.assertEqual(p.status_code, 200, p.text)
        review = p.json()['review']
        task = review['tasks'][0]
        batch = D(task['batch_base_yield'])
        for forged_batches in (D(task['batches']) + 1, D(task['batches']) - D('0.5')):
            forged = dict(task, batches=str(forged_batches), planned_base_quantity=str(forged_batches * batch),
                          planned_quantity=str(forged_batches * batch / D(task['factor'])))
            async with self.pool.acquire() as c:
                with self.assertRaisesRegex(asyncpg.PostgresError, 'fewest whole recipe batches'):
                    async with c.transaction():
                        list_id = await c.fetchval("INSERT INTO prep_inventory.day_lists(store_id,prep_date,track) VALUES('berts','2026-10-08','daily') "
                                                   "ON CONFLICT(store_id,prep_date,track) DO UPDATE SET track=EXCLUDED.track RETURNING id")
                        snapshot = dict(review, tasks=[forged])
                        version = await c.fetchval('''INSERT INTO prep_inventory.day_list_versions(list_id,store_id,revision,count_event_id,day_group,note,actor,
                            review_snapshot,review_hash,request_key,request_fingerprint) VALUES($1,'berts',1,$2,'weekday','Forged','tester',$3,$4,$5,$4) RETURNING id''',
                            list_id, UUID(count['id']), snapshot, b'\x00' * 32, uuid4())
                        await c.execute('''INSERT INTO prep_inventory.day_tasks(version_id,store_id,ordinal,product_id,planning_version_id,recipe_version_id,
                            unit_profile_id,included,planned_quantity,factor,planned_base_quantity,task_snapshot) VALUES($1,'berts',1,$2,$3,$4,$5,true,$6,$7,$8,$9)''',
                            version, UUID(forged['product_id']), UUID(forged['planning_version_id']), UUID(forged['recipe_version_id']),
                            UUID(forged['unit_profile_id']), D(forged['planned_quantity']), D(forged['factor']), D(forged['planned_base_quantity']), forged)
