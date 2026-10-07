"""Standalone measured waste and full physical prep counts; Track 1 independent."""
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Header, HTTPException, Request
from pydantic import AwareDatetime, Field, model_validator
import prep_batches as batches
import prep_mapping as mapping
from native_units import lock_store
from purchase_api import serial
from purchase_parser import fingerprint

PURPOSE = Literal['waste', 'count']


class Stamp(mapping.Strict):
    performed_at: AwareDatetime
    business_date: date
    timezone_name: str = Field(min_length=1, max_length=80)
    calendar_date_confirmed: Literal[True]
    note: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def boundary(self):
        try: zone = ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, ValueError): raise ValueError('Select a valid IANA timezone')
        if self.performed_at.astimezone(zone).date() != self.business_date:
            raise ValueError('Date must match the confirmed calendar day at this location')
        return self


class WasteIn(Stamp):
    source_kind: Literal['raw', 'prepared']
    raw_item_code: str | None = None
    product_version_id: UUID | None = None
    profile_id: UUID | None = None
    source_batch_id: UUID | None = None
    quantity: Decimal = mapping.POSITIVE
    source_unit: str = Field(min_length=1, max_length=80)
    factor: Decimal = mapping.POSITIVE
    measurement_basis: Literal['measured']
    already_included_in_batch: Literal[False]
    category: Literal['storage_spoilage', 'service_discard', 'other']

    @model_validator(mode='after')
    def source(self):
        raw = bool(self.raw_item_code) and self.product_version_id is None and self.profile_id is None and self.source_batch_id is None
        prepared = self.raw_item_code is None and self.product_version_id is not None and self.profile_id is not None and self.source_batch_id is not None
        if not ((self.source_kind == 'raw' and raw) or (self.source_kind == 'prepared' and prepared)):
            raise ValueError('Select exactly one purchased item or prepared source batch')
        return self


class CountLine(mapping.Strict):
    product_version_id: UUID
    profile_id: UUID
    quantity: Decimal = Field(ge=0, max_digits=28, decimal_places=12)
    evidence: str = Field(min_length=1, max_length=2000)


class CountIn(Stamp):
    complete_scope_confirmed: Literal[True]
    lines: list[CountLine] = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def unique(self):
        if len({l.product_version_id for l in self.lines}) != len(self.lines):
            raise ValueError('Count each prepared identity once')
        return self


class ChangeIn(mapping.Strict):
    kind: Literal['replacement', 'void']
    replacement: WasteIn | CountIn | None = None
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def required(self):
        if (self.kind == 'replacement') != (self.replacement is not None):
            raise ValueError('Replacement requires a complete observation; void cannot include new quantities')
        return self


class RecordIn(mapping.Strict):
    body: WasteIn | CountIn
    expected_review_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    reviewed: Literal[True]


class CorrectionIn(mapping.Strict):
    change: ChangeIn
    expected_review_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    reviewed: Literal[True]


def enabled(): return batches.enabled() and os.getenv('PREP_OBSERVATIONS_ENABLED', 'false').lower() == 'true'


async def ready(conn):
    await batches.ready(conn)
    if not await conn.fetchval("SELECT to_regclass('prep_inventory.count_observations') IS NOT NULL"):
        raise HTTPException(503, 'Prep waste/count observations are awaiting schema setup')


async def predecessor(conn, store, purpose, ident):
    row = await conn.fetchrow('SELECT * FROM prep_inventory.observations WHERE id=$1 AND store_id=$2 AND purpose=$3', ident, store, purpose)
    if not row: raise HTTPException(404, 'Observation is not at this location or in this journal')
    if row['kind'] == 'void' or await conn.fetchval('SELECT 1 FROM prep_inventory.observations WHERE predecessor_id=$1', ident):
        raise HTTPException(409, 'Observation was corrected or voided. Select its current record.')
    return dict(row)


async def preview(conn, store, purpose, body=None, old_id=None, change=None, container_fill_id=None):
    await ready(conn)
    old = await predecessor(conn, store, purpose, old_id) if old_id else None
    linked = await conn.fetchval("SELECT to_regclass('prep_inventory.container_waste_links') IS NOT NULL")
    if old and linked and await conn.fetchval('SELECT 1 FROM prep_inventory.container_waste_links WHERE observation_id=$1',old_id):
        if not container_fill_id: raise HTTPException(409, 'Container waste requires its paired container reversal; use the container history')
    kind = change.kind if change else 'initial'
    if old and purpose == 'count' and await conn.fetchval("SELECT to_regclass('prep_inventory.opening_decisions') IS NOT NULL"):
        if await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM prep_inventory.batch_events b JOIN prep_inventory.opening_decisions d ON d.id=b.opening_decision_id
            WHERE d.count_id=$1 AND prep_inventory.lot_used(b.id)>0)''', old_id):
            raise HTTPException(409, 'Opening count has dependent prep or waste. Resolve that use before correcting the count.')
    body = change.replacement if change else body
    movements, released = [], {}
    if old and purpose == 'waste':
        for m in await conn.fetch("SELECT * FROM prep_inventory.waste_movements WHERE event_id=$1 AND side='apply' ORDER BY ordinal", old_id):
            value = {k: m[k] for k in ('raw_item_code', 'product_id', 'base_unit', 'source_batch_id')}
            value.update(side='reverse', quantity=m['quantity'].copy_negate(), reverses_movement_id=m['id'])
            movements.append(value)
            if m['source_batch_id']: released[m['source_batch_id']] = m['quantity'].copy_negate()
    if kind == 'void':
        p = {k: old[k] for k in ('performed_at', 'business_date', 'timezone_name', 'raw_item_code', 'product_id', 'base_unit', 'source_batch_id')}
        p.update(body=None, movements=movements, lines=[], scope=old['review_snapshot'].get('scope', []))
    else:
        expected = WasteIn if purpose == 'waste' else CountIn
        if not isinstance(body, expected): raise HTTPException(422, 'Use the matching waste or physical-count form')
        policy = await conn.fetchrow('SELECT * FROM prep_inventory.batch_policies WHERE store_id=$1', store)
        if policy and policy['timezone_name'] != body.timezone_name:
            raise HTTPException(409, 'Location calendar-day timezone is already confirmed; review date-policy changes separately')
        if old and (old['performed_at'] != body.performed_at or old['business_date'] != body.business_date or old['timezone_name'] != body.timezone_name):
            raise HTTPException(422, 'Correction must retain the original observation time and date boundary')
        p = {'performed_at': body.performed_at, 'business_date': body.business_date, 'timezone_name': body.timezone_name,
             'body': body.model_dump(mode='json'), 'movements': movements, 'lines': [], 'scope': [],
             'raw_item_code': None, 'product_id': None, 'base_unit': None, 'source_batch_id': None}
        if purpose == 'waste':
            from prep_openings import activity_time, source_valid
            await activity_time(conn, store, body.performed_at)
            unit = body.source_unit.casefold()
            if body.source_kind == 'raw':
                source = await conn.fetchrow('''SELECT i.code,i.name,i.item_type,i.base_unit AS catalog_unit,i.pack_count,i.unit_qty,i.unit_uom,ib.base_unit
                    FROM public.items i JOIN public.store_items s ON s.item_code=i.code AND s.store_id=$1
                    JOIN purchasing.item_bases ib ON ib.store_id=s.store_id AND ib.item_code=i.code WHERE i.code=$2 AND i.item_type='raw' ''', store, body.raw_item_code)
                if not source: raise HTTPException(422, 'Purchased item needs a verified native base unit at this location')
                mapping.conversion(unit, source['base_unit'], body.factor)
                p.update(raw_item_code=body.raw_item_code, base_unit=source['base_unit'], source={'raw': dict(source)})
            else:
                if container_fill_id:
                    frozen = await conn.fetchrow('''SELECT p.product_version_id,p.unit_profile_id,f.source_batch_id,f.product_id,f.factor
                        FROM prep_inventory.container_fills f JOIN prep_inventory.container_profiles p ON p.id=f.profile_id
                        WHERE f.id=$1 AND f.store_id=$2''',container_fill_id,store)
                    if not frozen or (body.product_version_id,body.profile_id,body.source_batch_id,body.factor) != (frozen['product_version_id'],frozen['unit_profile_id'],frozen['source_batch_id'],frozen['factor']):
                        raise HTTPException(422, 'Container waste retains the original measured food conversion and lot')
                    product = dict(await conn.fetchrow('SELECT * FROM prep_inventory.product_versions WHERE id=$1',body.product_version_id))
                    profile = dict(await conn.fetchrow('SELECT * FROM prep_inventory.unit_profiles WHERE id=$1',body.profile_id))
                else:
                    product = await mapping.current_product(conn, store, body.product_version_id)
                    profile = await mapping.current_profile(conn, store, body.profile_id, body.product_version_id)
                if unit != profile['source_unit'] or body.factor != profile['base_units_per_source_unit']:
                    raise HTTPException(422, 'Prepared waste requires the exact verified unit conversion')
                lot = await conn.fetchrow('''SELECT * FROM prep_inventory.batch_events e WHERE e.id=$1 AND e.store_id=$2 AND e.product_id=$3
                    AND e.kind<>'void' AND NOT EXISTS(SELECT 1 FROM prep_inventory.batch_events WHERE predecessor_id=e.id)''', body.source_batch_id, store, product['product_id'])
                if not lot or lot['performed_at'] > body.performed_at or not await source_valid(conn, dict(lot)):
                    raise HTTPException(422, 'Choose a current recorded lot produced before this waste')
                p.update(product_id=product['product_id'], base_unit=product['base_unit'], source_batch_id=lot['id'],
                         source={'product': product, 'profile': profile, 'batch': {k: lot[k] for k in ('id', 'product_id', 'product_version_id', 'recipe_version_id', 'performed_at', 'review_hash')}})
                p['availableAfterReversal'] = batches.exact_sum([await batches.available(conn, lot['id'], body.performed_at), released.get(lot['id'], Decimal(0)), mapping.times(body.quantity,body.factor) if container_fill_id else Decimal(0)])
            p['factor'] = body.factor; p['baseQuantity'] = mapping.times(body.quantity, body.factor)
            if body.source_kind == 'prepared' and p['baseQuantity'] > p['availableAfterReversal']:
                raise HTTPException(409, 'Recorded source output is insufficient for this waste; refresh and review')
            if old and (old['raw_item_code'], old['product_id'], old['base_unit']) != (p['raw_item_code'], p['product_id'], p['base_unit']):
                raise HTTPException(422, 'Waste correction must retain the same item identity and canonical unit')
            p['movements'].append({k: p[k] for k in ('raw_item_code', 'product_id', 'base_unit', 'source_batch_id')} |
                                  {'side': 'apply', 'quantity': p['baseQuantity'].copy_negate(), 'reverses_movement_id': None})
        else:
            products = await conn.fetch('SELECT * FROM prep_inventory.products WHERE store_id=$1 ORDER BY id::text', store)
            p['scope'] = old['review_snapshot']['scope'] if old else [str(x['id']) for x in products]
            resolved = []
            for l in body.lines:
                product = await mapping.current_product(conn, store, l.product_version_id)
                profile = await mapping.current_profile(conn, store, l.profile_id, l.product_version_id)
                resolved.append({'product': product, 'profile': profile, 'quantity': l.quantity, 'evidence': l.evidence})
            if len(resolved) != len(p['scope']) or sorted(str(x['product']['product_id']) for x in resolved) != p['scope']:
                raise HTTPException(422, 'Full prep count requires every item in its declared scope once, with an explicit quantity including zero')
            for n, x in enumerate(sorted(resolved, key=lambda x: str(x['product']['product_id'])), 1):
                v, u = x['product'], x['profile']
                p['lines'].append({'line_number': n, 'product_id': v['product_id'], 'product_version_id': v['id'], 'profile_id': u['id'],
                    'base_unit': v['base_unit'], 'quantity': x['quantity'], 'factor': u['base_units_per_source_unit'],
                    'base_quantity': mapping.times(x['quantity'], u['base_units_per_source_unit']), 'evidence': x['evidence']})
            p['definitions'] = resolved
            if not old and await conn.fetchval("SELECT 1 FROM prep_inventory.observations WHERE store_id=$1 AND purpose='count' AND kind='initial' AND performed_at=$2", store, body.performed_at):
                raise HTTPException(409, 'A physical prep count already exists at this time; correct its existing record')
    p.update(purpose=purpose, kind=kind, predecessor_id=old_id, root_id=old['root_id'] if old else None,
             revision=old['revision']+1 if old else 1, reason=change.reason if change else body.note,
             cost={'status': 'not_calculated', 'amount': None})
    if container_fill_id: p['container_fill_id'] = str(container_fill_id)
    for m in p['movements']: m['quantity'] = format(m['quantity'], 'f')
    for l in p['lines']:
        for k in ('quantity', 'factor', 'base_quantity'): l[k] = format(l[k], 'f')
    p = serial(p)
    return {'review': p, 'reviewHash': fingerprint(p).hex()}


async def persist(conn, store, plan, key, digest, actor):
    p = plan['review']; ident = uuid4()
    def uid(value): return UUID(value) if value else None
    await conn.execute("INSERT INTO prep_inventory.batch_policies(store_id,timezone_name,day_basis,confirmed_by) VALUES($1,$2,'calendar_day',$3) ON CONFLICT DO NOTHING", store, p['timezone_name'], actor)
    saved = await conn.fetchrow('''INSERT INTO prep_inventory.observations(id,store_id,purpose,root_id,predecessor_id,revision,kind,performed_at,
        business_date,timezone_name,raw_item_code,product_id,base_unit,source_batch_id,reason,review_snapshot,review_hash,recorded_by,request_key,request_fingerprint)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20) RETURNING *''',
        ident, store, p['purpose'], uid(p['root_id']) or ident, uid(p['predecessor_id']), p['revision'], p['kind'], datetime.fromisoformat(p['performed_at']),
        date.fromisoformat(p['business_date']), p['timezone_name'], p['raw_item_code'], uid(p['product_id']), p['base_unit'], uid(p['source_batch_id']),
        p['reason'], p, bytes.fromhex(plan['reviewHash']), actor, key, digest)
    for n, m in enumerate(p['movements'], 1):
        await conn.execute('''INSERT INTO prep_inventory.waste_movements(event_id,store_id,ordinal,side,raw_item_code,product_id,base_unit,source_batch_id,quantity,reverses_movement_id)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)''', ident, store, n, m['side'], m['raw_item_code'], uid(m['product_id']), m['base_unit'], uid(m['source_batch_id']), Decimal(m['quantity']), uid(m['reverses_movement_id']))
    for l in p['lines']:
        await conn.execute('''INSERT INTO prep_inventory.count_observations(event_id,store_id,line_number,product_id,product_version_id,profile_id,base_unit,quantity,factor,base_quantity,evidence)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)''', ident, store, l['line_number'], uid(l['product_id']), uid(l['product_version_id']), uid(l['profile_id']),
            l['base_unit'], Decimal(l['quantity']), Decimal(l['factor']), Decimal(l['base_quantity']), l['evidence'])
    return serial({'event': dict(saved), 'replayed': False})


async def setup(conn, store):
    await ready(conn)
    foundation = await mapping.setup(conn, store)
    batch = await batches.setup(conn, store)
    events = await conn.fetch('''SELECT * FROM prep_inventory.observations e WHERE store_id=$1
        AND NOT EXISTS(SELECT 1 FROM prep_inventory.observations WHERE predecessor_id=e.id) ORDER BY recorded_at DESC,id''', store)
    return serial({'products': foundation['products'], 'profiles': foundation['profiles'], 'rawItems': foundation['rawItems'],
                   'lots': batch['lots'], 'policy': batch['policy'], 'events': [dict(x) for x in events],
                   'scope': 'Full prepared inventory; purchased items excluded', 'countBehavior': 'Observation only; no balance reset',
                   'cost': {'status': 'not_calculated', 'amount': None}})


def install_routes(router, context):
    async def ctx(request, store, write=False):
        actor, pool = await context(request, store, write)
        if not enabled(): raise HTTPException(503, 'Prep waste and physical counts are awaiting enablement')
        return actor, pool

    @router.get('/{store_id}/prep-observations/setup')
    async def get_setup(store_id: str, request: Request):
        _, pool = await ctx(request, store_id)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read', readonly=True): return await setup(conn, store_id)

    @router.get('/{store_id}/prep-observations/{purpose}/{root_id}/history')
    async def history(store_id: str, purpose: PURPOSE, root_id: UUID, request: Request):
        _, pool = await ctx(request, store_id)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read', readonly=True):
                await ready(conn)
                rows = await conn.fetch('SELECT * FROM prep_inventory.observations WHERE store_id=$1 AND purpose=$2 AND root_id=$3 ORDER BY revision', store_id, purpose, root_id)
                if not rows: raise HTTPException(404, 'Observation history is not at this location or in this journal')
                return serial({'events': [dict(x) for x in rows]})

    @router.post('/{store_id}/prep-observations/{purpose}/preview')
    async def initial_preview(store_id: str, purpose: PURPOSE, body: WasteIn | CountIn, request: Request):
        _, pool = await ctx(request, store_id, True)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read', readonly=True): return await preview(conn, store_id, purpose, body)

    @router.post('/{store_id}/prep-observations/{purpose}/{event_id}/change-preview')
    async def change_preview(store_id: str, purpose: PURPOSE, event_id: UUID, body: ChangeIn, request: Request):
        _, pool = await ctx(request, store_id, True)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read', readonly=True): return await preview(conn, store_id, purpose, old_id=event_id, change=body)

    async def record(request, store, purpose, body, key, old=None):
        actor, pool = await ctx(request, store, True)
        digest = fingerprint({'body': body.model_dump(mode='json'), 'purpose': purpose, 'predecessor': str(old) if old else None})
        async with pool.acquire() as conn:
            async with conn.transaction():
                await ready(conn)
                await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))', str(key))
                await lock_store(conn, store)
                previous = await mapping.replay(conn, 'observations', store, key, digest)
                if previous: return serial({'event': previous, 'replayed': True})
                await conn.execute('LOCK TABLE public.items,public.store_items,public.dishes,public.dish_lines,public.prep_items IN SHARE MODE')
                plan = await preview(conn, store, purpose, body.body if not old else None, old, body.change if old else None)
                if plan['reviewHash'] != body.expected_review_hash: raise HTTPException(409, 'Observation source/scope changed. Review a fresh preview.')
                return await persist(conn, store, plan, key, digest, actor)

    @router.post('/{store_id}/prep-observations/{purpose}')
    async def initial_record(store_id: str, purpose: PURPOSE, body: RecordIn, request: Request, idempotency_key: UUID = Header(...)):
        return await record(request, store_id, purpose, body, idempotency_key)

    @router.post('/{store_id}/prep-observations/{purpose}/{event_id}/changes')
    async def changed_record(store_id: str, purpose: PURPOSE, event_id: UUID, body: CorrectionIn, request: Request, idempotency_key: UUID = Header(...)):
        return await record(request, store_id, purpose, body, idempotency_key, event_id)
