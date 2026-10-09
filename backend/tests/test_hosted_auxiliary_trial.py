"""Wrong project, unsupported endpoint or enabled features must precede all SQL."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch
import hosted_auxiliary_trial as trial

class TargetGuardTests(unittest.IsolatedAsyncioTestCase):
    async def held_before_connection(self, config, project):
        with TemporaryDirectory() as folder, patch.object(trial, 'dotenv_values', return_value=config), patch.object(
                trial.asyncpg, 'connect', AsyncMock()) as connect:
            output=Path(folder)/'receipt.json'
            with self.assertRaises((ValueError, trial.hosted_test_trial.DevelopmentTargetError)):
                await trial.run(Path(folder)/'private.env',project,output)
            connect.assert_not_awaited()
            self.assertFalse(output.exists())

    async def test_wrong_project_never_connects(self):
        await self.held_before_connection({'USE_PG':'true','DATABASE_URL':
            'postgresql://postgres.aaaaaaaaaaaaaaaaaaaa:invented@aws-0-us-east-1.pooler.supabase.com:5432/postgres'}, 'bbbbbbbbbbbbbbbbbbbb')

    async def test_direct_endpoint_is_held_for_session_pooler_trial(self):
        await self.held_before_connection({'USE_PG':'true','DATABASE_URL':
            'postgresql://postgres:invented@db.aaaaaaaaaaaaaaaaaaaa.supabase.co:5432/postgres'}, 'aaaaaaaaaaaaaaaaaaaa')

    async def test_enabled_native_features_never_connect(self):
        await self.held_before_connection({'USE_PG':'true','PURCHASE_IMPORT_ENABLED':'true','DATABASE_URL':
            'postgresql://postgres.aaaaaaaaaaaaaaaaaaaa:invented@aws-0-us-east-1.pooler.supabase.com:5432/postgres'}, 'aaaaaaaaaaaaaaaaaaaa')
