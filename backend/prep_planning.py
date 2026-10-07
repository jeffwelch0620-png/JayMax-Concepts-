"""Versioned Track 2 planning metadata; no production, stock or accounting writes."""
import os
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from fastapi import Header, HTTPException, Request
from pydantic import Field, field_validator, model_validator
import prep_mapping as mapping
import catalog_mapping
from native_units import lock_store
from purchase_api import serial
from purchase_parser import fingerprint


def enabled():
    requested=os.getenv('PREP_PLANNING_ENABLED','false').lower()=='true'
    if requested and (not mapping.enabled() or not catalog_mapping.enabled()):
        raise HTTPException(503,'Prep planning requires reviewed prep setup and canonical catalog mapping')
    return requested


async def installed(conn):
    return await conn.fetchval("SELECT to_regclass('prep_inventory.planning_versions') IS NOT NULL")


async def ready(conn):
    if not enabled():raise HTTPException(503,'Prep planning is awaiting enablement')
    await mapping.ready(conn);await catalog_mapping.ready(conn)
    if not await installed(conn):raise HTTPException(503,'Prep planning migration is awaiting setup')


async def hold_legacy(conn):
    if enabled() or await installed(conn):
        raise HTTPException(409,'Legacy standing prep metadata is retained. Use reviewed prep planning; list execution cutover is still pending.')


class SavePlan(mapping.Strict):
    action:Literal['save']
    recipe_version_id:UUID
    unit_profile_id:UUID
    track:Literal['daily','bulk']
    schedule:Literal['daily','recurring','on_demand']
    weekday_par:Decimal=Field(ge=0,max_digits=28,decimal_places=12)
    weekend_par:Decimal=Field(ge=0,max_digits=28,decimal_places=12)
    recur_days:list[Annotated[int,Field(ge=0,le=6,strict=True)]]=Field(default_factory=list,max_length=7)
    fixed_quantity:Decimal|None=Field(default=None,gt=0,max_digits=28,decimal_places=12)
    note:str=Field(min_length=1,max_length=2000)
    verified:Literal[True]

    @field_validator('verified',mode='before')
    @classmethod
    def explicit_review(cls,value):
        if value is not True:raise ValueError('Explicitly confirm the reviewed planning quantities')
        return value

    @model_validator(mode='after')
    def scheduling(self):
        if len(set(self.recur_days))!=len(self.recur_days):raise ValueError('Choose each weekday once (Monday is zero)')
        if self.schedule=='recurring':
            if not self.recur_days or self.fixed_quantity is None:raise ValueError('Recurring prep requires weekdays and a positive fixed quantity')
        elif self.recur_days or self.fixed_quantity is not None:raise ValueError('Only recurring prep has weekdays and a fixed quantity')
        self.recur_days.sort()
        return self


class RetirePlan(mapping.Strict):
    action:Literal['retire']
    note:str=Field(min_length=1,max_length=2000)


Command=Annotated[SavePlan|RetirePlan,Field(discriminator='action')]


def version(request):
    raw=request.headers.get('if-match','').strip('"')
    if not raw:raise HTTPException(428,'Refresh the plan and supply its version; zero means no saved plan')
    if not raw.isdigit() or not 0<=int(raw)<2**31-1:raise HTTPException(422,'Supply a valid prep planning version')
    return int(raw)


async def current(conn,store,product):
    row=await conn.fetchrow('SELECT * FROM prep_inventory.planning_versions WHERE store_id=$1 AND product_id=$2 ORDER BY revision DESC LIMIT 1',store,product)
    return serial(dict(row)) if row else None


async def setup(conn,store):
    definitions=await mapping.setup(conn,store)
    plans=[dict(r) for r in await conn.fetch('SELECT DISTINCT ON(product_id) * FROM prep_inventory.planning_versions WHERE store_id=$1 ORDER BY product_id,revision DESC',store)]
    recipes={str(r['id']):r for r in definitions['recipes']}
    for p in plans:
        recipe=recipes.get(str(p['recipe_version_id']))
        p['reviewNeeded']=not recipe or recipe['reviewNeeded']
        if recipe and not p['reviewNeeded']:
            try:await mapping.current_profile(conn,store,p['unit_profile_id'],UUID(recipe['product_version_id']))
            except HTTPException:p['reviewNeeded']=True
    legacy=await conn.fetch('SELECT source_id,raw_record FROM prep_inventory.legacy_planning_sources WHERE store_id=$1 ORDER BY source_id',store)
    return serial({'store_id':store,'products':definitions['products'],'recipes':definitions['recipes'],
        'unitProfiles':definitions['profiles'],'plans':plans,'legacy_sources':[dict(r) for r in legacy]})


async def save(pool,store,product,actor,body,key,expected):
    digest=fingerprint(serial({'store':store,'product':product,'actor':actor,'expected':expected,'body':body.model_dump()}))
    async with pool.acquire() as conn,conn.transaction():
        await ready(conn);await catalog_mapping.lock_catalog(conn);await lock_store(conn,store)
        prior=await conn.fetchrow('SELECT * FROM prep_inventory.planning_versions WHERE request_key=$1',key)
        if prior:
            if prior['request_fingerprint']!=digest:raise HTTPException(409,'Request key belongs to another prep planning edit')
            return serial({'request_key':key,'plan':dict(prior),'current_plan':await current(conn,store,product),'replayed':True})
        previous=await current(conn,store,product)
        if (previous['revision'] if previous else 0)!=expected:raise HTTPException(409,'Prep planning changed. Refresh and review your retained entry.')
        if body.action=='retire':
            if not previous or not previous['active']:raise HTTPException(409,'Only an active saved plan can be retired')
            values={k:previous[k] for k in ('recipe_version_id','unit_profile_id','track','schedule','weekday_par','weekend_par','recur_days','fixed_quantity')}
            values['recipe_version_id']=UUID(values['recipe_version_id']);values['unit_profile_id']=UUID(values['unit_profile_id'])
            for k in ('weekday_par','weekend_par','fixed_quantity'):
                if values[k] is not None:values[k]=Decimal(values[k])
        else:
            # Legacy metadata editors and ingredient editors do not all share this lock yet.
            await conn.execute('LOCK TABLE public.items,public.store_items,public.dishes,public.dish_lines,public.prep_items IN SHARE MODE')
            definitions=await mapping.setup(conn,store)
            recipe=next((r for r in definitions['recipes'] if r['id']==str(body.recipe_version_id) and r['product_id']==str(product)),None)
            if not recipe:raise HTTPException(422,'Select the current reviewed recipe for this prepared product and location')
            if recipe['reviewNeeded']:raise HTTPException(409,'Prep recipe or ingredients changed; review the definition before planning')
            await mapping.current_profile(conn,store,body.unit_profile_id,UUID(recipe['product_version_id']))
            values=body.model_dump(exclude={'action','note','verified'})
        row=await conn.fetchrow('''INSERT INTO prep_inventory.planning_versions(store_id,product_id,revision,predecessor_id,
            recipe_version_id,unit_profile_id,track,schedule,weekday_par,weekend_par,recur_days,fixed_quantity,active,note,actor,request_key,request_fingerprint)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17) RETURNING *''',
            store,product,expected+1,UUID(previous['id']) if previous else None,values['recipe_version_id'],values['unit_profile_id'],
            values['track'],values['schedule'],values['weekday_par'],values['weekend_par'],values['recur_days'],values['fixed_quantity'],
            body.action=='save',body.note,actor,key,digest)
        return serial({'request_key':key,'plan':dict(row),'current_plan':dict(row),'replayed':False})


def install_routes(router,context):
    @router.get('/{store_id}/prep-planning')
    async def read_plans(store_id:str,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn,conn.transaction(isolation='repeatable_read',readonly=True):
            await ready(conn);return await setup(conn,store_id)

    @router.put('/{store_id}/prep-planning/{product_id}')
    async def write_plan(store_id:str,product_id:UUID,body:Command,request:Request,idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True)
        return await save(pool,store_id,product_id,actor,body,idempotency_key,version(request))

    @router.get('/{store_id}/prep-planning/{product_id}/history')
    async def history(store_id:str,product_id:UUID,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn,conn.transaction(isolation='repeatable_read',readonly=True):
            await ready(conn)
            if not await conn.fetchval('SELECT 1 FROM prep_inventory.products WHERE id=$1 AND store_id=$2',product_id,store_id):raise HTTPException(404,'Prepared product is not at this location')
            return serial([dict(r) for r in await conn.fetch('SELECT * FROM prep_inventory.planning_versions WHERE store_id=$1 AND product_id=$2 ORDER BY revision',store_id,product_id)])
