"""Provisioning guards must hold before network access or credential replacement."""
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch
import provision_build_connections as provision

CONFIG={'USE_PG':'true','DATABASE_URL':
  'postgresql://postgres.aaaaaaaaaaaaaaaaaaaa:invented@aws-0-us-east-1.pooler.supabase.com:5432/postgres'}

class PlanGuards(unittest.IsolatedAsyncioTestCase):
    async def test_mismatched_target_never_checks_storage_or_connects(self):
        with patch.object(provision,'dotenv_values',return_value=CONFIG), patch.object(provision,'private_directory') as storage, patch.object(
                provision.asyncpg,'connect',AsyncMock()) as connect:
            with self.assertRaises(provision.hosted_test_trial.DevelopmentTargetError):
                await provision.run(Path('unused.env'),'bbbbbbbbbbbbbbbbbbbb',Path('unused'),Path('unused.json'))
            storage.assert_not_called();connect.assert_not_awaited()

    async def test_private_storage_hold_never_connects(self):
        with patch.object(provision,'dotenv_values',return_value=CONFIG), patch.object(provision,'private_directory',side_effect=ValueError), patch.object(
                provision.asyncpg,'connect',AsyncMock()) as connect:
            with self.assertRaises(ValueError):
                await provision.run(Path('unused.env'),'aaaaaaaaaaaaaaaaaaaa',Path('unused'),Path('unused.json'))
            connect.assert_not_awaited()

class PrivateStorageGuards(unittest.TestCase):
    def test_outside_local_credential_root_rejected_before_acl_command(self):
        with TemporaryDirectory() as folder, patch.object(provision.subprocess,'run') as command:
            with self.assertRaises(ValueError):provision.private_directory(Path(folder))
            command.assert_not_called()

    def test_failed_acl_check_holds_and_existing_file_is_never_overwritten(self):
        with TemporaryDirectory() as folder, patch.dict(os.environ,{'LOCALAPPDATA':folder}):
            target=Path(folder)/'JayMaxBuild/credentials/test';target.mkdir(parents=True)
            with patch.object(provision.subprocess,'run',return_value=subprocess.CompletedProcess([],2,b'',b'')):
                with self.assertRaises(ValueError):provision.private_directory(target)
            existing=target/'runtime-connections.env';existing.write_text('original-marker',encoding='utf-8')
            with patch.object(provision.subprocess,'run',return_value=subprocess.CompletedProcess([],0,b'verified\r\n',b'')):
                with self.assertRaises(ValueError):provision.private_directory(target)
            self.assertEqual(existing.read_text(encoding='utf-8'),'original-marker')
