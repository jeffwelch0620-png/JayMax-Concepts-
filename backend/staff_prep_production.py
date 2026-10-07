"""Claimed staff measurements awaiting atomic manager production acceptance."""
import os
from datetime import date
from typing import Literal
from uuid import UUID, uuid4, uuid5
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import Field, field_validator, model_validator
import staff_prep_tasks as tasks
import prep_batches as batches
import prep_execution as execution
import catalog_mapping
from staff_prep_counts import Reviewed, Credentials
from native_units import lock_store
from purchase_api import serial
from purchase_parser import fingerprint


class MeasuredBatch(batches.BatchIn):
    @field_validator('calendar_date_confirmed', 'single_output_confirmed', mode='before')
    @classmethod
    def explicit(cls, value):
        if value is not True: raise ValueError('Explicit measurement boundary confirmation is required')
        return value


class Submission(tasks.mapping.Strict):
    root_id: UUID
    expected_revision: int = Field(ge=0, strict=True)
    task_id: UUID
    staff_member_id: UUID
    assignment_id: UUID
    kind: Literal['submit', 'withdraw'] = 'submit'
    batch: MeasuredBatch | None = None
    note: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def shape(self):
        if (self.kind == 'submit') != (self.batch is not None): raise ValueError('Submit includes a full measured batch; withdrawal has none')
        if self.kind == 'withdraw' and self.expected_revision == 0: raise ValueError('Withdrawal requires an existing submission')
        return self


class StaffPreview(Credentials):
    submission: Submission


class StaffCommit(StaffPreview, Reviewed):
    expected_review_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


class Decision(tasks.mapping.Strict):
    submission_id: UUID
    decision: Literal['accepted', 'rejected']
    task_complete: bool = Field(strict=True)
    note: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def shape(self):
        if self.decision == 'rejected' and self.task_complete: raise ValueError('Rejection cannot finish a task')
        return self


class DecisionCommit(Decision, Reviewed):
    expected_review_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


async def ready(conn):
    if os.getenv('STAFF_PREP_PRODUCTION_ENABLED','false').lower()!='true': raise HTTPException(503,'Staff production awaits enablement')
    await tasks.ready(conn)
    if not await conn.fetchval("SELECT to_regclass('prep_inventory.staff_production_decisions') IS NOT NULL"):
        raise HTTPException(503, 'Staff production awaits additive schema setup')


async def history(conn, root, store):
    events = serial([dict(r) for r in await conn.fetch('SELECT * FROM prep_inventory.staff_production_submissions WHERE root_id=$1 AND store_id=$2 ORDER BY revision', root,store)])
    decisions = serial([dict(r) for r in await conn.fetch('''SELECT d.* FROM prep_inventory.staff_production_decisions d
        JOIN prep_inventory.staff_production_submissions s ON s.id=d.submission_id WHERE s.root_id=$1 AND s.store_id=$2 ORDER BY s.revision''',root,store)])
    return dict(root_id=str(root), events=events, decisions=decisions)


async def state(conn,store,day,track,member=None):
    await ready(conn)
    roots=await conn.fetch('''SELECT DISTINCT s.root_id FROM prep_inventory.staff_production_submissions s
        JOIN prep_inventory.day_tasks t ON t.id=s.task_id JOIN prep_inventory.day_list_versions v ON v.id=t.version_id
        JOIN prep_inventory.day_lists l ON l.id=v.list_id WHERE s.store_id=$1 AND l.prep_date=$2 AND l.track=$3
        AND ($4::uuid IS NULL OR s.staff_member_id=$4) ORDER BY s.root_id''',store,day,track,member)
    return dict(store_id=store,day=str(day),track=track,selected_member_id=str(member) if member else None,
        submissions=[await history(conn,r['root_id'],store) for r in roots], accountingEffect='none')


async def current_assignment(conn,store,day,track,body):
    s=await tasks.state(conn,store,day,track); e=s['execution']
    task=next((t for t in e['tasks'] if t['id']==str(body.task_id)),None)
    a=next((a for a in s['assignments'] if a['task_id']==str(body.task_id)),None)
    progress=next((p for p in e['task_progress'] if p['task_id']==str(body.task_id)),None)
    if e['status']!='released' or not task or not task['included'] or not progress or progress['closed'] or progress['needs_review']:
        raise HTTPException(409,'Submit only for an open current released task with reviewed production')
    if not a or not a['current'] or a['current']['id']!=str(body.assignment_id) or a['current']['staff_member_id']!=str(body.staff_member_id):
        raise HTTPException(409,'Assignment changed; review the currently assigned task')
    if a['roster_changed'] or not a['current_member'] or not a['current_member']['active']:
        raise HTTPException(409,'Roster changed; manager must review the assignment')
    return e,task,a,progress


async def submission_preview(conn,store,day,track,body,actor,kind):
    await ready(conn)
    h=await history(conn,body.root_id,store); old=h['events'][-1] if h['events'] else None
    if body.expected_revision!=(old['revision'] if old else 0): raise HTTPException(409,'Submission revision changed; refresh the retained draft')
    if old:
        if old['review_snapshot']['day']!=str(day) or old['review_snapshot']['track']!=track: raise HTTPException(422,'A revision keeps its original calendar date and track')
        if old['task_id']!=str(body.task_id) or old['staff_member_id']!=str(body.staff_member_id): raise HTTPException(422,'A revision keeps its original task and claimed staff identity')
        if old['kind']=='withdraw' or any(d['decision']=='accepted' for d in h['decisions']): raise HTTPException(409,'Withdrawn or accepted production cannot be revised by staff')
        if body.kind=='withdraw' and any(d['submission_id']==old['id'] for d in h['decisions']): raise HTTPException(409,'Decided submission cannot be withdrawn')
    member=await conn.fetchrow('SELECT id FROM staff_members WHERE id=$1 AND store_id=$2 AND active',body.staff_member_id,store)
    if not member: raise HTTPException(422,'Select active roster staff at this location')
    if body.kind=='submit':
        e,t,a,progress=await current_assignment(conn,store,day,track,body)
        if body.batch.recipe_version_id!=UUID(t['recipe_version_id']) or body.batch.business_date!=day: raise HTTPException(422,'Measured production must use the task recipe and selected calendar date')
        p=await batches.preview(conn,store,body.batch)
        sources=dict(task=t,assignment=a['current'],member=a['current_member'],execution_revision=e['revision'],release_event_id=e['release']['id'],progress=progress)
    else:
        if old['assignment_id']!=str(body.assignment_id): raise HTTPException(422,'Withdrawal keeps the original assignment')
        p=None; sources=old['review_snapshot']['sources']
    review=serial(dict(store_id=store,day=day,track=track,submission=body.model_dump(mode='json'),predecessor_id=old['id'] if old else None,
        submitted_by=actor,credential_kind=kind,identity_verified=False,sources=sources,batch=p,
        accountingEffect='none',productionEffect='none'))
    return dict(review=review,reviewHash=fingerprint(review).hex())


async def coordinated(conn,store,key):
    await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))',str(key))
    await catalog_mapping.lock_catalog(conn); await lock_store(conn,store)
    await conn.execute('LOCK TABLE public.staff_members,public.items,public.store_items,public.dishes,public.dish_lines,public.prep_items IN SHARE MODE')


async def submit(pool,store,day,track,actor,kind,body,key):
    digest=fingerprint(serial(dict(store=store,day=day,track=track,actor=actor,kind=kind,body=body.model_dump(mode='json',exclude={'pin'}))))
    async with pool.acquire() as conn,conn.transaction():
        await ready(conn);await coordinated(conn,store,key)
        old=await conn.fetchrow('SELECT * FROM prep_inventory.staff_production_submissions WHERE request_key=$1',key)
        if old:
            if old['request_fingerprint']!=digest: raise HTTPException(409,'Request key belongs to another submission or actor')
            row=serial(dict(old));replayed=True
        else:
            p=await submission_preview(conn,store,day,track,body.submission,actor,kind)
            if p['reviewHash']!=body.expected_review_hash: raise HTTPException(409,'Assignment, recipe or measured source changed since review')
            b=body.submission;r=p['review']
            row=serial(dict(await conn.fetchrow('''INSERT INTO prep_inventory.staff_production_submissions(id,store_id,root_id,revision,predecessor_id,
                task_id,staff_member_id,assignment_id,kind,note,submitted_by,credential_kind,review_snapshot,review_hash,request_key,request_fingerprint)
                VALUES($16,$1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15) RETURNING *''',store,b.root_id,b.expected_revision+1,
                UUID(r['predecessor_id']) if r['predecessor_id'] else None,b.task_id,b.staff_member_id,b.assignment_id,b.kind,b.note,actor,kind,r,bytes.fromhex(p['reviewHash']),key,digest,b.root_id if b.expected_revision==0 else uuid4())))
            await conn.execute('UPDATE store_state SET revision=revision+1 WHERE store_id=$1',store);replayed=False
        return dict(submission=row,history=await history(conn,UUID(row['root_id']),store),replayed=replayed,productionEffect='none')


async def decision_preview(conn,store,day,track,body):
    await ready(conn)
    row=await conn.fetchrow('SELECT * FROM prep_inventory.staff_production_submissions WHERE id=$1 AND store_id=$2',body.submission_id,store)
    if not row or row['review_snapshot']['day']!=str(day) or row['review_snapshot']['track']!=track: raise HTTPException(422,'Select submission at this date, track and location')
    if row['kind']!='submit' or await conn.fetchval('SELECT 1 FROM prep_inventory.staff_production_submissions WHERE predecessor_id=$1',row['id']) or await conn.fetchval('SELECT 1 FROM prep_inventory.staff_production_decisions WHERE submission_id=$1',row['id']):
        raise HTTPException(409,'Select a current undecided production submission')
    s=serial(dict(row)); batch=None; sources=None
    if body.decision=='accepted':
        b=Submission(**s['review_snapshot']['submission']);e,t,a,progress=await current_assignment(conn,store,day,track,b)
        batch=await batches.preview(conn,store,b.batch)
        batch['review']['staff_submission_id']=s['id']
        batch['reviewHash']=fingerprint(batch['review']).hex()
        sources=dict(task=t,assignment=a['current'],execution_revision=e['revision'],release_event_id=e['release']['id'],progress=progress)
    review=serial(dict(store_id=store,day=day,track=track,decision=body.model_dump(mode='json'),submission=s,sources=sources,batch=batch,
        accountingEffect='none',productionEffect='record_once' if batch else 'none'))
    return dict(review=review,reviewHash=fingerprint(review).hex())


async def decision_result(conn,row,store,day,track,replayed):
    def event(table,key): return conn.fetchrow('SELECT * FROM prep_inventory.'+table+' WHERE id=$1',row[key]) if row[key] else None
    batch=await event('batch_events','batch_event_id') if row['batch_event_id'] else None
    link=await event('execution_events','execution_event_id') if row['execution_event_id'] else None
    finish=await event('execution_events','finish_event_id') if row['finish_event_id'] else None
    root=await conn.fetchval('SELECT root_id FROM prep_inventory.staff_production_submissions WHERE id=$1',row['submission_id'])
    return serial(dict(decision=dict(row),batch_event=dict(batch) if batch else None,execution_event=execution.event_record(link) if link else None,
        finish_event=execution.event_record(finish) if finish else None,history=await history(conn,root,store),current=await tasks.state(conn,store,day,track),replayed=replayed))


async def decide(pool,store,day,track,actor,body,key):
    digest=fingerprint(serial(dict(store=store,day=day,track=track,actor=actor,body=body.model_dump(mode='json'))))
    async with pool.acquire() as conn,conn.transaction():
        await ready(conn);await coordinated(conn,store,key)
        old=await conn.fetchrow('SELECT * FROM prep_inventory.staff_production_decisions WHERE request_key=$1',key)
        if old:
            if old['request_fingerprint']!=digest: raise HTTPException(409,'Request key belongs to another decision or actor')
            return await decision_result(conn,old,store,day,track,True)
        command=Decision(**body.model_dump(exclude={'expected_review_hash','reviewed'}));p=await decision_preview(conn,store,day,track,command)
        if p['reviewHash']!=body.expected_review_hash: raise HTTPException(409,'Submission, assignment or production changed since review')
        batch=link=finish=None
        if body.decision=='accepted':
            batch=(await batches.persist(conn,store,p['review']['batch'],key,digest,actor))['event']
            source=p['review']['sources'];draft=UUID(source['task']['version_id']);revision=source['execution_revision']
            cmd=execution.Command(action='link',draft_version_id=draft,task_id=UUID(source['task']['id']),batch_event_id=UUID(batch['id']),reason=body.note)
            lp=await execution.preview(conn,store,day,track,cmd,revision)
            lp['review']['staff_submission_id']=str(body.submission_id);lp['reviewHash']=fingerprint(lp['review']).hex()
            link=await execution.persist(conn,store,cmd,lp,revision,key,digest,actor)
            if body.task_complete:
                cmd=execution.Command(action='finish',draft_version_id=draft,task_id=UUID(source['task']['id']),reason=body.note)
                fp=await execution.preview(conn,store,day,track,cmd,revision+1)
                fp['review']['staff_submission_id']=str(body.submission_id);fp['reviewHash']=fingerprint(fp['review']).hex()
                finish=await execution.persist(conn,store,cmd,fp,revision+1,uuid5(key,'staff-production-finish'),digest,actor)
        row=await conn.fetchrow('''INSERT INTO prep_inventory.staff_production_decisions(store_id,submission_id,decision,task_complete,note,
            recorded_by,review_snapshot,review_hash,batch_event_id,execution_event_id,finish_event_id,request_key,request_fingerprint)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13) RETURNING *''',store,body.submission_id,body.decision,body.task_complete,
            body.note,actor,p['review'],bytes.fromhex(p['reviewHash']),UUID(batch['id']) if batch else None,UUID(link['id']) if link else None,
            UUID(finish['id']) if finish else None,key,digest)
        if body.decision=='rejected':await conn.execute('UPDATE store_state SET revision=revision+1 WHERE store_id=$1',store)
        return await decision_result(conn,row,store,day,track,False)


def create_router(pool_factory,store_check,manager_authorize,staff_authorize):
    router=APIRouter();base='/api/pg/purchases/{store}/staff-prep-production/{day}';staff='/api/pg/staff/{store}/prep-production/{day}'
    @router.get(base)
    async def read(store:str,day:date,request:Request,track:Literal['daily','bulk']='daily'):
        store_check(store);manager_authorize(request,store,False)
        async with pool_factory().acquire() as c,c.transaction(isolation='repeatable_read',readonly=True):return await state(c,store,day,track)
    @router.post(base+'/preview')
    async def review(store:str,day:date,request:Request,body:Decision,track:Literal['daily','bulk']='daily'):
        store_check(store);manager_authorize(request,store,True)
        async with pool_factory().acquire() as c,c.transaction(isolation='repeatable_read',readonly=True):return await decision_preview(c,store,day,track,body)
    @router.post(base+'/decisions')
    async def decision(store:str,day:date,request:Request,body:DecisionCommit,idempotency_key:UUID=Header(...),track:Literal['daily','bulk']='daily'):
        store_check(store);actor=manager_authorize(request,store,True)
        return await decide(pool_factory(),store,day,track,actor,body,idempotency_key)
    @router.post(staff+'/setup')
    async def staff_setup(store:str,day:date,request:Request,body:Credentials,staff_member_id:UUID,track:Literal['daily','bulk']='daily'):
        store_check(store)
        async with pool_factory().acquire() as c,c.transaction(isolation='repeatable_read',readonly=True):
            await ready(c);_,kind=await staff_authorize(request,c,store,body.pin)
            if not await c.fetchval('SELECT 1 FROM staff_members WHERE id=$1 AND store_id=$2 AND active',staff_member_id,store): raise HTTPException(422,'Select active roster staff at this location')
            return dict(await state(c,store,day,track,staff_member_id),setup=await batches.setup(c,store),credential_kind=kind,identity_verified=False)
    @router.post(staff+'/preview')
    async def staff_review(store:str,day:date,request:Request,body:StaffPreview,track:Literal['daily','bulk']='daily'):
        store_check(store)
        async with pool_factory().acquire() as c,c.transaction(isolation='repeatable_read',readonly=True):
            await ready(c);actor,kind=await staff_authorize(request,c,store,body.pin)
            return await submission_preview(c,store,day,track,body.submission,actor,kind)
    @router.post(staff+'/submissions')
    async def staff_submit(store:str,day:date,request:Request,body:StaffCommit,idempotency_key:UUID=Header(...),track:Literal['daily','bulk']='daily'):
        store_check(store)
        async with pool_factory().acquire() as c:
            await ready(c);actor,kind=await staff_authorize(request,c,store,body.pin)
        return await submit(pool_factory(),store,day,track,actor,kind,body,idempotency_key)
    return router
