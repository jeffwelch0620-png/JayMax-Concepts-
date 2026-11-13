"""M6 analytics (Jeff 2026-11-06): how a store's prep, counts and orders went over a date range,
split by prep track (Daily, Bulk, Salad). The General Manager and above see it (positions.py
see_analytics), each for the stores they are assigned to.

A read only: every number comes from the records the workflows already keep, at their latest
revision. Nothing here writes, and no table or view is added: switched off, the routes answer 503
and the database is untouched. Quantities are compared item by item in each item's own unit;
nothing adds pounds to quarts.
"""
import json
import os
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from statistics import median
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request

import order_calendar
from purchase_api import serial

TRACKS = ('daily', 'bulk', 'salad')
MAX_DAYS = 92                    # one quarter per read
LIST_LIMIT = 15                  # rows shown under each tile
STORE_WIDE = {'available': True, 'store_wide': True}   # not split by track: shown with All tracks only


def enabled():
    return os.getenv('ANALYTICS_ENABLED', 'false').lower() == 'true'


async def _has(conn, *tables):
    return all([await conn.fetchval('SELECT to_regclass($1) IS NOT NULL', t) for t in tables])


def _num(value):
    return Decimal(value) if value is not None else Decimal(0)


def _minutes(rows):
    """Count, median, average and longest wait in whole minutes."""
    waits = [r['minutes'] for r in rows if r['minutes'] is not None]
    if not waits: return {'median_minutes': None, 'average_minutes': None, 'longest_minutes': None}
    return {'median_minutes': round(median(waits)), 'average_minutes': round(sum(waits) / len(waits)), 'longest_minutes': round(max(waits))}


NAMES = '''(SELECT DISTINCT ON (v.product_id) v.product_id, v.name FROM prep_inventory.product_versions v
    WHERE v.store_id=$1 AND NOT EXISTS (SELECT 1 FROM prep_inventory.product_versions n WHERE n.predecessor_id=v.id)
    ORDER BY v.product_id, v.revision DESC)'''
PLANS = '''(SELECT DISTINCT ON (product_id) product_id, track FROM prep_inventory.planning_versions
    WHERE store_id=$1 ORDER BY product_id, revision DESC)'''


async def throughput(conn, store, start, end, track, today):
    """Released prep lists: each included task's planned amount against what was made and accepted
    (prep_inventory.task_progress). A task met plan when made >= planned; a past task that didn't is short."""
    if not await _has(conn, 'prep_inventory.day_tasks', 'prep_inventory.execution_events') \
            or not await conn.fetchval("SELECT to_regprocedure('prep_inventory.task_progress(uuid)') IS NOT NULL"):
        return {'available': False}
    lists = await conn.fetch('''SELECT l.id, l.prep_date, l.track, p.action AS phase, p.draft_version_id
        FROM prep_inventory.day_lists l LEFT JOIN LATERAL (SELECT e.action, e.draft_version_id FROM prep_inventory.execution_events e
            WHERE e.list_id=l.id AND e.action IN ('release','reopen') ORDER BY e.revision DESC LIMIT 1) p ON true
        WHERE l.store_id=$1 AND l.prep_date BETWEEN $2 AND $3 AND ($4::text IS NULL OR l.track=$4)''', store, start, end, track)
    released = [l['draft_version_id'] for l in lists if l['phase'] == 'release']
    tasks = await conn.fetch(f'''SELECT t.id, l.prep_date, l.track, t.planned_base_quantity AS planned,
            (t.task_snapshot->>'needed_base_quantity')::numeric AS needed, coalesce(t.task_snapshot->>'name', n.name) AS name,
            pr.base_unit, prep_inventory.task_progress(t.id) AS progress
        FROM prep_inventory.day_tasks t JOIN prep_inventory.day_list_versions v ON v.id=t.version_id
        JOIN prep_inventory.day_lists l ON l.id=v.list_id JOIN prep_inventory.products pr ON pr.id=t.product_id
        LEFT JOIN {NAMES} n ON n.product_id=t.product_id
        WHERE t.store_id=$1 AND t.version_id=ANY($2::uuid[]) AND t.included AND t.planned_base_quantity>0
        ORDER BY l.prep_date, l.track, t.ordinal''', store, released)
    by_track, short = {}, []
    for t in tasks:
        p = t['progress'] if isinstance(t['progress'], dict) else json.loads(t['progress'])
        made, planned = _num(p['effective_base_quantity']), _num(t['planned'])
        s = by_track.setdefault(t['track'], {'track': t['track'], 'tasks': 0, 'met_plan': 0, 'short': 0, 'complete': 0, 'needs_review': 0, 'percents': []})
        s['tasks'] += 1
        s['complete'] += p['status'] == 'complete'
        s['needs_review'] += bool(p['needs_review'])
        s['percents'].append(made / planned * 100)
        if made >= planned: s['met_plan'] += 1
        elif t['prep_date'] < today:
            s['short'] += 1
            short.append({'prep_date': t['prep_date'], 'track': t['track'], 'name': t['name'], 'unit': t['base_unit'],
                          'needed': t['needed'], 'planned': planned, 'made': made, 'short_by': planned - made})
    tracks = []
    for s in by_track.values():
        percents = s.pop('percents')
        tracks.append({**s, 'average_percent_of_plan': round(sum(percents) / len(percents)) if percents else None})
    lists_out = {'released': sum(l['phase'] == 'release' for l in lists),
                 'not_released': sum(l['phase'] != 'release' and l['prep_date'] <= today for l in lists)}
    short.sort(key=lambda r: (r['prep_date'], r['short_by'] / r['planned']), reverse=True)
    return {'available': True, 'lists': lists_out, 'tracks': sorted(tracks, key=lambda r: TRACKS.index(r['track'])),
            'tasks': sum(s['tasks'] for s in tracks), 'met_plan': sum(s['met_plan'] for s in tracks),
            'short': sum(s['short'] for s in tracks), 'short_tasks': short[:LIST_LIMIT]}


async def shortages(conn, store, start, end, track):
    """Shortage notes cooks sent the Shift Leader (M5), by reason and track."""
    if not await _has(conn, 'prep_inventory.staff_shortage_reports'): return {'available': False}
    rows = await conn.fetch('''SELECT business_date, track, reason, short_quantity, identity_verified,
            coalesce(task_snapshot->>'name', task_snapshot->'task_snapshot'->>'name') AS name
        FROM prep_inventory.staff_shortage_reports WHERE store_id=$1 AND business_date BETWEEN $2 AND $3 AND ($4::text IS NULL OR track=$4)
        ORDER BY business_date DESC, reported_at DESC''', store, start, end, track)
    count = lambda key: {k: sum(r[key] == k for r in rows) for k in sorted({r[key] for r in rows})}
    return {'available': True, 'reports': len(rows), 'verified': sum(r['identity_verified'] for r in rows),
            'by_reason': count('reason'), 'by_track': count('track'), 'latest': [dict(r) for r in rows[:LIST_LIMIT]]}


async def waste(conn, store, start, end, track):
    """Waste recorded (container waste is already a waste record), current revisions only, per item in its unit.
    Purchased items carry no track, so they show only when no track is chosen. Grouped by the waste category the
    manager chose (storage spoilage, service discard, other); o.reason is the free-text note."""
    if not await _has(conn, 'prep_inventory.observations', 'prep_inventory.waste_movements'): return {'available': False}
    rows = await conn.fetch(f'''SELECT o.id, o.business_date, o.review_snapshot->'body'->>'category' AS category, o.base_unit, o.product_id, o.raw_item_code,
            coalesce(n.name, i.name, o.raw_item_code) AS name, pl.track,
            -sum(m.quantity) FILTER (WHERE m.side='apply') AS quantity
        FROM prep_inventory.observations o JOIN prep_inventory.waste_movements m ON m.event_id=o.id
        LEFT JOIN {NAMES} n ON n.product_id=o.product_id LEFT JOIN {PLANS} pl ON pl.product_id=o.product_id
        LEFT JOIN public.items i ON i.code=o.raw_item_code
        WHERE o.store_id=$1 AND o.purpose='waste' AND o.kind<>'void' AND o.business_date BETWEEN $2 AND $3
          AND NOT EXISTS (SELECT 1 FROM prep_inventory.observations x WHERE x.predecessor_id=o.id)
        GROUP BY o.id, n.name, i.name, pl.track''', store, start, end)
    rows = [r for r in rows if track is None or r['track'] == track]
    items = {}
    for r in rows:
        key = (r['product_id'] or r['raw_item_code'], r['base_unit'])
        it = items.setdefault(key, {'name': r['name'], 'unit': r['base_unit'], 'track': r['track'], 'kind': 'prep' if r['product_id'] else 'purchased',
                                    'quantity': Decimal(0), 'entries': 0})
        it['quantity'] += _num(r['quantity']); it['entries'] += 1
    reasons = {}
    for r in rows: reasons[r['category'] or 'other'] = reasons.get(r['category'] or 'other', 0) + 1
    top = sorted(items.values(), key=lambda r: (-r['entries'], r['name']))
    return {'available': True, 'entries': len(rows), 'items': len(items), 'by_reason': reasons, 'top_items': top[:LIST_LIMIT]}


async def acceptance(conn, store, start, end, track, zone):
    """How long staff work waited for a manager: submitted to accepted or sent back, by the day it was decided.
    Nightly and prep counts cover the whole store; cook output follows the track."""
    out = {}
    pairs = [('nightly_counts', 'actual_inventory', None), ('prep_counts', 'prep_inventory', None)]
    for key, schema, _ in pairs:
        if not await _has(conn, f'{schema}.staff_decisions'): out[key] = {'available': False}; continue
        decided = await conn.fetch(f'''SELECT d.decision, extract(epoch FROM d.reviewed_at - s.submitted_at)/60 AS minutes
            FROM {schema}.staff_decisions d LEFT JOIN LATERAL (SELECT u.submitted_at FROM {schema}.staff_submissions u
                WHERE u.sheet_id=d.sheet_id AND (u.id=d.submission_id OR (d.submission_id IS NULL AND u.submitted_at<=d.reviewed_at))
                ORDER BY (u.id=d.submission_id) DESC, u.submitted_at DESC LIMIT 1) s ON true
            WHERE d.store_id=$1 AND (d.reviewed_at AT TIME ZONE $4)::date BETWEEN $2 AND $3''', store, start, end, zone)
        waiting = await conn.fetchval(f'''SELECT count(DISTINCT s.id) FROM {schema}.staff_sheets s JOIN {schema}.staff_submissions u ON u.sheet_id=s.id
            WHERE s.store_id=$1 AND (u.submitted_at AT TIME ZONE $4)::date BETWEEN $2 AND $3
              AND NOT EXISTS (SELECT 1 FROM {schema}.staff_decisions d WHERE d.sheet_id=s.id)''', store, start, end, zone)
        out[key] = {'available': True, 'decided': len(decided), 'accepted': sum(r['decision'] == 'accepted' for r in decided),
                    'sent_back': sum(r['decision'] == 'rejected' for r in decided), 'waiting': waiting, **_minutes(decided)}
    if not await _has(conn, 'prep_inventory.staff_production_decisions'):
        out['output'] = {'available': False}
    else:
        decided = await conn.fetch('''SELECT d.decision, extract(epoch FROM d.recorded_at - s.recorded_at)/60 AS minutes
            FROM prep_inventory.staff_production_decisions d JOIN prep_inventory.staff_production_submissions s ON s.id=d.submission_id
            WHERE d.store_id=$1 AND (d.recorded_at AT TIME ZONE $4)::date BETWEEN $2 AND $3 AND ($5::text IS NULL OR s.review_snapshot->>'track'=$5)''',
            store, start, end, zone, track)
        waiting = await conn.fetchval('''SELECT count(*) FROM prep_inventory.staff_production_submissions s
            WHERE s.store_id=$1 AND s.kind='submit' AND (s.recorded_at AT TIME ZONE $4)::date BETWEEN $2 AND $3
              AND ($5::text IS NULL OR s.review_snapshot->>'track'=$5)
              AND NOT EXISTS (SELECT 1 FROM prep_inventory.staff_production_submissions n WHERE n.root_id=s.root_id AND n.revision>s.revision)
              AND NOT EXISTS (SELECT 1 FROM prep_inventory.staff_production_decisions d WHERE d.submission_id=s.id)''', store, start, end, zone, track)
        out['output'] = {'available': True, 'decided': len(decided), 'accepted': sum(r['decision'] == 'accepted' for r in decided),
                         'sent_back': sum(r['decision'] == 'rejected' for r in decided), 'waiting': waiting, **_minutes(decided)}
    return out


async def transfers(conn, store, start, end, track):
    """Bulk supply (always the Bulk track) asked, sent, held and accepted, and store-to-store transfers
    sent and received, where this store is either end. A difference is listed item by item."""
    out = {}
    if track not in (None, 'bulk'):
        out['bulk'] = STORE_WIDE
    elif not await _has(conn, 'prep_inventory.bulk_requests', 'prep_inventory.bulk_event_lines'):
        out['bulk'] = {'available': False}
    else:
        rows = await conn.fetch('''SELECT r.id, r.store_id, r.maker_store_id, r.run_date, r.kind, q.ordinal, q.base_unit, q.requested_base_quantity AS requested,
                (SELECT l->>'name' FROM jsonb_array_elements(r.review_snapshot->'lines') l WHERE (l->>'ordinal')::int=q.ordinal LIMIT 1) AS name,
                f.base_quantity AS sent, f.held_base_quantity AS held, a.base_quantity AS accepted,
                EXISTS (SELECT 1 FROM prep_inventory.bulk_events c WHERE c.request_id=r.id AND c.action='cancel') AS cancelled
            FROM prep_inventory.bulk_requests r JOIN prep_inventory.bulk_request_lines q ON q.request_id=r.id
            LEFT JOIN (prep_inventory.bulk_event_lines f JOIN prep_inventory.bulk_events fe ON fe.id=f.event_id AND fe.action='fulfill')
                ON f.request_id=r.id AND f.ordinal=q.ordinal
            LEFT JOIN (prep_inventory.bulk_event_lines a JOIN prep_inventory.bulk_events ae ON ae.id=a.event_id AND ae.action='accept')
                ON a.request_id=r.id AND a.ordinal=q.ordinal
            WHERE $1 IN (r.store_id, r.maker_store_id) AND r.run_date BETWEEN $2 AND $3
            ORDER BY r.run_date DESC, r.created_at DESC, q.ordinal''', store, start, end)
        requests = {}
        for r in rows:
            requests.setdefault(r['id'], {'cancelled': r['cancelled'], 'sent': r['sent'] is not None, 'accepted': r['accepted'] is not None})
        differences = []
        for r in rows:
            if r['cancelled'] or r['accepted'] is None: continue
            owed = max(_num(r['requested']) - _num(r['accepted']) - _num(r['held']), Decimal(0))
            lost = _num(r['sent']) - _num(r['accepted'])
            if owed or lost:
                differences.append({'run_date': r['run_date'], 'from_store_id': r['maker_store_id'], 'to_store_id': r['store_id'], 'kind': r['kind'],
                                    'name': r['name'], 'unit': r['base_unit'], 'requested': r['requested'], 'sent': r['sent'], 'held': r['held'],
                                    'accepted': r['accepted'], 'still_owed': owed, 'sent_not_accepted': lost})
        out['bulk'] = {'available': True, 'requests': len(requests), 'cancelled': sum(q['cancelled'] for q in requests.values()),
                       'accepted': sum(q['accepted'] and not q['cancelled'] for q in requests.values()),
                       'open': sum(not q['accepted'] and not q['cancelled'] for q in requests.values()),
                       'lines_short': len(differences), 'differences': differences[:LIST_LIMIT]}
    if track is not None:
        out['store'] = STORE_WIDE
    elif not await _has(conn, 'actual_inventory.store_transfer_events'):
        out['store'] = {'available': False}
    else:
        rows = await conn.fetch('''SELECT t.id, t.from_store_id, t.to_store_id, t.sent_date, t.item_code, i.name, t.base_unit,
                t.sent_base_quantity AS sent, t.cost_amount, t.cost_base_quantity, e.action, e.received_base_quantity AS received
            FROM actual_inventory.store_transfers t LEFT JOIN public.items i ON i.code=t.item_code
            LEFT JOIN actual_inventory.store_transfer_events e ON e.transfer_id=t.id
            WHERE $1 IN (t.from_store_id, t.to_store_id) AND t.sent_date BETWEEN $2 AND $3 ORDER BY t.sent_date DESC, t.created_at DESC''', store, start, end)
        differences = []
        for r in rows:
            if r['action'] != 'receive' or r['received'] == r['sent']: continue
            short = r['sent'] - r['received']
            cost = (r['cost_amount'] / r['cost_base_quantity'] * short).quantize(Decimal('0.01')) if r['cost_amount'] is not None and r['cost_base_quantity'] else None
            differences.append({'sent_date': r['sent_date'], 'from_store_id': r['from_store_id'], 'to_store_id': r['to_store_id'], 'name': r['name'] or r['item_code'],
                                'unit': r['base_unit'], 'sent': r['sent'], 'received': r['received'], 'short': short, 'short_cost': cost})
        out['store'] = {'available': True, 'transfers': len(rows), 'received': sum(r['action'] == 'receive' for r in rows),
                        'cancelled': sum(r['action'] == 'cancel' for r in rows), 'open': sum(r['action'] is None for r in rows),
                        'received_short': len(differences), 'differences': differences[:LIST_LIMIT]}
    return out


def deadline(value):
    """A weekly day restored from before a schedule change keeps its deadlines as 'HH:MM' text
    (order_calendar.day_view); today's rows have times."""
    return time.fromisoformat(value) if isinstance(value, str) else value


async def on_time(conn, store, start, end, now):
    """Each order cycle in the range under the schedule that stood on its day (skips and moves included):
    the count and each supplier's order done on time, late or still overdue, with the late reasons kept."""
    if not await order_calendar.installed(conn): return {'available': False}
    rows = await conn.fetch('SELECT * FROM purchasing.order_calendar WHERE store_id=$1 ORDER BY order_weekday', store)
    day_changes = await conn.fetch('''SELECT order_weekday,day_before,changed_at FROM purchasing.order_schedule_changes
        WHERE store_id=$1 AND kind IN ('set_day','remove_day') ORDER BY changed_at,id''', store) if await order_calendar.schedule_ready(conn) else []
    if not rows and not day_changes: return {'available': True, 'has_calendar': False, 'cycles': 0}
    tz = order_calendar.zone(rows)
    today = now.astimezone(tz).date()
    exc = await order_calendar.exceptions(conn, store, start, end)
    cycles = []
    for n in range((end - start).days + 1):
        d = start + timedelta(days=n)
        if d > today: break
        at = datetime.combine(d, time(23, 59, 59), tz)
        entry = order_calendar.effective(order_calendar.rows_at(rows, day_changes, at), exc, d, 1).get(d)
        if entry: cycles.append((d, entry))
    out, late = [], []
    counts = {'done': 0, 'late': 0, 'overdue': 0, 'due': 0}
    orders = {'done': 0, 'late': 0, 'overdue': 0, 'due': 0}
    for d, entry in cycles:
        row = entry['row']
        count_due, order_due = datetime.combine(d, deadline(row['count_due']), tz), datetime.combine(d, deadline(row['order_due']), tz)
        count = await conn.fetchrow('''SELECT status,recorded_at FROM actual_inventory.count_snapshots s WHERE store_id=$1 AND count_date=$2
            AND NOT EXISTS(SELECT 1 FROM actual_inventory.count_snapshots c WHERE c.corrects_snapshot_id=s.id)
            ORDER BY recorded_at DESC,id DESC LIMIT 1''', store, d)
        done = count['recorded_at'] if count and count['status'] == 'complete' else None
        cs = order_calendar.status(done, count_due, now, d, today)
        counts[cs] = counts.get(cs, 0) + 1
        submitted = await conn.fetch('''SELECT vendor_id, min(submitted_at) AS submitted_at FROM public.purchase_orders WHERE store_id=$1 AND vendor_id=ANY($2)
            AND archived_at IS NULL AND status NOT IN ('draft','rejected') AND (submitted_at AT TIME ZONE $3)::date=$4 GROUP BY vendor_id''',
            store, list(row['vendor_ids']), str(tz), d)
        by_vendor = {r['vendor_id']: r['submitted_at'] for r in submitted}
        vendors = []
        for vid in row['vendor_ids']:
            vs = order_calendar.status(by_vendor.get(vid), order_due, now, d, today)
            orders[vs] = orders.get(vs, 0) + 1
            vendors.append({'vendor_id': vid, 'status': vs, 'submitted_at': by_vendor.get(vid)})
        out.append({'cycle_date': d, 'moved_from': entry['moved_from'], 'count': cs, 'count_done_at': done, 'orders': vendors})
    if cycles:
        names = {r['id']: r['name'] for r in await conn.fetch('SELECT id,name FROM public.vendors WHERE id=ANY($1)',
                                                             sorted({v['vendor_id'] for c in out for v in c['orders']}))}
        for c in out:
            for v in c['orders']: v['name'] = names.get(v['vendor_id'], v['vendor_id'])
        late = [dict(r) for r in await conn.fetch('''SELECT cycle_date, kind, vendor_id, reason FROM purchasing.order_cycle_notes
            WHERE store_id=$1 AND cycle_date BETWEEN $2 AND $3 ORDER BY cycle_date DESC, recorded_at DESC''', store, start, end)]
        for n in late: n['name'] = names.get(n['vendor_id']) if n['vendor_id'] else None
    return {'available': True, 'has_calendar': True, 'cycles': len(cycles), 'counts': counts, 'orders': orders,
            'cycle_list': list(reversed(out))[:LIST_LIMIT], 'late_reasons': late[:LIST_LIMIT]}


# Toast sales (I3, workspace sql/toast/04 and 08): built server-side from Toast's saved orders, one row per
# store and business day, checked against Toast's own Sales Summary. Read only; JMAX never writes to Toast.
TOAST_STORE = {'berts': 'berts', 'rudds': 'rudds', 'papa': 'papa', 'papa_leonis': 'papa'}
# The daily sync saves yesterday at 10:15 UTC and builds it at 10:45 UTC (about 6 AM Eastern). After 8 AM a
# missing yesterday is late, not just early.
SALES_DUE_HOUR = 8
# Salad Bar covers (proposed rule, to confirm with Jay and Rudd): menu items and add-ons whose Toast name
# contains "salad bar", e.g. "Salad Bar Entree", "Pizza Bar and Salad Bar Combo", "Salad Bar with meal".
SALAD_BAR = '%salad bar%'


TOAST_TABLES = ('integrations.toast_daily_sales', 'integrations.toast_item_sales', 'integrations.toast_modifier_sales',
                'integrations.toast_location_map')


async def toast_readable(conn):
    """The Toast tables are server-only (no anon or authenticated access). A database login that may not read
    them sees the section as not set up, instead of the whole report failing. Schema access is checked first:
    without USAGE on the schema, even resolving a table name in it is a permission error (runtime_permissions.py
    keeps the restricted login out of integrations)."""
    if not await conn.fetchval("""SELECT CASE WHEN to_regnamespace('integrations') IS NULL THEN false
                                      ELSE has_schema_privilege('integrations', 'USAGE') END"""):
        return False
    for table in TOAST_TABLES:
        if not await conn.fetchval("SELECT CASE WHEN to_regclass($1) IS NULL THEN false ELSE has_table_privilege(to_regclass($1), 'SELECT') END", table):
            return False
    return True


async def sales(conn, store, start, end, track, now):
    """Net sales, orders and average check by day from integrations.toast_daily_sales, the same days before
    for comparison, the best-selling items, Salad Bar covers and whether every day has arrived from Toast.
    Store-wide: shown with All tracks; the Salad track sees its Salad Bar covers only."""
    if track not in (None, 'salad'): return STORE_WIDE
    toast = TOAST_STORE.get(store)
    if toast is None or not await toast_readable(conn): return {'available': False}
    zone = ZoneInfo(order_calendar.DEFAULT_ZONE)
    local = now.astimezone(zone)
    today = local.date()
    span = (end - start).days + 1
    rows = await conn.fetch('''SELECT business_date, orders, net_sales, discounts, refunds, status, problems
        FROM integrations.toast_daily_sales WHERE store_id=$1 AND business_date BETWEEN $2 AND $3 ORDER BY business_date''',
                            toast, start - timedelta(days=span), end)
    days = [r for r in rows if r['business_date'] >= start]
    before = [r for r in rows if r['business_date'] < start]
    latest = await conn.fetchval('SELECT max(business_date) FROM integrations.toast_daily_sales WHERE store_id=$1', toast)

    def totals(part):
        net, orders = sum((_num(r['net_sales']) for r in part), Decimal(0)), sum(r['orders'] or 0 for r in part)
        return {'net_sales': net, 'orders': orders, 'average_check': round(net / orders, 2) if orders else None,
                'discounts': sum((_num(r['discounts']) for r in part), Decimal(0)), 'refunds': sum((_num(r['refunds']) for r in part), Decimal(0)),
                'days': len(part), 'open_days': sum(1 for r in part if (r['orders'] or 0) > 0)}

    # Days that should have arrived: through yesterday, and yesterday only once the morning sync is due.
    last_expected = min(end, today - timedelta(days=1) if local.hour >= SALES_DUE_HOUR else today - timedelta(days=2))
    have = {r['business_date'] for r in days}
    missing = [start + timedelta(days=i) for i in range((last_expected - start).days + 1) if start + timedelta(days=i) not in have]
    review = [{'business_date': r['business_date'], 'problems': list(r['problems'] or [])} for r in days if r['status'] != 'complete']
    # The newest saved day, whatever the range: a stalled sync shows even on an older range.
    stale = latest is None or latest < today - timedelta(days=1 if local.hour >= SALES_DUE_HOUR else 2)
    health = {'latest_day': latest, 'missing_days': missing, 'needs_review': review, 'stale': stale}

    covers = await conn.fetch('''SELECT business_date, sum(quantity) AS quantity, sum(amount) AS amount FROM (
            SELECT s.business_date, s.quantity, s.net_amount AS amount FROM integrations.toast_item_sales s
            JOIN integrations.toast_location_map m ON m.toast_restaurant_guid=s.toast_restaurant_guid
            WHERE m.store_id=$1 AND s.business_date BETWEEN $2 AND $3 AND s.display_name ILIKE $4
            UNION ALL
            SELECT s.business_date, s.quantity, s.amount FROM integrations.toast_modifier_sales s
            JOIN integrations.toast_location_map m ON m.toast_restaurant_guid=s.toast_restaurant_guid
            WHERE m.store_id=$1 AND s.business_date BETWEEN $2 AND $3 AND s.display_name ILIKE $4
              -- An add-on on an item that is itself a Salad Bar item is the same cover: count it once.
              AND NOT EXISTS (SELECT 1 FROM integrations.toast_item_sales p WHERE p.toast_restaurant_guid=s.toast_restaurant_guid
                              AND p.business_date=s.business_date AND p.item_key=s.parent_item_key AND p.display_name ILIKE $4)) x
        GROUP BY business_date ORDER BY business_date''', toast, start, end, SALAD_BAR)
    salad = {'covers': sum((_num(r['quantity']) for r in covers), Decimal(0)), 'amount': sum((_num(r['amount']) for r in covers), Decimal(0)),
             'by_day': [dict(r) for r in covers]}
    if track == 'salad':
        return {'available': True, 'track_only': True, 'salad_bar': salad, **health}

    items = await conn.fetch('''SELECT coalesce(s.item_guid::text, s.item_key) AS item, min(s.display_name) AS name,
            sum(s.quantity) AS quantity, sum(s.net_amount) AS net_sales
        FROM integrations.toast_item_sales s JOIN integrations.toast_location_map m ON m.toast_restaurant_guid=s.toast_restaurant_guid
        WHERE m.store_id=$1 AND s.business_date BETWEEN $2 AND $3
        GROUP BY 1 ORDER BY sum(s.net_amount) DESC NULLS LAST, min(s.display_name) LIMIT $4''', toast, start, end, LIST_LIMIT)
    by_day = [{'business_date': r['business_date'], 'orders': r['orders'], 'net_sales': r['net_sales'],
               'average_check': round(_num(r['net_sales']) / r['orders'], 2) if r['orders'] else None, 'status': r['status']} for r in days]
    # The comparison covers the range up to the newest saved day (today is never saved yet), against the same
    # number of days just before. It is fair only when both stretches are fully saved and complete.
    upto = min(end, latest) if latest else None
    compared = (upto - start).days + 1 if upto and upto >= start else 0
    now_part = [r for r in days if r['business_date'] <= upto] if compared else []
    earlier = [r for r in before if r['business_date'] >= start - timedelta(days=compared)] if compared else []
    whole = lambda part: len(part) == compared and all(r['status'] == 'complete' for r in part)
    return {'available': True, 'totals': totals(days),
            'before': {**totals(earlier), 'start': start - timedelta(days=compared), 'end': start - timedelta(days=1),
                       'compared_days': compared, 'complete': compared > 0 and whole(now_part) and whole(earlier)},
            'by_day': by_day, 'top_items': [dict(r) for r in items], 'salad_bar': salad, **health}


async def report(conn, store, start, end, track, now):
    import menu_portions  # imports this module
    zone = order_calendar.DEFAULT_ZONE
    today = now.astimezone(ZoneInfo(zone)).date()
    return serial({'store_id': store, 'start': start, 'end': end, 'track': track, 'today': today, 'timezone_name': zone,
                   'throughput': await throughput(conn, store, start, end, track, today),
                   'shortages': await shortages(conn, store, start, end, track),
                   'waste': await waste(conn, store, start, end, track),
                   'acceptance': await acceptance(conn, store, start, end, track, zone),
                   'transfers': await transfers(conn, store, start, end, track),
                   'on_time': await on_time(conn, store, start, end, now) if track is None else STORE_WIDE,
                   'sales': await sales(conn, store, start, end, track, now),
                   'prep_vs_sales': await menu_portions.prep_against_sales(conn, store, start, end, track)})


def window(start, end, today):
    end = end or today
    start = start or end - timedelta(days=6)
    if start > end: raise HTTPException(422, 'Start must be on or before end')
    if (end - start).days + 1 > MAX_DAYS: raise HTTPException(422, f'Choose at most {MAX_DAYS} days')
    return start, end


def create_router(pool_factory, store_check, manager_authorize, clock=lambda: datetime.now().astimezone()):
    router = APIRouter()

    @router.get('/api/pg/analytics/{store}')
    async def read(store: str, request: Request, start: date | None = None, end: date | None = None, track: str | None = None):
        if not enabled(): raise HTTPException(503, 'Analytics is not switched on')
        store_check(store); manager_authorize(request, store, False, require='see_analytics')
        if track not in (None, *TRACKS): raise HTTPException(422, 'Track must be daily, bulk or salad')
        now = clock()
        start, end = window(start, end, now.astimezone(ZoneInfo(order_calendar.DEFAULT_ZONE)).date())
        async with pool_factory().acquire() as conn, conn.transaction(isolation='repeatable_read', readonly=True):
            return await report(conn, store, start, end, track, now)

    return router
