"""Immutable analytical periods and zero-only scope additions; no stock writes."""
import copy
from uuid import UUID, uuid4
from typing import Literal
from fastapi import Header, HTTPException, Request
from pydantic import Field, model_validator
import prep_mapping as mapping
import prep_observations as observations
import prep_periods as periods
from native_units import lock_store
from purchase_api import serial
from purchase_parser import fingerprint

class ZeroAddition(mapping.Strict):
    product_id: UUID
    zero_at_opening_confirmed: Literal[True]
    evidence: str = Field(min_length=1, max_length=2000)

class CloseIn(mapping.Strict):
    period: periods.PeriodIn
    zero_additions: list[ZeroAddition] = Field(default_factory=list, max_length=500)
    reason: str = Field(min_length=1, max_length=2000)
    @model_validator(mode='after')
    def unique(self):
        if len({x.product_id for x in self.zero_additions}) != len(self.zero_additions): raise ValueError('Confirm each added identity once')
        if not self.reason.strip() or any(not x.evidence.strip() for x in self.zero_additions): raise ValueError('Retain a review reason and evidence for each added zero')
        return self

class ReopenIn(mapping.Strict):
    from_closure_id: UUID
    reason: str = Field(min_length=1, max_length=2000)
    @model_validator(mode='after')
    def reason_present(self):
        if not self.reason.strip(): raise ValueError('Explain why the analytical snapshots are reopened')
        return self

class SaveClose(mapping.Strict):
    submission: CloseIn
    expected_review_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    reviewed: Literal[True]

class SaveReopen(mapping.Strict):
    submission: ReopenIn
    expected_review_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    reviewed: Literal[True]

async def ready(conn):
    await observations.ready(conn)
    if not await conn.fetchval("SELECT to_regclass('prep_inventory.period_closures') IS NOT NULL"): raise HTTPException(503, 'Saved prep periods are awaiting schema setup')

async def active(conn, store):
    return [dict(x) for x in await conn.fetch('''SELECT c.* FROM prep_inventory.period_closures c WHERE c.store_id=$1
        AND NOT EXISTS(SELECT 1 FROM prep_inventory.period_reopenings r WHERE r.store_id=c.store_id AND c.id=ANY(r.closure_ids)) ORDER BY c.ordinal''', store)]

async def facts(conn, store, body):
    opening = await periods.count(conn, store, body.period.opening_count_id)
    closing = await periods.count(conn, store, body.period.closing_count_id)
    from prep_openings import activity_time
    await activity_time(conn, store, opening['performed_at'])
    left, right = opening['review_snapshot'], closing['review_snapshot']
    added = set(right['scope']) - set(left['scope'])
    supplied = {str(x.product_id): x for x in body.zero_additions}
    if set(left['scope']) - set(right['scope']): raise HTTPException(409, 'Scope removals need a separate retirement workflow; preserve the counted identities')
    if set(supplied) != added: raise HTTPException(409, 'Confirm exactly the added identities as measured zero at the opening boundary; nonzero additions cannot be inferred')
    events, history = [], []
    for table, extra in [('batch_events', "AND e.source_kind='production'"), ('observations', "AND e.purpose='waste'")]:
        rows = await conn.fetch(f'''SELECT e.*, EXISTS(SELECT 1 FROM prep_inventory.{table} n WHERE n.predecessor_id=e.id) AS superseded
            FROM prep_inventory.{table} e WHERE store_id=$1 AND performed_at >= $2 AND performed_at <= $3 {extra}''', store, opening['performed_at'], closing['performed_at'])
        history.extend(serial({'journal': table, **periods.source(dict(x))}) for x in rows)
        events.extend(dict(x) for x in rows if not x['superseded'] and x['kind'] != 'void')
    projection = copy.deepcopy(opening); handoff = []
    for pid in sorted(added):
        line = next(x for x in right['lines'] if x['product_id'] == pid)
        if await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM prep_inventory.batch_movements m JOIN prep_inventory.batch_events e ON e.id=m.event_id
            WHERE e.store_id=$1 AND m.product_id=$2 AND e.performed_at<$3
            UNION ALL SELECT 1 FROM prep_inventory.observations WHERE store_id=$1 AND purpose='waste' AND product_id=$2 AND performed_at<$3
            UNION ALL SELECT 1 FROM prep_inventory.count_observations l JOIN prep_inventory.observations o ON o.id=l.event_id
            WHERE l.store_id=$1 AND l.product_id=$2 AND o.performed_at<$3 AND l.base_quantity<>0)''', store, UUID(pid), opening['performed_at']):
            raise HTTPException(409, 'Added item has earlier recorded stock/activity; historical reconciliation is required instead of a zero handoff')
        for event in events:
            if event['performed_at'] == opening['performed_at'] and body.period.opening_cutoff == 'after_all' and any(m.get('product_id') == pid for m in event['review_snapshot']['movements']):
                raise HTTPException(409, 'Added item has activity before the selected opening cutoff; reconcile timing')
        projection['review_snapshot']['lines'].append({**line, 'quantity': '0', 'base_quantity': '0', 'evidence': supplied[pid].evidence})
        handoff.append({'product_id': pid, 'base_unit': line['base_unit'], 'base_quantity': '0', 'zero_at_opening_confirmed': True, 'evidence': supplied[pid].evidence})
    projection['review_snapshot']['scope'] = right['scope']
    report = periods.calculate(body.period, projection, closing, events)['report']
    report['scopeHandoff'] = {'physicalOpeningScope': left['scope'], 'periodScope': right['scope'], 'zeroAdditions': handoff, 'retainedQuantitiesUnchanged': True, 'createsStockSources': False}
    report['basis'] = 'Reviewed analytical snapshot; later source changes require reopening and replacement; coverage remains partial'
    history = sorted(history, key=lambda x: (x['journal'], x['id']))
    return serial({'report': report, 'reportHash': fingerprint(report).hex(), 'sourceHistory': history, 'sourceDigest': fingerprint({'report': report, 'history': history}).hex()})

async def freshness(conn, row):
    try:
        now = await facts(conn, row['store_id'], CloseIn(**row['review_snapshot']['submission']))
        current = now['sourceDigest'] == row['source_digest'].hex()
        return {'status': 'current' if current else 'stale', 'reason': None if current else 'Counts or interval activity changed'}
    except HTTPException as e: return {'status': 'stale', 'reason': str(e.detail)}

async def close_plan(conn, store, body):
    await ready(conn); chain = await active(conn, store)
    for row in chain:
        if (await freshness(conn, row))['status'] != 'current': raise HTTPException(409, 'Saved prep periods are stale; reopen affected and following periods before replacements')
    if chain:
        last = chain[-1]
        if str(body.period.opening_count_id) != str(last['closing_count_id']) or body.period.opening_cutoff != last['closing_cutoff']:
            raise HTTPException(409, 'Next period must begin at the prior closing count with its exact cutoff; no gap, overlap or boundary reinterpretation')
    data = await facts(conn, store, body)
    ordinal = await conn.fetchval('SELECT coalesce(max(ordinal),0)+1 FROM prep_inventory.period_closures WHERE store_id=$1', store)
    p = serial({'store_id': store, 'submission': body.model_dump(mode='json'), 'previous_id': chain[-1]['id'] if chain else None, 'ordinal': ordinal, **data})
    return {'review': p, 'reviewHash': fingerprint(p).hex()}

async def reopen_plan(conn, store, body):
    await ready(conn); chain = await active(conn, store)
    index = next((i for i, r in enumerate(chain) if str(r['id']) == str(body.from_closure_id)), None)
    if index is None: raise HTTPException(409, 'Choose an active saved period at this location')
    for row in chain[:index]:
        if (await freshness(conn, row))['status'] != 'current': raise HTTPException(409, 'An earlier period is stale; reopen from the earliest affected period')
    p = serial({'store_id': store, 'submission': body.model_dump(mode='json'), 'closure_ids': [r['id'] for r in chain[index:]],
        'snapshots': [{'id': r['id'], 'review_hash': r['review_hash'], 'freshness': await freshness(conn, r)} for r in chain[index:]], 'track1Writeback': False})
    return {'review': p, 'reviewHash': fingerprint(p).hex()}

async def persist(conn, store, plan, key, digest, actor, reopen=False):
    p = plan['review']; ident = uuid4()
    if reopen:
        row = await conn.fetchrow('''INSERT INTO prep_inventory.period_reopenings(id,store_id,closure_ids,reason,review_snapshot,review_hash,
            recorded_by,request_key,request_fingerprint) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *''', ident, store, [UUID(x) for x in p['closure_ids']], p['submission']['reason'], p, bytes.fromhex(plan['reviewHash']), actor, key, digest)
    else:
        b = p['submission']['period']
        row = await conn.fetchrow('''INSERT INTO prep_inventory.period_closures(id,store_id,ordinal,previous_id,opening_count_id,closing_count_id,
            opening_cutoff,closing_cutoff,reason,review_snapshot,review_hash,source_digest,recorded_by,request_key,request_fingerprint)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15) RETURNING *''', ident, store, p['ordinal'], UUID(p['previous_id']) if p['previous_id'] else None,
            UUID(b['opening_count_id']), UUID(b['closing_count_id']), b['opening_cutoff'], b['closing_cutoff'], p['submission']['reason'], p, bytes.fromhex(plan['reviewHash']), bytes.fromhex(p['sourceDigest']), actor, key, digest)
    return serial({'event': dict(row), 'replayed': False})

def install_routes(router, context):
    async def ctx(request, store):
        actor, pool = await context(request, store, True)
        if not observations.enabled(): raise HTTPException(503, 'Saved prep periods are awaiting enablement')
        return actor, pool
    @router.get('/{store_id}/prep-period-journal')
    async def history(store_id: str, request: Request):
        _, pool = await ctx(request, store_id)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read', readonly=True):
                await ready(conn); ids = {r['id'] for r in await active(conn, store_id)}
                rows = await conn.fetch('SELECT * FROM prep_inventory.period_closures WHERE store_id=$1 ORDER BY ordinal', store_id)
                result = []; affected = False
                for r in rows:
                    state = await freshness(conn, dict(r)) if r['id'] in ids else {'status': 'reopened', 'reason': 'Historical snapshot retained'}
                    if r['id'] in ids and state['status'] == 'stale': affected = True
                    result.append(dict(r) | {'freshness': state, 'chain_status': 'requires_reopening' if r['id'] in ids and affected else state['status']})
                changes = await conn.fetch('SELECT * FROM prep_inventory.period_reopenings WHERE store_id=$1 ORDER BY recorded_at,id', store_id)
                return serial({'store_id': store_id, 'closures': result, 'reopenings': [dict(r) for r in changes], 'track1Writeback': False})
    @router.post('/{store_id}/prep-period-journal/preview')
    async def preview(store_id: str, body: CloseIn, request: Request):
        _, pool = await ctx(request, store_id)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read', readonly=True): return await close_plan(conn, store_id, body)
    @router.post('/{store_id}/prep-period-journal/reopen-preview')
    async def reopening_preview(store_id: str, body: ReopenIn, request: Request):
        _, pool = await ctx(request, store_id)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read', readonly=True): return await reopen_plan(conn, store_id, body)
    async def save(request, store, body, key, reopen):
        actor, pool = await ctx(request, store)
        digest = fingerprint({'operation': 'reopen' if reopen else 'close', 'body': body.model_dump(mode='json')})
        async with pool.acquire() as conn:
            async with conn.transaction():
                await ready(conn)
                await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))', str(key))
                await lock_store(conn, store)
                previous = await mapping.replay(conn, 'period_reopenings' if reopen else 'period_closures', store, key, digest)
                if previous: return serial({'event': previous, 'replayed': True})
                other = 'period_closures' if reopen else 'period_reopenings'
                if await conn.fetchval(f'SELECT 1 FROM prep_inventory.{other} WHERE request_key=$1', key): raise HTTPException(409, 'Request key already belongs to another analytical journal action')
                plan = await (reopen_plan if reopen else close_plan)(conn, store, body.submission)
                if plan['reviewHash'] != body.expected_review_hash: raise HTTPException(409, 'Period sources or active chain changed; review a fresh preview')
                return await persist(conn, store, plan, key, digest, actor, reopen)
    @router.post('/{store_id}/prep-period-journal')
    async def close(store_id: str, body: SaveClose, request: Request, idempotency_key: UUID = Header(...)):
        return await save(request, store_id, body, idempotency_key, False)
    @router.post('/{store_id}/prep-period-journal/reopen')
    async def reopen(store_id: str, body: SaveReopen, request: Request, idempotency_key: UUID = Header(...)):
        return await save(request, store_id, body, idempotency_key, True)
