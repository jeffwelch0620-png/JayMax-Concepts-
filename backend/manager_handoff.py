"""Store-scoped manager production summaries; never production or stock writers."""
import os
import re
import asyncpg
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from purchase_api import serial
from purchase_parser import fingerprint

TABLES = ('store_settings', 'handoff_notes', 'handoff_note_revisions', 'handoff_command_receipts')
TRACK = Literal['daily', 'bulk']
# Match browser String.trim exactly; Python strip also removes extra controls.
TRIM = '\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff'


def version(request):
    raw = request.headers.get('if-match','').strip()
    if not raw: raise HTTPException(428, 'Refresh the handoff note and supply its version')
    if len(raw)>12 or not re.fullmatch(r'(?:[0-9]+|"[0-9]+")',raw) or not 0 <= int(raw.strip('"')) < 2147483647:
        raise HTTPException(422, 'Use a valid handoff revision')
    return int(raw.strip('"'))


class HandoffRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def validated(request):
            try: return await handler(request)
            except RequestValidationError:
                # Do not echo malformed/invalid Unicode note content in errors.
                raise HTTPException(422, 'Use valid handoff fields, dates, revisions and request headers') from None
        return validated


def enabled():
    return os.getenv('MANAGER_HANDOFF_NOTES_ENABLED', 'false').lower() == 'true'


class Command(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['create_draft', 'save_draft', 'submit', 'correct']
    note_id: UUID
    business_date: date
    prep_track: TRACK
    settings_revision: int = Field(gt=0, le=2147483647, strict=True)
    summary: str = Field(min_length=1, max_length=6000)
    next_shift_note: str = Field(default='', max_length=4000)
    reported_readiness: Literal['not_assessed', 'ready', 'action_needed']
    correction_reason: str = Field(default='', max_length=2000)

    @field_validator('business_date', mode='before')
    @classmethod
    def iso_day(cls, value):
        if type(value) is date: return value
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError('Use an ISO business date')
        return value

    @field_validator('summary', 'correction_reason')
    @classmethod
    def trim(cls, value):
        return value.strip(TRIM)

    @model_validator(mode='after')
    def content(self):
        for value in (self.summary, self.next_shift_note, self.correction_reason):
            if '\x00' in value: raise ValueError('NUL is not valid note text')
            try: value.encode('utf-8')
            except UnicodeEncodeError: raise ValueError('Use valid Unicode text') from None
        if not self.summary or ((self.action == 'correct') != bool(self.correction_reason)):
            raise ValueError('Write a summary; only a submitted correction requires a reason')
        return self


async def installed(conn):
    rows = await conn.fetch('''SELECT c.relname,c.relrowsecurity FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='operations' AND c.relname=ANY($1::text[])''', list(TABLES))
    return (len(rows) == len(TABLES) and all(r['relrowsecurity'] for r in rows)
            and await conn.fetchval("""SELECT count(*)=6 FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_proc p ON p.oid=t.tgfoid
                JOIN pg_namespace fn ON fn.oid=p.pronamespace
                WHERE n.nspname='operations' AND fn.nspname='operations' AND NOT p.prosecdef
                AND (tgname,c.relname,p.proname,tgtype) IN (
                    ('handoff_header_guard','handoff_notes','guard_handoff_header',31),
                    ('handoff_revision_guard','handoff_note_revisions','guard_handoff_history',31),
                    ('handoff_receipt_guard','handoff_command_receipts','guard_handoff_history',27),
                    ('handoff_notes_no_truncate','handoff_notes','refuse_handoff_truncate',34),
                    ('handoff_revisions_no_truncate','handoff_note_revisions','refuse_handoff_truncate',34),
                    ('handoff_receipts_no_truncate','handoff_command_receipts','refuse_handoff_truncate',34))
                AND tgenabled IN ('O','A') AND NOT tgisinternal"""))


async def settings(conn, store):
    if not await installed(conn):
        raise HTTPException(503, 'Manager handoff storage is awaiting reviewed installation')
    if not await conn.fetchval('SELECT active FROM public.stores WHERE id=$1', store):
        raise HTTPException(404, 'Restaurant is not available for manager notes')
    row = await conn.fetchrow('SELECT * FROM operations.store_settings WHERE store_id=$1', store)
    try:
        if not row: raise ValueError('missing settings')
        ZoneInfo(row['timezone_name'])
    except (ValueError, ZoneInfoNotFoundError):
        raise HTTPException(503, 'Reviewed store timezone is unavailable') from None
    return dict(row)


async def note(conn, store, note_id):
    row = await conn.fetchrow('''SELECT h.*,v.summary,v.next_shift_note,v.reported_readiness,v.actor_id,v.action,v.correction_reason
        FROM operations.handoff_notes h JOIN operations.handoff_note_revisions v
        ON (v.store_id,v.note_id,v.revision)=(h.store_id,h.id,h.revision)
        WHERE h.store_id=$1 AND h.id=$2''', store, note_id)
    return dict(row) if row else None


def digest(store, actor, body, expected):
    return fingerprint(serial(dict(store=store, actor=actor, expected=expected, command=body.model_dump()))).hex()


def business_today(timezone_name):
    return datetime.now(timezone.utc).astimezone(ZoneInfo(timezone_name)).date()


@asynccontextmanager
async def database_errors():
    try: yield
    except asyncpg.IntegrityConstraintViolationError:
        raise HTTPException(409, 'Handoff identity or context changed; refresh and review the current record') from None
    except asyncpg.PostgresError:
        raise HTTPException(503, 'Handoff storage could not be confirmed; retain the exact request') from None
    except (OSError, TimeoutError, asyncpg.InterfaceError):
        raise HTTPException(503, 'Handoff connection could not be confirmed; retain the exact request') from None


@asynccontextmanager
async def read_connection(pool):
    async with database_errors(), pool.acquire() as conn, conn.transaction(isolation='repeatable_read', readonly=True):
        await conn.execute("SET LOCAL statement_timeout='20s'")
        yield conn


async def day_state(conn, store, day, track):
    config = await settings(conn, store)
    current_id = await conn.fetchval('SELECT id FROM operations.handoff_notes WHERE store_id=$1 AND business_date=$2 AND prep_track=$3', store, day, track)
    previous_id = await conn.fetchval('''SELECT id FROM operations.handoff_notes WHERE store_id=$1 AND business_date<$2
        AND prep_track=$3 AND status='submitted' ORDER BY business_date DESC,id LIMIT 1''', store, day, track)
    return serial(dict(store_id=store, business_date=day, prep_track=track, settings=config,
                       current=await note(conn, store, current_id) if current_id else None,
                       previous=await note(conn, store, previous_id) if previous_id else None))


async def saved(conn, store, actor, key, body, expected):
    receipt = await conn.fetchrow('''SELECT * FROM operations.handoff_command_receipts
        WHERE store_id=$1 AND actor_id=$2 AND request_key=$3''', store, actor, key)
    if not receipt: return None
    if receipt['request_fingerprint'] != digest(store, actor, body, expected):
        raise HTTPException(409, 'This request key belongs to different handoff content')
    accepted = await conn.fetchrow('''SELECT * FROM operations.handoff_note_revisions
        WHERE store_id=$1 AND note_id=$2 AND revision=$3''', store, receipt['note_id'], receipt['accepted_revision'])
    return serial(dict(store_id=store, actor_id=actor, request_key=key, request_fingerprint=receipt['request_fingerprint'],
                       expected_revision=expected, note_id=body.note_id, accepted=dict(accepted),
                       current=await note(conn, store, body.note_id)))


async def execute(pool, store, actor, body, key, expected):
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SET LOCAL lock_timeout='5s'")
        await conn.execute("SET LOCAL statement_timeout='20s'")
        # Also serializes competing creates and same-key requests in this store.
        await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('manager-handoff:'||$1,0))", store)
        config = await settings(conn, store)
        # Capture the reviewed settings revision without granting runtime UPDATE.
        # Any future settings writer must coordinate with this store lock or use
        # a separate drained maintenance window; this module never edits settings.
        replay = await saved(conn, store, actor, key, body, expected)
        if replay: return dict(replay, replayed=True)
        current = await note(conn, store, body.note_id)
        if body.action == 'create_draft':
            if expected != 0 or current: raise HTTPException(409, 'Open the current handoff before editing')
            existing = await conn.fetchval('''SELECT id FROM operations.handoff_notes
                WHERE store_id=$1 AND business_date=$2 AND prep_track=$3''', store, body.business_date, body.prep_track)
            if existing: raise HTTPException(409, 'A note already exists for this store/date/track; refresh to open it')
            if body.settings_revision != config['revision']:
                raise HTTPException(409, 'Store timezone settings changed; refresh before creating the note')
        else:
            if not current: raise HTTPException(404, 'Handoff note not found at this restaurant')
            if current['revision'] != expected or (current['business_date'], current['prep_track'], current['settings_revision']) != (body.business_date, body.prep_track, body.settings_revision):
                raise HTTPException(409, 'Handoff context or revision changed; review the current record')
            if (body.action == 'correct') != (current['status'] == 'submitted'):
                raise HTTPException(409, 'Choose a command for the current draft/submitted status')
            if body.action == 'submit' and any(current[k] != getattr(body, k) for k in ('summary', 'next_shift_note', 'reported_readiness')):
                raise HTTPException(409, 'Save and review the draft before submitting it')
        if body.business_date > business_today(config['timezone_name']):
            raise HTTPException(422, 'A shift summary cannot use a future business date')
        if expected >= 2147483647:
            raise HTTPException(409, 'Handoff revision limit reached; retain and review this record')
        revision = expected + 1
        status = 'submitted' if body.action in ('submit', 'correct') else 'draft'
        if not current:
            await conn.execute('''INSERT INTO operations.handoff_notes(id,store_id,business_date,prep_track,creator_id,timezone_name,settings_revision,revision,status)
                VALUES($1,$2,$3,$4,$5,$6,$7,1,'draft')''', body.note_id, store, body.business_date, body.prep_track, actor, config['timezone_name'], config['revision'])
        else:
            await conn.execute('''UPDATE operations.handoff_notes SET revision=$3,status=$4,updated_at=clock_timestamp(),
                first_submitted_at=CASE WHEN $4='submitted' THEN coalesce(first_submitted_at,clock_timestamp()) ELSE NULL END
                WHERE store_id=$1 AND id=$2''', store, body.note_id, revision, status)
        await conn.execute('''INSERT INTO operations.handoff_note_revisions(store_id,note_id,revision,action,actor_id,status,summary,next_shift_note,reported_readiness,correction_reason)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)''', store, body.note_id, revision, body.action, actor, status,
                           body.summary, body.next_shift_note, body.reported_readiness, body.correction_reason)
        await conn.execute('''INSERT INTO operations.handoff_command_receipts(store_id,actor_id,request_key,request_fingerprint,note_id,accepted_revision)
            VALUES($1,$2,$3,$4,$5,$6)''', store, actor, key, digest(store, actor, body, expected), body.note_id, revision)
        return dict(await saved(conn, store, actor, key, body, expected), replayed=False)


def create_router(pool_factory, authorize):
    router = APIRouter(prefix='/api/pg/operations/{store}/handoff-notes', route_class=HandoffRoute)

    async def context(request, store):
        if not enabled(): raise HTTPException(503, 'Manager handoff notes are not enabled')
        actor = await authorize(request, store)
        return actor, pool_factory()

    @router.get('/days/{day}')
    async def read_day(store: str, day: date, request: Request, track: TRACK = 'bulk'):
        actor, pool = await context(request, store)
        async with read_connection(pool) as conn:
            return dict(await day_state(conn, store, day, track), actor_id=actor)

    @router.get('/notes/{note_id}/history')
    async def history(store: str, note_id: UUID, request: Request, after: int = 0):
        if not 0 <= after <= 2147483647: raise HTTPException(422, 'Use a valid nonnegative history cursor')
        actor, pool = await context(request, store)
        async with read_connection(pool) as conn:
            await settings(conn, store)
            current = await note(conn, store, note_id)
            if not current: raise HTTPException(404, 'Handoff note not found at this restaurant')
            rows = await conn.fetch('''SELECT * FROM operations.handoff_note_revisions
                WHERE store_id=$1 AND note_id=$2 AND revision>$3 ORDER BY revision LIMIT 51''', store, note_id, after)
            return serial(dict(store_id=store, actor_id=actor, note_id=note_id, current_revision=current['revision'],
                               after=after, rows=[dict(r) for r in rows[:50]],
                               next_after=rows[49]['revision'] if len(rows)>50 else None))

    @router.post('/commands')
    async def command(store: str, body: Command, request: Request, idempotency_key: UUID = Header(...)):
        actor, pool = await context(request, store)
        async with database_errors():
            return await execute(pool, store, actor, body, idempotency_key, version(request))

    @router.post('/status')
    async def status(store: str, body: Command, request: Request, idempotency_key: UUID = Header(...)):
        actor, pool = await context(request, store)
        expected = version(request)
        async with read_connection(pool) as conn:
            await settings(conn, store)
            prior = await saved(conn, store, actor, idempotency_key, body, expected)
            if prior: return dict(prior, outcome='saved')
            return serial(dict(store_id=store, actor_id=actor, request_key=idempotency_key, note_id=body.note_id,
                               expected_revision=expected, request_fingerprint=digest(store, actor, body, expected),
                               outcome='unconfirmed', current=await note(conn, store, body.note_id)))
    return router
