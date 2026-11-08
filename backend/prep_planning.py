"""Versioned Track 2 planning metadata; no production, stock or accounting writes."""
import prep_tracks
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
    track:prep_tracks.Track
    schedule:Literal['daily','recurring','on_demand']
    weekday_par:Decimal=Field(ge=0,max_digits=28,decimal_places=12)
    weekend_par:Decimal=Field(ge=0,max_digits=28,decimal_places=12)
    recur_days:list[Annotated[int,Field(ge=0,le=6,strict=True)]]=Field(default_factory=list,max_length=7)
    fixed_quantity:Decimal|None=Field(default=None,gt=0,max_digits=28,decimal_places=12)
    # Bulk daily pars, Monday first (migrations/20261105_bulk_daily_pars.sql); used when the store's Bulk par mode is daily.
    daily_pars:list[Annotated[Decimal,Field(ge=0,max_digits=28,decimal_places=12)]]|None=Field(default=None,min_length=7,max_length=7)
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
        if self.daily_pars is not None and (self.track!='bulk' or self.schedule!='daily'):raise ValueError('Only to-par Bulk items have daily pars')
        self.recur_days.sort()
        return self


class ParModeIn(mapping.Strict):
    """A store's Bulk par mode: window (Monday run weekday par, Thursday run weekend par) or daily
    (each run's target is the sum of the daily pars for the days it covers)."""
    mode:Literal['window','daily']
    note:str=Field(min_length=1,max_length=2000)


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


async def par_modes_installed(conn):
    return await conn.fetchval("SELECT to_regclass('prep_inventory.bulk_par_modes') IS NOT NULL")


async def bulk_par_mode(conn,store):
    """The store's current Bulk par mode; window until the store chooses daily."""
    if not await par_modes_installed(conn):return 'window'
    return await conn.fetchval('SELECT prep_inventory.bulk_par_mode($1)',store)


async def missing_daily_pars(conn,store):
    """Names of active to-par Bulk items at the store that have no daily pars yet."""
    return [r['name'] for r in await conn.fetch('''SELECT n.name FROM prep_inventory.products p
        JOIN LATERAL(SELECT * FROM prep_inventory.planning_versions v WHERE v.product_id=p.id ORDER BY v.revision DESC LIMIT 1) v ON true
        JOIN LATERAL(SELECT name FROM prep_inventory.product_versions n WHERE n.product_id=p.id ORDER BY n.revision DESC LIMIT 1) n ON true
        WHERE p.store_id=$1 AND v.active AND v.track='bulk' AND v.schedule='daily' AND v.daily_pars IS NULL ORDER BY n.name''',store)]


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
        'unitProfiles':definitions['profiles'],'plans':plans,'legacy_sources':[dict(r) for r in legacy],'bulk_par_mode':await bulk_par_mode(conn,store)})


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
            values={k:previous.get(k) for k in ('recipe_version_id','unit_profile_id','track','schedule','weekday_par','weekend_par','recur_days','fixed_quantity','daily_pars')}
            values['recipe_version_id']=UUID(values['recipe_version_id']);values['unit_profile_id']=UUID(values['unit_profile_id'])
            for k in ('weekday_par','weekend_par','fixed_quantity'):
                if values[k] is not None:values[k]=Decimal(values[k])
            if values['daily_pars'] is not None:values['daily_pars']=[Decimal(v) for v in values['daily_pars']]
        else:
            # Legacy metadata editors and ingredient editors do not all share this lock yet.
            await conn.execute('LOCK TABLE public.items,public.store_items,public.dishes,public.dish_lines,public.prep_items IN SHARE MODE')
            definitions=await mapping.setup(conn,store)
            recipe=next((r for r in definitions['recipes'] if r['id']==str(body.recipe_version_id) and r['product_id']==str(product)),None)
            if not recipe:raise HTTPException(422,'Select the current reviewed recipe for this prepared product and location')
            if recipe['reviewNeeded']:raise HTTPException(409,'Prep recipe or ingredients changed; review the definition before planning')
            await mapping.current_profile(conn,store,body.unit_profile_id,UUID(recipe['product_version_id']))
            values=body.model_dump(exclude={'action','note','verified'})
            if body.daily_pars is not None and not await par_modes_installed(conn):raise HTTPException(503,'Bulk daily pars migration is awaiting setup')
            if body.track=='bulk' and body.schedule=='daily' and body.daily_pars is None and await bulk_par_mode(conn,store)=='daily':
                raise HTTPException(422,'This store uses daily Bulk pars; enter a par for each day')
        columns='recipe_version_id,unit_profile_id,track,schedule,weekday_par,weekend_par,recur_days,fixed_quantity'
        params=[values[k] for k in columns.split(',')]
        if values.get('daily_pars') is not None:  # older databases have no daily_pars column until the migration
            columns+=',daily_pars';params.append(values['daily_pars'])
        row=await conn.fetchrow(f'''INSERT INTO prep_inventory.planning_versions(store_id,product_id,revision,predecessor_id,{columns},active,note,actor,request_key,request_fingerprint)
            VALUES({','.join(f'${n}' for n in range(1,len(params)+10))}) RETURNING *''',
            store,product,expected+1,UUID(previous['id']) if previous else None,*params,body.action=='save',body.note,actor,key,digest)
        return serial({'request_key':key,'plan':dict(row),'current_plan':dict(row),'replayed':False})


async def mode_history(conn,store):
    if not await par_modes_installed(conn):raise HTTPException(503,'Bulk par mode migration is awaiting setup')
    return [dict(r) for r in await conn.fetch('SELECT id,store_id,revision,mode,note,actor,recorded_at FROM prep_inventory.bulk_par_modes WHERE store_id=$1 ORDER BY revision',store)]


async def save_mode(pool,store,actor,body,key,expected):
    digest=fingerprint(serial({'store':store,'actor':actor,'expected':expected,'body':body.model_dump()}))
    async with pool.acquire() as conn,conn.transaction():
        await ready(conn);await lock_store(conn,store)
        history=await mode_history(conn,store)
        prior=await conn.fetchrow('SELECT * FROM prep_inventory.bulk_par_modes WHERE request_key=$1',key)
        if prior:
            if prior['request_fingerprint']!=digest:raise HTTPException(409,'Request key belongs to another Bulk par mode change')
            return serial({'request_key':key,'mode':history[-1]['mode'],'revision':history[-1]['revision'],'history':history,'replayed':True})
        latest=history[-1] if history else None
        if (latest['revision'] if latest else 0)!=expected:raise HTTPException(409,'Bulk par mode changed. Refresh before switching.')
        if (latest['mode'] if latest else 'window')==body.mode:raise HTTPException(409,f'This store already uses {body.mode} Bulk pars')
        if body.mode=='daily':
            missing=await missing_daily_pars(conn,store)
            if missing:raise HTTPException(409,f"Enter daily pars for every active Bulk item before switching: {', '.join(missing)}")
        await conn.execute('''INSERT INTO prep_inventory.bulk_par_modes(store_id,revision,predecessor_id,mode,note,actor,request_key,request_fingerprint)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8)''',store,expected+1,latest['id'] if latest else None,body.mode,body.note,actor,key,digest)
        history=await mode_history(conn,store)
        return serial({'request_key':key,'mode':body.mode,'revision':expected+1,'history':history,'replayed':False})


def install_routes(router,context):
    @router.get('/{store_id}/prep-planning')
    async def read_plans(store_id:str,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn,conn.transaction(isolation='repeatable_read',readonly=True):
            await ready(conn);return await setup(conn,store_id)

    @router.put('/{store_id}/prep-planning/{product_id}')
    async def write_plan(store_id:str,product_id:UUID,body:Command,request:Request,idempotency_key:UUID=Header(...)):
        prep_tracks.check(store_id,getattr(body,'track',None))
        actor,pool=await context(request,store_id,True,require='par')  # pars: owner/admin only
        return await save(pool,store_id,product_id,actor,body,idempotency_key,version(request))

    @router.get('/{store_id}/bulk-par-mode')
    async def read_mode(store_id:str,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn,conn.transaction(isolation='repeatable_read',readonly=True):
            await ready(conn);history=await mode_history(conn,store_id)
            return serial({'store_id':store_id,'mode':history[-1]['mode'] if history else 'window','revision':history[-1]['revision'] if history else 0,
                'history':history,'missing_daily_pars':await missing_daily_pars(conn,store_id)})

    @router.put('/{store_id}/bulk-par-mode')
    async def write_mode(store_id:str,body:ParModeIn,request:Request,idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True,require='par')  # pars: owner/admin only
        return await save_mode(pool,store_id,actor,body,idempotency_key,version(request))

    @router.get('/{store_id}/prep-planning/{product_id}/history')
    async def history(store_id:str,product_id:UUID,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn,conn.transaction(isolation='repeatable_read',readonly=True):
            await ready(conn)
            if not await conn.fetchval('SELECT 1 FROM prep_inventory.products WHERE id=$1 AND store_id=$2',product_id,store_id):raise HTTPException(404,'Prepared product is not at this location')
            return serial([dict(r) for r in await conn.fetch('SELECT * FROM prep_inventory.planning_versions WHERE store_id=$1 AND product_id=$2 ORDER BY revision',store_id,product_id)])
