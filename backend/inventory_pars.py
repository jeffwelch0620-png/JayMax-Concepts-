"""Reviewed purchased-item stock targets; no stock, order or accounting writes."""
from decimal import Decimal, localcontext
from typing import Literal
from uuid import UUID
from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
import catalog_mapping
import native_units
from purchase_api import serial
from purchase_parser import fingerprint


class Review(BaseModel):
    model_config=ConfigDict(extra='forbid')
    action:Literal['confirm','withdraw']='confirm'
    unit_profile_id:UUID|None=None
    quantity:Decimal|None=Field(default=None,ge=0,max_digits=28,decimal_places=12,allow_inf_nan=False)
    coverage_note:str=Field(min_length=1,max_length=2000)
    verified:Literal[True]

    @field_validator('quantity',mode='before')
    @classmethod
    def explicit_number(cls,value):
        if isinstance(value,bool):raise ValueError('Enter an explicit decimal quantity')
        return value

    @field_validator('verified',mode='before')
    @classmethod
    def explicit_confirmation(cls,value):
        if value is not True:raise ValueError('Explicit confirmation is required')
        return value

    @field_validator('coverage_note')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('Describe the coverage period and reason for this target')
        return value.strip()


async def installed(conn):
    return bool(await conn.fetchval("SELECT to_regclass('purchasing.inventory_par_versions') IS NOT NULL"))


async def current(conn,store,code):
    row=await conn.fetchrow('SELECT * FROM purchasing.inventory_par_versions WHERE store_id=$1 AND item_code=$2 ORDER BY revision DESC LIMIT 1',store,code)
    return dict(row) if row else None


async def setup(conn,store):
    items=await conn.fetch('''SELECT i.code,i.name,si.par AS legacy_quantity,si.active FROM public.items i
        JOIN public.store_items si ON si.item_code=i.code WHERE si.store_id=$1 AND i.item_type='raw' ORDER BY i.code''',store)
    available=catalog_mapping.enabled() and await installed(conn)
    profiles=await native_units.profiles(conn,store) if available else []
    count_profiles={p['item_code']:p for p in profiles if p['profile_kind']=='count'}
    plans=await conn.fetch('''SELECT DISTINCT ON(item_code) * FROM purchasing.inventory_par_versions
        WHERE store_id=$1 ORDER BY item_code,revision DESC''',store) if available else []
    by_code={p['item_code']:dict(p) for p in plans}
    result=[]
    for item in items:
        saved=by_code.get(item['code']);profile=count_profiles.get(item['code'])
        status='unconfirmed'
        if saved and saved['confirmed']:
            status='confirmed' if profile and not profile['stale'] and profile['id']==saved['unit_profile_id'] else 'needs_review'
        result.append(dict(item,review=saved,status=status,count_profile=profile if profile and not profile['stale'] else None))
    return serial(dict(store_id=store,available=available,items=result))


async def save(pool,store,code,actor,body,key,expected):
    digest=fingerprint(serial(dict(store=store,item=code,actor=actor,expected=expected,body=body.model_dump())))
    async with pool.acquire() as conn,conn.transaction():
        if not catalog_mapping.enabled() or not await installed(conn):raise HTTPException(503,'Reviewed inventory par setup is awaiting installation')
        await catalog_mapping.lock_catalog(conn);await native_units.lock_store(conn,store)
        prior=await conn.fetchrow('SELECT * FROM purchasing.inventory_par_versions WHERE request_key=$1',key)
        if prior:
            if prior['request_fingerprint']!=digest:raise HTTPException(409,'Par review key belongs to another request')
            return serial(dict(request_key=key,review=dict(prior),current_review=await current(conn,store,code),replayed=True))
        await conn.execute('LOCK TABLE public.items,public.store_items IN SHARE MODE')
        item=await conn.fetchrow('''SELECT i.item_type,si.active FROM public.items i JOIN public.store_items si ON si.item_code=i.code
            WHERE si.store_id=$1 AND i.code=$2''',store,code)
        if not item or item['item_type']!='raw':raise HTTPException(422,'Choose a purchased product at this location')
        previous=await current(conn,store,code)
        if (previous['revision'] if previous else 0)!=expected:raise HTTPException(409,'Par review changed. Reload and review your retained values.')
        if body.action=='withdraw':
            if body.quantity is not None or body.unit_profile_id is not None:raise HTTPException(422,'Withdrawal cannot change quantities or units')
            if not previous or not previous['confirmed']:raise HTTPException(409,'Only a previously confirmed par can be withdrawn')
            values=previous
        else:
            if not item['active']:raise HTTPException(409,'Review the inactive product before confirming a target')
            if body.quantity is None or body.unit_profile_id is None:raise HTTPException(422,'Enter a quantity, including explicit zero, and select a verified count unit')
            profile=next((p for p in await native_units.profiles(conn,store) if p['item_code']==code and p['profile_kind']=='count'),None)
            if not profile or profile['id']!=body.unit_profile_id or profile['stale']:raise HTTPException(409,'Count conversion changed or is unconfirmed. Review it in Invoice Master first.')
            factor=profile['base_units_per_source_unit']
            if body.quantity>=Decimal('1e16') or factor>=Decimal('1e16'):raise HTTPException(422,'Par quantity or conversion exceeds supported exact range')
            with localcontext() as ctx:
                ctx.prec=80
                base=body.quantity*factor
            values=dict(unit_profile_id=profile['id'],source_unit=profile['source_unit'],quantity=body.quantity,
                        factor=factor,base_unit=profile['base_unit'],base_quantity=base)
        row=await conn.fetchrow('''INSERT INTO purchasing.inventory_par_versions(store_id,item_code,revision,predecessor_id,
            unit_profile_id,source_unit,quantity,factor,base_unit,base_quantity,confirmed,coverage_note,actor,request_key,request_fingerprint)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15) RETURNING *''',store,code,expected+1,
            previous['id'] if previous else None,values['unit_profile_id'],values['source_unit'],values['quantity'],values['factor'],
            values['base_unit'],values['base_quantity'],body.action=='confirm',body.coverage_note,actor,key,digest)
        return serial(dict(request_key=key,review=dict(row),current_review=dict(row),replayed=False))


def install_routes(router,context):
    @router.get('/{store_id}/inventory-pars')
    async def read_pars(store_id:str,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn,conn.transaction(isolation='repeatable_read',readonly=True):
            return await setup(conn,store_id)

    @router.put('/{store_id}/inventory-pars/{item_code}')
    async def review_par(store_id:str,item_code:str,body:Review,request:Request,idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True)
        from prep_planning import version
        return await save(pool,store_id,item_code,actor,body,idempotency_key,version(request))

    @router.get('/{store_id}/inventory-pars/{item_code}/history')
    async def history(store_id:str,item_code:str,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn,conn.transaction(isolation='repeatable_read',readonly=True):
            if not await installed(conn):raise HTTPException(503,'Reviewed inventory par setup is awaiting installation')
            if not await conn.fetchval('SELECT 1 FROM public.store_items WHERE store_id=$1 AND item_code=$2',store_id,item_code):raise HTTPException(404,'Product is not at this location')
            return serial([dict(r) for r in await conn.fetch('SELECT * FROM purchasing.inventory_par_versions WHERE store_id=$1 AND item_code=$2 ORDER BY revision',store_id,item_code)])
