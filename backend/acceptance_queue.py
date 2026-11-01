"""The acceptance queue (Jeff 2026-10-30): everything staff sent in that is waiting on a manager.

A BOH Shift Leader or above accepts output reports, prep counts and nightly counts; a Kitchen
Manager or above sends them back or reassigns the task. Shortage notes from cooks are shown beside
them. This is a read: each item is still accepted on its own review screen, which applies the rule.
"""
from datetime import date

from fastapi import APIRouter, Request

import positions
import staff_shortages
from purchase_api import serial


async def _has(conn, table):
    return await conn.fetchval('SELECT to_regclass($1) IS NOT NULL', table)


async def waiting_output(conn, store, day):
    """Output reports for the day whose latest revision is a submission with no decision yet."""
    if not await _has(conn, 'prep_inventory.staff_production_submissions'): return []
    rows = await conn.fetch('''SELECT s.id, s.root_id, s.task_id, s.review_snapshot->>'track' AS track, s.recorded_at,
            m.name AS staff_name, s.review_snapshot->'sources'->'task'->'task_snapshot'->>'name' AS task_name,
            (s.submitted_by = 'member:' || s.staff_member_id::text) AS identity_verified
        FROM prep_inventory.staff_production_submissions s JOIN public.staff_members m ON m.id = s.staff_member_id
        WHERE s.store_id=$1 AND (s.review_snapshot->>'day')::date=$2 AND s.kind='submit'
          AND NOT EXISTS (SELECT 1 FROM prep_inventory.staff_production_submissions n WHERE n.root_id=s.root_id AND n.revision>s.revision)
          AND NOT EXISTS (SELECT 1 FROM prep_inventory.staff_production_decisions d WHERE d.submission_id=s.id)
        ORDER BY s.recorded_at''', store, day)
    return [dict(r) for r in rows]


async def waiting_sheets(conn, schema, store):
    """Count sheets staff have submitted that have no decision yet (any day: they stay until decided)."""
    if not await _has(conn, f'{schema}.staff_decisions'): return []
    rows = await conn.fetch(f'''SELECT s.id, max(u.submitted_at) AS submitted_at, count(u.id) AS submissions
        FROM {schema}.staff_sheets s JOIN {schema}.staff_submissions u ON u.sheet_id=s.id AND u.store_id=s.store_id
        WHERE s.store_id=$1 AND NOT EXISTS (SELECT 1 FROM {schema}.staff_decisions d WHERE d.sheet_id=s.id)
        GROUP BY s.id ORDER BY max(u.submitted_at)''', store)
    return [dict(r) for r in rows]


async def queue(conn, store, day, user):
    output = await waiting_output(conn, store, day)
    prep_counts = await waiting_sheets(conn, 'prep_inventory', store)
    nightly = await waiting_sheets(conn, 'actual_inventory', store)
    shortages = await staff_shortages.for_day(conn, store, day)
    return serial({'store_id': store, 'day': day,
                   'can_accept': positions.can(user, 'accept_staff_work'), 'can_send_back': positions.can(user, 'edit_staff_work'),
                   'waiting': {'output': len(output), 'prep_counts': len(prep_counts), 'nightly_counts': len(nightly)},
                   'output': output, 'prep_counts': prep_counts, 'nightly_counts': nightly, 'shortages': shortages})


def create_router(pool_factory, store_check, manager_authorize, token_user):
    router = APIRouter()

    @router.get('/api/pg/purchases/{store}/acceptance-queue/{day}')
    async def read(store: str, day: date, request: Request):
        store_check(store); manager_authorize(request, store, False)
        async with pool_factory().acquire() as conn, conn.transaction(isolation='repeatable_read', readonly=True):
            return await queue(conn, store, day, token_user(request))

    return router
