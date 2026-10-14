"""Connection-loss cleanup must not replace the original read-only failure."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from tempfile import TemporaryDirectory
from pathlib import Path
from readonly_snapshot import readonly_snapshot


class ReadonlySnapshotTests(unittest.IsolatedAsyncioTestCase):
    def connection(self, **changes):
        tx = SimpleNamespace(start=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock())
        for key, value in changes.items(): setattr(tx, key, AsyncMock(side_effect=value))
        return SimpleNamespace(transaction=MagicMock(return_value=tx)), tx

    async def test_connection_loss_survives_failed_rollback_without_private_text(self):
        original = ConnectionError('TEST ONLY original disconnect')
        conn, tx = self.connection(rollback=RuntimeError('TEST ONLY private diagnostic'))
        with self.assertRaises(ConnectionError) as caught:
            async with readonly_snapshot(conn): raise original
        self.assertIs(caught.exception, original)
        self.assertEqual(original.snapshotCleanupErrorType, 'RuntimeError')
        self.assertNotIn('private diagnostic', str(original))
        tx.commit.assert_not_awaited(); tx.rollback.assert_awaited_once()

    async def test_success_and_successful_rollback_preserve_readonly_contract(self):
        conn, tx = self.connection()
        async with readonly_snapshot(conn): pass
        conn.transaction.assert_called_once_with(isolation='repeatable_read', readonly=True)
        tx.start.assert_awaited_once(); tx.commit.assert_awaited_once(); tx.rollback.assert_not_awaited()
        conn, tx = self.connection()
        original = ValueError('TEST ONLY failed inspection')
        with self.assertRaises(ValueError) as caught:
            async with readonly_snapshot(conn): raise original
        self.assertIs(caught.exception, original)
        tx.rollback.assert_awaited_once(); tx.commit.assert_not_awaited()

    async def test_commit_and_begin_failures_are_not_reported_as_success(self):
        for operation in ('start', 'commit'):
            conn, tx = self.connection(**{operation:ConnectionError('TEST ONLY disconnected')})
            with self.subTest(operation=operation), self.assertRaises(ConnectionError):
                async with readonly_snapshot(conn): pass
            tx.rollback.assert_not_awaited()

    async def test_cancelled_inspection_survives_cleanup_failure(self):
        conn, tx = self.connection(rollback=ConnectionError('TEST ONLY disconnected'))
        original = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError) as caught:
            async with readonly_snapshot(conn): raise original
        self.assertIs(caught.exception, original)
        self.assertEqual(original.snapshotCleanupErrorType, 'ConnectionError')
        tx.commit.assert_not_awaited()

    async def test_hosted_metadata_snapshot_preserves_original_disconnect(self):
        import hosted_auxiliary_trial as trial
        conn, tx = self.connection(rollback=RuntimeError('TEST ONLY cleanup'))
        conn.execute=AsyncMock()
        original=ConnectionError('TEST ONLY source disconnect')
        with patch.object(trial.candidate,'catalog_contracts',AsyncMock(side_effect=original)):
            with self.assertRaises(ConnectionError) as caught: await trial.snapshot(conn)
        self.assertIs(caught.exception, original)
        self.assertEqual(original.snapshotCleanupErrorType,'RuntimeError')
        tx.commit.assert_not_awaited()

    async def test_export_snapshot_preserves_disconnect_before_dump(self):
        import hosted_backup as backup
        conn, tx = self.connection(rollback=RuntimeError('TEST ONLY cleanup'))
        conn.fetch=AsyncMock(return_value=[{'nspname':s} for s in backup.SCHEMAS])
        conn.fetchval=AsyncMock(return_value='TEST ONLY snapshot')
        conn.close=AsyncMock()
        original=ConnectionError('TEST ONLY source disconnect')
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            def directory(path,area): path.mkdir();return path
            with patch.object(backup,'private_directory',side_effect=directory),\
                 patch.object(backup.asyncpg,'connect',AsyncMock(return_value=conn)),\
                 patch.object(backup.native,'configure',AsyncMock()),\
                 patch.object(backup,'fingerprint',AsyncMock(side_effect=original)),\
                 patch.object(backup,'tool',AsyncMock()) as tool:
                with self.assertRaises(ConnectionError) as caught:
                    await backup.export_backup('postgresql://postgres.abcdefghijklmnopqrst:TEST_ONLY@aws-0.pooler.supabase.com:5432/postgres',
                        'abcdefghijklmnopqrst','TEST ONLY dump','TEST ONLY restore',root/'archive',root/'key',{})
                self.assertIs(caught.exception,original)
                self.assertEqual(original.snapshotCleanupErrorType,'RuntimeError')
                tool.assert_not_awaited()
            self.assertFalse((root/'archive/archive.partial').exists())
            self.assertFalse((root/'archive/backup.partial.enc').exists())
            conn.close.assert_awaited_once()
