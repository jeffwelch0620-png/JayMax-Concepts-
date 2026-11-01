"""Order calendar (M4, Jeff 2026-11-01): the next order cycle, what is due or overdue, why anything
was late, and what is still on order. A reminder and a record only: it never blocks a count or an
order, and never changes stock, orders or accounting."""
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo
from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from purchase_api import serial

ON_ORDER = ('approved', 'sent', 'receiving')


async def installed(conn):
    return await conn.fetchval("SELECT to_regclass('purchasing.order_cycle_notes') IS NOT NULL")


def clock(t):
    return t.strftime('%I:%M %p').lstrip('0')


def cycle(rows, now):
    """Today's cycle if today is an order day, otherwise the next order day."""
    by_day = {r['order_weekday']: r for r in rows}
    tz = ZoneInfo(rows[0]['timezone_name'])
    today = now.astimezone(tz).date()
    for ahead in range(7):
        day = today + timedelta(days=ahead)
        if day.weekday() in by_day: return day, by_day[day.weekday()], tz, today


def delivery(day, row):
    return day + timedelta(days=(row['delivery_weekday'] - day.weekday()) % 7 or 7)


def status(done_at, due, now, day, today):
    if done_at: return 'late' if done_at > due else 'done'
    if day > today: return 'upcoming'
    return 'overdue' if now > due else 'due'


async def order_late(conn, store, vendor_id, now):
    """(cycle date, calendar row) when an order for this supplier is submitted after its deadline today."""
    if not await installed(conn): return None
    rows = await conn.fetch('SELECT * FROM purchasing.order_calendar WHERE store_id=$1', store)
    if not rows: return None
    local = now.astimezone(ZoneInfo(rows[0]['timezone_name']))
    row = next((r for r in rows if r['order_weekday'] == local.weekday()), None)
    if row and vendor_id in row['vendor_ids'] and local.time() > row['order_due']: return local.date(), row
    return None


async def state(conn, store, now, can_create, can_approve):
    base = {'store_id': store, 'can_create': can_create, 'can_approve': can_approve}
    rows = await conn.fetch('SELECT * FROM purchasing.order_calendar WHERE store_id=$1 ORDER BY order_weekday', store)
    if not rows: return {**base, 'calendar': None, 'on_order': []}
    day, row, tz, today = cycle(rows, now)
    count_due, order_due = datetime.combine(day, row['count_due'], tz), datetime.combine(day, row['order_due'], tz)
    # The day's current count (after any recount or correction) decides: done only if it is complete.
    count = await conn.fetchrow('''SELECT status,recorded_at FROM actual_inventory.count_snapshots s WHERE store_id=$1 AND count_date=$2
        AND NOT EXISTS(SELECT 1 FROM actual_inventory.count_snapshots c WHERE c.corrects_snapshot_id=s.id)
        ORDER BY recorded_at DESC,id DESC LIMIT 1''', store, day)
    if count and count['status'] != 'complete': count = None
    names = {r['id']: r['name'] for r in await conn.fetch('SELECT id,name FROM public.vendors WHERE id=ANY($1)', row['vendor_ids'])}
    orders = await conn.fetch('''SELECT ref,vendor_id,status,submitted_at FROM public.purchase_orders WHERE store_id=$1 AND vendor_id=ANY($2)
        AND archived_at IS NULL AND (status='draft' OR (status<>'rejected' AND (submitted_at AT TIME ZONE $3)::date=$4))''',
        store, row['vendor_ids'], row['timezone_name'], day)
    notes = await conn.fetch('''SELECT kind,vendor_id,po_id,reason,recorded_by,recorded_at FROM purchasing.order_cycle_notes
        WHERE store_id=$1 AND cycle_date=$2 ORDER BY recorded_at''', store, day)
    vendors = []
    for vid in row['vendor_ids']:
        mine = [o for o in orders if o['vendor_id'] == vid]
        submitted = min((o['submitted_at'] for o in mine if o['status'] != 'draft' and o['submitted_at']), default=None)
        vendors.append({'vendor_id': vid, 'name': names.get(vid, vid), 'status': status(submitted, order_due, now, day, today),
                        'submitted_at': submitted, 'drafts': sum(o['status'] == 'draft' for o in mine)})
    count_status = status(count['recorded_at'] if count else None, count_due, now, day, today)
    calendar = {'cycle_date': day, 'today': today, 'timezone_name': row['timezone_name'],
                'count_due': count_due, 'order_due': order_due, 'count_due_label': clock(row['count_due']), 'order_due_label': clock(row['order_due']),
                'delivery_date': delivery(day, row), 'count': {'status': count_status, 'recorded_at': count['recorded_at'] if count else None,
                'needs_reason': count_status in ('late', 'overdue') and not any(n['kind'] == 'count_late' for n in notes)},
                'vendors': vendors, 'notes': [dict(n) for n in notes]}
    return {**base, 'calendar': calendar, 'on_order': await on_order(conn, store, rows)}


async def on_order(conn, store, rows):
    """Approved or sent orders not yet received. When the latest count was taken after an order's
    delivery day, its stock may already be counted: confirming the receipt keeps it from being counted
    twice (Draft 0.7, O4)."""
    tz = ZoneInfo(rows[0]['timezone_name'])
    by_day = {r['order_weekday']: r for r in rows}
    latest = await conn.fetchrow('''SELECT count_date,timing,boundary_date FROM actual_inventory.count_snapshots s WHERE store_id=$1
        AND status='complete' AND NOT EXISTS(SELECT 1 FROM actual_inventory.count_snapshots c WHERE c.corrects_snapshot_id=s.id)
        ORDER BY count_date DESC,boundary_date DESC,recorded_at DESC,id DESC LIMIT 1''', store)
    out = []
    for o in await conn.fetch('''SELECT ref,vendor_id,vendor_name,status,submitted_at,approved_at,sent_at FROM public.purchase_orders
            WHERE store_id=$1 AND archived_at IS NULL AND status=ANY($2) ORDER BY submitted_at,ref''', store, list(ON_ORDER)):
        placed = o['submitted_at'].astimezone(tz).date() if o['submitted_at'] else None
        row = by_day.get(placed.weekday()) if placed else None
        due = delivery(placed, row) if row and o['vendor_id'] in row['vendor_ids'] else None
        out.append({**dict(o), 'expected_delivery': due,
                    'maybe_counted': bool(latest and due and latest['boundary_date'] > due),
                    'latest_count_date': latest['count_date'] if latest else None})
    return out


class LateCount(BaseModel):
    model_config = ConfigDict(extra='forbid')
    cycle_date: date
    reason: str = Field(min_length=1, max_length=500)

    @field_validator('reason')
    @classmethod
    def clean(cls, value):
        value = value.strip()
        if not value: raise ValueError('Say why the count is late')
        return value


async def record_count_late(pool, store, actor, body, key):
    async with pool.acquire() as conn, conn.transaction():
        if not await installed(conn): raise HTTPException(503, 'Order calendar is awaiting its migration')
        prior = await conn.fetchrow('SELECT * FROM purchasing.order_cycle_notes WHERE request_key=$1', key)
        if prior:
            if (prior['store_id'], prior['cycle_date'], prior['kind'], prior['reason'], prior['recorded_by']) != (store, body.cycle_date, 'count_late', body.reason, actor):
                raise HTTPException(409, 'Request key belongs to another note')
            return serial({'note': dict(prior), 'replayed': True})
        rows = await conn.fetch('SELECT * FROM purchasing.order_calendar WHERE store_id=$1', store)
        if not any(r['order_weekday'] == body.cycle_date.weekday() for r in rows): raise HTTPException(422, 'That date is not an order day here')
        today = (await conn.fetchval('SELECT now()')).astimezone(ZoneInfo(rows[0]['timezone_name'])).date()
        if body.cycle_date > today: raise HTTPException(422, 'A count cannot be late before its day')
        note = await conn.fetchrow('''INSERT INTO purchasing.order_cycle_notes(store_id,cycle_date,kind,reason,recorded_by,request_key)
            VALUES($1,$2,'count_late',$3,$4,$5) RETURNING *''', store, body.cycle_date, body.reason, actor, key)
        return serial({'note': dict(note), 'replayed': False})


def install_routes(router, context):
    @router.get('/{store_id}/order-calendar')
    async def read(store_id: str, request: Request):
        actor, pool = await context(request, store_id)
        flags = {}
        for permission in ('create_orders', 'approve_orders'):
            try:
                await context(request, store_id, False, permission); flags[permission] = True
            except HTTPException as e:
                if e.status_code != 403: raise
                flags[permission] = False
        async with pool.acquire() as conn:
            if not await installed(conn): return {'store_id': store_id, 'installed': False}
            return serial({**await state(conn, store_id, await conn.fetchval('SELECT now()'), flags['create_orders'], flags['approve_orders']), 'installed': True})

    @router.post('/{store_id}/order-calendar/late-count')
    async def late_count(store_id: str, body: LateCount, request: Request, idempotency_key: UUID = Header(...)):
        actor, pool = await context(request, store_id, True)
        return await record_count_late(pool, store_id, actor, body, idempotency_key)
