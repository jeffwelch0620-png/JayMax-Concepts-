"""N3 collector integration: fictional data in a fresh loopback test database."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import asyncpg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/ops'))
import s1_observation as s1


def local_control(dsn):
    """Reject application/hosted targets before creating any connection."""
    try:
        uri = urlsplit(dsn)
        allowed = (uri.scheme in ('postgres', 'postgresql')
            and uri.hostname in ('127.0.0.1', 'localhost', '::1')
            and uri.username == 'purchase_implementation_test'
            and uri.path == '/native_purchase_test_control'
            and uri.port is not None and not uri.query and not uri.fragment)
    except (TypeError, ValueError):
        allowed = False
    if not allowed:
        raise ValueError('Dedicated loopback disposable control database required')
    return uri


def activity_ddl():
    # Use exactly the checked-in definition, not a handwritten approximation.
    matches = re.findall(r'CREATE TABLE public\.activity_log \([\s\S]+?\n\);',
        (ROOT / 'supabase/schema.sql').read_text(encoding='utf-8'))
    if len(matches) != 1:
        raise ValueError('One reference activity table definition required')
    return matches[0]


class FixtureIdentityConnection:
    """Test only: translate the verified disposable identity, never other reads.

    Production requires postgres/postgres/postgres. CI deliberately uses a
    different role and a newly generated database. First execute the real identity
    query and assert the fixture context plus readonly=on, then translate only its
    returned identity fields. No SQL is rewritten and no runtime bypass is added.
    """
    def __init__(self, conn, database):
        self.conn, self.database = conn, database
        self.identity_checks = 0

    def __getattr__(self, name):
        return getattr(self.conn, name)

    async def fetchrow(self, sql, *args):
        row = await self.conn.fetchrow(sql, *args)
        if sql.startswith('SELECT current_user AS actor,session_user AS login,'):
            if dict(row) != {'actor':'purchase_implementation_test',
                    'login':'purchase_implementation_test', 'db':self.database, 'readonly':'on'}:
                raise AssertionError('Real disposable read-only identity required')
            self.identity_checks += 1
            return {'actor':'postgres','login':'postgres','db':'postgres','readonly':'on'}
        return row


class CollectorFixtureSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_disposable_targets_refuse_without_any_connection(self):
        for dsn in ('postgresql://purchase_implementation_test@remote.invalid:5432/native_purchase_test_control',
                'postgresql://postgres@127.0.0.1:5432/postgres',
                'postgresql://purchase_implementation_test@127.0.0.1:5432/ordinary',
                'postgresql://other@127.0.0.1:5432/native_purchase_test_control',
                'postgresql://purchase_implementation_test@127.0.0.1/native_purchase_test_control',
                'postgresql://purchase_implementation_test@127.0.0.1:5432/native_purchase_test_control?host=remote.invalid',
                'postgresql://purchase_implementation_test@127.0.0.1:5432/native_purchase_test_control#fragment',
                'postgresql://purchase_implementation_test@127.0.0.1:bad/native_purchase_test_control', None):
            with self.subTest(dsn=dsn), self.assertRaises(ValueError):
                local_control(dsn)
        for host in ('127.0.0.1', 'localhost', '[::1]'):
            self.assertEqual(local_control('postgresql://purchase_implementation_test:TEST_ONLY@'
                +host+':5432/native_purchase_test_control').username,'purchase_implementation_test')

    async def test_identity_adapter_checks_actual_identity_before_test_translation(self):
        expected={'actor':'purchase_implementation_test','login':'purchase_implementation_test',
                  'db':'native_purchase_test_s1_fictional','readonly':'on'}
        sql='SELECT current_user AS actor,session_user AS login,current_database() AS db,current_setting(\'transaction_read_only\') AS readonly'
        for key,value in (('actor','other'),('login','other'),('db','postgres'),('readonly','off')):
            with self.subTest(key=key):
                conn=AsyncMock();conn.fetchrow.return_value={**expected,key:value}
                adapter=FixtureIdentityConnection(conn,expected['db'])
                with self.assertRaises(AssertionError): await adapter.fetchrow(sql)
                conn.fetchrow.assert_awaited_once_with(sql)
                self.assertEqual(adapter.identity_checks,0)
        conn=AsyncMock();conn.fetchrow.return_value=expected
        adapter=FixtureIdentityConnection(conn,expected['db'])
        self.assertEqual((await adapter.fetchrow(sql))['actor'],'postgres')
        conn.fetchrow.return_value={'version':'TEST_ONLY','name':'fixture'}
        self.assertEqual(await adapter.fetchrow('SELECT version,name'),conn.fetchrow.return_value)
        self.assertEqual(adapter.identity_checks,1)


@unittest.skipUnless(os.environ.get('NATIVE_PURCHASE_TEST_DSN'), 'Dedicated disposable PostgreSQL required')
class S1CollectorDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        control=local_control(os.environ['NATIVE_PURCHASE_TEST_DSN'])
        self.database='native_purchase_test_s1_'+uuid4().hex
        self.admin=await asyncpg.connect(control.geturl(),ssl=False,timeout=10,command_timeout=10,
            server_settings={'application_name':'TEST_ONLY_S1_CONTROL'})
        self.addAsyncCleanup(self.admin.close,timeout=4)
        await self.admin.execute('CREATE DATABASE '+self.database+' TEMPLATE template0')
        self.addAsyncCleanup(self.drop_database)
        self.dsn=control._replace(path='/'+self.database).geturl()
        self.setup=await asyncpg.connect(self.dsn,ssl=False,timeout=10,command_timeout=10,
            server_settings={'application_name':'TEST_ONLY_S1_FIXTURE'})
        self.addAsyncCleanup(self.setup.close,timeout=4)
        self.owned=[]
        self.addAsyncCleanup(self.close_remaining_owned)
        await self.setup.execute(activity_ddl())
        await self.setup.execute('''CREATE TABLE public.staff_pins(store_id text NOT NULL,pin text NOT NULL);
            INSERT INTO public.staff_pins VALUES('berts','12345678'),('rudds','87654321'),('papa','TEST_ONLY_X');
            CREATE SCHEMA cron;
            CREATE TABLE cron.job(jobid bigint,active boolean,schedule text);
            INSERT INTO cron.job VALUES(3,true,'0 0 * * *'),(4,true,'0 0 * * *');
            CREATE SCHEMA supabase_migrations;
            CREATE TABLE supabase_migrations.schema_migrations(version text,name text);
            INSERT INTO supabase_migrations.schema_migrations VALUES
                ('TEST_ONLY_001','fixture_one'),('TEST_ONLY_002','fixture_two');''')
        for name in s1.OBJECTS:
            if name in ('public.activity_log','public.staff_pins'): continue
            schema,table=name.split('.')
            self.assertRegex(schema,r'^[a-z_]+$');self.assertRegex(table,r'^[a-z_]+$')
            await self.setup.execute('CREATE SCHEMA IF NOT EXISTS '+schema)
            await self.setup.execute('CREATE TABLE '+name+'(test_only integer)')
        await self.setup.execute('''ALTER TABLE public.items ENABLE ROW LEVEL SECURITY;
            CREATE POLICY test_only_read ON public.items FOR SELECT USING(true)''')
        self.start=datetime(2026,10,1,tzinfo=timezone.utc)
        self.end=self.start+timedelta(days=11)
        self.rows=[(UUID(int=i+1),'berts','fixture@example.invalid',
            'owner' if i%2 else 'manager','GET' if i%3 else 'POST',
            '/TEST_ONLY_PRIVATE_PATH/'+str(i),200 if i%5 else 403,
            self.start+timedelta(hours=i),'TEST_ONLY_USER_'+str(i%3)) for i in range(250)]
        extras=[(uuid4(),'berts','fixture@example.invalid',role,'GET','/TEST_ONLY_EXCLUDED',200,at,'TEST_ONLY_EXCLUDED')
            for role,at in (('owner',self.start-timedelta(seconds=1)),('manager',self.end),('staff',self.start))]
        await self.setup.executemany('''INSERT INTO public.activity_log
            (id,store_id,user_email,role,method,path,status,created_at,user_id)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)''',self.rows+extras)

    async def drop_database(self):
        await self.admin.execute('DROP DATABASE '+self.database)

    async def close_remaining_owned(self):
        for conn,_,_ in self.owned:
            if not conn.is_closed():
                try: await conn.close(timeout=4)
                finally:
                    if not conn.is_closed(): conn.terminate()

    async def connector(self, phase, *, readonly, timeout, command_timeout, adapt=True):
        self.assertTrue(readonly);self.assertIn(phase,s1.PHASES)
        self.assertEqual((timeout,command_timeout),(10,s1.COMMAND_TIMEOUT_SECONDS))
        conn=await asyncpg.connect(self.dsn,ssl=False,timeout=timeout,command_timeout=command_timeout,
            server_settings={'default_transaction_read_only':'on','application_name':'TEST_ONLY_S1_COLLECTOR'})
        adapter=FixtureIdentityConnection(conn,self.database)
        self.owned.append((conn,adapter,await conn.fetchval('SELECT pg_backend_pid()')))
        self.assertEqual(await conn.fetchval('SHOW default_transaction_read_only'),'on')
        return adapter if adapt else conn

    async def assert_owned_closed(self,count):
        self.assertEqual(len(self.owned),count)
        self.assertTrue(all(conn.is_closed() for conn,_,_ in self.owned))
        for _ in range(20):
            active=await self.setup.fetchval('SELECT count(*) FROM pg_stat_activity WHERE pid=ANY($1::int[])',
                [pid for _,_,pid in self.owned])
            if active==0: break
            await asyncio.sleep(.05)
        self.assertEqual(active,0)

    async def snapshot(self):
        return [await self.setup.fetch('SELECT * FROM '+name+' ORDER BY 1') for name in
            ('public.activity_log','public.staff_pins','cron.job','supabase_migrations.schema_migrations')]

    async def test_complete_collector_reads_real_metadata_ledger_and_audit_without_writes(self):
        self.assertEqual({row['column_name']:row['is_nullable'] for row in await self.setup.fetch(
            "SELECT column_name,is_nullable FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='staff_pins'")},
            {'store_id':'NO','pin':'NO'})
        before=await self.snapshot()
        with TemporaryDirectory() as directory:
            path=Path(directory)/'TEST_ONLY.ndjson'
            with path.open('xb') as stream:
                diagnostics=s1.Diagnostics(s1.JsonlCheckpoints(stream))
                result=await s1.collect(self.connector,diagnostics,audit_from=self.start,as_of=self.end,remaining_seconds=120)
            raw=path.read_bytes();lines=raw.splitlines(keepends=True)
            saved={row['operation']:row['data'] for row in map(json.loads,lines)}
        self.assertEqual(result['status'],'complete')
        self.assertEqual(result['auditTotal'],250)
        self.assertTrue(result['recordsTruncated']);self.assertFalse(result['breakdownTruncated'])
        self.assertIs(result['coverageComplete'],True)  # Exact aggregate coverage; bounded sample is informational.
        self.assertFalse(result['envelopeExpired'])
        self.assertEqual(len(saved),11)
        self.assertEqual(result['completedObservations'],list(saved))
        self.assertEqual(len(saved['metadata.relations']),14)
        self.assertEqual(saved['metadata.ledger'],{'rows':[
            {'version':'TEST_ONLY_002','name':'fixture_two'},{'version':'TEST_ONLY_001','name':'fixture_one'}],
            'truncated':False,'total':2,'max_version':'TEST_ONLY_002'})
        for key in ('ledgerTruncated','sessionsTruncated','sessionGroupsTruncated','policiesTruncated'):
            self.assertFalse(result[key])
        self.assertTrue(all(json.loads(line)['format']=='jaymax-s1-checkpoint-v3' for line in lines))
        self.assertEqual(result['format'],'jaymax-s1-diagnostics-v3')
        self.assertEqual(saved['metadata.pin_configuration'],[
            {'store_id':'berts','configured':True},{'store_id':'papa','configured':False},
            {'store_id':'rudds','configured':True}])
        self.assertEqual([row['jobid'] for row in saved['metadata.toast_jobs']],[3,4])
        self.assertEqual(len(saved['metadata.policies']['rows']),1)
        self.assertTrue(any(row['application_name'] for row in saved['metadata.sessions']['rows']))
        self.assertEqual(saved['audit.summary'],{'total':250,
            'first_at':self.start.isoformat(),'last_at':self.rows[-1][7].isoformat()})
        self.assertEqual(sum(row['n'] for row in saved['audit.breakdown']['groups']),250)
        self.assertGreater(len(saved['audit.breakdown']['groups']),3)
        for side,expected in (('earliest',self.rows[:100]),('latest',self.rows[-100:])):
            sample=saved['audit.records'][side]
            self.assertEqual(len(sample),100)
            self.assertEqual([r['created_at'] for r in sample],[r[7].isoformat() for r in expected])
            self.assertEqual([r['path'] for r in sample],[r[5] for r in expected])
            self.assertTrue(all('user_email' not in r for r in sample))
        self.assertLessEqual(max(map(len,lines)),128*1024);self.assertLessEqual(len(raw),512*1024)
        public=json.dumps(result)
        for value in ('TEST_ONLY','PRIVATE_PATH','fixture@example.invalid','12345678','87654321'):
            self.assertNotIn(value,public)
        self.assertEqual([adapter.identity_checks for _,adapter,_ in self.owned],[1,1])
        self.assertEqual(result['ownedClientsClosed'],{'metadata':True,'audit':True})
        await self.assert_owned_closed(2)
        self.assertEqual(await self.snapshot(),before)

    async def test_real_disposable_identity_without_adapter_is_refused_and_closed(self):
        async def connect(phase,**kwargs): return await self.connector(phase,adapt=False,**kwargs)
        diagnostics=s1.Diagnostics(lambda *_:None)
        with self.assertRaises(s1.ObservationHeld):
            await s1.collect(connect,diagnostics,audit_from=self.start,as_of=self.end,remaining_seconds=120)
        self.assertEqual(diagnostics.receipt()['failedOperation'],'metadata.identity')
        self.assertIsNone(diagnostics.receipt()['auditTotal'])
        self.assertEqual(diagnostics.completed,[])
        await self.assert_owned_closed(1)

    async def test_real_ledger_shape_failure_preserves_prefix_and_skips_audit(self):
        # Deliberately break only this newly created fixture, never a shared schema.
        await self.setup.execute('ALTER TABLE supabase_migrations.schema_migrations DROP COLUMN name')
        with TemporaryDirectory() as directory:
            path=Path(directory)/'TEST_ONLY.ndjson'
            with path.open('xb') as stream:
                diagnostics=s1.Diagnostics(s1.JsonlCheckpoints(stream))
                with self.assertRaises(asyncpg.UndefinedColumnError):
                    await s1.collect(self.connector,diagnostics,audit_from=self.start,as_of=self.end,remaining_seconds=120)
            saved=[json.loads(line)['operation'] for line in path.read_bytes().splitlines()]
        receipt=diagnostics.receipt()
        self.assertEqual(receipt['failedOperation'],'metadata.ledger')
        self.assertEqual(receipt['error']['sqlState'],'42703')
        self.assertEqual(saved,diagnostics.completed)
        self.assertEqual(saved[-1],'metadata.sessions')
        self.assertIsNone(receipt['auditTotal']);self.assertNotIn('audit',receipt['ownedClientsClosed'])
        self.assertNotIn('TEST_ONLY',json.dumps(receipt))
        await self.assert_owned_closed(1)

    async def test_seventy_ledger_rows_report_full_aggregate_and_keep_newest_sixty_four(self):
        await self.reduce_audit_to_one_hundred()
        await self.setup.execute('TRUNCATE supabase_migrations.schema_migrations')
        await self.setup.executemany('INSERT INTO supabase_migrations.schema_migrations VALUES($1,$2)',
            [('TEST_ONLY_'+str(i).zfill(3),'fixture_'+str(i)) for i in range(1,71)])
        before=await self.snapshot()
        with TemporaryDirectory() as directory:
            path=Path(directory)/'TEST_ONLY.ndjson'
            with path.open('xb') as stream:
                diagnostics=s1.Diagnostics(s1.JsonlCheckpoints(stream))
                result=await s1.collect(self.connector,diagnostics,audit_from=self.start,as_of=self.end,remaining_seconds=120)
            raw=path.read_bytes();lines=raw.splitlines(keepends=True)
            saved={row['operation']:row['data'] for row in map(json.loads,lines)}
        self.assertTrue(result['ledgerTruncated'])
        self.assertEqual(result['auditTotal'],100)
        self.assertFalse(result['recordsTruncated'])
        self.assertFalse(result['breakdownTruncated'])
        for key in ('sessionsTruncated','sessionGroupsTruncated','policiesTruncated'):
            self.assertFalse(result[key])
        self.assertIs(result['coverageComplete'],False)  # Ledger alone makes visibility incomplete.
        ledger=saved['metadata.ledger']
        self.assertEqual((ledger['total'],ledger['max_version']),(70,'TEST_ONLY_070'))
        self.assertEqual([row['version'] for row in ledger['rows']],
            ['TEST_ONLY_'+str(i).zfill(3) for i in range(70,6,-1)])
        self.assertEqual(len(ledger['rows']),64)
        self.assertEqual(result['status'],'complete')  # Execution, not complete metadata visibility.
        self.assertLessEqual(max(map(len,lines)),128*1024);self.assertLessEqual(len(raw),512*1024)
        self.assertNotIn('TEST_ONLY',json.dumps(result))
        self.assertEqual(await self.snapshot(),before)
        await self.assert_owned_closed(2)

    async def reduce_audit_to_one_hundred(self):
        await self.setup.execute('DELETE FROM public.activity_log WHERE created_at >= $1 '
            'AND created_at < $2 AND role=ANY($3::text[])',
            self.start+timedelta(hours=100),self.end,['owner','manager'])

    async def test_untruncated_coverage_and_newest_session_groups_use_one_observation(self):
        await self.reduce_audit_to_one_hundred()
        extras=[]
        try:
            for i in range(3):
                conn=await asyncpg.connect(self.dsn,ssl=False,timeout=10,command_timeout=10,
                    server_settings={'application_name':'TEST_ONLY_S1_EXTRA_'+str(i)})
                extras.append(conn)
                self.addAsyncCleanup(conn.close,timeout=4)
                await conn.fetchval('SELECT 1')
            expected=await self.setup.fetch('SELECT pid,backend_start FROM pg_stat_activity '
                'WHERE datname=current_database() ORDER BY backend_start DESC,pid DESC')
            before=await self.snapshot()
            with TemporaryDirectory() as directory:
                path=Path(directory)/'TEST_ONLY.ndjson'
                with path.open('xb') as stream:
                    diagnostics=s1.Diagnostics(s1.JsonlCheckpoints(stream))
                    result=await s1.collect(self.connector,diagnostics,
                        audit_from=self.start,as_of=self.end,remaining_seconds=120)
                raw=path.read_bytes();lines=raw.splitlines(keepends=True)
                saved={row['operation']:row['data'] for row in map(json.loads,lines)}
            self.assertIs(result['coverageComplete'],True)
            self.assertEqual(result['auditTotal'],100)
            sessions=saved['metadata.sessions']
            self.assertEqual(sessions['total'],4)  # Fixture plus the three extra clients; observer excluded.
            self.assertEqual([row['session_ref'] for row in sessions['rows']],
                [str(row['pid']) for row in expected])
            self.assertEqual(sessions['rows'][0]['session_ref'],str(await extras[-1].fetchval('SELECT pg_backend_pid()')))
            self.assertEqual(sum(row['n'] for row in sessions['groups']),4)
            for i in range(3):
                group=next(row for row in sessions['groups'] if row['application_name']=='TEST_ONLY_S1_EXTRA_'+str(i))
                self.assertEqual((group['usename'],group['state'],group['n']),
                    ('purchase_implementation_test','idle',1))
            self.assertFalse(sessions['truncated']);self.assertFalse(sessions['groupsTruncated'])
            for row in sessions['rows']+sessions['groups']:
                self.assertNotIn('client_addr',row);self.assertNotIn('query',row)
            self.assertLessEqual(max(map(len,lines)),128*1024);self.assertLessEqual(len(raw),512*1024)
            self.assertNotIn('TEST_ONLY',json.dumps(result))
            self.assertEqual(await self.snapshot(),before)
            await self.assert_owned_closed(2)
        finally:
            for conn in extras:
                if not conn.is_closed():await conn.close(timeout=4)

    async def test_server_statement_timeout_has_sqlstate_and_label_before_client_deadline(self):
        async def slow(conn): return await conn.fetchval('SELECT pg_sleep(1)')
        diagnostics=s1.Diagnostics(lambda *_:None)
        plans={'metadata':[('metadata.ledger',slow)],
               'audit':[('audit.records',AsyncMock())]}
        with patch.object(s1,'STATEMENT_TIMEOUT_MS',150),patch.object(s1,'COMMAND_TIMEOUT_SECONDS',3):
            with self.assertRaises(asyncpg.QueryCanceledError):
                await s1.observe(self.connector,plans,diagnostics,remaining_seconds=60)
        receipt=diagnostics.receipt()
        self.assertEqual(receipt['failedOperation'],'metadata.ledger')
        self.assertEqual(receipt['error'],{'errorType':'QueryCanceledError','sqlState':'57014'})
        self.assertFalse(receipt['envelopeExpired'])
        self.assertEqual(receipt['ownedClientsClosed'],{'metadata':True})
        self.assertIsNone(receipt['ledgerTruncated'])
        plans['audit'][0][1].assert_not_awaited()
        await self.assert_owned_closed(1)
