"""M2 Bulk daily pars, phase B (Jeff 2026-11-04 and 2026-11-05): the quick daily Bulk count and the
spot-prep check. A manager counts only the store's active to-par Bulk items at night (Bert's
includes its Bulk held at Rudd's). In daily par mode each item's on hand, plus spot requests still
on their way, is compared with its daily pars for the days left before the next Monday or Thursday
run; anything short is shown as a spot prep needed. The check only suggests: a requesting store
still sends its own spot request, and the Bulk kitchen makes its own spot prep. Separate from the
full prep count, so the counts that drive the runs are unchanged. migrations/20261105_bulk_quick_counts.sql
enforces the same rules. No stock, purchase or accounting writes."""
from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal, Inexact, localcontext
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import Header, HTTPException, Request
from pydantic import AwareDatetime, Field, model_validator
import bulk_supply as bulk
import prep_day_tasks as day_tasks
import prep_mapping as mapping
import prep_planning as planning
from native_units import lock_store
from purchase_api import serial
from purchase_parser import fingerprint

STORE_ZONE = 'America/New_York'  # all three stores are in Eastern Tennessee
# Spot request amounts are in the item's par unit, to 12 decimal places (bulk_supply.SpotLine).
SPOT_STEP = Decimal('1e-12')


class QuickLine(mapping.Strict):
    product_id: UUID
    # The unit shown when the amount was entered; a changed unit is refused rather than reinterpreted.
    profile_id: UUID
    quantity: Decimal = Field(ge=0, max_digits=28, decimal_places=12)


class QuickCountIn(mapping.Strict):
    business_date: date
    performed_at: AwareDatetime
    note: str = Field(min_length=1, max_length=2000)
    lines: list[QuickLine] = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def night(self):
        # Counted that night, or after midnight before the next day starts.
        if self.performed_at.astimezone(ZoneInfo(STORE_ZONE)).date() not in (self.business_date, self.business_date + timedelta(days=1)):
            raise ValueError('A quick Bulk count is for the night it was taken')
        if len({l.product_id for l in self.lines}) != len(self.lines): raise ValueError('Count each item once')
        self.lines.sort(key=lambda l: str(l.product_id))
        return self


def days_before_next_run(night):
    """Days (Monday is zero) after a count on `night` that come before the next Bulk run covers them.
    Sunday and Wednesday nights: none, the next morning's run covers them."""
    days, d = [], night + timedelta(days=1)
    while day_tasks.bulk_day_group(d) is None:
        days.append(d.weekday()); d += timedelta(days=1)
    return days, d


def spot_need(plan, factor, night, counted_base, incoming_base):
    """The spot prep needed before the next run, in base units: the daily pars for the days left
    minus what is on hand and already on its way; never below zero. None without daily pars."""
    pars = plan.get('daily_pars')
    if not pars: return None
    days, run = days_before_next_run(night)
    with localcontext() as ctx:
        ctx.prec = 80; ctx.traps[Inexact] = True
        need = mapping.times(sum((Decimal(pars[d]) for d in days), Decimal(0)), factor)
        short = max(need - counted_base - incoming_base, Decimal(0))
        # Suggested in the par unit, rounded up so the request covers the shortfall.
        ctx.traps[Inexact] = False
        quantity = Decimal(format((short / factor).quantize(SPOT_STEP, rounding=ROUND_CEILING).normalize(), 'f'))
    return {'days': days, 'next_run': run, 'need_base_quantity': need, 'short_base_quantity': short, 'spot_quantity': quantity}


async def installed(conn):
    return await conn.fetchval("SELECT to_regclass('prep_inventory.bulk_quick_counts') IS NOT NULL")


async def ready(conn):
    await day_tasks.ready(conn)
    if not await installed(conn): raise HTTPException(503, 'Quick Bulk count migration is awaiting setup')


async def items(conn, store):
    """The store's active to-par Bulk items with their par unit, by name."""
    setup = await planning.setup(conn, store)
    products = {p['product_id']: p for p in setup['products']}
    profiles = {p['id']: p for p in setup['unitProfiles']}
    found = []
    for p in setup['plans']:
        if not (p['active'] and p['track'] == 'bulk' and p['schedule'] == 'daily'): continue
        profile = profiles.get(p['unit_profile_id'])
        name = products[p['product_id']]['name']
        # A count only needs the item's par unit, as a Bulk request does (bulk_supply.preview).
        if not profile: raise HTTPException(409, f'Review the Bulk plan for {name} before counting it')
        found.append({'product_id': p['product_id'], 'name': name, 'base_unit': products[p['product_id']]['base_unit'],
            'profile_id': profile['id'], 'product_version_id': profile['product_version_id'], 'source_unit': profile['source_unit'],
            'factor': Decimal(str(profile['base_units_per_source_unit'])), 'plan': p})
    return setup['bulk_par_mode'], sorted(found, key=lambda i: i['name'].casefold())


async def incoming(conn, store, counted_at, next_run):
    """Base amounts per item that this store's spot requests add after the count: requests needed before
    the next run and not cancelled; the amount asked until the maker signs off, then what it actually
    sent; once accepted, what arrived, but only if it was accepted after the count (earlier deliveries
    are already in the count). Stock the maker holds for this store counts toward its par too, if it
    was signed off after the count (earlier holdings are in the count's "Held at" zone)."""
    if bulk.MAKERS.get(store) is None or not await bulk.installed(conn): return {}
    rows = await conn.fetch('''SELECT l.product_id::text AS product_id,
        sum(CASE WHEN ae.id IS NOT NULL THEN CASE WHEN ae.created_at>$2 THEN a.base_quantity ELSE 0 END
            ELSE coalesce(f.base_quantity, l.requested_base_quantity) END
          + CASE WHEN fe.created_at>$2 THEN f.held_base_quantity ELSE 0 END) AS amount
        FROM prep_inventory.bulk_request_lines l JOIN prep_inventory.bulk_requests r ON r.id=l.request_id
        LEFT JOIN (prep_inventory.bulk_event_lines f JOIN prep_inventory.bulk_events fe ON fe.id=f.event_id AND fe.action='fulfill')
         ON f.request_id=l.request_id AND f.ordinal=l.ordinal
        LEFT JOIN (prep_inventory.bulk_event_lines a JOIN prep_inventory.bulk_events ae ON ae.id=a.event_id AND ae.action='accept')
         ON a.request_id=l.request_id AND a.ordinal=l.ordinal
        WHERE r.store_id=$1 AND r.kind='spot' AND r.run_date<$3
        AND NOT EXISTS(SELECT 1 FROM prep_inventory.bulk_events e WHERE e.request_id=r.id AND e.action='cancel') GROUP BY l.product_id''',
        store, counted_at, next_run)
    return {r['product_id']: r['amount'] for r in rows}


async def history(conn, store, night):
    counts = [dict(r) for r in await conn.fetch('''SELECT id,store_id,business_date,revision,performed_at,note,actor,recorded_at
        FROM prep_inventory.bulk_quick_counts WHERE store_id=$1 AND business_date=$2 ORDER BY revision''', store, night)]
    if counts:
        counts[-1]['lines'] = [dict(r) for r in await conn.fetch('''SELECT product_id,quantity,factor,base_quantity
            FROM prep_inventory.bulk_quick_count_lines WHERE count_id=$1 ORDER BY line_number''', counts[-1]['id'])]
    return counts


async def read(conn, store, night):
    await ready(conn)
    mode, found = await items(conn, store)
    counts = await history(conn, store, night)
    latest = counts[-1] if counts else None
    check = None
    if latest and mode == 'daily':
        counted = {str(l['product_id']): l['base_quantity'] for l in latest['lines']}
        on_way = await incoming(conn, store, latest['performed_at'], days_before_next_run(night)[1])
        check = []
        for i in found:
            if i['product_id'] not in counted:
                # Added to Bulk after this count: a missing count is not zero, so the check is incomplete.
                check.append({'product_id': i['product_id'], 'name': i['name'], 'base_unit': i['base_unit'], 'source_unit': i['source_unit'], 'counted': False,
                    'counted_base_quantity': None, 'incoming_base_quantity': None, 'days': None, 'next_run': None,
                    'need_base_quantity': None, 'short_base_quantity': None, 'spot_quantity': None})
                continue
            need = spot_need(i['plan'], i['factor'], night, counted[i['product_id']], on_way.get(i['product_id'], Decimal(0)))
            check.append({'product_id': i['product_id'], 'name': i['name'], 'base_unit': i['base_unit'], 'source_unit': i['source_unit'], 'counted': True,
                'counted_base_quantity': counted[i['product_id']], 'incoming_base_quantity': on_way.get(i['product_id'], Decimal(0)),
                **(need or {'days': None, 'next_run': None, 'need_base_quantity': None, 'short_base_quantity': None, 'spot_quantity': None})})
    days, run = days_before_next_run(night)
    return serial({'store_id': store, 'business_date': night, 'par_mode': mode, 'maker_store_id': bulk.MAKERS.get(store),
        'days_before_next_run': days, 'next_run': run, 'revision': latest['revision'] if latest else 0,
        'items': [{k: v for k, v in i.items() if k != 'plan'} for i in found], 'counts': counts, 'check': check,
        'check_complete': check is not None and all(c['counted'] for c in check)})


async def save(pool, store, actor, body, key, expected):
    digest = fingerprint(serial({'store': store, 'actor': actor, 'expected': expected, 'body': body.model_dump()}))
    async with pool.acquire() as conn, conn.transaction():
        await ready(conn); await lock_store(conn, store)
        prior = await conn.fetchrow('SELECT * FROM prep_inventory.bulk_quick_counts WHERE request_key=$1', key)
        if prior:
            if prior['request_fingerprint'] != digest: raise HTTPException(409, 'Request key belongs to another quick Bulk count')
            return {'request_key': key, 'replayed': True, 'count_id': prior['id'], **await read(conn, store, prior['business_date'])}
        latest = await conn.fetchrow('''SELECT id,revision FROM prep_inventory.bulk_quick_counts WHERE store_id=$1 AND business_date=$2
            ORDER BY revision DESC LIMIT 1''', store, body.business_date)
        if (latest['revision'] if latest else 0) != expected: raise HTTPException(409, 'Quick Bulk count changed. Refresh before correcting.')
        _, found = await items(conn, store)
        if not found: raise HTTPException(409, 'This store has no active to-par Bulk items to count')
        scope = {i['product_id']: i for i in found}
        sent = {str(l.product_id): l.quantity for l in body.lines}
        missing = [i['name'] for i in found if i['product_id'] not in sent]
        if missing: raise HTTPException(422, f"Count every Bulk item; a missing count is not zero: {', '.join(missing)}")
        if set(sent) - set(scope): raise HTTPException(422, 'Only count active to-par Bulk items here')
        changed = [scope[str(l.product_id)]['name'] for l in body.lines if str(l.profile_id) != scope[str(l.product_id)]['profile_id']]
        if changed: raise HTTPException(409, f"The counting unit changed for: {', '.join(changed)}. Refresh and count them in the current unit.")
        lines =[{'line_number': n, 'product_id': i['product_id'], 'product_version_id': i['product_version_id'], 'profile_id': i['profile_id'],
            'base_unit': i['base_unit'], 'quantity': sent[i['product_id']], 'factor': i['factor'],
            'base_quantity': mapping.times(sent[i['product_id']], i['factor'])} for n, i in enumerate(sorted(found, key=lambda i: i['product_id']), 1)]
        review = serial({'store_id': store, 'business_date': body.business_date, 'lines': lines})
        ident = await conn.fetchval('''INSERT INTO prep_inventory.bulk_quick_counts(store_id,business_date,revision,predecessor_id,performed_at,timezone_name,
            note,actor,review_snapshot,request_key,request_fingerprint) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING id''',
            store, body.business_date, expected + 1, latest['id'] if latest else None, body.performed_at, STORE_ZONE, body.note, actor, review, key, digest)
        for l in lines:
            await conn.execute('''INSERT INTO prep_inventory.bulk_quick_count_lines(count_id,store_id,line_number,product_id,product_version_id,profile_id,
                base_unit,quantity,factor,base_quantity) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)''', ident, store, l['line_number'], UUID(l['product_id']),
                UUID(l['product_version_id']), UUID(l['profile_id']), l['base_unit'], l['quantity'], l['factor'], l['base_quantity'])
        return {'request_key': key, 'replayed': False, 'count_id': ident, **await read(conn, store, body.business_date)}


def expected_revision(request):
    raw = request.headers.get('if-match', '').strip('"')
    if not raw: raise HTTPException(428, "Refresh the night's quick count and supply its version; zero means none yet")
    if not raw.isdigit() or not 0 <= int(raw) < 2**31 - 1: raise HTTPException(422, 'Supply a valid quick Bulk count version')
    return int(raw)


def install_routes(router, context):
    @router.get('/{store_id}/bulk-quick-counts')
    async def read_counts(store_id: str, request: Request, night: date):
        _, pool = await context(request, store_id)
        async with pool.acquire() as conn, conn.transaction(isolation='repeatable_read', readonly=True): return await read(conn, store_id, night)

    # Nightly counts are accepted by the store's managers (backend/positions.py accept_staff_work).
    @router.post('/{store_id}/bulk-quick-counts')
    async def write_count(store_id: str, body: QuickCountIn, request: Request, idempotency_key: UUID = Header(...)):
        actor, pool = await context(request, store_id, True, require='accept_staff_work')
        return serial(await save(pool, store_id, actor, body, idempotency_key, expected_revision(request)))
