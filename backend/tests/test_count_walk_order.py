"""Walk-order count layouts: per-location quantities that add up to the Track 1 count line."""
import os
import unittest
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg

import actual_inventory_api as actual
import test_actual_inventory as counts

MIGRATION = 'migrations/20261029_count_walk_order.sql'


class LayoutModelTests(unittest.TestCase):
    def test_location_codes_are_stable_slugs(self):
        self.assertEqual(actual.location_code('Walk-in Cooler'), 'walk-in-cooler')
        self.assertEqual(actual.location_code('  Dry storage #2 '), 'dry-storage-2')
        with self.assertRaises(Exception):
            actual.location_code('---')

    def test_counts_without_a_layout_keep_their_request_hash(self):
        body = dict(scope_id=str(uuid4()), count_date='2026-10-25', timing='before_receipts', note='Synthetic',
                    lines=[dict(item_code='a', counted_quantity='1', counted_unit='case', base_units_per_counted_unit='2',
                                inventory_value='3', confirmed=True, note='n')])
        payload = actual.serial(actual.CountInput(**body).model_dump())
        payload.pop('layout_id')
        for line in payload['lines']:
            line.pop('locations')
        self.assertEqual(actual.request_hash(actual.CountInput(**body), 'lines'), actual.fingerprint(
            payload | {'lines': sorted(payload['lines'], key=lambda r: r['item_code'])}))


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PG DSN required')
class CountWalkOrderTests(counts.ActualInventoryTests):
    # Reuse the Track 1 fixture without re-running its own tests here.
    for _name in [n for n in dir(counts.ActualInventoryTests) if n.startswith('test_')]:
        locals()[_name] = None
    del _name

    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with self.pool.acquire() as conn:
            await conn.execute((counts.native.ROOT / MIGRATION).read_text(encoding='utf-8'))
        result, _ = await self.scope(('other_food', 'test_food'))
        self.assertEqual(result.status_code, 200, result.text)
        self.current = (await self.client.get('/api/pg/actual-inventory/berts/setup')).json()['scope']

    async def save_layout(self, locations, key=None):
        body = {'scope_id': self.current['header']['id'], 'note': 'Synthetic walk order', 'locations': locations}
        return await self.client.post('/api/pg/actual-inventory/berts/layout', json=body,
                                      headers={'Idempotency-Key': key or str(uuid4())})

    async def walk_layout(self):
        saved = await self.save_layout([{'name': 'Walk-in cooler', 'items': ['test_food', 'other_food']},
                                        {'name': 'Dry storage', 'items': ['test_food']}])
        self.assertEqual(saved.status_code, 200, saved.text)
        return saved.json()

    def line(self, code, locations, value=None, confirmed=False):
        return {'item_code': code, 'counted_quantity': None, 'counted_unit': 'case', 'base_units_per_counted_unit': '20',
                'inventory_value': value, 'confirmed': confirmed, 'note': 'Synthetic per-location count' if confirmed else '',
                'locations': [{'location_code': c, 'counted_quantity': q} for c, q in locations]}

    async def save_count(self, layout, lines, **extra):
        body = {'scope_id': self.current['header']['id'], 'count_date': '2026-10-25', 'timing': 'before_receipts',
                'note': 'Synthetic walk-order count', 'layout_id': layout['header']['id'], 'lines': lines, **extra}
        return await self.client.post('/api/pg/actual-inventory/berts/counts', json=body,
                                      headers={'Idempotency-Key': str(uuid4())})

    async def test_layout_follows_walk_order_and_places_every_item(self):
        setup = (await self.client.get('/api/pg/actual-inventory/berts/setup')).json()
        self.assertIsNone(setup['layout'])
        proposed = {c for l in setup['proposedLayout']['locations'] for c in l['items']}
        self.assertEqual(proposed, {'other_food', 'test_food'})
        missing = await self.save_layout([{'name': 'Walk-in cooler', 'items': ['test_food']}])
        self.assertEqual(missing.status_code, 422, missing.text)
        foreign = await self.save_layout([{'name': 'Walk-in cooler', 'items': ['test_food', 'other_food', 'prep_sauce']}])
        self.assertEqual(foreign.status_code, 422, foreign.text)
        same_name = await self.save_layout([{'name': 'Shelf', 'items': ['test_food']}, {'name': 'shelf', 'items': ['other_food']}])
        self.assertEqual(same_name.status_code, 422, same_name.text)
        layout = await self.walk_layout()
        self.assertEqual([(l['location_code'], l['walk_position'], l['items']) for l in layout['locations']],
                         [('walk-in-cooler', 1, ['test_food', 'other_food']), ('dry-storage', 2, ['test_food'])])
        current = (await self.client.get('/api/pg/actual-inventory/berts/setup')).json()['layout']
        self.assertEqual(current['header']['id'], layout['header']['id'])

    async def test_location_quantities_add_up_to_the_count_total(self):
        layout = await self.walk_layout()
        saved = await self.save_count(layout, [
            self.line('test_food', [('walk-in-cooler', '1.5'), ('dry-storage', '0.5')], value='60', confirmed=True),
            self.line('other_food', [('walk-in-cooler', '3')], value='45', confirmed=True)])
        self.assertEqual(saved.status_code, 200, saved.text)
        count = saved.json()
        self.assertEqual(count['header']['status'], 'complete')
        self.assertEqual(count['layout']['header']['id'], layout['header']['id'])  # recounts reuse it
        lines = {l['item_code']: l for l in count['lines']}
        self.assertEqual(Decimal(lines['test_food']['counted_quantity']), Decimal('2'))
        self.assertEqual(Decimal(lines['other_food']['counted_quantity']), Decimal('3'))
        self.assertEqual([(q['location_code'], Decimal(q['counted_quantity'])) for q in lines['test_food']['locations']],
                         [('walk-in-cooler', Decimal('1.5')), ('dry-storage', Decimal('0.5'))])

    async def test_blank_location_leaves_item_uncounted_and_mismatches_are_refused(self):
        layout = await self.walk_layout()
        partial = await self.save_count(layout, [
            self.line('test_food', [('walk-in-cooler', '1'), ('dry-storage', None)]),
            self.line('other_food', [('walk-in-cooler', '0')], value='0', confirmed=True)])
        self.assertEqual(partial.status_code, 200, partial.text)
        lines = {l['item_code']: l for l in partial.json()['lines']}
        self.assertIsNone(lines['test_food']['counted_quantity'])
        self.assertEqual(partial.json()['header']['status'], 'incomplete')
        good_other = self.line('other_food', [('walk-in-cooler', '3')])
        for bad in ([self.line('test_food', [('walk-in-cooler', '1')]), good_other],
                    [self.line('test_food', [('walk-in-cooler', '1'), ('dry-storage', '1'), ('freezer', '1')]), good_other],
                    [self.line('test_food', [('walk-in-cooler', '1'), ('walk-in-cooler', '1')]), good_other],
                    [{**self.line('test_food', [('walk-in-cooler', '1'), ('dry-storage', '1')]), 'counted_quantity': '2'}, good_other],
                    [self.line('test_food', [('walk-in-cooler', None), ('dry-storage', '1')], value='10'), good_other]):
            with self.subTest(bad=bad[0]):
                refused = await self.save_count(layout, bad)
                self.assertEqual(refused.status_code, 422, refused.text)
        body = {'scope_id': self.current['header']['id'], 'count_date': '2026-10-25', 'timing': 'before_receipts',
                'note': 'Synthetic', 'lines': [self.line('test_food', [('walk-in-cooler', '1')]), good_other]}
        refused = await self.client.post('/api/pg/actual-inventory/berts/counts', json=body,
                                         headers={'Idempotency-Key': str(uuid4())})
        self.assertEqual(refused.status_code, 422, refused.text)

    async def test_database_refuses_location_rows_outside_the_counts_layout(self):
        layout = await self.walk_layout()
        plain, _ = await self.count(self.current, '2026-10-26')
        self.assertEqual(plain.status_code, 200, plain.text)
        async with self.pool.acquire() as conn:
            with self.assertRaises(asyncpg.RaiseError) as held:
                async with conn.transaction():
                    await conn.execute('''INSERT INTO actual_inventory.count_line_locations
                        (snapshot_id,item_code,layout_id,location_code,counted_quantity) VALUES($1,'test_food',$2,'walk-in-cooler',2)''',
                        UUID(plain.json()['header']['id']), UUID(layout['header']['id']))
            self.assertIn("count's own layout", str(held.exception))
