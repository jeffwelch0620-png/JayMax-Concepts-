"""M6 analytics (Jeff 2026-11-06): the date window, who may see it, the switch, and the numbers
from a Bulk run that came up short and a delivery accepted short."""
import os
import unittest
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal as D
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException

import analytics
import deployment_readiness
import positions

TODAY = date(2026, 11, 6)


class AnalyticsModelTests(unittest.IsolatedAsyncioTestCase):
    def test_window_defaults_to_the_last_seven_days_and_caps_a_quarter(self):
        self.assertEqual(analytics.window(None, None, TODAY), (TODAY - timedelta(days=6), TODAY))
        self.assertEqual(analytics.window(date(2026, 11, 1), date(2026, 11, 1), TODAY), (date(2026, 11, 1), date(2026, 11, 1)))
        for start, end in ((date(2026, 11, 5), date(2026, 11, 4)), (TODAY - timedelta(days=analytics.MAX_DAYS), TODAY)):
            with self.assertRaises(HTTPException) as e: analytics.window(start, end, TODAY)
            self.assertEqual(e.exception.status_code, 422)

    def test_a_cycle_before_a_schedule_change_keeps_its_old_deadlines(self):
        import order_calendar as cal
        now_rows = [{'order_weekday': 2, 'count_due': time(11), 'order_due': time(14), 'delivery_weekday': 3, 'vendor_ids': ['pfg'], 'timezone_name': 'America/New_York'}]
        before = {**cal.day_view({**now_rows[0], 'count_due': time(12), 'order_due': time(15)})}
        changes = [{'order_weekday': 2, 'day_before': before, 'changed_at': datetime(2026, 11, 5, tzinfo=timezone.utc)}]
        row = cal.effective(cal.rows_at(now_rows, changes, datetime(2026, 11, 4, 23, tzinfo=timezone.utc)), {}, date(2026, 11, 4), 1)[date(2026, 11, 4)]['row']
        self.assertEqual((row['count_due'], analytics.deadline(row['count_due']), analytics.deadline(row['order_due'])), ('12:00', time(12), time(15)))
        self.assertEqual(analytics.deadline(time(11)), time(11))

    def test_waits_in_whole_minutes(self):
        self.assertEqual(analytics._minutes([{'minutes': D(10)}, {'minutes': D(20)}, {'minutes': D(90)}, {'minutes': None}]),
                         {'median_minutes': 20, 'average_minutes': 40, 'longest_minutes': 90})
        self.assertEqual(analytics._minutes([]), {'median_minutes': None, 'average_minutes': None, 'longest_minutes': None})

    async def test_waste_is_grouped_by_the_chosen_category_not_the_note(self):
        rows = [{'id': 1, 'business_date': TODAY, 'category': 'storage_spoilage', 'base_unit': 'lb', 'product_id': None, 'raw_item_code': 'romaine',
                 'name': 'Romaine', 'track': None, 'quantity': D('2')},
                {'id': 2, 'business_date': TODAY, 'category': 'storage_spoilage', 'base_unit': 'lb', 'product_id': None, 'raw_item_code': 'romaine',
                 'name': 'Romaine', 'track': None, 'quantity': D('1')},
                {'id': 3, 'business_date': TODAY, 'category': 'service_discard', 'base_unit': 'fl_oz', 'product_id': 'p1', 'raw_item_code': None,
                 'name': 'Ranch', 'track': 'daily', 'quantity': D('16')}]
        seen = []

        class Conn:
            async def fetchval(self, *a): return True
            async def fetch(self, sql, *a): seen.append(sql); return rows

        w = await analytics.waste(Conn(), 'berts', TODAY, TODAY, None)
        self.assertEqual((w['entries'], w['items'], w['by_reason']), (3, 2, {'storage_spoilage': 2, 'service_discard': 1}))
        self.assertIn("review_snapshot->'body'->>'category'", seen[0])
        self.assertEqual((await analytics.waste(Conn(), 'berts', TODAY, TODAY, 'daily'))['by_reason'], {'service_discard': 1})

    def sales_conn(self, days, items=(), covers=(), latest=None, installed=True):
        seen = []

        class Conn:
            async def fetchval(self, sql, *a):
                if 'to_regclass' in sql or 'to_regnamespace' in sql: seen.append((sql, a)); return installed
                return latest

            async def fetch(self, sql, *a):
                seen.append((sql, a))
                if 'toast_daily_sales' in sql: return [r for r in days if a[1] <= r['business_date'] <= a[2]]
                if 'UNION ALL' in sql: return list(covers)
                return list(items)
        return Conn(), seen

    @staticmethod
    def day(d, net, orders, status='complete', problems=()):
        return {'business_date': d, 'orders': orders, 'net_sales': D(net), 'discounts': D('1.00'), 'refunds': D('0'), 'status': status, 'problems': list(problems)}

    async def test_sales_totals_compare_with_the_days_just_before(self):
        # Range Nov 2-4 (3 days); the 3 days before are Oct 30 - Nov 1. Eastern 9 AM on Nov 6: through Nov 5 is due.
        now = datetime(2026, 11, 6, 14, tzinfo=timezone.utc)
        days = [self.day(date(2026, 10, 30), '100.00', 10), self.day(date(2026, 10, 31), '100.00', 10), self.day(date(2026, 11, 1), '100.00', 10),
                self.day(date(2026, 11, 2), '150.00', 10), self.day(date(2026, 11, 3), '0.00', 0),
                self.day(date(2026, 11, 4), '180.00', 12, 'needs review', ['refund without item detail'])]
        conn, seen = self.sales_conn(days, items=[{'item': 'g1', 'name': 'Hamburger Steak', 'quantity': D(5), 'net_sales': D('80.00')}],
                                     covers=[{'business_date': date(2026, 11, 2), 'quantity': D(4), 'amount': D('23.96')}], latest=date(2026, 11, 5))
        s = await analytics.sales(conn, 'papa_leonis', date(2026, 11, 2), date(2026, 11, 4), None, now)
        self.assertIn('has_schema_privilege', seen[0][0], 'schema access is checked before any table name in it is resolved')
        queries = [(q, a) for q, a in seen if 'toast_daily_sales' in q and 'to_regclass' not in q]
        self.assertEqual(queries[0][1][0], 'papa', "Inventory's papa_leonis is Toast's papa")
        self.assertEqual((s['totals']['net_sales'], s['totals']['orders'], s['totals']['average_check'], s['totals']['open_days']), (D('330.00'), 22, D('15.00'), 2))
        self.assertEqual((s['before']['net_sales'], s['before']['start'], s['before']['end']), (D('300.00'), date(2026, 10, 30), date(2026, 11, 1)))
        # Nov 4 needs review, so the selected stretch isn't complete and no change is shown.
        self.assertFalse(s['before']['complete'])
        clean = days[:5] + [self.day(date(2026, 11, 4), '180.00', 12)]
        conn, _ = self.sales_conn(clean, latest=date(2026, 11, 5))
        self.assertTrue((await analytics.sales(conn, 'berts', date(2026, 11, 2), date(2026, 11, 4), None, now))['before']['complete'])
        # One earlier day missing, or one needing review: not complete either.
        for edit in (lambda d: d[1:], lambda d: [self.day(date(2026, 10, 30), '100.00', 10, 'needs review')] + d[1:]):
            conn, _ = self.sales_conn(edit(clean), latest=date(2026, 11, 5))
            self.assertFalse((await analytics.sales(conn, 'berts', date(2026, 11, 2), date(2026, 11, 4), None, now))['before']['complete'])
        # A range ending today, which Toast hasn't saved yet: Nov 2-4 is compared with the three days before,
        # not with four, so an unchanged week doesn't look like a drop.
        conn, _ = self.sales_conn(clean, latest=date(2026, 11, 4))
        b = (await analytics.sales(conn, 'berts', date(2026, 11, 2), date(2026, 11, 5), None, datetime(2026, 11, 5, 14, tzinfo=timezone.utc)))['before']
        self.assertEqual((b['compared_days'], b['start'], b['end'], b['net_sales'], b['complete']), (3, date(2026, 10, 30), date(2026, 11, 1), D('300.00'), True))
        self.assertEqual([r['average_check'] for r in s['by_day']], [D('15.00'), None, D('15.00')])
        self.assertEqual(s['needs_review'], [{'business_date': date(2026, 11, 4), 'problems': ['refund without item detail']}])
        self.assertEqual((s['missing_days'], s['stale']), ([], False))
        self.assertEqual((s['salad_bar']['covers'], s['top_items'][0]['name']), (D(4), 'Hamburger Steak'))

    async def test_sales_say_when_a_day_has_not_arrived_from_toast(self):
        days = [self.day(date(2026, 11, 2), '150.00', 10)]
        conn, _ = self.sales_conn(days, latest=date(2026, 11, 2))
        # 9 AM Eastern on Nov 5: Nov 3 and 4 are due and missing; the latest day is behind.
        s = await analytics.sales(conn, 'berts', date(2026, 11, 2), date(2026, 11, 8), None, datetime(2026, 11, 5, 14, tzinfo=timezone.utc))
        self.assertEqual((s['missing_days'], s['stale']), ([date(2026, 11, 3), date(2026, 11, 4)], True))
        # 6 AM Eastern: yesterday's sync is not due yet, so only Nov 3 is missing and nothing is late.
        conn, _ = self.sales_conn(days + [self.day(date(2026, 11, 3), '1.00', 1)], latest=date(2026, 11, 3))
        s = await analytics.sales(conn, 'berts', date(2026, 11, 2), date(2026, 11, 8), None, datetime(2026, 11, 5, 11, tzinfo=timezone.utc))
        self.assertEqual((s['missing_days'], s['stale']), ([], False))

    async def test_sales_are_store_wide_and_the_salad_track_sees_its_covers(self):
        conn, seen = self.sales_conn([self.day(date(2026, 11, 3), '9.00', 1, 'needs review', ['refund without item detail'])],
                                     covers=[{'business_date': date(2026, 11, 2), 'quantity': D(4), 'amount': D('23.96')}], latest=date(2026, 11, 3))
        now = datetime(2026, 11, 5, 14, tzinfo=timezone.utc)
        self.assertEqual(await analytics.sales(conn, 'berts', date(2026, 11, 2), date(2026, 11, 4), 'bulk', now), analytics.STORE_WIDE)
        s = await analytics.sales(conn, 'berts', date(2026, 11, 2), date(2026, 11, 4), 'salad', now)
        self.assertEqual((s['track_only'], s['salad_bar']['covers'], 'totals' in s), (True, D(4), False))
        # The Salad view keeps the data warnings: a day needing review, and a sync that has fallen behind.
        self.assertEqual((s['needs_review'][0]['business_date'], s['stale'], s['missing_days']), (date(2026, 11, 3), True, [date(2026, 11, 2), date(2026, 11, 4)]))
        self.assertIn('NOT EXISTS', [q for q, _ in seen if 'UNION ALL' in q][0], 'an add-on on a Salad Bar item is not a second cover')
        conn, _ = self.sales_conn([], installed=False)
        self.assertEqual(await analytics.sales(conn, 'berts', date(2026, 11, 2), date(2026, 11, 4), None, now), {'available': False})
        self.assertEqual(await analytics.sales(conn, 'elsewhere', date(2026, 11, 2), date(2026, 11, 4), None, now), {'available': False})

    def test_general_manager_and_above_see_it(self):
        seen = {code for code, (role, _, _) in positions.POSITIONS.items() if positions.can({'role': role, 'position': code}, 'see_analytics')}
        self.assertEqual(seen, {'OWN', 'OPS', 'GM'})
        # A login with no position keeps its access class: owners only.
        self.assertTrue(positions.can({'role': 'owner'}, 'see_analytics'))
        self.assertFalse(positions.can({'role': 'manager'}, 'see_analytics'))

    def test_the_switch_must_match_in_server_and_web_app(self):
        base = {'USE_PG': 'true'}, {'REACT_APP_USE_PG': 'true'}
        self.assertEqual(deployment_readiness.configuration(*base)['status'], 'passed')
        held = deployment_readiness.configuration({**base[0], 'ANALYTICS_ENABLED': 'true'}, base[1])
        self.assertIn({'key': 'ANALYTICS', 'reason': 'Backend and built frontend feature flags differ'}, held['problems'])
        both = deployment_readiness.configuration({**base[0], 'ANALYTICS_ENABLED': 'true'}, {**base[1], 'REACT_APP_ANALYTICS': 'true'})
        self.assertEqual((both['status'], both['analytics']), ('passed', {'backend': True, 'frontend': True}))

    async def test_route_is_off_by_default_and_checks_the_permission_and_track(self):
        calls = []

        def authorize(request, store, write, require=None):
            calls.append((store, write, require))
            if request.headers.get('x-position') != 'GM': raise HTTPException(403, positions.DENIED[require])

        app = FastAPI()
        app.include_router(analytics.create_router(lambda: None, lambda s: None, authorize))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            with patch.dict(os.environ, {'ANALYTICS_ENABLED': 'false'}):
                self.assertEqual((await client.get('/api/pg/analytics/berts')).status_code, 503)
            with patch.dict(os.environ, {'ANALYTICS_ENABLED': 'true'}):
                denied = await client.get('/api/pg/analytics/berts', headers={'x-position': 'KM'})
                self.assertEqual((denied.status_code, denied.json()['detail']), (403, 'Analytics is visible to the General Manager and above'))
                self.assertEqual((await client.get('/api/pg/analytics/berts', params={'track': 'lunch'}, headers={'x-position': 'GM'})).status_code, 422)
                self.assertEqual((await client.get('/api/pg/analytics/berts', params={'start': '2026-11-06', 'end': '2026-11-01'},
                                                   headers={'x-position': 'GM'})).status_code, 422)
        self.assertEqual(calls[0], ('berts', False, 'see_analytics'))

    async def test_group_summary_shows_each_store_the_login_may_see_for_the_last_seven_full_days(self):
        def authorize(request, store, write, require=None):
            if store not in request.headers.get('x-stores', '').split(','): raise HTTPException(403, positions.DENIED[require])

        class Pool:
            def acquire(self): return self
            def transaction(self, **kw): return self
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
        seen = []

        async def summary(conn, store, start, end, now):
            seen.append((store, start, end)); return {'store_id': store}
        app = FastAPI()
        # 2 AM Eastern on Nov 7: yesterday is Nov 6, so the week is Oct 31 - Nov 6.
        app.include_router(analytics.create_router(lambda: Pool(), lambda s: None, authorize,
                                                   clock=lambda: datetime(2026, 11, 7, 7, tzinfo=timezone.utc)))
        stub = patch.object(analytics, 'store_summary', summary); stub.start(); self.addCleanup(stub.stop)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            with patch.dict(os.environ, {'ANALYTICS_ENABLED': 'false'}):
                self.assertEqual((await client.get('/api/pg/analytics-summary')).status_code, 503)
            with patch.dict(os.environ, {'ANALYTICS_ENABLED': 'true'}):
                none = await client.get('/api/pg/analytics-summary', headers={'x-stores': ''})
                self.assertEqual((none.status_code, none.json()['detail']), (403, 'Analytics is visible to the General Manager and above'))
                some = await client.get('/api/pg/analytics-summary', headers={'x-stores': 'rudds'})
                self.assertEqual((some.json()['start'], some.json()['end'], some.json()['stores']), ('2026-10-31', '2026-11-06', [{'store_id': 'rudds'}]))
                every = await client.get('/api/pg/analytics-summary', headers={'x-stores': 'berts,rudds,papa'})
                self.assertEqual([s['store_id'] for s in every.json()['stores']], ['berts', 'rudds', 'papa'])
        self.assertEqual(seen[0], ('rudds', date(2026, 10, 31), date(2026, 11, 6)))

    async def test_a_store_tile_compares_only_complete_stretches_and_names_the_largest_prep_gap(self):
        import menu_portions
        sales = {'available': True, 'totals': {'net_sales': D('700'), 'orders': 70, 'average_check': D('10'), 'days': 7},
                 'before': {'net_sales': D('600'), 'compared_days': 7, 'complete': False},
                 'latest_day': date(2026, 11, 6), 'stale': False, 'missing_days': [], 'needs_review': [{'business_date': date(2026, 11, 2)}]}
        prep = {'available': True, 'coverage': {'covered_percent': 80}, 'missing_count': 2,
                'items': [{'has_portions': True, 'gap': D(0), 'name': 'Even', 'unit': 'lb', 'gap_percent': 0},
                          {'has_portions': True, 'gap': D('-4'), 'name': 'Invented slaw', 'unit': 'qt', 'gap_percent': -20},
                          {'has_portions': False, 'gap': None, 'name': 'No portions', 'unit': 'lb', 'gap_percent': None}]}

        async def fixed(value): return value
        with patch.object(analytics, 'sales', lambda *a: fixed(sales)), patch.object(analytics, 'waste', lambda *a: fixed({'available': False})),                 patch.object(menu_portions, 'prep_against_sales', lambda *a: fixed(prep)):
            tile = await analytics.store_summary(None, 'berts', date(2026, 10, 31), date(2026, 11, 6), None)
        self.assertEqual((tile['sales']['net_sales'], tile['sales']['before_net_sales'], tile['sales']['compared_days'], tile['sales']['needs_review']),
                         (D('700'), None, 0, 1), 'an incomplete stretch is never compared')
        self.assertEqual(tile['waste'], {'available': False})
        self.assertEqual(tile['prep_vs_sales'], {'available': True, 'covered_percent': 80, 'missing_count': 2,
                                                 'largest_gap': {'name': 'Invented slaw', 'unit': 'qt', 'gap': D('-4'), 'gap_percent': -20}})


import test_bulk_supply as bulk_tests
import test_prep_day_tasks as day


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class AnalyticsDatabaseTests(bulk_tests.BulkSupplyDatabaseTests):
    # Reuse the Bulk supply fixture without re-running its own tests here.
    for _name in [n for n in dir(bulk_tests.BulkSupplyDatabaseTests) if n.startswith('test_')]:
        locals()[_name] = None
    del _name

    async def report(self, store, track=None):
        now = datetime(2026, 10, 20, 16, tzinfo=timezone.utc)
        async with self.pool.acquire() as c:
            return await analytics.report(c, store, date(2026, 10, 1), date(2026, 10, 15), track, now)

    async def test_a_short_bulk_run_and_a_delivery_accepted_short(self):
        flag = patch.dict(os.environ, {'PREP_EXECUTION_ENABLED': 'true'}); flag.start(); self.addCleanup(flag.stop)
        async with self.pool.acquire() as c:
            for name in ('20261005_prep_opening_sources.sql', '20261007_prep_execution.sql', '20261007_prep_progress.sql', '20261030_bulk_release_coverage.sql'):
                await c.execute((day.recovery.counts.native.ROOT / 'migrations' / name).read_text(encoding='utf-8'))
        # Rudd's asks for 18 lb; the maker's run needs 3 + 18 = 21 and plans one 48 lb batch.
        sent = await self.scheduled(await self.rudds_count('12'))
        count = await self.prep_count('2')
        saved = await self.write_day(self.bulk_body(count_event_id=count['id'])); self.assertEqual(saved.status_code, 200, saved.text)
        command = dict(action='release', draft_version_id=saved.json()['draft']['id'], reason='Manager reviewed the Bulk run')
        ok = await self.catalog.post(f'/api/pg/purchases/berts/prep-execution/{bulk_tests.RUN}/preview', params={'track': 'bulk'}, json=command, headers={'If-Match': '0'})
        self.assertEqual(ok.status_code, 200, ok.text)
        done = await self.catalog.post(f'/api/pg/purchases/berts/prep-execution/{bulk_tests.RUN}/commands', params={'track': 'bulk'},
                                       headers={'If-Match': '0', 'Idempotency-Key': str(uuid4())},
                                       json=dict(command=command, expected_review_hash=ok.json()['reviewHash'], reviewed=True))
        self.assertEqual(done.status_code, 200, done.text)
        # 12 sent and 3 held at the maker; Rudd's accepts 12, so 3 are still owed.
        fulfill = dict(action='fulfill', handoff='pickup', note='Made Thursday', lines=[dict(ordinal=1, base_quantity='12', held_base_quantity='3', packaging='3 x 5 lb bags')])
        self.assertEqual((await self.step('berts', sent['id'], fulfill)).status_code, 200)
        self.assertEqual((await self.step('rudds', sent['id'], dict(action='accept', note='Checked in', lines=[dict(ordinal=1, base_quantity='12')]))).status_code, 200)

        maker = await self.report('berts')
        t = maker['throughput']
        self.assertEqual((t['available'], t['lists'], t['tasks'], t['met_plan'], t['short']), (True, {'released': 1, 'not_released': 0}, 1, 0, 1))
        short = t['short_tasks'][0]
        self.assertEqual((short['prep_date'], short['track'], D(short['planned']), D(short['made']), D(short['short_by'])), (bulk_tests.RUN, 'bulk', D(48), D(0), D(48)))
        self.assertEqual(t['tracks'][0]['average_percent_of_plan'], 0)
        # The Daily filter leaves the Bulk run out; the Bulk filter keeps it.
        self.assertEqual((await self.report('berts', 'daily'))['throughput']['tasks'], 0)
        self.assertEqual((await self.report('berts', 'bulk'))['throughput']['tasks'], 1)

        for store in ('rudds', 'berts'):  # both ends see the same delivery
            bulk = (await self.report(store))['transfers']['bulk']
            self.assertEqual((bulk['requests'], bulk['accepted'], bulk['open'], bulk['lines_short']), (1, 1, 0, 1))
            line = bulk['differences'][0]
            self.assertEqual((line['from_store_id'], line['to_store_id'], D(line['requested']), D(line['sent']), D(line['held']), D(line['accepted']),
                              D(line['still_owed']), D(line['sent_not_accepted'])), ('berts', 'rudds', D(18), D(12), D(3), D(12), D(3), D(0)))
        # Store-wide parts are left out when a track is chosen; parts not installed here say so.
        daily = await self.report('rudds', 'daily')
        self.assertEqual((daily['transfers']['bulk'], daily['on_time']), (analytics.STORE_WIDE, analytics.STORE_WIDE))
        self.assertEqual((maker['on_time'], maker['shortages']), ({'available': False}, {'available': False}))
