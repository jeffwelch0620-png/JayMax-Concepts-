"""Postgres (Supabase) connection pool -- the migration target running alongside the
existing Motor/MongoDB connection in server.py while the migration is in progress
(see docs/SUPABASE_MIGRATION_PLAN.md). Connects with DATABASE_URL, which should be
the Postgres *service role* connection (bypasses RLS) -- authorization stays decided
in FastAPI, matching the existing collaboration_security middleware, since none of
the new tables have RLS policies written yet.
"""
import os
import json
import logging
import asyncpg
from fastapi import HTTPException

logger = logging.getLogger(__name__)

_pool = None

async def _init_connection(conn):
    # The Prep module leans heavily on jsonb columns (usage/containers logs, etc.).
    # Without this codec asyncpg hands back/expects raw JSON text on every touch;
    # with it, query params and result columns round-trip as plain Python
    # dicts/lists everywhere in the app code.
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog", format="text")

async def init_pool():
    # Fails open, deliberately: during the migration the app must keep serving the
    # existing Mongo-backed /api/... routes even if Postgres isn't reachable yet (e.g.
    # DATABASE_URL still has the [YOUR-PASSWORD] placeholder). Only /api/pg/... routes
    # are affected -- they'll 503 via pool() below until this succeeds.
    global _pool
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url or "[YOUR-PASSWORD]" in database_url:
        logger.warning("DATABASE_URL not configured (or password placeholder not filled in) -- /api/pg/* routes will 503")
        return None
    try:
        _pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5, statement_cache_size=0, init=_init_connection)
    except Exception:
        logger.exception("Could not connect to Postgres -- /api/pg/* routes will 503")
        _pool = None
    return _pool

async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None

def pool():
    if _pool is None:
        raise HTTPException(503, "Postgres isn't connected -- check DATABASE_URL in backend/.env")
    return _pool
