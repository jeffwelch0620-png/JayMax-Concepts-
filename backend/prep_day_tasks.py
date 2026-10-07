"""Reviewed dated Track 2 drafts and overrides. No execution or stock writers."""
import os
from datetime import date,timedelta
from decimal import Decimal,localcontext
from typing import Literal
from uuid import UUID
from fastapi import Header,HTTPException,Request
from pydantic import Field,field_validator,model_validator
import prep_planning as planning
import prep_mapping as mapping
import prep_observations as observations
import catalog_mapping
from native_units import lock_store
from purchase_api import serial
from purchase_parser import fingerprint


def enabled():
    requested=os.getenv('PREP_DAY_TASKS_ENABLED','false').lower()=='true'
    if requested and (not planning.enabled() or not observations.enabled()):raise HTTPException(503,'Dated prep tasks require reviewed planning and native prep observations')
    return requested


async def installed(conn):return await conn.fetchval("SELECT to_regclass('prep_inventory.day_list_versions') IS NOT NULL")


async def ready(conn):
    if not enabled():raise HTTPException(503,'Dated prep task drafts are awaiting enablement')
    await planning.ready(conn);await observations.ready(conn)
    if not await installed(conn):raise HTTPException(503,'Dated prep task migration is awaiting setup')


async def hold_legacy(conn):
    if enabled() or await installed(conn):raise HTTPException(409,'Legacy prep lists and day overrides are retained. Use reviewed dated prep drafts; release and completion are awaiting cutover.')


class Override(mapping.Strict):
    planning_version_id:UUID
    kind:Literal['target_par','fixed_quantity','omit']
    quantity:Decimal|None=Field(default=None,ge=0,max_digits=28,decimal_places=12)
    reason:str=Field(min_length=1,max_length=2000)

    @model_validator(mode='after')
    def quantity_for_kind(self):
        if (self.kind=='omit')!=(self.quantity is None):raise ValueError('Quantity is required except when omitting an item')
        return self


class DraftIn(mapping.Strict):
    track:Literal['daily','bulk']
    day_group:Literal['weekday','weekend']
    count_event_id:UUID|None=None
    overrides:list[Override]=Field(default_factory=list,max_length=500)
    note:str=Field(min_length=1,max_length=2000)

    @model_validator(mode='after')
    def unique_overrides(self):
        if len({o.planning_version_id for o in self.overrides})!=len(self.overrides):raise ValueError('Override each standing plan once')
        self.overrides.sort(key=lambda o:str(o.planning_version_id))
        return self


class CommitIn(mapping.Strict):
    draft:DraftIn
    expected_review_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    reviewed:Literal[True]

    @field_validator('reviewed',mode='before')
    @classmethod
    def explicit_review(cls,value):
        if value is not True:raise ValueError('Explicitly review this dated draft')
        return value


async def counts(conn,store,day):
    return await conn.fetch('''SELECT o.* FROM prep_inventory.observations o WHERE store_id=$1 AND purpose='count'
        AND business_date=$2 AND kind<>'void' AND NOT EXISTS(SELECT 1 FROM prep_inventory.observations c WHERE c.predecessor_id=o.id)
        ORDER BY performed_at DESC,id''',store,day-timedelta(days=1))


async def latest(conn,store,day,track):
    r=await conn.fetchrow('''SELECT v.* FROM prep_inventory.day_lists d JOIN prep_inventory.day_list_versions v ON v.list_id=d.id
        WHERE d.store_id=$1 AND d.prep_date=$2 AND d.track=$3 ORDER BY v.revision DESC LIMIT 1''',store,day,track)
    return serial(dict(r)) if r else None


def subtract(a,b):
    with localcontext() as ctx:ctx.prec=100;return max(a-b,Decimal(0))


def exact_source_quantity(base,factor):
    with localcontext() as ctx:
        ctx.prec=100
        value=(base/factor).quantize(Decimal('0.000000000001'))
        return value if mapping.times(value,factor)==base and value<Decimal('1e16') else None


async def preview(conn,store,day,body,expected):
    await ready(conn)
    previous=await latest(conn,store,day,body.track)
    if previous and await conn.fetchval("SELECT to_regclass('prep_inventory.execution_events') IS NOT NULL"):
        phase=await conn.fetchval("SELECT action FROM prep_inventory.execution_events WHERE list_id=$1 AND action IN ('release','reopen') ORDER BY revision DESC LIMIT 1",UUID(previous['list_id']))
        if phase=='release':raise HTTPException(409,'Reopen the released dated draft before editing')
    if (previous['revision'] if previous else 0)!=expected:raise HTTPException(409,'Dated prep draft changed. Refresh and review your retained entries.')
    setup=await planning.setup(conn,store)
    plans=[p for p in setup['plans'] if p['active'] and p['track']==body.track]
    if len(plans)>500:raise HTTPException(422,'Dated draft supports at most 500 standing prep plans')
    by_id={p['id']:p for p in plans}
    if any(str(o.planning_version_id) not in by_id for o in body.overrides):raise HTTPException(409,'An overridden standing plan changed, retired or belongs to another track/location')
    overrides={str(o.planning_version_id):o for o in body.overrides}
    prior_counts=await counts(conn,store,day)
    count=None;count_lines={}
    if body.count_event_id:
        if not prior_counts or prior_counts[0]['id']!=body.count_event_id:raise HTTPException(409,'Choose the latest current physical prep count from the previous calendar day; corrected, voided or older counts are held')
        count=dict(prior_counts[0])
        count_lines={str(l['product_id']):dict(l) for l in await conn.fetch('SELECT * FROM prep_inventory.count_observations WHERE event_id=$1',body.count_event_id)}
    recipes={r['id']:r for r in setup['recipes']};profiles={p['id']:p for p in setup['unitProfiles']};products={p['product_id']:p for p in setup['products']}
    tasks=[]
    for p in sorted(plans,key=lambda p:p['product_id']):
        override=overrides.get(p['id'])
        scheduled=p['schedule']=='daily' or (p['schedule']=='recurring' and day.weekday() in p['recur_days'])
        included=override.kind!='omit' if override else scheduled
        recipe=recipes.get(p['recipe_version_id']);profile=profiles.get(p['unit_profile_id'])
        if included and (p['reviewNeeded'] or not recipe or not profile):raise HTTPException(409,'A scheduled prep definition, recipe or unit changed; review its standing plan before generating tasks')
        # Historical profiles stay readable even for an omitted obsolete definition.
        if not profile:profile=dict(await conn.fetchrow('SELECT * FROM prep_inventory.unit_profiles WHERE id=$1',UUID(p['unit_profile_id'])))
        factor=Decimal(str(profile['base_units_per_source_unit']));target=None;counted=None;needed=None;qty=None;issue=None
        mode=override.kind if override else ('fixed_quantity' if p['schedule']=='recurring' else 'target_par')
        if not included:mode='omit';qty=Decimal(0);needed=Decimal(0)
        elif mode=='fixed_quantity':
            qty=override.quantity if override else Decimal(p['fixed_quantity']);needed=mapping.times(qty,factor)
        else:
            target=override.quantity if override else Decimal(p['weekend_par'] if body.day_group=='weekend' else p['weekday_par'])
            line=count_lines.get(p['product_id'])
            if not line:issue='Physical prep count is missing for this product; no zero stock assumed'
            else:
                counted=line['base_quantity'];needed=subtract(mapping.times(target,factor),counted);qty=exact_source_quantity(needed,factor)
                if qty is None:issue='Exact deficit cannot be expressed within 12 decimal places in this unit; enter a reviewed fixed quantity'
        tasks.append(serial({'ordinal':len(tasks)+1,'product_id':p['product_id'],'planning_version_id':p['id'],'recipe_version_id':p['recipe_version_id'],
            'unit_profile_id':p['unit_profile_id'],'name':products[p['product_id']]['name'],'source_unit':profile['source_unit'],'base_unit':products[p['product_id']]['base_unit'],
            'factor':factor,'included':included,'mode':mode,'target_par':target,'counted_base_quantity':counted,'needed_base_quantity':needed,
            'planned_quantity':qty,'planned_base_quantity':mapping.times(qty,factor) if qty is not None else None,'issue':issue,
            'override_reason':override.reason if override else None}))
    review=serial({'store_id':store,'prep_date':day,'track':body.track,'base_revision':expected,'inputs':body.model_dump(),
        'source_scope':sorted(p['id'] for p in plans),'count':count,'tasks':tasks,'status':'draft','execution_ready':False,
        'unresolved_tasks':sum(t['included'] and t['planned_quantity'] is None for t in tasks)})
    return {'review':review,'reviewHash':fingerprint(review).hex()}


async def read(conn,store,day,track):
    await ready(conn);setup=await planning.setup(conn,store)
    current=await latest(conn,store,day,track);available_counts=await counts(conn,store,day)
    if current:
        review=current['review_snapshot'];scope=sorted(p['id'] for p in setup['plans'] if p['active'] and p['track']==track)
        saved_count=review['inputs']['count_event_id']
        changed=scope!=review['source_scope'] or (bool(saved_count) and (not available_counts or str(available_counts[0]['id'])!=saved_count))
        scheduled={t['planning_version_id'] for t in review['tasks'] if t['included']}
        current['source_changed']=changed or any(p['reviewNeeded'] and p['id'] in scheduled for p in setup['plans'])
    phase=None
    if current and await conn.fetchval("SELECT to_regclass('prep_inventory.execution_events') IS NOT NULL"):
        phase=await conn.fetchval("SELECT action FROM prep_inventory.execution_events WHERE list_id=$1 AND action IN ('release','reopen') ORDER BY revision DESC LIMIT 1",UUID(current['list_id']))
    return serial({'store_id':store,'prep_date':day,'track':track,'current':current,'planning':setup,'execution_status':'released' if phase=='release' else 'draft',
        'counts':[{'id':c['id'],'business_date':c['business_date'],'performed_at':c['performed_at'],'timezone_name':c['timezone_name'],'latest':n==0} for n,c in enumerate(available_counts)]})


async def commit(pool,store,day,actor,body,key,expected):
    digest=fingerprint(serial({'store':store,'day':day,'actor':actor,'expected':expected,'body':body.model_dump()}))
    async with pool.acquire() as conn,conn.transaction():
        await ready(conn);await catalog_mapping.lock_catalog(conn);await lock_store(conn,store)
        prior=await conn.fetchrow('SELECT * FROM prep_inventory.day_list_versions WHERE request_key=$1',key)
        if prior:
            if prior['request_fingerprint']!=digest:raise HTTPException(409,'Request key belongs to another dated prep edit')
            return serial({'request_key':key,'draft':dict(prior),'current_draft':await latest(conn,store,day,body.draft.track),'replayed':True})
        await conn.execute('LOCK TABLE public.items,public.store_items,public.dishes,public.dish_lines,public.prep_items IN SHARE MODE')
        plan=await preview(conn,store,day,body.draft,expected)
        if plan['reviewHash']!=body.expected_review_hash:raise HTTPException(409,'Planning, recipe, unit or physical count changed. Review a fresh preview.')
        identity=await conn.fetchval('''INSERT INTO prep_inventory.day_lists(store_id,prep_date,track) VALUES($1,$2,$3)
            ON CONFLICT(store_id,prep_date,track) DO NOTHING RETURNING id''',store,day,body.draft.track)
        if not identity:identity=await conn.fetchval('SELECT id FROM prep_inventory.day_lists WHERE store_id=$1 AND prep_date=$2 AND track=$3',store,day,body.draft.track)
        previous=await latest(conn,store,day,body.draft.track)
        row=await conn.fetchrow('''INSERT INTO prep_inventory.day_list_versions(list_id,store_id,revision,predecessor_id,count_event_id,
            day_group,note,actor,review_snapshot,review_hash,request_key,request_fingerprint)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) RETURNING *''',identity,store,expected+1,
            UUID(previous['id']) if previous else None,body.draft.count_event_id,body.draft.day_group,body.draft.note,actor,plan['review'],bytes.fromhex(plan['reviewHash']),key,digest)
        for t in plan['review']['tasks']:
            await conn.execute('''INSERT INTO prep_inventory.day_tasks(version_id,store_id,ordinal,product_id,planning_version_id,recipe_version_id,
                unit_profile_id,included,planned_quantity,factor,planned_base_quantity,task_snapshot)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)''',row['id'],store,t['ordinal'],UUID(t['product_id']),UUID(t['planning_version_id']),
                UUID(t['recipe_version_id']),UUID(t['unit_profile_id']),t['included'],Decimal(t['planned_quantity']) if t['planned_quantity'] is not None else None,
                Decimal(t['factor']),Decimal(t['planned_base_quantity']) if t['planned_base_quantity'] is not None else None,t)
        return serial({'request_key':key,'draft':dict(row),'current_draft':dict(row),'replayed':False})


def install_routes(router,context):
    @router.get('/{store_id}/prep-day-drafts/{day}')
    async def read_draft(store_id:str,day:date,request:Request,track:Literal['daily','bulk']='daily'):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn,conn.transaction(isolation='repeatable_read',readonly=True):return await read(conn,store_id,day,track)

    @router.post('/{store_id}/prep-day-drafts/{day}/preview')
    async def preview_draft(store_id:str,day:date,body:DraftIn,request:Request):
        _,pool=await context(request,store_id,True)
        async with pool.acquire() as conn,conn.transaction(isolation='repeatable_read',readonly=True):return await preview(conn,store_id,day,body,planning.version(request))

    @router.put('/{store_id}/prep-day-drafts/{day}')
    async def save_draft(store_id:str,day:date,body:CommitIn,request:Request,idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True)
        return await commit(pool,store_id,day,actor,body,idempotency_key,planning.version(request))

    @router.get('/{store_id}/prep-day-drafts/{day}/history')
    async def history(store_id:str,day:date,request:Request,track:Literal['daily','bulk']='daily'):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn,conn.transaction(isolation='repeatable_read',readonly=True):
            await ready(conn)
            return serial([dict(r) for r in await conn.fetch('''SELECT v.* FROM prep_inventory.day_lists d JOIN prep_inventory.day_list_versions v ON v.list_id=d.id
                WHERE d.store_id=$1 AND d.prep_date=$2 AND d.track=$3 ORDER BY v.revision''',store_id,day,track)])
