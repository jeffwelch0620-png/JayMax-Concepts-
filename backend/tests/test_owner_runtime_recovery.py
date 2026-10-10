"""Owner-backed application transactions under an ordinary disposable role."""
import os,re
from urllib.parse import urlparse
from uuid import uuid4
from unittest.mock import patch
import asyncpg
import deployment_readiness as readiness
import test_deployment_readiness as checks
import test_native_backup as backup_checks


class OwnerRuntimeRecoveryTests(checks.DeploymentReadinessTests):
    async def asyncSetUp(self):
        self.runtime_role='native_purchase_test_runtime_'+uuid4().hex
        self.control=os.environ['NATIVE_PURCHASE_TEST_DSN']
        admin=await asyncpg.connect(self.control)
        try:
            await admin.execute('CREATE ROLE "'+self.runtime_role+'" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS')
        finally:await admin.close()
        self.addAsyncCleanup(self.drop_runtime_role)
        self.original_pool=asyncpg.create_pool
        with patch.object(asyncpg,'create_pool',side_effect=self.runtime_pool):
            await super().asyncSetUp()

    async def drop_runtime_role(self):
        admin=await asyncpg.connect(self.control)
        try:await admin.execute('DROP ROLE "'+self.runtime_role+'"')
        finally:await admin.close()

    async def runtime_pool(self,dsn,*args,**kwargs):
        uri=urlparse(dsn);name=uri.path.lstrip('/')
        if uri.hostname not in ('127.0.0.1','localhost') or not re.fullmatch(r'native_purchase_test_(restore_)?[0-9a-f]{32}',name):
            raise RuntimeError('Ordinary-role test refuses non-disposable databases')
        admin=await asyncpg.connect(self.control)
        try:await admin.execute('ALTER DATABASE "'+name+'" OWNER TO "'+self.runtime_role+'"')
        finally:await admin.close()
        return await self.original_pool(dsn,*args,user=self.runtime_role,**kwargs)

    async def assert_ordinary(self,pool):
        async with pool.acquire() as conn:
            role=await conn.fetchrow('SELECT current_user AS name,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user')
            self.assertEqual(role['name'],self.runtime_role)
            self.assertFalse(role['rolsuper']);self.assertFalse(role['rolbypassrls'])
            result=await readiness.inspect(conn,(self.client_role,),('berts','rudds'))
            self.assertEqual(result['status'],'passed',result['issues'])
            self.assertEqual(len(result['migrations']),29)

    async def test_ordinary_owner_inventory_transactions_and_restore_preserve_exact_replay(self):
        async with self.pool.acquire() as conn:
            await conn.execute((readiness.ROOT/'migrations/20261007_native_private_access.sql').read_text(encoding='utf-8'))
        await self.assert_ordinary(self.pool)
        # The existing full recovery contract posts/corrects synthetic purchases,
        # uses explicit physical-count values, closes/reopens periods, preserves
        # multiline source bytes and tests original request-key replay after restore.
        # Source and restored API pools both connect as the ordinary owning role.
        with patch.object(asyncpg,'create_pool',side_effect=self.runtime_pool):
            await backup_checks.NativeBackupTests.test_full_recovery_preserves_rows_schema_acl_reports_and_write_guards(self)
        self.assertTrue(self.target_pools)
        for pool in self.target_pools:await self.assert_ordinary(pool)
