"""Staff count sheets that follow the store's walk order: per-location quantities from staff,
totalled by the server and carried into the accepted Track 1 count."""
import os
import unittest
from decimal import Decimal
from uuid import uuid4

import staff_count_drafts as drafts
import test_staff_count_drafts as staff

MIGRATION = 'migrations/20261029_count_walk_order.sql'


class SheetLayoutTests(unittest.TestCase):
    def test_sheet_keeps_walk_order_and_only_issued_items(self):
        layout = {'header': {'id': 'L1', 'revision': 2}, 'locations': [
            {'location_code': 'walk-in', 'name': 'Walk-in', 'items': ['a', 'gone']},
            {'location_code': 'dry', 'name': 'Dry', 'items': ['a']}]}
        self.assertEqual(drafts.sheet_layout(layout, {'a'}), {'id': 'L1', 'revision': 2, 'locations': [
            {'location_code': 'walk-in', 'name': 'Walk-in', 'items': ['a']},
            {'location_code': 'dry', 'name': 'Dry', 'items': ['a']}]})
        self.assertIsNone(drafts.sheet_layout(None, {'a'}))

    def test_sheets_without_a_walk_order_keep_their_request_fingerprint(self):
        body = drafts.SubmitInput(pin='1', expected_review_hash='a' * 64, counter_name='C', note='N',
                                  lines=[{'item_code': 'a', 'counted_quantity': '1'}])
        self.assertEqual(drafts.submit_payload(body), {'expected_review_hash': 'a' * 64, 'counter_name': 'C', 'note': 'N',
                                                       'lines': [{'item_code': 'a', 'counted_quantity': '1', 'note': ''}]})


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class StaffWalkOrderTests(staff.StaffCountDraftTests):
    # Reuse the staff count fixture without re-running its own tests here.
    for _name in [n for n in dir(staff.StaffCountDraftTests) if n.startswith('test_')]:
        locals()[_name] = None
    del _name

    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with self.pool.acquire() as conn:
            await conn.execute((staff.fixtures.recovery.counts.native.ROOT / MIGRATION).read_text(encoding='utf-8'))

    async def walk_order(self):
        body = {'scope_id': self.scope_record['header']['id'], 'note': 'Invented walk order',
                'locations': [{'name': 'Walk-in cooler', 'items': ['test_food']}, {'name': 'Dry storage', 'items': ['test_food']}]}
        saved = await self.real.post('/api/pg/actual-inventory/berts/layout', json=body, headers={'Idempotency-Key': str(uuid4())})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.layout = saved.json()

    def walked(self, cooler, dry):
        return [{'item_code': 'test_food', 'counted_quantity': None, 'note': 'Counted in walk order',
                 'locations': [{'location_code': 'walk-in-cooler', 'counted_quantity': cooler},
                               {'location_code': 'dry-storage', 'counted_quantity': dry}]}]

    async def test_sheet_follows_walk_order_and_acceptance_keeps_location_quantities(self):
        await self.walk_order()
        issued, _ = await self.issue(); self.assertEqual(issued.status_code, 200, issued.text)
        layout = issued.json()['sheet']['sheet_snapshot']['layout']
        self.assertEqual(layout['id'], self.layout['header']['id'])
        self.assertEqual([l['name'] for l in layout['locations']], ['Walk-in cooler', 'Dry storage'])
        saved, _ = await self.submit(issued.json(), lines=self.walked('1', '2'))
        self.assertEqual(saved.status_code, 200, saved.text)
        line = saved.json()['submission']['quantities'][0]
        self.assertEqual(line['counted_quantity'], '3')
        self.assertEqual([q['counted_quantity'] for q in line['locations']], ['1', '2'])
        result, _ = await self.decision(saved.json()['review'])
        self.assertEqual(result.status_code, 200, result.text)
        count = result.json()['count']
        self.assertEqual(count['header']['layout_id'], self.layout['header']['id'])
        self.assertEqual(count['lines'][0]['base_quantity'], '60')
        self.assertEqual({q['location_code']: Decimal(q['counted_quantity']) for q in count['lines'][0]['locations']},
                         {'walk-in-cooler': Decimal(1), 'dry-storage': Decimal(2)})

    async def test_blank_location_is_incomplete_and_wrong_shapes_are_refused(self):
        await self.walk_order()
        issued, _ = await self.issue(); review = issued.json()
        partial, _ = await self.submit(review, lines=self.walked('1', None))
        self.assertEqual(partial.status_code, 200, partial.text)
        self.assertIsNone(partial.json()['submission']['quantities'][0]['counted_quantity'])
        blocked, _ = await self.decision(partial.json()['review'])
        self.assertEqual(blocked.status_code, 422, blocked.text)
        review = partial.json()['review']
        totals_only, _ = await self.submit(review)
        self.assertEqual(totals_only.status_code, 422, totals_only.text)
        missing = self.walked('1', '2'); missing[0]['locations'].pop()
        self.assertEqual((await self.submit(review, lines=missing))[0].status_code, 422)
        both = self.walked('1', '2'); both[0]['counted_quantity'] = '3'
        self.assertEqual((await self.submit(review, lines=both))[0].status_code, 422)

    async def test_sheet_issued_before_a_walk_order_stays_totals_only(self):
        issued, _ = await self.issue(); self.assertNotIn('layout', issued.json()['sheet']['sheet_snapshot'])
        await self.walk_order()  # A walk order saved later does not change an issued sheet.
        issued = await self.current(); self.assertNotIn('layout', issued['sheet']['sheet_snapshot'])
        self.assertEqual((await self.submit(issued, lines=self.walked('1', '2')))[0].status_code, 422)
        saved, _ = await self.submit(issued); self.assertEqual(saved.status_code, 200, saved.text)
        result, _ = await self.decision(saved.json()['review']); self.assertEqual(result.status_code, 200, result.text)
        self.assertIsNone(result.json()['count']['header']['layout_id'])
