"""AM-to-PM manager prep handoff (Jeff 2026-11-11). The morning manager carries one unfinished dated prep
task to a named evening manager, who accepts responsibility for it. A handoff never records production,
changes stock, assigns staff or finishes the task; it reads those facts and records who is responsible.

Rules (decisions 2026-11-01 and 2026-11-11):
- An acceptance is saved only against the prep facts as they are now. If the task, its progress or its
  assignee changes after acceptance, the handoff shows as needing acceptance again.
- Any manager at the store may take a handoff over with a recorded reason (backup coverage), including
  the morning manager covering the evening shift themselves.
- Corrections and withdrawals are new revisions; nothing is deleted.
"""
import hashlib
import json
import re
from datetime import datetime, time
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

import manager_actor
import manager_handoff
import prep_tracks
from native_units import lock_store
from purchase_api import serial
from purchase_parser import fingerprint

TABLES = ('prep_handoffs', 'prep_handoff_revisions', 'prep_handoff_receipts')
SENIOR = {'OWN', 'OPS', 'GM'}
TRIM = manager_handoff.TRIM


def iso_day(value):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value): raise ValueError('Use an ISO business date')
    datetime.strptime(value, '%Y-%m-%d')
    return value


class Command(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['send', 'correct', 'accept', 'take_over', 'withdraw']
    handoff_id: UUID
    business_date: str
    prep_track: prep_tracks.Track
    task_id: UUID
    prep_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    recipient_id: str = Field(default='', max_length=160)
    remaining_base_quantity: Optional[Decimal] = Field(default=None, ge=0, max_digits=24, decimal_places=12)
    ready_by: str = ''
    note: str = Field(default='', max_length=2000)
    reason: str = Field(default='', max_length=1000)

    @field_validator('business_date')
    @classmethod
    def iso_day(cls, value):
        return iso_day(value)

    @field_validator('note', 'reason')
    @classmethod
    def trim(cls, value):
        value = value.strip(TRIM)
        if '\x00' in value: raise ValueError('NUL is not valid text')
        return value

    @model_validator(mode='after')
    def fields_for_action(self):
        details = self.action in ('send', 'correct')
        if details != (self.remaining_base_quantity is not None and bool(self.ready_by) and bool(self.recipient_id)):
            raise ValueError('Send and correct need the recipient, remaining amount and ready-by time; other actions take neither')
        if details and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', self.ready_by):
            raise ValueError('Use a ready-by time as HH:MM')
        if details and not re.fullmatch(r'[A-Za-z0-9_.-]{1,160}', self.recipient_id):
            raise ValueError('Choose a manager login')
        if (self.action in ('correct', 'take_over', 'withdraw')) != bool(self.reason):
            raise ValueError('Correcting, taking over or withdrawing needs a reason; sending and accepting do not')
        if self.action not in ('send', 'correct') and self.note:
            raise ValueError('Only sending or correcting a handoff changes its note')
        return self


def qty(value):
    """One spelling per amount ('256.000000000000' and '256.00' are both '256'), so digests and screens agree."""
    text = format(Decimal(value).normalize(), 'f')
    return '0' if Decimal(text) == 0 else text


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')).hexdigest()


async def installed(conn):
    rows = await conn.fetch('''SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='operations' AND c.relname=ANY($1::text[]) AND c.relrowsecurity''', list(TABLES))
    return len(rows) == len(TABLES)


async def settings(conn, store):
    config = await manager_handoff.settings(conn, store)
    if not await installed(conn):
        raise HTTPException(503, 'Prep handoff storage is awaiting installation')
    return config


# Manager accounts are read through the accounts connection (as manager_actor does), never the inventory
# login, which may be restricted from account tables.
async def account(accounts, actor):
    try: row = await accounts().fetchrow('SELECT id,email,role,position FROM public.app_users WHERE id=$1', actor)
    except Exception: raise HTTPException(503, 'Current manager account could not be confirmed') from None
    if not row: raise HTTPException(403, 'Current manager or owner access required')
    return dict(row)


async def managers(accounts, store):
    """Logins that may receive or take over a handoff at this store: owners and its managers."""
    try:
        rows = await accounts().fetch('''SELECT id,email,role,position FROM public.app_users
            WHERE role='owner' OR (role='manager' AND $1=ANY(locations)) ORDER BY role DESC,email''', manager_actor.RESTAURANTS[store])
    except Exception: raise HTTPException(503, 'Manager accounts could not be confirmed') from None
    return [dict(r) for r in rows]


async def task_facts(conn, store, task_id):
    """What the handoff links to, read fresh: the task, its progress and its current assignee. None when
    the task is not at this store."""
    row = await conn.fetchrow('''SELECT t.id,t.version_id,t.included,t.planned_base_quantity,t.task_snapshot,l.id AS list_id,l.prep_date,l.track,
          EXISTS(SELECT 1 FROM prep_inventory.day_list_versions n WHERE n.predecessor_id=t.version_id) AS superseded,
          (SELECT e.draft_version_id FROM prep_inventory.execution_events e WHERE e.list_id=l.id AND e.action IN ('release','reopen')
            ORDER BY e.revision DESC LIMIT 1) AS phase_version,
          (SELECT e.action FROM prep_inventory.execution_events e WHERE e.list_id=l.id AND e.action IN ('release','reopen')
            ORDER BY e.revision DESC LIMIT 1) AS phase_action,
          (SELECT e.id FROM prep_inventory.execution_events e WHERE e.list_id=l.id AND e.action IN ('release','reopen')
            ORDER BY e.revision DESC LIMIT 1) AS phase_event,
          prep_inventory.task_progress(t.id) AS progress,
          a.revision AS assignment_revision,a.staff_member_id,s.name AS staff_name
        FROM prep_inventory.day_tasks t
        JOIN prep_inventory.day_list_versions v ON v.id=t.version_id
        JOIN prep_inventory.day_lists l ON l.id=v.list_id
        LEFT JOIN LATERAL (SELECT revision,staff_member_id FROM prep_inventory.task_assignments WHERE task_id=t.id ORDER BY revision DESC LIMIT 1) a ON true
        LEFT JOIN public.staff_members s ON s.id=a.staff_member_id
        WHERE t.id=$1 AND t.store_id=$2''', task_id, store)
    if not row: return None
    progress = row['progress'] if isinstance(row['progress'], dict) else json.loads(row['progress'])
    snapshot = row['task_snapshot'] if isinstance(row['task_snapshot'], dict) else json.loads(row['task_snapshot'] or '{}')
    # An unresolved draft task (e.g. a par item still waiting for its count) has no planned amount yet.
    planned = None if progress.get('planned_base_quantity') is None else Decimal(progress['planned_base_quantity'])
    reviewed = Decimal(progress.get('reviewed_base_quantity') or 0)
    released = (row['phase_action'] == 'release' and row['phase_version'] == row['version_id']
                and not row['superseded'] and row['included'] and planned is not None)
    facts = dict(task_id=str(row['id']), business_date=str(row['prep_date']), prep_track=row['track'],
                 name=snapshot.get('name') or 'Prep item', base_unit=snapshot.get('base_unit') or 'unit',
                 planned_base_quantity=None if planned is None else qty(planned),
                 effective_base_quantity=qty(progress.get('effective_base_quantity') or 0), reviewed_base_quantity=qty(reviewed),
                 remaining_base_quantity=None if planned is None else qty(max(planned - reviewed, Decimal(0))),
                 status=progress['status'], closed=bool(progress['closed']), needs_review=bool(progress['needs_review']),
                 # The release event itself, so reopening and releasing again can't revive an earlier acceptance.
                 available=bool(released), release_event_id=str(row['phase_event']) if row['phase_event'] else None,
                 assignment_revision=row['assignment_revision'],
                 assignee=({'id': str(row['staff_member_id']), 'name': row['staff_name']} if row['staff_member_id'] else None))
    return dict(facts, prep_hash=digest(facts))


async def day_tasks(conn, store, day, track):
    ids = await conn.fetch('''SELECT t.id FROM prep_inventory.day_lists l
        JOIN LATERAL (SELECT id FROM prep_inventory.day_list_versions WHERE list_id=l.id ORDER BY revision DESC LIMIT 1) v ON true
        JOIN prep_inventory.day_tasks t ON t.version_id=v.id
        WHERE l.store_id=$1 AND l.prep_date=$2 AND l.track=$3 AND t.included ORDER BY t.ordinal''', store, day, track)
    return [await task_facts(conn, store, r['id']) for r in ids]


async def current(conn, store, handoff_id):
    row = await conn.fetchrow('''SELECT h.id,h.store_id,h.task_id,h.business_date,h.prep_track,h.sender_id,h.revision,h.status,h.created_at,h.updated_at,
          v.action,v.actor_id,v.recorded_at,v.recipient_id,v.remaining_base_quantity,v.base_unit,v.ready_by,v.note,v.reason,v.prep_snapshot,v.prep_hash
        FROM operations.prep_handoffs h JOIN operations.prep_handoff_revisions v
        ON (v.store_id,v.handoff_id,v.revision)=(h.store_id,h.id,h.revision) WHERE h.store_id=$1 AND h.id=$2''', store, handoff_id)
    return dict(row) if row else None


async def accepted_hash(conn, store, handoff_id, revision):
    """The prep facts digest of the acceptance the current revision rests on (None while waiting)."""
    return await conn.fetchval('''SELECT prep_hash FROM operations.prep_handoff_revisions WHERE store_id=$1 AND handoff_id=$2
        AND revision<=$3 AND action IN ('accept','take_over') AND revision>coalesce((SELECT max(revision) FROM operations.prep_handoff_revisions
        WHERE store_id=$1 AND handoff_id=$2 AND revision<=$3 AND action IN ('send','correct')),0) ORDER BY revision DESC LIMIT 1''',
        store, handoff_id, revision)


def label(people, login):
    person = people.get(login)
    return person['email'] if person else 'Former login'


async def view(conn, store, row, people, timezone_name):
    facts = await task_facts(conn, store, row['task_id'])
    live = facts['prep_hash'] if facts else None
    changed = live != row['prep_hash']
    if row['status'] == 'accepted':
        effective = 'needs_acceptance' if live != await accepted_hash(conn, store, row['id'], row['revision']) else 'accepted'
    else:
        effective = row['status']
    return serial(dict(
        id=row['id'], task_id=row['task_id'], business_date=row['business_date'], prep_track=row['prep_track'],
        revision=row['revision'], status=row['status'], effective_status=effective, action=row['action'],
        sender_id=row['sender_id'], sender=label(people, row['sender_id']),
        recipient_id=row['recipient_id'], recipient=label(people, row['recipient_id']),
        actor=label(people, row['actor_id']), recorded_at=row['recorded_at'].isoformat(),
        remaining_base_quantity=qty(row['remaining_base_quantity']), base_unit=row['base_unit'],
        ready_by=row['ready_by'].astimezone(ZoneInfo(timezone_name)).strftime('%H:%M'), note=row['note'], reason=row['reason'],
        recorded_prep=row['prep_snapshot'] if isinstance(row['prep_snapshot'], dict) else json.loads(row['prep_snapshot']),
        current_prep=facts, prep_changed=changed))


async def day_state(conn, accounts, store, day, track, actor):
    config = await settings(conn, store)
    people = {p["id"]: p for p in await managers(accounts, store)}
    me = await account(accounts, actor)
    ids = await conn.fetch('''SELECT id FROM operations.prep_handoffs WHERE store_id=$1 AND business_date=$2 AND prep_track=$3
        ORDER BY created_at,id''', store, day, track)
    handoffs = [await view(conn, store, await current(conn, store, r['id']), people, config['timezone_name']) for r in ids]
    return serial(dict(store_id=store, business_date=day, prep_track=track, timezone_name=config['timezone_name'],
                       actor_id=actor, senior=me['role'] == 'owner' or me['position'] in SENIOR,
                       managers=[{'id': p['id'], 'label': p['email']} for p in people.values()],
                       tasks=await day_tasks(conn, store, day, track), handoffs=handoffs))


def request_digest(store, actor, body, expected):
    return fingerprint(serial(dict(store=store, actor=actor, expected=expected, command=body.model_dump(mode='json')))).hex()


async def replayed(conn, store, actor, key, body, expected):
    receipt = await conn.fetchrow('''SELECT * FROM operations.prep_handoff_receipts WHERE store_id=$1 AND actor_id=$2 AND request_key=$3''',
                                  store, actor, key)
    if not receipt: return None
    if receipt['request_fingerprint'] != request_digest(store, actor, body, expected):
        raise HTTPException(409, 'This request key belongs to a different handoff request')
    return receipt


async def execute(pool, accounts, store, actor, body, key, expected):
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SET LOCAL lock_timeout='5s'")
        await conn.execute("SET LOCAL statement_timeout='20s'")
        # Serializes handoff commands per store, so two managers can't act on the same handoff at once.
        await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('prep-handoff:'||$1,0))", store)
        # The same store row lock the prep writers (execution, assignments, production) take, held until
        # commit, so no prep change can land between reading the facts and saving against them.
        await lock_store(conn, store)
        config = await settings(conn, store)
        people = {p["id"]: p for p in await managers(accounts, store)}
        if await replayed(conn, store, actor, key, body, expected):
            row = await current(conn, store, body.handoff_id)
            return dict(handoff=await view(conn, store, row, people, config['timezone_name']), replayed=True)
        me = await account(accounts, actor)
        senior = me['role'] == 'owner' or me['position'] in SENIOR
        day = datetime.strptime(body.business_date, '%Y-%m-%d').date()
        zone = ZoneInfo(config['timezone_name'])
        if day > manager_handoff.business_today(config['timezone_name']):
            raise HTTPException(422, 'A handoff cannot be for a future business date')
        facts = await task_facts(conn, store, body.task_id)
        if not facts or (facts['business_date'], facts['prep_track']) != (body.business_date, body.prep_track):
            raise HTTPException(404, 'Prep task not found for this restaurant, date and track')
        if facts['prep_hash'] != body.prep_hash:
            raise HTTPException(409, 'The prep task changed since you last refreshed. Review the current amounts and assignee, then try again.')
        row = await current(conn, store, body.handoff_id)
        if body.action == 'send':
            if expected != 0 or row: raise HTTPException(409, 'This handoff already exists; refresh to open it')
            if not facts['available'] or facts['closed']:
                raise HTTPException(409, 'Only a released, unfinished prep task can be handed off')
            if await conn.fetchval("SELECT 1 FROM operations.prep_handoffs WHERE task_id=$1 AND status<>'withdrawn'", body.task_id):
                raise HTTPException(409, 'This prep task already has an open handoff; refresh to see it')
        else:
            if not row or (str(row['task_id']), str(row['business_date']), row['prep_track']) != (str(body.task_id), body.business_date, body.prep_track):
                raise HTTPException(404, 'Handoff not found for this restaurant, date and track')
            if row['revision'] != expected:
                raise HTTPException(409, 'The handoff changed since you last refreshed; review the current version')
            if row['status'] == 'withdrawn': raise HTTPException(409, 'This handoff was withdrawn')
        if body.action in ('send', 'correct'):
            if body.recipient_id not in people:
                raise HTTPException(422, 'Choose a manager or owner with access to this restaurant')
            if body.recipient_id == actor:
                raise HTTPException(422, 'Name the evening manager. To cover the evening yourself, send it to them and take it over with a reason.')
            if body.action == 'correct' and not (actor == row['sender_id'] or senior):
                raise HTTPException(403, 'Only the sending manager, a GM or an owner can correct this handoff')
            recipient, remaining, base_unit = body.recipient_id, body.remaining_base_quantity, facts['base_unit']
            ready_by = datetime.combine(day, time.fromisoformat(body.ready_by), zone)
            note, status = body.note, 'waiting'
        else:
            recipient, remaining, base_unit = row['recipient_id'], row['remaining_base_quantity'], row['base_unit']
            ready_by, note = row['ready_by'], row['note']
            if body.action == 'accept':
                if actor != row['recipient_id']:
                    raise HTTPException(403, 'Only the named manager can accept. Another manager can take it over with a reason.')
                if row['status'] == 'accepted' and facts['prep_hash'] == await accepted_hash(conn, store, row['id'], row['revision']):
                    raise HTTPException(409, 'You already accepted this handoff and the prep has not changed')
                if not facts['available']:
                    raise HTTPException(409, 'The linked prep task is no longer released; ask the sending manager to correct or withdraw the handoff')
                status = 'accepted'
            elif body.action == 'take_over':
                if actor not in people: raise HTTPException(403, 'Current manager or owner access required')
                if not facts['available']:
                    raise HTTPException(409, 'The linked prep task is no longer released; ask the sending manager to correct or withdraw the handoff')
                if actor == row['recipient_id'] and row['status'] == 'waiting':
                    raise HTTPException(409, 'You are the named manager; accept the handoff instead')
                recipient, status = actor, 'accepted'
            else:
                if not (actor == row['sender_id'] or senior):
                    raise HTTPException(403, 'Only the sending manager, a GM or an owner can withdraw this handoff')
                status = 'withdrawn'
        revision = expected + 1
        prep_snapshot = {k: v for k, v in facts.items() if k != 'prep_hash'}
        if body.action == 'send':
            await conn.execute('''INSERT INTO operations.prep_handoffs(id,store_id,task_id,business_date,prep_track,sender_id,revision,status)
                VALUES($1,$2,$3,$4,$5,$6,1,'waiting')''', body.handoff_id, store, body.task_id, day, body.prep_track, actor)
        else:
            await conn.execute('''UPDATE operations.prep_handoffs SET revision=$3,status=$4,updated_at=clock_timestamp()
                WHERE store_id=$1 AND id=$2''', store, body.handoff_id, revision, status)
        await conn.execute('''INSERT INTO operations.prep_handoff_revisions(store_id,handoff_id,revision,action,actor_id,status,recipient_id,
              remaining_base_quantity,base_unit,ready_by,note,reason,prep_snapshot,prep_hash)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb,$14)''', store, body.handoff_id, revision, body.action, actor, status,
                           recipient, remaining, base_unit, ready_by, note, body.reason, json.dumps(prep_snapshot), facts['prep_hash'])
        await conn.execute('''INSERT INTO operations.prep_handoff_receipts(store_id,actor_id,request_key,request_fingerprint,handoff_id,accepted_revision)
            VALUES($1,$2,$3,$4,$5,$6)''', store, actor, key, request_digest(store, actor, body, expected), body.handoff_id, revision)
        return dict(handoff=await view(conn, store, await current(conn, store, body.handoff_id), people, config['timezone_name']), replayed=False)


def create_router(pool_factory, authorize, accounts):
    router = APIRouter(prefix='/api/pg/operations/{store}/prep-handoffs', route_class=manager_handoff.HandoffRoute)

    async def context(request, store):
        if not manager_handoff.enabled(): raise HTTPException(503, 'Manager handoff is not enabled')
        return await authorize(request, store), pool_factory()

    @router.get('/days/{day}')
    async def read_day(store: str, day: str, request: Request, track: prep_tracks.Track = 'daily'):
        prep_tracks.check(store, track)
        try: iso_day(day)
        except ValueError: raise HTTPException(422, 'Use an ISO business date') from None
        actor, pool = await context(request, store)
        async with manager_handoff.read_connection(pool) as conn:
            return await day_state(conn, accounts, store, datetime.strptime(day, '%Y-%m-%d').date(), track, actor)

    @router.get('/handoffs/{handoff_id}/history')
    async def history(store: str, handoff_id: UUID, request: Request):
        actor, pool = await context(request, store)
        async with manager_handoff.read_connection(pool) as conn:
            config = await settings(conn, store)
            if not await current(conn, store, handoff_id): raise HTTPException(404, 'Handoff not found at this restaurant')
            people = {p["id"]: p for p in await managers(accounts, store)}
            rows = await conn.fetch('''SELECT * FROM operations.prep_handoff_revisions WHERE store_id=$1 AND handoff_id=$2
                ORDER BY revision LIMIT 200''', store, handoff_id)
            zone = ZoneInfo(config['timezone_name'])
            return serial(dict(store_id=store, actor_id=actor, handoff_id=handoff_id, rows=[dict(
                revision=r['revision'], action=r['action'], actor=label(people, r['actor_id']), recorded_at=r['recorded_at'].isoformat(),
                status=r['status'], recipient=label(people, r['recipient_id']), remaining_base_quantity=qty(r['remaining_base_quantity']),
                base_unit=r['base_unit'], ready_by=r['ready_by'].astimezone(zone).strftime('%H:%M'), note=r['note'], reason=r['reason'])
                for r in rows]))

    @router.post('/commands')
    async def command(store: str, body: Command, request: Request, idempotency_key: UUID = Header(...)):
        prep_tracks.check(store, body.prep_track)
        actor, pool = await context(request, store)
        async with manager_handoff.database_errors():
            return await execute(pool, accounts, store, actor, body, idempotency_key, manager_handoff.version(request))
    return router
