"""PostgreSQL connection pool selected by DATABASE_URL.

The backend uses a PostgreSQL login, not a Supabase API service-role key. The
reviewed build has separate restricted inventory and account logins. FastAPI enforces
application authorization. USE_PG=true in server.py retires the Mongo client.
The deployment preflight checks both mode flags and native database permissions.
"""
import os
import json
import asyncio
from contextlib import suppress
import logging
import asyncpg
from db_tls import connection_tls
from fastapi import HTTPException

logger = logging.getLogger(__name__)

_pool = None
_retry_task = None
CONNECT_TIMEOUT = 20      # seconds per attempt: startup must never hang on the database
RETRY_INTERVAL = 30       # seconds between background retries after a failed start

async def _init_connection(conn):
    # The Prep module leans heavily on jsonb columns (usage/containers logs, etc.).
    # Without this codec asyncpg hands back/expects raw JSON text on every touch;
    # with it, query params and result columns round-trip as plain Python
    # dicts/lists everywhere in the app code.
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog", format="text")

async def init_pool():
    # Keep process health available while reconnecting; database routes return 503.
    # In PostgreSQL mode this never starts Mongo or changes the authoritative source.
    global _pool, _retry_task
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url or "[YOUR-PASSWORD]" in database_url:
        logger.warning("DATABASE_URL not configured (or password placeholder not filled in) -- /api/pg/* routes will 503")
        return None
    _pool = await _try_connect(database_url)
    if _pool is None:
        # Keep the app serving (health check, clear 503s) and reconnect on its own once the
        # database is reachable, instead of staying down until the next restart.
        if _retry_task is None or _retry_task.done():
            _retry_task = asyncio.create_task(_retry_until_connected(database_url))
    return _pool

async def _try_connect(database_url, *, transition=None):
    try:
        init = _init_connection
        extra_timeout = 0
        if transition is not None:
            import connection_transition
            if not isinstance(transition, connection_transition.ClientRevision):
                raise ValueError('Bound client revision required')
            transition.validate(database_url, 'inventory')
            async def init(conn):
                await _init_connection(conn)
                await connection_transition.inspect_connection(conn, database_url, 'inventory', transition)
            extra_timeout = connection_transition.CHECK_TIMEOUT['inventory']
        return await asyncio.wait_for(
            asyncpg.create_pool(database_url, min_size=1, max_size=2, statement_cache_size=0,
                                init=init, ssl=connection_tls(database_url),
                                timeout=CONNECT_TIMEOUT),
            CONNECT_TIMEOUT + 5 + extra_timeout)
    except Exception as exc:
        # Driver errors can contain credentials; log only the exception class.
        logger.warning('Postgres unavailable (%s); database routes will 503', type(exc).__name__)
        return None

async def _retry_until_connected(database_url):
    global _pool
    while _pool is None:
        await asyncio.sleep(RETRY_INTERVAL)
        _pool = await _try_connect(database_url)
    logger.info("Connected to Postgres")

async def close_pool():
    global _pool, _retry_task
    if _retry_task is not None:
        _retry_task.cancel()
        with suppress(asyncio.CancelledError):
            await _retry_task
        _retry_task = None
    if _pool is not None:
        await _pool.close()
        _pool = None

def pool():
    if _pool is None:
        raise HTTPException(503, "Postgres isn't connected -- check DATABASE_URL in backend/.env")
    return _pool
