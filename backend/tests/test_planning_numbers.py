"""Fictional catalog values must not break active summaries or alter Track 1."""
import json
import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, patch
import planning_numbers as numbers
import server


def item(**changes):
    return dict(controlNumber='TEST', name='Fictional food', currentStock=2,
        packCount=1, unitQty=1, unitUOM='each', portionSize=1, portionUOM='each',
        vendorSkus=[dict(price='1e400', packCount=1, unitQty=1, unitUOM='each')], **changes)


class PlanningRangeTests(unittest.IsolatedAsyncioTestCase):
    def test_numbers_and_arithmetic_refuse_overflow_and_positive_underflow(self):
        for value in ('1e400', '1e-400', 'Infinity', 'NaN', 'N/A', True):
            with self.subTest(value=value): self.assertIsNone(numbers.number(value))
        for value in ('0', '0E-10', '1e-308', '1e308'):
            with self.subTest(value=value): self.assertEqual(numbers.number(value), float(value))
        for result in (numbers.product(1e308, 2), numbers.product(1e-308, 1e-308),
                       numbers.quotient(1e308, 1e-308), numbers.quotient(1e-308, 1e308),
                       numbers.total([1e308, 1e308]), numbers.total([1, None])):
            self.assertIsNone(result)
        self.assertEqual(numbers.product(0, 2), 0)
        self.assertEqual(numbers.quotient(0, 2), 0)

    async def test_derived_costs_nested_recipes_and_adjustments_are_json_safe(self):
        for price, pack, portion in [('1e400', '1', '1'), ('1e-400','1','1'),
                                     ('1e308','1e-308','1'), ('1','1','1e-400'),
                                     ('1','1e-400','1'), ('1','1e400','1'), ('1e-308','1e308','1')]:
            with self.subTest(price=price, pack=pack, portion=portion):
                food=item(); food['vendorSkus'][0].update(price=price, packCount=pack); food['portionSize']=portion
                d=server.item_derived(food)
                self.assertTrue(d['calculationUnavailable']); self.assertIsNone(d['costPerPortion'])
                json.dumps(d, allow_nan=False)
                prep=dict(id='prep', yieldQty=2, lines=[dict(controlNumber='TEST', qty=1)])
                dish=dict(id='dish', lines=[dict(sourceType='prep',recipeId='prep',qty=1)])
                self.assertIsNone(server.recipe_cost(dish, {'TEST':food}, {'prep':prep}))
                self.assertIsNone(server.adj_value(dict(qty=1,qtyBasis='portion'),food))
                conn=AsyncMock(); conn.fetchrow.return_value=dict(price=Decimal(price),base_per_purchase_unit=Decimal(pack))
                pg=await server._pg_item_derived(conn,'TEST')
                if portion == '1': self.assertIsNone(pg['costPerPortion'])
                json.dumps(pg,allow_nan=False)
        food=item();food['vendorSkus'][0]['price']='0E-10'
        self.assertEqual(server.item_derived(food)['costPerPortion'],0)

    async def test_active_owner_summary_keeps_native_values_and_unavailable_planning_costs(self):
        food=item(); dish=dict(id='dish',name='Fictional plate',price=10,lines=[dict(controlNumber='TEST',qty=1)])
        native=dict(inventoryValue='145.000000000001',netFoodPurchases30='178.000000000002',
                    count=None,countStatus='count_missing',scope=None,receivedFrom='2026-10-01',receivedBefore='2026-10-31')
        adjustment=dict(controlNumber='TEST',qty=1,qtyBasis='portion',reason='waste',date='9999-01-01')
        with patch.object(server,'USE_PG',True), patch.object(server,'ensure_seed',AsyncMock()), \
             patch.object(server,'_pg_owner_view',AsyncMock(return_value=([food],[],[dish],None))), \
             patch.object(server,'_adjustments_for',AsyncMock(return_value=[adjustment])), \
             patch.object(server.purchase_api,'enabled',return_value=True), \
             patch('native_inventory_views.read_operating_summary',AsyncMock(return_value=native)), \
             patch.object(server.db_pg,'pool',return_value=object()):
            result=await server.owner_summary()
            self.assertEqual(result['totals']['inventoryValue'],'435.000000000003')
            self.assertEqual(result['totals']['spend30'],'534.000000000006')
            self.assertIsNone(result['totals']['waste30'])
            for store in result['stores']:
                self.assertFalse(store['planningCostsAvailable'])
                self.assertIsNone(store['avgFoodCost']);self.assertIsNone(store['topCostDishes'][0]['cost'])
            json.dumps(result,allow_nan=False)
            context=server.build_ai_context('berts',[food],[],[dish],[adjustment],None,native)
            self.assertIn('Unknown',context);self.assertNotIn('$inf',context.lower())
