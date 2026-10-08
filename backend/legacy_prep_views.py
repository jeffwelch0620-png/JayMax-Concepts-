"""Retirement boundaries for legacy prep operating reads; no data migration."""
import os
from fastapi import HTTPException


async def stock_retired(conn):
    # Installed schema is a one-way cutover boundary, even when flags are off.
    if any(os.getenv(flag, 'false').lower() == 'true' for flag in
           ('PREP_BATCHES_ENABLED', 'PREP_CONTAINERS_ENABLED')):
        return True
    return bool(await conn.fetchval("""SELECT
        to_regclass('prep_inventory.batch_movements') IS NOT NULL OR
        to_regclass('prep_inventory.container_moves') IS NOT NULL"""))


async def reporting_retired(conn):
    if await stock_retired(conn):
        return True
    if any(os.getenv(flag, 'false').lower() == 'true' for flag in
           ('PREP_OBSERVATIONS_ENABLED', 'STAFF_PREP_COUNTS_ENABLED',
            'PREP_PLANNING_ENABLED', 'PREP_DAY_TASKS_ENABLED')):
        return True
    return bool(await conn.fetchval("""SELECT
        to_regclass('prep_inventory.count_observations') IS NOT NULL OR
        to_regclass('prep_inventory.staff_sheets') IS NOT NULL OR
        to_regclass('prep_inventory.planning_versions') IS NOT NULL OR
        to_regclass('prep_inventory.day_list_versions') IS NOT NULL"""))


async def counts_retired(conn):
    return (os.getenv('STAFF_PREP_COUNTS_ENABLED', 'false').lower() == 'true' or
            bool(await conn.fetchval("SELECT to_regclass('prep_inventory.staff_sheets') IS NOT NULL")))


async def lists_retired(conn):
    return (os.getenv('PREP_DAY_TASKS_ENABLED', 'false').lower() == 'true' or
            bool(await conn.fetchval("SELECT to_regclass('prep_inventory.day_list_versions') IS NOT NULL")))


async def capabilities(conn):
    return {'countsAvailable': not await counts_retired(conn),
            'listsAvailable': not await lists_retired(conn),
            'reportingAvailable': not await reporting_retired(conn)}


def archive_basis():
    return {'basis': 'legacy_prep_archive', 'archived': True, 'operational': False}


def hold_read(retired, archive, workflow):
    if retired and not archive:
        raise HTTPException(410, f'Historical prep {workflow} are retained for archive review. Use reviewed native prep workflows for current work.')


async def hold_report(conn):
    if await reporting_retired(conn):
        raise HTTPException(410, 'Historical prep reports and par advice are unavailable after prep cutover. Use reviewed prep counts, production and period reports.')


def unavailable():
    return {'available': False, 'basis': 'legacy_prep_retired',
            'message': 'Historical prep figures are retained for review. Use reviewed prep counts, production and period reports; current prep totals are unavailable here.'}
