"""Retain legacy adjustment/period records across native inventory cutover."""
import os
from fastapi import HTTPException
import legacy_prep_views


async def capabilities(conn):
    inventory = any(os.getenv(flag, 'false').lower() == 'true' for flag in
                    ('PURCHASE_IMPORT_ENABLED', 'ACTUAL_INVENTORY_ENABLED'))
    inventory = inventory or bool(await conn.fetchval("""SELECT
        to_regclass('purchasing.posting_batches') IS NOT NULL OR
        to_regclass('actual_inventory.count_snapshots') IS NOT NULL"""))
    prep = await legacy_prep_views.reporting_retired(conn)
    return {'inventoryRetired':inventory, 'adjustmentsAvailable':not (inventory or prep),
            'reportingPeriodsAvailable':not inventory}


def basis(available, name):
    return {'basis':name,'archived':not available,'operational':available}


async def hold_write(conn, collection):
    status=await capabilities(conn)
    if collection=='adjustments' and not status['adjustmentsAvailable']:
        raise HTTPException(409,'Legacy adjustments are retained history. Record measured prep waste through reviewed native prep workflows; physical Food Cost remains independent.')
    if collection=='reportingPeriods' and not status['reportingPeriodsAvailable']:
        raise HTTPException(409,'Legacy reporting periods are retained history. Close physical Food Cost periods through Actual Inventory; sales remain analytical drafts.')
