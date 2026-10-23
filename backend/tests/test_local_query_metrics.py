"""Fictional driver calls prove timing attribution, restoration and redaction."""
import asyncio
import json
import inspect
from types import SimpleNamespace
import unittest
from local_query_metrics import (MeasuredConnection, finish, instrument_functions,
                                query_scope, relation_group, GROUPS, par_attribution_bindings)


class LocalQueryMetricsTests(unittest.IsolatedAsyncioTestCase):
    async def test_nested_function_totals_overlap_but_exclusive_totals_reconcile(self):
        async def fetch(*args, **kwargs): return ['TEST ONLY row']
        metrics = {}
        ticks = iter([1, 1.25, 2, 2.5, 3, 3.75])
        conn = MeasuredConnection(SimpleNamespace(fetch=fetch), metrics, clock=lambda: next(ticks))
        with query_scope('readiness_check'):
            with query_scope('readiness'):
                await conn.fetch('SELECT TEST ONLY')
                await conn.fetch('SELECT indisvalid FROM pg_index')
            with query_scope('fingerprints'):
                await conn.fetch('TEST ONLY fingerprint')
        finish(metrics)
        self.assertEqual(metrics['queryCalls'], 3)
        self.assertEqual(metrics['querySeconds'], 1.5)
        self.assertEqual(metrics['functionsInclusive']['readiness_check']['queryCalls'], 3)
        self.assertEqual(metrics['functionsInclusive']['readiness']['queryCalls'], 2)
        self.assertEqual(metrics['exclusiveGroups']['readiness']['queryCalls'], 1)
        self.assertEqual(metrics['exclusiveGroups']['index_state']['queryCalls'], 1)
        self.assertEqual(metrics['exclusiveGroups']['fingerprints']['queryCalls'], 1)
        self.assertNotIn('TEST ONLY', json.dumps(metrics))

    async def test_error_propagates_and_scope_and_function_are_restored(self):
        async def fetch(*args): raise RuntimeError('TEST ONLY private failure')
        metrics = {}; ticks = iter([0, .5, 1, 1.75])
        conn = MeasuredConnection(SimpleNamespace(fetch=fetch), metrics, clock=lambda: next(ticks))
        async def leaf(): await conn.fetch('TEST ONLY private SQL', 'TEST ONLY parameter')
        owner = SimpleNamespace(leaf=leaf)
        with self.assertRaises(RuntimeError), instrument_functions([(owner, 'leaf', 'ledger')]):
            await owner.leaf()
        self.assertIs(owner.leaf, leaf)
        with self.assertRaises(RuntimeError): await conn.fetch('TEST ONLY after failure')
        finish(metrics)
        self.assertEqual(metrics['exclusiveGroups']['ledger']['queryCalls'], 1)
        self.assertEqual(metrics['exclusiveGroups']['other']['queryCalls'], 1)
        self.assertNotIn('TEST ONLY', json.dumps(metrics))

    async def test_task_scopes_are_independent_and_nonquery_methods_pass_through(self):
        ready = asyncio.Event()
        async def fetch(*args):
            ready.set(); await asyncio.sleep(0); return 1
        driver = SimpleNamespace(fetch=fetch, is_closed=lambda: False)
        metrics = {}; conn = MeasuredConnection(driver, metrics)
        async def scoped():
            with query_scope('capture_catalog'): await conn.fetch('TEST ONLY')
        async def unscoped():
            await ready.wait(); await conn.fetch('TEST ONLY')
        await asyncio.gather(scoped(), unscoped())
        self.assertFalse(conn.is_closed())
        finish(metrics)
        self.assertEqual(metrics['queryCalls'], 2)
        self.assertEqual(metrics['exclusiveGroups']['capture_catalog']['queryCalls'], 1)
        self.assertEqual(metrics['exclusiveGroups']['other']['queryCalls'], 1)

    async def test_acl_classification_and_leaf_precedence_use_fixed_labels_only(self):
        async def fetch(*args): return []
        metrics = {}; conn = MeasuredConnection(SimpleNamespace(fetch=fetch), metrics)
        await conn.fetch('SELECT a.attacl::text AS acl FROM pg_attribute a')
        await conn.fetch('SELECT * FROM pg_default_acl')
        with query_scope('capture_catalog'):
            await conn.fetch('SELECT * FROM pg_default_acl')
        finish(metrics)
        self.assertEqual(metrics['exclusiveGroups']['acl']['queryCalls'], 2)
        self.assertEqual(metrics['exclusiveGroups']['capture_catalog']['queryCalls'], 1)
        with self.assertRaises(ValueError), query_scope('TEST ONLY unreviewed label'): pass

    async def test_new_function_groups_attribute_once_and_keep_parent_totals(self):
        async def fetch(*args): return []
        metrics = {}; conn = MeasuredConnection(SimpleNamespace(fetch=fetch), metrics)
        leaves = ('original_columns', 'backup_fingerprints', 'writer_guard', 'locks',
                  'backend_permissions', 'object_guard', 'sequences')
        with query_scope('backup_compare'):
            for name in leaves:
                with query_scope(name): await conn.fetch('TEST ONLY private SQL')
        finish(metrics)
        self.assertEqual(metrics['queryCalls'], len(leaves))
        self.assertEqual(metrics['functionsInclusive']['backup_compare']['queryCalls'], len(leaves))
        self.assertEqual(metrics['exclusiveGroups']['backup_compare']['queryCalls'], 0)
        for name in leaves:
            with self.subTest(group=name):
                self.assertEqual(metrics['exclusiveGroups'][name]['queryCalls'], 1)
        self.assertEqual(sum(v['queryCalls'] for v in metrics['exclusiveGroups'].values()), len(leaves))
        self.assertNotIn('TEST ONLY', json.dumps(metrics))

    async def test_relation_selector_labels_sequences_without_retaining_identifiers(self):
        async def fetch(*args): return []
        metrics = {}; conn = MeasuredConnection(SimpleNamespace(fetch=fetch), metrics)
        async def relation(connection, quoted, kind): return await connection.fetch(quoted)
        owner = SimpleNamespace(relation=relation)
        with instrument_functions([(owner, 'relation', relation_group)]):
            await owner.relation(conn, 'TEST ONLY sequence name', 'S')
            await owner.relation(conn, quoted='TEST ONLY table name', kind='r')
        finish(metrics)
        self.assertIs(owner.relation, relation)
        self.assertEqual(metrics['exclusiveGroups']['sequences']['queryCalls'], 1)
        self.assertEqual(metrics['exclusiveGroups']['backup_fingerprints']['queryCalls'], 1)
        self.assertNotIn('TEST ONLY', json.dumps(metrics))

    async def test_invalid_dynamic_label_refuses_before_invoking_function_and_restores(self):
        called = []
        async def leaf(): called.append(True)
        owner = SimpleNamespace(leaf=leaf)
        with self.assertRaises(ValueError), instrument_functions([
                (owner, 'leaf', lambda args, kwargs: 'TEST ONLY unreviewed label')]):
            await owner.leaf()
        self.assertEqual(called, [])
        self.assertIs(owner.leaf, leaf)

    async def test_inline_control_queries_use_fixed_categories_and_preserve_driver_result(self):
        async def fetch(query, *args): return 'TEST ONLY result'
        metrics = {}; conn = MeasuredConnection(SimpleNamespace(fetch=fetch), metrics)
        queries = [
            ('SET LOCAL statement_timeout=\'20s\'', 'session_settings'),
            ('LOCK TABLE TEST_ONLY IN SHARE MODE', 'locks'),
            ('SELECT pg_try_advisory_lock($1::bigint)', 'locks'),
            ('SELECT pg_advisory_xact_lock($1::bigint)', 'locks'),
            ('SELECT pg_advisory_unlock($1::bigint)', 'locks'),
            ('INSERT INTO supabase_migrations.schema_migrations VALUES ($1)', 'ledger'),
            ('SELECT current_database() AS database,current_user AS actor, 1', 'identity'),
        ]
        for query, group in queries:
            self.assertEqual(await conn.fetch(query, 'TEST ONLY parameter'), 'TEST ONLY result')
        finish(metrics)
        self.assertEqual(metrics['exclusiveGroups']['locks']['queryCalls'], 4)
        self.assertEqual(metrics['exclusiveGroups']['session_settings']['queryCalls'], 1)
        self.assertEqual(metrics['exclusiveGroups']['ledger']['queryCalls'], 1)
        self.assertEqual(metrics['exclusiveGroups']['identity']['queryCalls'], 1)
        self.assertNotIn('TEST ONLY', json.dumps(metrics))

    async def test_exact_reviewed_ddl_is_classified_without_logging_or_executing_it(self):
        from pathlib import Path
        import hashlib
        from local_query_metrics import PAR_DDL_SHA256, exclusive_group
        raw = (Path(__file__).resolve().parents[2]/'migrations/20261018_reviewed_inventory_pars.sql').read_bytes()
        # Use the installer's existing transaction-body extraction; no DB calls.
        from apply_additive_migration import sql_body
        body = sql_body(raw)
        self.assertEqual(hashlib.sha256(body.encode()).hexdigest(), PAR_DDL_SHA256)
        self.assertEqual(exclusive_group((), body), 'apply_ddl')
        self.assertEqual(exclusive_group((), body+'\n-- TEST ONLY changed'), 'other')

    async def test_sequence_cursor_work_stays_outside_the_existing_method_boundary(self):
        async def rows():
            yield {'value': 'TEST ONLY sequence state'}
        driver = SimpleNamespace(cursor=lambda *args, **kwargs: rows())
        metrics = {}; conn = MeasuredConnection(driver, metrics)
        async def relation(connection, quoted, kind):
            return [row async for row in connection.cursor(quoted, prefetch=100)]
        owner = SimpleNamespace(relation=relation)
        with instrument_functions([(owner, 'relation', relation_group)]):
            result = await owner.relation(conn, 'TEST ONLY sequence name', 'S')
        finish(metrics)
        self.assertEqual(result, [{'value':'TEST ONLY sequence state'}])
        self.assertEqual(metrics['queryCalls'], 0)
        self.assertEqual(metrics['exclusiveGroups']['sequences']['queryCalls'], 0)
        self.assertEqual(metrics['driverOperations']['cursor_next']['calls'], 2)
        self.assertEqual(metrics['driverOperations']['cursor_next']['exhausted'], 1)
        self.assertEqual(metrics['driverOperationGroups']['sequences']['cursor_next']['completed'], 1)
        self.assertEqual(set(metrics['exclusiveGroups']), set(GROUPS))
        self.assertNotIn('TEST ONLY', json.dumps(metrics))

    def test_binding_factory_resolves_actual_coroutines_and_fixed_labels(self):
        import hosted_reviewed_pars as adapter
        bindings = par_attribution_bindings(adapter)
        self.assertGreater(len(bindings), 0)
        for owner, attribute, label in bindings:
            with self.subTest(attribute=attribute):
                self.assertTrue(inspect.iscoroutinefunction(getattr(owner, attribute)))
                if callable(label):
                    for kind in ('S', 'r'):
                        self.assertIn(label((None, 'TEST ONLY identifier', kind), {}), GROUPS)
                        self.assertIn(label((), {'kind': kind}), GROUPS)
                        self.assertEqual(label((None, '', kind), {}),
                                         'sequences' if kind == 'S' else 'backup_fingerprints')
                else:
                    self.assertIn(label, GROUPS)

    async def test_cursor_iteration_observes_row_requests_not_inferred_batches(self):
        for count in (0, 100, 250):
            with self.subTest(count=count):
                async def rows():
                    for number in range(count): yield number
                seen = []
                def factory(*args, **kwargs):
                    seen.append((args, kwargs)); return rows()
                metrics = {}; conn = MeasuredConnection(SimpleNamespace(cursor=factory), metrics)
                with query_scope('backup_fingerprints'):
                    result = [row async for row in conn.cursor('TEST ONLY query', 7, prefetch=100)]
                self.assertEqual(result, list(range(count)))
                self.assertEqual(seen, [(('TEST ONLY query', 7), {'prefetch': 100})])
                finish(metrics)
                operations = metrics['driverOperations']
                self.assertEqual(operations['cursor_create']['calls'], 1)
                self.assertEqual(operations['cursor_iter']['calls'], 1)
                self.assertEqual(operations['cursor_next']['completed'], count)
                self.assertEqual(operations['cursor_next']['calls'], count + 1)
                self.assertEqual(operations['cursor_next']['exhausted'], 1)
                self.assertEqual(metrics['queryCalls'], 0)
                self.assertNotIn('TEST ONLY', json.dumps(metrics))
                self.assertNotIn('protocolRoundTrips', metrics)

    async def test_early_cursor_exit_does_not_invent_close_or_exhaustion(self):
        async def rows():
            yield 1; yield 2
        source = rows()
        metrics = {}; conn = MeasuredConnection(SimpleNamespace(cursor=lambda *a: source), metrics)
        try:
            async for row in conn.cursor('TEST ONLY query'):
                self.assertEqual(row, 1); break
            finish(metrics)
            self.assertEqual(metrics['driverOperations']['cursor_next']['completed'], 1)
            self.assertEqual(metrics['driverOperations']['cursor_next']['exhausted'], 0)
            self.assertFalse(any('close' in key for key in metrics['driverOperations']))
        finally:
            await source.aclose()

    async def test_awaited_cursor_forwards_manual_operations_and_values(self):
        from unittest.mock import AsyncMock
        target = SimpleNamespace(fetch=AsyncMock(return_value=['TEST ONLY result']),
            fetchrow=AsyncMock(return_value=None), forward=AsyncMock(return_value=7))
        class Factory:
            def __await__(self):
                async def ready(): return target
                return ready().__await__()
        metrics = {}; conn = MeasuredConnection(SimpleNamespace(cursor=lambda *a, **k: Factory()), metrics)
        cursor = await conn.cursor('TEST ONLY query', timeout=2)
        self.assertEqual(await cursor.fetch(3, timeout=1), ['TEST ONLY result'])
        self.assertIsNone(await cursor.fetchrow())
        self.assertEqual(await cursor.forward(9), 7)
        target.fetch.assert_awaited_once_with(3, timeout=1)
        target.forward.assert_awaited_once_with(9)
        finish(metrics)
        for operation in ('cursor_await', 'cursor_fetch', 'cursor_fetchrow', 'cursor_forward'):
            self.assertEqual(metrics['driverOperations'][operation]['completed'], 1)
        self.assertNotIn('TEST ONLY', json.dumps(metrics))

    async def test_cursor_failures_and_cancellation_propagate_without_data(self):
        for error in (ValueError('TEST ONLY failure'), asyncio.CancelledError('TEST ONLY cancel')):
            with self.subTest(error=type(error).__name__):
                class Iterator:
                    def __aiter__(self): return self
                    async def __anext__(self): raise error
                metrics = {}; conn = MeasuredConnection(SimpleNamespace(cursor=lambda *a: Iterator()), metrics)
                with self.assertRaises(type(error)) as caught:
                    async for _ in conn.cursor('TEST ONLY query'): pass
                self.assertIs(caught.exception, error)
                finish(metrics)
                outcome = 'cancelled' if isinstance(error, asyncio.CancelledError) else 'errors'
                self.assertEqual(metrics['driverOperations']['cursor_next'][outcome], 1)
                self.assertNotIn('TEST ONLY', json.dumps(metrics))

    async def test_factory_and_iterator_errors_are_recorded_without_extra_driver_calls(self):
        from unittest.mock import Mock
        error = ValueError('TEST ONLY invalid cursor')
        driver = SimpleNamespace(cursor=Mock(side_effect=error), transaction=Mock(side_effect=error))
        metrics = {}; conn = MeasuredConnection(driver, metrics)
        for method in (conn.cursor, conn.transaction):
            with self.assertRaises(ValueError) as caught: method('TEST ONLY')
            self.assertIs(caught.exception, error)
        class BadFactory:
            def __aiter__(self): raise error
            def __await__(self):
                async def refuse(): raise error
                return refuse().__await__()
        driver.cursor.side_effect = None; driver.cursor.return_value = BadFactory()
        with self.assertRaises(ValueError):
            async for _ in conn.cursor('TEST ONLY'): pass
        with self.assertRaises(ValueError): await conn.cursor('TEST ONLY')
        finish(metrics)
        for operation in ('cursor_create', 'cursor_iter', 'cursor_await', 'transaction_create'):
            self.assertEqual(metrics['driverOperations'][operation]['errors'], 1)
        self.assertEqual(metrics['queryCalls'], 0)
        self.assertNotIn('TEST ONLY', json.dumps(metrics))

    async def test_transactions_delegate_context_result_exception_tuple_and_suppression(self):
        from unittest.mock import AsyncMock, Mock
        marker = object()
        target = SimpleNamespace(__aenter__=AsyncMock(return_value=marker),
                                 __aexit__=AsyncMock(return_value=True))
        driver = SimpleNamespace(transaction=Mock(return_value=target))
        metrics = {}; conn = MeasuredConnection(driver, metrics)
        error = RuntimeError('TEST ONLY suppressed')
        with query_scope('backup_catalog'):
            async with conn.transaction(readonly=True) as entered:
                self.assertIs(entered, marker); raise error
        driver.transaction.assert_called_once_with(readonly=True)
        args = target.__aexit__.await_args.args
        self.assertIs(args[0], RuntimeError); self.assertIs(args[1], error)
        self.assertIsNotNone(args[2])
        finish(metrics)
        for op in ('transaction_create', 'transaction_enter', 'transaction_exit'):
            self.assertEqual(metrics['driverOperations'][op]['completed'], 1)
            self.assertEqual(metrics['driverOperationGroups']['transaction_control'][op]['calls'], 1)
        self.assertEqual(metrics['driverOperations']['transaction_commit']['calls'], 0)
        self.assertEqual(metrics['driverOperations']['transaction_rollback']['calls'], 0)
        self.assertNotIn('TEST ONLY', json.dumps(metrics))

    async def test_manual_transaction_results_errors_and_cancellation_stay_separate(self):
        from unittest.mock import AsyncMock
        error = ValueError('TEST ONLY commit refused')
        target = SimpleNamespace(start=AsyncMock(return_value='TEST ONLY started'),
            commit=AsyncMock(side_effect=error), rollback=AsyncMock(side_effect=asyncio.CancelledError()))
        metrics = {}; conn = MeasuredConnection(SimpleNamespace(transaction=lambda: target), metrics)
        transaction = conn.transaction()
        self.assertEqual(await transaction.start(), 'TEST ONLY started')
        with self.assertRaises(ValueError) as caught: await transaction.commit()
        self.assertIs(caught.exception, error)
        with self.assertRaises(asyncio.CancelledError): await transaction.rollback()
        finish(metrics)
        self.assertEqual(metrics['driverOperations']['transaction_start']['completed'], 1)
        self.assertEqual(metrics['driverOperations']['transaction_commit']['errors'], 1)
        self.assertEqual(metrics['driverOperations']['transaction_rollback']['cancelled'], 1)
        self.assertEqual(metrics['queryCalls'], 0)
        self.assertNotIn('TEST ONLY', json.dumps(metrics))

    async def test_cursor_operation_scopes_are_task_local(self):
        async def rows():
            await asyncio.sleep(0); yield 1
        metrics = {}; conn = MeasuredConnection(SimpleNamespace(cursor=lambda *a: rows()), metrics)
        async def read(group):
            with query_scope(group):
                return [value async for value in conn.cursor('TEST ONLY')]
        self.assertEqual(await asyncio.gather(read('sequences'), read('backup_fingerprints')), [[1], [1]])
        finish(metrics)
        for group in ('sequences', 'backup_fingerprints'):
            self.assertEqual(metrics['driverOperationGroups'][group]['cursor_next']['calls'], 2)
        self.assertEqual(metrics['driverOperationGroups']['other']['cursor_next']['calls'], 0)

    async def test_operation_durations_are_exclusive_and_finish_detects_tampering(self):
        async def rows(): yield 7
        ticks = iter([0, .25, 1, 1.5, 2, 2.75, 3, 4])
        metrics = {}; conn = MeasuredConnection(SimpleNamespace(cursor=lambda *a: rows()), metrics,
                                                clock=lambda: next(ticks))
        with query_scope('sequences'):
            self.assertEqual([value async for value in conn.cursor('TEST ONLY')], [7])
        finish(metrics)
        self.assertEqual(metrics['driverOperations']['cursor_next']['seconds'], 1.75)
        metrics['driverOperationGroups']['sequences']['cursor_next']['completed'] += 1
        with self.assertRaises(ValueError): finish(metrics)
