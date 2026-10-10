"""Manager route coverage on full native, nonowner, invented local fixtures."""
import asyncio
import os
from uuid import uuid4

import asyncpg
import server
import runtime_permissions as candidate
import runtime_role_fixture as permissions
import hosted_staff_production as accounting
import test_menu_contract as menu
import test_shared_catalog as catalog
import test_staff_prep_tasks as roster


class MenuHistoryFixture(menu.MenuContractTests):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        # Legacy operational references must precede native cutover. Runtime
        # commands never manufacture or rewrite the captured legacy history.
        self.retained = {}
        async with self.pool.acquire() as conn:
            for table in ('count_lines', 'prep_items', 'prep_list_lines', 'prep_logs',
                          'prep_recipe_stock', 'prep_overrides', 'par_recommendations'):
                identity = await conn.fetchval("INSERT INTO dishes(store_id,name,recipe_type,yield_qty,yield_uom) VALUES('berts',$1,'prep',1,'qt') RETURNING id", 'Invented retained ' + table)
                await conn.execute("INSERT INTO dish_lines(dish_id,source_type,item_code,qty) VALUES($1,'item','test_food',1)", identity)
                self.retained[table] = str(identity)
                if table == 'count_lines':
                    session = await conn.fetchval("INSERT INTO count_sessions(store_id,count_date,count_type,status) VALUES('berts','2026-10-01','nightly_prep','submitted') RETURNING id")
                    await conn.execute("INSERT INTO count_lines(session_id,dish_id,status,qty,note) VALUES($1,$2,'counted',3,'Invented retained count')", session, identity)
                elif table == 'prep_items':
                    await conn.execute("INSERT INTO prep_items(store_id,name,recipe_id) VALUES('berts','Invented recipe prep',$1)", identity)
                elif table == 'prep_list_lines':
                    listing = await conn.fetchval("INSERT INTO prep_lists(store_id,prep_date,status) VALUES('berts','2026-10-01','released') RETURNING id")
                    await conn.execute("INSERT INTO prep_list_lines(list_id,recipe_id,name) VALUES($1,$2,'Invented retained list')", listing, identity)
                elif table == 'prep_logs':
                    await conn.execute("INSERT INTO prep_logs(store_id,kind,dish_id,name,date) VALUES('berts','batch',$1,'Invented retained production','2026-10-01')", identity)
                elif table == 'prep_recipe_stock':
                    await conn.execute("INSERT INTO prep_recipe_stock(store_id,dish_id,on_hand) VALUES('berts',$1,3)", identity)
                elif table == 'prep_overrides':
                    await conn.execute("INSERT INTO prep_overrides(store_id,date,type,recipe_id,note) VALUES('berts','2026-10-01','par',$1,'Invented retained override')", identity)
                else:
                    await conn.execute("INSERT INTO par_recommendations(id,store_id,recipe_id,recommended_par) VALUES($1,'berts',$2,3)", str(uuid4()), identity)


class ManagerMenuTests(permissions.RuntimeRoleMixin, MenuHistoryFixture):
    async def owner(self):
        return await asyncpg.connect(os.environ['NATIVE_PURCHASE_TEST_DSN'].rsplit('/', 1)[0] + '/' + self.db)

    async def facts(self):
        async with self.pool.acquire() as conn:
            return await accounting.accounting_fingerprints(conn, 'berts')

    async def history(self):
        async with self.pool.acquire() as conn:
            result = {}
            for table in self.retained:
                result[table] = await conn.fetchval("SELECT encode(sha256(convert_to(coalesce(string_agg(to_jsonb(t)::text,'' ORDER BY to_jsonb(t)::text),''),'UTF8')),'hex') FROM public." + table + ' t')
            return result

    async def test_manager_runtime_menu_definition_delete_preserves_accounting(self):
        _, opening, closing = await self.pair()
        source, *_ = await self.capture()
        self.assertEqual((await self.post(source['documents'][0])).status_code, 200)
        before = (await self.report(opening, closing)).json()
        facts = await self.facts()
        history = await self.history()
        saved = await self.create(self.dish(), await self.revision())
        self.assertEqual(saved.status_code, 200, saved.text)
        identity = saved.json()['id']
        edited = await self.changes([self.dish(id=identity, price=999,
            lines=[{'source_type': 'item', 'item_code': 'test_food', 'qty': 99}])], revision=await self.revision())
        self.assertEqual(edited.status_code, 200, edited.text)
        revision = await self.revision()
        path = '/api/pg/dishes/berts/' + identity
        self.assertEqual((await self.catalog.delete(path)).status_code, 428)
        self.assertEqual((await self.catalog.delete(path, headers={'If-Match': str(revision - 1)})).status_code, 409)
        self.assertEqual((await self.catalog.delete('/api/pg/dishes/rudds/' + identity,
            headers={'If-Match': str(await self.revision('rudds'))})).status_code, 404)
        self.assertEqual(await self.revision(), revision)
        removed = await self.catalog.delete(path, headers={'If-Match': str(revision)})
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertTrue(removed.json()['deleted'])
        self.assertEqual((await self.report(opening, closing)).json(), before)
        self.assertEqual(await self.facts(), facts)
        self.assertEqual(await self.history(), history)

    async def test_manager_runtime_menu_seven_retained_reference_types(self):
        before = await self.history()
        definitions = (await self.catalog.get('/api/pg/dishes/berts')).json()
        facts = await self.facts()
        revision = await self.revision()
        for table, identity in self.retained.items():
            with self.subTest(table=table):
                responses = (
                    await self.catalog.delete('/api/pg/dishes/berts/' + identity, headers={'If-Match': str(revision)}),
                    await self.changes(removed=[identity], revision=revision),
                    await self.replace([self.dish(id=other, name='Invented retained ' + source,
                        recipe_type='prep', yield_qty=1, yield_uom='qt')
                        for source, other in self.retained.items() if other != identity], revision),
                )
                for response in responses:
                    self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(await self.revision(), revision)
        self.assertEqual((await self.catalog.get('/api/pg/dishes/berts')).json(), definitions)
        self.assertEqual(await self.history(), before)
        self.assertEqual(await self.facts(), facts)

    async def test_manager_runtime_menu_dependency_changes_and_atomic_rollback(self):
        await menu.MenuContractTests.test_changed_prep_validates_retained_dependents_and_rolls_back(self)

    async def test_manager_runtime_menu_parallel_edits_and_role_store_boundaries(self):
        results = await asyncio.gather(self.create(self.dish(name='Invented parallel A')), self.create(self.dish(name='Invented parallel B')))
        self.assertEqual(sorted(r.status_code for r in results), [200, 409])
        accepted = next(r for r in results if r.status_code == 200)
        retained = [self.dish(id=identity, recipe_type='prep', yield_qty=1, yield_uom='qt')
                    for identity in self.retained.values()]
        self.assertEqual((await self.replace(retained + [self.dish(id=accepted.json()['id'])], 0)).status_code, 409)
        revision = await self.revision()
        before = (await self.catalog.get('/api/pg/dishes/berts')).json()
        for role, locations in (('staff', ['berts']), ('readonly', ['berts']), ('manager', ['rudds'])):
            token = server._token({'id': 'synthetic-denied-menu-' + role, 'role': role, 'email': 'invented@example.invalid', 'locations': locations})
            response = await self.catalog.post('/api/pg/dishes/berts', json=self.dish(), headers={'Authorization': 'Bearer ' + token, 'If-Match': str(revision)})
            self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(await self.revision(), revision)
        self.assertEqual((await self.catalog.get('/api/pg/dishes/berts')).json(), before)

    async def test_manager_runtime_menu_late_delete_failure_rolls_back_prior_upsert(self):
        created = await self.create(self.dish(name='Invented safe deletion'))
        self.assertEqual(created.status_code, 200, created.text)
        identity = created.json()['id']
        revision = await self.revision()
        before = (await self.catalog.get('/api/pg/dishes/berts')).json()
        facts = await self.facts()
        # Fail after the new header/lines were written and old lines deleted.
        # Only the separate local owner can install/remove the invented trigger.
        owner = await self.owner()
        try:
            await owner.execute("CREATE FUNCTION public.invented_manager_delete_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Invented late deletion failure'; END $$; CREATE TRIGGER invented_manager_delete_failure BEFORE DELETE ON public.dishes FOR EACH ROW EXECUTE FUNCTION public.invented_manager_delete_failure()")
            with self.assertRaises(asyncpg.RaiseError):
                await self.changes([self.dish(name='Invented rolled-back addition')], [identity], revision)
        finally:
            await owner.execute('DROP TRIGGER invented_manager_delete_failure ON public.dishes; DROP FUNCTION public.invented_manager_delete_failure()')
            await owner.close()
        self.assertEqual(await self.revision(), revision)
        self.assertEqual((await self.catalog.get('/api/pg/dishes/berts')).json(), before)
        self.assertEqual(await self.facts(), facts)
        owner = await self.owner()
        try:
            proof = await candidate.inspect(owner, self.runtime_role)
            self.assertEqual(proof['status'], 'passed_local_candidate', proof['issues'])
        finally:
            await owner.close()


class ManagerCatalogTests(permissions.RuntimeRoleMixin, catalog.SharedCatalogTests):
    async def test_manager_runtime_catalog_store_price_provenance_and_retirement(self):
        _, opening, closing = await self.pair()
        source, *_ = await self.capture()
        self.assertEqual((await self.post(source['documents'][0])).status_code, 200)
        report = (await self.report(opening, closing)).json()
        async with self.pool.acquire() as conn:
            facts = await accounting.accounting_fingerprints(conn, 'berts')
        self.assertEqual((await self.units())[0].status_code, 200)
        async with self.pool.acquire() as conn:
            revision = await conn.fetchval("SELECT COALESCE((SELECT revision FROM store_state WHERE store_id='rudds'),0)")
            original = dict(await conn.fetchrow("SELECT * FROM purchasing.store_vendor_items WHERE store_id='berts' AND vendor_item_id=$1", self.sku))
        linked = await self.link(revision=revision)
        self.assertEqual(linked.status_code, 200, linked.text)
        body = await self.payload()
        body['vendor_skus'][0].update(price='80.000000000000000009', available=False, preferred=False)
        edited = await self.put(body, linked.json()['revision'])
        self.assertEqual(edited.status_code, 200, edited.text)
        async with self.pool.acquire() as conn:
            self.assertEqual(dict(await conn.fetchrow("SELECT * FROM purchasing.store_vendor_items WHERE store_id='berts' AND vendor_item_id=$1", self.sku)), original)
            price = await conn.fetchrow("SELECT price,price_source,price_updated_at FROM purchasing.store_vendor_items WHERE store_id='rudds' AND vendor_item_id=$1", self.sku)
            self.assertEqual(str(price['price']), '80.000000000000000009')
            self.assertEqual(price['price_source'], 'manual')
        retried = await self.put(body, edited.json()['revision'])
        self.assertEqual(retried.status_code, 200, retried.text)
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval("SELECT price_updated_at FROM purchasing.store_vendor_items WHERE store_id='rudds' AND vendor_item_id=$1", self.sku), price['price_updated_at'])
        setup = (await self.client.get('/api/pg/purchases/berts/unit-setup')).json()
        self.assertFalse(setup['profiles'][0]['stale'])
        async with self.pool.acquire() as conn:
            revision = await conn.fetchval("SELECT revision FROM store_state WHERE store_id='rudds'")
        response = await self.catalog.delete('/api/pg/items/rudds/test_food', headers={'If-Match': str(revision)})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['retired'])
        self.assertFalse(response.json()['deleted'])
        self.assertEqual((await self.report(opening, closing)).json(), report)
        async with self.pool.acquire() as conn:
            self.assertEqual(await accounting.accounting_fingerprints(conn, 'berts'), facts)
            self.assertTrue(await conn.fetchval("SELECT active FROM store_items WHERE store_id='berts' AND item_code='test_food'"))
            self.assertFalse(await conn.fetchval("SELECT active FROM store_items WHERE store_id='rudds' AND item_code='test_food'"))


class ManagerRosterTests(permissions.RuntimeRoleMixin, roster.StaffTaskTests):
    async def roster_request(self, method, path='', body=None, token=None):
        manager = server._token({'id': 'synthetic-roster-manager', 'role': 'manager',
            'email': 'manager@example.invalid', 'locations': ['berts']})
        return await self.portal.request(method, '/api/pg/staff/berts/members' + path, json=body,
                                         headers={'Authorization': 'Bearer ' + (token or manager)})

    async def test_manager_runtime_roster_assignment_delete_race_cannot_orphan(self):
        _, task = await self.start()
        body = self.assignment_body(task)
        preview = await self.assignment_preview(body)
        self.assertEqual(preview.status_code, 200, preview.text)
        payload = dict(assignment=body, expected_review_hash=preview.json()['reviewHash'], reviewed=True)
        assigned, removed = await asyncio.gather(self.assign(payload=payload),
            self.roster_request('DELETE', '/' + str(self.member)))
        self.assertIn(assigned.status_code, (200, 409, 422), assigned.text)
        self.assertIn(removed.status_code, (200, 409), removed.text)
        async with self.pool.acquire() as conn:
            exists = await conn.fetchval('SELECT EXISTS(SELECT 1 FROM staff_members WHERE id=$1)', self.member)
            references = await conn.fetchval('SELECT count(*) FROM prep_inventory.task_assignments WHERE staff_member_id=$1', self.member)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM prep_inventory.task_assignments a LEFT JOIN staff_members s ON s.id=a.staff_member_id AND s.store_id=a.store_id WHERE a.staff_member_id IS NOT NULL AND s.id IS NULL'), 0)
        if assigned.status_code == 200:
            self.assertEqual(removed.status_code, 409)
            self.assertTrue(exists)
            self.assertEqual(references, 1)
        else:
            self.assertEqual(removed.status_code, 200)
            self.assertFalse(exists)
            self.assertEqual(references, 0)

    async def test_manager_runtime_roster_lifecycle_history_and_boundaries(self):
        created = await self.roster_request('POST', body={'name': 'Invented inactive employee', 'role': 'cook', 'active': False})
        self.assertEqual(created.status_code, 200, created.text)
        self.assertFalse(created.json()['active'])
        identity = created.json()['id']
        for method in ('PUT', 'DELETE'):
            response = await self.roster_request(method, '/not-a-uuid', body={'name': 'Invalid request', 'role': 'cook'} if method == 'PUT' else None)
            self.assertEqual(response.status_code, 422, response.text)
        updated = await self.roster_request('PUT', '/' + identity, {'name': 'Invented corrected employee', 'role': 'cook', 'active': True})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()['id'], identity)
        for role, locations in (('staff', ['berts']), ('readonly', ['berts']), ('manager', ['rudds'])):
            token = server._token({'id': 'synthetic-denied-roster-' + role, 'role': role, 'email': 'invented@example.invalid', 'locations': locations})
            for method, path, body in (('POST', '', {'name': 'Forbidden employee', 'role': 'cook'}),
                                       ('PUT', '/' + identity, {'name': 'Forbidden change', 'role': 'cook'}),
                                       ('DELETE', '/' + identity, None)):
                self.assertEqual((await self.roster_request(method, path, body, token)).status_code, 403)
        self.assertEqual((await self.roster_request('DELETE', '/' + identity)).status_code, 200)
        self.assertNotIn(identity, [r['id'] for r in (await self.roster_request('GET')).json()])
        # Roster identity with assignment history must survive deactivation and deletion.
        _, opening, closing = await self.pair()
        report = (await self.report(opening, closing)).json()
        async with self.pool.acquire() as conn:
            facts = await accounting.accounting_fingerprints(conn, 'berts')
        _, task = await self.start()
        assigned = await self.assign(self.assignment_body(task))
        self.assertEqual(assigned.status_code, 200, assigned.text)
        async with self.pool.acquire() as conn:
            prior = await conn.fetchval('SELECT to_jsonb(a)::text FROM prep_inventory.task_assignments a WHERE staff_member_id=$1', self.member)
        changed = await self.roster_request('PUT', '/' + str(self.member), {'name': 'Invented deactivated cook', 'role': 'cook', 'active': False})
        self.assertEqual(changed.status_code, 200, changed.text)
        held = await self.roster_request('DELETE', '/' + str(self.member))
        self.assertEqual(held.status_code, 409, held.text)
        self.assertEqual((await self.staff_plan(member=self.member)).status_code, 422)
        self.assertEqual((await self.report(opening, closing)).json(), report)
        async with self.pool.acquire() as conn:
            self.assertEqual(await accounting.accounting_fingerprints(conn, 'berts'), facts)
            self.assertEqual(await conn.fetchval('SELECT to_jsonb(a)::text FROM prep_inventory.task_assignments a WHERE staff_member_id=$1', self.member), prior)
            with self.assertRaises(asyncpg.ForeignKeyViolationError):
                async with conn.transaction():
                    await conn.execute('DELETE FROM staff_members WHERE id=$1', self.member)
