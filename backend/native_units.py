"""Explicit physical-unit profiles; catalog portion conversions are never adopted."""
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from purchase_api import ALLOWED_UNITS, serial
from purchase_parser import fingerprint


class UnitProfile(BaseModel):
    model_config=ConfigDict(extra='forbid')
    item_code:str
    profile_kind:Literal['count','purchase']
    vendor_item_id:UUID|None=None
    base_unit:Literal['lb','oz','g','kg','fl_oz','ml','l','gal','each']
    base_units_per_source_unit:Decimal=Field(gt=0,max_digits=28,decimal_places=12)
    expected_source_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    verified:Literal[True]
    note:str=Field(min_length=1,max_length=2000)

    @field_validator('note')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('Explain the verified physical conversion')
        return value


async def ready(conn):
    if not await conn.fetchval("SELECT to_regclass('purchasing.unit_profiles') IS NOT NULL"):
        raise HTTPException(503,'Native unit and order receiving setup is awaiting enablement')


async def lock_store(conn,store):
    await conn.execute('INSERT INTO public.store_state(store_id) VALUES($1) ON CONFLICT DO NOTHING',store)
    await conn.fetchval('SELECT revision FROM public.store_state WHERE store_id=$1 FOR UPDATE',store)


async def source_snapshot(conn,store,code,kind,vendor_item_id=None):
    item=await conn.fetchrow('''SELECT i.code,i.base_unit,i.item_type,i.pack_count,i.unit_qty,i.unit_uom,
        si.count_unit,si.base_per_count_unit FROM public.items i JOIN public.store_items si ON si.item_code=i.code
        WHERE si.store_id=$1 AND i.code=$2''',store,code)
    if item is None or item['item_type']!='raw':raise HTTPException(422,'Choose a purchased raw item at this location')
    source={'item':dict(item)}
    if kind=='purchase':
        if vendor_item_id is None:raise HTTPException(422,'Select the supplier product for a purchase-unit profile')
        sku=await conn.fetchrow('''SELECT id,vendor_id,vendor_sku,item_code,purchase_unit,base_per_purchase_unit,
            pack_count,unit_qty,unit_uom,pack_verified FROM public.vendor_items WHERE id=$1 AND item_code=$2''',vendor_item_id,code)
        if sku is None:raise HTTPException(422,'Supplier product does not belong to this item')
        source['supplierProduct']=dict(sku);unit=sku['purchase_unit']
    else:
        if vendor_item_id is not None:raise HTTPException(422,'Count profiles use the location count unit')
        unit=item['count_unit']
    if not unit or not unit.strip():raise HTTPException(422,'Set a nonblank source unit in the item setup first')
    return serial(source),unit


async def profiles(conn,store):
    rows=await conn.fetch('''SELECT DISTINCT ON (item_code,profile_kind,context_key) * FROM purchasing.unit_profiles
        WHERE store_id=$1 ORDER BY item_code,profile_kind,context_key,revision DESC''',store)
    result=[]
    for r in rows:
        value=dict(r)
        try:
            source,_=await source_snapshot(conn,store,r['item_code'],r['profile_kind'],r['vendor_item_id'])
            value['stale']=fingerprint(source)!=r['source_fingerprint']
        except HTTPException:value['stale']=True
        result.append(value)
    return result


async def setup(conn,store):
    await ready(conn)
    items=await conn.fetch('''SELECT i.code,i.name,ib.base_unit AS native_base_unit FROM public.items i
        JOIN public.store_items si ON si.item_code=i.code AND si.store_id=$1
        LEFT JOIN purchasing.item_bases ib ON ib.item_code=i.code AND ib.store_id=si.store_id
        WHERE i.item_type='raw' ORDER BY i.name,i.code''',store)
    result=[]
    for i in items:
        row=dict(i);row['issues']=[];row['countSource']=None
        try:
            source,unit=await source_snapshot(conn,store,i['code'],'count')
            row['countSource']={'snapshot':source,'unit':unit,'hash':fingerprint(source)}
        except HTTPException as exc:
            row['issues'].append('Count setup: '+str(exc.detail))
        row['supplierProducts']=[]
        for s in await conn.fetch('SELECT vi.id,v.name FROM public.vendor_items vi JOIN public.vendors v ON v.id=vi.vendor_id WHERE vi.item_code=$1 ORDER BY vi.id',i['code']):
            try:
                source,unit=await source_snapshot(conn,store,i['code'],'purchase',s['id'])
                row['supplierProducts'].append({'id':s['id'],'name':s['name'],'unit':unit,'snapshot':source,'hash':fingerprint(source)})
            except HTTPException as exc:
                row['issues'].append(s['name']+': '+str(exc.detail))
        result.append(row)
    return serial({'items':result,'profiles':await profiles(conn,store),'baseUnits':list(ALLOWED_UNITS)})


def install_routes(router,context):
    @router.get('/{store_id}/unit-setup')
    async def get_setup(store_id:str,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read',readonly=True):return await setup(conn,store_id)

    @router.post('/{store_id}/unit-profiles')
    async def save(store_id:str,body:UnitProfile,request:Request,idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True)
        digest=fingerprint(body.model_dump(mode='json'))
        async with pool.acquire() as conn:
            async with conn.transaction():
                await ready(conn);await lock_store(conn,store_id)
                prior=await conn.fetchrow('SELECT * FROM purchasing.unit_profiles WHERE request_key=$1',str(idempotency_key))
                if prior:
                    if prior['store_id']!=store_id or prior['request_fingerprint']!=digest:raise HTTPException(409,'Unit review key already belongs to a different request')
                    return serial({'profile':dict(prior),'replayed':True})
                source,unit=await source_snapshot(conn,store_id,body.item_code,body.profile_kind,body.vendor_item_id)
                if fingerprint(source).hex()!=body.expected_source_hash:raise HTTPException(409,'Item pack or unit setup changed. Refresh and verify it again.')
                await conn.execute('INSERT INTO purchasing.item_bases(store_id,item_code,base_unit) VALUES($1,$2,$3) ON CONFLICT DO NOTHING',store_id,body.item_code,body.base_unit)
                if await conn.fetchval('SELECT base_unit FROM purchasing.item_bases WHERE store_id=$1 AND item_code=$2',store_id,body.item_code)!=body.base_unit:
                    raise HTTPException(409,'This item already has a different fixed inventory unit')
                context_key=str(body.vendor_item_id) if body.vendor_item_id else ''
                revision=await conn.fetchval('''SELECT coalesce(max(revision),0)+1 FROM purchasing.unit_profiles
                    WHERE store_id=$1 AND item_code=$2 AND profile_kind=$3 AND context_key=$4''',store_id,body.item_code,body.profile_kind,context_key)
                saved=await conn.fetchrow('''INSERT INTO purchasing.unit_profiles(store_id,item_code,profile_kind,vendor_item_id,context_key,
                    revision,source_unit,base_unit,base_units_per_source_unit,source_snapshot,source_fingerprint,request_key,request_fingerprint,confirmed_by,note)
                    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15) RETURNING *''',store_id,body.item_code,body.profile_kind,
                    body.vendor_item_id,context_key,revision,unit,body.base_unit,body.base_units_per_source_unit,source,fingerprint(source),str(idempotency_key),digest,actor,body.note)
                await conn.execute('UPDATE public.store_state SET revision=revision+1,updated_at=now() WHERE store_id=$1',store_id)
                return serial({'profile':dict(saved),'replayed':False})
