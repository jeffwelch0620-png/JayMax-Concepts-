"""Partial item edits are atomic and preserve omitted catalog and count history."""
import os
import unittest
import test_shared_catalog as shared


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class ItemChangesTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = shared.SharedCatalogTests.asyncSetUp
    asyncTearDown = shared.SharedCatalogTests.asyncTearDown
    units = shared.SharedCatalogTests.units
    payload = shared.SharedCatalogTests.payload

    async def snapshot(self):
        async with self.pool.acquire() as conn:
            return [await conn.fetch(query) for query in (
                'SELECT * FROM items ORDER BY code',
                'SELECT * FROM store_items ORDER BY store_id,item_code',
                'SELECT * FROM purchasing.store_vendor_items ORDER BY store_id,vendor_item_id',
                'SELECT * FROM store_state ORDER BY store_id')]

    async def change(self, upserts=None, retired=None, revision=0):
        return await self.catalog.post('/api/pg/items/berts/changes',
            json=dict(upserts=upserts or [], retire_codes=retired or []), headers={'If-Match':str(revision)})

    async def test_partial_edit_preserves_omitted_item_and_physical_count_metadata(self):
        before = await self.snapshot()
        body = await self.payload('berts', par=7)
        response = await self.change([body])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['revision'], 1)
        after = await self.snapshot()
        for rows_before, rows_after in zip(before[:3], after[:3]):
            self.assertEqual([dict(row) for row in rows_before if row.get('code',row.get('item_code')) == 'other_food'],
                             [dict(row) for row in rows_after if row.get('code',row.get('item_code')) == 'other_food'])
        old = next(row for row in before[1] if row['store_id']=='berts' and row['item_code']=='test_food')
        new = next(row for row in after[1] if row['store_id']=='berts' and row['item_code']=='test_food')
        for key in ('count_unit','base_per_count_unit','current_stock','last_counted','last_counted_by','counted_nightly'):
            self.assertEqual(new[key],old[key],key)
        self.assertEqual(new['par'],7)

    async def test_invalid_later_upsert_rolls_back_earlier_edit_and_revision(self):
        before = await self.snapshot()
        first = await self.payload('berts', par=7)
        bad = {**first, 'code':'invalid_new_food', 'control_number':'INVALID', 'vendor_skus':[{
            **first['vendor_skus'][0], 'vendor_id':'nonexistent_vendor', 'vendor_sku':'INVALID'}]}
        response = await self.change([first,bad])
        self.assertGreaterEqual(response.status_code,400,response.text)
        self.assertEqual(await self.snapshot(),before)

    async def test_duplicate_overlap_unlinked_retirement_and_stale_revision_do_not_write(self):
        before = await self.snapshot(); body = await self.payload('berts')
        for edits,retired,revision,status in (([body,body],[],0,422),([body],['test_food'],0,422),
                ([],['test_food','test_food'],0,422),([],['unknown'],0,422),([body],[],99,409)):
            with self.subTest(retired=retired,revision=revision):
                response = await self.change(edits,retired,revision)
                self.assertEqual(response.status_code,status,response.text)
                self.assertEqual(await self.snapshot(),before)

    async def test_explicit_retirement_keeps_stock_and_count_participation(self):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE store_items SET current_stock=3,counted_nightly=true WHERE store_id='berts' AND item_code='test_food'")
        before = await self.snapshot()
        response = await self.change(retired=['test_food'])
        self.assertEqual(response.status_code,200,response.text)
        after = await self.snapshot()
        row = next(row for row in after[1] if row['store_id']=='berts' and row['item_code']=='test_food')
        self.assertFalse(row['active']); self.assertFalse(row['order_enabled']); self.assertFalse(row['sales_tracked'])
        self.assertTrue(row['counted_nightly']); self.assertEqual(row['current_stock'],3)
        self.assertEqual(before[0],after[0]); self.assertEqual(before[2],after[2])

    async def test_missing_revision_and_wrong_location_authorization_are_held(self):
        import server
        before = await self.snapshot()
        response = await self.catalog.post('/api/pg/items/berts/changes',json=dict(upserts=[],retire_codes=[]))
        self.assertEqual(response.status_code,428,response.text)
        token = server._token(dict(id='invented_other_manager',email='other@example.invalid',role='manager',locations=['rudds']))
        response = await self.catalog.post('/api/pg/items/berts/changes',json=dict(upserts=[],retire_codes=[]),
            headers={'Authorization':'Bearer '+token,'If-Match':'0'})
        self.assertEqual(response.status_code,403,response.text)
        self.assertEqual(await self.snapshot(),before)
