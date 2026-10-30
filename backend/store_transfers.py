"""M3 store transfers of purchased items (Jeff 2026-10-29). Inventory belongs to the store that
bought it; a transfer moves an item out of one store and into the other once, at the sender's
latest purchase cost, on the date the receiving manager confirms what arrived. No purchase or
sale is created and no stock is written: each store's food-cost period shows it as a transfer
in or out. Anything lost on the way stays in the sender's usage.
migrations/20261031_store_transfers.sql enforces the same rules."""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Literal
from uuid import UUID

from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from purchase_api import serial
from purchase_parser import fingerprint

QUANTITY = dict(max_digits=28, decimal_places=12)


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class SendIn(Strict):
    to_store_id: str = Field(min_length=1, max_length=40)
    item_code: str = Field(min_length=1, max_length=150)
    sent_base_quantity: Decimal = Field(gt=0, **QUANTITY)
    kind: Literal['lend', 'batch_ingredient']
    sent_date: date
    note: str = Field(min_length=1, max_length=2000)

    @field_validator('sent_base_quantity')
    @classmethod
    def finite(cls, value):
        if not value.is_finite(): raise ValueError('Use a finite decimal')
        return value


class SendCommit(Strict):
    transfer: SendIn
    expected_review_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    reviewed: Literal[True]


class StepIn(Strict):
    action: Literal['receive', 'cancel']
    received_base_quantity: Decimal | None = Field(default=None, ge=0, **QUANTITY)
    record_date: date | None = None
    note: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def by_action(self):
        if (self.action == 'receive') != (self.received_base_quantity is not None and self.record_date is not None):
            raise ValueError('Confirm the amount that arrived and the date it arrived')
        if self.received_base_quantity is not None and not self.received_base_quantity.is_finite(): raise ValueError('Use a finite decimal')
        return self


async def installed(conn):
    return await conn.fetchval("SELECT to_regclass('actual_inventory.store_transfers') IS NOT NULL")


async def ready(conn):
    if not await installed(conn): raise HTTPException(503, 'Store transfer migration is awaiting setup')


async def lock_stores(conn, *stores):
    for s in sorted(set(stores)):
        await conn.execute('INSERT INTO public.store_state(store_id) VALUES($1) ON CONFLICT(store_id) DO NOTHING', s)
        await conn.fetchval('SELECT revision FROM public.store_state WHERE store_id=$1 FOR UPDATE', s)


def cents(base_quantity, cost_amount, cost_base_quantity):
    with localcontext() as ctx:
        ctx.prec = 80
        return (base_quantity * cost_amount / cost_base_quantity).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


async def latest_cost(conn, store, item, base_unit, day):
    return await conn.fetchrow('''SELECT mapping_id, base_quantity, inventory_cost_amount, inventory_record_date FROM purchasing.current_purchase_facts
        WHERE store_id=$1 AND item_code=$2 AND base_unit=$3 AND base_quantity>0 AND inventory_record_date<=$4
        ORDER BY inventory_record_date DESC, goods_received_at DESC NULLS LAST, mapping_id DESC LIMIT 1''', store, item, base_unit, day)


async def preview(conn, store, body):
    await ready(conn)
    if body.to_store_id == store: raise HTTPException(422, 'Choose the other store')
    if not await conn.fetchval('SELECT 1 FROM public.stores WHERE id=$1', body.to_store_id): raise HTTPException(422, 'Unknown receiving store')
    # Each store's counting unit for the item is its own setting (purchasing.item_bases), never the recipe unit.
    rows = await conn.fetch('''SELECT si.store_id, i.name, ib.base_unit FROM public.items i
        JOIN public.store_items si ON si.item_code=i.code LEFT JOIN purchasing.item_bases ib ON ib.item_code=i.code AND ib.store_id=si.store_id
        WHERE i.code=$1 AND si.store_id IN ($2,$3)''', body.item_code, store, body.to_store_id)
    if len(rows) != 2: raise HTTPException(409, 'Both stores must carry this item')
    unset = sorted(r['store_id'] for r in rows if r['base_unit'] is None)
    if unset: raise HTTPException(409, f"Set up the counting unit for this item first at: {', '.join(unset)}")
    if len({r['base_unit'] for r in rows}) != 1: raise HTTPException(409, 'Both stores must count this item in the same base unit')
    base_unit = rows[0]['base_unit']
    cost = await latest_cost(conn, store, body.item_code, base_unit, body.sent_date)
    if not cost: raise HTTPException(409, 'This store has no purchase cost on record for the item, so it cannot be priced')
    review = serial({'from_store_id': store, 'to_store_id': body.to_store_id, 'item_code': body.item_code, 'name': rows[0]['name'],
        'base_unit': base_unit, 'inputs': body.model_dump(),
        'cost': {'mapping_id': cost['mapping_id'], 'base_quantity': cost['base_quantity'], 'cost_amount': cost['inventory_cost_amount'],
                 'record_date': cost['inventory_record_date']},
        'estimated_cost_amount': cents(body.sent_base_quantity, cost['inventory_cost_amount'], cost['base_quantity'])})
    return {'review': review, 'reviewHash': fingerprint(review).hex()}


async def send(pool, store, actor, body, key):
    digest = fingerprint(serial({'store': store, 'actor': actor, 'body': body.model_dump()}))
    async with pool.acquire() as conn, conn.transaction():
        await ready(conn); await lock_stores(conn, store, body.transfer.to_store_id)
        prior = await conn.fetchrow('SELECT * FROM actual_inventory.store_transfers WHERE request_key=$1', key)
        if prior:
            if prior['request_fingerprint'] != digest: raise HTTPException(409, 'Request key belongs to another transfer')
            return serial({'request_key': key, 'transfer': await one(conn, prior['id']), 'replayed': True})
        plan = await preview(conn, store, body.transfer)
        if plan['reviewHash'] != body.expected_review_hash: raise HTTPException(409, 'The item or its latest purchase cost changed. Review a fresh preview.')
        t, c = body.transfer, plan['review']['cost']
        ident = await conn.fetchval('''INSERT INTO actual_inventory.store_transfers(from_store_id,to_store_id,item_code,base_unit,sent_base_quantity,kind,sent_date,
            cost_mapping_id,cost_base_quantity,cost_amount,cost_record_date,note,actor,request_key,request_fingerprint)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15) RETURNING id''',
            store, t.to_store_id, t.item_code, plan['review']['base_unit'], t.sent_base_quantity, t.kind, t.sent_date,
            UUID(c['mapping_id']), Decimal(c['base_quantity']), Decimal(c['cost_amount']), date.fromisoformat(c['record_date']), t.note, actor, key, digest)
        return serial({'request_key': key, 'transfer': await one(conn, ident), 'replayed': False})


async def step(pool, store, transfer_id, actor, body, key):
    digest = fingerprint(serial({'store': store, 'transfer': transfer_id, 'actor': actor, 'body': body.model_dump()}))
    async with pool.acquire() as conn, conn.transaction():
        await ready(conn)
        t = await conn.fetchrow('SELECT * FROM actual_inventory.store_transfers WHERE id=$1 AND $2 IN (from_store_id, to_store_id)', transfer_id, store)
        if not t: raise HTTPException(404, 'Transfer is not for this location')
        await lock_stores(conn, t['from_store_id'], t['to_store_id'])
        prior = await conn.fetchrow('SELECT * FROM actual_inventory.store_transfer_events WHERE request_key=$1', key)
        if prior:
            if prior['request_fingerprint'] != digest: raise HTTPException(409, 'Request key belongs to another transfer step')
            return serial({'request_key': key, 'transfer': await one(conn, transfer_id), 'replayed': True})
        if await conn.fetchval('SELECT 1 FROM actual_inventory.store_transfer_events WHERE transfer_id=$1', transfer_id):
            raise HTTPException(409, 'This transfer was already received or cancelled')
        if body.action == 'cancel' and store != t['from_store_id']: raise HTTPException(403, 'Only the sending store cancels a transfer')
        if body.action == 'receive':
            if store != t['to_store_id']: raise HTTPException(403, 'Only the receiving store confirms what arrived')
            if body.received_base_quantity > t['sent_base_quantity']: raise HTTPException(422, 'Received more than was sent')
            if body.record_date < t['sent_date']: raise HTTPException(422, 'A transfer cannot be received before it was sent')
            if await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM actual_inventory.active_period_closures p WHERE p.store_id IN ($1,$2)
                AND $3>=p.period_start AND $3<p.period_end_exclusive) OR EXISTS(SELECT 1 FROM public.reporting_periods p
                WHERE p.store_id IN ($1,$2) AND p.status='closed' AND $3 BETWEEN p.period_start AND p.period_end)''', t['from_store_id'], t['to_store_id'], body.record_date):
                raise HTTPException(409, 'The received date is in a closed period at one of the stores')
        await conn.execute('''INSERT INTO actual_inventory.store_transfer_events(transfer_id,action,store_id,received_base_quantity,record_date,
            transfer_cost_amount,note,actor,request_key,request_fingerprint) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)''',
            transfer_id, body.action, store, body.received_base_quantity, body.record_date,
            cents(body.received_base_quantity, t['cost_amount'], t['cost_base_quantity']) if body.action == 'receive' else None,
            body.note, actor, key, digest)
        return serial({'request_key': key, 'transfer': await one(conn, transfer_id), 'replayed': False})


async def one(conn, transfer_id):
    t = dict(await conn.fetchrow('''SELECT t.*, i.name, e.action, e.received_base_quantity, e.record_date, e.transfer_cost_amount,
        e.note AS closing_note, e.actor AS closing_actor, e.created_at AS closed_at FROM actual_inventory.store_transfers t
        JOIN public.items i ON i.code=t.item_code LEFT JOIN actual_inventory.store_transfer_events e ON e.transfer_id=t.id WHERE t.id=$1''', transfer_id))
    t['status'] = {'receive': 'received', 'cancel': 'cancelled'}.get(t.pop('action'), 'sent')
    t['short_base_quantity'] = t['sent_base_quantity'] - t['received_base_quantity'] if t['status'] == 'received' else None
    del t['request_fingerprint']
    return serial(t)


async def read(conn, store, since):
    await ready(conn)
    ids = [r['id'] for r in await conn.fetch('''SELECT t.id FROM actual_inventory.store_transfers t
        WHERE $1 IN (t.from_store_id, t.to_store_id) AND (t.sent_date>=$2 OR NOT EXISTS(SELECT 1 FROM actual_inventory.store_transfer_events e WHERE e.transfer_id=t.id))
        ORDER BY t.sent_date DESC, t.created_at DESC LIMIT 500''', store, since)]
    items = await conn.fetch('''SELECT i.code, i.name, ib.base_unit FROM public.items i
        JOIN purchasing.item_bases ib ON ib.item_code=i.code AND ib.store_id=$1
        WHERE i.item_type='raw' ORDER BY i.name, i.code''', store)
    stores = await conn.fetch('SELECT id, name FROM public.stores WHERE id<>$1 ORDER BY id', store)
    return serial({'store_id': store, 'transfers': [await one(conn, i) for i in ids], 'items': [dict(r) for r in items], 'stores': [dict(r) for r in stores]})


async def movements(conn, store, start, end_exclusive):
    """Received transfers in (+) and out (-) for a food-cost period, or [] before the migration."""
    if not await installed(conn): return []
    return [dict(r) for r in await conn.fetch('''SELECT * FROM actual_inventory.transfer_movements
        WHERE store_id=$1 AND record_date>=$2 AND record_date<$3 ORDER BY record_date, transfer_id''', store, start, end_exclusive)]


def install_routes(router, context):
    @router.get('/{store_id}/transfers')
    async def read_transfers(store_id: str, request: Request, since: date):
        _, pool = await context(request, store_id)
        async with pool.acquire() as conn, conn.transaction(isolation='repeatable_read', readonly=True): return await read(conn, store_id, since)

    @router.post('/{store_id}/transfers/preview')
    async def preview_transfer(store_id: str, body: SendIn, request: Request):
        _, pool = await context(request, store_id, True)
        async with pool.acquire() as conn, conn.transaction(isolation='repeatable_read', readonly=True): return await preview(conn, store_id, body)

    @router.post('/{store_id}/transfers')
    async def send_transfer(store_id: str, body: SendCommit, request: Request, idempotency_key: UUID = Header(...)):
        actor, pool = await context(request, store_id, True)
        return await send(pool, store_id, actor, body, idempotency_key)

    @router.post('/{store_id}/transfers/{transfer_id}/steps')
    async def transfer_step(store_id: str, transfer_id: UUID, body: StepIn, request: Request, idempotency_key: UUID = Header(...)):
        actor, pool = await context(request, store_id, True)
        return await step(pool, store_id, transfer_id, actor, body, idempotency_key)
