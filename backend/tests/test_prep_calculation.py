"""Draft 0.7 daily/salad prep: N = max(0, T - H - I), rounded up to whole recipe batches."""
import unittest
from decimal import Decimal as D

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
