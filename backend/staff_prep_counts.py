"""Issued Track 2 count sheets, immutable staff quantities and reviewed observations."""
import os
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import Field, field_validator, model_validator
import prep_mapping as mapping
import prep_observations as observations
from native_units import lock_store
from purchase_api import serial
from purchase_parser import fingerprint
from workflow_integrity import conflict_transaction, require_independent
from staff_response import staff_view


class Reviewed(mapping.Strict):
    reviewed: Literal[True]

    @field_validator('reviewed', mode='before')
    @classmethod
    def explicit(cls, value):
        if value is not True: raise ValueError('Explicit review is required')
        return value


class IssuedUnit(mapping.Strict):
    product_version_id: UUID
    profile_id: UUID


class SheetIn(observations.Stamp):
    units: list[IssuedUnit] = Field(min_length=1, max_length=500)

    @field_validator('calendar_date_confirmed', mode='before')
    @classmethod
    def explicit_boundary(cls, value):
        if value is not True: raise ValueError('Explicit calendar boundary confirmation is required')
        return value

    @model_validator(mode='after')
    def distinct(self):
        if len({u.product_version_id for u in self.units}) != len(self.units):
            raise ValueError('Choose one verified count unit per prepared identity')
        self.units.sort(key=lambda u: str(u.product_version_id))
        if self.calendar_date_confirmed is not True: raise ValueError('Confirm the calendar boundary')
        return self


class IssueIn(Reviewed):
    sheet: SheetIn
    expected_review_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


class Credentials(mapping.Strict):
    pin: str = Field('', max_length=100)


class Quantity(mapping.Strict):
    product_id: UUID
    quantity: Decimal | None = Field(None, ge=0, max_digits=28, decimal_places=12)
    evidence: str = Field('', max_length=2000)


class SubmitIn(Credentials):
    expected_review_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    counter_name: str = Field(min_length=1, max_length=200)
    note: str = Field(min_length=1, max_length=2000)
    lines: list[Quantity] = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def distinct(self):
        if len({u.product_id for u in self.lines}) != len(self.lines):
            raise ValueError('Include every issued prepared identity once')
        self.lines.sort(key=lambda u: str(u.product_id))
        return self


class Decision(Reviewed):
    decision: Literal['accepted', 'rejected']
    note: str = Field(min_length=1, max_length=2000)


class DecisionIn(Decision):
    expected_review_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_observation_hash: str | None = Field(None, pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def matching(self):
        if (self.decision == 'accepted') != (self.expected_observation_hash is not None):
            raise ValueError('Acceptance requires its reviewed physical observation; rejection has none')
        return self


def enabled():
    requested = os.getenv('STAFF_PREP_COUNTS_ENABLED', 'false').lower() == 'true'
    if requested and not observations.enabled():
        raise HTTPException(503, 'Staff prep counts require native prep observations')
    return requested


async def ready(conn):
    if not enabled(): raise HTTPException(503, 'Staff prep count submissions are awaiting enablement')
    await observations.ready(conn)
    if not await conn.fetchval("SELECT to_regclass('prep_inventory.staff_decisions') IS NOT NULL"):
        raise HTTPException(503, 'Staff prep count migration is awaiting setup')


async def hold_legacy(conn):
    if os.getenv('STAFF_PREP_COUNTS_ENABLED', 'false').lower() == 'true' or await conn.fetchval("SELECT to_regclass('prep_inventory.staff_sheets') IS NOT NULL"):
        raise HTTPException(409, 'Legacy prep count sessions are retained. Use manager-issued native prep sheets and reviewed observations.')


async def boundary_errors(conn, store, stamp, sheet_id=None):
    errors = []
    from datetime import datetime
    time = datetime.fromisoformat(stamp['performed_at'])
    policy = await conn.fetchval('SELECT timezone_name FROM prep_inventory.batch_policies WHERE store_id=$1', store)
    if policy and policy != stamp['timezone_name']: errors.append('The location timezone changed; issue a new sheet')
    if await conn.fetchval("SELECT 1 FROM prep_inventory.observations WHERE store_id=$1 AND purpose='count' AND kind='initial' AND performed_at=$2", store, time):
        errors.append('A physical prep count already occupies this boundary; review its correction history')
    if await conn.fetchval('''SELECT 1 FROM prep_inventory.staff_sheets s WHERE store_id=$1 AND performed_at=$2
        AND ($3::uuid IS NULL OR id<>$3) AND NOT EXISTS(SELECT 1 FROM prep_inventory.staff_decisions d
        WHERE d.sheet_id=s.id AND d.decision='rejected')''', store, time, sheet_id):
        errors.append('Another issued sheet occupies this physical boundary')
    return errors


async def issue_preview(conn, store, body):
    await ready(conn)
    items = []
    for unit in body.units:
        p = await mapping.current_product(conn, store, unit.product_version_id)
        u = await mapping.current_profile(conn, store, unit.profile_id, unit.product_version_id)
        items.append(dict(product_id=p['product_id'], product_version_id=p['id'], profile_id=u['id'],
                          name=p['name'], base_unit=p['base_unit'], counted_unit=u['source_unit'],
                          factor=u['base_units_per_source_unit']))
    scope = [str(r['id']) for r in await conn.fetch('SELECT id FROM prep_inventory.products WHERE store_id=$1 ORDER BY id::text', store)]
    if sorted(str(i['product_id']) for i in items) != scope:
        raise HTTPException(422, 'Issue a full prepared-inventory sheet; purchased items are excluded')
    stamp = body.model_dump(mode='json', exclude={'units'})
    errors = await boundary_errors(conn, store, stamp)
    if errors: raise HTTPException(409, '; '.join(errors))
    snapshot = serial(dict(store_id=store, stamp=stamp, items=sorted(items, key=lambda i: str(i['product_id']))))
    return dict(review=snapshot, reviewHash=fingerprint(snapshot).hex())


async def detail(conn, store, ident):
    sheet = await conn.fetchrow('SELECT * FROM prep_inventory.staff_sheets WHERE id=$1 AND store_id=$2', ident, store)
    if not sheet: raise HTTPException(404, 'Prep count sheet not found at this location')
    history = await conn.fetch('SELECT * FROM prep_inventory.staff_submissions WHERE sheet_id=$1 ORDER BY revision DESC', ident)
    decision = await conn.fetchrow('SELECT * FROM prep_inventory.staff_decisions WHERE sheet_id=$1', ident)
    errors = []
    if not decision:
        snapshot = sheet['sheet_snapshot']
        errors.extend(await boundary_errors(conn, store, snapshot['stamp'], ident))
        scope = {str(r['id']) for r in await conn.fetch('SELECT id FROM prep_inventory.products WHERE store_id=$1', store)}
        if scope != {i['product_id'] for i in snapshot['items']}: errors.append('Prepared-inventory scope changed; issue a new sheet')
        for item in snapshot['items']:
            try:
                await mapping.current_product(conn, store, UUID(item['product_version_id']))
                await mapping.current_profile(conn, store, UUID(item['profile_id']), UUID(item['product_version_id']))
            except HTTPException: errors.append(f"Prepared definition or count units changed for {item['name']}; issue a new sheet")
    return review_record(sheet,history,decision,errors)


def review_record(sheet,history,decision,errors):
    result = serial(dict(sheet=dict(sheet), latest=dict(history[0]) if history else None,
                         history=[dict(r) for r in history], decision=dict(decision) if decision else None, errors=errors))
    result['reviewHash'] = fingerprint(result).hex()
    return result


async def count_definitions(conn,store):
    await mapping.ready(conn)
    products = await conn.fetch('''SELECT DISTINCT ON(product_id) * FROM prep_inventory.product_versions
        WHERE store_id=$1 ORDER BY product_id,revision DESC''',store)
    profiles = await conn.fetch('''SELECT DISTINCT ON(product_version_id,source_unit) * FROM prep_inventory.unit_profiles
        WHERE store_id=$1 ORDER BY product_version_id,source_unit,revision DESC''',store)
    return serial(dict(products=[dict(r) for r in products],profiles=[dict(r) for r in profiles]))


async def details(conn,store,identities=None,definitions=None,pending_only=False):
    sheets = await conn.fetch('''SELECT s.* FROM prep_inventory.staff_sheets s WHERE store_id=$1
        AND ($2::uuid[] IS NULL OR id=ANY($2))
        AND (NOT $3 OR NOT EXISTS(SELECT 1 FROM prep_inventory.staff_decisions d WHERE d.sheet_id=s.id))
        ORDER BY performed_at DESC,issued_at DESC''',store,identities,pending_only)
    if not sheets: return []
    ids = [r['id'] for r in sheets]
    histories = {ident:[] for ident in ids}
    for row in await conn.fetch('''SELECT * FROM prep_inventory.staff_submissions
        WHERE store_id=$1 AND sheet_id=ANY($2::uuid[]) ORDER BY sheet_id,revision DESC''',store,ids):
        histories[row['sheet_id']].append(row)
    decisions = {r['sheet_id']:r for r in await conn.fetch('''SELECT * FROM prep_inventory.staff_decisions
        WHERE store_id=$1 AND sheet_id=ANY($2::uuid[])''',store,ids)}
    pending = [r for r in sheets if r['id'] not in decisions]
    if pending:
        definitions = definitions if definitions is not None else await count_definitions(conn,store)
        scope = {str(r['id']) for r in await conn.fetch('SELECT id FROM prep_inventory.products WHERE store_id=$1',store)}
        versions = {r['id'] for r in definitions['products']}
        profiles = {(r['id'],r['product_version_id']) for r in definitions['profiles']}
        policy = await conn.fetchval('SELECT timezone_name FROM prep_inventory.batch_policies WHERE store_id=$1',store)
        boundaries = [datetime.fromisoformat(r['sheet_snapshot']['stamp']['performed_at']) for r in pending]
        observed = {r['performed_at'] for r in await conn.fetch('''SELECT performed_at FROM prep_inventory.observations
            WHERE store_id=$1 AND purpose='count' AND kind='initial' AND performed_at=ANY($2::timestamptz[])''',store,boundaries)}
        occupied = {}
        for row in await conn.fetch('''SELECT s.id,s.performed_at FROM prep_inventory.staff_sheets s
            WHERE store_id=$1 AND performed_at=ANY($2::timestamptz[])
            AND NOT EXISTS(SELECT 1 FROM prep_inventory.staff_decisions d WHERE d.sheet_id=s.id AND d.decision='rejected')''',store,boundaries):
            occupied.setdefault(row['performed_at'],set()).add(row['id'])
    results = []
    for sheet in sheets:
        errors = []
        decision = decisions.get(sheet['id'])
        if not decision:
            snapshot = sheet['sheet_snapshot']; stamp = snapshot['stamp']
            instant = datetime.fromisoformat(stamp['performed_at'])
            if policy and policy!=stamp['timezone_name']:errors.append('The location timezone changed; issue a new sheet')
            if instant in observed:errors.append('A physical prep count already occupies this boundary; review its correction history')
            if occupied.get(instant,set())-{sheet['id']}:errors.append('Another issued sheet occupies this physical boundary')
            if scope!={i['product_id'] for i in snapshot['items']}:errors.append('Prepared-inventory scope changed; issue a new sheet')
            for item in snapshot['items']:
                if item['product_version_id'] not in versions or (item['profile_id'],item['product_version_id']) not in profiles:
                    errors.append(f"Prepared definition or count units changed for {item['name']}; issue a new sheet")
        results.append(review_record(sheet,histories[sheet['id']],decision,errors))
    return results


async def prior(conn, table, store, key, digest):
    assert table in ('staff_sheets', 'staff_submissions', 'staff_decisions')
    row = await conn.fetchrow(f'SELECT * FROM prep_inventory.{table} WHERE request_key=$1', key)
    if row and (row['store_id'] != store or row['request_fingerprint'] != digest):
        raise HTTPException(409, 'Request key belongs to another action or actor; check its saved outcome')
    return row


async def coordinate(conn, store, key):
    await ready(conn)
    await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))', str(key))
    await lock_store(conn, store)


def current(review, expected, allow_stale=False):
    if review['decision'] or review['reviewHash'] != expected:
        raise HTTPException(409, 'Prep count sheet changed or was decided; refresh without discarding your draft')
    if review['errors'] and not allow_stale: raise HTTPException(409, '; '.join(review['errors']))


async def issue(pool, store, actor, body, key):
    digest = fingerprint(dict(body=body.model_dump(mode='json'), actor=actor))
    async with pool.acquire() as conn, conflict_transaction(conn):
        await coordinate(conn, store, key)
        old = await prior(conn, 'staff_sheets', store, key, digest)
        if old: return dict(sheet=serial(dict(old)), current=await detail(conn, store, old['id']), replayed=True)
        plan = await issue_preview(conn, store, body.sheet)
        if plan['reviewHash'] != body.expected_review_hash: raise HTTPException(409, 'Prepared scope or units changed since issue review')
        row = await conn.fetchrow('''INSERT INTO prep_inventory.staff_sheets(store_id,performed_at,business_date,timezone_name,
            sheet_snapshot,review_hash,issued_by,request_key,request_fingerprint) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *''',
            store, body.sheet.performed_at, body.sheet.business_date, body.sheet.timezone_name, plan['review'],
            bytes.fromhex(plan['reviewHash']), actor, key, digest)
        return dict(sheet=serial(dict(row)), current=await detail(conn, store, row['id']), replayed=False)


async def submit(pool, store, ident, actor, kind, body, key):
    # Neither the PIN nor a PIN-derived digest is retained. Name is claimed attribution.
    public_body = body.model_dump(mode='json', exclude={'pin'})
    digest = fingerprint(dict(sheet_id=str(ident), body=public_body, actor=actor, credential_kind=kind))
    async with pool.acquire() as conn, conflict_transaction(conn):
        await coordinate(conn, store, key)
        old = await prior(conn, 'staff_submissions', store, key, digest)
        if old: return dict(submission=serial(dict(old)), current=await detail(conn, store, ident), replayed=True)
        review = await detail(conn, store, ident); current(review, body.expected_review_hash)
        members = {i['product_id'] for i in review['sheet']['sheet_snapshot']['items']}
        if {str(l.product_id) for l in body.lines} != members: raise HTTPException(422, 'Include every issued prepared item once; blank means uncounted')
        row = await conn.fetchrow('''INSERT INTO prep_inventory.staff_submissions(sheet_id,store_id,revision,counter_name,
            credential_kind,submitted_by,note,quantities,submitted_body,request_key,request_fingerprint)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING *''', ident, store,
            (review['latest']['revision'] if review['latest'] else 0)+1, body.counter_name, kind, actor, body.note,
            public_body['lines'], public_body, key, digest)
        return dict(submission=serial(dict(row)), current=await detail(conn, store, ident), replayed=False)


async def decision_preview(conn, store, ident, body, actor=None):
    await ready(conn)
    review = await detail(conn, store, ident)
    if review['decision']: raise HTTPException(409, 'This sheet already has a final decision')
    plan = None
    if body.decision == 'accepted':
        if actor is not None:
            require_independent(actor, [row['submitted_by'] for row in review['history']])
        if review['errors']: raise HTTPException(409, '; '.join(review['errors']))
        if not review['latest']: raise HTTPException(422, 'Staff must submit measured quantities first')
        rows = {l['product_id']: l for l in review['latest']['quantities']}
        lines = []
        for item in review['sheet']['sheet_snapshot']['items']:
            line = rows[item['product_id']]
            if line['quantity'] is None or not line['evidence'].strip():
                raise HTTPException(422, 'All issued quantities and measurement evidence are required for acceptance; blank is not zero')
            lines.append(observations.CountLine(product_version_id=item['product_version_id'], profile_id=item['profile_id'],
                                                 quantity=line['quantity'], evidence=line['evidence']))
        stamp = review['sheet']['sheet_snapshot']['stamp'] | dict(note=body.note)
        plan = await observations.preview(conn, store, 'count', observations.CountIn(**stamp, complete_scope_confirmed=True, lines=lines))
    return dict(current=review, observation=plan, decision=body.model_dump(mode='json', include={'decision', 'note', 'reviewed'}))


async def decide(pool, store, ident, actor, body, key):
    digest = fingerprint(dict(sheet_id=str(ident), body=body.model_dump(mode='json'), actor=actor))
    async with pool.acquire() as conn, conflict_transaction(conn):
        await coordinate(conn, store, key)
        old = await prior(conn, 'staff_decisions', store, key, digest)
        if old: return await outcome(conn, store, ident, serial(dict(old)), True)
        # Native definition writes share the store lock; public catalog writers are held as in observation recording.
        await conn.execute('LOCK TABLE public.items,public.store_items,public.dishes,public.dish_lines,public.prep_items IN SHARE MODE')
        plan = await decision_preview(conn, store, ident, body, actor)
        current(plan['current'], body.expected_review_hash, allow_stale=body.decision == 'rejected')
        observation_id = None
        if plan['observation']:
            if plan['observation']['reviewHash'] != body.expected_observation_hash:
                raise HTTPException(409, 'Physical observation changed; review acceptance again')
            saved = await observations.persist(conn, store, plan['observation'], key, digest, actor)
            observation_id = UUID(saved['event']['id'])
        latest = plan['current']['latest']
        row = await conn.fetchrow('''INSERT INTO prep_inventory.staff_decisions(sheet_id,store_id,submission_id,decision,
            observation_id,note,review_snapshot,reviewed_by,request_key,request_fingerprint)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING *''', ident, store,
            UUID(latest['id']) if latest else None, body.decision, observation_id, body.note, plan, actor, key, digest)
        return await outcome(conn, store, ident, serial(dict(row)), False)


async def outcome(conn, store, ident, decision, replayed):
    event = await conn.fetchrow('SELECT * FROM prep_inventory.observations WHERE id=$1 AND store_id=$2',
                                UUID(decision['observation_id']), store) if decision['observation_id'] else None
    return dict(decision=decision, current=await detail(conn, store, ident), observation=serial(dict(event)) if event else None, replayed=replayed)


def create_router(pool_factory, store_check, manager_authorize, staff_authorize):
    router = APIRouter()

    async def manager(request, store, write=False):
        store_check(store); actor = manager_authorize(request, store, write); pool = pool_factory()
        async with pool.acquire() as conn: await ready(conn)
        return actor, pool

    @router.get('/api/pg/purchases/{store}/staff-prep-counts')
    async def setup(store: str, request: Request):
        _, pool = await manager(request, store)
        async with pool.acquire() as conn, conn.transaction(isolation='repeatable_read', readonly=True):
            definitions = await count_definitions(conn,store)
            return dict(store_id=store, products=definitions['products'], profiles=definitions['profiles'],
                        sheets=await details(conn,store,definitions=definitions))

    @router.post('/api/pg/purchases/{store}/staff-prep-counts/preview')
    async def issue_plan(store: str, request: Request, body: SheetIn):
        _, pool = await manager(request, store, True)
        async with pool.acquire() as conn, conn.transaction(isolation='repeatable_read', readonly=True):
            return await issue_preview(conn, store, body)

    @router.post('/api/pg/purchases/{store}/staff-prep-counts')
    async def issue_sheet(store: str, request: Request, body: IssueIn, idempotency_key: UUID = Header(...)):
        actor, pool = await manager(request, store, True)
        return await issue(pool, store, actor, body, idempotency_key)

    @router.post('/api/pg/purchases/{store}/staff-prep-counts/{ident}/decision-preview')
    async def review_decision(store: str, ident: UUID, request: Request, body: Decision):
        actor, pool = await manager(request, store, True)
        async with pool.acquire() as conn, conn.transaction(isolation='repeatable_read', readonly=True):
            return await decision_preview(conn, store, ident, body, actor)

    @router.post('/api/pg/purchases/{store}/staff-prep-counts/{ident}/decision')
    async def record_decision(store: str, ident: UUID, request: Request, body: DecisionIn, idempotency_key: UUID = Header(...)):
        actor, pool = await manager(request, store, True)
        return await decide(pool, store, ident, actor, body, idempotency_key)

    @router.post('/api/pg/staff/{store}/prep-count-drafts')
    async def staff_sheets(store: str, request: Request, body: Credentials):
        store_check(store); pool = pool_factory()
        async with pool.acquire() as conn, conn.transaction(isolation='repeatable_read', readonly=True):
            await ready(conn); await staff_authorize(request, conn, store, body.pin)
            return staff_view(await details(conn,store,pending_only=True))

    @router.post('/api/pg/staff/{store}/prep-count-drafts/{ident}/submit')
    async def staff_submit(store: str, ident: UUID, request: Request, body: SubmitIn, idempotency_key: UUID = Header(...)):
        store_check(store); pool = pool_factory()
        async with pool.acquire() as conn:
            await ready(conn); actor, kind = await staff_authorize(request, conn, store, body.pin)
        return staff_view(await submit(pool, store, ident, actor, kind, body, idempotency_key))

    return router
