"""Invented operating summaries; no managed database or operational invoice reads."""
import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import httpx
import native_inventory_views as views
import test_manual_purchases as fixtures


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PG DSN required')
class NativeInventoryViewTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.ManualPurchaseTests.asyncSetUp
    asyncTearDown = fixtures.ManualPurchaseTests.asyncTearDown
    target = fixtures.ManualPurchaseTests.target
    scope = fixtures.ManualPurchaseTests.scope
    count = fixtures.ManualPurchaseTests.count
    manual = fixtures.ManualPurchaseTests.manual
    body = fixtures.ManualPurchaseTests.body
    post = fixtures.ManualPurchaseTests.post
    plan = fixtures.ManualPurchaseTests.plan
    correct = fixtures.ManualPurchaseTests.correct

    async def summary(self, store='berts', day='2026-10-05'):
        return await views.read_operating_summary(self.pool, store, date.fromisoformat(day))

    async def receipt(self, number=None, day='2026-10-04', amount='40'):
        doc = (await self.manual(fixtures.record(number=number or str(uuid4()), amount=amount))).json()['documents'][0]
        posted = await self.post(doc, {**self.body(doc), 'received_date': day})
        self.assertEqual(posted.status_code, 200, posted.text)
        return doc

    async def test_empty_and_purchase_only_states_do_not_invent_inventory(self):
        empty = await self.summary()
        self.assertEqual(empty['countStatus'], 'scope_missing'); self.assertIsNone(empty['inventoryValue'])
        self.assertEqual(Decimal(empty['netFoodPurchases30']), 0)
        await self.receipt()
        with patch.dict(os.environ, {'ACTUAL_INVENTORY_ENABLED': 'false'}):
            result = await self.summary()
        self.assertEqual(result['countStatus'], 'awaiting_enablement'); self.assertIsNone(result['inventoryValue'])
        self.assertEqual(Decimal(result['netFoodPurchases30']), 40)
        self.assertFalse(result['liveOnHandAvailable']); self.assertFalse(result['orderSuggestionsAvailable'])

    async def test_last_count_value_ignores_stock_prices_portions_and_prepped_items(self):
        scope = (await self.scope())[0].json()
        saved = (await self.count(scope, '2026-10-04', quantity='3', value='75'))[0]
        self.assertEqual(saved.status_code, 200, saved.text)
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE store_items SET current_stock=999,par=999 WHERE store_id='berts'")
            await conn.execute("UPDATE items SET portion_size=999 WHERE code='test_food'")
            await conn.execute("INSERT INTO vendor_items(vendor_id,vendor_sku,item_code,purchase_unit,price) VALUES('synthetic_other','TEST','test_food','case',999)")
            await conn.execute("UPDATE store_items SET current_stock=999 WHERE item_code='prep_sauce'")
        result = await self.summary()
        self.assertEqual(result['inventoryValue'], '75.00'); self.assertEqual(result['count']['count_date'], '2026-10-04')
        self.assertEqual(result['items'][0]['base_quantity'], '60'); self.assertEqual(len(result['items']), 1)

    async def test_incomplete_recount_and_new_scope_hold_totals_without_old_fallback(self):
        scope = (await self.scope())[0].json()
        first = (await self.count(scope, '2026-10-04'))[0].json()
        replacement = (await self.count(scope, '2026-10-04', confirmed=False, corrects_snapshot_id=first['header']['id']))[0]
        self.assertEqual(replacement.status_code, 200, replacement.text)
        result = await self.summary()
        self.assertEqual(result['countStatus'], 'incomplete'); self.assertIsNone(result['inventoryValue'])
        self.assertEqual(result['count']['id'], replacement.json()['header']['id'])
        changed = (await self.scope(codes=('other_food',)))[0]
        self.assertEqual(changed.status_code, 200, changed.text)
        result = await self.summary()
        self.assertEqual(result['countStatus'], 'count_missing'); self.assertIsNone(result['count']); self.assertIsNone(result['inventoryValue'])

    async def test_count_date_and_timing_order_beat_backdated_entry_and_future_count(self):
        scope = (await self.scope())[0].json()
        for day, timing, value in [('2026-10-04', 'before_receipts', '60'), ('2026-10-04', 'after_receipts', '70'), ('2026-10-03', 'after_receipts', '99'), ('2026-10-06', 'before_receipts', '999')]:
            saved = (await self.count(scope, day, timing=timing, value=value))[0]
            self.assertEqual(saved.status_code, 200, saved.text)
        result = await self.summary()
        self.assertEqual(result['inventoryValue'], '70.00'); self.assertEqual(result['count']['timing'], 'after_receipts')

    async def test_received_window_and_signed_corrections_ignore_supplier_and_future_dates(self):
        old = await self.receipt(day='2026-09-05', amount='10')
        current = await self.receipt(day='2026-09-06', amount='20')
        await self.receipt(day='2026-10-05', amount='30')
        await self.receipt(day='2026-10-06', amount='100')
        preview = await self.plan(current, classification='nonfood', movement_kind='no_inventory', item_code=None, base_unit=None,
                                  received_quantity=None, received_unit=None, base_units_per_received_unit=None)
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual((await self.correct(current, preview.json())).status_code, 200)
        result = await self.summary()
        self.assertEqual(result['receivedFrom'], '2026-09-06'); self.assertEqual(result['receivedBefore'], '2026-10-06')
        self.assertEqual(Decimal(result['netFoodPurchases30']), 30)
        self.assertEqual(result['purchaseLedgerEntries30'], 3)
        other = await self.summary('rudds')
        self.assertEqual(Decimal(other['netFoodPurchases30']), 0); self.assertIsNone(other['inventoryValue'])

    async def test_actual_server_owner_item_and_ai_views_use_native_facts(self):
        import server
        previous = server.db_pg._pool; server.db_pg._pool = self.pool
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("INSERT INTO stores(id,name) VALUES('papa','Invented Papa')")
                await conn.execute("INSERT INTO invoices(store_id,vendor_id,invoice_date,total) VALUES('berts','synthetic_other','2026-10-04',9999)")
                await conn.execute("UPDATE store_items SET current_stock=9999,par=9999 WHERE store_id='berts'")
            scope = (await self.scope())[0].json()
            self.assertEqual((await self.count(scope, '2026-10-04', value='75'))[0].status_code, 200)
            await self.receipt()
            token = server._token({'id':'synthetic-owner','email':'owner@example.invalid','role':'owner','locations':[]})
            with patch('native_inventory_views.datetime') as clock:
                clock.now.return_value=datetime(2026,10,5,tzinfo=timezone.utc)
                client=httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://test',headers={'Authorization':'Bearer '+token})
                result = await client.get('/api/owner/summary')
                self.assertEqual(result.status_code, 200, result.text)
                owner = result.json(); berts = next(s for s in owner['stores'] if s['id']=='berts')
                self.assertEqual(berts['inventoryValue'], '75.00'); self.assertEqual(Decimal(berts['spend30']), 40)
                self.assertIsNone(owner['totals']['inventoryValue']); self.assertIsNone(owner['totals']['orderAlerts'])
                items = (await client.get('/api/pg/items/berts')).json()
                self.assertTrue(all(i['currentStock'] is None and i['lastCounted'] is None for i in items))
                operating = await client.get('/api/pg/purchases/berts/operating-summary')
                self.assertEqual(operating.status_code, 200, operating.text)
                summary = operating.json()
                draft = await client.post('/api/orders/berts', json={'vendor':'Invented supplier',
                    'note':'Invented reviewed quantity', 'lines':[{'itemCode':'test_food',
                    'controlNumber':'FOOD','name':'Invented food','qty':1.5,'purchaseUnit':'case','unitCost':10}]})
                self.assertEqual(draft.status_code, 200, draft.text)
                self.assertEqual(draft.json()['restaurantId'], 'berts')
                self.assertEqual(draft.json()['status'], 'draft')
                self.assertEqual(draft.json()['lines'][0]['itemCode'], 'test_food')
                self.assertEqual(draft.json()['lines'][0]['qty'], 1.5)
                self.assertEqual(draft.json()['lines'][0]['purchaseUnit'], 'case')
                self.assertEqual(Decimal((await self.summary())['netFoodPurchases30']), 40)
                await client.aclose()
            context = server.build_ai_context('berts', [], [{'invoiceDate':'2026-10-04','extendedCost':9999}], [], [], [], summary)
            self.assertIn('75.00 USD', context); self.assertIn('40 USD', context)
            self.assertNotIn('9999', context); self.assertNotIn('BELOW PAR:', context)
            self.assertIn('automatic ordering shortfalls are unknown', context)
            with self.assertRaises(server.HTTPException):
                server.build_ai_context('berts', [], [], [], [], [])
        finally:
            server.db_pg._pool = previous

    async def test_missing_native_schema_raises_instead_of_zero_or_legacy_fallback(self):
        async with self.pool.acquire() as conn:
            await conn.execute('ALTER VIEW purchasing.actual_purchase_facts RENAME TO unavailable_purchase_facts')
        with self.assertRaises(Exception) as failure:
            await self.summary()
        self.assertEqual(failure.exception.status_code, 503)
