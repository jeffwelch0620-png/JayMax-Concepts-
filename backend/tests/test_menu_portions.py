"""M6 prep against sales (Jeff 2026-11-13): menu portions, who may set them, and the comparison of prep
made, wasted and counted with what invented Toast sales imply was used."""
import os
import unittest
from pathlib import Path
from datetime import date, datetime, timezone
from decimal import Decimal as D
from unittest.mock import patch
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

import analytics
import menu_portions as portions
import positions

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


def row(product, quantity, effective=None, minute=0):
    return {'product_id': product, 'base_quantity': D(quantity), 'effective_from': effective,
            'recorded_at': T0.replace(minute=minute)}


class PortionModelTests(unittest.IsolatedAsyncioTestCase):
    def test_the_newest_row_covering_a_day_wins(self):
        rows = [row('fries', '6', None, 0), row('fries', '5', date(2026, 11, 1), 1), row('slaw', '2', None, 2)]
        self.assertEqual(portions.lines_on(rows, date(2026, 10, 15)), ({'fries': D(6), 'slaw': D(2)}, False))
        self.assertEqual(portions.lines_on(rows, date(2026, 11, 2)), ({'fries': D(5), 'slaw': D(2)}, False))
        # A later correction "from the start" covers every day again, including after Nov 1.
        fixed = rows + [row('fries', '4', None, 3)]
        self.assertEqual(portions.lines_on(fixed, date(2026, 11, 2))[0]['fries'], D(4))
        # A zero row removes a line; the marker row says the item uses no tracked prep.
        gone = rows + [row('slaw', '0', date(2026, 11, 1), 4), row(None, '1', date(2026, 11, 1), 4)]
        self.assertEqual(portions.lines_on(gone, date(2026, 11, 2)), ({'fries': D(5)}, True))
        self.assertEqual(portions.lines_on(gone, date(2026, 10, 2)), ({'fries': D(6), 'slaw': D(2)}, False))
        self.assertEqual(portions.lines_on([], date(2026, 10, 2)), ({}, False))

    def test_an_item_has_portions_only_when_one_applies_inside_the_range(self):
        start, end = date(2026, 10, 5), date(2026, 10, 6)
        later = {('item', 1): [row('fries', '1', date(2026, 10, 10), 0)]}
        cleared = {('item', 1): [row('fries', '1', None, 0), row('fries', '0', date(2026, 10, 1), 1)]}
        starts_inside = {('item', 1): [row('fries', '1', date(2026, 10, 6), 0)]}
        cleared_inside = {('item', 1): [row('fries', '1', None, 0), row('fries', '0', date(2026, 10, 6), 1)]}
        self.assertEqual(portions.with_portions(later, start, end), set())
        self.assertEqual(portions.with_portions(cleared, start, end), set())
        self.assertEqual(portions.with_portions(starts_inside, start, end), {'fries'})
        self.assertEqual(portions.with_portions(cleared_inside, start, end), {'fries'})

    def test_a_change_names_each_prep_item_once_with_a_positive_amount(self):
        base = dict(sold_kind='item', sold_guid=str(uuid4()), sold_name='Invented Plate')
        portions.PortionChange(**base, lines=[{'product_id': str(uuid4()), 'base_quantity': '0.375'}])
        portions.PortionChange(**base, no_prep=True)
        same = str(uuid4())
        for bad in (dict(lines=[{'product_id': same, 'base_quantity': '1'}, {'product_id': same, 'base_quantity': '2'}]),
                    dict(lines=[{'product_id': str(uuid4()), 'base_quantity': '0'}]),
                    dict(lines=[{'product_id': str(uuid4()), 'base_quantity': '0.1234567'}]),
                    dict(no_prep=True, lines=[{'product_id': str(uuid4()), 'base_quantity': '1'}]),
                    dict(sold_kind='dish'), dict(sold_name='  '), dict(sold_name='bad\x00name'), dict(extra=1)):
            with self.assertRaises(ValidationError): portions.PortionChange(**{**base, **bad})

    def test_owners_and_the_ops_lead_set_portions(self):
        allowed = {code for code, (role, _, _) in positions.POSITIONS.items() if positions.can({'role': role, 'position': code}, 'set_portions')}
        self.assertEqual(allowed, {'OWN', 'OPS'})
        self.assertFalse(positions.can({'role': 'manager'}, 'set_portions'))

    async def test_routes_are_off_with_analytics_and_check_permissions(self):
        calls = []

        def authorize(request, store, write, require=None):
            calls.append((write, require))
            if request.headers.get('x-position') not in positions.PERMISSIONS[require]: raise HTTPException(403, positions.DENIED[require])
            return 'usr_' + request.headers['x-position']

        app = FastAPI(); app.include_router(portions.create_router(lambda: None, lambda s: None, authorize))
        change = dict(sold_kind='item', sold_guid=str(uuid4()), sold_name='Invented Plate', no_prep=True)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            with patch.dict(os.environ, {'ANALYTICS_ENABLED': 'false'}):
                self.assertEqual((await client.get('/api/pg/menu-portions/berts', headers={'x-position': 'OWN'})).status_code, 503)
            with patch.dict(os.environ, {'ANALYTICS_ENABLED': 'true'}):
                self.assertEqual((await client.get('/api/pg/menu-portions/berts', headers={'x-position': 'KM'})).status_code, 403)
                denied = await client.post('/api/pg/menu-portions/berts', json=change, headers={'x-position': 'GM', 'Idempotency-Key': str(uuid4())})
                self.assertEqual((denied.status_code, denied.json()['detail']), (403, positions.DENIED['set_portions']))
                self.assertEqual((await client.post('/api/pg/menu-portions/berts', json=change, headers={'x-position': 'OWN'})).status_code, 422,
                                 'a change needs an idempotency key')
        self.assertIn((True, 'set_portions'), calls)

    async def test_nothing_shows_without_the_table_or_toast_access(self):
        class Conn:
            def __init__(self, table, toast): self.table, self.toast = table, toast
            async def fetchval(self, sql, *a):
                if 'menu_portions' in str(a): return self.table
                return self.toast
        for conn in (Conn(False, True), Conn(True, False)):
            self.assertEqual(await portions.prep_against_sales(conn, 'berts', date(2026, 10, 5), date(2026, 10, 6), None), {'available': False})
        self.assertEqual(await portions.prep_against_sales(Conn(True, True), 'elsewhere', date(2026, 10, 5), date(2026, 10, 6), None), {'available': False})

    def test_migration_is_append_only_and_seeds_nothing(self):
        sql = (Path(__file__).resolve().parents[2] / 'migrations/20261113_menu_portions.sql').read_text()
        self.assertNotIn('INSERT INTO', sql.upper())
        for guard in ('menu_portions_append_only', 'menu_portions_no_truncate', 'ENABLE ROW LEVEL SECURITY'):
            self.assertIn(guard, sql)


import test_prep_observations as observations

ITEM, MODIFIER, DRINK, OTHER = (UUID(int=n) for n in (1, 2, 3, 4))
TOAST = '''CREATE SCHEMA integrations;
CREATE TABLE integrations.toast_location_map(toast_restaurant_guid uuid PRIMARY KEY, store_id text NOT NULL);
CREATE TABLE integrations.toast_item_sales(toast_restaurant_guid uuid, business_date date, item_key text, item_guid uuid,
  display_name text, quantity numeric, net_amount numeric, PRIMARY KEY(toast_restaurant_guid, business_date, item_key));
CREATE TABLE integrations.toast_modifier_sales(toast_restaurant_guid uuid, business_date date, parent_item_key text, option_key text,
  option_guid uuid, display_name text, quantity numeric, amount numeric, PRIMARY KEY(toast_restaurant_guid, business_date, parent_item_key, option_key));
CREATE TABLE integrations.toast_daily_sales(store_id text, business_date date, status text);'''


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class PortionDatabaseTests(observations.PrepObservationTests):
    for _name in [n for n in dir(observations.PrepObservationTests) if n.startswith('test_')]:
        locals()[_name] = None
    del _name

    async def asyncSetUp(self):
        await super().asyncSetUp()
        await install_portions(self)

    async def set(self, guid, lines=(), kind='item', name='Invented Plate', key=None, position='OWN', **over):
        return await set_portion(self, guid, lines, kind, name, key, position, **over)

    async def report(self, store='berts', start=date(2026, 10, 5), end=date(2026, 10, 6), track=None):
        async with self.pool.acquire() as c:
            return await portions.prep_against_sales(c, store, start, end, track)

    async def test_made_wasted_and_counted_against_what_sales_imply(self):
        await made_wasted_and_counted(self)

    async def test_changes_are_kept_replayed_and_refused_outside_the_store(self):
        await changes_kept(self)


async def install_portions(self):
        root = observations.fixtures.foundation.recovery.counts.native.ROOT
        berts, rudds = uuid4(), uuid4()
        async with self.pool.acquire() as c:
            await c.execute((root / 'migrations/20261113_menu_portions.sql').read_text())
            await c.execute(TOAST)
            await c.execute('INSERT INTO integrations.toast_location_map VALUES($1,$2),($3,$4)', berts, 'berts', rudds, 'rudds')
            sales = [(berts, date(2026, 10, 5), 'i1', ITEM, 'Invented Plate', 12, '120.00'), (berts, date(2026, 10, 6), 'i1', ITEM, 'Invented Plate', 8, '80.00'),
                     (berts, date(2026, 10, 5), 'i2', DRINK, 'Invented Tea', 30, '60.00'), (berts, date(2026, 10, 5), 'open:Cake', None, 'Cake', 1, '5.00'),
                     (rudds, date(2026, 10, 5), 'i9', OTHER, 'Other store item', 3, '30.00')]
            await c.executemany('INSERT INTO integrations.toast_item_sales VALUES($1,$2,$3,$4,$5,$6,$7::numeric)', sales)
            await c.execute("INSERT INTO integrations.toast_modifier_sales VALUES($1,'2026-10-05','i1','m1',$2,'Extra side',4,'4.00')", berts, MODIFIER)
            await c.execute("INSERT INTO integrations.toast_daily_sales VALUES('berts','2026-10-05','complete'),('berts','2026-10-06','needs review')")
        self.product_id = UUID(self.p['product_id'])
        self.flag = patch.dict(os.environ, {'ANALYTICS_ENABLED': 'true'}); self.flag.start(); self.addCleanup(self.flag.stop)

        def authorize(request, store, write, require=None):
            position = request.headers.get('x-position', 'OWN')
            if position not in positions.PERMISSIONS[require]: raise HTTPException(403, positions.DENIED[require])
            return 'usr_' + position
        app = FastAPI()
        app.include_router(portions.create_router(lambda: self.pool, lambda s: None, authorize,
                                                  clock=lambda: datetime(2026, 10, 7, 14, tzinfo=timezone.utc)))
        self.portions = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')
        self.addAsyncCleanup(self.portions.aclose)


async def set_portion(self, guid, lines, kind, name, key, position, **over):
        body = dict(sold_kind=kind, sold_guid=str(guid), sold_name=name, lines=[{'product_id': str(self.product_id), 'base_quantity': q} for q in lines], **over)
        return await self.portions.post('/api/pg/menu-portions/berts', json=body, headers={'x-position': position, 'Idempotency-Key': key or str(uuid4())})


async def made_wasted_and_counted(self):
        # Count 10 lb the night before, make 48 lb and waste 5 lb on Oct 5, count 7 lb on Oct 6.
        await self.save_obs('count', await self.count_body('10', performed_at='2026-10-04T22:00:00-04:00', business_date='2026-10-04'))
        batch, _ = await self.record(await self.entry())
        await self.save_obs('waste', await self.waste(batch, '5'))
        await self.save_obs('count', await self.count_body('7', performed_at='2026-10-06T22:00:00-04:00', business_date='2026-10-06'))

        before = await self.report()
        self.assertEqual(before['items'][0]['has_portions'], False)
        self.assertIsNone(before['items'][0]['gap'], 'no portions means no implied use, never zero')
        self.assertEqual((before['missing_count'], before['coverage']['covered_percent']), (2, 0))

        # A portion that only starts after the range is not a portion for it: still missing, not zero use.
        self.assertEqual((await self.set(ITEM, ['1.5'], effective_from='2026-10-10')).status_code, 200)
        later = await self.report()
        self.assertEqual((later['items'][0]['has_portions'], later['items'][0]['implied'], later['missing_count']), (False, None, 2))
        # 1.5 lb per plate from the start; 0.5 lb per extra side; the tea uses no tracked prep.
        self.assertEqual((await self.set(ITEM, ['1.5'])).status_code, 200)
        self.assertEqual((await self.set(MODIFIER, ['0.5'], kind='modifier', name='Extra side')).status_code, 200)
        self.assertEqual((await self.set(DRINK, no_prep=True, name='Invented Tea')).status_code, 200)
        r = await self.report()
        it = r['items'][0]
        # used = 10 + 48 - 5 - 7 = 46; implied = (12 + 8) x 1.5 + 4 x 0.5 = 32; gap 14 (44%).
        self.assertEqual((it['made'], it['wasted'], it['opening'], it['closing'], it['counts_used']), (D(48), D(5), D(10), D(7), True))
        self.assertEqual((it['used'], it['implied'], it['gap'], it['gap_percent']), (D(46), D(32), D(14), 44))
        self.assertEqual([s['name'] for s in it['from_sales']], ['Invented Plate', 'Extra side'])
        # Only the open item (no Toast id) is left uncovered; the other store's sales are not counted.
        self.assertEqual((r['missing_count'], r['coverage']['open_items'], r['coverage']['covered_percent'], r['modifiers_with_portions']),
                         (0, D('5.00'), 98, 1))
        self.assertEqual((r['sales_days'], r['sales_days_complete'], r['range_days']), (2, 1, 2))

        # From Oct 6 the plate uses 1 lb: implied = 12 x 1.5 + 8 x 1 + 2 = 28.
        self.assertEqual((await self.set(ITEM, ['1'], effective_from='2026-10-06', reason='Smaller portion')).status_code, 200)
        self.assertEqual((await self.report())['items'][0]['implied'], D(28))
        # Without a closing count the on-hand change is left out: one day, Oct 5 only.
        one = (await self.report(end=date(2026, 10, 5)))['items'][0]
        self.assertEqual((one['counts_used'], one['used'], one['implied']), (False, D(43), D(20)))
        self.assertEqual((await self.report(track='bulk'))['items'], [], 'the track filter follows the prep plan')

async def changes_kept(self):
        key = str(uuid4())
        first = await self.set(ITEM, ['1.5'], key=key)
        self.assertEqual(first.json(), {'saved': 1, 'replayed': False})
        self.assertEqual((await self.set(ITEM, ['1.5'], key=key)).json(), {'saved': 1, 'replayed': True})
        self.assertEqual((await self.set(ITEM, ['2'], key=key)).status_code, 409)
        self.assertEqual((await self.set(ITEM, ['2'], position='GM')).status_code, 403)
        self.assertEqual((await self.set(OTHER, ['1'])).status_code, 422, "another store's menu item")
        self.assertEqual((await self.set(uuid4(), ['1'])).status_code, 422, 'never sold here')
        foreign = await self.portions.post('/api/pg/menu-portions/berts', headers={'Idempotency-Key': str(uuid4())},
                                           json=dict(sold_kind='item', sold_guid=str(ITEM), sold_name='Invented Plate',
                                                     lines=[{'product_id': str(uuid4()), 'base_quantity': '1'}]))
        self.assertEqual(foreign.status_code, 422)
        # Clearing the plate writes a zero line; the history keeps both.
        self.assertEqual((await self.set(ITEM, [])).json()['saved'], 1)
        menu = (await self.portions.get('/api/pg/menu-portions/berts')).json()
        plate = next(s for s in menu['sold'] if s['guid'] == str(ITEM))
        self.assertEqual((plate['status'], plate['lines'], plate['changes'], menu['can_edit']), ('missing', [], 2, True))
        self.assertFalse((await self.portions.get('/api/pg/menu-portions/berts', headers={'x-position': 'GM'})).json()['can_edit'])
        history = (await self.portions.get('/api/pg/menu-portions/berts/history', params={'kind': 'item', 'guid': str(ITEM)})).json()
        self.assertEqual([D(c['base_quantity']) for c in history['changes']], [D(0), D('1.5')])
        async with self.pool.acquire() as c:
            for sql in ('UPDATE prep_inventory.menu_portions SET base_quantity=9', 'DELETE FROM prep_inventory.menu_portions',
                        'TRUNCATE prep_inventory.menu_portions'):
                with self.assertRaisesRegex(Exception, 'append-only'):
                    await c.execute(sql)


import test_prep_openings as openings


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class PortionOpeningTests(openings.PrepOpeningTests):
    for _name in [n for n in dir(openings.PrepOpeningTests) if n.startswith('test_')]:
        locals()[_name] = None
    del _name

    async def asyncSetUp(self):
        await super().asyncSetUp()
        await install_portions(self)

    async def test_opening_stock_is_not_prep_made(self):
        # A store's first prep count becomes opening stock (source_kind 'opening'); it is on hand, not made.
        count = await self.count_at('09:00', quantities={self.p['id']: '50'})
        await self.opening(count)
        self.assertEqual((await set_portion(self, ITEM, ['1.5'], 'item', 'Invented Plate', None, 'OWN')).status_code, 200)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval("SELECT count(*) FROM prep_inventory.batch_events WHERE source_kind='opening'"), 1)
            r = await portions.prep_against_sales(c, 'berts', date(2026, 10, 5), date(2026, 10, 5), None)
        row = next(i for i in r['items'] if i['product_id'] == self.product_id)
        self.assertEqual((row['made'], row['implied']), (D(0), D(18)))
