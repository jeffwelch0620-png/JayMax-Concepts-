"""Workflow conflict responses and separation of known recording identities."""
import os
from contextlib import asynccontextmanager
from uuid import UUID

import asyncpg
from fastapi import HTTPException


@asynccontextmanager
async def conflict_transaction(conn):
    # Catch outside the transaction context: partial journal effects must roll back
    # before an occupied key/identity becomes a reviewable HTTP conflict.
    try:
        async with conn.transaction():
            yield
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, 'Workflow identity or request key conflicts with retained history; refresh and review before retrying') from None


def identity(value):
    value = str(value)
    try:
        return str(UUID(value))
    except ValueError:
        return value


def self_acceptance_enabled():
    return os.getenv('SELF_ACCEPTANCE_ENABLED', 'false').lower() == 'true'


def require_independent_staff_work(actor, authors, claimed_staff=None):
    # EP-07 (Jeff 2026-11-05): a manager may accept their own staff count, prep count or cook output
    # while SELF_ACCEPTANCE_ENABLED is on. Both identities stay on the record, so self-accepted work
    # can be found later. Orders never use this: their creator never approves.
    if not self_acceptance_enabled():
        require_independent(actor, authors, claimed_staff)


def require_independent(actor, authors, claimed_staff=None):
    identities = {identity(author) for author in authors if author is not None}
    if claimed_staff is not None:
        identities.add(identity(claimed_staff))
    if identity(actor) in identities:
        raise HTTPException(403, 'A different reviewer must accept work recorded or edited by this identity')
