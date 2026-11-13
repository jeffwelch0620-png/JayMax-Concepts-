"""M6 prep against sales (Jeff 2026-11-13).

Menu portions say which prep items one sold Toast menu item or modifier uses, and how much, in the prep
item's own base unit. Owners and the Operations & Integration Lead set them (positions.py set_portions);
the General Manager and above see them with the rest of Analytics.

The analytics section compares, for each prep item over a date range:
  used    = opening count + made - nested use - wasted - closing count   (counts only when both exist)
          = made - nested use - wasted                                    (otherwise)
  implied = sum over days of Toast sold quantity x the portion that stood that day
  gap     = used - implied
A positive gap means more left the shelf than sales explain (bigger portions, waste not recorded, staff
meals); a negative gap means sales imply more than was made (smaller portions, prep not recorded, or prep
made before the range). Menu items with no portions show as missing, never as zero use.

Read only on food records: portions are a planning reference. Nothing here changes stock, food or
accounting records and nothing is deducted automatically (Inventory stays the only writer).
"""
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

import analytics
import order_calendar
from purchase_api import serial
from purchase_parser import fingerprint

TABLE = 'prep_inventory.menu_portions'
MENU_DAYS = 90            # the portions screen lists what sold in the last 90 days
MAX_LINES = 20
ROW_LIMIT = 50            # prep items shown in the analytics section
NO_PREP = None            # the line key of the "uses no tracked prep" marker


class Line(BaseModel):
    model_config = ConfigDict(extra='forbid')
    product_id: UUID
    base_quantity: Decimal = Field(gt=0, lt=1000000)

    @field_validator('base_quantity')
    @classmethod
    def places(cls, value):
        if not value.is_finite() or -value.normalize().as_tuple().exponent > 6:
            raise ValueError('Use at most six decimal places')
        return value


class PortionChange(BaseModel):
    """The whole set of prep items one sold item or modifier uses, from a date onward (None: from the start)."""
    model_config = ConfigDict(extra='forbid')
    sold_kind: Literal['item', 'modifier']
    sold_guid: UUID
    sold_name: str = Field(min_length=1, max_length=200)
    effective_from: date | None = None
    no_prep: bool = False
    lines: list[Line] = Field(default_factory=list, max_length=MAX_LINES)
    reason: str = Field(default='', max_length=500)

    @field_validator('sold_name', 'reason')
    @classmethod
    def clean(cls, value):
        value = value.strip()
        if any(ord(c) < 32 for c in value): raise ValueError('Use plain text')
        return value

    @model_validator(mode='after')
    def shape(self):
        if not self.sold_name: raise ValueError('Name the menu item')
        if self.no_prep and self.lines: raise ValueError('An item that uses no tracked prep has no portions')
        if len({line.product_id for line in self.lines}) != len(self.lines): raise ValueError('List each prep item once')
        return self


def lines_on(rows, day):
    """The lines that stand on a business date: for each prep item (and the no-prep marker), the most recently
    recorded row whose effective_from is on or before the date. Returns ({product_id: quantity > 0}, no_prep)."""
    best = {}
    for r in rows:
        if r['effective_from'] is not None and day is not None and r['effective_from'] > day: continue
        key = r['product_id']
        if key not in best or r['recorded_at'] > best[key]['recorded_at']: best[key] = r
    marker = best.pop(NO_PREP, None)
    return ({k: Decimal(r['base_quantity']) for k, r in best.items() if r['base_quantity'] > 0},
            bool(marker and marker['base_quantity'] > 0))


async def installed(conn):
    return await conn.fetchval('SELECT to_regclass($1) IS NOT NULL', TABLE)


async def products(conn, store):
    """The store's prep items with their current name and the track of their latest plan (none if not planned)."""
    plans = (f'LEFT JOIN {analytics.PLANS} pl ON pl.product_id=p.id' if await analytics._has(conn, 'prep_inventory.planning_versions')
             else 'LEFT JOIN (SELECT NULL::uuid AS product_id, NULL::text AS track) pl ON false')
    return [dict(r) for r in await conn.fetch(f'''SELECT p.id AS product_id, coalesce(n.name, p.identity_key) AS name, p.base_unit, pl.track
        FROM prep_inventory.products p LEFT JOIN {analytics.NAMES} n ON n.product_id=p.id {plans}
        WHERE p.store_id=$1 ORDER BY lower(coalesce(n.name, p.identity_key))''', store)]


async def portion_rows(conn, store, kind=None, guid=None):
    return await conn.fetch(f'''SELECT * FROM {TABLE} WHERE store_id=$1 AND ($2::text IS NULL OR sold_kind=$2)
        AND ($3::uuid IS NULL OR sold_guid=$3) ORDER BY recorded_at, id''', store, kind, guid)


SOLD = '''SELECT 'item' AS kind, s.item_guid AS guid, min(s.display_name) AS name, sum(s.quantity) AS quantity, sum(s.net_amount) AS amount
        FROM integrations.toast_item_sales s JOIN integrations.toast_location_map m ON m.toast_restaurant_guid=s.toast_restaurant_guid
        WHERE m.store_id=$1 AND s.business_date BETWEEN $2 AND $3 AND s.item_guid IS NOT NULL GROUP BY s.item_guid
    UNION ALL
    SELECT 'modifier', s.option_guid, min(s.display_name), sum(s.quantity), sum(s.amount)
        FROM integrations.toast_modifier_sales s JOIN integrations.toast_location_map m ON m.toast_restaurant_guid=s.toast_restaurant_guid
        WHERE m.store_id=$1 AND s.business_date BETWEEN $2 AND $3 AND s.option_guid IS NOT NULL GROUP BY s.option_guid'''


async def menu(conn, store, today):
    """What sold in the last 90 days (plus anything that already has portions) with the portions that stand today."""
    toast = analytics.TOAST_STORE.get(store)
    if toast is None or not await analytics.toast_readable(conn): return {'available': False, 'reason': 'toast'}
    if not await installed(conn): return {'available': False, 'reason': 'migration'}
    sold = {(r['kind'], r['guid']): dict(r) for r in await conn.fetch(SOLD, toast, today - timedelta(days=MENU_DAYS), today)}
    grouped = {}
    for r in await portion_rows(conn, store):
        grouped.setdefault((r['sold_kind'], r['sold_guid']), []).append(r)
    out = []
    for key in set(sold) | set(grouped):
        s = sold.get(key) or {'kind': key[0], 'guid': key[1], 'name': grouped[key][-1]['sold_name'], 'quantity': Decimal(0), 'amount': Decimal(0)}
        lines, no_prep = lines_on(grouped.get(key, []), today)
        rows = grouped.get(key, [])
        out.append({**s, 'no_prep': no_prep, 'lines': [{'product_id': k, 'base_quantity': v} for k, v in lines.items()],
                    'status': 'mapped' if lines else 'no_prep' if no_prep else 'missing',
                    'changes': len({r['request_key'] for r in rows}), 'last_changed_at': rows[-1]['recorded_at'] if rows else None})
    out.sort(key=lambda r: (r['kind'] != 'item', -(r['amount'] or 0), -(r['quantity'] or 0), r['name']))
    return {'available': True, 'days': MENU_DAYS, 'products': await products(conn, store), 'sold': out}


async def save(pool, store, actor, body, key):
    digest = fingerprint(serial({'store': store, 'actor': actor, 'change': body.model_dump(mode='json')})).hex()
    async with pool.acquire() as conn, conn.transaction():
        if not await installed(conn): raise HTTPException(503, 'Menu portions are awaiting their migration')
        toast = analytics.TOAST_STORE.get(store)
        if toast is None or not await analytics.toast_readable(conn): raise HTTPException(503, 'Toast sales are not available to this server')
        await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('menu-portions:'||$1||':'||$2,0))", store, str(body.sold_guid))
        prior = await conn.fetch(f'SELECT * FROM {TABLE} WHERE request_key=$1', key)
        if prior:
            if any(r['store_id'] != store or r['recorded_by'] != actor or r['request_fingerprint'] != digest for r in prior):
                raise HTTPException(409, 'Request key belongs to another portion change')
            return serial({'saved': len(prior), 'replayed': True})
        table = 'toast_item_sales' if body.sold_kind == 'item' else 'toast_modifier_sales'
        column = 'item_guid' if body.sold_kind == 'item' else 'option_guid'
        if not await conn.fetchval(f'''SELECT EXISTS(SELECT 1 FROM integrations.{table} s JOIN integrations.toast_location_map m
                ON m.toast_restaurant_guid=s.toast_restaurant_guid WHERE m.store_id=$1 AND s.{column}=$2)''', toast, body.sold_guid):
            raise HTTPException(422, 'That menu item has no Toast sales at this store')
        wanted = {line.product_id: line.base_quantity for line in body.lines}
        units = {r['id']: r['base_unit'] for r in await conn.fetch(
            'SELECT id, base_unit FROM prep_inventory.products WHERE store_id=$1 AND id=ANY($2::uuid[])', store, list(wanted))}
        if set(units) != set(wanted): raise HTTPException(422, "Choose this store's prep items")
        history = await portion_rows(conn, store, body.sold_kind, body.sold_guid)
        # Lines used before but left out now are set to zero from the same date; the marker is written once used.
        earlier = {r['product_id']: r['base_unit'] for r in history if r['product_id'] is not None}
        rows = [(p, units[p], q) for p, q in wanted.items()]
        rows += [(p, earlier[p], Decimal(0)) for p in sorted(set(earlier) - set(wanted))]
        if body.no_prep or any(r['product_id'] is None for r in history):
            rows.append((None, None, Decimal(1 if body.no_prep else 0)))
        if not rows: raise HTTPException(422, 'Add a prep item or mark the item as using no tracked prep')
        for product, unit, quantity in rows:
            await conn.execute(f'''INSERT INTO {TABLE}(id,store_id,sold_kind,sold_guid,sold_name,product_id,base_unit,base_quantity,
                effective_from,reason,recorded_by,request_key,request_fingerprint) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)''',
                uuid4(), store, body.sold_kind, body.sold_guid, body.sold_name, product, unit, quantity, body.effective_from,
                body.reason, actor, key, digest)
        return serial({'saved': len(rows), 'replayed': False})


async def history(conn, store, kind, guid):
    if not await installed(conn): return {'available': False}
    names = {r['product_id']: r['name'] for r in await products(conn, store)}
    return {'available': True, 'changes': [{**dict(r), 'product_name': names.get(r['product_id'])}
                                           for r in reversed(await portion_rows(conn, store, kind, guid))]}


# ---- Analytics section ----------------------------------------------------------------------------

async def prep_against_sales(conn, store, start, end, track):
    toast = analytics.TOAST_STORE.get(store)
    if toast is None or not await installed(conn) or not await analytics.toast_readable(conn): return {'available': False}
    if not await analytics._has(conn, 'prep_inventory.batch_events', 'prep_inventory.batch_movements',
                                'prep_inventory.observations', 'prep_inventory.waste_movements', 'prep_inventory.count_observations'):
        return {'available': False}
    catalog = {r['product_id']: r for r in await products(conn, store)}
    keep = lambda p: p in catalog and (track is None or catalog[p]['track'] == track)

    # Sold per day, and the portions that stood each day.
    sold = await conn.fetch('''SELECT 'item' AS kind, s.business_date, s.item_guid AS guid, min(s.display_name) AS name,
            sum(s.quantity) AS quantity, sum(s.net_amount) AS amount
        FROM integrations.toast_item_sales s JOIN integrations.toast_location_map m ON m.toast_restaurant_guid=s.toast_restaurant_guid
        WHERE m.store_id=$1 AND s.business_date BETWEEN $2 AND $3 AND s.item_guid IS NOT NULL GROUP BY s.business_date, s.item_guid
        UNION ALL
        SELECT 'modifier', s.business_date, s.option_guid, min(s.display_name), sum(s.quantity), sum(s.amount)
        FROM integrations.toast_modifier_sales s JOIN integrations.toast_location_map m ON m.toast_restaurant_guid=s.toast_restaurant_guid
        WHERE m.store_id=$1 AND s.business_date BETWEEN $2 AND $3 AND s.option_guid IS NOT NULL GROUP BY s.business_date, s.option_guid''',
                            toast, start, end)
    open_items = await conn.fetchval('''SELECT coalesce(sum(s.net_amount),0) FROM integrations.toast_item_sales s
        JOIN integrations.toast_location_map m ON m.toast_restaurant_guid=s.toast_restaurant_guid
        WHERE m.store_id=$1 AND s.business_date BETWEEN $2 AND $3 AND s.item_guid IS NULL''', toast, start, end)
    grouped = {}
    for r in await portion_rows(conn, store):
        grouped.setdefault((r['sold_kind'], r['sold_guid']), []).append(r)
    implied, missing, sources = {}, {}, {}
    coverage = {'mapped': Decimal(0), 'no_prep': Decimal(0), 'missing': Decimal(0), 'open_items': analytics._num(open_items)}
    modifiers_mapped = set()
    for r in sold:
        key = (r['kind'], r['guid'])
        lines, no_prep = lines_on(grouped.get(key, []), r['business_date'])
        qty = analytics._num(r['quantity'])
        if r['kind'] == 'item':
            coverage['mapped' if lines else 'no_prep' if no_prep else 'missing'] += analytics._num(r['amount'])
            if not lines and not no_prep:
                m = missing.setdefault(r['guid'], {'kind': 'item', 'guid': r['guid'], 'name': r['name'], 'quantity': Decimal(0), 'amount': Decimal(0)})
                m['quantity'] += qty; m['amount'] += analytics._num(r['amount'])
        elif lines:
            modifiers_mapped.add(r['guid'])
        for product, per in lines.items():
            implied[product] = implied.get(product, Decimal(0)) + qty * per
            s = sources.setdefault(product, {})
            s[key] = s.get(key, {'name': r['name'], 'quantity': Decimal(0), 'use': Decimal(0)})
            s[key]['quantity'] += qty; s[key]['use'] += qty * per

    # Made, used inside other prep, wasted: current revisions only, by business date.
    moves = await conn.fetch('''SELECT m.product_id, m.kind, sum(m.quantity) AS quantity
        FROM prep_inventory.batch_events e JOIN prep_inventory.batch_movements m ON m.event_id=e.id
        WHERE e.store_id=$1 AND e.business_date BETWEEN $2 AND $3 AND e.kind<>'void' AND m.side='apply' AND m.kind IN ('output','prepared_input')
          AND NOT EXISTS (SELECT 1 FROM prep_inventory.batch_events n WHERE n.predecessor_id=e.id)
        GROUP BY m.product_id, m.kind''', store, start, end)
    wasted = await conn.fetch('''SELECT o.product_id, -sum(m.quantity) AS quantity
        FROM prep_inventory.observations o JOIN prep_inventory.waste_movements m ON m.event_id=o.id
        WHERE o.store_id=$1 AND o.purpose='waste' AND o.kind<>'void' AND o.product_id IS NOT NULL AND o.business_date BETWEEN $2 AND $3
          AND m.side='apply' AND NOT EXISTS (SELECT 1 FROM prep_inventory.observations x WHERE x.predecessor_id=o.id)
        GROUP BY o.product_id''', store, start, end)
    # Counts: the day before the range (opening) and the last day of it (closing), latest count that day.
    counts = await conn.fetch('''SELECT DISTINCT ON (c.product_id, o.business_date) c.product_id, o.business_date, c.base_quantity
        FROM prep_inventory.observations o JOIN prep_inventory.count_observations c ON c.event_id=o.id
        WHERE o.store_id=$1 AND o.purpose='count' AND o.kind<>'void' AND o.business_date IN ($2::date - 1, $3::date)
          AND NOT EXISTS (SELECT 1 FROM prep_inventory.observations x WHERE x.predecessor_id=o.id)
        ORDER BY c.product_id, o.business_date, o.performed_at DESC''', store, start, end)
    made, nested, waste = {}, {}, {}
    for r in moves:
        (made if r['kind'] == 'output' else nested)[r['product_id']] = abs(analytics._num(r['quantity']))
    for r in wasted: waste[r['product_id']] = analytics._num(r['quantity'])
    opening = {r['product_id']: analytics._num(r['base_quantity']) for r in counts if r['business_date'] < start}
    closing = {r['product_id']: analytics._num(r['base_quantity']) for r in counts if r['business_date'] == end}
    mapped_products = {r['product_id'] for rows in grouped.values() for r in rows if r['product_id'] is not None}

    out = []
    for p in sorted(p for p in set(made) | set(nested) | set(waste) | set(implied) | mapped_products if keep(p)):
        counted = p in opening and p in closing
        used = made.get(p, Decimal(0)) - nested.get(p, Decimal(0)) - waste.get(p, Decimal(0))
        if counted: used += opening[p] - closing[p]
        has_portions = p in mapped_products
        use = implied.get(p, Decimal(0)) if has_portions else None
        gap = used - use if use is not None else None
        top = sorted(sources.get(p, {}).values(), key=lambda s: -s['use'])[:5]
        out.append({'product_id': p, 'name': catalog[p]['name'], 'unit': catalog[p]['base_unit'], 'track': catalog[p]['track'],
                    'made': made.get(p, Decimal(0)), 'nested_use': nested.get(p, Decimal(0)), 'wasted': waste.get(p, Decimal(0)),
                    'opening': opening.get(p) if counted else None, 'closing': closing.get(p) if counted else None, 'counts_used': counted,
                    'used': used, 'implied': use, 'gap': gap, 'has_portions': has_portions,
                    'gap_percent': round(gap / use * 100) if gap is not None and use else None, 'from_sales': top})
    out.sort(key=lambda r: (not r['has_portions'], -abs(r['gap_percent'] or 0), r['name']))
    total = coverage['mapped'] + coverage['no_prep'] + coverage['missing'] + coverage['open_items']
    days = await conn.fetch('SELECT business_date, status FROM integrations.toast_daily_sales WHERE store_id=$1 AND business_date BETWEEN $2 AND $3',
                            toast, start, end)
    return {'available': True, 'items': out[:ROW_LIMIT], 'item_count': len(out),
            'coverage': {**coverage, 'total': total,
                         'covered_percent': round((coverage['mapped'] + coverage['no_prep']) / total * 100) if total else None},
            'missing_items': sorted(missing.values(), key=lambda m: -m['amount'])[:analytics.LIST_LIMIT], 'missing_count': len(missing),
            'modifiers_with_portions': len(modifiers_mapped),
            'sales_days': len(days), 'sales_days_complete': sum(d['status'] == 'complete' for d in days), 'range_days': (end - start).days + 1}


# ---- Routes -----------------------------------------------------------------------------------------

def create_router(pool_factory, store_check, manager_authorize, clock=lambda: datetime.now().astimezone()):
    router = APIRouter()

    def today():
        return clock().astimezone(ZoneInfo(order_calendar.DEFAULT_ZONE)).date()

    def can_edit(request, store):
        try:
            manager_authorize(request, store, True, require='set_portions'); return True
        except HTTPException as e:
            if e.status_code != 403: raise
            return False

    @router.get('/api/pg/menu-portions/{store}')
    async def read(store: str, request: Request):
        if not analytics.enabled(): raise HTTPException(503, 'Analytics is not switched on')
        store_check(store); manager_authorize(request, store, False, require='see_analytics')
        async with pool_factory().acquire() as conn, conn.transaction(isolation='repeatable_read', readonly=True):
            return serial({**await menu(conn, store, today()), 'can_edit': can_edit(request, store), 'store_id': store})

    @router.get('/api/pg/menu-portions/{store}/history')
    async def read_history(store: str, request: Request, kind: Literal['item', 'modifier'], guid: UUID):
        if not analytics.enabled(): raise HTTPException(503, 'Analytics is not switched on')
        store_check(store); manager_authorize(request, store, False, require='see_analytics')
        async with pool_factory().acquire() as conn, conn.transaction(isolation='repeatable_read', readonly=True):
            return serial(await history(conn, store, kind, guid))

    @router.post('/api/pg/menu-portions/{store}')
    async def change(store: str, body: PortionChange, request: Request, idempotency_key: UUID = Header(...)):
        if not analytics.enabled(): raise HTTPException(503, 'Analytics is not switched on')
        store_check(store)
        actor = manager_authorize(request, store, True, require='set_portions')
        return await save(pool_factory(), store, actor, body, idempotency_key)

    return router
