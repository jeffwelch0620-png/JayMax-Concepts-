"""Optional separately restricted pool for account and notification tables."""
import asyncio
from contextlib import suppress
import logging
import os
from urllib.parse import urlsplit, unquote
import asyncpg
from fastapi import HTTPException
import db_pg
import auxiliary_permissions

logger = logging.getLogger(__name__)
_pool = None
_retry_task = None
_configured = None


def same_target(primary, auxiliary):
    try:
        urls = [urlsplit(value) for value in (primary, auxiliary)]
        if any(u.scheme not in ('postgres', 'postgresql') or not u.hostname or not u.username or
               not u.path.strip('/') or '[YOUR-PASSWORD]' in value for u, value in zip(urls, (primary, auxiliary))):
            return False
        endpoints = [(u.hostname.lower(), u.port or 5432, unquote(u.path)) for u in urls]
        if endpoints[0] != endpoints[1]:
            return False
        if urls[0].hostname.lower().endswith('.pooler.supabase.com'):
            users = [unquote(u.username).rsplit('.', 1) for u in urls]
            if any(len(u) != 2 or not u[1] for u in users) or users[0][1] != users[1][1]:
                return False
        return True
    except (ValueError, TypeError):
        return False


async def _try_connect(url):
    candidate = None
    try:
        local = urlsplit(url).hostname in ('127.0.0.1', '::1', 'localhost')
        candidate = await asyncio.wait_for(asyncpg.create_pool(
            url, min_size=1, max_size=3, statement_cache_size=0, init=db_pg._init_connection,
            ssl=None if local else 'require', timeout=db_pg.CONNECT_TIMEOUT,
            command_timeout=30), db_pg.CONNECT_TIMEOUT + 5)
        async with candidate.acquire() as conn:
            report = await auxiliary_permissions.inspect(conn)
        if report['status'] != 'passed':
            await candidate.close()
            categories = sorted({issue.split(':', 1)[0] for issue in report['issues']})
            logger.warning('Auxiliary database permissions held (%s); no connection fallback', ', '.join(categories))
            return None
        return candidate
    except asyncio.CancelledError:
        if candidate is not None:
            await candidate.close()
        raise
    except Exception as exc:
        if candidate is not None:
            await candidate.close()
        # Driver messages and URLs may contain connection material; retain only type.
        logger.warning('Auxiliary database unavailable (%s); no connection fallback', type(exc).__name__)
        return None


async def init_pool():
    global _pool, _retry_task, _configured
    _configured = 'AUXILIARY_DATABASE_URL' in os.environ
    if not _configured:
        return None
    url = os.environ.get('AUXILIARY_DATABASE_URL', '').strip()
    if not same_target(os.environ.get('DATABASE_URL', '').strip(), url):
        logger.warning('Auxiliary database must use the same database endpoint/project')
        return None
    _pool = await _try_connect(url)
    if _pool is None and (_retry_task is None or _retry_task.done()):
        _retry_task = asyncio.create_task(_retry_until_connected(url))
    return _pool


async def _retry_until_connected(url):
    global _pool
    while _pool is None:
        await asyncio.sleep(db_pg.RETRY_INTERVAL)
        _pool = await _try_connect(url)


def pool():
    configured = _configured if _configured is not None else 'AUXILIARY_DATABASE_URL' in os.environ
    if not configured:
        return db_pg.pool()
    if _pool is None:
        raise HTTPException(503, 'Account and notification database is unavailable')
    return _pool


async def close_pool():
    global _pool, _retry_task, _configured
    if _retry_task is not None:
        _retry_task.cancel()
        with suppress(asyncio.CancelledError):
            await _retry_task
        _retry_task = None
    if _pool is not None:
        await _pool.close()
        _pool = None
    _configured = None
