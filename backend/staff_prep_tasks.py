"""Versioned manager assignments and location-authorized, read-only staff prep plans."""
import os
from datetime import date
from decimal import Decimal
from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import Field
import prep_execution as execution
import prep_mapping as mapping
from staff_prep_counts import Reviewed, Credentials
from staff_response import staff_view
from native_units import lock_store
from purchase_api import serial
from purchase_parser import fingerprint


class Assignment(mapping.Strict):
    task_id: UUID
    expected_revision: int = Field(ge=0, strict=True)
    staff_member_id: UUID | None
    note: str = Field(min_length=1, max_length=2000)


class Commit(Reviewed):
    assignment: Assignment
    expected_review_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


class ReadIn(Credentials):
    day: date
    track: Literal['daily', 'bulk'] = 'daily'
    staff_member_id: UUID | None = None


def enabled():
    requested = os.getenv('STAFF_PREP_TASKS_ENABLED', 'false').lower() == 'true'
    if requested and not execution.enabled(): raise HTTPException(503, 'Staff prep access requires native execution')
    return requested


async def ready(conn):
    if not enabled(): raise HTTPException(503, 'Staff prep access awaits enablement')
    await execution.ready(conn)
    if not await conn.fetchval("SELECT to_regclass('prep_inventory.task_assignments') IS NOT NULL"):
        raise HTTPException(503, 'Staff prep assignments await schema setup')


async def hold_legacy(conn):
    if os.getenv('STAFF_PREP_TASKS_ENABLED', 'false').lower() == 'true' or await conn.fetchval("SELECT to_regclass('prep_inventory.task_assignments') IS NOT NULL"):
        raise HTTPException(409, 'Legacy staff prep sheets are retained. Select an explicit date in the native staff prep plan.')


async def roster(conn, store):
    return serial([dict(r) for r in await conn.fetch('SELECT id,store_id,name,role,active FROM public.staff_members WHERE store_id=$1 ORDER BY name,id', store)])


async def history(conn, task):
    return serial([dict(r) for r in await conn.fetch('SELECT * FROM prep_inventory.task_assignments WHERE task_id=$1 ORDER BY revision', task)])


async def state(conn, store, day, track):
    await ready(conn)
    s = await execution.state(conn, store, day, track)
    members = await roster(conn, store)
    assignments = []
    for task in s['tasks']:
        rows = await history(conn, UUID(task['id']))
        current = rows[-1] if rows else None
        member = next((m for m in members if current and m['id'] == current['staff_member_id']), None)
        assignments.append(dict(task_id=task['id'], current=current, history=rows, current_member=member,
            roster_changed=bool(current and current['staff_member_id'] and member != current['review_snapshot']['member'])))
    return dict(store_id=store, day=str(day), track=track, execution=s, members=members, assignments=assignments)


async def preview(conn, store, day, track, body):
    s = await state(conn, store, day, track)
    e = s['execution']
    if e['status'] != 'released': raise HTTPException(409, 'Assign tasks only from the currently released dated plan')
    task = next((t for t in e['tasks'] if t['id'] == str(body.task_id)), None)
    if not task or not task['included'] or task['planned_quantity'] is None or Decimal(task['planned_quantity']) <= 0:
        raise HTTPException(422, 'Select a positive included task at this location, date and track')
    progress = next((p for p in e['task_progress'] if p['task_id'] == str(body.task_id)), None)
    if not progress: raise HTTPException(503, 'Assignments require native task progress')
    if progress['closed'] or progress['needs_review']: raise HTTPException(409, 'Finished or changed production must be reviewed before assignment')
    prior = next(a['current'] for a in s['assignments'] if a['task_id'] == str(body.task_id))
    if body.expected_revision != (prior['revision'] if prior else 0): raise HTTPException(409, 'Assignment changed; refresh and review the retained draft')
    member = next((m for m in s['members'] if m['id'] == str(body.staff_member_id) and m['active']), None)
    if body.staff_member_id and not member: raise HTTPException(422, 'Choose active roster staff at this location')
    if not body.staff_member_id and not prior: raise HTTPException(422, 'An unassigned task has no assignment to remove')
    review = serial(dict(store_id=store, day=day, track=track, assignment=body.model_dump(mode='json'),
        draft_version_id=e['draft_version_id'], release_event_id=e['release']['id'], execution_revision=e['revision'],
        task=task, progress=progress, member=member, predecessor_id=prior['id'] if prior else None,
        accountingEffect='none', productionEffect='none', identityBasis='Roster assignment; shared PIN does not verify an employee'))
    return dict(review=review, reviewHash=fingerprint(review).hex())


async def commit(pool, store, day, track, actor, body, key):
    digest = fingerprint(serial(dict(store=store, day=day, track=track, actor=actor, body=body.model_dump(mode='json'))))
    async with pool.acquire() as conn, conn.transaction():
        await ready(conn)
        await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))', str(key))
        await lock_store(conn, store)
        old = await conn.fetchrow('SELECT * FROM prep_inventory.task_assignments WHERE request_key=$1', key)
        if old:
            if old['request_fingerprint'] != digest: raise HTTPException(409, 'Request key belongs to another assignment or actor')
            return dict(assignment=serial(dict(old)), assignment_history=await history(conn,old['task_id']), current=await state(conn, store, day, track), replayed=True)
        await conn.execute('LOCK TABLE public.staff_members IN SHARE MODE')
        plan = await preview(conn, store, day, track, body.assignment)
        if plan['reviewHash'] != body.expected_review_hash: raise HTTPException(409, 'Plan, production or roster changed since review')
        p = plan['review']
        saved = await conn.fetchrow('''INSERT INTO prep_inventory.task_assignments(store_id,task_id,revision,predecessor_id,
            staff_member_id,note,review_snapshot,review_hash,recorded_by,request_key,request_fingerprint)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING *''', store,body.assignment.task_id,
            body.assignment.expected_revision+1,UUID(p['predecessor_id']) if p['predecessor_id'] else None,
            body.assignment.staff_member_id,body.assignment.note,p,bytes.fromhex(plan['reviewHash']),actor,key,digest)
        await conn.execute('UPDATE public.store_state SET revision=revision+1 WHERE store_id=$1', store)
        return dict(assignment=serial(dict(saved)), assignment_history=await history(conn,saved['task_id']), current=await state(conn, store, day, track), replayed=False)


async def staff_state(conn, store, body, kind):
    s = await state(conn, store, body.day, body.track)
    if body.staff_member_id and not any(m['id'] == str(body.staff_member_id) and m['active'] for m in s['members']):
        raise HTTPException(422, 'Selected roster identity is not active at this location')
    e = s['execution']
    tasks = []
    if e['status'] == 'released':
        for t in e['tasks']:
            if not t['included'] or t['planned_quantity'] is None or Decimal(t['planned_quantity']) <= 0: continue
            a = next((a for a in s['assignments'] if a['task_id'] == t['id']), None)
            if a is None:
                raise HTTPException(409, 'Task assignment state is incomplete; manager must review the current plan')
            if body.staff_member_id and (not a['current'] or a['current']['staff_member_id'] != str(body.staff_member_id)): continue
            tasks.append(dict(id=t['id'],name=t['task_snapshot']['name'],quantity=t['planned_quantity'],
                source_unit=t['task_snapshot']['source_unit'],base_unit=t['task_snapshot']['base_unit'],product_id=t['product_id'],recipe_version_id=t['recipe_version_id'],
                assignment=a['current']['id'] if a['current'] else None,assigned_member=a['current_member'],roster_changed=a['roster_changed'],
                progress=next((p for p in e['task_progress'] if p['task_id']==t['id']), None)))
            if tasks[-1]['progress'] is None:
                raise HTTPException(409, 'Task progress is incomplete; manager must review the current plan')
    return dict(store_id=store,day=str(body.day),track=body.track,status=e['status'],draft_version_id=e['draft_version_id'],
        execution_revision=e['revision'],selected_member_id=str(body.staff_member_id) if body.staff_member_id else None,
        credential_kind=kind,identity_verified=False,tasks=tasks,
        completionBehavior='Read-only plan. Manager records measured production and reviews task completion.')


def create_router(pool_factory, store_check, manager_authorize, staff_authorize):
    router = APIRouter()
    base = '/api/pg/purchases/{store}/staff-prep-tasks/{day}'

    @router.get(base)
    async def read(store: str, day: date, request: Request, track: Literal['daily','bulk']='daily'):
        store_check(store); manager_authorize(request,store,False)
        async with pool_factory().acquire() as conn, conn.transaction(isolation='repeatable_read',readonly=True): return await state(conn,store,day,track)

    @router.post(base+'/preview')
    async def plan(store: str, day: date, request: Request, body: Assignment, track: Literal['daily','bulk']='daily'):
        store_check(store); manager_authorize(request,store,True)
        async with pool_factory().acquire() as conn, conn.transaction(isolation='repeatable_read',readonly=True): return await preview(conn,store,day,track,body)

    @router.post(base+'/assignments')
    async def save(store: str, day: date, request: Request, body: Commit, idempotency_key: UUID=Header(...), track: Literal['daily','bulk']='daily'):
        store_check(store); actor=manager_authorize(request,store,True)
        return await commit(pool_factory(),store,day,track,actor,body,idempotency_key)

    @router.post('/api/pg/staff/{store}/prep-task-plan')
    async def staff_read(store: str, request: Request, body: ReadIn):
        store_check(store)
        async with pool_factory().acquire() as conn, conn.transaction(isolation='repeatable_read',readonly=True):
            await ready(conn); _,kind=await staff_authorize(request,conn,store,body.pin)
            return staff_view(await staff_state(conn,store,body,kind))

    return router
