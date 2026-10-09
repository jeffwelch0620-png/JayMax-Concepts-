"""Connection selection, credential-safe failure, retry and shutdown boundaries."""
import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
import db_auxiliary as db


class TargetTests(unittest.TestCase):
    def test_same_database_and_pooler_project_required(self):
        primary = 'postgresql://inventory.project@aws-0.pooler.supabase.com:5432/postgres'
        self.assertTrue(db.same_target(primary, 'postgresql://aux.project@aws-0.pooler.supabase.com:5432/postgres'))
        for other in ('postgresql://aux.other@aws-0.pooler.supabase.com:5432/postgres',
                      'postgresql://aux@aws-0.pooler.supabase.com:5432/postgres',
                      'postgresql://aux.project@elsewhere:5432/postgres',
                      'postgresql://aux.project@aws-0.pooler.supabase.com:6543/postgres',
                      'postgresql://aux.project@aws-0.pooler.supabase.com:5432/other',
                      'postgresql://aux:[YOUR-PASSWORD]@host/db', 'not-a-url'):
            self.assertFalse(db.same_target(primary, other))
        self.assertTrue(db.same_target('postgresql://one@127.0.0.1/local', 'postgresql://two@127.0.0.1:5432/local'))


class PoolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = patch.dict(os.environ, {}, clear=True); self.env.start()
        self.state = patch.multiple(db, _pool=None, _retry_task=None, _configured=None); self.state.start()
        self.addCleanup(self.state.stop); self.addCleanup(self.env.stop)

    async def asyncTearDown(self):
        await db.close_pool()

    async def test_unset_compatibility_but_explicit_empty_never_falls_back(self):
        with patch('db_pg.pool', return_value='existing-primary') as primary:
            self.assertEqual(db.pool(), 'existing-primary')
            os.environ['AUXILIARY_DATABASE_URL'] = ''
            await db.init_pool()
            with self.assertRaises(HTTPException) as error: db.pool()
            self.assertEqual(error.exception.status_code, 503)
            self.assertEqual(primary.call_count, 1)

    async def test_failed_initial_connection_retries_then_closes_without_fallback(self):
        os.environ.update(DATABASE_URL='postgresql://main@127.0.0.1/local', AUXILIARY_DATABASE_URL='postgresql://aux@127.0.0.1/local')
        connection = AsyncMock()
        with patch.object(db, '_try_connect', AsyncMock(side_effect=[None, connection])), patch('db_pg.RETRY_INTERVAL', 0):
            self.assertIsNone(await db.init_pool())
            with self.assertRaises(HTTPException): db.pool()
            await db._retry_task
            self.assertIs(db.pool(), connection)
            await db.close_pool()
            connection.close.assert_awaited_once()
            self.assertIsNone(db._retry_task)
            with self.assertRaises(HTTPException): db.pool()

    async def test_pending_retry_is_cancelled_and_awaited(self):
        os.environ.update(DATABASE_URL='postgresql://main@127.0.0.1/local', AUXILIARY_DATABASE_URL='postgresql://aux@127.0.0.1/local')
        with patch.object(db, '_try_connect', AsyncMock(return_value=None)):
            await db.init_pool(); task = db._retry_task
            await asyncio.sleep(0)
            await db.close_pool()
            self.assertTrue(task.cancelled())

    async def test_driver_messages_and_connection_material_are_not_logged(self):
        with patch.object(db.asyncpg, 'create_pool', AsyncMock(side_effect=ValueError('synthetic-private-value'))):
            with self.assertLogs('db_auxiliary', level='WARNING') as logs:
                self.assertIsNone(await db._try_connect('postgresql://aux:synthetic-private-value@127.0.0.1/local'))
            self.assertNotIn('synthetic-private-value', '\n'.join(logs.output))

    async def test_different_target_is_held_before_connection_attempt(self):
        os.environ.update(DATABASE_URL='postgresql://main@127.0.0.1/local', AUXILIARY_DATABASE_URL='postgresql://aux@127.0.0.1/other')
        with patch.object(db, '_try_connect', AsyncMock()) as connect:
            await db.init_pool(); connect.assert_not_awaited()
            with self.assertRaises(HTTPException): db.pool()

    async def test_permission_hold_closes_candidate_and_logs_only_category(self):
        candidate = MagicMock()
        candidate.close = AsyncMock()
        candidate.acquire.return_value.__aenter__ = AsyncMock(return_value=object())
        candidate.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch.object(db.asyncpg, 'create_pool', AsyncMock(return_value=candidate)), patch.object(
                db.auxiliary_permissions, 'inspect', AsyncMock(return_value={
                    'status': 'held', 'issues': ['excess-table:synthetic-private-value']})):
            with self.assertLogs('db_auxiliary', level='WARNING') as logs:
                self.assertIsNone(await db._try_connect('postgresql://aux@127.0.0.1/local'))
            candidate.close.assert_awaited_once()
            self.assertIn('excess-table', '\n'.join(logs.output))
            self.assertNotIn('synthetic-private-value', '\n'.join(logs.output))
