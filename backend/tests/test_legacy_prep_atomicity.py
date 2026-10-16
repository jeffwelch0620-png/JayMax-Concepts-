"""Pre-cutover prep only; fictional facts in owned disposable PostgreSQL."""
import os
import unittest
from decimal import Decimal
import httpx
import server
import test_legacy_prep_cutover as fixtures


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class LegacyPrepAtomicityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await fixtures.LegacyPrepCutoverTests.asyncSetUp(self)
        self.addAsyncCleanup(fixtures.LegacyPrepCutoverTests.asyncTearDown, self)
        async with self.pool.acquire() as conn:
            # other_food sorts before test_food. The later ingredient must not
            # cause a partial deduction of the earlier, valid ingredient.
            await conn.execute("UPDATE store_items SET current_stock=10 WHERE store_id='berts'")
            await conn.execute("UPDATE vendor_items SET price=3,base_per_purchase_unit=1,preferred=true WHERE item_code='test_food'")
            await conn.execute("INSERT INTO vendor_items(vendor_id,vendor_sku,item_code,purchase_unit,price,base_per_purchase_unit,preferred) VALUES('synthetic_other','ATOMIC-ONLY','other_food','case',2,1,true)")
            await conn.execute("INSERT INTO dish_lines(dish_id,source_type,item_code,qty) VALUES($1,'item','other_food',1),($1,'item','test_food',2)", self.dish)
            self.list_id = await conn.fetchval("INSERT INTO prep_lists(store_id,prep_date,status) VALUES('berts','2026-10-16','released') RETURNING id")
            self.task_id = await conn.fetchval("INSERT INTO prep_list_lines(list_id,recipe_id,task_type,name,batches_planned,batches_done) VALUES($1,$2,'batch','Fictional atomicity task',3,0) RETURNING id", self.list_id, self.dish)
        self.direct = '/api/pg/prep/berts/complete'
        self.task = f'/api/pg/preplists/berts/{self.list_id}/task/{self.task_id}/complete'

    async def snapshot(self):
        async with self.pool.acquire() as conn:
            return {table: await conn.fetchval('SELECT jsonb_agg(to_jsonb(r) ORDER BY to_jsonb(r)::text) FROM '+table+' r')
                    for table in ('store_items','prep_recipe_stock','prep_logs','prep_list_lines','prep_lists',
                                  'purchasing.actual_purchase_facts')}

    async def post(self, task=False, **changes):
        return await self.web.post(self.task if task else self.direct,
            json={**({'doneBy':'Fictional tester'} if task else {'recipeId':str(self.dish)}), 'batches':1, **changes})

    async def write_tripwire(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""CREATE FUNCTION reject_early_prep_write() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'Fictional preflight test: unexpected stock write'; END $$;
                CREATE TRIGGER reject_early_prep_write BEFORE UPDATE ON store_items
                FOR EACH ROW EXECUTE FUNCTION reject_early_prep_write()""")

    async def invalid_later_ingredient(self, task):
        await self.write_tripwire()
        for price in ('1e400','1e-400','1e308'):
            with self.subTest(price=price):
                async with self.pool.acquire() as conn:
                    await conn.execute("UPDATE vendor_items SET price=$1 WHERE item_code='test_food'", Decimal(price))
                before=await self.snapshot()
                result=await self.post(task)
                self.assertEqual(result.status_code,422,result.text)
                self.assertIn('supported calculation range',result.text)
                self.assertEqual(await self.snapshot(),before)

    async def test_direct_later_invalid_cost_or_arithmetic_reaches_no_stock_writes(self):
        await self.invalid_later_ingredient(False)

    async def test_task_later_invalid_cost_or_arithmetic_reaches_no_stock_writes(self):
        await self.invalid_later_ingredient(True)

    async def missing_later_price(self,task):
        await self.write_tripwire()
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE vendor_items SET price=NULL WHERE item_code='test_food'")
        before=await self.snapshot()
        result=await self.post(task)
        self.assertEqual(result.status_code,422,result.text)
        self.assertEqual(await self.snapshot(),before)

    async def test_direct_missing_later_price_is_refused_before_any_stock_write(self):
        await self.missing_later_price(False)

    async def test_task_missing_later_price_is_refused_before_any_stock_write(self):
        await self.missing_later_price(True)

    async def test_legacy_helper_ignores_unavailable_supplier_and_keeps_selected_unknown(self):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE vendor_items SET price=NULL,preferred=true WHERE item_code='test_food'")
            await conn.execute("""INSERT INTO vendor_items(vendor_id,vendor_sku,item_code,purchase_unit,price,base_per_purchase_unit,preferred,available)
                VALUES('synthetic_other','UNAVAILABLE-PRICE','test_food','case',999,1,true,false),
                      ('synthetic_other','ALTERNATE-PRICE','test_food','case',12,1,false,true)""")
            unknown=await server._pg_item_derived(conn,'test_food')
            self.assertTrue(unknown['priceMissing']);self.assertIsNone(unknown['costPerPortion'])
            await conn.execute("UPDATE vendor_items SET price=0 WHERE item_code='test_food' AND vendor_sku='00001'")
            zero=await server._pg_item_derived(conn,'test_food')
            self.assertFalse(zero['priceMissing']);self.assertEqual(zero['costPerPortion'],0)
            await conn.execute("UPDATE vendor_items SET available=false WHERE item_code='test_food'")
            unavailable=await server._pg_item_derived(conn,'test_food')
            self.assertTrue(unavailable['priceMissing']);self.assertIsNone(unavailable['costPerPortion'])

    async def happy(self, task):
        result=await self.post(task)
        self.assertEqual(result.status_code,200,result.text)
        async with self.pool.acquire() as conn:
            stocks=await conn.fetch("SELECT item_code,current_stock FROM store_items WHERE store_id='berts' ORDER BY item_code")
            self.assertEqual([(r['item_code'],r['current_stock']) for r in stocks],
                             [('other_food',9),('prep_sauce',10),('test_food',8)])
            self.assertEqual(await conn.fetchval('SELECT on_hand FROM prep_recipe_stock WHERE dish_id=$1',self.dish),16)
            logs=await conn.fetch('SELECT * FROM prep_logs')
            self.assertEqual(len(logs),1);self.assertEqual(logs[0]['total_cost'],8)
            self.assertEqual([u['controlNumber'] for u in logs[0]['usage']],['other_food','test_food'])
            self.assertEqual(await conn.fetchval('SELECT batches_done FROM prep_list_lines WHERE id=$1',self.task_id),1 if task else 0)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.actual_purchase_facts'),0)

    async def test_direct_happy_path_deducts_both_and_writes_one_log(self):
        await self.happy(False)

    async def test_task_happy_path_deducts_both_and_updates_progress_once(self):
        await self.happy(True)

    async def later_database_failure(self, task):
        before=await self.snapshot()
        async with self.pool.acquire() as conn:
            # The helper inserts its log after both stock updates and the prep
            # stock upsert. A database error here must undo every earlier write.
            await conn.execute("""CREATE FUNCTION reject_prep_log() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'Fictional late database failure' USING ERRCODE='23514'; END $$;
                CREATE TRIGGER reject_prep_log BEFORE INSERT ON prep_logs
                FOR EACH ROW EXECUTE FUNCTION reject_prep_log()""")
        token=server._token({'id':'fictional-owner','email':'owner@example.invalid','role':'owner','locations':[]})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app,raise_app_exceptions=False),
            base_url='http://test',headers={'Authorization':'Bearer '+token}) as web:
            result=await web.post(self.task if task else self.direct,
                json={**({'doneBy':'Fictional tester'} if task else {'recipeId':str(self.dish)}),'batches':1})
        self.assertEqual(result.status_code,500,result.text)
        self.assertEqual(await self.snapshot(),before)

    async def test_direct_late_database_error_rolls_back_all_facts(self):
        await self.later_database_failure(False)

    async def test_task_late_database_error_rolls_back_all_facts_and_progress(self):
        await self.later_database_failure(True)

    async def test_unsafe_output_or_container_is_refused_before_any_stock_write(self):
        await self.write_tripwire()
        for changes in ({'batches':'1e400'}, {'containers':[{'size':'1e400','count':1}]},
                        {'batches':1e308}):
            with self.subTest(changes=changes):
                before=await self.snapshot();result=await self.post(**changes)
                self.assertEqual(result.status_code,422,result.text)
                self.assertEqual(await self.snapshot(),before)
