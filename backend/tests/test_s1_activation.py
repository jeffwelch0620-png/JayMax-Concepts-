"""S1 approval/ledger/HTTP rehearsal tests. All identities and secrets fictional."""
import asyncio
from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import multiprocessing
import os
from pathlib import Path
import ssl
import sys
import threading

import httpx
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/ops'))
import s1_activation as activation
import s1_operator as operator
import s1_activation_workers as workers

MEMBER='11111111-1111-4111-8111-111111111111'


def actors(profile):
    return {role:{'id':'TEST-ONLY-'+role,'email':role+'@example.invalid','role':role,'locations':['berts']}
            for role in profile['roles']}


def approval(profile,directory,people=None):
    now=activation.engine.utc_now()
    return {'format':activation.FORMAT,'profileSha256':activation.digest(profile),
            'actorsSha256':activation.digest(people or actors(profile)),'attemptId':profile['attemptId'],
            'approved':True,'ownerReference':'TEST_ONLY_OWNER_APPROVAL','rosterId':MEMBER if profile['roster'] and profile['pinConfigured'] else None,
            'startsAt':now.isoformat(),'stopChecksAt':(now+timedelta(seconds=780)).isoformat(),
            'endsAt':(now+timedelta(seconds=900)).isoformat(),'evidenceDirectory':str(directory.resolve()),
            'preflight':{'observedAt':now.isoformat(),'apiCommit':profile['proof']['sourceCommit'],
                         'runtimeSha256':profile['proof']['apiRuntimeSha256'],'quietConfirmed':True}}


def test_prepare_is_inert_local_default_and_no_boolean_host_bypass(monkeypatch):
    monkeypatch.setattr(httpx,'AsyncClient',lambda **_:pytest.fail('network client created'))
    value=activation.prepare()
    assert value['mode']=='rehearsal' and value['executionApproved'] is False and len(activation.sequence(value))==21
    for origin in ('https://outside.invalid','http://jaymax-api.onrender.com','https://jaymax-api.onrender.com/'):
        with pytest.raises(activation.Held): activation.prepare(mode='hosted',origin=origin)
    with pytest.raises(activation.Held): activation._ApprovedTransport(True)
    with pytest.raises(activation.Held):
        activation.engine.LocalTransport(activation.ORIGIN,approved=True,guard=lambda:None,**{
            'ends_at':activation.engine.utc_now()+timedelta(seconds=900),
            'stop_checks_at':activation.engine.utc_now()+timedelta(seconds=780)})


@pytest.mark.parametrize('field,value',[('executionApproved',True),('clock','real'),('unexpected',1)])
def test_profile_mutation_is_refused(field,value):
    profile=activation.prepare();profile[field]=value
    with pytest.raises(activation.Held): activation.check_profile(profile)


@pytest.mark.parametrize('field,value',[('approved',False),('ownerReference',''),('attemptId','0'*32),
    ('profileSha256','0'*64),('actorsSha256','0'*64),('startsAt','2000-01-01'),('rosterId','not-an-id')])
def test_wrong_approval_refuses_before_claim(tmp_path,field,value):
    profile=activation.prepare();bound=approval(profile,tmp_path);bound[field]=value
    with pytest.raises(activation.Held): activation.Journal(profile,bound,actors(profile),tmp_path)
    assert not list(tmp_path.iterdir())


def test_stale_proof_and_changed_sources_refuse(tmp_path,monkeypatch):
    profile=activation.prepare();bound=approval(profile,tmp_path)
    bound['preflight']['observedAt']='2000-01-01T00:00:00+00:00'
    with pytest.raises(activation.Held): activation.Journal(profile,bound,actors(profile),tmp_path)
    monkeypatch.setattr(activation,'execution_pins',lambda:{'changed':'source'})
    with pytest.raises(activation.Held): activation.check_profile(profile)


def test_exclusive_attempt_and_pending_dispatch_survive_close(tmp_path):
    profile=activation.prepare();bound=approval(profile,tmp_path)
    ledger=activation.Journal(profile,bound,actors(profile),tmp_path)
    ledger.intent('P01')
    result=ledger.finish(cleanup_confirmed=True)
    assert result['status']=='held' and result['requestPending']
    with pytest.raises(FileExistsError): activation.Journal(profile,bound,actors(profile),tmp_path)
    rows=[json.loads(line) for line in next(tmp_path.glob('*.jsonl')).read_text().splitlines()]
    assert [row['event'] for row in rows]==['claimed','intent','closed']


def test_two_processes_race_one_claim(tmp_path):
    profile=activation.prepare();bound=approval(profile,tmp_path);ctx=multiprocessing.get_context('spawn')
    parents=[];children=[]
    for _ in range(2):
        parent,child=ctx.Pipe(duplex=False)
        process=ctx.Process(target=workers.claim,args=(profile,bound,actors(profile),str(tmp_path),child))
        process.start();child.close();parents.append(parent);children.append(process)
    result=[]
    try:
        for parent in parents:
            assert parent.poll(20);result.append(parent.recv_bytes())
        assert sorted(result)==[b'held',b'won']
    finally:
        for parent in parents: parent.close()
        for process in children:
            process.join(10)
            if process.is_alive(): process.terminate();process.join(3)
            assert process.exitcode==0
            process.close()


@pytest.mark.parametrize('roster,pin,roles',[(True,True,('owner','manager','staff')),
    (False,True,('owner',)),(False,False,('owner','staff'))])
def test_finite_variants_omit_without_budget_reallocation(roster,pin,roles):
    profile=activation.prepare(roster=roster,pin_configured=pin,roles=roles)
    order=activation.sequence(profile)
    assert len(order)<=21 and len(order)==len(set(order)) and order[0]=='P01'
    if not roster: assert 'P02' not in order and 'P11' not in order
    if not pin: assert set(label for label in order if label.startswith('P'))=={'P01','P12'}
    elif not roster: assert activation.steps(profile)['P04'].path==activation.engine.VERIFY


def test_actor_and_store_are_independent_of_returned_login(tmp_path):
    profile=activation.prepare();people=actors(profile);bound=approval(profile,tmp_path,people)
    ledger=activation.Journal(profile,bound,people,tmp_path)
    response={'token':'TEST-ONLY-token-value.0123456789','user':dict(people['owner'],id='wrong-subject')}
    client=activation.rehearsal_client(ledger,transport=httpx.MockTransport(lambda _:httpx.Response(200,json=response)))
    # Advance approved ledger to login without trusting returned identity.
    for label in ('P01','P02'):
        ledger.intent(label);ledger.result({'request':label,'outcome':'passed','httpStatus':200})
    with pytest.raises(activation.Held,match='approved_actor_mismatch'):
        asyncio.run(client.login('owner',people['owner']['email'],operator.FICTIONAL_PASSWORD))
    assert not client._sessions
    ledger.finish(cleanup_confirmed=True)
    people['manager']['locations']=[]
    with pytest.raises(activation.Held): activation.actor_check(people,profile)


@contextmanager
def fixture_server(profile,tls_context=None):
    people=actors(profile);order=activation.sequence(profile);seen=[];errors=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def handle_case(self):
            try:
                label=order[len(seen)];step=activation.steps(profile).get(label)
                data=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0')))) if self.command=='POST' else None
                if label.startswith('L'):
                    role=activation.engine.ROLES[int(label[1:])-1]
                    assert self.path=='/api/auth/login' and data=={'email':people[role]['email'],'password':operator.FICTIONAL_PASSWORD}
                    value={'token':'TEST-ONLY-'+role+'-token.0123456789','user':people[role]};status=200
                else:
                    assert self.path==step.path
                    if label.startswith('R'):
                        assert self.headers['Authorization']=='Bearer TEST-ONLY-'+step.actor+'-token.0123456789'
                    else: assert self.headers.get('Authorization') is None
                    status=step.status
                    if step.shape=='yes': value={'ok':True,'staff':[{'id':MEMBER,'name':'TEST ONLY','role':'owner_admin','active':True}]}
                    elif step.shape=='no': value={'ok':False}
                    elif step.shape=='identified': value={'ok':True,'name':'TEST ONLY','role':'owner_admin'}
                    elif step.shape=='me': value={'sub':people[step.actor]['id'],**{k:v for k,v in people[step.actor].items() if k!='id'}}
                    elif step.shape=='users': value=list(people.values())
                    elif step.shape=='disabled': value={'detail':'Staff PIN portal is disabled. Ask a manager to set a PIN.'}
                    else: value={'detail':'TEST ONLY refusal'}
                    if label in ('P03','P04','P05','P06','P07','P08'): assert data['pin']!='4826'
                seen.append(label)
                self.send_response(status);self.send_header('Content-Type','application/json')
                if status==429: self.send_header('Retry-After','60')
                self.end_headers();self.wfile.write(json.dumps(value).encode())
            except BaseException as error:
                errors.append(type(error).__name__);self.send_error(500)
        do_GET=handle_case;do_POST=handle_case
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    if tls_context is not None: server.socket=tls_context.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try: yield ('https' if tls_context is not None else 'http')+'://127.0.0.1:'+str(server.server_port),seen,errors
    finally: server.shutdown();server.server_close();thread.join(3);assert not thread.is_alive()


def test_complete_supervised_loopback_profile_and_replay_refusal(tmp_path):
    if os.name!='nt': return
    base=activation.prepare()
    with fixture_server(base) as (origin,seen,errors):
        profile=activation.prepare(origin=origin);bound=approval(profile,tmp_path)
        result=operator.execute_approved(profile,bound,actors(profile),evidence_directory=tmp_path,
            owner_reference=bound['ownerReference'],input_mode='fixture')
        assert result['status']=='passed', result
        assert result['cleanupConfirmed'] and result['evidenceClosureConfirmed'] and result['requestsCompleted']==21
        assert seen==list(activation.sequence(profile)) and not errors
        with pytest.raises(FileExistsError):
            operator.execute_approved(profile,bound,actors(profile),evidence_directory=tmp_path,
                owner_reference=bound['ownerReference'],input_mode='fixture')
        raw=next(tmp_path.glob('*.jsonl')).read_text()
        assert all(secret not in raw for secret in (operator.FICTIONAL_PASSWORD,'@example.invalid','Bearer','TEST-ONLY-owner'))
        assert '"pin"' not in raw and '"password"' not in raw and '"token"' not in raw


@pytest.mark.parametrize('trusted',[True,False])
def test_actual_loopback_tls_verification_isolated_ca_only(tmp_path,trusted):
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from ipaddress import ip_address
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'TEST ONLY loopback')])
    now=activation.engine.utc_now()
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1))
          .not_valid_after(now+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True)
          .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip_address('127.0.0.1'))]),critical=False)
          .sign(key,hashes.SHA256()))
    certificate=tmp_path/'fictional-ca.pem';private=tmp_path/'fictional-key.pem'
    certificate.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    server_tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);server_tls.load_cert_chain(certificate,private)
    with fixture_server(activation.prepare(),server_tls) as (origin,seen,errors):
        profile=activation.prepare(origin=origin);bound=approval(profile,tmp_path)
        ledger=activation.Journal(profile,bound,actors(profile),tmp_path)
        client=activation.rehearsal_client(ledger,tls_context=ssl.create_default_context(cafile=str(certificate)) if trusted else None)
        if trusted:
            value=asyncio.run(client.probe('P01',pin='4826'));ledger.result(value)
            assert value['outcome']=='passed' and seen==['P01'] and not errors
        else:
            with pytest.raises(activation.Held,match='request_failed'): asyncio.run(client.probe('P01',pin='4826'))
            assert not seen
        client.close();ledger.finish(cleanup_confirmed=True)


@pytest.mark.parametrize('override',['transport','tls','unsupervised'])
def test_hosted_factory_refuses_test_overrides_before_network(tmp_path,override,monkeypatch):
    profile=activation.prepare(mode='hosted',origin=activation.ORIGIN);bound=approval(profile,tmp_path)
    async def permit(_): pytest.fail('dispatch')
    cap=activation._Capability(activation._KEY,profile,bound,actors(profile),permit,lambda:None,
                               supervised=override!='unsupervised')
    monkeypatch.setattr(httpx,'AsyncClient',lambda **_:pytest.fail('network client'))
    args={'transport':httpx.MockTransport(lambda _:None)} if override=='transport' else {'tls_context':ssl.create_default_context()} if override=='tls' else {}
    with pytest.raises(activation.Held,match='supervised_production_transport_required'):
        activation._ApprovedTransport(cap,**args)


@pytest.mark.parametrize('roster,configured,roles',[(True,True,('owner','manager','staff')),
    (False,True,('owner',)),(False,False,('owner','staff'))])
def test_real_app_routes_with_approved_identity_bindings_and_variants(tmp_path,monkeypatch,roster,configured,roles):
    import server
    import staff_pin_security as security
    from test_staff_pin_security import Connection, Pool
    now=[1000.0]
    monkeypatch.setattr(security,'limiter',security.PinAttemptLimiter(tmp_path/'limiter.sqlite3',clock=lambda:now[0]))
    monkeypatch.setattr(server,'AUTH_REQUIRED',True);monkeypatch.setattr(server,'USE_PG',True)
    monkeypatch.setattr(server,'AUTH_SECRET','TEST-ONLY-activation-secret')
    profile=activation.prepare(roster=roster,pin_configured=configured,roles=roles);people=actors(profile)
    rows={actor['email']:{**actor,'password_hash':server._password_hash(operator.FICTIONAL_PASSWORD),
                         'created_at':activation.engine.utc_now()} for actor in people.values()}
    class Auxiliary:
        async def fetchrow(self,_,email): return rows.get(email)
        async def fetch(self,_): return list(rows.values())
    pool=Pool(Connection('4826' if configured else None))
    monkeypatch.setattr(server.db_auxiliary,'pool',lambda:Auxiliary())
    monkeypatch.setattr(server.db_pg,'pool',lambda:pool)
    async def no_activity(*args): pass
    monkeypatch.setattr(server,'_record_activity',no_activity)
    directory=tmp_path/'evidence';directory.mkdir()
    ledger=activation.Journal(profile,approval(profile,directory),people,directory)
    client=activation.rehearsal_client(ledger,transport=httpx.ASGITransport(app=server.app),clock=lambda:now[0])
    async def wait(seconds): now[0]+=seconds;await asyncio.sleep(0)
    async def emit(value): ledger.result(value)
    asyncio.run(activation.run_sequence(client,pin='4826',credentials={role:(actor['email'],operator.FICTIONAL_PASSWORD)
        for role,actor in people.items()},staff_id=MEMBER if roster and configured else None,emit=emit,wait=wait))
    result=ledger.finish(cleanup_confirmed=True,completed=True)
    assert result['status']=='passed' and result['clockMode']=='virtual' and result['securityAcceptance'] is False
    assert result['requestsCompleted']==len(activation.sequence(profile))<=21


def test_missing_roster_and_wrong_store_refuse(tmp_path):
    profile=activation.prepare();people=actors(profile);bound=approval(profile,tmp_path)
    ledger=activation.Journal(profile,bound,people,tmp_path)
    client=activation.rehearsal_client(ledger,transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'ok':True,'staff':[]})))
    with pytest.raises(activation.Held,match='probe_shape'): asyncio.run(client.probe('P01',pin='4826'))
    assert ledger.pending=='P01'
    assert not client._validate_me({'sub':people['manager']['id'],'email':people['manager']['email'],
        'role':'manager','locations':['rudds']},activation.engine.Session('TEST ONLY',people['manager']['id'],people['manager']['email'],'manager'))
    ledger.finish(cleanup_confirmed=True)


@pytest.mark.parametrize('field',['content-length','retry-after'])
def test_huge_numeric_headers_are_fixed_category_refusals(field):
    label='P01' if field=='content-length' else 'P08'
    value={'ok':True,'staff':[]} if label=='P01' else {'detail':'TEST ONLY'}
    response=httpx.Response(200 if label=='P01' else 429,json=value,headers={field:'1'*5000})
    client=activation.engine.LocalTransport('https://s1-fixture.invalid',approved=True,guard=lambda:None,
        stop_checks_at=activation.engine.utc_now()+timedelta(seconds=780),ends_at=activation.engine.utc_now()+timedelta(seconds=901),
        transport=httpx.MockTransport(lambda _:response))
    with pytest.raises(activation.Held): asyncio.run(client.probe(label,pin='4826'))


@pytest.mark.parametrize('stage',['initial_receipt','intent','result'])
def test_evidence_failure_consumes_attempt_and_disallows_further_dispatch(tmp_path,monkeypatch,stage):
    profile=activation.prepare();bound=approval(profile,tmp_path)
    original=activation.os.fsync;count=[0]
    fail_at={'initial_receipt':2,'intent':3,'result':4}[stage]
    def sync(fd):
        count[0]+=1
        if count[0]==fail_at: raise OSError('TEST ONLY private storage failure')
        return original(fd)
    monkeypatch.setattr(activation.os,'fsync',sync)
    if stage=='initial_receipt':
        with pytest.raises(activation.Held,match='initial_evidence_failed'):
            activation.Journal(profile,bound,actors(profile),tmp_path)
    else:
        journal=activation.Journal(profile,bound,actors(profile),tmp_path)
        with pytest.raises(activation.Held,match='evidence_write_failed'):
            journal.intent('P01')
            if stage=='result': journal.result({'request':'P01','outcome':'passed','httpStatus':200})
        assert journal.closed and journal.stream.closed
        with pytest.raises(activation.Held): journal.intent('P01')
    assert len(list(tmp_path.glob('*.claim')))==1
    with pytest.raises(FileExistsError): activation.Journal(profile,bound,actors(profile),tmp_path)


def test_copied_directory_and_mutated_private_bindings_do_not_rearm(tmp_path):
    profile=activation.prepare();people=actors(profile);bound=approval(profile,tmp_path)
    other=tmp_path/'other';other.mkdir()
    with pytest.raises(activation.Held): activation.Journal(profile,bound,people,other)
    assert not list(other.iterdir())
    journal=activation.Journal(profile,bound,people,tmp_path)
    people['owner']['id']='changed external record'
    assert journal.actors['owner']['id']!='changed external record'
    journal.actors['owner']['id']='changed inside binding'
    with pytest.raises(activation.Held,match='private_binding_changed'): journal.intent('P01')
    journal.finish(cleanup_confirmed=True)


@pytest.mark.parametrize('change',['quiet','commit','runtime'])
def test_preflight_is_bound_not_a_generic_approval(tmp_path,change):
    profile=activation.prepare();bound=approval(profile,tmp_path)
    if change=='quiet': bound['preflight']['quietConfirmed']=False
    elif change=='commit': bound['preflight']['apiCommit']='0'*40
    else: bound['preflight']['runtimeSha256']='0'*64
    with pytest.raises(activation.Held): activation.Journal(profile,bound,actors(profile),tmp_path)
    assert not list(tmp_path.iterdir())


def test_unexpected_result_fields_never_reach_evidence(tmp_path):
    profile=activation.prepare();journal=activation.Journal(profile,approval(profile,tmp_path),actors(profile),tmp_path)
    journal.intent('P01')
    with pytest.raises(activation.Held):
        journal.result({'request':'P01','outcome':'passed','httpStatus':200,'token':'TEST ONLY token'})
    journal.finish(cleanup_confirmed=True)
    assert 'TEST ONLY token' not in next(tmp_path.glob('*.jsonl')).read_text()


def test_invalid_public_profile_never_opens_private_binding_files(tmp_path,monkeypatch,capsys):
    reads=[]
    def read(file):
        reads.append(str(file))
        if str(file)=='profile.json': return {'mode':'hosted','origin':'https://outside.invalid'}
        pytest.fail('private binding read')
    monkeypatch.setattr(operator,'read_json',read)
    monkeypatch.setattr(sys,'argv',['operator','run-approved','--profile','profile.json','--approval','approval.json',
        '--actors','actors.json','--evidence',str(tmp_path),'--owner-reference','TEST_ONLY_OWNER_APPROVAL'])
    assert operator.main()==1 and reads==['profile.json']
    assert 'S1 held.' in capsys.readouterr().out
