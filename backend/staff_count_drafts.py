"""Immutable staff quantity drafts and atomic, explicit-value manager acceptance."""
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import Field, field_validator
import actual_inventory_api as actual
from native_units import profiles
from purchase_api import serial
from purchase_parser import fingerprint


class NoteModel(actual.StrictModel):
    note: str = Field(min_length=1, max_length=2000)

    @field_validator('note')
    @classmethod
    def required(cls, value):
        if not value.strip(): raise ValueError('A review or measurement note is required')
        return value.strip()


class IssueInput(NoteModel):
    scope_id: UUID
    count_date: date
    timing: Literal['before_receipts','after_receipts']


class Credentials(actual.StrictModel):
    pin: str = Field('', max_length=100)


class Quantity(actual.StrictModel):
    item_code: str
    counted_quantity: Decimal | None = Field(None, ge=0, max_digits=28, decimal_places=10)
    note: str = Field('', max_length=2000)


class SubmitInput(NoteModel):
    pin: str = Field('', max_length=100)
    expected_review_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    counter_name: str = Field(min_length=1, max_length=200)
    lines: list[Quantity] = Field(min_length=1, max_length=10000)

    @field_validator('counter_name')
    @classmethod
    def counter(cls, value):
        if not value.strip(): raise ValueError('Enter the counter name for attribution')
        return value.strip()


class Value(actual.StrictModel):
    item_code: str
    inventory_value: Decimal = Field(ge=0, max_digits=20, decimal_places=2)
    confirmed: Literal[True]
    note: str = Field(min_length=1, max_length=2000)

    @field_validator('note')
    @classmethod
    def evidence(cls, value):
        if not value.strip(): raise ValueError('Confirm the quantity and value evidence')
        return value.strip()


class DecisionInput(NoteModel):
    expected_review_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    decision: Literal['accepted','rejected']
    quantities_reviewed: bool = False
    values: list[Value] = Field(default_factory=list, max_length=10000)


async def ready(conn):
    if not actual.enabled(): raise HTTPException(503, 'Actual inventory is awaiting enablement')
    if not await conn.fetchval("SELECT to_regclass('actual_inventory.staff_decisions') IS NOT NULL"):
        raise HTTPException(503, 'Staff count review setup is awaiting enablement')


async def detail(conn, store, sheet_id):
    sheet = await conn.fetchrow('SELECT * FROM actual_inventory.staff_sheets WHERE id=$1 AND store_id=$2', sheet_id, store)
    if not sheet: raise HTTPException(404, 'Count sheet not found at this location')
    submissions = await conn.fetch('SELECT * FROM actual_inventory.staff_submissions WHERE sheet_id=$1 ORDER BY revision DESC', sheet_id)
    decision = await conn.fetchrow('SELECT * FROM actual_inventory.staff_decisions WHERE sheet_id=$1', sheet_id)
    current = await actual.get_scope(conn, store)
    errors = []
    if not current or current['header']['id'] != sheet['scope_id']: errors.append('The purchased-item scope changed; issue a new sheet')
    if not decision and await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM actual_inventory.count_snapshots
        WHERE store_id=$1 AND scope_id=$2 AND count_date=$3 AND timing=$4)''',store,sheet['scope_id'],sheet['count_date'],sheet['timing']):
        errors.append('An accounting count already occupies this boundary; use the manager recount workflow')
    live = {p['item_code']:p for p in await profiles(conn, store) if p['profile_kind']=='count' and not p['stale']}
    items = sheet['sheet_snapshot']['items']
    for item in items:
        p = live.get(item['item_code'])
        if not p or str(p['id']) != item['profile_id']: errors.append(f"Verified count units changed for {item['item_code']}; issue a new sheet")
    result = serial({'sheet':dict(sheet), 'latest':dict(submissions[0]) if submissions else None,
                     'history':[dict(r) for r in submissions], 'decision':dict(decision) if decision else None,
                     'errors':errors})
    result['reviewHash'] = fingerprint(result).hex()
    return result


async def prior(conn, table, store, key, digest):
    assert table in ('staff_sheets','staff_submissions','staff_decisions')
    row = await conn.fetchrow(f'SELECT * FROM actual_inventory.{table} WHERE request_key=$1', key)
    if row and (row['store_id'] != store or row['request_fingerprint'] != digest):
        raise HTTPException(409, 'Request key belongs to a different action; check its saved outcome')
    return row


async def lock_catalog(conn, store, codes):
    # Item definitions are shared across stores. A store revision lock alone
    # cannot hold another store's catalog edit while accepting these units.
    await conn.fetch('''SELECT i.code FROM public.items i JOIN public.store_items si ON si.item_code=i.code
        WHERE si.store_id=$1 AND i.code=ANY($2::text[]) ORDER BY i.code FOR SHARE OF i,si''',store,codes)


async def issue(pool, store, actor, body, key):
    digest = fingerprint({'body':body.model_dump(mode='json'),'actor':actor})
    async with pool.acquire() as conn, conn.transaction():
        await ready(conn); await actual.lock_store(conn, store)
        old = await prior(conn, 'staff_sheets', store, key, digest)
        if old: return await detail(conn, store, old['id'])
        scope = await actual.get_scope(conn, store)
        if not scope or scope['header']['id'] != body.scope_id: raise HTTPException(409, 'Issue against the current purchased-item scope')
        await lock_catalog(conn,store,[i['item_code'] for i in scope['items']])
        occupied = await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM actual_inventory.count_snapshots
            WHERE store_id=$1 AND scope_id=$2 AND count_date=$3 AND timing=$4)
            OR EXISTS(SELECT 1 FROM actual_inventory.staff_sheets s WHERE store_id=$1 AND scope_id=$2
            AND count_date=$3 AND timing=$4 AND NOT EXISTS(SELECT 1 FROM actual_inventory.staff_decisions d
            WHERE d.sheet_id=s.id AND d.decision='rejected'))''',store,body.scope_id,body.count_date,body.timing)
        if occupied: raise HTTPException(409, 'This boundary already has a count or issued sheet; review it before starting another')
        live = {p['item_code']:p for p in await profiles(conn, store) if p['profile_kind']=='count' and not p['stale']}
        items = []
        for item in scope['items']:
            p = live.get(item['item_code'])
            if not p or p['base_unit'] != item['base_unit']: raise HTTPException(409, f"Verify the count-unit profile for {item['item_code']} first")
            items.append({**item, 'profile_id':str(p['id']), 'counted_unit':p['source_unit'],
                          'base_units_per_counted_unit':str(p['base_units_per_source_unit'])})
        snapshot = serial({'scope_revision':scope['header']['revision'],'items':items})
        sheet_id = await conn.fetchval('''INSERT INTO actual_inventory.staff_sheets
            (store_id,scope_id,count_date,timing,note,sheet_snapshot,request_key,request_fingerprint,issued_by)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id''', store, body.scope_id, body.count_date,
            body.timing, body.note, snapshot, key, digest, actor)
        return await detail(conn, store, sheet_id)


def check_current(review, expected):
    if review['decision']: raise HTTPException(409, 'This sheet already has a final decision; check history')
    if review['errors']: raise HTTPException(409, '; '.join(review['errors']))
    if review['reviewHash'] != expected: raise HTTPException(409, 'Count draft changed after review; refresh before submitting or accepting')


async def submit(pool, store, sheet_id, actor, kind, body, key):
    # Shared PIN is never retained or hashed into audit evidence.
    digest = fingerprint({'sheet':str(sheet_id),'body':body.model_dump(mode='json',exclude={'pin'}),'actor':actor,'kind':kind})
    async with pool.acquire() as conn, conn.transaction():
        await ready(conn); await actual.lock_store(conn, store)
        old = await prior(conn, 'staff_submissions', store, key, digest)
        if old: return {'submission':serial(dict(old)),'review':await detail(conn, store, sheet_id)}
        review = await detail(conn, store, sheet_id); check_current(review, body.expected_review_hash)
        members = {i['item_code'] for i in review['sheet']['sheet_snapshot']['items']}
        if len(body.lines) != len(members) or {r.item_code for r in body.lines} != members:
            raise HTTPException(422, 'Include each issued item once; leave uncounted quantities blank')
        quantities = serial([r.model_dump() for r in sorted(body.lines,key=lambda r:r.item_code)])
        revision = (review['latest']['revision'] if review['latest'] else 0)+1
        row = await conn.fetchrow('''INSERT INTO actual_inventory.staff_submissions
            (sheet_id,store_id,revision,counter_name,credential_kind,submitted_by,note,quantities,request_key,request_fingerprint)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING *''',sheet_id,store,revision,
            body.counter_name,kind,actor,body.note,quantities,key,digest)
        return {'submission':serial(dict(row)),'review':await detail(conn, store, sheet_id)}


async def decide(pool, store, sheet_id, actor, body, key):
    digest = fingerprint({'sheet':str(sheet_id),'body':body.model_dump(mode='json'),'actor':actor})
    async with pool.acquire() as conn, conn.transaction():
        await ready(conn); await actual.lock_store(conn, store)
        old = await prior(conn, 'staff_decisions', store, key, digest)
        if old: return await outcome(conn,store,sheet_id)
        sheet = await conn.fetchrow('SELECT sheet_snapshot FROM actual_inventory.staff_sheets WHERE id=$1 AND store_id=$2',sheet_id,store)
        if not sheet: raise HTTPException(404, 'Count sheet not found at this location')
        await lock_catalog(conn,store,[i['item_code'] for i in sheet['sheet_snapshot']['items']])
        review = await detail(conn, store, sheet_id)
        # Rejection can retire a stale or unused sheet; acceptance cannot.
        if review['decision'] or review['reviewHash'] != body.expected_review_hash:
            raise HTTPException(409, 'Count draft changed or was already decided; refresh its history')
        snapshot_id = None
        if body.decision == 'accepted':
            check_current(review, body.expected_review_hash)
            if not body.quantities_reviewed or not review['latest']: raise HTTPException(422, 'Review the submitted physical quantities before accepting')
            quantities = {r['item_code']:r for r in review['latest']['quantities']}
            items = review['sheet']['sheet_snapshot']['items']
            values = {r.item_code:r for r in body.values}
            if len(body.values) != len(items) or set(values) != {i['item_code'] for i in items}:
                raise HTTPException(422, 'Confirm explicit values for every issued item')
            lines = []
            for item in items:
                q = quantities[item['item_code']]; v = values[item['item_code']]
                if q['counted_quantity'] is None: raise HTTPException(422, 'Uncounted quantities remain incomplete; staff must submit a complete revision')
                lines.append(actual.CountLine(item_code=item['item_code'],counted_quantity=q['counted_quantity'],
                    counted_unit=item['counted_unit'],base_units_per_counted_unit=item['base_units_per_counted_unit'],
                    inventory_value=v.inventory_value,confirmed=True,note=v.note))
            sheet = review['sheet']
            count = actual.CountInput(scope_id=sheet['scope_id'],count_date=sheet['count_date'],timing=sheet['timing'],
                note=body.note,lines=lines)
            snapshot_id = await actual.save_count(pool,store,actor,count,key,conn=conn)
        elif body.values:
            raise HTTPException(422, 'Reject without inventory values; rejection does not create an accounting count')
        submission_id = UUID(review['latest']['id']) if review['latest'] else None
        await conn.execute('''INSERT INTO actual_inventory.staff_decisions
            (sheet_id,store_id,submission_id,decision,snapshot_id,note,review_snapshot,reviewed_by,request_key,request_fingerprint)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)''',sheet_id,store,submission_id,body.decision,
            snapshot_id,body.note,review,actor,key,digest)
        return await outcome(conn,store,sheet_id)


async def outcome(conn, store, sheet_id):
    review = await detail(conn, store, sheet_id)
    decision = review['decision']
    count = await actual.get_count(conn, store, UUID(decision['snapshot_id'])) if decision and decision['snapshot_id'] else None
    return serial({'review':review,'count':count})


def create_router(pool_factory, store_check, manager_authorize, staff_authorize):
    router = APIRouter()

    async def manager(request,store,write=False):
        store_check(store); actor=manager_authorize(request,store,write); pool=pool_factory()
        async with pool.acquire() as conn: await ready(conn)
        return actor,pool

    @router.get('/api/pg/actual-inventory/{store}/staff-sheets')
    async def sheets(store:str,request:Request):
        _,pool=await manager(request,store)
        async with pool.acquire() as conn, conn.transaction(isolation='repeatable_read',readonly=True):
            ids=await conn.fetch('SELECT id FROM actual_inventory.staff_sheets WHERE store_id=$1 ORDER BY count_date DESC,issued_at DESC',store)
            return [await detail(conn,store,r['id']) for r in ids]

    @router.post('/api/pg/actual-inventory/{store}/staff-sheets')
    async def issue_sheet(store:str,request:Request,body:IssueInput,idempotency_key:UUID=Header(...)):
        actor,pool=await manager(request,store,True)
        return await issue(pool,store,actor,body,idempotency_key)

    @router.post('/api/pg/actual-inventory/{store}/staff-sheets/{sheet_id}/decision')
    async def decision(store:str,sheet_id:UUID,request:Request,body:DecisionInput,idempotency_key:UUID=Header(...)):
        actor,pool=await manager(request,store,True)
        return await decide(pool,store,sheet_id,actor,body,idempotency_key)

    @router.post('/api/pg/staff/{store}/count-drafts')
    async def staff_list(store:str,request:Request,body:Credentials):
        store_check(store); pool=pool_factory()
        async with pool.acquire() as conn, conn.transaction(isolation='repeatable_read',readonly=True):
            await ready(conn); await staff_authorize(request,conn,store,body.pin)
            ids=await conn.fetch('''SELECT s.id FROM actual_inventory.staff_sheets s WHERE s.store_id=$1
                AND NOT EXISTS(SELECT 1 FROM actual_inventory.staff_decisions d WHERE d.sheet_id=s.id)
                ORDER BY s.count_date DESC,s.issued_at DESC''',store)
            # Staff quantities and units only. No manager values/accepted history.
            return [await detail(conn,store,r['id']) for r in ids]

    @router.post('/api/pg/staff/{store}/count-drafts/{sheet_id}/submit')
    async def staff_submit(store:str,sheet_id:UUID,request:Request,body:SubmitInput,idempotency_key:UUID=Header(...)):
        store_check(store); pool=pool_factory()
        async with pool.acquire() as conn:
            await ready(conn); actor,kind=await staff_authorize(request,conn,store,body.pin)
        return await submit(pool,store,sheet_id,actor,kind,body,idempotency_key)

    return router
