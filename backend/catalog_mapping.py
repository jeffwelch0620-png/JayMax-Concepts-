"""Shared catalog identity and store supplier settings; no accounting writes."""
import os
from decimal import Decimal
from uuid import UUID
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
import purchase_api


def enabled():
    requested=os.getenv('CATALOG_MAPPING_ENABLED','false').lower()=='true'
    if requested and not (purchase_api.enabled() and os.getenv('ACTUAL_INVENTORY_ENABLED','false').lower()=='true'):
        raise HTTPException(503,'Shared catalog requires native purchases and actual inventory')
    return requested


async def ready(conn):
    if not await conn.fetchval("SELECT to_regclass('purchasing.store_vendor_items') IS NOT NULL"):
        raise HTTPException(503,'Shared catalog migration is awaiting enablement')


async def reject_legacy_schema(conn):
    if not enabled() and await conn.fetchval("SELECT to_regclass('purchasing.store_vendor_items') IS NOT NULL"):
        raise HTTPException(503,'Shared catalog schema is installed. Enable shared catalog before reading or editing catalog settings; legacy global price/settings fallback is held.')


async def lock_catalog(conn):
    await reject_legacy_schema(conn)
    if enabled():
        await ready(conn)
        # Take this before store revisions, across every supported catalog writer.
        await conn.execute("SELECT pg_advisory_xact_lock(70620261006::bigint)")


async def supplier_rows(conn,store,code):
    return await supplier_rows_many(conn,store,[code])


async def supplier_rows_many(conn,store,codes):
    await ready(conn)
    rows=await conn.fetch('''SELECT vi.*,v.name AS vendor_name,
        s.price AS store_price,s.price_updated_at AS store_price_updated_at,s.price_source AS store_price_source,
        coalesce(s.preferred,false) AS store_preferred,coalesce(s.available,false) AS store_available
        FROM public.vendor_items vi JOIN public.vendors v ON v.id=vi.vendor_id
        LEFT JOIN purchasing.store_vendor_items s ON s.vendor_item_id=vi.id AND s.store_id=$1
        WHERE vi.item_code=ANY($2::text[])
        ORDER BY store_available DESC,store_preferred DESC,vi.vendor_id,vi.vendor_sku,vi.id''',store,codes)
    return [{**dict(r),**{key:r['store_'+key] for key in ('price','price_updated_at','price_source','preferred','available')}} for r in rows]


async def save_supplier(conn,store,code,sku_id,sku):
    await conn.execute('''INSERT INTO purchasing.store_vendor_items(store_id,item_code,vendor_item_id,preferred,available,
        price,price_updated_at,price_source) VALUES($1,$2,$3,$4,$5,$6,CASE WHEN $6::numeric IS NOT NULL THEN now() END,
        CASE WHEN $6::numeric IS NOT NULL THEN 'manual' END)
        ON CONFLICT(store_id,vendor_item_id) DO UPDATE SET preferred=$4,available=$5,price=$6,
        price_updated_at=CASE WHEN store_vendor_items.price IS DISTINCT FROM $6::numeric THEN now() ELSE store_vendor_items.price_updated_at END,
        price_source=CASE WHEN store_vendor_items.price IS DISTINCT FROM $6::numeric THEN 'manual' ELSE store_vendor_items.price_source END''',
        store,code,sku_id,sku.preferred,sku.available,sku.price)


def same(left,right):
    if isinstance(left,Decimal) and right is not None:return left==Decimal(str(right))
    return left==right


async def hold_shared_changes(conn,store,body):
    original=await conn.fetchrow('SELECT * FROM public.items WHERE code=$1',body.code)
    if original is None:return
    other=await conn.fetchval('SELECT EXISTS(SELECT 1 FROM public.store_items WHERE item_code=$1 AND store_id<>$2)',body.code,store)
    if not other:return
    columns=('name','base_unit','category','item_type','is_high_value','notes','costing_type','pack_count','unit_qty','unit_uom','portion_size','portion_uom')
    for key in columns:
        if (key not in ('category','item_type','is_high_value','notes') or key in body.model_fields_set) and not same(original[key],getattr(body,key)):
            raise HTTPException(409,'This product is shared across locations. Shared product and pack changes require catalog review; location settings and supplier prices can be edited here.')
    for sk in body.vendor_skus:
        row=await conn.fetchrow('SELECT * FROM public.vendor_items WHERE vendor_id=$1 AND vendor_sku=$2 AND item_code=$3',sk.vendor_id,sk.vendor_sku,body.code)
        if row is None or any(not same(row[key],getattr(sk,key)) for key in ('vendor_description','purchase_unit','base_per_purchase_unit','pack_count','unit_qty','unit_uom')):
            raise HTTPException(409,'This supplier product is shared. Review its identity and physical pack in the shared catalog before changing it.')


class LinkItem(BaseModel):
    model_config=ConfigDict(extra='forbid')
    item_code:str=Field(min_length=1,max_length=200)
    control_number:str=Field(min_length=1,max_length=100)
    storage_area:str|None=None
    count_unit:str=Field(min_length=1,max_length=40)
    base_per_count_unit:Decimal=Field(gt=0,max_digits=28,decimal_places=12,allow_inf_nan=False)
    par:Decimal=Field(default=Decimal(0),ge=0,max_digits=28,decimal_places=12,allow_inf_nan=False)
    counted_nightly:bool=False
    order_enabled:bool=True
    sales_tracked:bool=False
    vendor_item_ids:list[UUID]=Field(min_length=1,max_length=100)
    verified:bool
    expected_catalog_hash:str=Field(pattern=r'^[0-9a-f]{64}$')

    @field_validator('control_number','count_unit')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('Enter a nonblank location identifier and count unit')
        return value.strip()


async def shared_choices(conn,store):
    await ready(conn)
    items=await conn.fetch("SELECT * FROM public.items WHERE item_type='raw' AND active ORDER BY name,code")
    result=[]
    for item in items:
        skus=[dict(r) for r in await conn.fetch('''SELECT vi.id,vi.vendor_id,v.name AS vendor_name,vi.vendor_sku,
            vi.vendor_description,vi.purchase_unit,vi.base_per_purchase_unit,vi.pack_count,vi.unit_qty,vi.unit_uom
            FROM public.vendor_items vi JOIN public.vendors v ON v.id=vi.vendor_id
            WHERE vi.item_code=$1 AND v.active ORDER BY vi.vendor_id,vi.vendor_sku''',item['code'])]
        snapshot=purchase_api.serial({'item':dict(item),'supplier_products':skus})
        from purchase_parser import fingerprint
        result.append({'item_code':item['code'],'name':item['name'],'base_unit':item['base_unit'],
            'linked':bool(await conn.fetchval('SELECT EXISTS(SELECT 1 FROM public.store_items WHERE store_id=$1 AND item_code=$2)',store,item['code'])),
            'supplier_products':purchase_api.serial(skus),'catalog_hash':fingerprint(snapshot).hex()})
    return result


async def link(conn,store,body):
    choices=await shared_choices(conn,store)
    choice=next((r for r in choices if r['item_code']==body.item_code),None)
    if choice is None:raise HTTPException(422,'Choose an existing active purchased product')
    if not body.verified:raise HTTPException(422,'Confirm the product, supplier SKUs and physical count unit')
    if choice['catalog_hash']!=body.expected_catalog_hash:raise HTTPException(409,'Shared product changed; refresh and verify its identity again')
    if choice['linked']:raise HTTPException(409,'This product is already linked here; edit its location settings')
    ids=[str(i) for i in body.vendor_item_ids]
    if len(set(ids))!=len(ids) or not set(ids)<= {s['id'] for s in choice['supplier_products']}:
        raise HTTPException(422,'Select each matching supplier product exactly once')
    if await conn.fetchval('SELECT EXISTS(SELECT 1 FROM public.store_items WHERE store_id=$1 AND control_number=$2)',store,body.control_number):
        raise HTTPException(409,'This location control number already belongs to another product')
    await conn.execute('''INSERT INTO public.store_items(store_id,item_code,control_number,count_unit,base_per_count_unit,
        storage_area,par,counted_nightly,active,order_enabled,sales_tracked)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,true,$9,$10)''',store,body.item_code,body.control_number,body.count_unit,
        body.base_per_count_unit,body.storage_area,body.par,body.counted_nightly,body.order_enabled,body.sales_tracked)
    for id in body.vendor_item_ids:
        await conn.execute('''INSERT INTO purchasing.store_vendor_items(store_id,item_code,vendor_item_id,available)
            VALUES($1,$2,$3,true)''',store,body.item_code,id)
    # No price, stock, physical count, fixed base or unit review is inferred/copied.
    return {'ok':True,'itemCode':body.item_code,'controlNumber':body.control_number}
