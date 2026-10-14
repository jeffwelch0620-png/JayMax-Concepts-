"""Connection-loss cleanup must not replace the original read-only failure."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from tempfile import TemporaryDirectory
from pathlib import Path
from readonly_snapshot import readonly_snapshot, preserve_cleanup_failure, error_details


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
        conn.fetch=AsyncMock(side_effect=lambda sql,*args: [] if 'pg_settings' in sql else [{'nspname':s} for s in backup.SCHEMAS])
        conn.fetchval=AsyncMock(return_value='TEST ONLY snapshot')
        conn.close=AsyncMock(side_effect=RuntimeError('TEST ONLY private close failure'))
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
                self.assertEqual(original.connectionCloseErrorType,'RuntimeError')
                tool.assert_not_awaited()
            self.assertFalse((root/'archive/archive.partial').exists())
            self.assertFalse((root/'archive/backup.partial.enc').exists())
            conn.close.assert_awaited_once()

    async def test_safe_receipt_fields_validate_categories_and_sqlstate(self):
        error = ConnectionError('TEST ONLY password=private')
        error.sqlstate = '08003'
        error.snapshotCleanupErrorType = 'InterfaceError'
        self.assertEqual(error_details(error), {'errorType':'ConnectionError', 'sqlState':'08003',
                                              'snapshotCleanupErrorType':'InterfaceError'})
        for invalid in ('08003 private', 'private://password', 8003, ['08003']):
            with self.subTest(value=invalid):
                error.sqlstate = invalid
                error.snapshotCleanupErrorType = invalid
                self.assertEqual(error_details(error), {'errorType':'ConnectionError', 'sqlState':None,
                                                       'snapshotCleanupErrorType':None})

    async def test_cleanup_failure_preserves_body_and_cancellation_but_alone_fails(self):
        for original in (ConnectionError('TEST ONLY original'), asyncio.CancelledError()):
            with self.subTest(error=type(original).__name__):
                cleanup = AsyncMock(side_effect=RuntimeError('TEST ONLY private cleanup'))
                with self.assertRaises(type(original)) as caught:
                    async with preserve_cleanup_failure(cleanup, 'lockReleaseErrorType'):
                        raise original
                self.assertIs(caught.exception, original)
                self.assertEqual(error_details(original)['lockReleaseErrorType'], 'RuntimeError')
                cleanup.assert_awaited_once()
        with self.assertRaises(RuntimeError):
            async with preserve_cleanup_failure(AsyncMock(side_effect=RuntimeError()), 'connectionCloseErrorType'):
                pass

    async def test_default_activity_isolation_is_not_strengthened(self):
        conn, tx = self.connection()
        async with readonly_snapshot(conn, isolation=None): pass
        conn.transaction.assert_called_once_with(readonly=True)
        tx.commit.assert_awaited_once()

    async def test_remaining_inspectors_keep_original_error_when_rollback_fails(self):
        import deployment_readiness as readiness
        import hosted_install_preservation as preservation
        import apply_additive_migration as additive
        import hosted_additive_index as hosted
        for entry in ('readiness', 'preservation', 'local_prepare', 'local_verify', 'hosted_prepare'):
            conn, tx = self.connection(rollback=RuntimeError('TEST ONLY cleanup'))
            original = ConnectionError('TEST ONLY original')
            conn.execute = AsyncMock(side_effect=original)
            with self.subTest(entry=entry), self.assertRaises(ConnectionError) as caught:
                if entry == 'readiness': await readiness.inspect(conn)
                elif entry == 'preservation': await preservation.fingerprints(conn, {})
                elif entry == 'local_prepare':
                    with patch.object(additive, 'checked_delivery', return_value=([], {})):
                        await additive.prepare(conn, {}, 'TEST ONLY')
                elif entry == 'local_verify':
                    with patch.object(additive, 'validate_plan'):
                        await additive._verify_outcome(conn, {})
                else:
                    with patch.object(hosted, 'maintenance'), patch.object(hosted, 'server_version', AsyncMock()), \
                         patch.object(hosted, 'writer_sessions', AsyncMock()):
                        await hosted.prepare(conn, {}, {}, {}, {}, {})
            self.assertIs(caught.exception, original)
            self.assertEqual(original.snapshotCleanupErrorType, 'RuntimeError')
            tx.commit.assert_not_awaited()

    async def test_both_reconcilers_preserve_body_error_through_unlock_failure(self):
        import apply_additive_migration as additive
        import hosted_additive_index as hosted
        for entry in ('local', 'hosted'):
            conn, tx = self.connection(rollback=RuntimeError('TEST ONLY rollback'))
            original = ConnectionError('TEST ONLY original')
            conn.is_in_transaction = MagicMock(return_value=False)
            conn.fetchval = AsyncMock(return_value=True)
            conn.execute = AsyncMock(side_effect=RuntimeError('TEST ONLY unlock'))
            with patch.object(additive, '_verify_outcome', AsyncMock(side_effect=original)), \
                 patch.object(hosted, 'validate'), patch.object(hosted, 'server_version', AsyncMock()), \
                 self.subTest(entry=entry), self.assertRaises(ConnectionError) as caught:
                if entry == 'local': await additive.verify_outcome(conn, {})
                else: await hosted.reconcile(conn, {'core':{}}, {}, {}, {}, {})
            self.assertIs(caught.exception, original)
            self.assertEqual(original.lockReleaseErrorType, 'RuntimeError')
            if entry == 'hosted': self.assertEqual(original.snapshotCleanupErrorType, 'RuntimeError')
            conn.fetchval.assert_awaited_once()
            conn.execute.assert_awaited_once()

    async def test_successful_reconcile_cannot_pass_failed_unlock(self):
        import apply_additive_migration as additive
        conn = SimpleNamespace(is_in_transaction=lambda:False, fetchval=AsyncMock(return_value=True),
                               execute=AsyncMock(side_effect=ConnectionError('TEST ONLY unlock')))
        with patch.object(additive, '_verify_outcome', AsyncMock(return_value={'status':'verified_not_applied'})), \
             self.assertRaises(ConnectionError) as caught:
            await additive.verify_outcome(conn, {})
        self.assertEqual(error_details(caught.exception)['lockReleaseErrorType'], 'ConnectionError')

    async def test_local_cli_writes_original_categories_when_close_also_fails(self):
        import apply_additive_migration as additive
        from test_hosted_additive_index import core_plan
        import json
        import os
        for body_fails in (True, False):
            with self.subTest(body_fails=body_fails), TemporaryDirectory() as directory:
                root = Path(directory)
                source = root/'original.json'; source.write_text('{}')
                original = ConnectionError('TEST ONLY password=private')
                original.sqlstate = '08003'; original.snapshotCleanupErrorType = 'InterfaceError'
                conn = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError('TEST ONLY private close')))
                args = SimpleNamespace(mode='dry-run', original_install_receipt=str(source),
                                       delivery_version='TEST ONLY', output=str(root/'receipt.json'))
                with patch.dict(os.environ, {'NATIVE_PURCHASE_TEST_DSN':
                        'postgresql://purchase_implementation_test@127.0.0.1:55439/native_purchase_test_control'}), \
                     patch.object(additive.asyncpg, 'connect', AsyncMock(return_value=conn)), \
                     patch.object(additive, 'prepare', AsyncMock(side_effect=original if body_fails else None,
                         return_value=core_plan())):
                    self.assertEqual(await additive.main(args), 2)
                raw = Path(args.output).read_text(); result = json.loads(raw)
                self.assertEqual(result['status'], 'held')
                self.assertEqual(result['connectionCloseErrorType'], 'RuntimeError')
                with self.assertRaises(ValueError): additive.validate_plan(result)
                with self.assertRaises(ValueError): await additive.apply(SimpleNamespace(), result)
                if body_fails:
                    self.assertEqual(result['errorType'], 'ConnectionError')
                    self.assertEqual(result['sqlState'], '08003')
                    self.assertEqual(result['snapshotCleanupErrorType'], 'InterfaceError')
                self.assertNotIn('password', raw); self.assertNotIn('private close', raw)

    async def test_partial_file_cleanup_attempts_second_path_after_failure(self):
        import hosted_backup as backup
        first = SimpleNamespace(exists=MagicMock(return_value=True), unlink=MagicMock(side_effect=OSError()))
        second = SimpleNamespace(exists=MagicMock(return_value=True), unlink=MagicMock())
        with self.assertRaises(OSError): await backup.remove_partial_files((first, second))
        second.unlink.assert_called_once()
