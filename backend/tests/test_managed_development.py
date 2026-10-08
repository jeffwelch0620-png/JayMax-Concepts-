"""Offline delivery-integrity and target-refusal checks; no hosted connections."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

import managed_development as development
import deployment_readiness as readiness

SOURCE = 'a' * 20
TARGET = 'b' * 20


def direct(ref):
    return f'postgresql://postgres:synthetic-secret@db.{ref}.supabase.co:5432/postgres'


def pooled(ref):
    return f'postgresql://postgres.{ref}:synthetic-secret@aws-0-synthetic.pooler.supabase.com:5432/postgres'


class DeliveryTests(unittest.TestCase):
    def test_exact_bytes_dependency_order_and_unique_delivery_versions(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / 'bundle'
            manifest = development.prepare_bundle(root)
            self.assertEqual([e['sourceFile'] for e in manifest['migrations']],
                             ['migrations/' + name for name in readiness.MIGRATIONS])
            self.assertEqual(development.verify_bundle(root)['files'], 29)
            self.assertFalse(manifest['automaticApply'])
            self.assertFalse(manifest['deliveryVersionsAreHistoricalAppliedVersions'])
            versions = [e['deliveryVersion'] for e in manifest['migrations']]
            self.assertEqual(len(set(versions)), 29)
            for entry in manifest['migrations']:
                self.assertEqual((root / entry['deliveryFile']).read_bytes(),
                                 (readiness.ROOT / entry['sourceFile']).read_bytes())
            with self.assertRaises(ValueError): development.prepare_bundle(root)

    def test_changed_sql_missing_extra_and_reordered_entries_refuse_delivery(self):
        for change in ('sql', 'missing', 'extra', 'order'):
            with self.subTest(change=change), TemporaryDirectory() as tmp:
                root = Path(tmp) / 'bundle'; manifest = development.prepare_bundle(root)
                file = root / manifest['migrations'][0]['deliveryFile']
                if change == 'sql': file.write_bytes(file.read_bytes() + b'\nSELECT 1;')
                if change == 'missing': file.unlink()
                if change == 'extra': (root / 'native-migrations/20990101000000_unreviewed.sql').write_text('SELECT 1;')
                if change == 'order':
                    manifest['migrations'][0], manifest['migrations'][1] = manifest['migrations'][1], manifest['migrations'][0]
                    (root / 'manifest.json').write_text(json.dumps(manifest))
                with self.assertRaises((ValueError, FileNotFoundError)): development.verify_bundle(root)

    def test_same_project_direct_and_pooler_are_refused_and_distinct_ref_is_required(self):
        for url in (direct(SOURCE), pooled(SOURCE)):
            with self.assertRaises(development.DevelopmentTargetError):
                development.target_identity(direct(SOURCE), url, SOURCE)
        for expected in ('', SOURCE, 'invalid'):
            with self.assertRaises(development.DevelopmentTargetError):
                development.target_identity(direct(SOURCE), pooled(TARGET), expected)
        self.assertEqual(development.target_identity(direct(SOURCE), pooled(TARGET), TARGET)['projectRef'], TARGET)

    def test_transaction_pooling_spoofed_hosts_queries_and_incomplete_urls_refused(self):
        for url in (pooled(TARGET).replace(':5432', ':6543'), direct(TARGET) + '?host=elsewhere',
                    direct(TARGET) + '#fragment', direct(TARGET).replace('.supabase.co', '.supabase.co.evil.invalid'),
                    pooled(TARGET).replace('pooler.supabase.com', 'example.invalid'),
                    direct(TARGET).replace('synthetic-secret', '[YOUR-PASSWORD]'),
                    direct(TARGET).replace('synthetic-secret', ''), 'bad',
                    direct(TARGET).replace(':5432', ':bad')):
            with self.subTest(url=url), self.assertRaises(development.DevelopmentTargetError) as context:
                development.project_identity(url)
            self.assertNotIn('synthetic-secret', str(context.exception))


class TargetInspectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_source_target_and_enabled_feature_refusals_happen_before_connection(self):
        source = {'DATABASE_URL': direct(SOURCE)}
        target = {'DATABASE_URL': pooled(TARGET), 'JMAX_DEVELOPMENT_PROJECT_REF': TARGET, 'USE_PG': 'true',
                  **{name + '_ENABLED': 'false' for name in readiness.FEATURES}}
        for replacement in ({'DATABASE_URL': pooled(SOURCE), 'JMAX_DEVELOPMENT_PROJECT_REF': SOURCE},
                            {'PURCHASE_IMPORT_ENABLED': 'true'}, {'USE_PG': 'false'}):
            with patch.object(development, 'dotenv_values', side_effect=[source, {**target, **replacement}]), \
                    patch.object(development.asyncpg, 'connect', new_callable=AsyncMock) as connect:
                report = await development.inspect_target('source-private', 'target-private')
                self.assertEqual(report['status'], 'held'); connect.assert_not_awaited()
                self.assertNotIn('synthetic-secret', str(report))

    async def test_driver_value_errors_are_redacted_and_read_only_ssl_is_required(self):
        values = [{'DATABASE_URL': direct(SOURCE)},
                  {'DATABASE_URL': pooled(TARGET), 'JMAX_DEVELOPMENT_PROJECT_REF': TARGET, 'USE_PG': 'true',
                   **{name + '_ENABLED': 'false' for name in readiness.FEATURES}}]
        with patch.object(development, 'dotenv_values', side_effect=values), \
                patch.object(development.asyncpg, 'connect', new_callable=AsyncMock,
                             side_effect=ValueError('driver included synthetic-secret')) as connect:
            report = await development.inspect_target('source-private', 'target-private')
        self.assertEqual(report['status'], 'held')
        self.assertNotIn('synthetic-secret', str(report))
        self.assertEqual(report['errorType'], 'ValueError')
        self.assertEqual(connect.call_args.kwargs['ssl'], 'require')
        self.assertEqual(connect.call_args.kwargs['server_settings']['default_transaction_read_only'], 'on')
