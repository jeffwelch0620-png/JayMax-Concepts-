"""Fictional packets and in-process transports only; never read private config."""
import asyncio
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import timedelta
import json
import io
import os
import subprocess
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
from uuid import uuid4

import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/ops'))
import read_only_probe as probe


def approval(value, directory=None):
    now=probe.utc()
    return {'packetSha256':probe.digest(value), 'stage':value['stage'], 'approved':True,
            'startsAt':now.isoformat(), 'endsAt':(now+timedelta(minutes=30)).isoformat(),
            'reference':'TEST_ONLY_OWNER_APPROVAL', 'evidenceDirectory':str(Path(directory or '.').resolve())}


def health_receipt():
    return {'format':probe.FORMAT, 'stage':'health', 'status':'preliminary_pass',
            'sourcesSha256':probe.digest(probe.sources()), 'completedAt':probe.utc().isoformat(),
            'cleanupConfirmed':True, 'target':{'url':probe.HEALTH_URL}}


class Clock:
    def __init__(self): self.value=0
    def __call__(self): return self.value


class Stream(httpx.AsyncByteStream):
    def __init__(self, chunks): self.chunks=chunks; self.closed=False
    async def __aiter__(self):
        for chunk in self.chunks: yield chunk
    async def aclose(self): self.closed=True


class ProbeGuards(unittest.IsolatedAsyncioTestCase):
    def test_process_control_interrupts_persist_receipts_then_propagate_in_isolated_process(self):
        # A real asyncio Task treats KeyboardInterrupt/SystemExit specially. Run
        # both in a child so a regression cannot abort the surrounding suite.
        code=r'''
import asyncio, json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import read_only_probe as probe
import maintenance_connection as maintenance
from test_read_only_probe import approval, health_receipt

async def main():
    count=0
    for kind in (KeyboardInterrupt,SystemExit):
        for phase in ('health','monitor','close','terminate','receipt'):
            with TemporaryDirectory() as directory:
                path=Path(directory); health=health_receipt(); failure=kind('TEST ONLY private interrupt')
                stage='calibration' if phase in ('close','terminate') else 'health'
                value=probe.packet(stage,**({'project':'abcdefghijklmnopqrst',
                    'health_sha':probe.digest(health)} if stage=='calibration' else {}))
                conn=SimpleNamespace(maintenance_peer=('2001:db8::1',5432,0,0),maintenance_tls=True,
                    close=AsyncMock(),terminate=lambda:None)
                if phase=='close': conn.close.side_effect=failure
                if phase=='terminate':
                    conn.close.side_effect=OSError('TEST ONLY private close')
                    def terminate(): raise failure
                    conn.terminate=terminate
                async def observe():
                    if phase in ('health','receipt'): raise failure
                    if phase=='monitor': await asyncio.Event().wait()
                    return {'status':'ok','database':'connected'}
                guards=0
                def resources(**kwargs):
                    nonlocal guards
                    guards+=1
                    if phase=='monitor' and guards==3: raise failure
                    return {}
                class FailingReceipt:
                    def __init__(self,stream): self.stream=stream
                    def write(self,raw): raise OSError('TEST ONLY private disk failure')
                    def close(self): self.stream.close()
                def fresh(p):
                    stream=Path(p).open('xb')
                    return FailingReceipt(stream) if phase=='receipt' and Path(p).suffix=='.json' else stream
                with patch.object(probe,'_fresh_private_file',side_effect=fresh), \
                     patch.object(probe,'private_path',side_effect=lambda p,**kw:Path(p)), \
                     patch.object(probe,'resources',side_effect=resources), \
                     patch.object(probe,'health_observation',side_effect=observe), \
                     patch('dotenv.dotenv_values',return_value={'MAINTENANCE_DATABASE_URL':
                         'postgresql://postgres:TEST_ONLY@db.abcdefghijklmnopqrst.supabase.co:5432/postgres'}), \
                     patch.object(maintenance,'connect',AsyncMock(return_value=conn)), \
                     patch.object(probe,'calibration',AsyncMock(return_value={'coverageComplete':True})), \
                     patch.dict('os.environ',{'DATABASE_SSL_ROOT_CERT':''}):
                    try:
                        await probe.execute_approved(value,approval(value,path),evidence_directory=path,
                            **({'config_path':path/'fake','health':health} if stage=='calibration' else {}))
                    except BaseException as caught:
                        assert caught is failure,(phase,type(caught).__name__)
                    else: raise AssertionError('Interrupt swallowed: '+phase)
                receipt_path=next(path.glob('*.json'))
                if phase=='receipt': assert receipt_path.read_bytes()==b''
                else:
                    receipt=json.loads(receipt_path.read_bytes())
                    assert receipt['status']=='held'
                    key='cleanupErrorType' if phase=='close' else 'error'
                    if phase=='close': assert receipt[key]==kind.__name__
                    elif phase=='terminate': assert receipt['terminateFailed'] is True
                    else: assert receipt[key]['errorType']==kind.__name__
                    assert 'private interrupt' not in json.dumps(receipt)
                if stage=='calibration': conn.close.assert_awaited_once()
                assert len(asyncio.all_tasks())==1,phase
                count+=1
    print('CONTROL_CASES_PASSED='+str(count))
asyncio.run(main())
'''
        env={**os.environ,'PYTHON_DOTENV_DISABLED':'1',
             'PYTHONPATH':os.pathsep.join((str(probe.ROOT/'tools/ops'),str(probe.ROOT/'backend'),
                 str(probe.ROOT/'backend/tests'),os.environ.get('PYTHONPATH','')))}
        result=subprocess.run([sys.executable,'-c',code],cwd=probe.ROOT,env=env,
            capture_output=True,text=True,timeout=40)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'CONTROL_CASES_PASSED=10')

    def test_generated_artifacts_never_overwrite_or_repair_existing_file(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'TEST_ONLY_existing.json'; path.write_bytes(b'TEST ONLY unchanged')
            with patch.object(probe.subprocess,'run') as acl:
                with self.assertRaises(FileExistsError): probe._fresh_private_file(path)
                acl.assert_not_called()
            self.assertEqual(path.read_bytes(),b'TEST ONLY unchanged')

    async def test_real_private_evidence_acl_and_refusal_of_broad_read_grant(self):
        if os.name != 'nt':
            with self.assertRaises(probe.Held): probe.private_path('TEST_ONLY')
            return
        import hosted_backup as backup
        with TemporaryDirectory() as directory,patch.dict(os.environ,{'LOCALAPPDATA':directory}):
            root=Path(directory).resolve()
            private=backup.private_directory(root/'JayMaxBuild/backups'/('backup-'+uuid4().hex),'backups')
            value=probe.packet('health'); auth=approval(value,private)
            with patch.object(probe,'resources',return_value={}), \
                 patch.object(probe,'health_observation',AsyncMock(return_value={'status':'ok','database':'connected'})):
                result=await probe.execute_approved(value,auth,evidence_directory=private)
            self.assertEqual(result['status'],'preliminary_pass')
            receipt=next(private.glob('*.json'))
            self.assertEqual(probe.private_path(receipt),receipt)
            modified=probe.subprocess.run(['icacls.exe',str(receipt),'/grant','*S-1-1-0:(R)'],
                capture_output=True,timeout=20,creationflags=probe.subprocess.CREATE_NO_WINDOW)
            self.assertEqual(modified.returncode,0)
            with self.assertRaises(FileExistsError): probe._fresh_private_file(receipt)
            with self.assertRaises(probe.Held): probe.private_path(receipt)

    def test_cli_only_prepares_checks_packets_and_never_executes_or_overwrites(self):
        with TemporaryDirectory() as directory,patch.object(probe,'execute_approved') as execute:
            path=Path(directory)/'packet.json'
            for args,expected in ((['packet','--stage','health','--file',str(path)],0),
                                  (['check','--file',str(path)],0),
                                  (['packet','--stage','health','--file',str(path)],2)):
                with self.subTest(args=args),patch.object(sys,'argv',['probe',*args]),redirect_stdout(io.StringIO()):
                    self.assertEqual(probe.main(),expected)
            execute.assert_not_called()
            self.assertFalse(json.loads(path.read_text())['executionApproved'])
            with patch.object(sys,'argv',['probe','run','--file',str(path)]),redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit): probe.main()
        with self.assertRaises(probe.Held): probe.unique_object([('status','ok'),('status','other')])

    async def test_observed_boundary_is_inclusive_and_evidence_limit_holds_without_losing_failure(self):
        clock=Clock(); observed=probe.Observed(object(),clock=clock)
        observed.record(-10,'fetch','completed')
        with self.assertRaises(probe.Held): observed.record(-10.001,'fetch','completed')
        with patch.dict(probe.LIMITS,events=2):
            with self.assertRaises(probe.Held): observed.record(0,'fetch','completed')
            observed.record(0,'fetch','failed')
        self.assertEqual(len(observed.reads),2)

    async def test_calibration_boundary_owns_one_connection_and_closes_on_success_failure_timeout(self):
        import maintenance_connection as maintenance
        import hosted_install_preservation as preservation
        for mode in ('pass','timeout','query','close','cancel','cleanup_cancel'):
            with self.subTest(mode=mode),TemporaryDirectory() as directory:
                path=Path(directory); health=health_receipt()
                value=probe.packet('calibration',project='abcdefghijklmnopqrst',health_sha=probe.digest(health))
                auth=approval(value,path)
                conn=SimpleNamespace(maintenance_peer=('2001:db8::1',5432,0,0),maintenance_tls=True,
                                     close=AsyncMock(),terminate=lambda:None)
                if mode=='close': conn.close.side_effect=OSError('TEST ONLY private close')
                if mode=='cleanup_cancel': conn.close.side_effect=asyncio.CancelledError()
                async def collect(*args,**kwargs):
                    if mode=='timeout': await asyncio.sleep(1)
                    if mode=='cancel': raise asyncio.CancelledError()
                    if mode=='query':
                        original=type('Driver',(RuntimeError,),{'sqlstate':'57014'})('TEST ONLY raw SQL/password')
                        raise preservation.wrap_fingerprint_timeout(original,'backup',(('public','TEST_ONLY_PRIVATE'),))
                    return {'coverageComplete':True,'metrics':{g:{'queryCalls':1,'cursorOperations':0,
                             'cursorEnvelopes':0,'maxSeconds':1} for g in probe.GROUPS}}
                with patch.object(probe,'_fresh_private_file',side_effect=lambda p:Path(p).open('xb')), patch.object(probe,'private_path',side_effect=lambda p,**kw:Path(p)), \
                     patch.object(probe,'resources',return_value={}), \
                     patch('dotenv.dotenv_values',return_value={'MAINTENANCE_DATABASE_URL':
                        'postgresql://postgres:TEST_ONLY@db.abcdefghijklmnopqrst.supabase.co:5432/postgres'}), \
                     patch.object(maintenance,'connect',AsyncMock(return_value=conn)) as connect, \
                     patch.object(probe,'calibration',side_effect=collect), \
                     patch.dict(probe.LIMITS,work=.03 if mode=='timeout' else 600), \
                     patch.dict('os.environ',{'DATABASE_SSL_ROOT_CERT':''}):
                    # Packet budgets must bind the exact reviewed implementation.
                    value['limits']=dict(probe.LIMITS); auth['packetSha256']=probe.digest(value)
                    if mode in ('cancel','cleanup_cancel'):
                        with self.assertRaises(asyncio.CancelledError):
                            await probe.execute_approved(value,auth,evidence_directory=path,config_path=path/'fake',health=health)
                    else:
                        result=await probe.execute_approved(value,auth,evidence_directory=path,config_path=path/'fake',health=health)
                        self.assertEqual(result['status'],'calibration_pass' if mode=='pass' else 'held')
                        self.assertNotIn('TEST_ONLY_PRIVATE',json.dumps(result))
                    self.assertEqual(connect.await_count,1); self.assertEqual(conn.close.await_count,1)
                    receipt=json.loads(next(path.glob('*.json')).read_bytes())
                    self.assertNotIn('password',json.dumps(receipt))
                    if mode=='query':
                        self.assertEqual(receipt['error']['sqlState'],'57014')
                        self.assertEqual(receipt['error']['fingerprintTimeout']['candidateObjects'],['public.TEST_ONLY_PRIVATE'])

    async def test_private_boundary_source_and_config_refusals_happen_without_connection(self):
        import maintenance_connection as maintenance
        health=health_receipt()
        value=probe.packet('calibration',project='abcdefghijklmnopqrst',health_sha=probe.digest(health))
        with TemporaryDirectory() as directory:
            path=Path(directory); auth=approval(value,path)
            with patch.object(probe,'_fresh_private_file',side_effect=lambda p:Path(p).open('xb')), patch.object(probe,'private_path',side_effect=lambda p,**kw:Path(p)), \
                 patch.object(probe,'resources',return_value={}), \
                 patch('dotenv.dotenv_values',return_value={'DATABASE_URL':'TEST ONLY must not fall back'}), \
                 patch.object(maintenance,'connect',AsyncMock()) as connect:
                result=await probe.execute_approved(value,auth,evidence_directory=path,config_path=path/'fake',health=health)
                self.assertEqual(result['status'],'held'); connect.assert_not_awaited()

    async def test_primary_fingerprint_failure_survives_stubborn_monitor_cleanup_hold(self):
        import maintenance_connection as maintenance
        import hosted_install_preservation as preservation
        entered=asyncio.Event(); release=asyncio.Event(); stopped=asyncio.Event()
        async def stubborn_sleep(seconds):
            self.assertEqual(seconds,1)
            entered.set()
            try: await release.wait()
            except asyncio.CancelledError:
                try: await release.wait()
                finally: stopped.set()
                raise
        original=type('Driver',(RuntimeError,),{'sqlstate':'57014'})('TEST ONLY private SQL/password')
        primary=preservation.wrap_fingerprint_timeout(original,'backup',(('public','TEST_ONLY_PRIVATE'),))
        async def collect(*args,**kwargs):
            await entered.wait()
            raise primary
        with TemporaryDirectory() as directory:
            path=Path(directory); health=health_receipt()
            value=probe.packet('calibration',project='abcdefghijklmnopqrst',health_sha=probe.digest(health))
            conn=SimpleNamespace(maintenance_peer=('2001:db8::1',5432,0,0),maintenance_tls=True,
                                 close=AsyncMock(),terminate=lambda:None)
            with patch.object(probe,'_fresh_private_file',side_effect=lambda p:Path(p).open('xb')), \
                 patch.object(probe,'private_path',side_effect=lambda p,**kw:Path(p)), \
                 patch.object(probe,'resources',return_value={}), \
                 patch('dotenv.dotenv_values',return_value={'MAINTENANCE_DATABASE_URL':
                     'postgresql://postgres:TEST_ONLY@db.abcdefghijklmnopqrst.supabase.co:5432/postgres'}), \
                 patch.object(maintenance,'connect',AsyncMock(return_value=conn)), \
                 patch.object(probe,'calibration',side_effect=collect), \
                 patch.object(probe.asyncio,'sleep',side_effect=stubborn_sleep), \
                 patch.dict('os.environ',{'DATABASE_SSL_ROOT_CERT':''}):
                try:
                    result=await probe.execute_approved(value,approval(value,path),
                        evidence_directory=path,config_path=path/'fake',health=health)
                    self.assertEqual(result['status'],'held')
                    self.assertFalse(result['cleanupConfirmed'])
                    self.assertNotIn('TEST_ONLY_PRIVATE',json.dumps(result))
                    self.assertNotIn('57014',json.dumps(result))
                    receipt=json.loads(next(path.glob('*.json')).read_bytes())
                    self.assertEqual(receipt['error']['errorType'],type(primary).__name__)
                    self.assertEqual(receipt['error']['sqlState'],'57014')
                    self.assertEqual(receipt['error']['snapshotCleanupErrorType'],'ObservationTaskCleanupHeld')
                    self.assertEqual(receipt['error']['fingerprintTimeout']['candidateObjects'],['public.TEST_ONLY_PRIVATE'])
                    self.assertNotIn('password',json.dumps(receipt))
                    conn.close.assert_awaited_once()
                finally:
                    release.set()
                    await asyncio.wait_for(stopped.wait(),1)

    async def test_cleanup_only_hold_still_refuses_success(self):
        entered=asyncio.Event(); release=asyncio.Event(); stopped=asyncio.Event()
        async def sleep(seconds):
            entered.set()
            try: await release.wait()
            except asyncio.CancelledError:
                try: await release.wait()
                finally: stopped.set()
                raise
        async def work(): await entered.wait(); return 'TEST ONLY completed'
        wait=asyncio.wait
        async def bounded_wait(*args,**kwargs):
            if 'timeout' in kwargs:
                self.assertEqual(kwargs['timeout'],5)
                kwargs['timeout']=.01
            return await wait(*args,**kwargs)
        with patch.object(probe.asyncio,'sleep',side_effect=sleep), \
             patch.object(probe.asyncio,'wait',side_effect=bounded_wait):
            try:
                with self.assertRaises(probe.Held) as caught: await probe.supervised(work(),lambda:None)
                self.assertEqual(caught.exception.snapshotCleanupErrorType,'ObservationTaskCleanupHeld')
            finally:
                release.set()
                await asyncio.wait_for(stopped.wait(),1)

    def test_source_manifest_covers_hash_sql_ca_and_operator_sources_without_importing_server(self):
        files=probe.sources()
        for path in ('tools/ops/read_only_probe.py', 'backend/maintenance_connection.py',
                     'backend/hosted_backup.py','backend/hosted_install_preservation.py',
                     'backend/readonly_snapshot.py','backend/native_backup.py',
                     'backend/schema_reconciliation.py','backend/db_tls.py',
                     'backend/certs/supabase-prod-ca-2021.crt','backend/requirements.txt'):
            self.assertIn(path,files)
        self.assertFalse(any('/tests/' in f for f in files))
        self.assertIn('backend/server.py',files) # hashed as data, never imported by probe
        self.assertTrue(all(len(h)==64 for h in files.values()))

    def test_packets_require_single_stage_and_exact_source_limits_and_discovery(self):
        for stage in ('health','calibration'):
            value=probe.packet(stage,**({} if stage=='health' else
                 {'project':'abcdefghijklmnopqrst','health_sha':'a'*64}))
            self.assertEqual(probe.check_packet(value),probe.digest(value))
            for edit in ('sources','limits','target','extra','executionApproved'):
                invalid=deepcopy(value)
                if edit=='sources': invalid['sources'].pop(next(iter(invalid['sources'])))
                elif edit=='limits': invalid['limits']['statement']=30
                elif edit=='target': invalid['target']['url']='https://other.invalid'
                elif edit=='extra': invalid['apply']=True
                else: invalid['executionApproved']=True
                with self.subTest(stage=stage,edit=edit), self.assertRaises(probe.Held): probe.check_packet(invalid)
        for kwargs in ({'stage':'health','project':'abcdefghijklmnopqrst'}, {'stage':'unknown'},
                       {'stage':'calibration','project':'abcdefghijklmnopqrst'},
                       {'stage':'calibration','project':'https://bad','health_sha':'a'*64}):
            with self.subTest(kwargs=kwargs), self.assertRaises(probe.Held): probe.packet(**kwargs)

    def test_approval_is_fresh_exact_stage_and_health_does_not_approve_database(self):
        value=probe.packet('health'); auth=approval(value)
        self.assertEqual(probe.approve_check(value,auth),probe.digest(value))
        for key,wrong in [('approved',False),('approved',1),('packetSha256','a'*64),
                          ('stage','calibration'),('reference','private URL / password')]:
            changed={**auth,key:wrong}
            with self.subTest(key=key,wrong=wrong),self.assertRaises(probe.Held): probe.approve_check(value,changed)
        for delta in (-1,80,3700):
            changed={**auth,'endsAt':(probe.utc()+timedelta(seconds=delta)).isoformat()}
            with self.subTest(delta=delta),self.assertRaises(probe.Held): probe.approve_check(value,changed)
        with self.assertRaises(probe.Held): probe.timestamp('2026-10-23T00:00:00')
        health=health_receipt()
        db=probe.packet('calibration',project='abcdefghijklmnopqrst',health_sha=probe.digest(health))
        with self.assertRaises(probe.Held): probe.approve_check(db,auth,health=health)
        self.assertEqual(probe.approve_check(db,approval(db),health=health),probe.digest(db))
        for field,wrong in [('cleanupConfirmed',False),('status','held'),('sourcesSha256','0'*64),
                            ('completedAt',(probe.utc()-timedelta(hours=1)).isoformat())]:
            bad={**health,field:wrong}
            bound=probe.packet('calibration',project='abcdefghijklmnopqrst',health_sha=probe.digest(bad))
            with self.subTest(field=field),self.assertRaises(probe.Held): probe.approve_check(bound,approval(bound),health=bad)

    async def test_refusal_precedes_config_private_paths_memory_and_network(self):
        value=probe.packet('health')
        with patch.object(probe,'private_path') as private,patch.object(probe,'resources') as resource, \
             patch.object(probe,'health_observation',AsyncMock()) as health:
            with self.assertRaises(probe.Held):
                await probe.execute_approved(value,{},evidence_directory='TEST_ONLY')
            private.assert_not_called(); resource.assert_not_called(); health.assert_not_awaited()

    async def test_health_one_request_no_auth_redirect_retry_or_proxy_and_exact_signal(self):
        stream=Stream([b'{"status":"ok",', b'"database":"connected"}'])
        calls=[]
        async def handler(request):
            calls.append(request)
            return httpx.Response(200,stream=stream)
        result=await probe.health_observation(transport=httpx.MockTransport(handler))
        self.assertEqual(result,{'httpStatus':200,'status':'ok','database':'connected'})
        self.assertEqual(len(calls),1); self.assertTrue(stream.closed)
        self.assertEqual(str(calls[0].url),probe.HEALTH_URL)
        for key in ('authorization','cookie'): self.assertNotIn(key,calls[0].headers)
        self.assertEqual(calls[0].headers['accept-encoding'],'identity')

    async def test_health_rejects_status_shape_missing_pool_encoded_and_oversized_without_retry(self):
        cases=[(302,b'{}',{}),(503,b'{}',{}),(200,b'{"status":"ok"}',{}),
               (200,b'{"status":"ok","database":"not connected"}',{}),
               (200,b'{"status":"ok","database":"connected","extra":"TEST ONLY"}',{}),
               (200,b'not json',{}),(200,b'x'*4097,{}),(200,b'{}',{'content-encoding':'gzip'})]
        for status,data,headers in cases:
            count=0; stream=Stream([data])
            async def handler(request):
                nonlocal count
                count+=1
                return httpx.Response(status,headers=headers,stream=stream)
            with self.subTest(status=status,data=data[:60]),self.assertRaises(probe.Held):
                await probe.health_observation(transport=httpx.MockTransport(handler))
            self.assertEqual(count,1); self.assertTrue(stream.closed)

    async def test_health_total_deadline_and_transport_failure_are_not_retried(self):
        for mode in ('sleep','tls'):
            count=0
            async def handler(request):
                nonlocal count
                count+=1
                if mode=='tls': raise httpx.ConnectError('TEST ONLY private transport text')
                await asyncio.sleep(1)
            with patch.dict(probe.LIMITS,health=.01):
                with self.subTest(mode=mode),self.assertRaises((TimeoutError,httpx.ConnectError)):
                    await probe.health_observation(transport=httpx.MockTransport(handler))
            self.assertEqual(count,1)

    async def test_observer_records_await_maxima_envelope_and_does_not_keep_sql_or_args(self):
        clock=Clock()
        class Raw:
            async def fetch(self,*args): clock.value+=2; return [1]
            def cursor(self,*args,**kwargs):
                async def cursor():
                    for _ in range(3): clock.value+=2; yield {'value':'a'}
                return cursor()
        observed=probe.Observed(Raw(),clock=clock)
        observed.group='backup'
        await observed.fetch('TEST ONLY private SQL','TEST ONLY password')
        self.assertEqual(len([r async for r in observed.cursor('TEST ONLY secret relation')]),3)
        self.assertEqual(observed.summary()['backup']['maxSeconds'],6)
        self.assertEqual(observed.summary()['backup']['cursorOperations'],4)
        self.assertNotIn('TEST ONLY',json.dumps(observed.reads+observed.cursors))
        with self.assertRaises(probe.Held): observed.unobserved_method

    async def test_slow_cursor_envelope_holds_even_with_fast_buffered_steps(self):
        clock=Clock()
        class Raw:
            def cursor(self,*args,**kwargs):
                async def cursor():
                    for _ in range(6): clock.value+=2; yield {'value':'hash'}
                return cursor()
        observed=probe.Observed(Raw(),clock=clock)
        with self.assertRaises(probe.Held): _=[r async for r in observed.cursor('private')]
        self.assertEqual(observed.cursors[0]['seconds'],12)

    async def test_driver_timeout_cancel_and_resource_hold_preserve_original_failure(self):
        clock=Clock()
        class Failure(Exception): sqlstate='57014'
        for error in (Failure('TEST ONLY private'),asyncio.CancelledError()):
            raw=type('Raw',(),{'fetch':AsyncMock(side_effect=error)})()
            observed=probe.Observed(raw,clock=clock)
            with self.assertRaises(type(error)) as caught: await observed.fetch('TEST ONLY')
            self.assertIs(caught.exception,error)
            self.assertEqual(observed.reads[0]['outcome'],'cancelled' if isinstance(error,asyncio.CancelledError) else 'failed')
        with patch.object(probe,'memory',return_value={'freeBytes':950*1024**2,'totalBytes':6*1024**3}):
            with self.assertRaises(probe.Held): probe.resources(start=True)
            probe.resources()
        with patch.object(probe,'memory',return_value={'freeBytes':400*1024**2,'totalBytes':6*1024**3}):
            with self.assertRaises(probe.Held): probe.resources()

    async def test_resource_monitor_cancels_work_and_no_automatic_retry(self):
        done=asyncio.Event()
        async def work():
            try: await asyncio.sleep(5)
            finally: done.set()
        def guard(): raise probe.Held('TEST ONLY resource guard')
        with self.assertRaises(probe.Held): await probe.supervised(work(),guard)
        self.assertTrue(done.is_set())

    async def test_simultaneous_read_failure_retains_primary_error_over_resource_monitor(self):
        original=type('Driver',(RuntimeError,),{'sqlstate':'57014'})('TEST ONLY private driver')
        async def work(): raise original
        def guard(): raise probe.Held('TEST ONLY resource guard')
        with self.assertRaises(type(original)) as caught:
            await probe.supervised(work(),guard)
        self.assertIs(caught.exception,original)

    async def test_private_exclusive_claim_prevents_second_request_and_public_redacts(self):
        with TemporaryDirectory() as directory:
            path=Path(directory); value=probe.packet('health'); auth=approval(value,path)
            with patch.object(probe,'_fresh_private_file',side_effect=lambda p:Path(p).open('xb')), patch.object(probe,'private_path',side_effect=lambda p,**kw:Path(p)), \
                 patch.object(probe,'resources',return_value={}), \
                 patch.object(probe,'health_observation',AsyncMock(return_value={'status':'ok'})) as request:
                result=await probe.execute_approved(value,auth,evidence_directory=path)
                self.assertEqual(result['status'],'preliminary_pass')
                with self.assertRaises(FileExistsError):
                    await probe.execute_approved(value,auth,evidence_directory=path)
                self.assertEqual(request.await_count,1)
                self.assertEqual(len(list(path.glob('*.json'))),1)
                self.assertNotIn(str(path),json.dumps(result))
                self.assertNotIn('TEST_ONLY',json.dumps(result))
                with self.assertRaises(probe.Held):
                    await probe.execute_approved(value,auth,evidence_directory=path/'other')

    async def test_failed_health_and_cancellation_leave_consumed_private_receipt_no_error_text(self):
        for failure in (RuntimeError('TEST ONLY password raw SQL'),asyncio.CancelledError()):
            with TemporaryDirectory() as directory:
                path=Path(directory); value=probe.packet('health'); auth=approval(value,path)
                with patch.object(probe,'_fresh_private_file',side_effect=lambda p:Path(p).open('xb')), patch.object(probe,'private_path',side_effect=lambda p,**kw:Path(p)), \
                     patch.object(probe,'resources',return_value={}), \
                     patch.object(probe,'health_observation',AsyncMock(side_effect=failure)):
                    if isinstance(failure,asyncio.CancelledError):
                        with self.assertRaises(asyncio.CancelledError): await probe.execute_approved(value,auth,evidence_directory=path)
                    else:
                        result=await probe.execute_approved(value,auth,evidence_directory=path)
                        self.assertEqual(result['status'],'held')
                    receipt=json.loads(next(path.glob('*.json')).read_bytes())
                    self.assertEqual(receipt['status'],'held')
                    self.assertNotIn('password',json.dumps(receipt))
