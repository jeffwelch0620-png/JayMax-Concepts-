"""Split backup round trip on a disposable PostgreSQL: main backup without the raw Toast report
rows, monthly files with them, and a restore check that needs both. Fictional rows only.

Only the hosted routing and private-folder seams are replaced; SQL, snapshots, pg_dump,
encryption and pg_restore are real."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import asyncpg
import hosted_backup as backup
import native_backup as native
import toast_payload_backup as payloads

PROJECT = 'abcdefghijklmnopqrst'
URL = 'postgresql://postgres.' + PROJECT + ':TEST_ONLY@aws-0-us-east-1.pooler.supabase.com:5432/postgres'
MARCH, APRIL = '2026-03', '2026-04'
TRICKY = 'TEST ONLY line one\nline two \\ "quoted" é ✓'


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN') and os.getenv('NATIVE_BACKUP_PG_DUMP'),
                     'Disposable loopback PostgreSQL and pg_dump required')
class SplitBackupDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.control = os.environ['NATIVE_PURCHASE_TEST_DSN']
        self.admin = await asyncpg.connect(self.control)
        self.databases = []
        self.source = await self.database('native_purchase_test_')
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.dump = Path(os.environ['NATIVE_BACKUP_PG_DUMP'])
        self.restore_bin = self.dump.with_name('pg_restore' + self.dump.suffix)
        conn = await asyncpg.connect(self.source)
        try:
            # Times must come back identical whatever the session time zone.
            await conn.execute(f"ALTER DATABASE {native.quoted(self.source.rsplit('/', 1)[1])} SET timezone='America/New_York'")
            for schema in backup.CURRENT_SCHEMAS:
                if schema != 'public':
                    await conn.execute('CREATE SCHEMA ' + schema)
            await conn.execute('''
                CREATE TABLE integrations.toast_sync_runs(id uuid PRIMARY KEY, status text NOT NULL);
                CREATE TABLE integrations.toast_report_payloads(id uuid PRIMARY KEY,
                    sync_run_id uuid NOT NULL REFERENCES integrations.toast_sync_runs(id),
                    report_kind text NOT NULL, business_date date NOT NULL, payload jsonb NOT NULL,
                    fetched_at timestamptz NOT NULL, ingestion_metadata jsonb);
                CREATE INDEX ON integrations.toast_report_payloads(business_date);
                CREATE TABLE integrations.toast_sales_days(store_id text, business_date date,
                    source_payload_id uuid REFERENCES integrations.toast_report_payloads(id),
                    PRIMARY KEY(store_id, business_date));''')
            self.run = uuid4()
            await conn.execute("INSERT INTO integrations.toast_sync_runs VALUES($1,'succeeded')", self.run)
            self.rows = []
            for day in ('2026-03-01', '2026-03-31', '2026-04-15'):
                self.rows.append(await self.payload(conn, day))
            await conn.execute("INSERT INTO integrations.toast_sales_days SELECT 'berts', business_date, id FROM integrations.toast_report_payloads")
        finally:
            await conn.close()

    async def asyncTearDown(self):
        try:
            for name in reversed(self.databases):
                await self.admin.execute(f'DROP DATABASE IF EXISTS {native.quoted(name)} WITH (FORCE)')
        finally:
            await self.admin.close()
            self.folder.cleanup()

    async def database(self, prefix):
        name = prefix + uuid4().hex
        await self.admin.execute('CREATE DATABASE ' + native.quoted(name))
        self.databases.append(name)
        return self.control.rsplit('/', 1)[0] + '/' + name

    async def payload(self, conn, day):
        row = uuid4()
        await conn.execute('''INSERT INTO integrations.toast_report_payloads VALUES($1,$2,'sales',$3::text::date,$4::jsonb,
            '2026-11-12 01:02:03.456789+00',$5::jsonb)''', row, self.run, day,
            json.dumps({'note': TRICKY, 'lines': [{'amount': 12.5}]}), json.dumps({'paginationComplete': True}))
        return str(row)

    def private_directory(self, path, area):
        path = Path(path)
        path.mkdir(parents=True)
        return path

    async def main_backup(self):
        settings = native.disposable_connection(self.source)
        real_tool = backup.tool
        async def connect(*args, **kwargs):
            return await asyncpg.connect(self.source, server_settings={'default_transaction_read_only': 'on'})
        async def tool(executable, args, settings=None, remote=False):
            return await real_tool(executable, args, settings, False)
        import maintenance_connection
        with patch.object(maintenance_connection, 'dump_settings', AsyncMock(return_value=settings)), \
             patch.object(maintenance_connection, 'connect', connect), \
             patch.object(backup, 'private_directory', self.private_directory), patch.object(backup, 'tool', tool):
            label = uuid4().hex
            return await backup.export_backup(URL, PROJECT, self.dump, self.restore_bin, self.root / label / 'archive',
                self.root / label / 'key', {}, maintenance_direct_ipv6=True, schemas=backup.CURRENT_SCHEMAS,
                streamed=True, split_tables=(backup.SPLIT_TABLE,))

    async def monthly(self, months):
        async def connect(url):
            return await asyncpg.connect(self.source)
        with patch.object(backup, 'hosted_connection', return_value={}), patch.object(payloads, 'connect', connect), \
             patch.object(backup, 'private_directory', self.private_directory):
            label = uuid4().hex
            return await payloads.export_months(URL, PROJECT, months, self.root / label / 'archive', self.root / label / 'key')

    async def restore(self, result, monthly_results):
        target = await self.database('native_purchase_test_backup_')
        pairs = [(Path(m['file']), Path(r['privateKey'])) for r in monthly_results for m in r['months']]
        with patch.object(backup, 'private_directory', self.private_directory):
            return await backup.verify_restore(target, result['encryptedBackup'], result['privateKey'], PROJECT,
                                               self.restore_bin, self.root / uuid4().hex, payload_backups=pairs), target

    async def test_main_backup_leaves_rows_out_and_restores_with_its_monthly_files(self):
        result = await self.main_backup()
        self.assertEqual(result['separateTableRows'], {backup.SPLIT_TABLE: 3})
        manifest = backup.decrypt_backup(result['encryptedBackup'], result['privateKey'], PROJECT)
        self.assertEqual(manifest['tablesInSeparateBackups'], [backup.SPLIT_TABLE])
        self.assertEqual(manifest['separateTableRowIds'][backup.SPLIT_TABLE], sorted(self.rows))
        self.assertTrue(manifest['tables'][backup.SPLIT_TABLE]['rowsInSeparateBackups'])
        # The archive itself holds no report rows.
        archive = bytearray()
        backup.decrypt_backup(result['encryptedBackup'], result['privateKey'], PROJECT, archive.extend)
        self.assertNotIn(b'TEST ONLY line one', bytes(archive))

        # A row saved after the main backup is in the monthly file but not wanted by the restore.
        conn = await asyncpg.connect(self.source)
        try:
            later = await self.payload(conn, '2026-04-20')
        finally:
            await conn.close()
        months = await self.monthly([MARCH, APRIL])
        self.assertEqual([(m['month'], m['rows']) for m in months['months']], [(MARCH, 2), (APRIL, 2)])
        files = [m['file'] for m in months['months']]
        self.assertEqual(payloads.verify_months(files, months['privateKey'], PROJECT)['rows'], 4)

        restored, target = await self.restore(result, [months])
        self.assertEqual(restored['status'], 'verified_application_restore')
        self.assertEqual(restored['rowsLoaded'], 3)
        conn = await asyncpg.connect(target)
        try:
            self.assertEqual(await conn.fetchval("SELECT payload->>'note' FROM integrations.toast_report_payloads LIMIT 1"), TRICKY)
            self.assertFalse(await conn.fetchval('SELECT EXISTS(SELECT 1 FROM integrations.toast_report_payloads WHERE id=$1::uuid)', later))
            # Links and indexes came back after the rows.
            self.assertEqual(await conn.fetchval("SELECT count(*) FROM pg_constraint WHERE conrelid='integrations.toast_sales_days'::regclass AND contype='f'"), 1)
            self.assertEqual(await conn.fetchval("SELECT count(*) FROM pg_indexes WHERE schemaname='integrations' AND tablename='toast_report_payloads'"), 2)
        finally:
            await conn.close()

    async def test_restore_refuses_without_every_needed_row(self):
        result = await self.main_backup()
        with self.assertRaisesRegex(backup.BackupError, 'needs its monthly payload backups'):
            await self.restore(result, [])
        march = await self.monthly([MARCH])
        with self.assertRaisesRegex(backup.BackupError, 'missing 1 rows'):
            await self.restore(result, [march])

    async def test_damaged_or_mismatched_monthly_file_is_refused_before_any_write(self):
        result = await self.main_backup()
        months = await self.monthly([MARCH, APRIL])
        march = Path(months['months'][0]['file'])
        data = bytearray(march.read_bytes())
        data[-5] ^= 1
        march.write_bytes(bytes(data))
        with self.assertRaisesRegex(backup.BackupError, 'authentication or manifest'):
            await self.restore(result, [months])
        with self.assertRaisesRegex(backup.BackupError, 'authentication or manifest'):
            payloads.read_month(months['months'][1]['file'], months['privateKey'], 'zyxwvutsrqponmlkjihg')
