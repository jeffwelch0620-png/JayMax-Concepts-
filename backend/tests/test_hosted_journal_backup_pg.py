"""Owned disposable PostgreSQL only. No real hosted DNS, credentials or artifacts."""
import asyncio
from copy import deepcopy
from datetime import datetime,timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock,patch
from urllib.parse import urlsplit
from uuid import UUID,uuid4

import asyncpg
from cryptography.fernet import Fernet
import hosted_backup as legacy
import hosted_journal_backup as journal
import journal_backup_receipts as receipts
from application_backup_profiles import Held,LEGACY6,RECEIVING7,canonical,digest
import manager_handoff as handoff
import test_manager_handoff as fixture
from test_journal_backup_receipts import binding,packet,POLICY
from test_hosted_journal_backup import PROJECT,URL
from readonly_snapshot import readonly_snapshot


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable loopback PostgreSQL required')
class JournalDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        other=os.environ.get('NATIVE_JOURNAL_RESTORE_TEST_DSN')
        if other:
            u=urlsplit(other)
            if (u.hostname not in ('127.0.0.1','::1') or u.port is None or u.port<1024
                    or u.path!='/native_purchase_test_control' or u.username!='purchase_implementation_test'
                    or u.scheme not in ('postgres','postgresql') or u.query or u.fragment):
                raise Held('fictional_second_control_required')
        await fixture.HandoffDatabaseTests.asyncSetUp(self)
        self.source_url=os.environ['NATIVE_PURCHASE_TEST_DSN'].rsplit('/',1)[0]+'/'+self.db
        self.control_url=os.environ['NATIVE_PURCHASE_TEST_DSN']
        self.restore_control=other or self.control_url
        self.restore_admin=await asyncpg.connect(other) if other else self.admin
        self.restore_roles=[]
        self.settings=journal.native.disposable_connection(self.source_url)
        self.dump=Path(os.environ['NATIVE_BACKUP_PG_DUMP'])
        self.restore_bin=self.dump.with_name('pg_restore'+self.dump.suffix)
        self.targets=[];self.roles=[]
        self.opened_pids=[]
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)
        async with self.pool.acquire() as c:
            for schema in ('actual_inventory','prep_inventory','integrations','supabase_migrations'):
                await c.execute('CREATE SCHEMA '+schema)
            await c.execute('''CREATE TABLE supabase_migrations.schema_migrations(version text PRIMARY KEY,name text,statements text[]);
                INSERT INTO supabase_migrations.schema_migrations VALUES('20991025000001','TEST ONLY journal',ARRAY['SELECT 1;']);
                CREATE TABLE purchasing.test_source_bytes(id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,raw bytea,cost numeric(38,18));''')
            self.raw=b'TEST ONLY PFG\r\nunknown unmapped field,\x00\xff'
            await c.execute("INSERT INTO purchasing.test_source_bytes(raw,cost) VALUES($1,0.000000000000000001)",self.raw)
        self.value=fixture.body();self.key=uuid4()
        r=await fixture.HandoffDatabaseTests.command(self,self.value,key=str(self.key));self.assertEqual(r.status_code,200,r.text)
        for expected,change in ((1,dict(action='submit')),(2,dict(action='correct',summary='TEST ONLY corrected',correction_reason='TEST ONLY measured'))):
            r=await fixture.HandoffDatabaseTests.command(self,self.value|change,expected)
            self.assertEqual(r.status_code,200,r.text)

    async def asyncTearDown(self):
        for db in reversed(self.targets):
            await self.restore_admin.execute('DROP DATABASE '+db)
        if self.restore_admin is not self.admin:
            try:
                for role in self.restore_roles:await self.restore_admin.execute('DROP ROLE '+role)
            finally:await self.restore_admin.close()
        await fixture.HandoffDatabaseTests.asyncTearDown(self)
        c=await asyncpg.connect(self.control_url)
        try:
            for role in reversed(self.roles):await c.execute('DROP ROLE '+role)
        finally:await c.close()

    def private_directory(self,path,area):
        path=Path(path);path.mkdir(parents=True,exist_ok=False);return path

    async def export(self,policy=None,tool=None,timeout=600):
        p=POLICY if policy is None else policy
        b=binding();b['sourceBinding']=journal.source_binding(journal.maintenance.direct_settings(URL,PROJECT),PROJECT)
        b['dependencyPolicySha256']=digest(canonical(p));raw=packet(b,policy=p)
        label=uuid4().hex
        async def connect(*args,**kwargs):
            # Mock the routing boundary only; real session, snapshot and pg_dump.
            c=await asyncpg.connect(self.source_url,server_settings={'default_transaction_read_only':'on',
                'application_name':kwargs.get('label','jaymax-test-only-journal')})
            self.opened_pids.append(c.get_server_pid())
            return c
        reviewed_tool=legacy.tool
        async def loopback_tool(executable,args,settings=None,remote=False):
            # The production source is TLS-only. This fictional harness routes the
            # explicit loopback tool boundary without a production bypass switch.
            if settings is not None:
                self.assertEqual(settings,self.settings)
            return await reviewed_tool(executable,args,settings,False)
        with patch.object(journal.maintenance,'dump_settings',AsyncMock(return_value=self.settings)),\
             patch.object(journal.maintenance,'connect',connect),\
             patch.object(legacy,'private_directory',self.private_directory),\
             patch.object(legacy,'tool',tool or loopback_tool):
            result=await journal.export_backup(URL,PROJECT,self.dump,self.restore_bin,self.root/label/'archive',self.root/label/'key',
                {'migrations/20991025_test_only.sql':digest(b'TEST ONLY')},execution_packet=raw,packet_sha=digest(raw),timeout_seconds=timeout)
        encrypted=Path(result['encryptedBackup']).read_bytes();key=Path(result['privateKey']).read_bytes()
        return result,encrypted,key,b

    async def target(self):
        name='native_purchase_test_backup_'+uuid4().hex
        await self.restore_admin.execute('CREATE DATABASE '+name);self.targets.append(name)
        oid=await self.restore_admin.fetchval('SELECT oid::bigint FROM pg_database WHERE datname=$1',name)
        system=await self.restore_admin.fetchval('SELECT system_identifier::text FROM pg_control_system()')
        return journal.RestoreTarget(self.restore_control.rsplit('/',1)[0]+'/'+name,self.restore_control,system,oid)

    async def restore(self,target,encrypted,key,b,policy=None):
        with patch.object(legacy,'private_directory',self.private_directory):
            return await journal.verify_restore(target,encrypted,key,self.restore_bin,self.root/uuid4().hex,
                expected=b,expected_encrypted_sha=digest(encrypted),policy=policy or POLICY,execution_window=b['window'])

    async def test_seven_schema_export_restore_preserves_bytes_decimal_history_guards_and_replay(self):
        result,encrypted,key,b=await self.export()
        self.assertEqual(result['status'],'exported_not_restore_verified')
        m,_=journal.open_envelope(encrypted,key,expected=b,expected_encrypted_sha=digest(encrypted),policy=POLICY)
        self.assertEqual(m['facts']['tables']['operations.handoff_note_revisions']['rows'],3)
        self.assertFalse(Path(result['encryptedBackup']).with_name('archive.partial').exists())
        target=await self.target();got=await self.restore(target,encrypted,key,b)
        if self.restore_admin is not self.admin:
            self.assertNotEqual(target.system_identifier,m['sourceSystemIdentifier'])
            self.assertEqual(got['recoveryTopology'],'cross_cluster')
        else:self.assertEqual(got['recoveryTopology'],'same_cluster')
        receipts.validate(got,expected=b,encrypted_sha=digest(encrypted),archive_sha=m['archiveSha256'],
            facts_sha=digest(canonical(m['facts'])),verification_window=b['window'],expected_receipt_sha=digest(canonical(got)))
        self.assertFalse(got['credentialRecoveryVerified']);self.assertFalse(got['operationalReleaseApproved'])
        pool=await asyncpg.create_pool(target.url,min_size=1,max_size=1)
        try:
            async with pool.acquire() as c:
                raw,cost=await c.fetchrow('SELECT raw,cost::text FROM purchasing.test_source_bytes')
                self.assertEqual(raw,self.raw);self.assertEqual(cost,'0.000000000000000001')
                self.assertEqual(await c.fetchval("SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='operations' AND NOT t.tgisinternal"),6)
                with self.assertRaises(asyncpg.RaiseError):await c.execute('TRUNCATE operations.handoff_command_receipts')
                with self.assertRaises(asyncpg.ForeignKeyViolationError):
                    await c.execute("INSERT INTO operations.store_settings VALUES('not-a-store','UTC',1)")
            before=m['facts']
            replay=await handoff.execute(pool,'berts','usr_manager',handoff.Command(**self.value),self.key,0)
            self.assertTrue(replay['replayed']);self.assertEqual(replay['accepted']['revision'],1);self.assertEqual(replay['current']['revision'],3)
            async with pool.acquire() as c,readonly_snapshot(c):
                self.assertEqual(await journal.fingerprint(c,RECEIVING7),before)
        finally:await pool.close()

    async def test_frozen_six_schema_oracle_agrees_in_same_snapshot(self):
        async with self.pool.acquire() as c,readonly_snapshot(c):
            expected=await legacy.fingerprint(c)
            self.assertEqual(await journal.fingerprint(c,LEGACY6),expected)
            seven=await journal.fingerprint(c,RECEIVING7)
            self.assertEqual({k:v for k,v in seven['tables'].items() if not k.startswith('operations.')},expected['tables'])
            with self.assertRaises(asyncpg.ReadOnlySQLTransactionError):await c.execute("UPDATE public.stores SET name='TEST ONLY forbidden'")

    async def test_missing_operations_extra_schema_and_foreign_data_hold(self):
        async with self.pool.acquire() as c:
            await c.execute('CREATE SCHEMA test_unknown')
            with self.assertRaises(Held):await journal.check_scope(c,RECEIVING7)
            await c.execute('DROP SCHEMA test_unknown')
            await c.execute('ALTER SCHEMA operations RENAME TO held_operations')
            with self.assertRaises(Held):await journal.check_scope(c,RECEIVING7)
            await c.execute('ALTER SCHEMA held_operations RENAME TO operations')

    async def test_managed_helper_requires_independent_definition_binding_and_restores(self):
        async with self.pool.acquire() as c:
            await c.execute("CREATE SCHEMA auth;CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql AS $$SELECT null::uuid$$;")
            await c.execute('CREATE POLICY test_journal_auth ON operations.handoff_notes USING(auth.uid() IS NULL)')
            async with readonly_snapshot(c):
                await c.execute(journal.NORMALIZE)
                dep=await journal.dependencies(c,RECEIVING7)
        self.assertEqual([f['proname'] for f in dep['authFunctions']],['uid'])
        with self.assertRaises(Held):await self.export()
        policy=dict(extensions=[],authFunctions=[dict(proname='uid',definitionSha256=digest(dep['authFunctions'][0]['definition'].encode()))])
        result,encrypted,key,b=await self.export(policy)
        target=await self.target();got=await self.restore(target,encrypted,key,b,policy)
        self.assertEqual(got['status'],'verified_application_restore')
        # PR73's marker refusal remains intact even on our approved local stubbed target.
        import manager_handoff_recovery
        c=await asyncpg.connect(target.url)
        try:
            with self.assertRaises(manager_handoff_recovery.Held):await manager_handoff_recovery.refuse_managed(c)
        finally:await c.close()

    async def test_unclassified_external_dependency_and_changed_helper_hold(self):
        async with self.pool.acquire() as c:
            await c.execute('CREATE SCHEMA auth;CREATE TABLE auth.test_outside(id integer PRIMARY KEY);ALTER TABLE operations.store_settings ADD COLUMN test_external integer REFERENCES auth.test_outside(id)')
            async with readonly_snapshot(c):
                with self.assertRaises(Held):await journal.dependencies(c,RECEIVING7)

    async def test_nonempty_function_only_wrong_oid_and_role_targets_refuse(self):
        _,encrypted,key,b=await self.export();target=await self.target()
        from dataclasses import replace
        with self.assertRaises(Held):await self.restore(replace(target,database_oid=target.database_oid+1),encrypted,key,b)
        c=await asyncpg.connect(target.url)
        try:await c.execute('CREATE FUNCTION public.test_only() RETURNS integer LANGUAGE sql AS $$SELECT 1$$')
        finally:await c.close()
        with self.assertRaises(Held):await self.restore(target,encrypted,key,b)

    async def test_types_default_acls_and_extra_empty_schema_targets_refuse(self):
        _,encrypted,key,b=await self.export()
        for sql in ("CREATE TYPE public.test_only AS ENUM('TEST ONLY')",
                    'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO PUBLIC',
                    'CREATE SCHEMA test_only_empty'):
            target=await self.target();c=await asyncpg.connect(target.url)
            try:await c.execute(sql)
            finally:await c.close()
            with self.subTest(object=sql),self.assertRaises(Held):await self.restore(target,encrypted,key,b)

    async def test_nonlogin_role_acl_default_acl_and_rls_roundtrip(self):
        role='journal_reader_'+uuid4().hex[:10];self.roles.append(role)
        if self.restore_admin is not self.admin:
            await self.restore_admin.execute('CREATE ROLE '+role+' NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION')
            self.restore_roles.append(role)
        async with self.pool.acquire() as c:
            await c.execute('CREATE ROLE '+role+' NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION')
            await c.execute('GRANT USAGE ON SCHEMA operations TO '+role)
            await c.execute('GRANT SELECT ON operations.handoff_notes TO '+role)
            await c.execute('CREATE POLICY test_only_reader ON operations.handoff_notes FOR SELECT TO '+role+" USING(store_id='berts')")
            await c.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA operations GRANT SELECT ON TABLES TO '+role)
            await c.execute("CREATE TYPE operations.test_only_unit AS ENUM('TEST ONLY batch','TEST ONLY portion')")
            await c.execute('REVOKE ALL ON TYPE operations.test_only_unit FROM PUBLIC')
            await c.execute('GRANT USAGE ON TYPE operations.test_only_unit TO '+role)
        _,encrypted,key,b=await self.export();target=await self.target()
        self.assertEqual((await self.restore(target,encrypted,key,b))['status'],'verified_application_restore')
        c=await asyncpg.connect(target.url)
        try:
            async with c.transaction():
                await c.execute('SET LOCAL ROLE '+role)
                self.assertEqual(await c.fetchval('SELECT count(*) FROM operations.handoff_notes'),1)
                with self.assertRaises(asyncpg.InsufficientPrivilegeError):await c.execute('DELETE FROM operations.handoff_notes')
        finally:await c.close()

    async def test_reviewed_extension_version_roundtrip_and_changed_policy_refuses(self):
        async with self.pool.acquire() as c:
            await c.execute('CREATE SCHEMA extensions;CREATE EXTENSION pgcrypto WITH SCHEMA extensions')
            await c.execute('ALTER TABLE operations.store_settings ADD COLUMN test_nonce bytea DEFAULT extensions.gen_random_bytes(4)')
            async with readonly_snapshot(c):dep=await journal.dependencies(c,RECEIVING7)
        self.assertEqual([e['extname'] for e in dep['extensions']],['pgcrypto'])
        policy=dict(extensions=dep['extensions'],authFunctions=[])
        _,encrypted,key,b=await self.export(policy)
        self.assertEqual((await self.restore(await self.target(),encrypted,key,b,policy))['status'],'verified_application_restore')
        wrong=deepcopy(policy);wrong['extensions'][0]['extversion']='0.0-TEST-ONLY'
        with self.assertRaises(Held):await self.export(wrong)

    async def test_missing_and_login_enabled_recovery_roles_refuse_before_bootstrap(self):
        role='journal_gate_'+uuid4().hex[:10]
        async with self.pool.acquire() as c:
            await c.execute('CREATE ROLE '+role+' NOLOGIN')
            await c.execute('GRANT SELECT ON public.stores TO '+role)
        self.roles.append(role)
        _,encrypted,key,b=await self.export()
        async with self.pool.acquire() as c:
            await c.execute('REVOKE SELECT ON public.stores FROM '+role)
            await c.execute('DROP ROLE '+role)
        self.roles.remove(role)
        target=await self.target()
        with self.assertRaisesRegex(Held,'preprovisioned_role_missing'):await self.restore(target,encrypted,key,b)
        # Source role passwords/LOGIN authority are never copied to make restore pass.
        await self.restore_admin.execute('CREATE ROLE '+role+' LOGIN')
        (self.restore_roles if self.restore_admin is not self.admin else self.roles).append(role)
        with self.assertRaisesRegex(Held,'recovery_role_not_inert'):await self.restore(target,encrypted,key,b)

    async def test_sequence_and_global_role_changes_hold_including_fresh_postsnapshot_read(self):
        real_tool=legacy.tool
        for change in ('sequence','global_role'):
            role='journal_drift_'+uuid4().hex[:10]
            async def drift(executable,args,settings=None,remote=False):
                result=await real_tool(executable,args,settings,False)
                if '--format=custom' in args:
                    async with self.pool.acquire() as c:
                        if change=='sequence':await c.fetchval("SELECT nextval('purchasing.test_source_bytes_id_seq')")
                        else:
                            await c.execute('CREATE ROLE '+role+' NOLOGIN');self.roles.append(role)
                return result
            with self.subTest(change=change),self.assertRaises(Held):await self.export(tool=drift)
        self.assertFalse(list(self.root.rglob('backup.jmax.enc')))

    async def test_overall_timeout_closes_only_owned_source_session(self):
        async def wait(conn,*args,**kwargs):
            await conn.fetchval('SELECT pg_sleep(10)')
        with patch.object(journal,'capture',wait),self.assertRaises(TimeoutError):await self.export(timeout=.25)
        self.assertTrue(self.opened_pids)
        self.assertEqual(await self.admin.fetchval('SELECT count(*) FROM pg_stat_activity WHERE pid=ANY($1::integer[])',self.opened_pids),0)
        self.assertFalse(list(self.root.rglob('backup.jmax.enc')))

    async def test_failed_and_cancelled_dump_close_source_and_have_no_final_file(self):
        original=legacy.tool
        for cancel in (False,True):
            async def fail(executable,args,*rest):
                if '--format=custom' in args:
                    Path(next(a.split('=',1)[1] for a in args if a.startswith('--file='))).write_bytes(b'PGDMP TEST ONLY partial')
                    if cancel:raise asyncio.CancelledError()
                    raise Held('test_only_tool_failure')
                return await original(executable,args,*rest)
            with self.subTest(cancel=cancel),self.assertRaises(asyncio.CancelledError if cancel else Held):await self.export(tool=fail)
        self.assertFalse(list(self.root.rglob('backup.jmax.enc')))
        self.assertFalse(list(self.root.rglob('archive.partial')))
        self.assertIsNone(legacy.EXPORT_CONTROL.get())
