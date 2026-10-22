"""Fictional driver calls prove timing attribution, restoration and redaction."""
import asyncio
import json
from types import SimpleNamespace
import unittest
from local_query_metrics import MeasuredConnection, finish, instrument_functions, query_scope


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
