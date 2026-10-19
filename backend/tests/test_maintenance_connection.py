"""Fictional maintenance endpoints only; network/configuration changes are mocked."""
import asyncio
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import socket
import ssl
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import maintenance_connection as maintenance
import hosted_backup as backup
import hosted_additive_index as index
import hosted_reviewed_pars as pars

PROJECT = 'abcdefghijklmnopqrst'
URL = 'postgresql://postgres:TEST_ONLY@db.' + PROJECT + '.supabase.co:5432/postgres'


def connection(*, readonly=True, **changes):
    row = {'actor':'postgres','login':'postgres','database':'postgres','pid':123,
           'default_readonly':'on' if readonly else 'off','readonly':'on',
           'label':'jaymax-direct-maintenance'} | changes
    tx = MagicMock()
    tx.start = AsyncMock(); tx.commit = AsyncMock(); tx.rollback = AsyncMock()
    tx.__aenter__ = AsyncMock(); tx.__aexit__ = AsyncMock(return_value=False)
    return SimpleNamespace(maintenance_peer=('2001:db8::1',5432,0,0),maintenance_tls=True,
        transaction=MagicMock(return_value=tx),fetchrow=AsyncMock(return_value=row),
        close=AsyncMock(),terminate=MagicMock())


class MaintenanceEndpointTests(unittest.TestCase):
    def test_only_exact_direct_owner_project_and_explicit_mode_are_accepted(self):
        self.assertEqual(maintenance.direct_settings(URL,PROJECT)['user'],'postgres')
        for bad in (URL.replace(PROJECT,'differentprojectxxxx'),URL.replace('postgres:','other:'),
                    URL.replace(':5432',':6543'),URL+'?sslmode=disable',URL+'#fragment',
                    URL.replace('db.'+PROJECT+'.supabase.co','127.0.0.1'),
                    URL.replace('db.'+PROJECT+'.supabase.co','db.'+PROJECT+'.supabase.co.attacker.invalid'),
                    URL.replace('postgres:TEST_ONLY@db.'+PROJECT+'.supabase.co',
                                'postgres.'+PROJECT+':TEST_ONLY@aws-0.pooler.supabase.com'),
                    URL.replace(':5432',':invalid'),URL.replace('TEST_ONLY',''),
                    URL.replace('/postgres','/other')):
            with self.subTest(endpoint=bad),self.assertRaises(maintenance.MaintenanceConnectionError):
                maintenance.direct_settings(bad,PROJECT)
        # Existing export callers retain the session-only boundary.
        with self.assertRaises(backup.BackupError):backup.hosted_connection(URL,PROJECT)

    def test_app_url_is_never_a_maintenance_fallback(self):
        for config in ({},{'DATABASE_URL':URL},{'MAINTENANCE_DATABASE_URL':None},
                       {'MAINTENANCE_DATABASE_URL':' '}):
            with self.subTest(config=config),self.assertRaises(maintenance.MaintenanceConnectionError):
                maintenance.config_url(config)
        self.assertEqual(maintenance.config_url({'MAINTENANCE_DATABASE_URL':URL,'DATABASE_URL':'TEST ONLY APP'}),URL)

    def test_only_native_ipv6_dump_routing_retains_hostname_tls(self):
        for address in ('127.0.0.1','::ffff:127.0.0.1','not-an-address'):
            with self.subTest(address=address),self.assertRaises(maintenance.MaintenanceConnectionError):
                maintenance.ipv6_address(address)
        settings=maintenance.direct_settings(URL,PROJECT)|{'hostaddr':'2001:db8::1'}
        with patch.dict('os.environ',{'PGHOSTADDR':'127.0.0.1','PGSERVICE':'TEST ONLY'}):
            env=backup.process_env(settings,True)
        self.assertEqual(env['PGHOSTADDR'],'2001:db8::1')
        self.assertEqual(env['PGHOST'],'db.'+PROJECT+'.supabase.co')
        self.assertEqual(env['PGSSLMODE'],'verify-full')
        self.assertNotIn('PGSERVICE',env)
        self.assertIn('default_transaction_read_only=on',env['PGOPTIONS'])


class MaintenanceConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def run_connection(self, conn, *, readonly=True, context=None):
        context=context or ssl.create_default_context()
        with patch.object(maintenance,'connection_tls',return_value=context),\
             patch.object(maintenance.asyncpg,'connect',AsyncMock(return_value=conn)) as connect:
            result=await maintenance.connect(URL,PROJECT,readonly=readonly)
        self.assertEqual(connect.await_count,1)
        self.assertIs(connect.await_args.kwargs['ssl'],context)
        self.assertIs(connect.await_args.kwargs['connection_class'],maintenance.DirectIPv6Connection)
        self.assertEqual(connect.await_args.args,(URL,))
        self.assertEqual(connect.await_args.kwargs['statement_cache_size'],0)
        conn.transaction.assert_called_once_with(readonly=True)
        return result

    async def test_readonly_and_approved_writer_sessions_verify_effective_settings(self):
        for readonly in (True,False):
            with self.subTest(readonly=readonly):
                conn=connection(readonly=readonly)
                self.assertIs(await self.run_connection(conn,readonly=readonly),conn)
                conn.close.assert_not_awaited();conn.terminate.assert_not_called()

    async def test_ipv4_plaintext_missing_transport_and_ignored_startup_are_refused(self):
        variants=[('maintenance_peer',('192.0.2.1',5432)),
                  ('maintenance_peer',('::ffff:192.0.2.1',5432)),
                  ('maintenance_peer',None),('maintenance_peer',('2001:db8::1',6543)),
                  ('maintenance_tls',False),('row',{'label':'Supavisor'}),
                  ('row',{'default_readonly':'off'}),('row',{'readonly':'off'}),
                  ('row',{'actor':'other'}),('row',{'login':'other'}),
                  ('row',{'database':'other'}),('row',{'pid':False})]
        for name,value in variants:
            with self.subTest(refusal=name,value=value):
                conn=connection()
                if name=='row':conn.fetchrow.return_value.update(value)
                else:setattr(conn,name,value)
                with self.assertRaises(maintenance.MaintenanceConnectionError):await self.run_connection(conn)
                conn.close.assert_awaited_once_with(timeout=5);conn.terminate.assert_not_called()

    async def test_unverified_tls_and_bad_source_refuse_before_connect(self):
        context=ssl.create_default_context();context.check_hostname=False
        for url,ctx in ((URL,context),(URL,False),(URL+'?host=elsewhere',ssl.create_default_context())):
            with self.subTest(url=url),patch.object(maintenance,'connection_tls',return_value=ctx),\
                 patch.object(maintenance.asyncpg,'connect',AsyncMock()) as connect:
                with self.assertRaises(maintenance.MaintenanceConnectionError):await maintenance.connect(url,PROJECT)
                connect.assert_not_awaited()

    async def test_non_boolean_mode_and_unreviewed_labels_refuse_before_connect(self):
        for options in ({'readonly':'false'},{'label':None},{'label':'unreviewed'},{'label':'jaymax-'+('x'*56)}):
            with self.subTest(options=options),patch.object(maintenance.asyncpg,'connect',AsyncMock()) as connect:
                with self.assertRaises(maintenance.MaintenanceConnectionError):await maintenance.connect(URL,PROJECT,**options)
                connect.assert_not_awaited()

    async def test_failure_and_cancellation_close_only_the_new_owned_client(self):
        for error in (ConnectionError('TEST ONLY private'),asyncio.CancelledError()):
            with self.subTest(error=type(error).__name__):
                conn=connection();conn.fetchrow.side_effect=error
                conn.close.side_effect=RuntimeError('TEST ONLY close')
                with self.assertRaises(type(error)) as caught:await self.run_connection(conn)
                self.assertIs(caught.exception,error)
                self.assertEqual(error.connectionCloseErrorType,'RuntimeError')
                conn.terminate.assert_called_once_with()

    async def test_readonly_cleanup_failure_preserves_original_validation_error(self):
        conn=connection(actor='other')
        conn.transaction.return_value.rollback.side_effect=ConnectionError('TEST ONLY rollback')
        with self.assertRaises(maintenance.MaintenanceConnectionError) as caught:await self.run_connection(conn)
        self.assertEqual(caught.exception.snapshotCleanupErrorType,'ConnectionError')
        conn.close.assert_awaited_once()

    async def test_dump_dns_is_ipv6_only_bounded_and_does_not_use_env_hostaddr(self):
        loop=asyncio.get_running_loop()
        result=[(socket.AF_INET6,socket.SOCK_STREAM,6,'',('2001:db8::2',5432,0,0))]
        with patch.object(loop,'getaddrinfo',AsyncMock(return_value=result)) as dns:
            settings=await maintenance.dump_settings(URL,PROJECT)
        self.assertEqual(settings['hostaddr'],'2001:db8::2')
        self.assertEqual(dns.await_args.kwargs['family'],socket.AF_INET6)
        with patch.object(loop,'getaddrinfo',AsyncMock(return_value=[])):
            with self.assertRaises(maintenance.MaintenanceConnectionError):await maintenance.dump_settings(URL,PROJECT)

    async def test_retained_or_reassigned_pid_is_never_a_writer_exemption(self):
        # A past owner label/PID, or an idle pool backend, must still hold.
        conn=connection()
        row={'can_inspect':True,'verified_roles':1,'application_sessions':1,
             'write_transactions':0,'unobservable_sessions':0}
        conn.is_in_transaction=lambda:True
        conn.execute=AsyncMock();conn.fetchrow=AsyncMock(return_value=row)
        observations=[]
        with self.assertRaises(index.Held):
            await index.writer_sessions(conn,{'writerLoginRoles':['test_only_writer']},'test',observations)
        self.assertEqual(observations[0]['applicationSessionCount'],1)
        sql=conn.fetchrow.await_args.args[0]
        self.assertNotIn('application_name',sql)
        self.assertIn('pid<>pg_backend_pid()',sql)


class MaintenanceParRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_opt_in_separate_config_and_direct_dry_run_never_use_app_connection(self):
        modes=(('good',True,{'DATABASE_URL':'TEST ONLY APP','MAINTENANCE_DATABASE_URL':URL}),
               ('missing',True,{'DATABASE_URL':URL}),
               ('unapproved_direct',False,{'DATABASE_URL':URL}),
               ('pooler',True,{'MAINTENANCE_DATABASE_URL':URL.replace('db.'+PROJECT+'.supabase.co','aws-0.pooler.supabase.com')}))
        for name,opt_in,config in modes:
            with self.subTest(mode=name),TemporaryDirectory() as temporary:
                root=Path(temporary);out=root/'out';out.mkdir()
                spec={'projectRef':PROJECT,'originalReceipt':'original','sourceIndexPlan':'index',
                      'backup':{'encryptedFile':'archive','keyFile':'key','restoreReceipt':'restore'}}
                review_path=root/'review';review_path.write_text(json.dumps(spec))
                args=SimpleNamespace(mode='dry-run',owner_config='TEST_ONLY_PRIVATE',expected_project=PROJECT,
                    review=str(review_path),review_sha256=pars.sha(review_path.read_bytes()),
                    output_directory=str(out),maintenance_direct_ipv6=opt_in)
                conn=SimpleNamespace(close=AsyncMock())
                direct=AsyncMock(return_value=conn);app=AsyncMock()
                with ExitStack() as stack:
                    for obj,attr,value in ((pars.backup,'private_directory',lambda *a:out),
                            (pars,'write_private',lambda p,raw:Path(p).write_bytes(raw)),
                            (pars,'private_file',Path),(pars,'dotenv_values',lambda *a,**kw:config),
                            (pars,'load_evidence',lambda *a,**kw:(({},{}),{},{})),
                            (pars,'target',lambda *a:{'connectionMode':'direct'}),
                            (pars,'connection_tls',lambda *a:True),
                            (pars.asyncpg,'connect',app),(maintenance,'connect',direct),
                            (pars,'prepare',AsyncMock(return_value={'TEST_ONLY':'prepared'}))):
                        stack.enter_context(patch.object(obj,attr,value))
                    with redirect_stdout(io.StringIO()):result=await pars.run(args)
                app.assert_not_awaited()
                if name=='good':
                    self.assertEqual(result,0);direct.assert_awaited_once()
                    self.assertEqual(direct.await_args.args,(URL,PROJECT))
                    self.assertTrue(direct.await_args.kwargs['readonly'])
                    conn.close.assert_awaited_once()
                else:
                    self.assertEqual(result,2);direct.assert_not_awaited()
                    self.assertFalse(json.loads((out/'receipt.json').read_text())['sqlCommitted'])

    def test_direct_flag_cannot_bypass_apply_plan_approval_arguments(self):
        common=['--owner-config','TEST_ONLY','--expected-project',PROJECT,'--review','TEST_ONLY',
                '--review-sha256','0'*64,'--output-directory','TEST_ONLY','--plan','TEST_ONLY',
                '--plan-sha256','1'*64]
        for module,extra in ((pars,['--maintenance-direct-ipv6']),(index,[])):
            with self.subTest(module=module.__name__),patch('sys.argv',['operator','apply',*common,*extra]):
                with self.assertRaises(SystemExit) as caught:module.arguments()
                self.assertEqual(caught.exception.code,2)
