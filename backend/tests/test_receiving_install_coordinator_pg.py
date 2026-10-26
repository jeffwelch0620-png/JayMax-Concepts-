"""Real six -> seven transition on two independent fictional PostgreSQL clusters.

Only the existing backup routing/filesystem seams are mocked. SQL, snapshots,
dump/encryption/restore, restricted LOGINs, coordinator guards and replay are real.
"""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit
from uuid import uuid4

import asyncpg
import pytest
import hosted_backup as legacy
import hosted_journal_backup as journal
import journal_backup_receipts as receipts
import manager_handoff as handoff
import manager_handoff_install as install
import receiving_install_coordinator as coordinator
from application_backup_profiles import Held,canonical,digest
from test_manager_handoff import body
import test_manager_handoff_install as install_fixture
from test_receiving_install_evidence import window,matrix,expectation,closed_key,migration_hashes
from test_journal_backup_receipts import binding,packet,POLICY
from test_hosted_journal_backup import PROJECT,URL


@pytest.fixture(autouse=True)
def phase_report(request):
    yield
    metrics=getattr(request.instance,'metrics',None)
    if metrics is not None:
        request.node.user_properties.append(('receiving_local_metrics',json.dumps(metrics,sort_keys=True)))


def memory_sample():
    if os.name=='nt':
        import ctypes
        class M(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in
                ('total','free','totalPage','freePage','totalVirtual','freeVirtual','extra')]
        m=M();m.length=ctypes.sizeof(m)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):raise RuntimeError('Memory reading failed')
        free,total=m.free,m.total
    else:
        values={k:int(v.split()[0])*1024 for k,v in (s.split(':',1) for s in Path('/proc/meminfo').read_text().splitlines())}
        free,total=values['MemAvailable'],values['MemTotal']
    return dict(availableMiB=round(free/1024**2),availablePercent=round(100*free/total,2))


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN') and os.getenv('NATIVE_RECEIVING_RESTORE_TEST_DSN'),
                     'Two explicit independent fictional controls required')
class TransitionDatabaseTests(unittest.IsolatedAsyncioTestCase):
    role_url=install_fixture.InstallDatabaseTests.role_url

    async def asyncSetUp(self):
        other=os.environ['NATIVE_RECEIVING_RESTORE_TEST_DSN'];u=urlsplit(other)
        if (u.scheme not in ('postgres','postgresql') or u.hostname not in ('127.0.0.1','::1')
                or u.port is None or u.port<1024 or u.path!='/native_purchase_test_control'
                or u.username!='purchase_implementation_test' or u.query or u.fragment):
            raise Held('independent_fictional_control_required')
        started=time.monotonic()
        await install_fixture.InstallDatabaseTests.asyncSetUp(self)
        # CI defaults to UTC; force the session boundary exposed locally. Only
        # this owned fictional database is affected; accepted engines are intact.
        await self.admin.execute('ALTER DATABASE '+journal.native.quoted(self.db)+" SET timezone='America/New_York'")
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name);self.restore_dsn=other;self.restore_targets=[];self.restore_roles=[]
        self.restore_admin=await asyncpg.connect(other)
        self.dump=Path(os.environ['NATIVE_BACKUP_PG_DUMP']);self.restore_bin=self.dump.with_name('pg_restore'+self.dump.suffix)
        self.metrics={'memoryAtFixtureStart':memory_sample()};self.chain_started=started
        self.settings=journal.native.disposable_connection(self.url)
        async with self.pool.acquire() as c:
            source_system=await c.fetchval('SELECT system_identifier::text FROM pg_control_system()')
            restore_system=await self.restore_admin.fetchval('SELECT system_identifier::text FROM pg_control_system()')
            self.assertNotEqual(source_system,restore_system)
            self.source={k:self.settings[k] for k in ('host','port','user','database')}
            self.source.update(systemIdentifier=source_system,
                databaseOid=await c.fetchval('SELECT oid::bigint FROM pg_database WHERE datname=current_database()'))
            await c.execute('''CREATE TABLE purchasing.test_only_original_bytes(id integer GENERATED ALWAYS AS IDENTITY,raw bytea,cost numeric(38,18));
                CREATE TABLE actual_inventory.test_only_count_baseline(item text PRIMARY KEY,quantity numeric,explicit_value numeric);
                INSERT INTO actual_inventory.test_only_count_baseline VALUES('TEST ONLY purchased item',10,145.125);''')
            self.raw=b'TEST ONLY original vendor,unmapped\x00\xff\r\n'
            await c.execute('INSERT INTO purchasing.test_only_original_bytes(raw,cost) VALUES($1,0.000000000000000001)',self.raw)
        self.key=uuid4();self.value=body()
        self.metrics['fixtureSetupSeconds']=round(time.monotonic()-started,6)

    async def asyncTearDown(self):
        started=time.monotonic()
        try:
            for db in reversed(self.restore_targets):await self.restore_admin.execute('DROP DATABASE '+journal.native.quoted(db))
            for role in reversed(self.restore_roles):await self.restore_admin.execute('DROP ROLE '+journal.native.quoted(role))
        finally:
            await self.restore_admin.close()
            await install_fixture.InstallDatabaseTests.asyncTearDown(self)
            self.folder.cleanup()
        self.metrics['databaseCloseoutSeconds']=round(time.monotonic()-started,6)
        self.metrics['completeChainAndDatabaseCloseoutSeconds']=round(time.monotonic()-self.chain_started,6)
        self.metrics['memoryAfterFixtureCloseout']=memory_sample()
        # Minimized counts/timings only, never URLs, keys, paths or source rows.
        print('RECEIVING_LOCAL_TIMING '+json.dumps(dict(method=self._testMethodName,
            twoIndependentClusters=True,custodyIsFictionalModel=True,metrics=self.metrics),sort_keys=True))

    @asynccontextmanager
    async def phase(self,name):
        start=time.monotonic()
        try:yield
        finally:self.metrics[name]=round(time.monotonic()-start,6)

    def private_directory(self,path,area):
        p=Path(path);p.mkdir(parents=True,exist_ok=False);return p

    def route(self):
        real_tool=legacy.tool
        async def connect(*args,**kwargs):
            return await asyncpg.connect(self.url,server_settings={'default_transaction_read_only':'on',
                'application_name':kwargs.get('label','receiving-fictional-capture')})
        async def tool(executable,args,settings=None,remote=False):
            if settings is not None:self.assertEqual(settings,self.settings)
            return await real_tool(executable,args,settings,False)
        return connect,tool

    async def pre_proof(self):
        connect,tool=self.route();w=window();label=uuid4().hex
        with patch.object(journal.maintenance,'dump_settings',AsyncMock(return_value=self.settings)),\
             patch.object(journal.maintenance,'connect',connect),\
             patch.object(legacy,'private_directory',self.private_directory),patch.object(legacy,'tool',tool):
            async with self.phase('legacyExportSeconds'):
                result=await legacy.export_backup(URL,PROJECT,self.dump,self.restore_bin,self.root/label/'archive',
                    self.root/label/'key',migration_hashes(),maintenance_direct_ipv6=True)
        a=Path(result['encryptedBackup']);k=Path(result['privateKey']);m,_=legacy.open_backup(a,k,PROJECT)
        db='native_purchase_test_backup_'+uuid4().hex
        await self.admin.execute('CREATE DATABASE '+db);self.restores.append(db)
        dsn=self.url.rsplit('/',1)[0]+'/'+db
        with patch.object(legacy,'private_directory',self.private_directory):
            async with self.phase('legacyRestoreSeconds'):
                restored=await legacy.verify_restore(dsn,a,k,PROJECT,self.restore_bin,self.root/uuid4().hex)
        e=expectation(m,a.read_bytes(),restored,'pre_install',self.source,capture=w)
        return a,k,restored,e

    async def prepared(self,proof):
        a,k,r,e=proof
        async with self.phase('planPrepareSeconds'):
            return await coordinator.prepare(self.url,self.runtime,self.accounts,self.versions,a,k,r,
                expected=e,expected_sha=digest(canonical(e)),consumers=matrix())

    async def applied(self,p,proof):
        a,k,r,_=proof
        async with self.phase('preKeyCustodyModelSeconds'):
            separate=self.root/('TEST_ONLY_modeled_separate_key_'+uuid4().hex)
            separate.write_bytes(k.read_bytes());self.assertEqual(separate.read_bytes(),k.read_bytes());k.unlink()
        async with self.phase('applicationAndGuardsSeconds'):
            return await coordinator.apply(self.url,p,digest(canonical(p)),a,k,r,custody_closeout=closed_key())

    async def post_proof(self):
        connect,tool=self.route();b=binding();b['window']=window();label=uuid4().hex;raw=packet(b)
        with patch.object(journal.maintenance,'dump_settings',AsyncMock(return_value=self.settings)),\
             patch.object(journal.maintenance,'connect',connect),\
             patch.object(legacy,'private_directory',self.private_directory),patch.object(legacy,'tool',tool):
            async with self.phase('journalExportSeconds'):
                result=await journal.export_backup(URL,PROJECT,self.dump,self.restore_bin,
                    self.root/label/'archive',self.root/label/'key',migration_hashes(),execution_packet=raw,packet_sha=digest(raw))
        a=Path(result['encryptedBackup']);k=Path(result['privateKey'])
        m,_=journal.open_envelope(a.read_bytes(),k.read_bytes(),expected=b,expected_encrypted_sha=result['encryptedSha256'],policy=POLICY)
        async with self.phase('independentRestorePreparationSeconds'):
            for role in m['authority']['requiredRoles']:
                if not await self.restore_admin.fetchval('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=$1)',role):
                    await self.restore_admin.execute('CREATE ROLE '+journal.native.quoted(role)+' NOLOGIN NOSUPERUSER NOINHERIT NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION')
                    self.restore_roles.append(role)
            db='native_purchase_test_backup_'+uuid4().hex
            await self.restore_admin.execute('CREATE DATABASE '+db);self.restore_targets.append(db)
            oid=await self.restore_admin.fetchval('SELECT oid::bigint FROM pg_database WHERE datname=$1',db)
            system=await self.restore_admin.fetchval('SELECT system_identifier::text FROM pg_control_system()')
            target=journal.RestoreTarget(self.restore_dsn.rsplit('/',1)[0]+'/'+db,self.restore_dsn,system,oid)
        with patch.object(legacy,'private_directory',self.private_directory):
            async with self.phase('journalRestoreSeconds'):
                r=await journal.verify_restore(target,a.read_bytes(),k.read_bytes(),self.restore_bin,self.root/uuid4().hex,
                    expected=b,expected_encrypted_sha=result['encryptedSha256'],policy=POLICY,execution_window=b['window'])
        e=expectation(m,a.read_bytes(),r,'post_install',self.source,capture=b['window'])
        return a,k,r,e,target

    async def test_complete_six_to_seven_chain_and_post_failure_keeps_installation(self):
        proof=await self.pre_proof();p=await self.prepared(proof);installed=await self.applied(p,proof)
        self.assertEqual(installed['status'],'installed_activation_held')
        async with self.phase('fictionalLoginAndHistorySeconds'):
            self.assertTrue((await install.qualify(self.role_url(self.runtime),self.role_url(self.accounts)))['actualAccountsLogin'])
            pool=await asyncpg.create_pool(self.role_url(self.runtime),min_size=1,max_size=1)
            try:
                await handoff.execute(pool,'berts','usr_owner',handoff.Command(**self.value),self.key,0)
                for rev,change in ((1,dict(action='submit')),(2,dict(action='correct',summary='TEST ONLY confirmed',correction_reason='TEST ONLY measured'))):
                    await handoff.execute(pool,'berts','usr_owner',handoff.Command(**(self.value|change)),uuid4(),rev)
            finally:await pool.close()
        a,k,r,e,target=await self.post_proof()
        # A missing/swapped post artifact must hold without dropping or reapplying.
        good=a.read_bytes();a.write_bytes(b'TEST ONLY unavailable post proof')
        failed=await coordinator.finish(self.url,p,digest(canonical(p)),installed,digest(canonical(installed)),a,k,r,expected=e,expected_sha=digest(canonical(e)))
        self.assertEqual(failed['status'],'installed_recovery_held');a.write_bytes(good)
        self.assertEqual((await coordinator.reconcile(self.url,p,digest(canonical(p))))['outcome'],'installed')
        async with self.phase('transitionFinishSeconds'):
            result=await coordinator.finish(self.url,p,digest(canonical(p)),installed,digest(canonical(installed)),a,k,r,expected=e,expected_sha=digest(canonical(e)))
        self.assertEqual(result['status'],'verified_local_recovery_custody_closeout_pending',result)
        async with self.phase('postKeyCustodyModelSeconds'):
            separate=self.root/('TEST_ONLY_modeled_separate_key_'+uuid4().hex)
            separate.write_bytes(k.read_bytes());self.assertEqual(separate.read_bytes(),k.read_bytes());k.unlink()
            result=coordinator.closeout(result,digest(canonical(result)),k,closed_key())
        self.assertEqual(result['status'],'passed_local_transition_activation_held',result)
        self.assertFalse(result['featureActivated']);self.assertFalse(result['credentialRecoveryVerified'])
        pool=await asyncpg.create_pool(target.url,min_size=1,max_size=1)
        try:
            replay=await handoff.execute(pool,'berts','usr_owner',handoff.Command(**self.value),self.key,0)
            self.assertTrue(replay['replayed']);self.assertEqual(replay['accepted']['revision'],1);self.assertEqual(replay['current']['revision'],3)
            async with pool.acquire() as c:
                raw,cost=await c.fetchrow('SELECT raw,cost::text FROM purchasing.test_only_original_bytes')
                self.assertEqual(raw,self.raw);self.assertEqual(cost,'0.000000000000000001')
                self.assertEqual(await c.fetchval('SELECT explicit_value::text FROM actual_inventory.test_only_count_baseline'),'145.125')
                self.assertEqual(await c.fetchval('SELECT count(*) FROM operations.handoff_note_revisions'),3)
        finally:await pool.close()

    async def test_changed_baseline_refuses_before_install_without_repair(self):
        proof=await self.pre_proof();p=await self.prepared(proof)
        async with self.pool.acquire() as c:await c.execute('UPDATE actual_inventory.test_only_count_baseline SET quantity=11')
        r=await self.applied(p,proof);self.assertEqual(r['status'],'installation_failed_activation_held')
        async with self.pool.acquire() as c:
            self.assertIsNone(await c.fetchval("SELECT to_regnamespace('operations')"))
            self.assertEqual(await c.fetchval('SELECT quantity FROM actual_inventory.test_only_count_baseline'),11)

    async def test_lost_commit_ack_reconciles_readonly_and_never_retries(self):
        proof=await self.pre_proof();p=await self.prepared(proof)
        async def lost(tx):await tx.commit();raise ConnectionResetError('TEST ONLY lost ack')
        with patch.object(install,'_commit',side_effect=lost) as commit:
            result=await self.applied(p,proof)
        self.assertEqual(result['status'],'commit_unknown_activation_held');self.assertFalse(result['retryAuthorized'])
        self.assertEqual(commit.await_count,1)
        self.assertEqual((await coordinator.reconcile(self.url,p,digest(canonical(p))))['outcome'],'installed')
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT count(*) FROM supabase_migrations.schema_migrations'),4)

    async def test_managed_markers_still_refuse_at_coordinator_boundary(self):
        proof=await self.pre_proof();p=await self.prepared(proof)
        async with self.pool.acquire() as c:await c.execute('CREATE SCHEMA auth')
        result=await self.applied(p,proof);self.assertEqual(result['status'],'installation_failed_activation_held')
        async with self.pool.acquire() as c:self.assertIsNone(await c.fetchval("SELECT to_regnamespace('operations')"))

    async def test_wrong_cluster_identity_refuses_preparation(self):
        proof=await self.pre_proof();a,k,r,e=proof;e['source']['systemIdentifier']='9999999'
        with self.assertRaises(Held):await self.prepared((a,k,r,e))
