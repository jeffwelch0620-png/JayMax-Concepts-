"""Offline fictional observations only: no credentials, sockets or real database."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/ops'))
import s1_observation as s1


def connection(**changes):
    tx = SimpleNamespace(start=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock())
    conn = SimpleNamespace(transaction=MagicMock(return_value=tx), execute=AsyncMock(),
        close=AsyncMock(), terminate=MagicMock(), is_closed=MagicMock(return_value=True))
    for key, value in changes.items():
        setattr(conn, key, value)
    return conn, tx


def plans(**changes):
    readers = {
        'metadata': [('metadata.identity', AsyncMock(return_value={'readOnly':True})),
                     ('metadata.relations', AsyncMock(return_value=[{'name':'TEST_ONLY_ITEM'}])),
                     ('metadata.ledger', AsyncMock(return_value={'rows':[{'version':'TEST_ONLY'}],
                         'truncated':False,'total':1,'max_version':'TEST_ONLY'}))],
        'audit': [('audit.records', AsyncMock(return_value={'recordsTruncated': False}))]
    }
    for label, reader in changes.items():
        for phase, entries in readers.items():
            readers[phase] = [(name, reader if name == label else callback) for name, callback in entries]
    return readers


def empty_metadata(sql, *args):
    return [{'kind':'total','n':0}] if 'FROM pg_stat_activity' in sql else []


class S1ObservationTests(unittest.IsolatedAsyncioTestCase):
    def fixture(self, readers=None):
        first, tx1 = connection()
        second, tx2 = connection()
        connect = AsyncMock(side_effect=[first, second])
        saved = []
        journal = s1.Diagnostics(lambda label, data: saved.append((label, deepcopy(data))))
        return first, second, tx1, tx2, connect, saved, journal, readers or plans()

    async def run_plan(self, fixture, **kwargs):
        return await s1.observe(fixture[4], fixture[7], fixture[6], remaining_seconds=60, **kwargs)

    async def test_success_records_true_readonly_commit_and_closes_two_owned_clients(self):
        f = self.fixture()
        result = await self.run_plan(f)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(f[4].await_count, 2)
        for phase, conn, tx in zip(s1.PHASES, f[:2], f[2:4]):
            f[4].assert_any_await(phase, readonly=True, timeout=10, command_timeout=12)
            conn.transaction.assert_called_once_with(isolation='repeatable_read', readonly=True)
            tx.commit.assert_awaited_once(); tx.rollback.assert_not_awaited()
            conn.close.assert_awaited_once_with(timeout=4)
            self.assertTrue(result['ownedClientsClosed'][phase])
        operations = [e['operation'] for e in result['operations']]
        self.assertIn('metadata.commit', operations)
        self.assertNotIn('metadata.rollback', operations)
        self.assertEqual(result['completedObservations'], [label for label, _ in f[5]])

    async def test_ledger_timeout_retains_completed_prefix_and_never_starts_audit(self):
        original = TimeoutError('TEST ONLY postgres://user:PRIVATE@host SQL/body')
        f = self.fixture(plans(**{'metadata.ledger':AsyncMock(side_effect=original)}))
        with self.assertRaises(TimeoutError) as caught:
            await self.run_plan(f)
        self.assertIs(caught.exception, original)
        result = f[6].receipt()
        self.assertEqual(result['failedOperation'], 'metadata.ledger')
        self.assertFalse(result['envelopeExpired'])
        self.assertEqual(result['status'], 'held')
        self.assertEqual(result['completedObservations'], ['metadata.identity','metadata.relations'])
        self.assertEqual([label for label, _ in f[5]], result['completedObservations'])
        self.assertEqual(f[4].await_count, 1)
        f[2].rollback.assert_awaited_once(); f[2].commit.assert_not_awaited()
        f[0].close.assert_awaited_once(); f[1].close.assert_not_awaited()
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertNotIn('TEST_ONLY_ITEM', json.dumps(result))

    async def test_each_read_failure_identifies_the_exact_step(self):
        for label in ('metadata.identity','metadata.relations','metadata.ledger','audit.records'):
            with self.subTest(label=label):
                f = self.fixture(plans(**{label:AsyncMock(side_effect=ConnectionError('PRIVATE'))}))
                with self.assertRaises(ConnectionError):
                    await self.run_plan(f)
                self.assertEqual(f[6].receipt()['failedOperation'], label)
                self.assertNotIn(label, f[6].receipt()['completedObservations'])

    async def test_begin_settings_commit_and_close_failures_are_distinct(self):
        for step in ('begin','settings','commit','close'):
            with self.subTest(step=step):
                f = self.fixture()
                target = {'begin':f[2].start,'settings':f[0].execute,
                          'commit':f[2].commit,'close':f[0].close}[step]
                original = ConnectionError('PRIVATE')
                target.side_effect = original
                with self.assertRaises(ConnectionError) as caught:
                    await self.run_plan(f)
                self.assertIs(caught.exception, original)
                self.assertEqual(f[6].receipt()['failedOperation'], 'metadata.'+step)
                self.assertEqual(f[4].await_count, 1)
                f[0].close.assert_awaited_once()

    async def test_connection_error_has_no_retry_or_unowned_client_cleanup(self):
        f = self.fixture()
        f[4].side_effect = ConnectionError('PRIVATE credential')
        with self.assertRaises(ConnectionError):
            await self.run_plan(f)
        self.assertEqual(f[6].receipt()['failedOperation'], 'metadata.connect')
        self.assertEqual(f[4].await_count, 1)
        f[0].close.assert_not_awaited(); f[1].close.assert_not_awaited()

    async def test_original_timeout_survives_rollback_close_and_terminate_failures(self):
        original = TimeoutError('PRIVATE primary')
        f = self.fixture(plans(**{'metadata.ledger':AsyncMock(side_effect=original)}))
        f[2].rollback.side_effect = RuntimeError('PRIVATE rollback')
        f[0].close.side_effect = ConnectionError('PRIVATE close')
        f[0].terminate.side_effect = OSError('PRIVATE terminate')
        f[0].is_closed.return_value = False
        with self.assertRaises(TimeoutError) as caught:
            await self.run_plan(f)
        self.assertIs(caught.exception, original)
        result = f[6].receipt()
        self.assertEqual(result['failedOperation'], 'metadata.ledger')
        failures = [e['operation'] for e in result['operations'] if e['status']=='failed']
        self.assertEqual(failures, ['metadata.ledger','metadata.rollback','metadata.close',
                                    'metadata.terminate','metadata.confirm_closed'])
        self.assertFalse(result['ownedClientsClosed']['metadata'])
        self.assertNotIn('PRIVATE', json.dumps(result))

    async def test_cleanup_only_failure_never_reports_success_even_if_terminate_fails(self):
        for terminate_fails in (False, True):
            with self.subTest(terminate_fails=terminate_fails):
                f = self.fixture()
                f[0].close.side_effect = TimeoutError('PRIVATE close')
                if terminate_fails:
                    f[0].terminate.side_effect = RuntimeError('PRIVATE terminate')
                with self.assertRaises(TimeoutError):
                    await self.run_plan(f)
                self.assertEqual(f[6].status, 'held')
                f[0].terminate.assert_called_once()
                self.assertEqual(f[4].await_count, 1)

    async def test_false_or_failed_closure_confirmation_holds(self):
        for value in (False, RuntimeError('PRIVATE')):
            with self.subTest(value=type(value).__name__):
                f = self.fixture()
                if isinstance(value, Exception): f[0].is_closed.side_effect=value
                else: f[0].is_closed.return_value=value
                with self.assertRaises((s1.ObservationHeld,RuntimeError)):
                    await self.run_plan(f)
                self.assertEqual(f[6].receipt()['failedOperation'], 'metadata.confirm_closed')

    async def test_checkpoint_failure_preserves_prior_data_and_stops_later_reads(self):
        f = self.fixture()
        original_sink = f[6].checkpoint
        def fail(label, value):
            if label == 'metadata.relations': raise OSError('PRIVATE disk')
            original_sink(label, value)
        f[6].checkpoint = fail
        with self.assertRaises(OSError): await self.run_plan(f)
        self.assertEqual(f[6].completed, ['metadata.identity'])
        failed = next(e for e in f[6].events if e['status']=='failed')
        self.assertEqual((failed['operation'],failed['checkpointFor']),
                         ('evidence.checkpoint','metadata.relations'))
        f[7]['metadata'][2][1].assert_not_awaited()
        self.assertEqual(f[4].await_count, 1)

    async def test_actual_deadline_cancellation_is_attributed_and_drained(self):
        async def slow(conn): await asyncio.Event().wait()
        f = self.fixture(plans(**{'metadata.ledger':slow}))
        with self.assertRaises(TimeoutError): await self.run_plan(f, work_seconds=7.1)
        result = f[6].receipt()
        self.assertEqual(result['error']['errorType'], 'TimeoutError')
        self.assertTrue(result['envelopeExpired'])
        failed = next(e for e in result['operations'] if e['status']=='failed')
        self.assertEqual((failed['operation'],failed['errorType']),
                         ('metadata.ledger','CancelledError'))
        f[0].close.assert_awaited_once(); f[2].rollback.assert_awaited_once()
        self.assertEqual(len(asyncio.all_tasks()), 1)

    async def test_operator_cancellation_preserves_its_type_and_completed_evidence(self):
        original = asyncio.CancelledError('PRIVATE')
        f = self.fixture(plans(**{'metadata.ledger':AsyncMock(side_effect=original)}))
        with self.assertRaises(asyncio.CancelledError) as caught:
            await self.run_plan(f)
        self.assertIs(caught.exception, original)
        self.assertEqual(f[6].receipt()['error']['errorType'], 'CancelledError')
        self.assertFalse(f[6].receipt()['envelopeExpired'])
        self.assertEqual(f[6].completed, ['metadata.identity','metadata.relations'])
        f[2].rollback.assert_awaited_once(); f[0].close.assert_awaited_once()

    async def test_second_phase_failure_retains_first_phase_checkpoints(self):
        f = self.fixture(plans(**{'audit.records':AsyncMock(side_effect=TimeoutError())}))
        with self.assertRaises(TimeoutError): await self.run_plan(f)
        self.assertEqual(f[6].completed, ['metadata.identity','metadata.relations','metadata.ledger'])
        self.assertEqual(f[6].receipt()['failedOperation'], 'audit.records')
        self.assertEqual(f[4].await_count, 2)
        f[0].close.assert_awaited_once(); f[1].close.assert_awaited_once()

    async def test_fixed_collector_keeps_exact_minimized_query_scope_and_limits(self):
        f = self.fixture()
        for conn in f[:2]:
            conn.fetchrow = AsyncMock(return_value={'actor':'postgres','login':'postgres','db':'postgres','readonly':'on'})
            conn.fetch = AsyncMock(side_effect=empty_metadata)
        f[1].fetchrow.side_effect = [
            {'actor':'postgres','login':'postgres','db':'postgres','readonly':'on'},
            {'total':0, 'first_at':None, 'last_at':None}]
        start=datetime(2026,10,15,4,tzinfo=timezone.utc)
        end=datetime(2026,10,23,22,tzinfo=timezone.utc)
        result=await s1.collect(f[4],f[6],audit_from=start,as_of=end,remaining_seconds=60)
        self.assertEqual(result['status'],'complete')
        self.assertEqual(len(f[5]),11)
        first_calls=f[0].fetch.await_args_list
        self.assertEqual(len(first_calls),6)
        self.assertEqual(first_calls[0].args[1],list(s1.OBJECTS))
        self.assertEqual(len(s1.OBJECTS),14)
        self.assertEqual(first_calls[3].args[1],[3,4])
        self.assertIn('LIMIT 21',first_calls[4].args[0])
        self.assertIn('LIMIT 65',first_calls[5].args[0])
        self.assertIn('ORDER BY version::text DESC',first_calls[5].args[0])
        self.assertIn('count(*) OVER ()',first_calls[5].args[0])
        pin_sql=first_calls[2].args[0]
        self.assertIn('AS configured',pin_sql);self.assertNotIn('SELECT pin',pin_sql)
        audit_call=f[1].fetch.await_args
        self.assertEqual(audit_call.args[0].count('LIMIT 100'),2)
        self.assertIn('ORDER BY created_at ASC,id ASC',audit_call.args[0])
        self.assertIn('ORDER BY created_at DESC,id DESC',audit_call.args[0])
        self.assertEqual(audit_call.args[1:],(start,end,['owner','manager']))
        self.assertNotIn('user_email',audit_call.args[0])
        for call in (*first_calls,audit_call):
            self.assertTrue(call.args[0].startswith(('SELECT','WITH')))
            self.assertNotIn('password_hash',call.args[0])
            self.assertNotIn('command,',call.args[0])

    async def test_fixed_collector_ledger_timeout_writes_prior_rows_to_real_temp_stream(self):
        f=self.fixture()
        f[0].fetchrow=AsyncMock(return_value={'actor':'postgres','login':'postgres','db':'postgres','readonly':'on'})
        async def read(sql,*args):
            if 'schema_migrations' in sql:raise TimeoutError('PRIVATE SQL credential')
            if 'FROM pg_stat_activity' in sql:return empty_metadata(sql)
            return [{'TEST_ONLY_RESULT':True}]
        f[0].fetch=AsyncMock(side_effect=read)
        with TemporaryDirectory() as directory:
            path=Path(directory)/'TEST_ONLY.ndjson'
            with path.open('xb') as stream:
                journal=s1.Diagnostics(s1.JsonlCheckpoints(stream))
                with self.assertRaises(TimeoutError):
                    await s1.collect(f[4],journal,audit_from=datetime(2026,1,1,tzinfo=timezone.utc),
                        as_of=datetime(2026,1,2,tzinfo=timezone.utc),remaining_seconds=60)
                self.assertEqual(journal.receipt()['failedOperation'],'metadata.ledger')
                self.assertEqual([json.loads(l)['operation'] for l in path.read_bytes().splitlines()],
                    ['metadata.identity','metadata.relations','metadata.policies','metadata.pin_configuration',
                     'metadata.toast_jobs','metadata.sessions'])
                self.assertNotIn('PRIVATE',json.dumps(journal.receipt()))
        self.assertEqual(f[4].await_count,1)

    def audit_fixture(self, total=250, groups=None):
        f = self.fixture()
        identity = {'actor':'postgres','login':'postgres','db':'postgres','readonly':'on'}
        f[0].fetchrow = AsyncMock(return_value=identity)
        f[0].fetch = AsyncMock(side_effect=empty_metadata)
        start = datetime(2026,10,15,tzinfo=timezone.utc)
        data = [{'created_at':start+timedelta(seconds=i), 'user_id':'TEST_ONLY_USER',
                 'role':'manager', 'method':'GET', 'path':'/TEST_ONLY_PRIVATE_PATH',
                 'status':200, 'store_id':'TEST_ONLY_STORE'} for i in range(total)]
        f[1].fetchrow = AsyncMock(side_effect=[identity, {'total':total,
            'first_at':data[0]['created_at'] if data else None,
            'last_at':data[-1]['created_at'] if data else None}])
        group_rows = groups if groups is not None else [{'day':start.replace(tzinfo=None),
            'role':'manager','user_id':'TEST_ONLY_USER','method':'GET','status_class':2,'n':total}]
        sample = [dict(sample='earliest',**row) for row in data[:100]]
        sample += [dict(sample='latest',**row) for row in data[-100:]]
        f[1].fetch = AsyncMock(side_effect=[group_rows, sample])
        return f, start, data

    async def collect_audit(self, f, start):
        return await s1.collect(f[4],f[6],audit_from=start,
            as_of=start+timedelta(days=1),remaining_seconds=60)

    async def test_full_interval_total_and_split_sample_keep_newest_of_250_rows(self):
        f,start,data = self.audit_fixture()
        result = await self.collect_audit(f,start)
        evidence = dict(f[5])
        self.assertEqual(evidence['audit.summary'],
            {'total':250,'first_at':data[0]['created_at'],'last_at':data[-1]['created_at']})
        self.assertEqual(evidence['audit.records']['earliest'],data[:100])
        self.assertEqual(evidence['audit.records']['latest'],data[-100:])
        self.assertEqual(result['auditTotal'],250)
        self.assertTrue(result['recordsTruncated'])
        self.assertFalse(result['breakdownTruncated'])
        self.assertNotIn('TEST_ONLY_',json.dumps(result))
        self.assertNotIn('/TEST_ONLY_PRIVATE_PATH',json.dumps(result))
        summary_sql = f[1].fetchrow.await_args.args[0]
        self.assertIn('count(*) AS total',summary_sql)
        self.assertIn('min(created_at)',summary_sql)
        self.assertIn('max(created_at)',summary_sql)
        self.assertNotIn('LIMIT',summary_sql)
        for call in (*f[1].fetchrow.await_args_list[1:],*f[1].fetch.await_args_list):
            self.assertEqual(call.args[1:],(start,start+timedelta(days=1),['owner','manager']))
            self.assertNotIn('user_email',call.args[0])
        f[1].transaction.assert_called_once_with(readonly=True,isolation='repeatable_read')

    async def test_empty_and_exact_sample_boundaries_are_explicit(self):
        for total in (0,1,199,200,201):
            with self.subTest(total=total):
                f,start,_ = self.audit_fixture(total,groups=[])
                result = await self.collect_audit(f,start)
                self.assertEqual(result['auditTotal'],total)
                self.assertEqual(result['recordsTruncated'],total>200)
                self.assertFalse(result['breakdownTruncated'])
                sample = dict(f[5])['audit.records']
                self.assertEqual(len(sample['earliest']),min(total,100))
                self.assertEqual(len(sample['latest']),min(total,100))

    async def test_breakdown_lookahead_and_byte_budget_both_report_truncation(self):
        for count,field_size,truncated in ((500,10,False),(501,10,True),(500,2048,True),(1,150000,True)):
            with self.subTest(count=count,field_size=field_size):
                groups = [{'day':datetime(2026,10,15), 'role':'manager',
                    'user_id':'X'*field_size+str(i),'method':'GET','status_class':2,'n':1}
                    for i in range(count)]
                f,start,_ = self.audit_fixture(groups=groups)
                result = await self.collect_audit(f,start)
                breakdown = dict(f[5])['audit.breakdown']
                self.assertEqual(result['breakdownTruncated'],truncated)
                self.assertLessEqual(len(breakdown['groups']),500)
                self.assertLessEqual(len(s1.checkpoint_bytes('audit.breakdown',breakdown)),96*1024)
                self.assertIn('LIMIT 501',f[1].fetch.await_args_list[0].args[0])
                lines = [s1.checkpoint_bytes(label,value) for label,value in f[5]]
                self.assertLessEqual(max(map(len,lines)),128*1024)
                self.assertLessEqual(sum(map(len,lines)),512*1024)
                with TemporaryDirectory() as directory:
                    with (Path(directory)/'TEST_ONLY.ndjson').open('xb') as stream:
                        sink=s1.JsonlCheckpoints(stream)
                        for label,value in f[5]: sink(label,value)
                        self.assertEqual(sink.bytes_written,sum(map(len,lines)))

    async def test_audit_not_evaluated_and_partial_failure_never_look_empty_complete(self):
        fresh=s1.Diagnostics(lambda *_:None).receipt()
        for key in ('auditTotal','recordsTruncated','breakdownTruncated'):
            self.assertIsNone(fresh[key])
        for step in ('summary','breakdown','records'):
            with self.subTest(step=step):
                f,start,_=self.audit_fixture()
                if step=='summary':
                    f[1].fetchrow.side_effect=[
                        {'actor':'postgres','login':'postgres','db':'postgres','readonly':'on'},TimeoutError()]
                elif step=='breakdown': f[1].fetch.side_effect=TimeoutError()
                else: f[1].fetch.side_effect=[[],TimeoutError()]
                with self.assertRaises(TimeoutError): await self.collect_audit(f,start)
                result=f[6].receipt()
                self.assertEqual(result['failedOperation'],'audit.'+step)
                self.assertFalse(result['envelopeExpired'])
                self.assertEqual(result['auditTotal'],None if step=='summary' else 250)
                self.assertIsNone(result['recordsTruncated'])
                self.assertEqual(result['breakdownTruncated'],False if step=='records' else None)
                self.assertTrue(result['ownedClientsClosed']['audit'])
                self.assertNotIn('TEST_ONLY_',json.dumps(result))

    async def test_failed_summary_checkpoint_cannot_publish_coverage(self):
        f,start,_=self.audit_fixture()
        sink=f[6].checkpoint
        def fail(label,value):
            if label=='audit.summary': raise OSError('PRIVATE')
            sink(label,value)
        f[6].checkpoint=fail
        with self.assertRaises(OSError): await self.collect_audit(f,start)
        self.assertIsNone(f[6].receipt()['auditTotal'])
        f[1].fetch.assert_not_awaited()

    async def test_oversized_record_checkpoint_holds_without_claiming_sample_coverage(self):
        f,start,_=self.audit_fixture()
        sample=[{'sample':'earliest','path':'X'*(128*1024)}]
        f[1].fetch.side_effect=[[],sample]
        with TemporaryDirectory() as directory:
            with (Path(directory)/'TEST_ONLY.ndjson').open('xb') as stream:
                f[6].checkpoint=s1.JsonlCheckpoints(stream)
                with self.assertRaises(s1.ObservationHeld): await self.collect_audit(f,start)
                receipt=f[6].receipt()
                self.assertEqual(receipt['auditTotal'],250)
                self.assertFalse(receipt['breakdownTruncated'])
                self.assertIsNone(receipt['recordsTruncated'])
                self.assertNotIn('audit.records',receipt['completedObservations'])
                self.assertTrue(receipt['ownedClientsClosed']['audit'])

    async def test_fixed_collector_rejects_wrong_identity_before_other_reads(self):
        for field,value in (('actor','TEST_ONLY_OTHER'),('login','TEST_ONLY_OTHER'),('db','TEST_ONLY_OTHER'),('readonly','off')):
            with self.subTest(field=field):
                f=self.fixture()
                row={'actor':'postgres','login':'postgres','db':'postgres','readonly':'on'}
                row[field]=value
                f[0].fetchrow=AsyncMock(return_value=row);f[0].fetch=AsyncMock()
                with self.assertRaises(s1.ObservationHeld):
                    await s1.collect(f[4],f[6],audit_from=datetime(2026,1,1,tzinfo=timezone.utc),
                        as_of=datetime(2026,1,2,tzinfo=timezone.utc),remaining_seconds=60)
                f[0].fetch.assert_not_awaited()
                self.assertEqual(f[6].receipt()['failedOperation'],'metadata.identity')

    async def test_client_no_reply_timeout_has_no_sqlstate_or_envelope_expiry(self):
        async def never_answers(conn):
            return await asyncio.wait_for(asyncio.Event().wait(),conn.command_timeout)
        f=self.fixture(plans(**{'metadata.ledger':never_answers}))
        async def connect(phase,**options):
            conn=f[0] if phase=='metadata' else f[1]
            conn.command_timeout=options['command_timeout']
            return conn
        f[4].side_effect=connect
        self.assertEqual((s1.CONNECT_TIMEOUT_SECONDS,s1.COMMAND_TIMEOUT_SECONDS,
                          s1.STATEMENT_TIMEOUT_MS,s1.LOCK_TIMEOUT_MS),(10,12,10000,1000))
        with patch.object(s1,'COMMAND_TIMEOUT_SECONDS',.04):
            with self.assertRaises(TimeoutError): await self.run_plan(f)
        receipt=f[6].receipt()
        self.assertEqual(receipt['failedOperation'],'metadata.ledger')
        self.assertEqual(receipt['error'],{'errorType':'TimeoutError','sqlState':None})
        self.assertFalse(receipt['envelopeExpired'])
        self.assertIsNone(receipt['ledgerTruncated'])
        self.assertEqual(f[4].await_count,1)
        f[2].rollback.assert_awaited_once();f[0].close.assert_awaited_once()

    def metadata_fixture(self,name,count,*,wide=False):
        f=self.fixture()
        identity={'actor':'postgres','login':'postgres','db':'postgres','readonly':'on'}
        f[0].fetchrow=AsyncMock(return_value=identity)
        f[1].fetchrow=AsyncMock(side_effect=[identity,{'total':0,'first_at':None,'last_at':None}])
        async def read(sql,*args):
            target=('ledger' if 'schema_migrations' in sql else
                    'policies' if 'FROM pg_policies' in sql else
                    'sessions' if 'FROM pg_stat_activity' in sql else None)
            if target!=name:return empty_metadata(sql)
            if name=='sessions':
                return self.session_rows(count,1 if count else 0,wide=wide)
            if name=='ledger':
                return [{'version':'TEST_ONLY_'+str(count-i).zfill(3),
                    'name':'X'*(128*1024) if wide else 'TEST_ONLY_PRIVATE',
                    'total':count,'max_version':'TEST_ONLY_'+str(count).zfill(3)} for i in range(count)]
            return [{'TEST_ONLY_PRIVATE':'X'*(128*1024) if wide else i} for i in range(count)]
        f[0].fetch=AsyncMock(side_effect=read)
        f[1].fetch=AsyncMock(return_value=[])
        return f

    async def collect_metadata(self,f):
        return await s1.collect(f[4],f[6],audit_from=datetime(2026,1,1,tzinfo=timezone.utc),
            as_of=datetime(2026,1,2,tzinfo=timezone.utc),remaining_seconds=60)

    def session_rows(self,count,groups,*,wide=False):
        start=datetime(2026,10,1,tzinfo=timezone.utc)
        name='X'*(128*1024) if wide else 'TEST_ONLY_SESSION'
        return ([{'kind':'total','n':count}]
            +[{'kind':'row','usename':'TEST_ONLY_ROLE','application_name':name,
               'state':'idle','backend_start':start+timedelta(seconds=i),'pid':i}
              for i in range(count, max(count-21,0),-1)]
            +[{'kind':'group','usename':'TEST_ONLY_ROLE','application_name':name+str(i),
               'state':'idle','n':1} for i in range(min(groups,51))])

    async def test_session_sample_and_group_limits_keep_full_total_and_private_names(self):
        for total,groups in ((0,0),(20,1),(21,1),(50,50),(73,51),(125,75)):
            with self.subTest(total=total,groups=groups):
                f=self.metadata_fixture('sessions',0)
                f[0].fetch.side_effect=lambda sql,*args: (self.session_rows(total,groups)
                    if 'FROM pg_stat_activity' in sql else [])
                result=await self.collect_metadata(f)
                saved=dict(f[5])['metadata.sessions']
                self.assertEqual(saved['total'],total)
                self.assertEqual(len(saved['rows']),min(total,20))
                self.assertEqual(saved['truncated'],total>20)
                self.assertEqual(len(saved['groups']),min(groups,50))
                self.assertEqual(saved['groupsTruncated'],groups>50)
                self.assertEqual(result['sessionGroupsTruncated'],groups>50)
                self.assertEqual(result['coverageComplete'],total<=20 and groups<=50)
                if total:self.assertEqual(saved['rows'][0]['session_ref'],str(total))
                sql=next(call.args[0] for call in f[0].fetch.await_args_list if 'FROM pg_stat_activity' in call.args[0])
                self.assertIn('observed AS MATERIALIZED',sql)
                self.assertEqual(sql.count('FROM pg_stat_activity'),1)
                self.assertIn('backend_start DESC NULLS LAST,pid DESC LIMIT 21',sql)
                self.assertIn('LIMIT 51',sql)
                for forbidden in ('client_addr','query,','query_text'):
                    self.assertNotIn(forbidden,sql)
                self.assertNotIn('TEST_ONLY',json.dumps(result))
                lines=[s1.checkpoint_bytes(label,value) for label,value in f[5]]
                self.assertLessEqual(max(map(len,lines)),128*1024)
                self.assertLessEqual(sum(map(len,lines)),512*1024)

    async def test_session_aggregate_validation_and_failed_sink_leave_both_flags_unknown(self):
        valid={'rows':[],'truncated':False,'groups':[],'groupsTruncated':False,'total':0}
        for change in ({'total':True},{'total':-1},{'groups':None},
                       {'groups':[{}]*51},{'groupsTruncated':None}):
            with self.subTest(change=change):
                journal=s1.Diagnostics(lambda *_:None)
                with self.assertRaises(s1.ObservationHeld):
                    await journal.capture('metadata.sessions',{**valid,**change})
                self.assertIsNone(journal.receipt()['sessionsTruncated'])
                self.assertIsNone(journal.receipt()['sessionGroupsTruncated'])
        journal=s1.Diagnostics(lambda *_:(_ for _ in ()).throw(OSError('PRIVATE')))
        with self.assertRaises(OSError):await journal.capture('metadata.sessions',valid)
        self.assertIsNone(journal.receipt()['sessionGroupsTruncated'])

    async def test_ledger_aggregate_requires_explicit_consistent_maximum(self):
        for value in ({'total':3,'max_version':None},{'total':0,'max_version':'TEST_ONLY'},
                      {'total':True,'max_version':'TEST_ONLY'},{'total':-1,'max_version':None},
                      {'total':0},{'total':3,'max_version':7}):
            with self.subTest(value=value):
                journal=s1.Diagnostics(lambda *_:None)
                with self.assertRaises(s1.ObservationHeld):
                    await journal.capture('metadata.ledger',{'rows':[],'truncated':False,**value})
                self.assertIsNone(journal.receipt()['ledgerTruncated'])
        for total,maximum in ((0,None),(3,'TEST_ONLY')):
            with self.subTest(total=total):
                journal=s1.Diagnostics(lambda *_:None)
                await journal.capture('metadata.ledger',{'rows':[],'truncated':False,
                    'total':total,'max_version':maximum})
                self.assertFalse(journal.receipt()['ledgerTruncated'])

    def test_coverage_summary_is_nullable_and_execution_status_remains_separate(self):
        journal=s1.Diagnostics(lambda *_:None)
        self.assertIsNone(journal.receipt()['coverageComplete'])
        journal.audit_coverage={'auditTotal':0,'recordsTruncated':False,'breakdownTruncated':False}
        journal.metadata_coverage={key:False for key in journal.metadata_coverage}
        for status in ('not_started','running','held','complete'):
            with self.subTest(status=status):
                journal.status=status
                self.assertIs(journal.receipt()['coverageComplete'],status=='complete')
        for coverage in (journal.audit_coverage,journal.metadata_coverage):
            for key in coverage:
                if not key.endswith('Truncated'):continue
                with self.subTest(key=key):
                    coverage[key]=True
                    self.assertIs(journal.receipt()['coverageComplete'],False)
                    coverage[key]=None
                    self.assertIsNone(journal.receipt()['coverageComplete'])
                    coverage[key]=False
        journal.audit_coverage['recordsTruncated']=True
        journal.metadata_coverage['sessionGroupsTruncated']=None
        self.assertIsNone(journal.receipt()['coverageComplete'])  # Unknown takes precedence.
        journal.metadata_coverage['sessionGroupsTruncated']=False
        journal.audit_coverage['recordsTruncated']=False
        for total in (None,True,'0'):
            with self.subTest(total=total):
                journal.audit_coverage['auditTotal']=total
                self.assertIs(journal.receipt()['coverageComplete'],None if total is None else False)

    async def test_metadata_empty_exact_and_lookahead_boundaries_are_explicit(self):
        for name,cap in s1.METADATA_CAPS.items():
            for count in (0,cap,cap+1):
                with self.subTest(name=name,count=count):
                    f=self.metadata_fixture(name,count)
                    result=await self.collect_metadata(f)
                    saved=dict(f[5])['metadata.'+name]
                    self.assertEqual(len(saved['rows']),min(count,cap))
                    self.assertEqual(saved['truncated'],count>cap)
                    self.assertEqual(result[name+'Truncated'],count>cap)
                    if name=='ledger':
                        self.assertEqual(saved['total'],count)
                        self.assertEqual(saved['max_version'],'TEST_ONLY_'+str(count).zfill(3) if count else None)
                    self.assertNotIn('TEST_ONLY',json.dumps(result))
                    self.assertEqual(result['format'],'jaymax-s1-diagnostics-v3')

    async def test_failed_metadata_checkpoint_cannot_publish_its_coverage(self):
        for name in s1.METADATA_CAPS:
            with self.subTest(name=name):
                f=self.metadata_fixture(name,s1.METADATA_CAPS[name]+1)
                original=f[6].checkpoint
                def fail(label,value):
                    if label=='metadata.'+name:raise OSError('TEST_ONLY_PRIVATE')
                    original(label,value)
                f[6].checkpoint=fail
                with self.assertRaises(OSError):await self.collect_metadata(f)
                receipt=f[6].receipt()
                self.assertIsNone(receipt[name+'Truncated'])
                self.assertNotIn('metadata.'+name,receipt['completedObservations'])
                event=next(e for e in receipt['operations'] if e['status']=='failed')
                self.assertEqual((event['operation'],event['checkpointFor']),('evidence.checkpoint','metadata.'+name))
                self.assertEqual(f[4].await_count,1)
                self.assertTrue(receipt['ownedClientsClosed']['metadata'])

    async def test_metadata_byte_cap_holds_without_a_false_complete_flag(self):
        for name in s1.METADATA_CAPS:
            with self.subTest(name=name),TemporaryDirectory() as directory:
                f=self.metadata_fixture(name,1,wide=True)
                path=Path(directory)/'TEST_ONLY.ndjson'
                with path.open('xb') as stream:
                    f[6].checkpoint=s1.JsonlCheckpoints(stream)
                    with self.assertRaises(s1.ObservationHeld):await self.collect_metadata(f)
                self.assertIsNone(f[6].receipt()[name+'Truncated'])
                lines=path.read_bytes().splitlines(keepends=True)
                self.assertTrue(all(len(line)<=128*1024 for line in lines))
                self.assertLessEqual(sum(map(len,lines)),512*1024)
                self.assertTrue(all(json.loads(line)['format']=='jaymax-s1-checkpoint-v3' for line in lines))
                self.assertTrue(f[6].receipt()['ownedClientsClosed']['metadata'])

    async def test_metadata_unknown_or_malformed_coverage_stays_unevaluated(self):
        journal=s1.Diagnostics(lambda *_:None)
        for name in s1.METADATA_CAPS:
            self.assertIsNone(journal.receipt()[name+'Truncated'])
        for name in s1.METADATA_CAPS:
            with self.subTest(name=name):
                journal=s1.Diagnostics(lambda *_:None)
                with self.assertRaises(s1.ObservationHeld):
                    await journal.capture('metadata.'+name,{'rows':[],'truncated':'false'})
                self.assertIsNone(journal.receipt()[name+'Truncated'])
                self.assertEqual(journal.receipt()['failedOperation'],'evidence.checkpoint')

    async def test_fixed_collector_refuses_invalid_audit_interval_without_connect(self):
        valid=datetime(2026,1,1,tzinfo=timezone.utc)
        for start,end in ((None,valid),(datetime(2026,1,1),valid),(valid,None),
                          (valid,datetime(2025,1,1,tzinfo=timezone.utc))):
            with self.subTest(start=start,end=end):
                f=self.fixture()
                with self.assertRaises(s1.ObservationHeld):
                    await s1.collect(f[4],f[6],audit_from=start,as_of=end,remaining_seconds=60)
                f[4].assert_not_awaited()

    async def test_invalid_limits_or_plan_refuse_before_connecting(self):
        for value in (0,-1,7,121,float('nan'),float('inf'),True):
            with self.subTest(value=value):
                f = self.fixture()
                with self.assertRaises(s1.ObservationHeld): await self.run_plan(f,work_seconds=value)
                f[4].assert_not_awaited()
        for invalid in ({'metadata':[]}, {'audit':[],'metadata':[]},
                        {'metadata':[('metadata.PRIVATE',AsyncMock())],'audit':[]},
                        {'metadata':[('metadata.identity',AsyncMock())]*2,'audit':[]}):
            with self.subTest(plan=list(invalid)):
                f = self.fixture(); f = (*f[:7], invalid)
                with self.assertRaises(s1.ObservationHeld): await self.run_plan(f)
                f[4].assert_not_awaited()

    async def test_diagnostics_cannot_be_reused_for_another_attempt(self):
        f = self.fixture()
        await self.run_plan(f)
        with self.assertRaises(s1.ObservationHeld): await self.run_plan(f)
        self.assertEqual(f[4].await_count, 2)

    async def test_full_diagnostic_budget_cannot_suppress_owned_cleanup(self):
        for close_fails in (False,True):
            with self.subTest(close_fails=close_fails):
                f=self.fixture()
                f[6].events=[{'operation':'metadata.identity','status':'completed'}]*64
                if close_fails: f[0].close.side_effect=TimeoutError()
                original=ConnectionError('PRIVATE primary')
                await s1.close_owned(f[0],f[6],'metadata',original)
                f[0].close.assert_awaited_once()
                self.assertEqual(f[0].terminate.call_count,1 if close_fails else 0)
                self.assertTrue(f[6].closed['metadata'])
                self.assertTrue(f[6].receipt()['diagnosticsTruncated'])
                self.assertEqual(len(f[6].events),64)

    async def test_public_labels_and_failed_callbacks_remain_bounded(self):
        journal=s1.Diagnostics(lambda *_:None)
        journal.events=[{'operation':'metadata.identity','status':'completed'}]*64
        callback=AsyncMock()
        with self.assertRaises(s1.ObservationHeld): await journal.run('metadata.ledger',callback)
        callback.assert_not_awaited()
        self.assertTrue(journal.truncated)


class S1EvidenceTests(unittest.TestCase):
    def test_private_prefix_survives_later_statement_failure(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'TEST_ONLY.ndjson'
            with path.open('xb') as stream:
                writer = s1.JsonlCheckpoints(stream)
                writer('metadata.identity', {'at':datetime(2026,1,1,tzinfo=timezone.utc)})
                writer('metadata.relations', [{'name':'TEST_ONLY'}])
                with self.assertRaises(TypeError): writer('metadata.ledger', object())
                rows = [json.loads(line) for line in path.read_bytes().splitlines()]
                self.assertEqual([r['operation'] for r in rows], ['metadata.identity','metadata.relations'])
            self.assertTrue(stream.closed)

    def test_short_write_and_flush_failure_are_not_complete_checkpoints(self):
        for phase in ('write','flush','fsync'):
            with self.subTest(phase=phase):
                stream = MagicMock()
                stream.write.side_effect = lambda data: len(data)-1 if phase=='write' else len(data)
                if phase=='flush': stream.flush.side_effect=OSError('PRIVATE')
                writer = s1.JsonlCheckpoints(stream)
                with patch.object(s1.os,'fsync',side_effect=OSError('PRIVATE') if phase=='fsync' else None):
                    with self.assertRaises((s1.ObservationHeld,OSError)):
                        writer('metadata.identity', {'TEST_ONLY':True})
                self.assertEqual(writer.bytes_written, 0)
                self.assertTrue(writer.failed)
                before=stream.write.call_count
                with self.assertRaises(s1.ObservationHeld): writer('metadata.identity',{})
                self.assertEqual(stream.write.call_count,before)

    def test_private_size_limits_and_nonfinite_json_are_refused(self):
        stream = MagicMock()
        writer = s1.JsonlCheckpoints(stream)
        for label,value in (('metadata.identity','X'*(128*1024)),
                            ('metadata.identity',float('nan')),('PRIVATE',{})):
            with self.subTest(label=label),self.assertRaises((s1.ObservationHeld,ValueError)):
                writer(label,value)
        stream.write.assert_not_called()
        writer.bytes_written=512*1024
        with self.assertRaises(s1.ObservationHeld): writer('audit.records',[])

    def test_exception_messages_and_unknown_type_names_never_enter_public_receipt(self):
        error = type('PRIVATE_TOKEN_CLASS',(RuntimeError,),{})('PRIVATE_URL_AND_SQL')
        error.sqlstate='08006'
        self.assertEqual(s1.safe_error(error), {'errorType':'OtherError','sqlState':'08006'})
        for state in ('PRIVATE_STRING',None,8006,['08006']):
            with self.subTest(state=state):
                error.sqlstate=state
                self.assertIsNone(s1.safe_error(error)['sqlState'])

    def test_invalid_label_refuses_before_callback(self):
        journal = s1.Diagnostics(lambda *_:None)
        with self.assertRaises(s1.ObservationHeld):
            asyncio.run(journal.run('PRIVATE_SECRET',AsyncMock()))
        self.assertEqual(journal.events,[])

    def test_public_receipt_is_a_detached_snapshot(self):
        journal=s1.Diagnostics(lambda *_:None)
        journal.events.append({'operation':'metadata.ledger','status':'failed'})
        result=journal.receipt();result['operations'][0]['operation']='PRIVATE_CHANGED'
        self.assertEqual(journal.events[0]['operation'],'metadata.ledger')

    def test_broken_sqlstate_property_does_not_replace_primary_error(self):
        class BrokenError(Exception):
            @property
            def sqlstate(self): raise RuntimeError('PRIVATE formatting')
        self.assertEqual(s1.safe_error(BrokenError()),{'errorType':'OtherError','sqlState':None})

    def test_async_checkpoint_sink_is_refused_before_an_observation(self):
        async def async_sink(label,value): pass
        class AsyncSink:
            async def __call__(self,label,value):pass
        for sink in (async_sink,AsyncSink()):
            with self.subTest(sink=type(sink).__name__),self.assertRaises(s1.ObservationHeld):
                s1.Diagnostics(sink)

    def test_returned_unawaited_checkpoint_cannot_claim_completion(self):
        async def not_written(): pass
        journal=s1.Diagnostics(lambda *_:not_written())
        with self.assertRaises(s1.ObservationHeld): asyncio.run(journal.capture('metadata.identity',{}))
        self.assertEqual(journal.completed,[])
