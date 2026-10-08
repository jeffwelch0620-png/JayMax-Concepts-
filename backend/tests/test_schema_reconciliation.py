"""Catalog comparisons and migration history probes; disposable schema only."""
import copy
import json
import os
from pathlib import Path
import unittest
from urllib.parse import urlparse
from uuid import uuid4

import asyncpg
import deployment_readiness as readiness
import schema_reconciliation as reconciliation


class SchemaComparisonTests(unittest.TestCase):
    def snapshot(self):
        catalog = {key: [] for key in reconciliation.KEYS}
        catalog['columns'] = [{'nspname': 'public', 'relname': 'items', 'attname': 'quantity', 'type': 'numeric'}]
        catalog['functions'] = [{'nspname': 'public', 'proname': 'same_name', 'args': 'value integer', 'definition_sha256': 'first', 'owner': 'local'},
                                {'nspname': 'public', 'proname': 'same_name', 'args': 'value text', 'definition_sha256': 'second', 'owner': 'local'}]
        return {'format': reconciliation.FORMAT, 'catalog': catalog, 'migrationHistory': {'status': 'unavailable'}, 'serverVersion': '17'}

    def test_changed_type_removed_overload_and_added_column_are_not_silently_accepted(self):
        reference = self.snapshot(); hosted = copy.deepcopy(reference)
        hosted['catalog']['columns'][0]['type'] = 'text'
        hosted['catalog']['columns'].append({'nspname': 'public', 'relname': 'items', 'attname': 'future_column', 'type': 'text'})
        hosted['catalog']['functions'].pop()
        report = reconciliation.compare(reference, hosted)
        self.assertEqual(report['status'], 'differences_require_review')
        self.assertEqual({row['kind'] for row in report['differences']}, {'definition_changed', 'missing_on_hosted', 'hosted_addition'})
        self.assertFalse(report['operationalReleaseApproved'])

    def test_owner_changes_and_private_schemas_remain_separate_from_public_structure(self):
        reference = self.snapshot(); hosted = copy.deepcopy(reference)
        hosted['catalog']['functions'][0]['owner'] = 'hosted'
        hosted['catalog']['columns'].append({'nspname': 'integrations', 'relname': 'payloads', 'attname': 'payload', 'type': 'jsonb'})
        report = reconciliation.compare(reference, hosted)
        self.assertEqual(report['status'], 'public_structure_matches_reference')
        self.assertEqual(len(report['ownershipAndAclDifferences']), 1)
        self.assertEqual(report['additionalSchemaObjects']['integrations']['columns'], 1)

    def test_definition_literals_are_hashed_exactly_without_exporting_bodies(self):
        record = {'definition': "SELECT 'two  spaces private-literal'", 'default_expr': "'private-default'::text", 'acl': None}
        safe = reconciliation.safe_record(record)
        self.assertNotIn('private-literal', str(safe)); self.assertNotIn('private-default', str(safe))
        self.assertNotEqual(safe['definition_sha256'], reconciliation.digest(record['definition'].replace('two  spaces', 'two spaces')))

    def test_unknown_format_missing_group_and_duplicate_identity_refuse_comparison(self):
        reference = self.snapshot(); hosted = self.snapshot()
        hosted['format'] = 'unknown'
        with self.assertRaises(ValueError): reconciliation.compare(reference, hosted)
        hosted = self.snapshot(); del hosted['catalog']['columns']
        with self.assertRaises(KeyError): reconciliation.compare(reference, hosted)
        hosted = self.snapshot(); hosted['catalog']['functions'].append(hosted['catalog']['functions'][0])
        with self.assertRaises(ValueError): reconciliation.compare(reference, hosted)


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class SchemaCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        dsn = os.environ['NATIVE_PURCHASE_TEST_DSN']; uri = urlparse(dsn)
        if uri.hostname != '127.0.0.1' or uri.path != '/native_purchase_test_control':
            raise RuntimeError('Dedicated loopback test control database required')
        self.name = 'native_purchase_test_' + uuid4().hex
        self.admin = await asyncpg.connect(dsn)
        await self.admin.execute('CREATE DATABASE "' + self.name + '"')
        self.conn = await asyncpg.connect(dsn.rsplit('/', 1)[0] + '/' + self.name)
        await self.conn.execute((reconciliation.ROOT / 'supabase/schema.sql').read_text(encoding='utf-8'))

    async def asyncTearDown(self):
        await self.conn.close()
        await self.admin.execute('DROP DATABASE "' + self.name + '"')
        await self.admin.close()

    async def test_baseline_catalog_is_repeatable_then_complete_native_chain_is_locally_installable(self):
        reference = await reconciliation.capture(self.conn)
        again = await reconciliation.capture(self.conn)
        self.assertEqual(reference['catalog'], again['catalog'])
        self.assertEqual(reference['migrationHistory']['status'], 'unavailable')
        self.assertFalse(reference['businessRowsIncluded'])
        self.assertEqual(reconciliation.compare(reference, again)['differences'], [])
        path = os.getenv('SCHEMA_REFERENCE_EVIDENCE')
        if path:
            Path(path).write_text(json.dumps(reference, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        for name in readiness.MIGRATIONS:
            await self.conn.execute((readiness.ROOT / 'migrations' / name).read_text(encoding='utf-8'))
        upgraded = await reconciliation.capture(self.conn)
        self.assertGreater(len(upgraded['catalog']['columns']), len(reference['catalog']['columns']))
        self.assertTrue(any(row['nspname'] == 'actual_inventory' for row in upgraded['catalog']['relations']))
        self.assertEqual(await self.conn.fetchval('SELECT count(*) FROM purchasing.posting_batches'), 0)
        self.assertEqual(await self.conn.fetchval('SELECT count(*) FROM actual_inventory.count_snapshots'), 0)

    async def test_live_catalog_changes_and_ledger_differences_are_reported(self):
        baseline = await reconciliation.capture(self.conn)
        await self.conn.execute('CREATE SCHEMA supabase_migrations; CREATE TABLE supabase_migrations.schema_migrations(version text PRIMARY KEY,name text,statements text[])')
        expected = reconciliation.reference_history()
        await self.conn.executemany('INSERT INTO supabase_migrations.schema_migrations VALUES($1,$2,ARRAY[\'private-migration-body\'])', [(row['version'], row['name']) for row in expected])
        history = await reconciliation.migration_history(self.conn)
        self.assertEqual(history['status'], 'identities_match'); self.assertFalse(history['statementChecksumsVerified'])
        self.assertNotIn('private-migration-body', str(history))
        await self.conn.execute('DELETE FROM supabase_migrations.schema_migrations WHERE version=$1', expected[0]['version'])
        await self.conn.execute('UPDATE supabase_migrations.schema_migrations SET name=\'changed_name\' WHERE version=$1', expected[1]['version'])
        await self.conn.execute("INSERT INTO supabase_migrations.schema_migrations(version,name) VALUES('20990101000000','future')")
        await self.conn.execute('ALTER TABLE public.items ADD COLUMN future_column text; ALTER TABLE public.items DISABLE TRIGGER t_items')
        changed = await reconciliation.capture(self.conn)
        history = changed['migrationHistory']
        self.assertEqual(history['status'], 'different')
        self.assertEqual(len(history['missingReferenceVersions']), 1)
        self.assertEqual(len(history['renamedReferenceVersions']), 1)
        self.assertEqual(len(history['additionalVersions']), 1)
        report = reconciliation.compare(baseline, changed)
        self.assertTrue(any(row['group'] == 'columns' and row['object'].endswith('future_column') for row in report['differences']))
        self.assertTrue(any(row['group'] == 'triggers' for row in report['differences']))
