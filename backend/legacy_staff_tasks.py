"""Retire the mixed text-assigned queue when reviewed staff workflows cut over.

The retained queue has no verified roster identities. Archive access does not
convert its names, create native assignments, or affect physical inventory.
"""
import os
from fastapi import HTTPException


async def retired(conn):
    if any(os.getenv(flag, 'false').lower() == 'true' for flag in
           ('ACTUAL_INVENTORY_ENABLED', 'STAFF_PREP_TASKS_ENABLED')):
        return True
    # Installed staff schema is a one-way boundary even with feature flags off.
    return bool(await conn.fetchval("""SELECT
        to_regclass('actual_inventory.staff_sheets') IS NOT NULL OR
        to_regclass('prep_inventory.task_assignments') IS NOT NULL"""))


def hold_read(is_retired, archive=False):
    if is_retired and not archive:
        raise HTTPException(410, 'Historical employee tasks are retained for manager archive review. Use reviewed count sheets and the native prep task plan for current work.')


async def hold_write(conn):
    if await retired(conn):
        raise HTTPException(409, 'Historical employee tasks are read-only. Create and review current work through count sheets and the native prep task plan.')


def archive_basis():
    return {'basis': 'legacy_staff_task_archive', 'archived': True,
            'operational': False, 'identityBasis': 'legacy_text'}
