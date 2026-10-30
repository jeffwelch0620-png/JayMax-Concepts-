"""M3 Bulk supply (Jeff 2026-10-29): Bert's Bulk is made at Rudd's from Bert's own goods.
Bert's sends its Bulk count as a request (par minus on hand), Rudd's makes it in the Monday or
Thursday run and signs off the amounts and packaging, and Bert's manager accepts what arrived.
A shortfall stays open until a spot prep or the next run. migrations/20261030_bulk_supply.sql
enforces the same rules. No stock, purchase or accounting writes."""
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import Header, HTTPException, Request
from pydantic import Field, field_validator, model_validator
import prep_day_tasks as day_tasks
import prep_mapping as mapping
import prep_planning as planning
from native_units import lock_store
from purchase_api import serial
from purchase_parser import fingerprint

# Requesting store -> the store whose Bulk kitchen makes its Bulk.
MAKERS = {'berts': 'rudds'}
QUANTITY = Field(ge=0, max_digits=28, decimal_places=12)


async def installed(conn):
    return await conn.fetchval("SELECT to_regclass('prep_inventory.bulk_requests') IS NOT NULL")


async def ready(conn):
    await day_tasks.ready(conn)
    if not await installed(conn): raise HTTPException(503, 'Bulk supply migration is awaiting setup')


def maker_for(store):
    if store not in MAKERS: raise HTTPException(422, 'This location makes its own Bulk')
    return MAKERS[store]


class SpotLine(mapping.Strict):
    product_id: UUID
    quantity: Decimal = mapping.POSITIVE
    reason: str = Field(min_length=1, max_length=2000)


class RequestIn(mapping.Strict):
    run_date: date
    kind: Literal['scheduled', 'spot']
    day_group: Literal['weekday', 'weekend'] | None = None
    count_event_id: UUID | None = None
    lines: list[SpotLine] = Field(default_factory=list, max_length=500)
    note: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def by_kind(self):
        if self.kind == 'scheduled':
            if self.day_group is None or self.count_event_id is None or self.lines:
                raise ValueError('A scheduled request uses the par group and last night\'s count')
        else:
            if self.day_group is not None or self.count_event_id is not None or not self.lines:
                raise ValueError('A spot request lists the items and amounts needed')
            if len({l.product_id for l in self.lines}) != len(self.lines): raise ValueError('Request each item once')
            self.lines.sort(key=lambda l: str(l.product_id))
        return self


class RequestCommit(mapping.Strict):
    request: RequestIn
    expected_review_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    reviewed: Literal[True]


class StepLine(mapping.Strict):
    ordinal: int = Field(gt=0)
    base_quantity: Decimal = QUANTITY
    packaging: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator('base_quantity')
    @classmethod
    def finite(cls, value):
        if not value.is_finite(): raise ValueError('Use a finite decimal')
        return value


class StepIn(mapping.Strict):
    action: Literal['fulfill', 'accept', 'cancel']
    handoff: Literal['delivery', 'pickup'] | None = None
    lines: list[StepLine] = Field(default_factory=list, max_length=500)
    note: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def by_action(self):
        if (self.action == 'fulfill') != (self.handoff is not None): raise ValueError('Choose delivery or pickup when signing off what was sent')
        if self.action == 'cancel' and self.lines: raise ValueError('A cancellation has no amounts')
        if self.action != 'cancel' and not self.lines: raise ValueError('Sign off every requested item')
        if len({l.ordinal for l in self.lines}) != len(self.lines): raise ValueError('Sign off each item once')
        if self.action == 'accept' and any(l.packaging for l in self.lines): raise ValueError('Packaging is signed off by the maker')
        self.lines.sort(key=lambda l: l.ordinal)
        return self


async def maker_released(conn, maker, run_date):
    if not await conn.fetchval("SELECT to_regclass('prep_inventory.execution_events') IS NOT NULL"): return False
    current = await day_tasks.latest(conn, maker, run_date, 'bulk')
    if not current: return False
    phase = await conn.fetchval("SELECT action FROM prep_inventory.execution_events WHERE list_id=$1 AND action IN ('release','reopen') ORDER BY revision DESC LIMIT 1", UUID(current['list_id']))
    return phase == 'release'


async def maker_products(conn, maker):
    """The maker's prepared items with an active Bulk plan, by name."""
    rows = await conn.fetch('''SELECT p.id, p.identity_key, p.base_unit FROM prep_inventory.products p
        JOIN LATERAL (SELECT * FROM prep_inventory.planning_versions v WHERE v.product_id=p.id ORDER BY v.revision DESC LIMIT 1) v ON true
        WHERE p.store_id=$1 AND v.active AND v.track='bulk' ''', maker)
    return {r['identity_key']: dict(r) for r in rows}


async def preview(conn, store, body):
    await ready(conn)
    maker = maker_for(store)
    if body.kind == 'scheduled' and await maker_released(conn, maker, body.run_date):
        raise HTTPException(409, "The maker already released this Bulk run; send a spot request instead")
    setup = await planning.setup(conn, store)
    products = {p['product_id']: p for p in setup['products']}
    profiles = {p['id']: p for p in setup['unitProfiles']}
    keys = {r['id']: r['identity_key'] for r in await conn.fetch('SELECT id::text, identity_key FROM prep_inventory.products WHERE store_id=$1', store)}
    made = await maker_products(conn, maker)
    plans = {p['product_id']: p for p in setup['plans'] if p['active'] and p['track'] == 'bulk'}
    lines, missing_count, not_made = [], [], []
    count = None
    if body.kind == 'scheduled':
        available = await day_tasks.counts(conn, store, body.run_date)
        if not available or available[0]['id'] != body.count_event_id:
            raise HTTPException(409, 'Use the latest prep count from the night before the Bulk run')
        count = dict(available[0])
        counted = {str(l['product_id']): l['base_quantity'] for l in await conn.fetch('SELECT product_id, base_quantity FROM prep_inventory.count_observations WHERE event_id=$1', body.count_event_id)}
        for p in sorted(plans.values(), key=lambda p: products[p['product_id']]['name'].casefold()):
            if p['schedule'] != 'daily': continue
            name = products[p['product_id']]['name']
            profile = profiles.get(p['unit_profile_id'])
            if p['reviewNeeded'] or not profile: raise HTTPException(409, f'Review the Bulk plan for {name} before requesting it')
            maker_item = made.get(keys[p['product_id']])
            if not maker_item or maker_item['base_unit'] != products[p['product_id']]['base_unit']: not_made.append(name); continue
            if p['product_id'] not in counted: missing_count.append(name); continue
            factor = Decimal(str(profile['base_units_per_source_unit']))
            target = Decimal(p['weekend_par'] if body.day_group == 'weekend' else p['weekday_par'])
            on_hand = counted[p['product_id']]
            lines.append({'product_id': p['product_id'], 'maker_product_id': str(maker_item['id']), 'name': name,
                'base_unit': products[p['product_id']]['base_unit'], 'source_unit': profile['source_unit'],
                'planning_version_id': p['id'], 'factor': factor, 'target_par': target, 'counted_base_quantity': on_hand,
                'requested_base_quantity': max(mapping.times(target, factor) - on_hand, Decimal(0)), 'reason': None})
    else:
        for l in body.lines:
            p = plans.get(str(l.product_id))
            name = products.get(str(l.product_id), {}).get('name', str(l.product_id))
            profile = profiles.get(p['unit_profile_id']) if p else None
            if not p or not profile: raise HTTPException(422, f'{name} has no Bulk plan here to request against')
            maker_item = made.get(keys[str(l.product_id)])
            if not maker_item or maker_item['base_unit'] != products[str(l.product_id)]['base_unit']: not_made.append(name); continue
            factor = Decimal(str(profile['base_units_per_source_unit']))
            lines.append({'product_id': str(l.product_id), 'maker_product_id': str(maker_item['id']), 'name': name,
                'base_unit': products[str(l.product_id)]['base_unit'], 'source_unit': profile['source_unit'],
                'planning_version_id': None, 'factor': None, 'target_par': None, 'counted_base_quantity': None,
                'requested_base_quantity': mapping.times(l.quantity, factor), 'reason': l.reason})
    if not_made: raise HTTPException(409, f"The maker has no active Bulk plan for: {', '.join(not_made)}. Add one there (par can be 0) first.")
    if missing_count: raise HTTPException(409, f"Count these Bulk items before requesting; a missing count is not zero: {', '.join(missing_count)}")
    if not lines: raise HTTPException(409, 'No Bulk items to request')
    for n, line in enumerate(lines, 1): line['ordinal'] = n
    review = serial({'store_id': store, 'maker_store_id': maker, 'run_date': body.run_date, 'kind': body.kind,
        'inputs': body.model_dump(), 'count': count, 'lines': lines})
    return {'review': review, 'reviewHash': fingerprint(review).hex()}


async def lock_both(conn, store):
    for s in sorted({store, maker_for(store)}): await lock_store(conn, s)


async def send(pool, store, actor, body, key):
    digest = fingerprint(serial({'store': store, 'actor': actor, 'body': body.model_dump()}))
    async with pool.acquire() as conn, conn.transaction():
        await ready(conn); await lock_both(conn, store)
        prior = await conn.fetchrow('SELECT * FROM prep_inventory.bulk_requests WHERE request_key=$1', key)
        if prior:
            if prior['request_fingerprint'] != digest: raise HTTPException(409, 'Request key belongs to another Bulk request')
            return serial({'request_key': key, 'request': await one(conn, prior['id']), 'replayed': True})
        plan = await preview(conn, store, body.request)
        if plan['reviewHash'] != body.expected_review_hash: raise HTTPException(409, 'Pars, counts or the maker\'s plans changed. Review a fresh preview.')
        if body.request.kind == 'scheduled' and await conn.fetchval('''SELECT 1 FROM prep_inventory.bulk_requests r WHERE r.store_id=$1 AND r.run_date=$2 AND r.kind='scheduled'
            AND NOT EXISTS(SELECT 1 FROM prep_inventory.bulk_events e WHERE e.request_id=r.id AND e.action='cancel')''', store, body.request.run_date):
            raise HTTPException(409, 'This Bulk run already has a request from this store; cancel it before sending another')
        r = body.request
        ident = await conn.fetchval('''INSERT INTO prep_inventory.bulk_requests(store_id,maker_store_id,run_date,kind,day_group,count_event_id,note,actor,
            review_snapshot,request_key,request_fingerprint) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING id''',
            store, maker_for(store), r.run_date, r.kind, r.day_group, r.count_event_id, r.note, actor, plan['review'], key, digest)
        for l in plan['review']['lines']:
            dec = lambda k: Decimal(l[k]) if l[k] is not None else None
            await conn.execute('''INSERT INTO prep_inventory.bulk_request_lines(request_id,store_id,maker_store_id,ordinal,product_id,maker_product_id,base_unit,
                planning_version_id,factor,target_par,counted_base_quantity,requested_base_quantity,reason) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)''',
                ident, store, maker_for(store), l['ordinal'], UUID(l['product_id']), UUID(l['maker_product_id']), l['base_unit'],
                UUID(l['planning_version_id']) if l['planning_version_id'] else None, dec('factor'), dec('target_par'), dec('counted_base_quantity'),
                Decimal(l['requested_base_quantity']), l['reason'])
        return serial({'request_key': key, 'request': await one(conn, ident), 'replayed': False})


async def step(pool, store, request_id, actor, body, key):
    digest = fingerprint(serial({'store': store, 'request': request_id, 'actor': actor, 'body': body.model_dump()}))
    async with pool.acquire() as conn, conn.transaction():
        await ready(conn)
        parent = await conn.fetchrow('SELECT * FROM prep_inventory.bulk_requests WHERE id=$1 AND $2 IN (store_id, maker_store_id)', request_id, store)
        if not parent: raise HTTPException(404, 'Bulk request is not for this location')
        for s in sorted({parent['store_id'], parent['maker_store_id']}): await lock_store(conn, s)
        prior = await conn.fetchrow('SELECT * FROM prep_inventory.bulk_events WHERE request_key=$1', key)
        if prior:
            if prior['request_fingerprint'] != digest: raise HTTPException(409, 'Request key belongs to another Bulk sign-off')
            return serial({'request_key': key, 'request': await one(conn, request_id), 'replayed': True})
        done = {r['action'] for r in await conn.fetch('SELECT action FROM prep_inventory.bulk_events WHERE request_id=$1', request_id)}
        if 'cancel' in done: raise HTTPException(409, 'This Bulk request was cancelled')
        if body.action in done: raise HTTPException(409, 'This step was already signed off')
        if body.action == 'fulfill' and store != parent['maker_store_id']: raise HTTPException(403, 'Only the making store signs off what it sent')
        if body.action in ('accept', 'cancel') and store != parent['store_id']: raise HTTPException(403, 'Only the requesting store accepts or cancels its request')
        if body.action == 'accept' and 'fulfill' not in done: raise HTTPException(409, 'Nothing has been sent to accept yet')
        if body.action == 'cancel' and 'fulfill' in done: raise HTTPException(409, 'A request that was already sent cannot be cancelled')
        ordinals = [r['ordinal'] for r in await conn.fetch('SELECT ordinal FROM prep_inventory.bulk_request_lines WHERE request_id=$1 ORDER BY ordinal', request_id)]
        if body.action != 'cancel' and [l.ordinal for l in body.lines] != ordinals:
            raise HTTPException(422, 'Sign off every requested item, entering zero for any not sent or not received')
        if body.action == 'fulfill' and any(l.base_quantity > 0 and not l.packaging for l in body.lines):
            raise HTTPException(422, 'Sign off the packaging of each item sent')
        if body.action == 'accept':
            sent = {r['ordinal']: r['base_quantity'] for r in await conn.fetch('''SELECT l.ordinal, l.base_quantity FROM prep_inventory.bulk_event_lines l
                JOIN prep_inventory.bulk_events e ON e.id=l.event_id WHERE e.request_id=$1 AND e.action='fulfill' ''', request_id)}
            if any(l.base_quantity > sent.get(l.ordinal, 0) for l in body.lines): raise HTTPException(422, 'Accepted more than was sent')
        event = await conn.fetchval('''INSERT INTO prep_inventory.bulk_events(request_id,action,store_id,handoff,note,actor,request_key,request_fingerprint)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id''', request_id, body.action, store, body.handoff, body.note, actor, key, digest)
        for l in body.lines:
            await conn.execute('INSERT INTO prep_inventory.bulk_event_lines(event_id,request_id,ordinal,base_quantity,packaging) VALUES($1,$2,$3,$4,$5)',
                event, request_id, l.ordinal, l.base_quantity, l.packaging)
        return serial({'request_key': key, 'request': await one(conn, request_id), 'replayed': False})


async def one(conn, request_id):
    r = dict(await conn.fetchrow('SELECT * FROM prep_inventory.bulk_requests WHERE id=$1', request_id))
    lines = [dict(l) for l in await conn.fetch('SELECT * FROM prep_inventory.bulk_request_lines WHERE request_id=$1 ORDER BY ordinal', request_id)]
    events = [dict(e) for e in await conn.fetch('SELECT id,action,store_id,handoff,note,actor,created_at FROM prep_inventory.bulk_events WHERE request_id=$1 ORDER BY created_at,id', request_id)]
    amounts = {}
    for row in await conn.fetch('''SELECT e.action, l.ordinal, l.base_quantity, l.packaging FROM prep_inventory.bulk_event_lines l
        JOIN prep_inventory.bulk_events e ON e.id=l.event_id WHERE e.request_id=$1''', request_id):
        amounts[(row['action'], row['ordinal'])] = row
    reviewed = {l['ordinal']: l for l in r['review_snapshot']['lines']}
    for l in lines:
        sent, got = amounts.get(('fulfill', l['ordinal'])), amounts.get(('accept', l['ordinal']))
        l['name'] = reviewed[l['ordinal']]['name']; l['source_unit'] = reviewed[l['ordinal']]['source_unit']
        l['sent_base_quantity'] = sent['base_quantity'] if sent else None
        l['packaging'] = sent['packaging'] if sent else None
        l['accepted_base_quantity'] = got['base_quantity'] if got else None
        l['shortfall_base_quantity'] = max(l['requested_base_quantity'] - got['base_quantity'], Decimal(0)) if got else None
    actions = [e['action'] for e in events]
    r['status'] = ('cancelled' if 'cancel' in actions else 'accepted' if 'accept' in actions else 'sent' if 'fulfill' in actions else 'requested')
    r['lines'] = lines; r['events'] = events
    del r['request_fingerprint']; del r['created_xid']
    return serial(r)


def open_shortfalls(requests):
    """Accepted short and not yet made up: no later accepted request for the same item."""
    accepted = sorted((r for r in requests if r['status'] == 'accepted'), key=lambda r: (r['run_date'], r['created_at']))
    out = []
    for i, r in enumerate(accepted):
        for l in r['lines']:
            if Decimal(l['shortfall_base_quantity'] or 0) <= 0: continue
            later = any(l['product_id'] in {x['product_id'] for x in s['lines'] if Decimal(x['accepted_base_quantity'] or 0) > 0} for s in accepted[i + 1:])
            if not later: out.append({'request_id': r['id'], 'run_date': r['run_date'], 'store_id': r['store_id'], 'product_id': l['product_id'],
                'name': l['name'], 'base_unit': l['base_unit'], 'shortfall_base_quantity': l['shortfall_base_quantity']})
    return out


async def read(conn, store, since):
    await ready(conn)
    ids = [r['id'] for r in await conn.fetch('''SELECT id FROM prep_inventory.bulk_requests WHERE $1 IN (store_id, maker_store_id) AND run_date>=$2
        ORDER BY run_date DESC, created_at DESC LIMIT 200''', store, since)]
    requests = [await one(conn, i) for i in ids]
    return serial({'store_id': store, 'maker_store_id': MAKERS.get(store), 'makes_for': sorted(s for s, m in MAKERS.items() if m == store),
        'requests': requests, 'open_shortfalls': open_shortfalls(requests)})


async def requested_for_run(conn, maker, run_date):
    """Other stores' live scheduled requests for the maker's Bulk run: {maker product id: base amount}."""
    if not await installed(conn): return None
    rows = await conn.fetch('''SELECT l.maker_product_id::text AS product_id, sum(l.requested_base_quantity) AS amount FROM prep_inventory.bulk_request_lines l
        JOIN prep_inventory.bulk_requests r ON r.id=l.request_id WHERE r.maker_store_id=$1 AND r.run_date=$2 AND r.kind='scheduled'
        AND NOT EXISTS(SELECT 1 FROM prep_inventory.bulk_events e WHERE e.request_id=r.id AND e.action='cancel') GROUP BY l.maker_product_id''', maker, run_date)
    return {r['product_id']: r['amount'] for r in rows}


def install_routes(router, context):
    @router.get('/{store_id}/bulk-supply')
    async def read_supply(store_id: str, request: Request, since: date):
        _, pool = await context(request, store_id)
        async with pool.acquire() as conn, conn.transaction(isolation='repeatable_read', readonly=True): return await read(conn, store_id, since)

    @router.post('/{store_id}/bulk-requests/preview')
    async def preview_request(store_id: str, body: RequestIn, request: Request):
        _, pool = await context(request, store_id, True)
        async with pool.acquire() as conn, conn.transaction(isolation='repeatable_read', readonly=True): return await preview(conn, store_id, body)

    @router.post('/{store_id}/bulk-requests')
    async def send_request(store_id: str, body: RequestCommit, request: Request, idempotency_key: UUID = Header(...)):
        actor, pool = await context(request, store_id, True)
        return await send(pool, store_id, actor, body, idempotency_key)

    @router.post('/{store_id}/bulk-requests/{request_id}/steps')
    async def sign_step(store_id: str, request_id: UUID, body: StepIn, request: Request, idempotency_key: UUID = Header(...)):
        actor, pool = await context(request, store_id, True)
        return await step(pool, store_id, request_id, actor, body, idempotency_key)
