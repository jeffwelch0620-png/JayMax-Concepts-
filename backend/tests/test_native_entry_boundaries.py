"""Invented purchase entry and legacy count boundaries on disposable PostgreSQL."""
import os
import unittest
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import httpx
import test_manual_purchases as fixtures


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PG DSN required')
class NativeEntryBoundaryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.ManualPurchaseTests.asyncSetUp
    asyncTearDown = fixtures.ManualPurchaseTests.asyncTearDown
    target = fixtures.ManualPurchaseTests.target
    body = fixtures.ManualPurchaseTests.body
    manual = fixtures.ManualPurchaseTests.manual
    post = fixtures.ManualPurchaseTests.post
    plan = fixtures.ManualPurchaseTests.plan
    correct = fixtures.ManualPurchaseTests.correct

    async def server_client(self, role='manager'):
        import server
        token = server._token({'id': 'synthetic-reviewer', 'email': 'reviewer@example.invalid', 'role': role, 'locations': ['berts']})
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url='http://test', headers={'Authorization': 'Bearer '+token})

    async def test_retired_entry_routes_cannot_change_stock_counts_or_purchases(self):
        import server
        previous = server.db_pg._pool; server.db_pg._pool = self.pool
        try:
            async with await self.server_client() as client:
                requests = [
                    ('post', '/api/pg/invoices/berts', {'vendor_id': 'synthetic_other', 'invoice_number': 'RETIRED', 'invoice_date': '2026-10-04', 'lines': []}),
                    ('put', '/api/state/berts/purchases', []),
                    ('post', '/api/counts/berts/submit', {'submittedBy': 'Invented counter', 'counts': [{'controlNumber': 'test_food', 'onHand': 999}]}),
                    ('post', '/api/staff/berts/counts/save', {'pin': '1234', 'doneBy': 'Invented counter', 'counts': [{'controlNumber': 'test_food', 'onHand': 999}]}),
                    ('post', '/api/pg/staff/berts/counts/save', {'pin': '1234', 'doneBy': 'Invented counter', 'counts': [{'controlNumber': 'test_food', 'onHand': 999}]}),
                    ('post', '/api/pg/staff/berts/counts', {'pin': '1234'}),
                ]
                for method, url, body in requests:
                    response = await client.request(method, url, json=body)
                    self.assertEqual(response.status_code, 410, (url, response.text))
            async with self.pool.acquire() as conn:
                for table in ('public.invoices', 'public.invoice_lines', 'public.inventory_count_submissions', 'purchasing.posting_batches'):
                    self.assertEqual(await conn.fetchval('SELECT count(*) FROM '+table), 0)
                self.assertEqual(await conn.fetchval("SELECT current_stock FROM store_items WHERE store_id='berts' AND item_code='test_food'"), 0)
        finally:
            server.db_pg._pool = previous

    async def test_manager_manual_capture_stays_separate_from_posting_and_pin_entry(self):
        import server
        previous = server.db_pg._pool; server.db_pg._pool = self.pool
        try:
            async with await self.server_client() as client:
                body = fixtures.record()
                captured = await client.post('/api/pg/purchases/berts/manual-records', json=body, headers={'Idempotency-Key': str(uuid4())})
                self.assertEqual(captured.status_code, 200, captured.text)
                self.assertEqual(captured.json()['manualRecord'], body)
                self.assertEqual((await client.get('/api/pg/purchases/berts/history')).json(), [])
                document = captured.json()['documents'][0]
                posted = await client.post(f"/api/pg/purchases/berts/documents/{document['id']}/post", json=fixtures.ManualPurchaseTests.body(self, document), headers={'Idempotency-Key': str(uuid4())})
                self.assertEqual(posted.status_code, 200, posted.text)
                history = (await client.get('/api/pg/purchases/berts/history')).json()
                self.assertEqual(history[0]['inventory_record_date'], '2026-10-04')
                self.assertEqual(Decimal(history[0]['inventory_cost_amount']), 40)
            for role in ('staff', 'readonly'):
                async with await self.server_client(role) as client:
                    denied = await client.post('/api/pg/purchases/berts/manual-records', json=body, headers={'Idempotency-Key': str(uuid4())})
                    self.assertEqual(denied.status_code, 403, denied.text)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url='http://test') as client:
                denied = await client.post('/api/pg/purchases/berts/manual-records', json={**body, 'pin': '1234'}, headers={'Idempotency-Key': str(uuid4())})
                self.assertEqual(denied.status_code, 401, denied.text)
            async with self.pool.acquire() as conn:
                self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.actual_purchase_facts'), 1)
                self.assertEqual(await conn.fetchval('SELECT count(*) FROM public.invoices'), 0)
                self.assertEqual(await conn.fetchval("SELECT current_stock FROM store_items WHERE store_id='berts' AND item_code='test_food'"), 0)
        finally:
            server.db_pg._pool = previous

    async def test_count_guard_is_disabled_when_actual_inventory_is_disabled(self):
        import server
        previous = server.db_pg._pool; server.db_pg._pool = self.pool
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("INSERT INTO items(code,name,base_unit) VALUES('berts_legacy','Invented legacy count','each')")
                await conn.execute("INSERT INTO store_items(store_id,item_code,counted_nightly,count_unit,base_per_count_unit) VALUES('berts','berts_legacy',true,'each',1)")
            with patch.dict(os.environ, {'ACTUAL_INVENTORY_ENABLED': 'false'}):
                async with await self.server_client() as client:
                    counts = await client.post('/api/pg/staff/berts/counts', json={'pin': '1234'})
                    self.assertEqual(counts.status_code, 200, counts.text)
                    saved = await client.post('/api/pg/staff/berts/counts/save', json={'doneBy': 'Invented counter', 'counts': [{'controlNumber': 'legacy', 'onHand': 3}]})
                    self.assertEqual(saved.status_code, 200, saved.text)
                    self.assertEqual(saved.json()['saved'], 1)
            async with self.pool.acquire() as conn:
                self.assertEqual(await conn.fetchval("SELECT current_stock FROM store_items WHERE item_code='berts_legacy'"), 3)
                self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.actual_purchase_facts'), 0)
        finally:
            server.db_pg._pool = previous

    async def test_server_history_retains_signed_corrections_and_zero_food_sources(self):
        import server
        previous = server.db_pg._pool; server.db_pg._pool = self.pool
        try:
            doc = (await self.manual()).json()['documents'][0]
            self.assertEqual((await self.post(doc)).status_code, 200)
            preview = await self.plan(doc, received_quantity='3')
            self.assertEqual(preview.status_code, 200, preview.text)
            review = preview.json()
            self.assertEqual((await self.correct(doc, review)).status_code, 200)
            zero = (await self.manual(fixtures.record(number='ZERO-FOOD', amount='0'))).json()['documents'][0]
            body = self.body(zero, movement_kind='no_inventory', item_code=None, base_unit=None, received_quantity=None, received_unit=None, base_units_per_received_unit=None)
            self.assertEqual((await self.post(zero, body)).status_code, 200)
            async with await self.server_client() as client:
                response = await client.get('/api/pg/purchases/berts/history')
                self.assertEqual(response.status_code, 200, response.text)
                rows = response.json()
                self.assertEqual(len(rows), 4)
                self.assertEqual({r['fact_kind'] for r in rows}, {'initial', 'reversal', 'replacement'})
                self.assertEqual(sum(Decimal(r['base_quantity']) for r in rows), 60)
                self.assertEqual(sum(Decimal(r['inventory_cost_amount']) for r in rows), 40)
                self.assertIsNone(next(r for r in rows if r['document_number'] == 'ZERO-FOOD')['inventory_record_date'])
        finally:
            server.db_pg._pool = previous
