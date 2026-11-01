"""Personal staff sign-in: own name and PIN (Jeff 2026-10-30; safeguards confirmed 2026-10-31).

An employee types their name (matches appear after 2 letters; the roster is never listed) and
enters a 4-5 digit PIN. An owner or the Ops Lead issues a temporary PIN, which the employee
replaces at first sign-in. 5 wrong PINs since the last sign-in, unlock or new PIN lock that person
for 15 minutes after the last one; a manager or above can unlock. A session ends after 12 hours or
30 minutes idle, on sign-out, on a new PIN, or when the person is made inactive. When
STAFF_PERSONAL_LOGIN_ENABLED is on, the shared store PIN is retired at every store at once.
migrations/20261101_staff_personal_login.sql holds the tables.
"""
import asyncio
import base64
import hashlib
import hmac
import os
import secrets
import tempfile
from datetime import timedelta
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import Field

import prep_mapping as mapping
import staff_pin_security
from purchase_api import serial
from purchase_parser import fingerprint

PIN = r'^[0-9]{4,5}$'
LOCK_AFTER, LOCK_MINUTES = 5, 15
SESSION_HOURS, IDLE_MINUTES = 12, 30
ITERATIONS = 240000
STORE_ZONE = ZoneInfo('America/New_York')  # all three stores are in Eastern Tennessee
RETIRED = 'The store PIN is retired. Sign in with your own name and PIN.'
# Wrong PINs across a whole store, on top of each person's lockout, so cycling through names is slow.
store_limiter = staff_pin_security.PinAttemptLimiter(Path(tempfile.gettempdir()) / 'jaymax-staff-pin' / 'personal.sqlite3', limit=30, window=60)


def enabled():
    return os.getenv('STAFF_PERSONAL_LOGIN_ENABLED', 'false').lower() == 'true'


async def installed(conn):
    return await conn.fetchval("SELECT to_regclass('prep_inventory.staff_sessions') IS NOT NULL")


async def setup_ready(conn):
    """PINs can be issued and unlocked once the migration is in, before sign-in is switched on."""
    if not await installed(conn): raise HTTPException(503, 'Personal staff sign-in migration is awaiting setup')


async def ready(conn):
    if not enabled(): raise HTTPException(503, 'Personal staff sign-in is not switched on')
    await setup_ready(conn)


def _b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode()


def pin_hash(pin, salt=None):
    salt = salt or secrets.token_bytes(16)
    return f"pbkdf2${_b64(salt)}${hashlib.pbkdf2_hmac('sha256', pin.encode(), salt, ITERATIONS).hex()}"


def pin_ok(pin, stored):
    try:
        _, salt, digest = stored.split('$', 2)
        salt = base64.urlsafe_b64decode(salt + '=' * (-len(salt) % 4))
        return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256', pin.encode(), salt, ITERATIONS).hex(), digest)
    except (ValueError, TypeError):
        return False


def acting_member(actor, member_id):
    """A personal session acts only as its own person (Jeff 2026-10-30). Returns whether the named
    person is verified: true for their own session, false for a shared PIN or a manager login."""
    if not str(actor).startswith('member:'): return False
    if member_id is not None and str(member_id) != str(actor).removeprefix('member:'):
        raise HTTPException(403, 'Signed-in staff can only act as themselves')
    return member_id is not None


class SignIn(mapping.Strict):
    staff_member_id: UUID
    pin: str = Field(pattern=PIN)
    new_pin: str | None = Field(default=None, pattern=PIN)   # required when signing in with a temporary PIN


class IssuePin(mapping.Strict):
    pin: str = Field(pattern=PIN)


async def lock_state(conn, member_id):
    """When the person's lockout ends, or None if they are not locked."""
    row = await conn.fetchrow('''WITH reset AS (SELECT greatest(
            coalesce((SELECT max(at) FROM prep_inventory.staff_sign_in_events WHERE staff_member_id=$1 AND kind IN ('signed_in','unlocked')), '-infinity'),
            coalesce((SELECT max(set_at) FROM prep_inventory.staff_member_pins WHERE staff_member_id=$1), '-infinity')) AS at)
        SELECT count(*) AS wrong, max(e.at) AS last FROM prep_inventory.staff_sign_in_events e, reset
        WHERE e.staff_member_id=$1 AND e.kind='failed' AND e.at > reset.at''', member_id)
    if row['wrong'] < LOCK_AFTER: return None
    until = row['last'] + timedelta(minutes=LOCK_MINUTES)
    return until if until > await conn.fetchval('SELECT clock_timestamp()') else None


async def replaced_first_pin(conn, member_id, current, body):
    """A retry of the first-PIN change whose reply was lost: the first PIN was already replaced by this
    new PIN, so it signs in instead of counting as a wrong PIN."""
    if not body.new_pin or current['temporary'] or current['set_by'] != f'member:{member_id}': return False
    previous = await conn.fetchrow('''SELECT * FROM prep_inventory.staff_member_pins WHERE staff_member_id=$1 AND set_at < $2
        ORDER BY set_at DESC LIMIT 1''', member_id, current['set_at'])
    return bool(previous and previous['temporary']
                and await asyncio.to_thread(pin_ok, body.new_pin, current['pin_hash'])
                and await asyncio.to_thread(pin_ok, body.pin, previous['pin_hash']))


async def current_pin(conn, member_id):
    return await conn.fetchrow('SELECT * FROM prep_inventory.staff_member_pins WHERE staff_member_id=$1 ORDER BY set_at DESC LIMIT 1', member_id)


async def end_sessions(conn, member_id, reason):
    await conn.execute('''UPDATE prep_inventory.staff_sessions SET ended_at=clock_timestamp(), end_reason=$2
        WHERE staff_member_id=$1 AND ended_at IS NULL''', member_id, reason)


def locked(until):
    return HTTPException(423, f"Too many wrong PINs. Try again after {until.astimezone(STORE_ZONE).strftime('%H:%M')}, or ask a manager to unlock you.")


async def names(conn, store, q):
    """Active names at the store with a word starting with what was typed (2 letters or more)."""
    await ready(conn)
    q = ' '.join(q.split()).casefold()
    if len(q) < 2: return []
    pattern = q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
    rows = await conn.fetch(r'''SELECT id, name FROM public.staff_members WHERE store_id=$1 AND active
        AND (lower(name) LIKE $2 OR lower(name) LIKE '% ' || $2) ORDER BY name LIMIT 8''', store, pattern)
    return [{'id': str(r['id']), 'name': r['name']} for r in rows]


async def sign_in(pool, store, body, mint):
    """Check the PIN and start a session."""
    ticket = await asyncio.to_thread(store_limiter.reserve, staff_pin_security.store_key(store))
    try:
        session, member = await _check(pool, store, body)
    except HTTPException as e:
        # A correct PIN (still to be replaced) doesn't spend the store's wrong-PIN budget.
        if getattr(e, 'pin_correct', False): await asyncio.to_thread(store_limiter.refund, ticket)
        raise
    await asyncio.to_thread(store_limiter.refund, ticket)
    token = mint({'sub': f"member:{member['id']}", 'email': f"member:{member['id']}", 'role': 'staff', 'kind': 'staff',
                  'sid': str(session['id']), 'store': store, 'exp': int(session['expires_at'].timestamp())})
    return {'token': token, 'staff_member_id': str(member['id']), 'name': member['name'], 'store_id': store,
            'expires_at': session['expires_at'].isoformat(), 'idle_minutes': IDLE_MINUTES}


def _correct(error):
    error.pin_correct = True
    return error


async def _check(pool, store, body):
    # A wrong PIN is committed before the request fails, so it counts toward the lockout.
    refused = None
    async with pool.acquire() as conn, conn.transaction():
        await ready(conn)
        member = await conn.fetchrow('SELECT id, name, active FROM public.staff_members WHERE id=$1 AND store_id=$2 FOR UPDATE',
                                     body.staff_member_id, store)
        if not member or not member['active']: raise HTTPException(401, 'Name or PIN not recognised')
        until = await lock_state(conn, member['id'])
        if until: raise locked(until)
        current = await current_pin(conn, member['id'])
        if not current: raise HTTPException(403, 'You have no PIN yet. Ask an owner or the Ops Lead to issue one.')
        if await replaced_first_pin(conn, member['id'], current, body):
            current, body = dict(current) | {'temporary': False}, body.model_copy(update={'pin': body.new_pin, 'new_pin': None})
        if not await asyncio.to_thread(pin_ok, body.pin, current['pin_hash']):
            await conn.execute("INSERT INTO prep_inventory.staff_sign_in_events(store_id,staff_member_id,kind,actor) VALUES($1,$2,'failed','sign-in')",
                               store, member['id'])
            until = await lock_state(conn, member['id'])
            refused = locked(until) if until else HTTPException(401, 'Name or PIN not recognised')
        else:
            if current['temporary']:
                if not body.new_pin:
                    raise _correct(HTTPException(409, {'code': 'pin_change_required', 'message': 'Choose your own PIN to finish signing in.'}))
                if body.new_pin == body.pin: raise _correct(HTTPException(422, 'Choose a PIN different from the one you were given'))
                await conn.execute('''INSERT INTO prep_inventory.staff_member_pins(store_id,staff_member_id,pin_hash,temporary,set_by)
                    VALUES($1,$2,$3,false,$4)''', store, member['id'], await asyncio.to_thread(pin_hash, body.new_pin), f"member:{member['id']}")
            await conn.execute("INSERT INTO prep_inventory.staff_sign_in_events(store_id,staff_member_id,kind,actor) VALUES($1,$2,'signed_in','sign-in')",
                               store, member['id'])
            session = await conn.fetchrow('''INSERT INTO prep_inventory.staff_sessions(store_id,staff_member_id,expires_at)
                VALUES($1,$2,clock_timestamp() + make_interval(hours => $3)) RETURNING *''', store, member['id'], SESSION_HOURS)
    if refused: raise refused
    return session, member


async def check_session(pool, user):
    """Whether a personal staff session is still open; each use counts as activity."""
    try:
        session, member = UUID(str(user.get('sid'))), UUID(str(user.get('sub', '')).removeprefix('member:'))
    except ValueError:
        return False
    if not enabled(): return False
    async with pool.acquire() as conn:
        if not await installed(conn): return False
        return await conn.fetchval('''UPDATE prep_inventory.staff_sessions s SET last_seen_at=greatest(s.last_seen_at, clock_timestamp())
            FROM public.staff_members m WHERE s.id=$1 AND s.staff_member_id=$2 AND s.store_id=$3 AND m.id=s.staff_member_id AND m.active
            AND s.ended_at IS NULL AND s.expires_at > clock_timestamp() AND s.last_seen_at > clock_timestamp() - make_interval(mins => $4)
            RETURNING true''', session, member, user.get('store'), IDLE_MINUTES) or False


async def sign_out(pool, user):
    async with pool.acquire() as conn:
        await conn.execute('''UPDATE prep_inventory.staff_sessions SET ended_at=clock_timestamp(), end_reason='signed_out'
            WHERE id=$1 AND ended_at IS NULL''', UUID(str(user['sid'])))


async def roster(conn, store):
    """Each active person's sign-in state, for managers."""
    await setup_ready(conn)
    rows = await conn.fetch('''SELECT m.id, m.name,
            (SELECT temporary FROM prep_inventory.staff_member_pins p WHERE p.staff_member_id=m.id ORDER BY set_at DESC LIMIT 1) AS temporary,
            (SELECT max(at) FROM prep_inventory.staff_sign_in_events e WHERE e.staff_member_id=m.id AND kind='signed_in') AS last_signed_in_at,
            (SELECT count(*) FROM prep_inventory.staff_sessions s WHERE s.staff_member_id=m.id AND s.ended_at IS NULL
                AND s.expires_at > clock_timestamp() AND s.last_seen_at > clock_timestamp() - make_interval(mins => $2)) AS open_sessions
        FROM public.staff_members m WHERE m.store_id=$1 AND m.active ORDER BY m.name''', store, IDLE_MINUTES)
    out = []
    for r in rows:
        until = await lock_state(conn, r['id'])
        out.append({'staff_member_id': str(r['id']), 'name': r['name'], 'has_pin': r['temporary'] is not None,
                    'temporary_pin': bool(r['temporary']), 'locked_until': until.isoformat() if until else None,
                    'last_signed_in_at': r['last_signed_in_at'].isoformat() if r['last_signed_in_at'] else None,
                    'signed_in': r['open_sessions'] > 0})
    return out


async def issue_pin(pool, store, member_id, actor, body, key):
    """A temporary PIN from an owner or the Ops Lead; it ends the person's sessions and lockout."""
    # The PIN itself stays out of the fingerprint: a 4-5 digit PIN is too short to keep behind a plain
    # hash. A replay is checked against the stored salted hash instead.
    digest = fingerprint(serial({'store': store, 'member': member_id, 'actor': actor}))
    async with pool.acquire() as conn, conn.transaction():
        await setup_ready(conn)
        await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))', str(key))   # concurrent retries replay
        prior = await conn.fetchrow('SELECT request_fingerprint, pin_hash FROM prep_inventory.staff_member_pins WHERE request_key=$1', key)
        if prior:
            if prior['request_fingerprint'] != digest or not await asyncio.to_thread(pin_ok, body.pin, prior['pin_hash']):
                raise HTTPException(409, 'Request key belongs to another PIN')
            return {'replayed': True}
        if not await conn.fetchval('SELECT 1 FROM public.staff_members WHERE id=$1 AND store_id=$2 AND active FOR UPDATE', member_id, store):
            raise HTTPException(404, 'Choose active staff at this location')
        await conn.execute('''INSERT INTO prep_inventory.staff_member_pins(store_id,staff_member_id,pin_hash,temporary,set_by,request_key,request_fingerprint)
            VALUES($1,$2,$3,true,$4,$5,$6)''', store, member_id, await asyncio.to_thread(pin_hash, body.pin), actor, key, digest)
        await end_sessions(conn, member_id, 'pin_reset')
        return {'replayed': False}


async def unlock(pool, store, member_id, actor, key):
    """Clears the lockout as it stands now; a retry of the same request replays and never clears a later one."""
    digest = fingerprint(serial({'store': store, 'member': member_id, 'actor': actor, 'action': 'unlock'}))
    async with pool.acquire() as conn, conn.transaction():
        await setup_ready(conn)
        await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))', str(key))
        prior = await conn.fetchrow('SELECT request_fingerprint FROM prep_inventory.staff_sign_in_events WHERE request_key=$1', key)
        if prior:
            if prior['request_fingerprint'] != digest: raise HTTPException(409, 'Request key belongs to another unlock')
            return {'replayed': True}
        if not await conn.fetchval('SELECT 1 FROM public.staff_members WHERE id=$1 AND store_id=$2 FOR UPDATE', member_id, store):
            raise HTTPException(404, 'Choose staff at this location')
        await conn.execute('''INSERT INTO prep_inventory.staff_sign_in_events(store_id,staff_member_id,kind,actor,request_key,request_fingerprint)
            VALUES($1,$2,'unlocked',$3,$4,$5)''', store, member_id, actor, key, digest)
        return {'replayed': False}


def create_router(pool_factory, store_check, manager_authorize, mint, staff_user):
    router = APIRouter()
    base = '/api/pg/staff/{store}'

    @router.get(base + '/sign-in/names')
    async def find_names(store: str, q: str = ''):
        store_check(store)
        async with pool_factory().acquire() as conn:
            return {'names': await names(conn, store, q[:60])}

    @router.post(base + '/sign-in')
    async def start(store: str, body: SignIn):
        store_check(store)
        return await sign_in(pool_factory(), store, body, mint)

    @router.post(base + '/sign-out')
    async def stop(store: str, request: Request):
        store_check(store)
        user = staff_user(request)
        if not user or user.get('store') != store: raise HTTPException(401, 'Not signed in')
        await sign_out(pool_factory(), user)
        return {'signed_out': True}

    @router.get(base + '/members/sign-in')
    async def read_roster(store: str, request: Request):
        # Managers and owners only: read-only collaborators don't see who is locked out or signed in.
        store_check(store); manager_authorize(request, store, True)
        async with pool_factory().acquire() as conn:
            return {'staff': await roster(conn, store), 'switched_on': enabled()}

    @router.put(base + '/members/{member_id}/pin')
    async def put_pin(store: str, member_id: UUID, body: IssuePin, request: Request, idempotency_key: UUID = Header(...)):
        store_check(store); actor = manager_authorize(request, store, True, 'issue_pins')
        return await issue_pin(pool_factory(), store, member_id, actor, body, idempotency_key)

    @router.post(base + '/members/{member_id}/unlock')
    async def post_unlock(store: str, member_id: UUID, request: Request, idempotency_key: UUID = Header(...)):
        store_check(store); actor = manager_authorize(request, store, True, 'unlock_pins')
        return await unlock(pool_factory(), store, member_id, actor, idempotency_key)

    return router
