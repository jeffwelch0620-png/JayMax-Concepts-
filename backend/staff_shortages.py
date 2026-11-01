"""Shortage reports: a note to the Shift Leader (Jeff 2026-11-01).

A signed-in cook reports that they are short on one of their own prep tasks for the day: how much
(optional, in the task's unit), why, and a note. It changes no counts, pars or production; the Shift
Leader sees it on the station board (and in the acceptance queue with step D).
migrations/20261101_staff_shortages.sql holds the table.
"""
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import Field

import prep_tracks
import staff_login
import staff_prep_tasks as tasks
from native_units import lock_store
from purchase_api import serial
from purchase_parser import fingerprint
from staff_prep_counts import Credentials


class Report(Credentials):
    day: date
    track: prep_tracks.Track = 'daily'
    task_id: UUID
    staff_member_id: UUID
    short_quantity: Decimal | None = Field(default=None, gt=0, max_digits=28, decimal_places=12)
    reason: Literal['out_of_ingredient', 'ran_out_of_time', 'equipment', 'other']
    note: str = Field(min_length=1, max_length=1000)


async def installed(conn):
    return await conn.fetchval("SELECT to_regclass('prep_inventory.staff_shortage_reports') IS NOT NULL")


async def ready(conn):
    await tasks.ready(conn)
    if not await installed(conn): raise HTTPException(503, 'Shortage reports migration is awaiting setup')


async def for_day(conn, store, day):
    """The day's reports, newest first, for the Shift Leader."""
    if not await installed(conn): return []
    rows = await conn.fetch('''SELECT r.id, r.business_date, r.track, r.task_id, r.task_snapshot, r.staff_member_id, m.name AS staff_name,
            r.short_quantity, r.reason, r.note, r.identity_verified, r.reported_at
        FROM prep_inventory.staff_shortage_reports r JOIN public.staff_members m ON m.id = r.staff_member_id
        WHERE r.store_id=$1 AND r.business_date=$2 ORDER BY r.reported_at DESC''', store, day)
    return [dict(r) for r in rows]


async def report(pool, store, actor, kind, body, key):
    digest = fingerprint(serial({'store': store, 'actor': actor, 'body': body.model_dump(mode='json', exclude={'pin'})}))
    async with pool.acquire() as conn, conn.transaction():
        await ready(conn)
        await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))', str(key))
        prior = await conn.fetchrow('SELECT * FROM prep_inventory.staff_shortage_reports WHERE request_key=$1', key)
        if prior:
            if prior['request_fingerprint'] != digest: raise HTTPException(409, 'Request key belongs to another report')
            return {'report': serial(dict(prior)), 'replayed': True}
        verified = staff_login.acting_member(actor, body.staff_member_id)
        await lock_store(conn, store)
        # Only a task in the cook's own queue for that day: named to them or made at their station.
        plan = await tasks.staff_state(conn, store, tasks.ReadIn(pin='', day=body.day, track=body.track, staff_member_id=body.staff_member_id), kind, verified)
        task = next((t for t in plan['tasks'] if t['id'] == str(body.task_id)), None)
        if not task: raise HTTPException(422, 'Report a shortage on one of your own prep tasks for that day')
        row = await conn.fetchrow('''INSERT INTO prep_inventory.staff_shortage_reports(store_id,business_date,track,task_id,task_snapshot,staff_member_id,
                short_quantity,reason,note,reported_by,identity_verified,request_key,request_fingerprint)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13) RETURNING *''', store, body.day, body.track, body.task_id,
            serial({'name': task['name'], 'quantity': task['quantity'], 'source_unit': task['source_unit']}), body.staff_member_id,
            body.short_quantity, body.reason, body.note, actor, verified, key, digest)
        return {'report': serial(dict(row)), 'replayed': False}


def create_router(pool_factory, store_check, staff_authorize):
    router = APIRouter()

    @router.post('/api/pg/staff/{store}/shortages')
    async def post_report(store: str, body: Report, request: Request, idempotency_key: UUID = Header(...)):
        prep_tracks.check(store, body.track)
        store_check(store)
        async with pool_factory().acquire() as conn:
            await ready(conn); actor, kind = await staff_authorize(request, conn, store, body.pin)
        # A shortage note comes from the cook themself (personal sign-in), so the Shift Leader knows who.
        if not str(actor).startswith('member:'): raise HTTPException(403, 'Sign in with your own name and PIN to report a shortage')
        result = await report(pool_factory(), store, actor, kind, body, idempotency_key)
        result['report'].pop('reported_by', None)
        return result

    return router
