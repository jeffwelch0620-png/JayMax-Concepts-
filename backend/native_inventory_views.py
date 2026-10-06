"""Read-only operating views of received purchases and dated explicit-value counts."""
import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from purchase_api import serial


async def operating_summary(conn, store_id, as_of=None):
    as_of = as_of or datetime.now(timezone.utc).date()
    start, end = as_of - timedelta(days=29), as_of + timedelta(days=1)
    if not await conn.fetchval("SELECT to_regclass('purchasing.actual_purchase_facts') IS NOT NULL"):
        raise HTTPException(503, 'Native purchase reporting schema is awaiting setup')
    # Aggregate in PostgreSQL numeric: reversals/credits remain signed, future
    # receipts and supplier dates do not change this calendar-day window.
    purchases = await conn.fetchrow('''SELECT coalesce(sum(inventory_cost_amount),0) AS food_amount,
        count(*) AS ledger_entries FROM purchasing.actual_purchase_facts
        WHERE store_id=$1 AND inventory_record_date >= $2 AND inventory_record_date < $3''', store_id, start, end)
    result = {'storeId': store_id, 'basis': 'native_received_purchases_and_explicit_counts',
              'asOfDate': as_of, 'dateBasis': 'UTC calendar date; inventory dates as reviewed',
              'receivedFrom': start, 'receivedBefore': end, 'netFoodPurchases30': purchases['food_amount'],
              'purchaseLedgerEntries30': purchases['ledger_entries'], 'inventoryValue': None,
              'count': None, 'scope': None, 'items': [], 'countStatus': 'awaiting_enablement',
              'liveOnHandAvailable': False, 'orderSuggestionsAvailable': False}
    if os.getenv('ACTUAL_INVENTORY_ENABLED', 'false').lower() != 'true':
        return serial(result)
    if not await conn.fetchval("SELECT to_regclass('actual_inventory.scope_bridges') IS NOT NULL"):
        raise HTTPException(503, 'Native physical-count reporting schema is awaiting setup')
    scope = await conn.fetchrow('SELECT id,revision FROM actual_inventory.scopes WHERE store_id=$1 ORDER BY revision DESC LIMIT 1', store_id)
    result['countStatus'] = 'scope_missing'
    if not scope:
        return serial(result)
    result['scope'] = dict(scope)
    result['countStatus'] = 'count_missing'
    count = await conn.fetchrow('''SELECT c.id,c.count_date,c.timing,c.status,c.counted_by,c.recorded_at
        FROM actual_inventory.count_snapshots c WHERE c.store_id=$1 AND c.scope_id=$2 AND c.count_date <= $3
        AND NOT EXISTS(SELECT 1 FROM actual_inventory.count_snapshots child WHERE child.corrects_snapshot_id=c.id)
        ORDER BY c.count_date DESC,c.boundary_date DESC,c.recorded_at DESC,c.id DESC LIMIT 1''', store_id, scope['id'], as_of)
    if not count:
        return serial(result)
    result['count'] = dict(count)
    result['countStatus'] = count['status']
    rows = await conn.fetch('''SELECT item_code,base_unit,counted_quantity,counted_unit,base_quantity,
        inventory_value,confirmed FROM actual_inventory.count_lines WHERE snapshot_id=$1 ORDER BY item_code''', count['id'])
    result['items'] = [dict(row) for row in rows]
    # A later incomplete/replacement count cannot silently fall back to a prior
    # complete count or present its partial value as a complete inventory total.
    if count['status'] == 'complete' and rows and all(r['confirmed'] and r['inventory_value'] is not None for r in rows):
        result['inventoryValue'] = await conn.fetchval('SELECT sum(inventory_value) FROM actual_inventory.count_lines WHERE snapshot_id=$1', count['id'])
    else:
        result['countStatus'] = 'incomplete'
    return serial(result)


async def read_operating_summary(pool, store_id, as_of=None):
    async with pool.acquire() as conn, conn.transaction(isolation='repeatable_read', readonly=True):
        return await operating_summary(conn, store_id, as_of)
