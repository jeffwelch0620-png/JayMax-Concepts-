"""Workflow conflict responses and separation of known recording identities."""
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


def require_independent(actor, authors, claimed_staff=None):
    identities = {identity(author) for author in authors if author is not None}
    if claimed_staff is not None:
        identities.add(identity(claimed_staff))
    if identity(actor) in identities:
        raise HTTPException(403, 'A different reviewer must accept work recorded or edited by this identity')
