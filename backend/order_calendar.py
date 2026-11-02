"""Order calendar (M4, Jeff 2026-11-01): the next order cycle, what is due or overdue, why anything
was late, and what is still on order. A reminder and a record only: it never blocks a count or an
order, and never changes stock, orders or accounting.

Only an owner or the Ops Lead changes the schedule (Jeff 2026-11-01): the weekly order days, and
skipping or moving one cycle (holidays, supplier changes). Every change keeps its reason."""
from datetime import date, datetime, time, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo
from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from purchase_api import serial
from purchase_parser import fingerprint

ON_ORDER = ('approved', 'sent', 'receiving')
DEFAULT_ZONE = 'America/New_York'
AHEAD = 21                       # days of cycles worked out ahead
HORIZON = 120                    # one cycle can be skipped or moved up to this many days ahead


async def installed(conn):
    return await conn.fetchval("SELECT to_regclass('purchasing.order_cycle_notes') IS NOT NULL")


async def schedule_ready(conn):
    return await conn.fetchval("SELECT to_regclass('purchasing.order_schedule_changes') IS NOT NULL")


def clock(t):
    return t.strftime('%I:%M %p').lstrip('0')


def delivery(day, row):
    return day + timedelta(days=(row['delivery_weekday'] - day.weekday()) % 7 or 7)


def status(done_at, due, now, day, today):
    if done_at: return 'late' if done_at > due else 'done'
    if day > today: return 'upcoming'
    return 'overdue' if now > due else 'due'


async def exceptions(conn, store, start, end, as_of=None):
    """The standing skip or move for each cycle date near [start, end]; a restore cancels one.
    With `as_of`, only changes made by then (the schedule an order was placed under)."""
    if not await schedule_ready(conn): return {}
    rows = await conn.fetch('''SELECT DISTINCT ON (cycle_date) cycle_date,kind,moved_to,delivery_date,reason,changed_by,changed_at
        FROM purchasing.order_schedule_changes WHERE store_id=$1 AND kind IN ('skip','move','restore')
        AND (cycle_date BETWEEN $2 AND $3 OR moved_to BETWEEN $2 AND $3) AND ($4::timestamptz IS NULL OR changed_at<=$4)
        ORDER BY cycle_date,changed_at DESC,id DESC''', store, start - timedelta(days=7), end + timedelta(days=7), as_of)
    return {r['cycle_date']: dict(r) for r in rows if r['kind'] != 'restore'}


def effective(rows, exc, start, days):
    """Cycles by the date they happen: the weekly days less skipped or moved cycles, plus moved ones on their new date."""
    by_day = {r['order_weekday']: r for r in rows}
    end = start + timedelta(days=days)
    out = {}
    for n in range(days):
        d = start + timedelta(days=n)
        if d.weekday() in by_day and d not in exc: out[d] = {'row': by_day[d.weekday()], 'delivery': delivery(d, by_day[d.weekday()]), 'moved_from': None}
    for d, e in exc.items():
        if e['kind'] == 'move' and start <= e['moved_to'] < end and d.weekday() in by_day:
            out[e['moved_to']] = {'row': by_day[d.weekday()], 'delivery': e['delivery_date'], 'moved_from': d}
    return out


def rows_at(rows, day_changes, at):
    """The weekly days as they stood at `at`: today's days with every later weekly change undone, newest first."""
    by_day = {r['order_weekday']: dict(r) for r in rows}
    for c in sorted((c for c in day_changes if c['changed_at'] > at), key=lambda c: c['changed_at'], reverse=True):
        if c['day_before']: by_day[c['order_weekday']] = dict(c['day_before'])
        else: by_day.pop(c['order_weekday'], None)
    return list(by_day.values())


def zone(rows):
    return ZoneInfo(rows[0]['timezone_name'] if rows else DEFAULT_ZONE)


async def order_late(conn, store, vendor_id, now):
    """(cycle date, calendar row) when an order for this supplier is submitted after its deadline today."""
    if not await installed(conn): return None
    rows = await conn.fetch('SELECT * FROM purchasing.order_calendar WHERE store_id=$1', store)
    if not rows: return None
    local = now.astimezone(zone(rows))
    today = local.date()
    entry = effective(rows, await exceptions(conn, store, today, today), today, 1).get(today)
    if entry and vendor_id in entry['row']['vendor_ids'] and local.time() > entry['row']['order_due']: return today, entry['row']
    return None


def day_view(r):
    return {'order_weekday': r['order_weekday'], 'count_due': r['count_due'].strftime('%H:%M'), 'order_due': r['order_due'].strftime('%H:%M'),
            'count_due_label': clock(r['count_due']), 'order_due_label': clock(r['order_due']),
            'delivery_weekday': r['delivery_weekday'], 'vendor_ids': list(r['vendor_ids'])}


async def schedule_view(conn, store, rows, today, exc, can_edit):
    """The weekly days and the next cycles (with any skip or move), for the owner or Ops Lead to change."""
    by_day = {r['order_weekday']: r for r in rows}
    upcoming = []
    for n in range(AHEAD):
        d = today + timedelta(days=n)
        if d.weekday() not in by_day: continue
        e = exc.get(d)
        upcoming.append({'cycle_date': d, 'change': e['kind'] if e else None, 'moved_to': e['moved_to'] if e else None,
                         'delivery_date': e['delivery_date'] if e and e['kind'] == 'move' else delivery(d, by_day[d.weekday()]),
                         'reason': e['reason'] if e else None})
        if len(upcoming) == 6: break
    vendors = [dict(v) for v in await conn.fetch('SELECT id,name FROM public.vendors WHERE active ORDER BY name')] if can_edit else []
    return {'can_edit': can_edit, 'ready': await schedule_ready(conn), 'days': [day_view(r) for r in rows], 'upcoming': upcoming, 'vendors': vendors}


async def state(conn, store, now, can_create, can_approve, can_edit=False):
    base = {'store_id': store, 'can_create': can_create, 'can_approve': can_approve}
    rows = await conn.fetch('SELECT * FROM purchasing.order_calendar WHERE store_id=$1 ORDER BY order_weekday', store)
    tz = zone(rows)
    today = now.astimezone(tz).date()
    exc = await exceptions(conn, store, today, today + timedelta(days=AHEAD))
    schedule = await schedule_view(conn, store, rows, today, exc, can_edit)
    cycles = effective(rows, exc, today, AHEAD)
    if not cycles: return {**base, 'calendar': None, 'on_order': await on_order(conn, store, rows), 'schedule': schedule}
    day = min(cycles)
    entry = cycles[day]; row = entry['row']
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
    calendar = {'cycle_date': day, 'today': today, 'timezone_name': row['timezone_name'], 'moved_from': entry['moved_from'],
                'count_due': count_due, 'order_due': order_due, 'count_due_label': clock(row['count_due']), 'order_due_label': clock(row['order_due']),
                'delivery_date': entry['delivery'], 'count': {'status': count_status, 'recorded_at': count['recorded_at'] if count else None,
                'needs_reason': count_status in ('late', 'overdue') and not any(n['kind'] == 'count_late' for n in notes)},
                'vendors': vendors, 'notes': [dict(n) for n in notes]}
    return {**base, 'calendar': calendar, 'on_order': await on_order(conn, store, rows), 'schedule': schedule}


async def on_order(conn, store, rows):
    """Approved or sent orders not yet received. When the latest count was taken after an order's
    delivery day, its stock may already be counted: confirming the receipt keeps it from being counted
    twice (Draft 0.7, O4)."""
    tz = zone(rows)
    latest = await conn.fetchrow('''SELECT count_date,timing,boundary_date FROM actual_inventory.count_snapshots s WHERE store_id=$1
        AND status='complete' AND NOT EXISTS(SELECT 1 FROM actual_inventory.count_snapshots c WHERE c.corrects_snapshot_id=s.id)
        ORDER BY count_date DESC,boundary_date DESC,recorded_at DESC,id DESC LIMIT 1''', store)
    day_changes = await conn.fetch('''SELECT order_weekday,day_before,changed_at FROM purchasing.order_schedule_changes
        WHERE store_id=$1 AND kind IN ('set_day','remove_day') ORDER BY changed_at,id''', store) if await schedule_ready(conn) else []
    out = []
    for o in await conn.fetch('''SELECT ref,vendor_id,vendor_name,status,submitted_at,approved_at,sent_at FROM public.purchase_orders
            WHERE store_id=$1 AND archived_at IS NULL AND status=ANY($2) ORDER BY submitted_at,ref''', store, list(ON_ORDER)):
        placed = o['submitted_at'].astimezone(tz).date() if o['submitted_at'] else None
        # The schedule the order was placed under, so later schedule edits don't rewrite its delivery.
        entry = effective(rows_at(rows, day_changes, o['submitted_at']), await exceptions(conn, store, placed, placed, o['submitted_at']),
                          placed, 1).get(placed) if placed else None
        due = entry['delivery'] if entry and o['vendor_id'] in entry['row']['vendor_ids'] else None
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
        exc = await exceptions(conn, store, body.cycle_date, body.cycle_date)
        if body.cycle_date not in effective(rows, exc, body.cycle_date, 1): raise HTTPException(422, 'That date is not an order day here')
        today = (await conn.fetchval('SELECT now()')).astimezone(zone(rows)).date()
        if body.cycle_date > today: raise HTTPException(422, 'A count cannot be late before its day')
        note = await conn.fetchrow('''INSERT INTO purchasing.order_cycle_notes(store_id,cycle_date,kind,reason,recorded_by,request_key)
            VALUES($1,$2,'count_late',$3,$4,$5) RETURNING *''', store, body.cycle_date, body.reason, actor, key)
        return serial({'note': dict(note), 'replayed': False})


class ScheduleChange(BaseModel):
    """One change to a store's order schedule, by an owner or the Ops Lead, with its reason."""
    model_config = ConfigDict(extra='forbid')
    kind: Literal['set_day', 'remove_day', 'skip', 'move', 'restore']
    order_weekday: int | None = Field(default=None, ge=0, le=6)      # 0 Monday ... 6 Sunday
    count_due: time | None = None
    order_due: time | None = None
    delivery_weekday: int | None = Field(default=None, ge=0, le=6)
    vendor_ids: list[str] | None = Field(default=None, min_length=1, max_length=10)
    cycle_date: date | None = None
    moved_to: date | None = None
    delivery_date: date | None = None
    reason: str = Field(min_length=1, max_length=500)

    @field_validator('reason')
    @classmethod
    def clean(cls, value):
        value = value.strip()
        if not value: raise ValueError('Say why the schedule changes')
        return value

    @model_validator(mode='after')
    def shape(self):
        day = (self.order_weekday, self.count_due, self.order_due, self.delivery_weekday, self.vendor_ids)
        once = (self.cycle_date, self.moved_to, self.delivery_date)
        if self.kind == 'set_day':
            if any(v is None for v in day) or any(v is not None for v in once): raise ValueError('A weekly order day needs its day, deadlines, delivery day and suppliers')
            if self.count_due > self.order_due: raise ValueError('The count is due no later than the order')
            if len(set(self.vendor_ids)) != len(self.vendor_ids): raise ValueError('List each supplier once')
        elif self.kind == 'remove_day':
            if self.order_weekday is None or any(v is not None for v in day[1:] + once): raise ValueError('Name only the weekly order day to remove')
        else:
            if self.cycle_date is None or any(v is not None for v in day): raise ValueError('Name the cycle date')
            if self.kind == 'move':
                if self.moved_to is None or self.delivery_date is None: raise ValueError('A moved cycle needs its new order date and delivery date')
                if self.moved_to == self.cycle_date or abs((self.moved_to - self.cycle_date).days) > 6: raise ValueError('Move a cycle by one to six days')
                if self.delivery_date < self.moved_to: raise ValueError('Delivery cannot come before the order')
            elif self.moved_to is not None or self.delivery_date is not None: raise ValueError('Only a moved cycle has a new date')
        return self


async def change_schedule(pool, store, actor, body, key):
    digest = fingerprint(serial({'store': store, 'actor': actor, 'change': body.model_dump(mode='json')}))
    async with pool.acquire() as conn, conn.transaction():
        if not await schedule_ready(conn): raise HTTPException(503, 'Order schedule changes are awaiting their migration')
        await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('order-schedule:'||$1,0))", store)
        prior = await conn.fetchrow('SELECT * FROM purchasing.order_schedule_changes WHERE request_key=$1', key)
        if prior:
            if prior['store_id'] != store or prior['changed_by'] != actor or bytes(prior['request_fingerprint']) != digest:
                raise HTTPException(409, 'Request key belongs to another schedule change')
            return serial({'change': dict(prior), 'replayed': True})
        rows = await conn.fetch('SELECT * FROM purchasing.order_calendar WHERE store_id=$1 ORDER BY order_weekday FOR UPDATE', store)
        today = (await conn.fetchval('SELECT now()')).astimezone(zone(rows)).date()
        before = after = None
        if body.kind == 'set_day':
            known = {r['id'] for r in await conn.fetch('SELECT id FROM public.vendors WHERE active AND id=ANY($1)', body.vendor_ids)}
            if known != set(body.vendor_ids): raise HTTPException(422, 'Choose active registered suppliers')
            old = next((r for r in rows if r['order_weekday'] == body.order_weekday), None)
            if not old:
                exc = await exceptions(conn, store, today, today + timedelta(days=HORIZON + 7))
                if any(e['kind'] == 'move' and e['moved_to'] >= today and e['moved_to'].weekday() == body.order_weekday for e in exc.values()):
                    raise HTTPException(409, 'A moved cycle already falls on that weekday; put it back or move it first')
            before = day_view(old) if old else None
            new = await conn.fetchrow('''INSERT INTO purchasing.order_calendar(store_id,order_weekday,count_due,order_due,delivery_weekday,vendor_ids,timezone_name)
                VALUES($1,$2,$3,$4,$5,$6,$7) ON CONFLICT (store_id,order_weekday) DO UPDATE SET count_due=EXCLUDED.count_due,order_due=EXCLUDED.order_due,
                delivery_weekday=EXCLUDED.delivery_weekday,vendor_ids=EXCLUDED.vendor_ids RETURNING *''', store, body.order_weekday, body.count_due,
                body.order_due, body.delivery_weekday, body.vendor_ids, rows[0]['timezone_name'] if rows else DEFAULT_ZONE)
            after = day_view(new)
        elif body.kind == 'remove_day':
            old = next((r for r in rows if r['order_weekday'] == body.order_weekday), None)
            if not old: raise HTTPException(404, 'That is not an order day here')
            # A moved cycle hangs off its usual weekday: put those back before removing the day.
            exc = await exceptions(conn, store, today, today + timedelta(days=HORIZON + 7))
            if any(e['kind'] == 'move' and d >= today and d.weekday() == body.order_weekday for d, e in exc.items()):
                raise HTTPException(409, 'A cycle from that day is moved to another date; put it back first')
            before = day_view(old)
            await conn.execute('DELETE FROM purchasing.order_calendar WHERE store_id=$1 AND order_weekday=$2', store, body.order_weekday)
        else:
            if body.cycle_date.weekday() not in {r['order_weekday'] for r in rows}: raise HTTPException(422, 'That date is not a weekly order day here')
            if body.cycle_date < today: raise HTTPException(422, 'A past cycle cannot be changed')
            if body.cycle_date > today + timedelta(days=HORIZON): raise HTTPException(422, f'Change a cycle up to {HORIZON} days ahead')
            # Every skip or move near the cycle and its new date (exceptions() looks a week either side).
            span = [body.cycle_date] + ([body.moved_to] if body.moved_to else [])
            exc = await exceptions(conn, store, min(span), max(span))
            current = exc.get(body.cycle_date)
            if body.kind == 'restore' and not current: raise HTTPException(409, 'That cycle is already on its usual day')
            if body.kind == 'restore' and any(e['kind'] == 'move' and e['moved_to'] == body.cycle_date for d, e in exc.items() if d != body.cycle_date):
                raise HTTPException(409, 'Another cycle has moved onto that date; move it first')
            if body.kind == 'skip' and current and current['kind'] == 'skip': raise HTTPException(409, 'That cycle is already skipped')
            if body.kind == 'move':
                if body.moved_to < today: raise HTTPException(422, 'Move a cycle to today or later')
                others = effective(rows, {d: e for d, e in exc.items() if d != body.cycle_date}, body.moved_to, 1)
                if body.moved_to in others: raise HTTPException(409, 'Another cycle already falls on that date')
        change = await conn.fetchrow('''INSERT INTO purchasing.order_schedule_changes(store_id,kind,order_weekday,cycle_date,moved_to,delivery_date,
            day_before,day_after,reason,changed_by,request_key,request_fingerprint) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) RETURNING *''',
            store, body.kind, body.order_weekday, body.cycle_date, body.moved_to, body.delivery_date, before, after, body.reason, actor, key, digest)
        return serial({'change': dict(change), 'replayed': False})


def install_routes(router, context):
    @router.get('/{store_id}/order-calendar')
    async def read(store_id: str, request: Request):
        actor, pool = await context(request, store_id)
        flags = {}
        for permission in ('create_orders', 'approve_orders', 'edit_order_schedule'):
            try:
                await context(request, store_id, False, permission); flags[permission] = True
            except HTTPException as e:
                if e.status_code != 403: raise
                flags[permission] = False
        async with pool.acquire() as conn:
            if not await installed(conn): return {'store_id': store_id, 'installed': False}
            return serial({**await state(conn, store_id, await conn.fetchval('SELECT now()'), flags['create_orders'], flags['approve_orders'],
                                         flags['edit_order_schedule']), 'installed': True})

    @router.post('/{store_id}/order-calendar/late-count')
    async def late_count(store_id: str, body: LateCount, request: Request, idempotency_key: UUID = Header(...)):
        actor, pool = await context(request, store_id, True)
        return await record_count_late(pool, store_id, actor, body, idempotency_key)

    @router.post('/{store_id}/order-calendar/schedule')
    async def schedule(store_id: str, body: ScheduleChange, request: Request, idempotency_key: UUID = Header(...)):
        actor, pool = await context(request, store_id, True, 'edit_order_schedule')
        return await change_schedule(pool, store_id, actor, body, idempotency_key)
