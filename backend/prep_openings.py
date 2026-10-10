"""Count-derived commissioning sources, never production or raw withdrawals."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4
from typing import Literal

from fastapi import Header, HTTPException, Request
from pydantic import Field
import prep_mapping as mapping
import prep_batches as batches
import prep_observations as observations
import prep_periods as periods
from native_units import lock_store
from purchase_api import serial
from purchase_parser import fingerprint


class OpeningIn(mapping.Strict):
    count_id: UUID
    before_activity_confirmed: Literal[True]
    note: str = Field(min_length=1, max_length=2000)


class SaveIn(mapping.Strict):
    opening: OpeningIn
    expected_review_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    reviewed: Literal[True]


class VoidIn(mapping.Strict):
    reason: str = Field(min_length=1, max_length=2000)


class VoidSaveIn(mapping.Strict):
    change: VoidIn
    expected_review_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    reviewed: Literal[True]


async def ready(conn):
    await observations.ready(conn)
    if not await conn.fetchval("SELECT to_regclass('prep_inventory.opening_decisions') IS NOT NULL"):
        raise HTTPException(503, 'Opening prep sources are awaiting schema setup')


async def source_valid(conn, lot):
    if lot.get('source_kind', 'production') != 'opening': return True
    return await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM prep_inventory.opening_decisions d
        JOIN prep_inventory.observations c ON c.id=d.count_id WHERE d.id=$1 AND d.kind='initial'
        AND NOT EXISTS(SELECT 1 FROM prep_inventory.opening_decisions n WHERE n.predecessor_id=d.id)
        AND c.kind<>'void' AND NOT EXISTS(SELECT 1 FROM prep_inventory.observations n WHERE n.predecessor_id=c.id))''', lot['opening_decision_id'])


async def preview(conn, store, body=None, old_id=None, change=None):
    await ready(conn)
    if old_id:
        old = await conn.fetchrow('SELECT * FROM prep_inventory.opening_decisions WHERE id=$1 AND store_id=$2', old_id, store)
        if not old: raise HTTPException(404, 'Opening decision is not at this location')
        if old['kind']=='void' or await conn.fetchval('SELECT 1 FROM prep_inventory.opening_decisions WHERE predecessor_id=$1', old_id):
            raise HTTPException(409, 'Opening decision is already voided; refresh its history')
        lots = await conn.fetch("SELECT * FROM prep_inventory.batch_events WHERE opening_decision_id=$1 AND source_kind='opening' ORDER BY product_id::text", old_id)
        for lot in lots:
            if await conn.fetchval('SELECT prep_inventory.lot_used($1)',lot['id']):
                raise HTTPException(409, 'Opening stock has dependent prep or waste. Resolve those records before voiding its source.')
        count = await conn.fetchrow('SELECT * FROM prep_inventory.observations WHERE id=$1',old['count_id'])
        p = {'kind':'void','predecessor_id':old_id,'root_id':old['root_id'],'revision':old['revision']+1,
             'reason':change.reason,'count':dict(count),'lots':[{'product_id':l['product_id'],'product_version_id':l['product_version_id'],
                 'base_unit':l['base_unit'],'count_line_id':l['count_line_id'],'quantity':'0','predecessor_id':l['id'],'root_id':l['root_id'],
                 'revision':l['revision']+1} for l in lots], 'before_activity_confirmed':True}
    else:
        if not body.before_activity_confirmed: raise HTTPException(422, 'Confirm this count precedes recorded prep and waste activity')
        count = await periods.count(conn, store, body.count_id)
        if await conn.fetchval("SELECT 1 FROM prep_inventory.opening_decisions d WHERE store_id=$1 AND kind='initial' AND NOT EXISTS(SELECT 1 FROM prep_inventory.opening_decisions n WHERE n.predecessor_id=d.id)", store):
            raise HTTPException(409, 'Opening prep stock is already established; this count cannot reset it')
        if await conn.fetchval("SELECT EXISTS(SELECT 1 FROM prep_inventory.batch_events WHERE store_id=$1 AND source_kind='production') OR EXISTS(SELECT 1 FROM prep_inventory.observations WHERE store_id=$1 AND purpose='waste')", store):
            raise HTTPException(409, 'Opening sources must be established before any recorded production or waste history; historical reconciliation is a separate workflow')
        lines = await conn.fetch('SELECT * FROM prep_inventory.count_observations WHERE event_id=$1 ORDER BY product_id::text', body.count_id)
        if count['review_snapshot']['scope'] != [str(x['id']) for x in await conn.fetch('SELECT id FROM prep_inventory.products WHERE store_id=$1 ORDER BY id::text',store)]:
            raise HTTPException(409, 'Opening count no longer covers the current prepared scope; take a complete current count')
        p={'kind':'initial','predecessor_id':None,'root_id':None,'revision':1,'reason':body.note,'count':count,
           'lots':[{'product_id':l['product_id'],'product_version_id':l['product_version_id'],'base_unit':l['base_unit'],
               'count_line_id':l['id'],'quantity':format(l['base_quantity'],'f'),'predecessor_id':None,'root_id':None,'revision':1} for l in lines if l['base_quantity']>0],
           'before_activity_confirmed':True}
    p['cost']={'status':'not_calculated','amount':None};p=serial(p)
    return {'review':p,'reviewHash':fingerprint(p).hex()}


async def persist(conn, store, plan, key, digest, actor):
    p=plan['review']; ident=uuid4();count=p['count']
    def uid(v):return UUID(str(v)) if v else None
    saved=await conn.fetchrow('''INSERT INTO prep_inventory.opening_decisions(id,store_id,root_id,predecessor_id,revision,kind,count_id,reason,review_snapshot,review_hash,recorded_by,request_key,request_fingerprint)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13) RETURNING *''',ident,store,uid(p['root_id']) or ident,uid(p['predecessor_id']),p['revision'],p['kind'],uid(count['id']),p['reason'],p,bytes.fromhex(plan['reviewHash']),actor,key,digest)
    for lot in p['lots']:
        child=uuid4();old=uid(lot['predecessor_id']);movements=[]
        if old:
            for m in await conn.fetch("SELECT * FROM prep_inventory.batch_movements WHERE event_id=$1 AND side='apply' ORDER BY ordinal",old):
                movements.append({k:m[k] for k in ('kind','recipe_version_id','recipe_line_id','raw_item_code','product_id','base_unit','source_batch_id')}|
                    {'side':'reverse','quantity':format(m['quantity'].copy_negate(),'f'),'reverses_movement_id':m['id']})
        else:
            movements.append({'side':'apply','kind':'output','recipe_version_id':None,'recipe_line_id':None,'raw_item_code':None,
                'product_id':lot['product_id'],'base_unit':lot['base_unit'],'quantity':lot['quantity'],'source_batch_id':None,'reverses_movement_id':None})
        v=serial({'source_kind':'opening','opening_decision_id':ident,'count_line_id':lot['count_line_id'],
            'kind':p['kind'],'predecessor_id':old,'root_id':lot['root_id'],'revision':lot['revision'],'reason':p['reason'],
            'product_id':lot['product_id'],'product_version_id':lot['product_version_id'],'recipe_version_id':None,
            'base_unit':lot['base_unit'],'performed_at':count['performed_at'],'business_date':count['business_date'],'timezone_name':count['timezone_name'],
            'inputs':[],'movements':movements,'usableBaseOutput':lot['quantity'] if not old else None,'cost':p['cost']})
        await conn.execute('''INSERT INTO prep_inventory.batch_events(id,store_id,root_id,predecessor_id,revision,kind,recipe_version_id,product_id,product_version_id,base_unit,
            performed_at,business_date,timezone_name,reason,review_snapshot,review_hash,recorded_by,request_key,request_fingerprint,source_kind,opening_decision_id,count_line_id)
            VALUES($1,$2,$3,$4,$5,$6,NULL,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,'opening',$19,$20)''',
            child,store,uid(lot['root_id']) or child,old,lot['revision'],p['kind'],uid(lot['product_id']),uid(lot['product_version_id']),lot['base_unit'],
            datetime.fromisoformat(count['performed_at']),date.fromisoformat(count['business_date']),count['timezone_name'],p['reason'],v,fingerprint(v),actor,uuid4(),fingerprint(v),ident,uid(lot['count_line_id']))
        for n,m in enumerate(movements,1):
            await conn.execute('''INSERT INTO prep_inventory.batch_movements(event_id,store_id,ordinal,side,kind,recipe_version_id,recipe_line_id,raw_item_code,product_id,base_unit,quantity,source_batch_id,reverses_movement_id)
                VALUES($1,$2,$3,$4,'output',NULL,NULL,NULL,$5,$6,$7,NULL,$8)''',child,store,n,m['side'],uid(m['product_id']),m['base_unit'],Decimal(m['quantity']),uid(str(m['reverses_movement_id'])) if m['reverses_movement_id'] else None)
    return serial({'event':dict(saved),'replayed':False})


async def activity_time(conn, store, instant):
    if not await conn.fetchval("SELECT to_regclass('prep_inventory.opening_decisions') IS NOT NULL"): return
    row=await conn.fetchrow("SELECT d.id,c.performed_at FROM prep_inventory.opening_decisions d JOIN prep_inventory.observations c ON c.id=d.count_id WHERE d.store_id=$1 AND d.kind='initial' AND NOT EXISTS(SELECT 1 FROM prep_inventory.opening_decisions n WHERE n.predecessor_id=d.id)",store)
    if row and (instant<row['performed_at'] or not await conn.fetchval('SELECT prep_inventory.opening_source_valid($1)',row['id'])):
        raise HTTPException(409,'Activity must follow the current reviewed opening count; reconcile its source before recording')


def install_routes(router, context):
    async def ctx(request,store):
        actor,pool=await context(request,store,True)
        if not observations.enabled():raise HTTPException(503,'Opening prep sources are awaiting enablement')
        return actor,pool
    @router.get('/{store_id}/prep-openings/setup')
    async def setup(store_id:str,request:Request):
        _,pool=await ctx(request,store_id)
        async with pool.acquire() as c:
            async with c.transaction(isolation='repeatable_read',readonly=True):
                await ready(c)
                decisions=await c.fetch('SELECT * FROM prep_inventory.opening_decisions WHERE store_id=$1 ORDER BY recorded_at,id',store_id)
                counts=await c.fetch("SELECT id,performed_at,business_date FROM prep_inventory.observations e WHERE store_id=$1 AND purpose='count' AND kind<>'void' AND NOT EXISTS(SELECT 1 FROM prep_inventory.observations n WHERE n.predecessor_id=e.id) ORDER BY performed_at",store_id)
                return serial({'store_id':store_id,'counts':[dict(x) for x in counts],'decisions':[dict(x) for x in decisions]})
    @router.post('/{store_id}/prep-openings/preview')
    async def review(store_id:str,body:OpeningIn,request:Request):
        _,pool=await ctx(request,store_id)
        async with pool.acquire() as c:
            async with c.transaction(isolation='repeatable_read',readonly=True):return await preview(c,store_id,body)
    @router.post('/{store_id}/prep-openings/{event_id}/void-preview')
    async def void_review(store_id:str,event_id:UUID,body:VoidIn,request:Request):
        _,pool=await ctx(request,store_id)
        async with pool.acquire() as c:
            async with c.transaction(isolation='repeatable_read',readonly=True):return await preview(c,store_id,old_id=event_id,change=body)
    async def save(request,store,body,key,old=None):
        if not body.reviewed:raise HTTPException(422,'Explicit review approval required')
        actor,pool=await ctx(request,store);digest=fingerprint({'body':body.model_dump(mode='json'),'predecessor':str(old) if old else None})
        async with pool.acquire() as c:
            async with c.transaction():
                await ready(c);await c.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))',str(key));await lock_store(c,store)
                prior=await mapping.replay(c,'opening_decisions',store,key,digest)
                if prior:return serial({'event':prior,'replayed':True})
                plan=await preview(c,store,body.opening if not old else None,old,body.change if old else None)
                if plan['reviewHash']!=body.expected_review_hash:raise HTTPException(409,'Opening source changed. Review a fresh preview.')
                return await persist(c,store,plan,key,digest,actor)
    @router.post('/{store_id}/prep-openings')
    async def record(store_id:str,body:SaveIn,request:Request,idempotency_key:UUID=Header(...)):return await save(request,store_id,body,idempotency_key)
    @router.post('/{store_id}/prep-openings/{event_id}/void')
    async def void(store_id:str,event_id:UUID,body:VoidSaveIn,request:Request,idempotency_key:UUID=Header(...)):return await save(request,store_id,body,idempotency_key,event_id)
