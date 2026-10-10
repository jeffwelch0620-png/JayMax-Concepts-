"""Measured preparation journal. Quantities explain Track 1; no accounting writes."""
import os
from datetime import date, datetime
from decimal import Decimal, localcontext
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Header, HTTPException, Request
from pydantic import AwareDatetime, Field, model_validator
import prep_mapping as mapping
import purchase_api
from purchase_api import serial
from purchase_parser import fingerprint
from native_units import lock_store


class InputIn(mapping.Strict):
    recipe_line_id: UUID
    quantity: Decimal = mapping.POSITIVE
    source_unit: str = Field(min_length=1, max_length=80)
    factor: Decimal = mapping.POSITIVE
    measurement_basis: Literal['measured', 'recipe_estimate']
    source_batch_id: UUID | None = None
    included_loss_quantity: Decimal | None = Field(default=None, ge=0, max_digits=28, decimal_places=12)
    evidence: str = Field(min_length=1, max_length=2000)
    loss_evidence: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode='after')
    def loss(self):
        if self.included_loss_quantity is not None and (self.included_loss_quantity > self.quantity or not self.loss_evidence):
            raise ValueError('Included loss must be within gross input and supported by an explanation')
        return self


class BatchIn(mapping.Strict):
    recipe_version_id: UUID
    planned_batches: Decimal = mapping.POSITIVE
    output_quantity: Decimal = mapping.POSITIVE
    performed_at: AwareDatetime
    business_date: date
    timezone_name: str = Field(min_length=1, max_length=80)
    calendar_date_confirmed: Literal[True]
    single_output_confirmed: Literal[True]
    inputs: list[InputIn] = Field(min_length=1, max_length=200)
    note: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def boundary(self):
        try:
            zone = ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Select a valid IANA timezone')
        if self.performed_at.astimezone(zone).date() != self.business_date:
            raise ValueError('Date must match the confirmed calendar day at this location')
        if len({i.recipe_line_id for i in self.inputs}) != len(self.inputs):
            raise ValueError('Record each recipe ingredient exactly once')
        return self


class ChangeIn(mapping.Strict):
    kind: Literal['replacement', 'void']
    replacement: BatchIn | None = None
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def replacement_required(self):
        if (self.kind == 'replacement') != (self.replacement is not None):
            raise ValueError('Replacement needs a full batch; void cannot include replacement quantities')
        return self


class RecordIn(mapping.Strict):
    batch: BatchIn
    expected_review_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    reviewed: Literal[True]


class CorrectionIn(mapping.Strict):
    change: ChangeIn
    expected_review_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    reviewed: Literal[True]


def enabled():
    return purchase_api.enabled() and mapping.enabled() and os.getenv('PREP_BATCHES_ENABLED', 'false').lower() == 'true'


def reject_legacy_write():
    if enabled():
        raise HTTPException(410, 'Legacy prep stock writes are held. Use reviewed native batch entry; sales, container and staff-task cutover is pending.')


async def ready(conn):
    await mapping.ready(conn)
    if not await conn.fetchval("SELECT to_regclass('prep_inventory.batch_movements') IS NOT NULL"):
        raise HTTPException(503, 'Prep batch journal is awaiting schema setup')


def exact_sum(values):
    with localcontext() as ctx:
        ctx.prec = 100
        return sum(values, Decimal(0))


async def available(conn, source_id):
    return await conn.fetchval('SELECT prep_inventory.lot_remaining($1)', source_id)


async def predecessor(conn, store, ident):
    old = await conn.fetchrow('SELECT * FROM prep_inventory.batch_events WHERE id=$1 AND store_id=$2', ident, store)
    if not old:
        raise HTTPException(404, 'Batch is not at this location')
    if old.get('source_kind', 'production') == 'opening':
        raise HTTPException(422, 'Opening stock uses its own reviewed whole-count void workflow; it is not a production batch')
    if old['kind'] == 'void' or await conn.fetchval('SELECT 1 FROM prep_inventory.batch_events WHERE predecessor_id=$1', ident):
        raise HTTPException(409, 'Batch was corrected or voided. Select its current record.')
    allocated = await conn.fetchval('SELECT prep_inventory.lot_used($1)', ident)
    if allocated:
        raise HTTPException(409, 'Prep or waste uses this output. Resolve its dependent records before correcting this batch.')
    return dict(old)


async def preview(conn, store, body=None, old_id=None, change=None):
    await ready(conn)
    old = await predecessor(conn, store, old_id) if old_id else None
    kind = change.kind if change else 'initial'
    body = change.replacement if change else body
    reversals = []
    released = {}
    if old:
        for row in await conn.fetch("SELECT * FROM prep_inventory.batch_movements WHERE event_id=$1 AND side='apply' ORDER BY ordinal", old_id):
            m = {k: row[k] for k in ('kind', 'recipe_version_id', 'recipe_line_id', 'raw_item_code', 'product_id', 'base_unit', 'source_batch_id')}
            m.update(side='reverse', quantity=row['quantity'].copy_negate(), reverses_movement_id=row['id'])
            reversals.append(m)
            if row['source_batch_id']:
                sid = row['source_batch_id']
                released[sid] = exact_sum([released.get(sid, Decimal(0)), row['quantity'].copy_negate()])
    if kind == 'void':
        plan = {k: old[k] for k in ('recipe_version_id', 'product_id', 'product_version_id', 'base_unit', 'performed_at', 'business_date', 'timezone_name')}
        plan.update(kind=kind, predecessor_id=old_id, root_id=old['root_id'], revision=old['revision']+1,
                    inputs=[], movements=reversals, reason=change.reason, batch=None, usableBaseOutput=None,
                    cost={'status': 'not_calculated', 'amount': None})
    else:
        from prep_openings import activity_time, source_valid
        await activity_time(conn, store, body.performed_at)
        recipe = await conn.fetchrow('SELECT * FROM prep_inventory.recipe_versions WHERE id=$1 AND store_id=$2', body.recipe_version_id, store)
        if not recipe:
            raise HTTPException(422, 'Approved recipe is not at this location')
        if await mapping.ancestry_changed(conn, store, await mapping.ancestry(conn, recipe['id']), await mapping.legacy_sources(conn, store)):
            raise HTTPException(409, 'Recipe or ingredient setup changed. Review current recipe versions first.')
        product = await mapping.current_product(conn, store, recipe['product_version_id'])
        profile = await mapping.current_profile(conn, store, recipe['output_profile_id'], recipe['product_version_id'])
        policy = await conn.fetchrow('SELECT * FROM prep_inventory.batch_policies WHERE store_id=$1', store)
        if policy and policy['timezone_name'] != body.timezone_name:
            raise HTTPException(409, 'Location calendar-day timezone is already confirmed; changing date policy requires a separate migration.')
        if old and (old['product_id'] != recipe['product_id'] or old['performed_at'] != body.performed_at or old['business_date'] != body.business_date or old['timezone_name'] != body.timezone_name):
            raise HTTPException(422, 'Correction must keep the same prepared identity and original date/time boundary')
        lines = await conn.fetch('SELECT * FROM prep_inventory.recipe_lines WHERE recipe_version_id=$1 ORDER BY line_number', recipe['id'])
        if {x.recipe_line_id for x in body.inputs} != {x['id'] for x in lines}:
            raise HTTPException(422, 'Record every approved ingredient exactly once')
        inputs, movements, allocations = [], list(reversals), {}
        for line in lines:
            value = next(x for x in body.inputs if x.recipe_line_id == line['id'])
            unit = value.source_unit.casefold()
            source, pid = None, None
            if line['source_kind'] == 'raw':
                if value.source_batch_id:
                    raise HTTPException(422, 'Purchased ingredients cannot use a prepared lot')
                mapping.conversion(unit, line['base_unit'], value.factor)
            else:
                if unit != line['source_unit'] or value.factor != line['factor']:
                    raise HTTPException(422, 'Prepared ingredient must use its reviewed unit conversion')
                pid = await conn.fetchval('SELECT product_id FROM prep_inventory.recipe_versions WHERE id=$1', line['prepared_recipe_id'])
                source = await conn.fetchrow('''SELECT * FROM prep_inventory.batch_events e WHERE e.id=$1 AND e.store_id=$2
                    AND e.product_id=$3 AND e.kind<>'void' AND NOT EXISTS(SELECT 1 FROM prep_inventory.batch_events WHERE predecessor_id=e.id)''', value.source_batch_id, store, pid)
                if not source or source['performed_at'] > body.performed_at or not await source_valid(conn, dict(source)):
                    raise HTTPException(422, 'Select an active recorded lot of this prepared item, produced before use')
            qty = mapping.times(value.quantity, value.factor)
            item = value.model_dump() | {'source_unit': unit, 'base_unit': line['base_unit'], 'base_quantity': qty,
                                        'standardBaseQuantity': mapping.times(line['base_quantity'], body.planned_batches),
                                        'includedLossBaseQuantity': mapping.times(value.included_loss_quantity, value.factor) if value.included_loss_quantity is not None else None,
                                        'definition': dict(line), 'sourceBatch': dict(source) if source else None}
            if source:
                sid = source['id']
                allocations[sid] = exact_sum([allocations.get(sid, Decimal(0)), qty])
                remaining = exact_sum([await available(conn, sid), released.get(sid, Decimal(0))])
                if allocations[sid] > remaining:
                    raise HTTPException(409, 'Recorded prepared lot has insufficient unallocated output. Refresh and review its quantities.')
                # This is the recorded allocation balance, never a physical count.
                item['availableAfterReversal'] = remaining
                # Avoid recursive JSON snapshots; immutable event ID retains full ancestry.
                item['sourceBatch'] = {k: source[k] for k in ('id', 'recipe_version_id', 'product_version_id', 'product_id', 'performed_at', 'review_hash')}
            inputs.append(item)
            movements.append({'side': 'apply', 'kind': line['source_kind']+'_input', 'recipe_version_id': recipe['id'],
                              'recipe_line_id': line['id'], 'raw_item_code': line['raw_item_code'], 'product_id': pid,
                              'base_unit': line['base_unit'], 'quantity': qty.copy_negate(), 'source_batch_id': value.source_batch_id, 'reverses_movement_id': None})
        output = mapping.times(body.output_quantity, profile['base_units_per_source_unit'])
        movements.append({'side': 'apply', 'kind': 'output', 'recipe_version_id': recipe['id'], 'recipe_line_id': None,
                          'raw_item_code': None, 'product_id': recipe['product_id'], 'base_unit': product['base_unit'],
                          'quantity': output, 'source_batch_id': None, 'reverses_movement_id': None})
        plan = {'kind': kind, 'predecessor_id': old_id, 'root_id': old['root_id'] if old else None,
                'revision': old['revision']+1 if old else 1, 'recipe_version_id': recipe['id'], 'product_id': recipe['product_id'],
                'product_version_id': recipe['product_version_id'], 'base_unit': product['base_unit'],
                'performed_at': body.performed_at, 'business_date': body.business_date, 'timezone_name': body.timezone_name,
                'reason': change.reason if change else body.note, 'batch': body.model_dump(mode='json'),
                'inputs': inputs, 'movements': movements, 'recipeReviewHash': recipe['review_hash'],
                'usableBaseOutput': output, 'standardBaseOutput': mapping.times(recipe['usable_base_yield'], body.planned_batches),
                'outputUnit': profile['source_unit'], 'cost': {'status': 'not_calculated', 'amount': None}}
    # PG numeric::text uses fixed notation. Keep reviewed movement strings in
    # that representation without touching immutable source/request snapshots.
    for m in plan['movements']: m['quantity'] = format(m['quantity'], 'f')
    plan = serial(plan)
    return {'review': plan, 'reviewHash': fingerprint(plan).hex()}


async def persist(conn, store, plan, key, digest, actor):
    p = plan['review']; ident = uuid4()
    await conn.execute('''INSERT INTO prep_inventory.batch_policies(store_id,timezone_name,day_basis,confirmed_by)
        VALUES($1,$2,'calendar_day',$3) ON CONFLICT(store_id) DO NOTHING''', store, p['timezone_name'], actor)
    saved = await conn.fetchrow('''INSERT INTO prep_inventory.batch_events(id,store_id,root_id,predecessor_id,revision,kind,
        recipe_version_id,product_id,product_version_id,base_unit,performed_at,business_date,timezone_name,reason,
        review_snapshot,review_hash,recorded_by,request_key,request_fingerprint)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19) RETURNING *''',
        ident, store, UUID(p['root_id']) if p['root_id'] else ident, UUID(p['predecessor_id']) if p['predecessor_id'] else None,
        p['revision'], p['kind'], UUID(p['recipe_version_id']), UUID(p['product_id']), UUID(p['product_version_id']), p['base_unit'],
        datetime.fromisoformat(p['performed_at']), date.fromisoformat(p['business_date']), p['timezone_name'],
        p['reason'], p, bytes.fromhex(plan['reviewHash']), actor, key, digest)
    for ordinal, m in enumerate(p['movements'], 1):
        def uid(k): return UUID(m[k]) if m[k] else None
        await conn.execute('''INSERT INTO prep_inventory.batch_movements(event_id,store_id,ordinal,side,kind,recipe_version_id,
            recipe_line_id,raw_item_code,product_id,base_unit,quantity,source_batch_id,reverses_movement_id)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)''', ident, store, ordinal, m['side'], m['kind'],
            uid('recipe_version_id'), uid('recipe_line_id'), m['raw_item_code'], uid('product_id'), m['base_unit'],
            Decimal(m['quantity']), uid('source_batch_id'), uid('reverses_movement_id'))
    return serial({'event': dict(saved), 'replayed': False})


async def setup(conn, store):
    await ready(conn)
    foundation = await mapping.setup(conn, store)
    recipes = []
    for r in foundation['recipes']:
        r['lines'] = serial([dict(x) for x in await conn.fetch('SELECT * FROM prep_inventory.recipe_lines WHERE recipe_version_id=$1 ORDER BY line_number', UUID(r['id']))])
        r['outputUnit'] = next(p['source_unit'] for p in foundation['profiles'] if p['id'] == r['output_profile_id']) if not r['reviewNeeded'] else None
        recipes.append(r)
    events = await conn.fetch('''SELECT * FROM prep_inventory.batch_events e WHERE store_id=$1
        AND NOT EXISTS(SELECT 1 FROM prep_inventory.batch_events WHERE predecessor_id=e.id) ORDER BY recorded_at DESC,id''', store)
    lots = []
    for e in events:
        if e['kind'] != 'void':
            from prep_openings import source_valid
            if not await source_valid(conn, dict(e)): continue
            lots.append({'id': e['id'], 'product_id': e['product_id'], 'recipe_version_id': e['recipe_version_id'],
                         'sourceKind': e.get('source_kind', 'production'), 'performed_at': e['performed_at'], 'base_unit': e['base_unit'], 'remainingRecordedQuantity': await available(conn, e['id'])})
    policy = await conn.fetchrow('SELECT * FROM prep_inventory.batch_policies WHERE store_id=$1', store)
    return serial({'recipes': recipes, 'lots': lots, 'events': [dict(e) for e in events if e.get('source_kind', 'production') == 'production'], 'policy': dict(policy) if policy else None,
                   'cost': {'status': 'not_calculated', 'amount': None}, 'quantityBasis': 'Recorded allocations; physical prep counts are separate observations'})


def install_routes(router, context):
    async def ctx(request, store, write=False):
        actor, pool = await context(request, store, write)
        if not enabled(): raise HTTPException(503, 'Native prep batch recording is awaiting enablement')
        return actor, pool

    @router.get('/{store_id}/prep-batches/setup')
    async def get_setup(store_id: str, request: Request):
        _, pool = await ctx(request, store_id)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read', readonly=True): return await setup(conn, store_id)

    @router.get('/{store_id}/prep-batches/{root_id}/history')
    async def history(store_id: str, root_id: UUID, request: Request):
        _, pool = await ctx(request, store_id)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read', readonly=True):
                await ready(conn)
                rows = await conn.fetch('SELECT * FROM prep_inventory.batch_events WHERE store_id=$1 AND root_id=$2 ORDER BY revision', store_id, root_id)
                if not rows: raise HTTPException(404, 'Batch history is not at this location')
                return serial({'events': [dict(r) for r in rows]})

    async def review(request, store, batch=None, old=None, change=None):
        _, pool = await ctx(request, store, True)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read', readonly=True): return await preview(conn, store, batch, old, change)

    @router.post('/{store_id}/prep-batches/preview')
    async def batch_preview(store_id: str, body: BatchIn, request: Request): return await review(request, store_id, body)

    @router.post('/{store_id}/prep-batches/{event_id}/change-preview')
    async def change_preview(store_id: str, event_id: UUID, body: ChangeIn, request: Request): return await review(request, store_id, old=event_id, change=body)

    async def record(request, store, body, key, old=None):
        actor, pool = await ctx(request, store, True)
        digest = fingerprint({'body': body.model_dump(mode='json'), 'predecessor': str(old) if old else None})
        async with pool.acquire() as conn:
            async with conn.transaction():
                await ready(conn)
                # Request keys are unique across stores; serialize cross-store
                # accidental key reuse before either request acquires its store.
                await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))', str(key))
                await lock_store(conn, store)
                previous = await mapping.replay(conn, 'batch_events', store, key, digest)
                if previous: return serial({'event': previous, 'replayed': True})
                await conn.execute('LOCK TABLE public.items,public.store_items,public.dishes,public.dish_lines,public.prep_items IN SHARE MODE')
                plan = await preview(conn, store, body.batch if not old else None, old, body.change if old else None)
                if plan['reviewHash'] != body.expected_review_hash: raise HTTPException(409, 'Batch sources changed. Review a fresh preview before recording.')
                return await persist(conn, store, plan, key, digest, actor)

    @router.post('/{store_id}/prep-batches')
    async def record_batch(store_id: str, body: RecordIn, request: Request, idempotency_key: UUID = Header(...)):
        return await record(request, store_id, body, idempotency_key)

    @router.post('/{store_id}/prep-batches/{event_id}/changes')
    async def record_change(store_id: str, event_id: UUID, body: CorrectionIn, request: Request, idempotency_key: UUID = Header(...)):
        return await record(request, store_id, body, idempotency_key, event_id)
