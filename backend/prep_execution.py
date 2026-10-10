"""Append-only manager release and production evidence links, never stock writes."""
import os
from datetime import date
from decimal import Decimal
from uuid import UUID
from typing import Literal
from fastapi import Header, HTTPException, Request
from pydantic import Field, field_validator, model_validator
import prep_day_tasks as drafts
import prep_mapping as mapping
import catalog_mapping
from native_units import lock_store
from purchase_api import serial
from purchase_parser import fingerprint


def enabled():
    requested = os.getenv('PREP_EXECUTION_ENABLED', 'false').lower() == 'true'
    if requested and not drafts.enabled():
        raise HTTPException(503, 'Prep execution requires reviewed dated drafts')
    return requested


async def installed(conn):
    return await conn.fetchval("SELECT to_regclass('prep_inventory.execution_events') IS NOT NULL")


async def ready(conn):
    if not enabled(): raise HTTPException(503, 'Prep execution is awaiting enablement')
    await drafts.ready(conn)
    if not await conn.fetchval("SELECT to_regclass('prep_inventory.opening_decisions') IS NOT NULL"):
        raise HTTPException(503, 'Prep execution requires the production/opening source boundary migration')
    if not await installed(conn): raise HTTPException(503, 'Prep execution migration is awaiting setup')


class Command(mapping.Strict):
    action: Literal['release', 'reopen', 'complete', 'link', 'finish', 'reconcile']
    draft_version_id: UUID
    task_id: UUID | None = None
    batch_event_id: UUID | None = None
    link_event_id: UUID | None = None
    task_complete: bool | None = Field(default=None, strict=True)
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def evidence(self):
        if self.action in ('complete','link','reconcile'):
            if not self.task_id or not self.batch_event_id: raise ValueError('Completion requires a task and reviewed production batch')
        elif self.action == 'finish':
            if not self.task_id or self.batch_event_id: raise ValueError('Finish selects a task without creating or relinking production')
        elif self.task_id or self.batch_event_id: raise ValueError('Only task commands select production evidence')
        if self.action == 'reconcile':
            if not self.link_event_id or self.task_complete is None: raise ValueError('Reconciliation requires the original production link and explicit task outcome')
        elif self.link_event_id or self.task_complete is not None: raise ValueError('Only reconciliation sets an original link and task outcome')
        return self

    def payload(self):
        # Preserve exact digests and review snapshots of commands saved before this extension.
        return self.model_dump(exclude={'link_event_id','task_complete'} if self.action in ('release','reopen','complete') else set())


async def progress_installed(conn):
    return await conn.fetchval("SELECT to_regprocedure('prep_inventory.task_progress(uuid)') IS NOT NULL")


def event_record(row):
    # Internal acceptance transaction metadata must not alter old reviewed JSON.
    return {k:v for k,v in dict(row).items() if k != 'created_xid'}


class Commit(mapping.Strict):
    command: Command
    expected_review_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    reviewed: Literal[True]

    @field_validator('reviewed', mode='before')
    @classmethod
    def explicit_review(cls, value):
        if value is not True: raise ValueError('Explicitly review this execution command')
        return value


async def state(conn, store, day, track):
    current = await drafts.latest(conn, store, day, track)
    events = []
    if current:
        events = [event_record(r) for r in await conn.fetch('SELECT * FROM prep_inventory.execution_events WHERE list_id=$1 ORDER BY revision', UUID(current['list_id']))]
    phase = next((e for e in reversed(events) if e['action'] in ('release','reopen')), None)
    status = 'released' if phase and phase['action'] == 'release' else 'draft'
    tasks = [] if not current else [dict(r) for r in await conn.fetch('SELECT * FROM prep_inventory.day_tasks WHERE version_id=$1 ORDER BY ordinal', UUID(current['id']))]
    completions = []; progress = []; supported = await progress_installed(conn)
    if supported:
        progress = [await conn.fetchval('SELECT prep_inventory.task_progress($1)', t['id']) for t in tasks]
    for event in events:
        if event['action'] not in ('complete','link'): continue
        effective = await conn.fetchrow('SELECT * FROM prep_inventory.batch_events WHERE root_id=$1 ORDER BY revision DESC LIMIT 1', event['batch_root_id'])
        accepted = next((e for e in reversed(events) if e.get('link_event_id') == event['id']), event)
        completions.append({'execution_id':event['id'], 'task_id':event['task_id'], 'linked_batch_event_id':event['batch_event_id'],
                            'acknowledged_batch_event_id':accepted['batch_event_id'], 'reconciliation_id':accepted['id'] if accepted is not event else None,
                            'effective_batch':dict(effective), 'needs_review':effective['id'] != accepted['batch_event_id']})
    return serial({'store_id':store, 'prep_date':day, 'track':track, 'revision':events[-1]['revision'] if events else 0,
                   'status':status, 'draft_version_id':current['id'] if current else None, 'draft':current,
                   'release':phase if status == 'released' else None, 'tasks':tasks, 'completions':completions, 'history':events,
                   'progress_supported':supported, 'task_progress':progress})


async def preview(conn, store, day, track, body, expected):
    await ready(conn)
    s = await state(conn, store, day, track)
    if s['revision'] != expected: raise HTTPException(409, 'Prep execution changed. Refresh and review the retained command.')
    current = s['draft']
    if not current or current['id'] != str(body.draft_version_id): raise HTTPException(409, 'Select the currently saved dated draft')
    task = batch = original = progress = None
    extended = body.action in ('link','finish','reconcile')
    if extended and not s['progress_supported']: raise HTTPException(503, 'Partial production and reconciliation migration is awaiting setup')
    if body.action == 'release':
        if s['status'] != 'draft': raise HTTPException(409, 'This draft is already released')
        p = await drafts.preview(conn, store, day, drafts.DraftIn(**current['review_snapshot']['inputs']), current['revision'])
        fresh = p['review'] | {'base_revision':current['revision']-1}
        if fingerprint(fresh).hex() != current['review_hash']: raise HTTPException(409, 'Draft sources changed. Save and review a fresh dated draft before release.')
        if fresh['unresolved_tasks']: raise HTTPException(409, 'Unknown task quantities must be resolved before release')
    elif body.action == 'reopen':
        if s['status'] != 'released': raise HTTPException(409, 'Only a released draft can be reopened')
        if s['completions']: raise HTTPException(409, 'Production history is linked. Review task progress independently; the released draft stays pinned.')
    else:
        if s['status'] != 'released': raise HTTPException(409, 'Release this draft before completing a task')
        task = next((t for t in s['tasks'] if t['id'] == str(body.task_id)), None)
        if not task or not task['included'] or task['planned_quantity'] is None or Decimal(task['planned_quantity']) <= 0:
            raise HTTPException(422, 'Select an included task with a positive reviewed planned quantity')
        progress = next((p for p in s['task_progress'] if p['task_id'] == str(body.task_id)), None)
        if extended and progress is None:
            raise HTTPException(409, 'Task progress is incomplete. Refresh and review the current plan.')
        if body.action == 'complete' and any(c['task_id'] == str(body.task_id) for c in s['completions']): raise HTTPException(409, 'This task already has production evidence; use progress and finish commands')
        if body.action in ('link','finish') and (progress['closed'] or progress['needs_review']): raise HTTPException(409, 'Task is finished or has changed production evidence requiring reconciliation')
        if body.action == 'finish':
            try:
                quantity = Decimal(progress.get('reviewed_base_quantity'))
            except (TypeError, ValueError, ArithmeticError):
                raise HTTPException(409, 'Finish requires verified measured production. Refresh and review the task.') from None
            if not quantity.is_finite() or quantity <= 0: raise HTTPException(409, 'Finish requires current reviewed positive production')
        else:
            row = await conn.fetchrow('''SELECT * FROM prep_inventory.batch_events e WHERE id=$1 AND store_id=$2
                AND source_kind='production' AND NOT EXISTS(SELECT 1 FROM prep_inventory.batch_events WHERE predecessor_id=e.id)''', body.batch_event_id, store)
            if not row or str(row['product_id']) != task['product_id'] or row['business_date'] != day:
                raise HTTPException(422, 'Select current production for the prepared product, location and service date')
            batch = serial(dict(row))
            if body.action == 'reconcile':
                original = next((e for e in s['history'] if e['id'] == str(body.link_event_id) and e['action'] in ('complete','link') and e['task_id'] == str(body.task_id)), None)
                linked = next((c for c in s['completions'] if c['execution_id'] == str(body.link_event_id)), None)
                if not original or original['batch_root_id'] != batch['root_id']: raise HTTPException(422, 'Reconcile the same original production root and task')
                if linked is None: raise HTTPException(409, 'Linked production is incomplete. Refresh and review the task.')
                if not linked['needs_review']: raise HTTPException(409, 'This production version is already reviewed')
                if body.task_complete and (row['kind'] == 'void' or any(c['needs_review'] and c['execution_id'] != str(body.link_event_id) for c in s['completions'] if c['task_id'] == str(body.task_id))):
                    raise HTTPException(409, 'A void must reopen the task; other changed production must be reconciled before finishing')
            else:
                if str(row['recipe_version_id']) != task['recipe_version_id'] or row['kind'] == 'void': raise HTTPException(422, 'Select positive production for the pinned task recipe')
                if await conn.fetchval("SELECT 1 FROM prep_inventory.execution_events WHERE batch_root_id=$1 AND action IN ('complete','link')", row['root_id']):
                    raise HTTPException(409, 'This production batch is already linked to a task')
            if row['kind'] != 'void' and (not batch['review_snapshot'].get('usableBaseOutput') or Decimal(batch['review_snapshot']['usableBaseOutput']) <= 0):
                raise HTTPException(422, 'Production must have verified positive measured output')
    review = serial({'store_id':store, 'prep_date':day, 'track':track, 'base_revision':expected, 'command':body.payload(),
                     'draft_review_hash':current['review_hash'], 'release_event_id':s['release']['id'] if s['release'] else None,
                     'task':task, 'batch':batch, 'status_after':'draft' if body.action == 'reopen' else 'released'})
    if extended: review.update(progress_before=progress, original_link=original)
    return {'review':review, 'reviewHash':fingerprint(review).hex()}


async def commit(pool, store, day, track, actor, body, expected, key):
    payload = body.model_dump() | {'command':body.command.payload()}
    digest = fingerprint(serial({'store':store, 'day':day, 'track':track, 'actor':actor, 'expected':expected, 'body':payload}))
    async with pool.acquire() as conn, conn.transaction():
        await ready(conn)
        await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))', str(key))
        await catalog_mapping.lock_catalog(conn); await lock_store(conn, store)
        old = await conn.fetchrow('SELECT * FROM prep_inventory.execution_events WHERE request_key=$1', key)
        if old:
            if old['request_fingerprint'] != digest: raise HTTPException(409, 'Request key belongs to another execution command')
            return serial({'request_key':key, 'event':event_record(old), 'current':await state(conn, store, day, track), 'replayed':True})
        await conn.execute('LOCK TABLE public.items,public.store_items,public.dishes,public.dish_lines,public.prep_items IN SHARE MODE')
        plan = await preview(conn, store, day, track, body.command, expected)
        if plan['reviewHash'] != body.expected_review_hash: raise HTTPException(409, 'Draft or production evidence changed. Review a fresh command.')
        row = await persist(conn, store, body.command, plan, expected, key, digest, actor)
        return serial({'request_key':key, 'event':row, 'current':await state(conn, store, day, track), 'replayed':False})


async def persist(conn, store, command, plan, expected, key, digest, actor):
    p = plan['review']; current = await drafts.latest(conn, store, date.fromisoformat(p['prep_date']), p['track'])
    def uid(value): return UUID(value) if value else None
    extra = ',link_event_id,task_complete' if command.action in ('link','finish','reconcile') else ''
    extra_values = ',$17,$18' if extra else ''
    row = await conn.fetchrow('''INSERT INTO prep_inventory.execution_events(list_id,store_id,revision,predecessor_id,action,draft_version_id,
        release_event_id,task_id,batch_event_id,batch_root_id,reason,actor,review_snapshot,review_hash,request_key,request_fingerprint)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16) RETURNING *'''.replace('request_fingerprint)', 'request_fingerprint'+extra+')').replace('$16)', '$16'+extra_values+')'),
        UUID(current['list_id']), store, expected+1,
        await conn.fetchval('SELECT id FROM prep_inventory.execution_events WHERE list_id=$1 ORDER BY revision DESC LIMIT 1', UUID(current['list_id'])),
        command.action, command.draft_version_id, uid(p['release_event_id']), command.task_id, command.batch_event_id,
        uid(p['batch']['root_id']) if p['batch'] else None, command.reason, actor, p, bytes.fromhex(plan['reviewHash']), key, digest,
        *([command.link_event_id, command.task_complete] if extra else []))
    return serial(event_record(row))


def install_routes(router, context):
    @router.get('/{store_id}/prep-execution/{day}')
    async def read_execution(store_id:str, day:date, request:Request, track:Literal['daily','bulk']='daily'):
        _, pool = await context(request, store_id)
        async with pool.acquire() as conn, conn.transaction(isolation='repeatable_read', readonly=True):
            await ready(conn); return await state(conn, store_id, day, track)

    @router.post('/{store_id}/prep-execution/{day}/preview')
    async def preview_command(store_id:str, day:date, body:Command, request:Request, track:Literal['daily','bulk']='daily'):
        _, pool = await context(request, store_id, True)
        async with pool.acquire() as conn, conn.transaction(isolation='repeatable_read', readonly=True):
            return await preview(conn, store_id, day, track, body, drafts.planning.version(request))

    @router.post('/{store_id}/prep-execution/{day}/commands')
    async def write_command(store_id:str, day:date, body:Commit, request:Request, idempotency_key:UUID=Header(...), track:Literal['daily','bulk']='daily'):
        actor, pool = await context(request, store_id, True)
        return await commit(pool, store_id, day, track, actor, body, drafts.planning.version(request), idempotency_key)
