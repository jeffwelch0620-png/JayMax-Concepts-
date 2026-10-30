"""Stations, each prep item's default station, and station time (Jeff 2026-10-30).

A cook's queue for a shift is their station's unassigned tasks plus anything assigned to them by
name; tasks for a station nobody is on stay with the Shift Leader. Every stint is recorded with its
start and, separately, its end, so station metrics and each employee's metrics per station can be
reported historically. migrations/20261031_stations.sql enforces one open stint per person.
"""
from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import Field
import prep_mapping as mapping
from native_units import lock_store
from purchase_api import serial
from purchase_parser import fingerprint
from staff_prep_counts import Credentials

STORE_ZONE = ZoneInfo('America/New_York')  # all three stores are in Eastern Tennessee


async def installed(conn):
    return await conn.fetchval("SELECT to_regclass('workforce.station_stints') IS NOT NULL")


async def ready(conn):
    if not await installed(conn): raise HTTPException(503, 'Stations migration is awaiting setup')


def check_day(day):
    """Station moves are for the current business day (yesterday allowed for a late close)."""
    today = datetime.now(STORE_ZONE).date()
    if day not in (today, today - timedelta(days=1)): raise HTTPException(422, 'Station moves are recorded for today (or yesterday until close)')


class Move(mapping.Strict):
    staff_member_id: UUID
    station_code: str | None = Field(default=None, min_length=1, max_length=20)   # None = off station
    reason: Literal['moved', 'off_station', 'shift_end'] = 'moved'
    note: str | None = Field(default=None, max_length=500)


class SelfMove(Credentials):
    staff_member_id: UUID
    station_code: str = Field(min_length=1, max_length=20)
    business_date: date


class ProductStation(mapping.Strict):
    station_code: str | None = Field(default=None, min_length=1, max_length=20)
    note: str = Field(min_length=1, max_length=500)


async def stations(conn, store):
    return [dict(r) for r in await conn.fetch('SELECT * FROM workforce.stations WHERE store_id=$1 ORDER BY department, name', store)]


async def open_stints(conn, store):
    return [dict(r) for r in await conn.fetch('''SELECT * FROM workforce.station_time WHERE store_id=$1 AND ended_at IS NULL
        ORDER BY station_name, staff_name''', store)]


async def product_stations(conn, store):
    """Each prepared item's current default station."""
    return {str(r['product_id']): r['station_code'] for r in await conn.fetch('''SELECT DISTINCT ON (product_id) product_id, station_code
        FROM workforce.product_stations WHERE store_id=$1 ORDER BY product_id, revision DESC''', store)}


async def member_station(conn, store, member_id):
    return await conn.fetchval('''SELECT s.station_code FROM workforce.station_stints s WHERE s.store_id=$1 AND s.staff_member_id=$2
        AND NOT EXISTS (SELECT 1 FROM workforce.stint_ends e WHERE e.stint_id=s.id)''', store, member_id)


async def board(conn, store, day):
    await ready(conn)
    roster = [dict(r) for r in await conn.fetch('SELECT id,name,role,active FROM public.staff_members WHERE store_id=$1 AND active ORDER BY name', store)]
    history = [dict(r) for r in await conn.fetch('''SELECT * FROM workforce.station_time WHERE store_id=$1 AND business_date=$2
        ORDER BY started_at, staff_name''', store, day)]
    names = {str(r['product_id']): r['name'] for r in await conn.fetch('''SELECT DISTINCT ON (product_id) product_id, name
        FROM prep_inventory.product_versions WHERE store_id=$1 ORDER BY product_id, revision DESC''', store)}
    defaults = await product_stations(conn, store)
    return serial({'store_id': store, 'business_date': day, 'stations': await stations(conn, store), 'roster': roster,
        'open': await open_stints(conn, store), 'history': history,
        'products': [{'product_id': p, 'name': n, 'station_code': defaults.get(p)} for p, n in sorted(names.items(), key=lambda x: x[1].casefold())]})


async def move(conn, store, day, actor, body, key, source='board'):
    """End the person's current stint (if any) and start the new one, in one transaction."""
    digest = fingerprint(serial({'store': store, 'day': day, 'actor': actor, 'source': source, 'body': body.model_dump()}))
    await lock_store(conn, store)
    prior = await conn.fetchrow('SELECT * FROM workforce.station_stints WHERE request_key=$1', key)
    if prior:
        if prior['request_fingerprint'] != digest: raise HTTPException(409, 'Request key belongs to another station move')
        return {'replayed': True}
    if not await conn.fetchval('SELECT 1 FROM public.staff_members WHERE id=$1 AND store_id=$2 AND active', body.staff_member_id, store):
        raise HTTPException(422, 'Choose active staff at this location')
    if body.station_code and not await conn.fetchval('SELECT 1 FROM workforce.stations WHERE store_id=$1 AND code=$2 AND active', store, body.station_code):
        raise HTTPException(422, 'Choose an active station at this location')
    current = await conn.fetchrow('''SELECT s.* FROM workforce.station_stints s WHERE s.staff_member_id=$1
        AND NOT EXISTS (SELECT 1 FROM workforce.stint_ends e WHERE e.stint_id=s.id)''', body.staff_member_id)
    if current and current['station_code'] == body.station_code: raise HTTPException(409, 'Already on that station')
    if not current and not body.station_code: raise HTTPException(409, 'This person is not on a station')
    if current:
        await conn.execute('INSERT INTO workforce.stint_ends(stint_id,ended_by,reason) VALUES($1,$2,$3)', current['id'], actor,
                           body.reason if not body.station_code else 'moved')
    if body.station_code:
        await conn.execute('''INSERT INTO workforce.station_stints(store_id,staff_member_id,station_code,business_date,source,assigned_by,note,
            request_key,request_fingerprint) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)''', store, body.staff_member_id, body.station_code, day,
            source, actor, body.note, key, digest)
    return {'replayed': False}


async def set_product_station(pool, store, product_id, actor, body, key):
    digest = fingerprint(serial({'store': store, 'product': product_id, 'actor': actor, 'body': body.model_dump()}))
    async with pool.acquire() as conn, conn.transaction():
        await ready(conn); await lock_store(conn, store)
        prior = await conn.fetchrow('SELECT * FROM workforce.product_stations WHERE request_key=$1', key)
        if prior:
            if prior['request_fingerprint'] != digest: raise HTTPException(409, 'Request key belongs to another station default')
            return serial({'product_station': dict(prior), 'replayed': True})
        if not await conn.fetchval('SELECT 1 FROM prep_inventory.products WHERE id=$1 AND store_id=$2', product_id, store):
            raise HTTPException(404, 'Prepared item is not at this location')
        if body.station_code and not await conn.fetchval('SELECT 1 FROM workforce.stations WHERE store_id=$1 AND code=$2 AND active', store, body.station_code):
            raise HTTPException(422, 'Choose an active station at this location')
        revision = (await conn.fetchval('SELECT max(revision) FROM workforce.product_stations WHERE product_id=$1', product_id) or 0) + 1
        row = await conn.fetchrow('''INSERT INTO workforce.product_stations(store_id,product_id,station_code,revision,note,set_by,request_key,request_fingerprint)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *''', store, product_id, body.station_code, revision, body.note, actor, key, digest)
        return serial({'product_station': dict(row), 'replayed': False})


def create_router(pool_factory, store_check, manager_authorize, staff_authorize):
    router = APIRouter()
    base = '/api/pg/purchases/{store}/stations'

    @router.get(base + '/board/{day}')
    async def read_board(store: str, day: date, request: Request):
        store_check(store); manager_authorize(request, store, False)
        async with pool_factory().acquire() as conn, conn.transaction(isolation='repeatable_read', readonly=True):
            return await board(conn, store, day)

    @router.post(base + '/board/{day}/moves')
    async def board_move(store: str, day: date, body: Move, request: Request, idempotency_key: UUID = Header(...)):
        # Putting people on stations is a Shift Leader job (BOH Shift Leader and up).
        store_check(store); actor = manager_authorize(request, store, True, 'accept_staff_work'); check_day(day)
        async with pool_factory().acquire() as conn, conn.transaction():
            await ready(conn)
            result = await move(conn, store, day, actor, body, idempotency_key)
            return {**result, 'board': await board(conn, store, day)}

    @router.put(base + '/products/{product_id}')
    async def product_default(store: str, product_id: UUID, body: ProductStation, request: Request, idempotency_key: UUID = Header(...)):
        # Which station normally makes an item: Kitchen Manager and up.
        store_check(store); actor = manager_authorize(request, store, True, 'edit_staff_work')
        return await set_product_station(pool_factory(), store, product_id, actor, body, idempotency_key)

    @router.post('/api/pg/staff/{store}/station')
    async def self_move(store: str, body: SelfMove, request: Request, idempotency_key: UUID = Header(...)):
        # A cook confirms their own station when they sign in (shared store PIN or personal login).
        store_check(store); check_day(body.business_date)
        async with pool_factory().acquire() as conn, conn.transaction():
            await ready(conn); actor, _ = await staff_authorize(request, conn, store, body.pin)
            await move(conn, store, body.business_date, f'self:{actor}', Move(staff_member_id=body.staff_member_id, station_code=body.station_code),
                       idempotency_key, source='self')
            return {'station_code': await member_station(conn, store, body.staff_member_id)}

    return router
