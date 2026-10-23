"""Fictional driver calls prove timing attribution, restoration and redaction."""
import asyncio
import json
from types import SimpleNamespace
import unittest
from local_query_metrics import (MeasuredConnection, finish, instrument_functions,
                                query_scope, relation_group, GROUPS)


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
        driver = SimpleNamespace(fetch=fetch, transaction=lambda: 'TEST ONLY transaction')
        metrics = {}; conn = MeasuredConnection(driver, metrics)
        async def scoped():
            with query_scope('capture_catalog'): await conn.fetch('TEST ONLY')
        async def unscoped():
            await ready.wait(); await conn.fetch('TEST ONLY')
        await asyncio.gather(scoped(), unscoped())
        self.assertEqual(conn.transaction(), 'TEST ONLY transaction')
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
        self.assertEqual(set(metrics['exclusiveGroups']), set(GROUPS))
        self.assertNotIn('TEST ONLY', json.dumps(metrics))
