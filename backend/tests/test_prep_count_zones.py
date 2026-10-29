"""Evening prep count zones: per-zone quantities that add up to the one prep count line."""
import os
import unittest
from decimal import Decimal
from uuid import uuid4

import asyncpg

import prep_observations as observations
import test_prep_observations as prep

MIGRATION = 'migrations/20261029_prep_count_zones.sql'
STAMP = {'performed_at': '2026-10-05T21:30:00-04:00', 'business_date': '2026-10-05', 'timezone_name': 'America/New_York',
         'calendar_date_confirmed': True, 'note': 'Invented evening count', 'complete_scope_confirmed': True}


class ZoneModelTests(unittest.TestCase):
    def line(self, **changes):
        return {'product_version_id': str(uuid4()), 'profile_id': str(uuid4()), 'evidence': 'Invented', **changes}

    def test_a_line_has_either_a_total_or_zone_quantities(self):
        self.assertEqual(observations.CountLine(**self.line(quantity='2')).quantity, Decimal(2))
        zoned = observations.CountLine(**self.line(zones=[{'zone_code': 'walk-in', 'quantity': '1.5'}]))
        self.assertIsNone(zoned.quantity)
        for bad in (self.line(), self.line(quantity='2', zones=[{'zone_code': 'walk-in', 'quantity': '2'}])):
            with self.assertRaises(ValueError): observations.CountLine(**bad)
        with self.assertRaises(ValueError): observations.CountLine(**self.line(zones=[{'zone_code': 'walk-in', 'quantity': 'NaN'}]))

    def test_zone_counts_name_their_layout_for_every_line(self):
        zoned = self.line(zones=[{'zone_code': 'walk-in', 'quantity': '1'}])
        observations.CountIn(**STAMP, zone_layout_id=str(uuid4()), lines=[zoned])
        for bad in ({'lines': [zoned]}, {'zone_layout_id': str(uuid4()), 'lines': [zoned, self.line(quantity='1')]},
                    {'zone_layout_id': str(uuid4()), 'lines': [self.line(quantity='1')]}):
            with self.assertRaises(ValueError): observations.CountIn(**STAMP, **bad)

    def test_counts_without_zones_keep_their_fingerprint_shape(self):
        body = observations.CountIn(**STAMP, lines=[self.line(quantity='2')])
        dumped = observations.body_dump(body)
        self.assertNotIn('zone_layout_id', dumped)
        self.assertNotIn('zones', dumped['lines'][0])


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PG required')
class PrepCountZoneTests(prep.PrepObservationTests):
    # Reuse the prep observation fixture without re-running its own tests here.
    for _name in [n for n in dir(prep.PrepObservationTests) if n.startswith('test_')]:
        locals()[_name] = None
    del _name

    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with self.pool.acquire() as c:
            await c.execute((prep.fixtures.foundation.recovery.counts.native.ROOT / MIGRATION).read_text(encoding='utf-8'))
        self.products = [p['product_id'] for p in (await self.state())['products']]

    async def save_zones(self, zones, key=None):
        return await self.client.post('/api/pg/purchases/berts/prep-count-zones', json={'note': 'Invented zones', 'zones': zones},
                                      headers={'Idempotency-Key': key or str(uuid4())})

    async def salad_zones(self):
        saved = await self.save_zones([{'name': 'Walk-in', 'product_ids': self.products},
                                       {'name': 'Salad station', 'product_ids': self.products[:1]}])
        self.assertEqual(saved.status_code, 200, saved.text)
        return saved.json()

    async def zone_body(self, layout, walk_in='2', station='1.5'):
        body = await self.count_body()
        ids = {r['product_version_id']: r for r in body['lines']}
        versions = {p['id']: p['product_id'] for p in (await self.state())['products']}
        for line in ids.values():
            line.pop('quantity')
            line['zones'] = [{'zone_code': 'walk-in', 'quantity': walk_in}]
            if versions[line['product_version_id']] == self.products[0]: line['zones'].append({'zone_code': 'salad-station', 'quantity': station})
        return body | {'zone_layout_id': layout['header']['id'], 'performed_at': '2026-10-05T21:30:00-04:00'}

    async def test_zone_count_adds_up_zones_and_keeps_the_breakdown(self):
        setup = await self.state()
        self.assertIsNone(setup['zoneLayout'])
        self.assertEqual(setup['proposedZoneLayout']['zones'][0]['name'], 'Walk-in')
        layout = await self.salad_zones()
        self.assertEqual([z['zone_code'] for z in layout['zones']], ['walk-in', 'salad-station'])
        self.assertEqual((await self.state())['zoneLayout']['header']['id'], layout['header']['id'])
        event, _ = await self.save_obs('count', await self.zone_body(layout))
        async with self.pool.acquire() as c:
            line = await c.fetchval('SELECT quantity FROM prep_inventory.count_observations WHERE event_id=$1 AND product_id=$2', event['id'], self.products[0])
            zones = await c.fetch('SELECT zone_code,quantity FROM prep_inventory.count_zone_quantities WHERE event_id=$1 AND product_id=$2', event['id'], self.products[0])
        self.assertEqual(line, Decimal('3.5'))
        self.assertEqual({r['zone_code']: r['quantity'] for r in zones}, {'walk-in': Decimal(2), 'salad-station': Decimal('1.5')})

    async def test_zones_must_match_the_layout(self):
        layout = await self.salad_zones()
        body = await self.zone_body(layout)
        target = next(l for l in body['lines'] if len(l['zones']) == 2)
        target['zones'].pop()
        self.assertEqual((await self.plan_obs('count', body)).status_code, 422)
        target['zones'] += [{'zone_code': 'salad-station', 'quantity': '1'}, {'zone_code': 'freezer', 'quantity': '1'}]
        self.assertEqual((await self.plan_obs('count', body)).status_code, 422)
        body = await self.zone_body(layout)
        body['zone_layout_id'] = str(uuid4())
        self.assertEqual((await self.plan_obs('count', body)).status_code, 422)

    async def test_layout_places_every_item_and_replays_by_key(self):
        self.assertEqual((await self.save_zones([{'name': 'Walk-in', 'product_ids': []}])).status_code, 422)
        if len(self.products) > 1:
            self.assertEqual((await self.save_zones([{'name': 'Walk-in', 'product_ids': self.products[:1]}])).status_code, 422)
        self.assertEqual((await self.save_zones([{'name': 'Walk-in', 'product_ids': self.products}, {'name': 'Walk In', 'product_ids': self.products}])).status_code, 422)
        self.assertEqual((await self.save_zones([{'name': 'Walk-in', 'product_ids': self.products + [str(uuid4())]}])).status_code, 422)
        key = str(uuid4())
        first = await self.save_zones([{'name': 'Walk-in', 'product_ids': self.products}], key)
        again = await self.save_zones([{'name': 'Walk-in', 'product_ids': self.products}], key)
        self.assertEqual(first.json()['header']['id'], again.json()['header']['id'])
        self.assertEqual((await self.save_zones([{'name': 'Cooler', 'product_ids': self.products}], key)).status_code, 409)

    async def test_database_refuses_zone_rows_that_do_not_add_up(self):
        layout = await self.salad_zones()
        event, _ = await self.save_obs('count', await self.zone_body(layout))
        async with self.pool.acquire() as c:
            with self.assertRaises(asyncpg.PostgresError):
                await c.execute('UPDATE prep_inventory.count_zone_quantities SET quantity=9 WHERE event_id=$1', event['id'])
        body = await self.count_body()
        plain, _ = await self.save_obs('count', body | {'performed_at': '2026-10-05T22:00:00-04:00'})
        async with self.pool.acquire() as c:
            with self.assertRaises(asyncpg.PostgresError):
                async with c.transaction():
                    await c.execute('''INSERT INTO prep_inventory.count_zone_quantities(event_id,store_id,product_id,layout_id,zone_code,quantity)
                        VALUES($1,'berts',$2,$3,'walk-in',0.5)''', plain['id'], self.products[0], layout['header']['id'])
