"""Backup authenticity, scope, restore boundary and secret-safe subprocess guards."""
import base64
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from cryptography.fernet import Fernet
import hosted_backup as backup

PROJECT = 'abcdefghijklmnopqrst'


class EncryptionTests(unittest.TestCase):
    def test_restore_list_keeps_public_acl_and_tables_but_skips_schema_recreation(self):
        toc = b'; header\n5; 2615 2200 SCHEMA - public pg_database_owner\n10; 0 0 ACL - SCHEMA public pg_database_owner\n11; 1259 12345 TABLE public app_users postgres\n12; 2615 12346 SCHEMA - purchasing postgres\n'
        result = backup.restore_list(toc)
        self.assertIn(b'; 5; 2615 2200 SCHEMA - public', result)
        self.assertIn(b'10; 0 0 ACL - SCHEMA public', result)
        self.assertIn(b'11; 1259 12345 TABLE public app_users', result)
        self.assertIn(b'12; 2615 12346 SCHEMA - purchasing', result)
        with self.assertRaises(backup.BackupError):
            backup.restore_list(b'; no public schema\n')
        with self.assertRaises(backup.BackupError):
            backup.restore_list(toc + b'13; 2615 2345 SCHEMA - public postgres\n')

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.key = root / 'key'
        self.key.write_bytes(Fernet.generate_key())
        self.archive = b'PGDMP\x00synthetic\r\ninvoice bytes\x00'
        self.manifest = {'format': backup.FORMAT, 'projectRef': PROJECT, 'schemas': list(backup.SCHEMAS),
            'archiveBytes': len(self.archive), 'archiveSha256': backup.digest(self.archive)}
        self.encrypted = root / 'backup.enc'
        self.save()

    def save(self):
        value = {'manifest': self.manifest, 'archive': base64.b64encode(self.archive).decode()}
        self.encrypted.write_bytes(Fernet(self.key.read_bytes()).encrypt(json.dumps(value).encode()))

    def test_roundtrip_preserves_binary_and_crlf(self):
        manifest, data = backup.open_backup(self.encrypted, self.key, PROJECT)
        self.assertEqual(data, self.archive)
        self.assertEqual(manifest, self.manifest)
        self.assertNotIn(b'invoice bytes', self.encrypted.read_bytes())

    def test_damage_wrong_key_and_wrong_project_are_rejected(self):
        for mode in ('damage', 'key', 'project'):
            self.key.write_bytes(Fernet.generate_key()); self.save()
            project = PROJECT
            if mode == 'damage':
                damaged = bytearray(self.encrypted.read_bytes()); damaged[-20] ^= 1
                self.encrypted.write_bytes(damaged)
            elif mode == 'key':
                self.key.write_bytes(Fernet.generate_key())
            else:
                project = 'differentprojectxxxx'
            with self.assertRaises(backup.BackupError):
                backup.open_backup(self.encrypted, self.key, project)

    def test_authenticated_but_partial_or_wrong_digest_manifest_is_rejected(self):
        for mode in ('schemas', 'digest', 'size'):
            original = dict(self.manifest)
            if mode == 'schemas': self.manifest['schemas'] = ['public']
            elif mode == 'digest': self.manifest['archiveSha256'] = 'bad'
            else: self.manifest['archiveBytes'] += 1
            self.save()
            with self.assertRaises(backup.BackupError):
                backup.open_backup(self.encrypted, self.key, PROJECT)
            self.manifest = original


class BoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_private_directory_acl_and_no_overwrite_boundary(self):
        path = Path(os.environ['LOCALAPPDATA']) / 'JayMaxBuild/backups' / ('backup-' + uuid4().hex)
        self.assertEqual(backup.private_directory(path, 'backups'), path)
        self.addCleanup(path.rmdir)
        with self.assertRaises(backup.BackupError):
            backup.private_directory(path, 'backups')
        with self.assertRaises(backup.BackupError):
            backup.private_directory(Path(self._testMethodName), 'backups')

    def test_expected_owner_project_session_endpoint_required(self):
        valid = 'postgresql://postgres.' + PROJECT + ':synthetic@aws-0.pooler.supabase.com:5432/postgres'
        self.assertEqual(backup.hosted_connection(valid, PROJECT)['database'], 'postgres')
        for url in (valid.replace(':5432', ':6543'), valid + '?host=elsewhere',
                    valid.replace(PROJECT, 'differentprojectxxxx'), valid.replace('/postgres', '/operational'),
                    valid.replace('aws-0.pooler.supabase.com', '127.0.0.1')):
            with self.assertRaises(backup.BackupError):
                backup.hosted_connection(url, PROJECT)

    async def test_remote_control_and_existing_style_destinations_refused_before_connect(self):
        for url in ('postgresql://test@example.com/native_purchase_test_backup_' + 'a' * 32,
                    'postgresql://test@127.0.0.1/native_purchase_test_control',
                    'postgresql://test@127.0.0.1/native_purchase_test_old'):
            with patch.object(backup.asyncpg, 'connect', AsyncMock()) as connect:
                with self.assertRaises((backup.BackupError, backup.native.BackupError)):
                    await backup.verify_restore(url, 'missing', 'missing', PROJECT, 'missing', 'missing')
                connect.assert_not_awaited()

    async def test_untrusted_backup_refused_before_connection_or_target_writes(self):
        dsn = 'postgresql://test@127.0.0.1/native_purchase_test_backup_' + 'a' * 32
        with patch.object(backup.asyncpg, 'connect', AsyncMock()) as connect:
            with self.assertRaises(backup.BackupError):
                await backup.verify_restore(dsn, 'missing', 'missing', PROJECT, 'missing', 'missing')
            connect.assert_not_awaited()

    def test_pg_service_indirection_removed_and_remote_tls_required(self):
        settings = {'host': 'example', 'port': 5432, 'user': 'role', 'password': 'synthetic-secret', 'database': 'db'}
        with patch.dict(os.environ, PGSERVICE='untrusted', PGSERVICEFILE='untrusted', PGSSLMODE='disable'):
            env = backup.process_env(settings, True)
        self.assertNotIn('PGSERVICE', env)
        self.assertNotIn('PGSERVICEFILE', env)
        self.assertEqual(env['PGSSLMODE'], 'verify-full')
        self.assertIn('default_transaction_read_only=on', env['PGOPTIONS'])

    async def test_dump_errors_do_not_expose_driver_text(self):
        result = type('Result', (), {'returncode': 1, 'stderr': b'synthetic-private-password', 'stdout': b''})()
        with patch.object(backup.subprocess, 'run', return_value=result):
            with self.assertRaises(backup.BackupError) as caught:
                await backup.tool('synthetic', [])
        self.assertNotIn('synthetic-private-password', str(caught.exception))
