"""Menu graph commands against invented shared catalog/count facts only."""
import asyncio
import os
import unittest
from uuid import uuid4

from pydantic import ValidationError
import menu_contract
import test_shared_catalog as shared


class MenuModelTests(unittest.TestCase):
    def test_invalid_numbers_sources_and_yields_are_rejected(self):
        base = {'name': 'Invented dish', 'lines': [{'source_type': 'item', 'item_code': 'test_food', 'qty': 1}]}
        for quantity in (0, -1, True, float('inf'), float('nan')):
            with self.subTest(quantity=quantity), self.assertRaises(ValidationError):
                menu_contract.DishIn(**{**base, 'lines': [{**base['lines'][0], 'qty': quantity}]})
        for change in ({'name': ' '}, {'recipe_type': 'other'}, {'lines': []}, {'price': -1}, {'target_pct': 0}, {'target_pct': 101}, {'yield_qty': 0}, {'prep_par': -1}, {'price': True}, {'id': 'not-a-uuid'}, {'recipe_type': 'prep'}, {'recipe_type': 'prep', 'yield_qty': 2, 'yield_uom': 'unverified vessel'}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                menu_contract.DishIn(**{**base, **change})
        for line in ({'source_type': 'item', 'qty': 1}, {'source_type': 'item', 'item_code': 'test_food', 'prep_dish_id': 'temporary', 'qty': 1}, {'source_type': 'prep', 'item_code': 'test_food', 'prep_dish_id': 'temporary', 'qty': 1}, {'source_type': 'other', 'qty': 1}):
            with self.subTest(line=line), self.assertRaises(ValidationError):
                menu_contract.DishIn(**{**base, 'lines': [line]})
        self.assertEqual(menu_contract.DishIn(**{**base, 'price': 0}).price, 0)


class MenuGraphValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_deep_graph_is_held_before_any_write_without_recursion_failure(self):
        class ReadOnlyConnection:
            async def fetch(self, query, *args):
                return [{'item_code': 'test_food'}] if 'FROM store_items' in query else []
        rows = [menu_contract.DishIn(name='Invented ' + str(i), client_id='temp-' + str(i), recipe_type='prep', yield_qty=1, yield_uom='qt', lines=[{'source_type': 'prep', 'prep_dish_id': 'temp-' + str(i+1), 'qty': 1}] if i < 100 else [{'source_type': 'item', 'item_code': 'test_food', 'qty': 1}]) for i in range(101)]
        with self.assertRaises(menu_contract.HTTPException) as caught:
            await menu_contract.prepare(ReadOnlyConnection(), 'berts', rows, replace=True)
        self.assertEqual(caught.exception.status_code, 422)
        self.assertIn('depth', caught.exception.detail)
        prepared, _ = await menu_contract.prepare(ReadOnlyConnection(), 'berts', rows[1:], replace=True)
        self.assertEqual(len(prepared), 100)


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Dedicated disposable PostgreSQL required')
class MenuContractTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = shared.SharedCatalogTests.asyncSetUp
    asyncTearDown = shared.SharedCatalogTests.asyncTearDown
    units = shared.SharedCatalogTests.units
    pair = shared.SharedCatalogTests.pair
    scope = shared.SharedCatalogTests.scope
    count = shared.SharedCatalogTests.count
    report = shared.SharedCatalogTests.report
    capture = shared.SharedCatalogTests.capture
    post = shared.SharedCatalogTests.post
    body = shared.SharedCatalogTests.body
    target = shared.SharedCatalogTests.target
    link = shared.SharedCatalogTests.link
    link_body = shared.SharedCatalogTests.link_body

    def dish(self, **changes):
        return {'name': 'Invented menu', 'recipe_type': 'menu', 'yield_qty': 1, 'yield_uom': 'each', 'price': None, 'lines': [{'source_type': 'item', 'item_code': 'test_food', 'qty': 1, 'uom': None}], **changes}

    async def replace(self, rows, revision, store='berts'):
        return await self.catalog.put('/api/pg/dishes/' + store, json=rows, headers={'If-Match': str(revision)})

    async def create(self, row, revision=0, store='berts'):
        return await self.catalog.post('/api/pg/dishes/' + store, json=row, headers={'If-Match': str(revision)})

    async def revision(self, store='berts'):
        async with self.pool.acquire() as conn:
            return await conn.fetchval('SELECT COALESCE((SELECT revision FROM store_state WHERE store_id=$1),0)', store)

    async def changes(self, upserts=(), removed=(), revision=0, store='berts'):
        return await self.catalog.post('/api/pg/dishes/' + store + '/changes',
            json={'upserts': list(upserts), 'delete_ids': list(removed)}, headers={'If-Match': str(revision)})

    async def test_unrelated_incomplete_definition_is_retained_without_rewriting(self):
        async with self.pool.acquire() as conn:
            old = await conn.fetchrow("INSERT INTO dishes(store_id,name,recipe_type) VALUES('berts','Old incomplete prep','prep') RETURNING *")
        created = await self.create(self.dish())
        self.assertEqual(created.status_code, 200, created.text)
        identity = created.json()['id']
        edited = await self.changes([self.dish(id=identity, name='Edited plate')], revision=1)
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(len(edited.json()['dishes']), 2)
        async with self.pool.acquire() as conn:
            self.assertEqual(dict(await conn.fetchrow('SELECT * FROM dishes WHERE id=$1', old['id'])), dict(old))
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM dish_lines WHERE dish_id=$1', old['id']), 0)
        strict = await self.replace([self.dish(id=identity), self.dish(id=str(old['id']), recipe_type='prep', yield_qty=1, yield_uom='qt', lines=[])], 2)
        self.assertEqual(strict.status_code, 422, strict.text)
        noop = await self.changes(revision=2)
        self.assertEqual(noop.status_code, 200, noop.text)
        removed = await self.changes(removed=[str(old['id'])], revision=3)
        self.assertEqual(removed.status_code, 200, removed.text)

    async def test_changed_prep_validates_retained_dependents_and_rolls_back(self):
        saved = await self.changes([self.dish(client_id='plate', name='Dependent plate', lines=[{'source_type': 'prep', 'prep_dish_id': 'sauce', 'qty': 1, 'uom': 'qt'}]),
            self.dish(client_id='sauce', name='Sauce', recipe_type='prep', yield_qty=2, yield_uom='qt')])
        self.assertEqual(saved.status_code, 200, saved.text)
        mapping = saved.json()['clientIds']
        self.assertEqual(set(mapping), {'plate', 'sauce'})
        before = (await self.catalog.get('/api/pg/dishes/berts')).json()
        bad = await self.changes([self.dish(id=mapping['sauce'], recipe_type='prep', yield_qty=2, yield_uom='lb')], revision=1)
        self.assertEqual(bad.status_code, 422, bad.text)
        self.assertIn('Dependent plate', bad.json()['detail'])
        self.assertIn(mapping['plate'], bad.json()['detail'])
        self.assertEqual((await self.catalog.get('/api/pg/dishes/berts')).json(), before)
        deleted = await self.changes(removed=[mapping['sauce']], revision=1)
        self.assertEqual(deleted.status_code, 422, deleted.text)
        self.assertEqual(await self.revision(), 1)
        bad_source = await self.changes([self.dish(id=mapping['sauce'], recipe_type='prep', yield_qty=2, yield_uom='qt', lines=[{'source_type': 'item', 'item_code': 'not_here', 'qty': 1}])], revision=1)
        self.assertEqual(bad_source.status_code, 422, bad_source.text)
        self.assertEqual((await self.catalog.get('/api/pg/dishes/berts')).json(), before)

    async def test_changes_require_current_revision_store_identity_and_retained_history(self):
        self.assertEqual((await self.catalog.post('/api/pg/dishes/berts/changes', json={})).status_code, 428)
        saved = await self.changes([self.dish(client_id='new', recipe_type='prep', yield_qty=1, yield_uom='qt')])
        self.assertEqual(saved.status_code, 200, saved.text)
        identity = saved.json()['clientIds']['new']
        self.assertEqual((await self.changes(revision=0)).status_code, 409)
        self.assertEqual((await self.changes(removed=[str(uuid4())], revision=1)).status_code, 422)
        self.assertEqual((await self.changes(removed=[identity], store='rudds')).status_code, 422)
        self.assertEqual((await self.changes(removed=[identity, identity], revision=1)).status_code, 422)
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO prep_logs(store_id,kind,dish_id,name,date) VALUES('berts','batch',$1,'Invented history','2026-10-06')", identity)
        before = (await self.catalog.get('/api/pg/dishes/berts')).json()
        held = await self.changes(removed=[identity], revision=1)
        self.assertEqual(held.status_code, 422, held.text)
        self.assertIn('history', held.json()['detail'])
        self.assertEqual((await self.catalog.get('/api/pg/dishes/berts')).json(), before)
        self.assertEqual(await self.revision(), 1)

    async def test_changes_check_incomplete_dependencies_and_cycles_with_recipe_identity(self):
        async with self.pool.acquire() as conn:
            old = await conn.fetchval("INSERT INTO dishes(store_id,name,recipe_type) VALUES('berts','Unfinished sauce','prep') RETURNING id")
        response = await self.changes([self.dish(lines=[{'source_type': 'prep', 'prep_dish_id': str(old), 'qty': 1}])])
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn('Unfinished sauce', response.json()['detail'])
        self.assertIn(str(old), response.json()['detail'])
        a = self.dish(name='Cycle A', client_id='a', recipe_type='prep', yield_qty=1, yield_uom='qt', lines=[{'source_type': 'prep', 'prep_dish_id': 'b', 'qty': 1}])
        b = self.dish(name='Cycle B', client_id='b', recipe_type='prep', yield_qty=1, yield_uom='qt', lines=[{'source_type': 'prep', 'prep_dish_id': 'a', 'qty': 1}])
        cyclic = await self.changes([a, b])
        self.assertEqual(cyclic.status_code, 422, cyclic.text)
        self.assertIn('Circular', cyclic.json()['detail'])
        self.assertEqual(await self.revision(), 0)
        self.assertEqual(len((await self.catalog.get('/api/pg/dishes/berts')).json()), 1)

    async def test_invalid_http_commands_leave_headers_lines_and_revision_unchanged(self):
        for change in ({'lines': []}, {'price': '-Infinity'}, {'lines': [{'source_type': 'item', 'item_code': 'test_food', 'qty': 'NaN'}]}, {'lines': [{'source_type': 'item', 'item_code': 'test_food', 'qty': 1, 'uom': 'lb'}]}, {'lines': [{'source_type': 'prep', 'prep_dish_id': str(uuid4()), 'qty': 1}]}):
            response = await self.create(self.dish(**change))
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual((await self.catalog.get('/api/pg/dishes/berts')).json(), [])
        self.assertEqual(await self.revision(), 0)
        async with self.pool.acquire() as conn:
            incomplete = await conn.fetchval("INSERT INTO dishes(store_id,name,recipe_type) VALUES('berts','Old incomplete prep','prep') RETURNING id")
            await conn.execute("INSERT INTO dish_lines(dish_id,source_type,item_code,qty) VALUES($1,'item','test_food',1)", incomplete)
        bad_parent = await self.create(self.dish(lines=[{'source_type': 'prep', 'prep_dish_id': str(incomplete), 'qty': 1}]))
        self.assertEqual(bad_parent.status_code, 422, bad_parent.text)
        self.assertEqual(await self.revision(), 0)
        self.assertEqual(len((await self.catalog.get('/api/pg/dishes/berts')).json()), 1)

    async def test_cross_store_sources_and_recipe_ids_are_held(self):
        for code in ('other_store_food', 'rudds_R01'):
            response = await self.create(self.dish(lines=[{'source_type': 'item', 'item_code': code, 'qty': 1}]))
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual((await self.link()).status_code, 200)
        unlinked = await self.create(self.dish(lines=[{'source_type': 'item', 'item_code': 'other_food', 'qty': 1}]), revision=1, store='rudds')
        self.assertEqual(unlinked.status_code, 422, unlinked.text)
        foreign = await self.create(self.dish(recipe_type='prep', yield_qty=2, yield_uom='qt'), revision=1, store='rudds')
        self.assertEqual(foreign.status_code, 200, foreign.text)
        response = await self.create(self.dish(lines=[{'source_type': 'prep', 'prep_dish_id': foreign.json()['id'], 'qty': 1}]))
        self.assertEqual(response.status_code, 422, response.text)
        response = await self.create(self.dish(id=foreign.json()['id']))
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(await self.revision(), 0)

    async def test_unsorted_new_nested_graph_resolves_every_temporary_id_and_unit_field(self):
        menu = self.dish(client_id='menu-temp', lines=[{'source_type': 'prep', 'prep_dish_id': 'sauce-temp', 'qty': 2, 'uom': 'qt'}])
        sauce = self.dish(name='Invented sauce', recipe_type='prep', yield_qty=4, yield_uom='qt', client_id='sauce-temp', lines=[{'source_type': 'prep', 'prep_dish_id': 'base-temp', 'qty': 1}])
        base = self.dish(name='Invented base', recipe_type='prep', yield_qty=2, yield_uom='qt', client_id='base-temp')
        result = await self.replace([menu, sauce, base], 0)
        self.assertEqual(result.status_code, 200, result.text)
        rows = result.json()['dishes']
        self.assertEqual([r['name'] for r in rows], ['Invented menu', 'Invented sauce', 'Invented base'])
        self.assertEqual(rows[0]['lines'][0]['prepDishId'], rows[1]['id'])
        self.assertEqual(rows[1]['lines'][0]['prepDishId'], rows[2]['id'])
        self.assertEqual(rows[0]['lines'][0]['uom'], 'qt')
        self.assertIsNone(rows[2]['price'])
        bad_menu = self.dish(id=rows[0]['id'], lines=[{'source_type': 'prep', 'prep_dish_id': rows[1]['id'], 'qty': 2, 'uom': 'lb'}])
        rejected = await self.create(bad_menu, revision=1)
        self.assertEqual(rejected.status_code, 422, rejected.text)
        self.assertEqual(await self.revision(), 1)

    async def test_cycles_missing_retained_children_and_duplicate_identity_are_atomic(self):
        a = self.dish(recipe_type='prep', yield_qty=1, yield_uom='qt', client_id='a')
        b = self.dish(name='Second', recipe_type='prep', yield_qty=1, yield_uom='qt', client_id='b')
        cyclic_a = {**a, 'lines': [{'source_type': 'prep', 'prep_dish_id': 'b', 'qty': 1}]}
        cyclic_b = {**b, 'lines': [{'source_type': 'prep', 'prep_dish_id': 'a', 'qty': 1}]}
        for rows in ([cyclic_a, cyclic_b], [a, {**b, 'client_id': 'a'}]):
            response = await self.replace(rows, 0)
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(await self.revision(), 0)
        created = (await self.replace([a], 0)).json()['dishes'][0]
        child = self.dish(id=created['id'], recipe_type='prep', yield_qty=1, yield_uom='qt')
        parent = self.dish(lines=[{'source_type': 'prep', 'prep_dish_id': created['id'], 'qty': 1}])
        good = await self.replace([child, parent], 1)
        self.assertEqual(good.status_code, 200, good.text)
        before = (await self.catalog.get('/api/pg/dishes/berts')).json()
        parent['id'] = good.json()['dishes'][1]['id']
        for rows in ([parent], [self.dish(id=created['id']), parent], [child, child, parent]):
            bad = await self.replace(rows, 2)
            self.assertEqual(bad.status_code, 422, bad.text)
            self.assertEqual((await self.catalog.get('/api/pg/dishes/berts')).json(), before)
            self.assertEqual(await self.revision(), 2)

    async def test_parallel_granular_commands_observe_revision_and_invalidate_bulk_save(self):
        results = await asyncio.gather(self.create(self.dish(name='First')), self.create(self.dish(name='Second')))
        self.assertEqual(sorted(r.status_code for r in results), [200, 409])
        self.assertEqual((await self.replace([], 0)).status_code, 409)
        self.assertEqual(len((await self.catalog.get('/api/pg/dishes/berts')).json()), 1)

    async def test_definition_changes_leave_actual_report_and_purchase_facts_unchanged(self):
        _, opening, closing = await self.pair()
        source, *_ = await self.capture()
        self.assertEqual((await self.post(source['documents'][0])).status_code, 200)
        before = (await self.report(opening, closing)).json()
        current = await self.revision()
        saved = await self.create(self.dish(), current)
        self.assertEqual(saved.status_code, 200, saved.text)
        edited = await self.replace([self.dish(id=saved.json()['id'], price=999, lines=[{'source_type': 'item', 'item_code': 'test_food', 'qty': 99}])], saved.json()['revision'])
        self.assertEqual(edited.status_code, 200, edited.text)
        deleted = await self.catalog.delete('/api/pg/dishes/berts/' + saved.json()['id'], headers={'If-Match': str(edited.json()['revision'])})
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual((await self.report(opening, closing)).json(), before)

    async def test_omitted_recipe_group_can_be_deleted_but_operating_history_prevents_loss(self):
        prep = self.dish(recipe_type='prep', yield_qty=1, yield_uom='qt', client_id='p')
        menu = self.dish(name='Plate', lines=[{'source_type': 'prep', 'prep_dish_id': 'p', 'qty': 1}])
        saved = await self.replace([menu, prep], 0)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual((await self.replace([], 1)).status_code, 200)
        created = await self.create(prep, 2)
        self.assertEqual(created.status_code, 200, created.text)
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO prep_logs(store_id,kind,dish_id,name,date) VALUES('berts','batch',$1,'Invented history','2026-10-06')", created.json()['id'])
        before = (await self.catalog.get('/api/pg/dishes/berts')).json()
        response = await self.replace([], 3)
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual((await self.catalog.get('/api/pg/dishes/berts')).json(), before)
        self.assertEqual(await self.revision(), 3)
