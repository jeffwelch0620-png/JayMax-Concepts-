"""Fictional missing-price estimates stay independent of actual accounting."""
import copy
import json
import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import planning_numbers as planning
import server


def food(price=None, **changes):
    return {**dict(controlNumber='TEST', name='Fictional food', currentStock=2,
        packCount=2, unitQty=4, unitUOM='each', portionSize=2, portionUOM='each',
        vendorSkus=[dict(price=price, packCount=2, unitQty=4, unitUOM='each',
                         available=True, preferred=True)]), **changes}


class BackendPlanningPriceTests(unittest.IsolatedAsyncioTestCase):
    def test_missing_prices_preserve_quantities_and_source_values(self):
        rows = [food(p) for p in (None, '', ' \t ')]
        no_price = food(); del no_price['vendorSkus'][0]['price']; rows.append(no_price)
        rows.extend([food(vendorSkus=[]), food(vendorSkus=None),
                     food(vendorSkus=[dict(price=20, available=False, preferred=True)])])
        # A selected preferred supplier with an unknown price is not replaced
        # by a different supplier's known price merely to obtain a cost.
        preferred = food(); preferred['vendorSkus'].append(dict(price=20, available=True))
        rows.append(preferred)
        for row in rows:
            with self.subTest(row=row):
                before = copy.deepcopy(row)
                result = server.item_derived(row)
                self.assertEqual(result['portionsPerUnit'], 4)
                self.assertIsNone(result['price'])
                self.assertIsNone(result['costPerPortion'])
                self.assertTrue(result['priceMissing'])
                self.assertTrue(result['calculationUnavailable'])
                self.assertEqual(row, before)
                json.dumps(result, allow_nan=False)

    def test_zero_and_positive_prices_remain_known(self):
        for value in (0, 0.0, Decimal('0E-10'), '0', '0E-10', '0.0000000000', '12'):
            with self.subTest(value=value):
                result = server.item_derived(food(value))
                self.assertFalse(result['priceMissing'])
                self.assertFalse(result['calculationUnavailable'])
                self.assertEqual(result['price'], float(value))
                self.assertEqual(result['costPerPortion'], float(value) / 4)

    def test_invalid_or_unsafe_prices_are_unavailable_but_not_missing(self):
        for value in ('1e400', '1e-400', 'NaN', 'Infinity', 'N/A', True):
            with self.subTest(value=value):
                result = server.item_derived(food(value))
                self.assertFalse(result['priceMissing'])
                self.assertTrue(result['calculationUnavailable'])
                self.assertIsNone(result['costPerPortion'])
                json.dumps(result, allow_nan=False)
        unsafe = food(); unsafe['vendorSkus'][0]['packCount'] = '1e400'
        result = server.item_derived(unsafe)
        self.assertTrue(result['priceMissing'])
        self.assertIsNone(result['portionsPerUnit'])
        self.assertIsNone(result['costPerPortion'])

    def test_nested_recipe_and_adjustment_do_not_hide_missing_cost_in_partial_total(self):
        prep = dict(id='prep', yieldQty=2, lines=[dict(controlNumber='TEST', qty=1)])
        dish = dict(id='dish', lines=[dict(controlNumber='KNOWN', qty=2),
                    dict(sourceType='prep', recipeId='prep', qty=3)])
        for price, expected in ((None, None), ('0E-10', 4), ('8', 7)):
            with self.subTest(price=price):
                items = {'TEST': food(price), 'KNOWN': food('8')}
                self.assertEqual(server.recipe_cost(dish, items, {'prep': prep}), expected)
                self.assertEqual(server.adj_value(dict(qty=2, qtyBasis='portion'), items['TEST']),
                                 None if price is None else float(price) / 2)

    async def test_legacy_pg_helper_preserves_unknown_and_explicit_zero(self):
        for value in (None, '', ' \t ', Decimal('0E-10'), Decimal('12')):
            with self.subTest(value=value):
                conn = AsyncMock()
                conn.fetchrow.return_value = dict(price=value, base_per_purchase_unit=Decimal('4'))
                result = await server._pg_item_derived(conn, 'TEST')
                missing = value is None or isinstance(value, str) and not value.strip()
                self.assertEqual(result['priceMissing'], missing)
                self.assertEqual(result['calculationUnavailable'], missing)
                self.assertEqual(result['portionsPerUnit'], 4)
                self.assertEqual(result['price'], None if missing else float(value))
                self.assertEqual(result['costPerPortion'], None if missing else float(value) / 4)
                conn.execute.assert_not_awaited()
        conn = AsyncMock(); conn.fetchrow.return_value = None
        result = await server._pg_item_derived(conn, 'TEST')
        self.assertTrue(result['priceMissing']); self.assertIsNone(result['costPerPortion'])

    async def test_native_owner_summary_and_ai_keep_accounting_separate_from_unknown_costs(self):
        missing, known = food(), food('8')
        known['controlNumber'] = 'KNOWN'
        dishes = [dict(id='unknown', name='Unknown plate', price=10,
                       lines=[dict(controlNumber='TEST', qty=1)]),
                  dict(id='known', name='Known plate', price=10,
                       lines=[dict(controlNumber='KNOWN', qty=1)])]
        native = dict(inventoryValue='145.000000000001', netFoodPurchases30='178.000000000002',
            count=None, countStatus='count_missing', scope=None, receivedFrom='2026-10-01', receivedBefore='2026-10-31')
        adjustment = dict(controlNumber='TEST', qty=1, qtyBasis='portion', reason='waste', date='9999-01-01')
        before = copy.deepcopy((missing, known, dishes, native, adjustment))
        with patch.object(server, 'USE_PG', True), patch.object(server, 'ensure_seed', AsyncMock()), \
             patch.object(server, '_pg_owner_view', AsyncMock(return_value=([missing, known], [], dishes, None))), \
             patch.object(server, '_adjustments_for', AsyncMock(return_value=[adjustment])), \
             patch.object(server.purchase_api, 'enabled', return_value=True), \
             patch('native_inventory_views.read_operating_summary', AsyncMock(return_value=native)), \
             patch.object(server.db_pg, 'pool', return_value=object()):
            result = await server.owner_summary()
            self.assertEqual(result['totals']['inventoryValue'], '435.000000000003')
            self.assertEqual(result['totals']['spend30'], '534.000000000006')
            self.assertIsNone(result['totals']['waste30'])
            for store in result['stores']:
                self.assertFalse(store['planningCostsAvailable'])
                self.assertIsNone(store['avgFoodCost'])
                by_name = {row['name']: row for row in store['topCostDishes']}
                self.assertIsNone(by_name['Unknown plate']['cost'])
                self.assertIsNone(by_name['Unknown plate']['pct'])
                self.assertEqual(by_name['Known plate']['cost'], 2)
            context = server.build_ai_context('berts', [missing, known], [], dishes, [adjustment], None, native)
        self.assertIn('TEST Fictional food Unknown/portion', context)
        self.assertIn('plate cost Unknown, FC unavailable', context)
        self.assertIn('145.000000000001 USD', context)
        self.assertNotIn('Unknown (outside supported calculation range)', context)
        self.assertEqual((missing, known, dishes, native, adjustment), before)
        json.dumps(result, allow_nan=False)

    async def test_legacy_estimated_inventory_stays_unknown_but_zero_is_known(self):
        for price, expected in ((None, None), ('0E-10', 0), ('12', 24)):
            with self.subTest(price=price), patch.object(server, 'USE_PG', True), \
                 patch.object(server, 'ensure_seed', AsyncMock()), \
                 patch.object(server, '_pg_owner_view', AsyncMock(return_value=([food(price)], [], [], []))), \
                 patch.object(server, '_adjustments_for', AsyncMock(return_value=[])), \
                 patch.object(server.purchase_api, 'enabled', return_value=False):
                result = await server.store_summary(dict(id='berts'))
                self.assertEqual(result['inventoryValue'], expected)

    def test_unknown_money_does_not_claim_all_missing_costs_are_range_errors(self):
        self.assertEqual(planning.money(None), 'Unknown')
        self.assertEqual(planning.money(0), '$0.00')

    def test_prep_refusal_distinguishes_missing_price_from_range_and_keeps_identity(self):
        for item, label in ((dict(name='Fictional food'), 'Fictional food'),
                            (dict(controlNumber='TEST'), 'TEST'), (dict(code='test_code'), 'test_code'),
                            ({}, 'this item')):
            with self.subTest(item=item), self.assertRaises(server.HTTPException) as held:
                server._require_prep_planning_cost(server.item_derived(food()), item)
            self.assertEqual(held.exception.status_code, 422)
            self.assertIn('Supplier planning price is unknown for '+label, held.exception.detail)
            self.assertIn('No prep write was made.', held.exception.detail)
            self.assertNotIn('supported calculation range', held.exception.detail)
        with self.assertRaises(server.HTTPException) as held:
            server._require_prep_planning_cost(server.item_derived(food('1e400')), {'name':'Fictional food'})
        self.assertIn('supported calculation range', held.exception.detail)
        self.assertNotIn('price is unknown', held.exception.detail)
        server._require_prep_planning_cost(server.item_derived(food('0E-10')), {})

    async def test_legacy_mongo_helpers_refuse_missing_and_range_costs_before_mutating(self):
        recipe = dict(id='prep', yieldQty=1, lines=[dict(controlNumber='TEST',qty=1)])
        for price in (None, '1e400'):
            for single in (False, True):
                with self.subTest(price=price,single=single):
                    db = MagicMock()
                    db.items.find.return_value.to_list = AsyncMock(return_value=[food(price)])
                    db.dishes.find.return_value.to_list = AsyncMock(return_value=[recipe])
                    with patch.object(server,'db',db), patch('prep_batches.reject_legacy_write'), \
                         self.assertRaises(server.HTTPException) as held:
                        if single:
                            await server._deduct_item_and_stock('berts',dict(controlNumber='TEST',vesselCapacity=1),1)
                        else:
                            await server._deduct_and_stock('berts',recipe,1,[],'batch','Fictional prep')
                    self.assertEqual(held.exception.status_code,422)
                    self.assertIn('price is unknown' if price is None else 'supported calculation range',held.exception.detail)
                    db.items.bulk_write.assert_not_called();db.items.update_one.assert_not_called()
                    db.prep_stock.update_one.assert_not_called();db.prep_logs.insert_one.assert_not_called()

    async def test_single_item_nonfinite_arithmetic_is_refused_before_write(self):
        derived={'portionsPerUnit':1,'costPerPortion':3,'calculationUnavailable':False}
        cases=(
            ('vessels',float('inf'),1,1,3,10),
            ('capacity',1,float('nan'),1,3,10),
            ('portions',1e308,2,1,3,10),
            ('units',1e308,1,1e-308,0,10),
            ('cost',1e308,1,1,3,10),
            ('remaining',1e308,1,1,0,-1e308),
            ('underflow',1e-308,1e-308,1,3,10),
        )
        for label,vessels,capacity,factor,price,stock in cases:
            with self.subTest(case=label):
                conn=MagicMock()
                conn.fetchrow=AsyncMock(side_effect=[{'current_stock':stock},{'name':'Fictional food'}])
                conn.execute=AsyncMock()
                with patch('prep_batches.reject_legacy_write'),patch('prep_containers.hold_legacy',new=AsyncMock()), \
                     patch.object(server,'_pg_item_derived',new=AsyncMock(return_value={**derived,'portionsPerUnit':factor,'costPerPortion':price})), \
                     self.assertRaises(server.HTTPException) as held:
                    await server._pg_deduct_item_and_stock(conn,'berts',{'item_code':'TEST','vessel_capacity':capacity},vessels)
                self.assertEqual(held.exception.status_code,422)
                self.assertIn('supported calculation range',held.exception.detail)
                conn.execute.assert_not_awaited()
                self.assertEqual(conn.fetchrow.await_count,2)
