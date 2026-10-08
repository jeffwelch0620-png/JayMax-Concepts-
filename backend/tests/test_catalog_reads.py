"""Query budgets and source-hash contracts; invented catalog data only."""
from contextlib import asynccontextmanager
from decimal import Decimal
import os
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
import server
import native_units
from purchase_api import serial
from purchase_parser import fingerprint


@asynccontextmanager
async def readonly_transaction():
    yield


def item(code):
    return dict(code=code,name=code,category=None,base_unit='lb',item_type='raw',is_high_value=False,
        notes=None,costing_type='portion',pack_count=4,unit_qty=5,unit_uom='lb',portion_size=4,
        portion_uom='oz',count_unit='case',base_per_count_unit=20,storage_area='Freezer',
        counted_nightly=True,active=True,store_active=False,order_enabled=False,sales_tracked=False,
        needs_review=False,current_stock=7,par=0,last_counted=None,last_counted_by=None,
        control_number='LOCAL-'+code,shared_store_count=2)


def sku(code):
    return dict(id=uuid4(),item_code=code,vendor_id='invented',vendor_name='Invented supplier',
        vendor_sku=code,vendor_description='Original retained pack',purchase_unit='case',
        base_per_purchase_unit=20,pack_count=4,unit_qty=5,unit_uom='lb',price=Decimal('99.000000000001'),
        price_updated_at=None,price_source='invoice',preferred=True,available=False,
        store_price=Decimal('88.000000000001'),store_price_updated_at=None,store_price_source='manual',
        store_preferred=True,store_available=False)


class CatalogReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_query_count_does_not_grow_with_items_in_either_mode(self):
        for shared in (False,True):
            budgets=[]
            for size in (1,300):
                rows=[item(str(n)) for n in range(size)]; suppliers=[sku(r['code']) for r in rows]
                class Connection:
                    def __init__(self):self.calls=[]
                    def transaction(self,**options):
                        self.options=options;return readonly_transaction()
                    async def fetch(self,sql,*args):
                        self.calls.append(sql)
                        if 'FROM public.items i JOIN public.store_items' in sql:return rows
                        if 'FROM public.vendor_items vi' in sql:return suppliers
                        raise AssertionError('Unexpected per-item query: '+sql)
                    async def fetchval(self,sql,*args):
                        self.calls.append(sql)
                        if 'supplier_price_events' in sql:return False
                        if 'store_vendor_items' in sql:return shared
                        raise AssertionError('Unexpected metadata query: '+sql)
                conn=Connection()
                with patch.dict(os.environ,{'CATALOG_MAPPING_ENABLED':str(shared).lower(),
                    'PURCHASE_IMPORT_ENABLED':'true','ACTUAL_INVENTORY_ENABLED':'true'}):
                    result=await server._pg_catalog_rows(conn,'berts')
                budgets.append(len(conn.calls));self.assertLessEqual(len(conn.calls),4)
                self.assertEqual(conn.options,{'isolation':'repeatable_read','readonly':True})
                self.assertEqual(len(result),size)
                self.assertFalse(result[0]['active']);self.assertTrue(result[0]['countActive'])
                self.assertIsNone(result[0]['currentStock'])
                self.assertFalse(result[0]['vendorSkus'][0]['available'])
                self.assertEqual(result[0]['vendorSkus'][0]['price'],'88.000000000001' if shared else '99.000000000001')
                self.assertEqual(result[0]['controlNumber'],'LOCAL-0' if shared else None)
            self.assertEqual(budgets[0],budgets[1])

    async def test_installed_shared_schema_is_held_even_for_an_empty_catalog_with_mode_off(self):
        class Connection:
            def transaction(self,**options):return readonly_transaction()
            fetchval=AsyncMock(return_value=True)
            fetch=AsyncMock(return_value=[])
        conn=Connection()
        with patch.dict(os.environ,{'CATALOG_MAPPING_ENABLED':'false'}):
            with self.assertRaises(server.HTTPException) as caught:await server._pg_catalog_rows(conn,'berts')
        self.assertEqual(caught.exception.status_code,503);conn.fetch.assert_not_called()

    def test_current_selection_ignores_unavailable_suppliers_without_removing_history(self):
        retired={'id':'retired','preferred':True,'available':False,'price':'999'}
        current={'id':'current','preferred':False,'available':True,'price':'80'}
        value={'vendorSkus':[retired,current]}
        self.assertEqual(server.preferred_sku(value),current)
        self.assertEqual(value['vendorSkus'],[retired,current])
        self.assertIsNone(server.preferred_sku({'vendorSkus':[retired]}))


class ProfileReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_profile_queries_are_constant_and_preserve_single_source_hashes(self):
        for size in (1,300):
            items=[];skus=[];rows=[]
            for n in range(size):
                product={key:item(str(n))[key] for key in ('code','base_unit','item_type','pack_count','unit_qty','unit_uom','count_unit','base_per_count_unit')}
                supplier={key:sku(str(n))[key] for key in ('id','vendor_id','vendor_sku','item_code','purchase_unit','base_per_purchase_unit','pack_count','unit_qty','unit_uom')}
                supplier['pack_verified']=True;items.append(product);skus.append(supplier)
                rows.append(dict(id=uuid4(),item_code=product['code'],profile_kind='purchase',vendor_item_id=supplier['id'],
                    source_fingerprint=fingerprint(serial({'item':product,'supplierProduct':supplier}))))
            class Connection:pass
            conn=Connection();conn.fetch=AsyncMock(side_effect=[rows,items,skus])
            result=await native_units.profiles(conn,'berts')
            self.assertEqual(conn.fetch.await_count,3);self.assertEqual(len(result),size)
            self.assertTrue(all(not profile['stale'] for profile in result))

    async def test_missing_changed_or_mismatched_sources_remain_stale(self):
        source={key:item('food')[key] for key in ('code','base_unit','item_type','pack_count','unit_qty','unit_uom','count_unit','base_per_count_unit')}
        row=dict(id=uuid4(),item_code='food',profile_kind='count',vendor_item_id=None,source_fingerprint=fingerprint(serial({'item':source})))
        class Connection:pass
        for items in ([],[{**source,'count_unit':'bag'}],[{**source,'item_type':'prep'}]):
            conn=Connection();conn.fetch=AsyncMock(side_effect=[[row],items,[]])
            self.assertTrue((await native_units.profiles(conn,'berts'))[0]['stale'])
        with self.assertRaises(native_units.HTTPException):
            native_units._source_values(source,{'item_code':'other'},'food','purchase',uuid4())


class SupplierEventReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_batch_price_checks_preserve_staleness_with_constant_queries(self):
        import catalog_mapping
        budgets = []
        for size in (1, 300):
            suppliers = [sku(str(n)) for n in range(size)]
            profiles = [dict(id=uuid4(), vendor_item_id=row['id'], profile_kind='purchase', stale=n % 3 == 0) for n, row in enumerate(suppliers)]
            events = [dict(vendor_item_id=row['id'], source='invoice', pack_stale=n % 3 == 1,
                invoice_stale=n % 3 == 2, basis_snapshot={'profile': {'id': str(profiles[n]['id'])}}) for n, row in enumerate(suppliers)]
            class Connection:
                fetchval = AsyncMock(return_value=True)
            conn = Connection()
            conn.fetch = AsyncMock(side_effect=[suppliers, events])
            with patch('native_units.profiles', AsyncMock(return_value=profiles)) as reviewed:
                result = await catalog_mapping.supplier_rows_many(conn, 'berts', [row['item_code'] for row in suppliers])
                reviewed.assert_awaited_once_with(conn, 'berts')
            budgets.append(conn.fetch.await_count + conn.fetchval.await_count)
            self.assertTrue(all(row['price'] is None and row['price_issues'] for row in result))
            self.assertIn('ANY($2::text[])', conn.fetch.await_args_list[0].args[0])
            conn.fetchval.reset_mock()
        self.assertEqual(budgets, [4, 4])
