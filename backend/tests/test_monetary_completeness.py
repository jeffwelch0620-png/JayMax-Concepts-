"""Fictional malformed planning evidence never becomes zero or a partial cost."""
import copy
import json
import unittest
from unittest.mock import AsyncMock, patch

import server
from test_backend_planning_prices import food


def plate(**changes):
    return dict(id='plate', name='Fictional plate', recipeType='menu', price=10,
                lines=[dict(sourceType='item', controlNumber='TEST', qty=2)], **changes)


class MonetaryCompletenessTests(unittest.IsolatedAsyncioTestCase):
    def test_pack_and_portion_families_and_positive_metadata_are_required(self):
        for pack, unit, portion, portion_unit in [
            (5, 'lb', 4, 'fl oz'), (5, 'unknown', 1, 'unknown'),
            (5, None, 1, 'each'), (0, 'each', 1, 'each'),
            (-1, 'each', -1, 'each'), (1, 'each', None, 'each'),
            (1, 'each', 0, 'each'), (1, [], 1, 'each'),
        ]:
            with self.subTest(values=(pack, unit, portion, portion_unit)):
                self.assertIsNone(server.calc_ppu(pack, unit, portion, portion_unit))
        self.assertEqual(server.calc_ppu(5, 'lb', 4, 'oz'), 20)
        for price in (0, 20):
            row = food(price, portionUOM='fl oz')
            before = copy.deepcopy(row)
            self.assertIsNone(server.item_derived(row)['costPerPortion'])
            self.assertIsNone(server.adj_value(dict(qty=1, qtyBasis='purchase', reason='waste'), row))
            self.assertEqual(row, before)
        row = food(-1)
        self.assertIsNone(server.item_derived(row)['costPerPortion'])

    def test_missing_malformed_ambiguous_and_cyclic_recipes_are_not_free(self):
        ingredient = food(8)
        prep = dict(id='prep', name='Fictional prep', recipeType='prep', yieldQty=2,
                    yieldUOM='each', lines=[dict(controlNumber='TEST', qty=1)])
        parent = plate(); parent['lines'] = [dict(sourceType='prep', recipeId='prep', qty=2)]
        cases = [None, dict(id='empty', lines=[]), dict(id='bad', lines={}),
                 dict(id='bad', lines=[None]), dict(id='bad', lines=['TEST']),
                 dict(id='bad', lines=[dict(controlNumber='MISSING', qty=1)]),
                 dict(id='bad', lines=[dict(sourceType='bogus', controlNumber='TEST', qty=1)]),
                 dict(id='bad', lines=[dict(controlNumber='TEST', recipeId='prep', qty=1)]),
                 dict(id='bad', lines=[dict(controlNumber='TEST', qty=1, uom='lb')]),
                 dict(id='bad', lines=[dict(controlNumber='TEST', qty=0)]),
                 dict(id='bad', lines=[dict(controlNumber='TEST', qty=True)]),
                 dict(id='bad', lines=[dict(sourceType='prep', recipeId='MISSING', qty=1)])]
        for recipe in cases:
            with self.subTest(recipe=recipe):
                result = server.recipe_cost_summary(recipe, [ingredient], [prep])
                self.assertIsNone(result['totalCost']); self.assertFalse(result['complete'])
                self.assertTrue(result['issues']); json.dumps(result, allow_nan=False)
        self.assertEqual(server.recipe_cost(parent, [ingredient], [prep]), 2)
        for change in (dict(yieldQty=0), dict(yieldQty=None), dict(yieldUOM=None),
                       dict(recipeType='menu'), dict(lines=[dict(sourceType='prep', recipeId='prep', qty=1)])):
            with self.subTest(change=change):
                self.assertIsNone(server.recipe_cost(parent, [ingredient], [{**prep, **change}]))
        self.assertIsNone(server.recipe_cost(parent, [ingredient], [prep, copy.deepcopy(prep)]))
        self.assertIsNone(server.recipe_cost(plate(), [ingredient, copy.deepcopy(ingredient)], []))
        chain = [dict(id=f'p{i}', recipeType='prep', yieldQty=1, yieldUOM='each',
                      lines=[dict(sourceType='prep', recipeId=f'p{i+1}', qty=1)] if i < 100 else prep['lines']) for i in range(101)]
        self.assertIsNone(server.recipe_cost(chain[0], [ingredient], chain))

    def test_canonical_identity_is_authoritative_and_missing_prices_poison_aggregate(self):
        ingredient = {**food(8), 'code': 'canonical', 'controlNumber': 'LOCAL'}
        menu = plate(); menu['lines'] = [dict(itemCode='canonical', qty=2)]
        self.assertEqual(server.recipe_cost(menu, [ingredient], []), 4)
        self.assertIsNone(server.recipe_cost({**menu, 'lines': [dict(itemCode='missing', controlNumber='LOCAL', qty=2)]}, [ingredient], []))
        self.assertEqual(server.recipe_cost({**menu, 'lines': [dict(itemCode='canonical', controlNumber='OLD_ALIAS', qty=2)]}, [ingredient], []), 4)
        missing = {**food(None), 'controlNumber': 'MISSING_PRICE'}
        menu['lines'].append(dict(controlNumber='MISSING_PRICE', qty=1))
        self.assertIsNone(server.recipe_cost(menu, [ingredient, missing], []))
        missing['vendorSkus'][0]['price'] = 0
        self.assertEqual(server.recipe_cost(menu, [ingredient, missing], []), 4)
        for adj in [dict(qty=None, qtyBasis='portion', reason='waste'),
                    dict(qty=-1, qtyBasis='portion', reason='waste'),
                    dict(qty=1, qtyBasis='unknown', reason='waste'),
                    dict(qty=1, qtyBasis='portion', reason='unknown')]:
            self.assertIsNone(server.adj_value(adj, ingredient))

    async def test_active_summary_and_ai_do_not_publish_partial_estimates(self):
        known = plate()
        missing = {**plate(), 'id': 'missing', 'name': 'Missing recipe',
                   'lines': [dict(controlNumber='NO_MATCH', qty=1)]}
        native = dict(inventoryValue='145.000000000001', netFoodPurchases30='178.000000000002',
                      count=None, countStatus='count_missing', scope=None,
                      receivedFrom='2026-10-01', receivedBefore='2026-10-31')
        rows = [food(8)]
        adjustments = [dict(controlNumber='NO_MATCH', date='9999-01-01', qty=1,
                            qtyBasis='portion', reason='waste')]
        snapshot = copy.deepcopy((rows, known, missing, native, adjustments))
        with patch.object(server, 'USE_PG', True), patch.object(server, 'ensure_seed', AsyncMock()), \
             patch.object(server, '_pg_owner_view', AsyncMock(return_value=(rows, [], [known, missing], None))), \
             patch.object(server, '_adjustments_for', AsyncMock(return_value=adjustments)), \
             patch.object(server.purchase_api, 'enabled', return_value=True), \
             patch('native_inventory_views.read_operating_summary', AsyncMock(return_value=native)), \
             patch.object(server.db_pg, 'pool', return_value=object()):
            result = await server.store_summary(dict(id='berts'))
            self.assertEqual(result['inventoryValue'], native['inventoryValue'])
            self.assertEqual(result['spend30'], native['netFoodPurchases30'])
            self.assertFalse(result['planningCostsAvailable'])
            self.assertIsNone(result['avgFoodCost']); self.assertIsNone(result['waste30'])
            bad = next(row for row in result['topCostDishes'] if row['name'] == 'Missing recipe')
            self.assertIsNone(bad['cost']); self.assertTrue(bad['costIssues'])
            context = server.build_ai_context('berts', rows, [], [known, missing], adjustments, None, native)
            self.assertIn('Missing recipe: price $10.00, plate cost Unknown, FC unavailable', context)
            self.assertIn('Planning cost needs review:', context)
            self.assertIn('last 30 days: Unknown', context)
        self.assertEqual((rows, known, missing, native, adjustments), snapshot)

    async def test_unknown_selling_price_does_not_reduce_average_coverage(self):
        dishes = [plate(), {**plate(), 'id':'no-price', 'price':None}]
        with patch.object(server, 'USE_PG', True), patch.object(server, 'ensure_seed', AsyncMock()), \
             patch.object(server, '_pg_owner_view', AsyncMock(return_value=([food(8)], [], dishes, []))), \
             patch.object(server, '_adjustments_for', AsyncMock(return_value=[])), \
             patch.object(server.purchase_api, 'enabled', return_value=False):
            result = await server.store_summary(dict(id='berts'))
        self.assertTrue(result['planningCostsAvailable']); self.assertIsNone(result['avgFoodCost'])
        self.assertIsNone(next(row for row in result['topCostDishes'] if row['price'] is None)['pct'])
