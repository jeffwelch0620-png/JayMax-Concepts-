"""Public asyncpg operation semantics; dedicated disposable loopback only."""
import asyncio
import json
import os
import unittest

import asyncpg
from apply_additive_migration import local_target
from local_query_metrics import MeasuredConnection, finish, query_scope


@unittest.skipUnless(os.environ.get('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class LocalQueryMetricsDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        dsn = os.environ['NATIVE_PURCHASE_TEST_DSN']
        local_target(dsn)
        self.raw = await asyncpg.connect(dsn, ssl=False, timeout=10, command_timeout=20)
        self.metrics = {}
        self.conn = MeasuredConnection(self.raw, self.metrics)

    async def asyncTearDown(self):
        await self.raw.close(timeout=10)

    async def test_iteration_cached_uncached_empty_exact_batch_and_early_exit(self):
        for count in (0, 100, 250):
            # Repeating the same query exercises the driver's statement cache.
            for _ in range(2):
                with self.subTest(count=count):
                    async with self.conn.transaction(readonly=True):
                        before = self.metrics.get('driverOperations', {}).get('cursor_next', {}).get('calls', 0)
                        with query_scope('sequences'):
                            actual = [r[0] async for r in self.conn.cursor(
                                'SELECT n FROM generate_series(1, $1::int) n', count, prefetch=100)]
                        self.assertEqual(actual, list(range(1, count + 1)))
                        self.assertEqual(self.metrics['driverOperations']['cursor_next']['calls'] - before, count + 1)
        async with self.conn.transaction(readonly=True):
            with query_scope('backup_fingerprints'):
                async for row in self.conn.cursor('SELECT n FROM generate_series(1, 250) n', prefetch=100):
                    self.assertEqual(row[0], 1); break
        # No artificial close/exhaustion call for the early exit. Leaving the
        # transaction delegates portal cleanup to PostgreSQL/asyncpg unchanged.
        finish(self.metrics)
        self.assertEqual(self.metrics['queryCalls'], 0)
        self.assertEqual(self.metrics['driverOperations']['cursor_next']['exhausted'], 6)
        self.assertEqual(self.metrics['driverOperationGroups']['backup_fingerprints']['cursor_next']['completed'], 1)
        self.assertEqual(self.metrics['driverOperations']['transaction_enter']['completed'], 7)
        self.assertNotIn('generate_series', json.dumps(self.metrics))

    async def test_awaited_cursor_manual_fetch_forward_and_driver_refusals(self):
        async with self.conn.transaction(readonly=True):
            cursor = await self.conn.cursor('SELECT n FROM generate_series(1, 7) n')
            self.assertEqual([r[0] for r in await cursor.fetch(2)], [1, 2])
            self.assertEqual(await cursor.forward(2), 2)
            self.assertEqual((await cursor.fetchrow())[0], 5)
            self.assertEqual([r[0] for r in await cursor.fetch(100)], [6, 7])
            self.assertIsNone(await cursor.fetchrow())
        # Invalid prefetch belongs to the driver; wrapping neither accepts it nor
        # connects/retries separately. Await and iteration have different rules.
        async with self.conn.transaction(readonly=True):
            with self.assertRaises(asyncpg.InterfaceError):
                await self.conn.cursor('SELECT 1', prefetch=100)
            with self.assertRaises(asyncpg.InterfaceError):
                async for _ in self.conn.cursor('SELECT 1', prefetch=0): pass
        finish(self.metrics)
        self.assertEqual(self.metrics['driverOperations']['cursor_await']['errors'], 1)
        self.assertEqual(self.metrics['driverOperations']['cursor_iter']['errors'], 1)
        self.assertEqual(self.metrics['driverOperations']['cursor_fetch']['completed'], 2)
        self.assertEqual(self.metrics['driverOperations']['cursor_forward']['completed'], 1)
        self.assertEqual(self.metrics['driverOperations']['cursor_fetchrow']['completed'], 2)

    async def test_nested_context_and_manual_transactions_preserve_commit_and_rollback(self):
        await self.conn.execute('CREATE TEMP TABLE test_only_metrics (n integer)')
        async with self.conn.transaction() as entered:
            self.assertIsNone(entered)
            await self.conn.execute('INSERT INTO test_only_metrics VALUES(1)')
            with self.assertRaisesRegex(ValueError, 'TEST ONLY rollback'):
                async with self.conn.transaction():
                    await self.conn.execute('INSERT INTO test_only_metrics VALUES(2)')
                    raise ValueError('TEST ONLY rollback')
            async with self.conn.transaction():
                await self.conn.execute('INSERT INTO test_only_metrics VALUES(3)')
        tx = self.conn.transaction()
        self.assertIsNone(await tx.start())
        await self.conn.execute('INSERT INTO test_only_metrics VALUES(4)')
        self.assertIsNone(await tx.rollback())
        tx = self.conn.transaction()
        await tx.start()
        await self.conn.execute('INSERT INTO test_only_metrics VALUES(5)')
        await tx.commit()
        with self.assertRaises(asyncpg.InterfaceError): await tx.start()
        self.assertEqual([r[0] for r in await self.conn.fetch('SELECT n FROM test_only_metrics ORDER BY n')], [1, 3, 5])
        finish(self.metrics)
        ops = self.metrics['driverOperations']
        self.assertEqual(ops['transaction_enter']['completed'], 3)
        self.assertEqual(ops['transaction_exit']['completed'], 3)
        self.assertEqual(ops['transaction_start']['completed'], 2)
        self.assertEqual(ops['transaction_start']['errors'], 1)
        self.assertEqual(ops['transaction_commit']['completed'], 1)
        self.assertEqual(ops['transaction_rollback']['completed'], 1)
        self.assertNotIn('TEST ONLY', json.dumps(self.metrics))

    async def test_timeout_and_cancellation_are_propagated_and_connection_recovers(self):
        # Query failure occurs on the first cursor step, not at factory creation.
        async with self.conn.transaction(readonly=True):
            with self.assertRaises(TimeoutError):
                async for _ in self.conn.cursor('SELECT pg_sleep(1)', prefetch=1, timeout=.02): pass
        async with self.conn.transaction(readonly=True):
            iterator = self.conn.cursor('SELECT pg_sleep(10)', prefetch=1).__aiter__()
            task = asyncio.create_task(iterator.__anext__())
            await asyncio.sleep(.05)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
        self.assertEqual(await self.conn.fetchval('SELECT 1'), 1)
        finish(self.metrics)
        self.assertEqual(self.metrics['driverOperations']['cursor_next']['errors'], 1)
        self.assertEqual(self.metrics['driverOperations']['cursor_next']['cancelled'], 1)
        self.assertEqual(self.metrics['queryCalls'], 1)
        self.assertNotIn('pg_sleep', json.dumps(self.metrics))

    async def test_actual_backup_sequence_and_fallback_match_unwrapped_results(self):
        from unittest.mock import patch
        import hosted_backup as backup
        await self.raw.execute('CREATE TEMP TABLE test_only_metrics_rows AS SELECT generate_series(1, 250) AS n')
        await self.raw.execute('CREATE TEMP SEQUENCE test_only_metrics_sequence START 7')
        async with self.raw.transaction(readonly=True):
            with patch.object(backup, 'MAX_FINGERPRINT_AGGREGATE_BYTES', 65):
                for quoted, kind, group in (('pg_temp.test_only_metrics_rows', 'r', 'backup_fingerprints'),
                        ('pg_temp.test_only_metrics_sequence', 'S', 'sequences')):
                    with self.subTest(kind=kind):
                        expected = await backup.relation_fingerprint(self.raw, quoted, kind)
                        with query_scope(group):
                            actual = await backup.relation_fingerprint(self.conn, quoted, kind)
                        self.assertEqual(actual, expected)
        finish(self.metrics)
        self.assertEqual(self.metrics['queryCalls'], 1)  # Bounded table probe only.
        self.assertEqual(self.metrics['driverOperationGroups']['sequences']['cursor_next']['completed'], 1)
        self.assertEqual(self.metrics['driverOperationGroups']['backup_fingerprints']['cursor_next']['completed'], 250)
        self.assertNotIn('test_only_metrics', json.dumps(self.metrics))
