"""Explicit S1 activation boundary. Import/prepare never reads credentials or sends HTTP.

Live use needs new exact owner approval, private evidence and the owned operator
supervisor. Tests and rehearsal are restricted to fictional/local endpoints.
"""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import MappingProxyType
from urllib.parse import urlsplit
from uuid import uuid4

import s1_request_transport as engine
import s1_resources as resource_observations

ROOT = Path(__file__).resolve().parents[2]
ORIGIN = 'https://jaymax-api.onrender.com'
FORMAT = 's1-http-activation-v1'
PREFLIGHT_SOURCE = 'owner_reported'
# Full 21-request bound even for reduced variants: quiet + cold P01 + other
# requests + maximum recovery wait + integrity/IPC/storage scheduling margin.
MIN_DISPATCH_SECONDS = 65 + 90 + 20 * 6 + 62 + 60
_KEY = object()
Held = engine.Held
ALL_ORDER = ('P01','P02','L01','L02','L03', *[f'P{i:02}' for i in range(3,10)],
             *[f'R{i:02}' for i in range(1,7)], 'P10','P11','P12')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, stderr=subprocess.DEVNULL, timeout=10)


@lru_cache(maxsize=16)
def app_proof(commit):
    def app_tree(ref):
        rows = git('ls-tree','-r',ref,'--','backend','migrations','supabase','render.yaml').decode().splitlines()
        return {name: meta.split()[2] for meta,name in (row.split('\t',1) for row in rows)
                if not name.startswith('backend/tests/') and '__pycache__' not in name}
    tree = app_tree(commit)
    refs = git('rev-list','--first-parent','-24',commit).decode().splitlines()
    return {'sourceCommit':commit, 'apiRuntimeSha256':digest(tree),
            'equivalentApiCommits':[ref for ref in refs if app_tree(ref)==tree]}


def execution_pins():
    result = {}
    files = set((ROOT/'tools/ops').glob('*.py')) | set((ROOT/'backend').glob('*.py'))
    files |= {ROOT/'backend/requirements.txt', ROOT/'render.yaml'}
    for file in sorted(files):
        if file.is_symlink() or not file.resolve().is_relative_to(ROOT): raise Held('source_redirected')
        result['source:'+file.relative_to(ROOT).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
    for name in ('httpx','httpcore','h11','anyio','certifi','idna','sniffio','typing_extensions'):
        module = importlib.import_module(name)
        file = Path(module.__file__)
        paths = sorted(file.parent.rglob('*.py')) if file.name == '__init__.py' else [file]
        if name == 'certifi': paths.append(Path(module.where()))
        for path in paths:
            if path.is_symlink(): raise Held('runtime_redirected')
            result['runtime:'+name+':'+path.relative_to(file.parent).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    result['pythonExecutable'] = hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
    result['pythonVersion'] = sys.version
    return result


def _local_origin(origin):
    if origin == 'https://s1-fixture.invalid': return True
    try:
        value = urlsplit(origin)
        return (value.scheme in ('http','https') and value.hostname=='127.0.0.1'
                and value.port is not None and 1024 <= value.port <= 65535
                and origin == value.scheme+'://127.0.0.1:'+str(value.port))
    except (ValueError, TypeError, AttributeError): return False


def prepare(*, mode='rehearsal', origin='https://s1-fixture.invalid', roles=engine.ROLES,
            roster=True, pin_configured=True, attempt_id=None, real_time_resources=False,
            operator_start_floor_mib=None):
    roles = list(roles)
    attempt_id = attempt_id or uuid4().hex
    if (mode not in ('rehearsal','hosted') or type(real_time_resources) is not bool
            or real_time_resources and mode!='rehearsal'
            or operator_start_floor_mib is not None and (type(operator_start_floor_mib) is not int
                                                        or not 1024 <= operator_start_floor_mib <= 8192)
            or type(roster) is not bool or type(pin_configured) is not bool
            or not roles or roles[0]!='owner' or roles != [role for role in engine.ROLES if role in roles]
            or not re.fullmatch('[a-f0-9]{32}',attempt_id)
            or (origin!=ORIGIN if mode=='hosted' else not _local_origin(origin))):
        raise Held('profile_invalid')
    return {'format':FORMAT,'mode':mode,'origin':origin,'attemptId':attempt_id,
            **({'rehearsalResources':'real'} if real_time_resources else {}),
            **({'operatorStartFloorMiB':operator_start_floor_mib} if operator_start_floor_mib is not None else {}),
            'clock':'real' if mode=='hosted' or real_time_resources else 'virtual',
            'roles':roles,'roster':roster,'pinConfigured':pin_configured,
            'limits':{'attempts':21,'workSeconds':780,'totalSeconds':900,'cleanupSeconds':120,
                      'quietSeconds':65,'responseBytes':65536,'automaticRetries':0},
            'proof':app_proof(git('rev-parse','HEAD').decode().strip()),
            'pins':execution_pins(), 'executionApproved':False}


def check_profile(value):
    try:
        expected = prepare(mode=value['mode'], origin=value['origin'], roles=value['roles'],
            roster=value['roster'],pin_configured=value['pinConfigured'],attempt_id=value['attemptId'],
            real_time_resources=value.get('rehearsalResources')=='real',
            operator_start_floor_mib=value.get('operatorStartFloorMiB'))
        if value != expected: raise ValueError
    except (KeyError, TypeError, ValueError):
        raise Held('profile_or_sources_changed') from None
    return digest(value)


def steps(profile):
    result = dict(engine.STEPS)
    if not profile['pinConfigured']:
        result = {key:value for key,value in result.items() if not key.startswith('P') or key in ('P01','P12')}
        result['P01'] = engine.Step('POST',engine.VERIFY,'anonymous',403,'disabled')
    elif not profile['roster']:
        for label in ('P02','P11'): result.pop(label)
        for label in ('P04','P06'): result[label] = engine.Step('POST',engine.VERIFY,'anonymous',200,'no')
    for index,role in enumerate(engine.ROLES):
        if role not in profile['roles']:
            for label in (f'R{index*2+1:02}',f'R{index*2+2:02}'): result.pop(label)
    return MappingProxyType(result)


def sequence(profile):
    routes = steps(profile)
    return tuple(label for label in ALL_ORDER if label in routes or
                 (label.startswith('L') and engine.ROLES[int(label[1:])-1] in profile['roles']))


def actor_check(actors, profile):
    if not isinstance(actors,dict) or set(actors)!=set(profile['roles']): raise Held('actor_bindings_invalid')
    subjects = set()
    for role,actor in actors.items():
        if (not isinstance(actor,dict) or set(actor)!={'id','email','role','locations'}
                or actor['role']!=role or not isinstance(actor['id'],str) or not actor['id']
                or actor['id'] in subjects or not isinstance(actor['email'],str)
                or actor['email']!=actor['email'].strip().lower() or '@' not in actor['email']
                or not isinstance(actor['locations'],list) or not all(isinstance(v,str) for v in actor['locations'])
                or len(set(actor['locations']))!=len(actor['locations'])
                or (role!='owner' and 'berts' not in actor['locations'])):
            raise Held('actor_bindings_invalid')
        subjects.add(actor['id'])


def stamp(value):
    try:
        result = datetime.fromisoformat(value)
        if result.utcoffset() is None: raise ValueError
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError): raise Held('approval_deadline_invalid') from None


def check_approval(profile, approval, actors, directory):
    sha = check_profile(profile)
    actor_check(actors,profile)
    try:
        if set(approval)!={'format','profileSha256','actorsSha256','attemptId','approved','ownerReference','rosterId',
                          'startsAt','stopChecksAt','endsAt','evidenceDirectory','preflight'}:
            raise ValueError
        if (approval['format']!=FORMAT or approval['approved'] is not True or approval['profileSha256']!=sha
                or approval['actorsSha256']!=digest(actors) or approval['attemptId']!=profile['attemptId']
                or not re.fullmatch('[a-zA-Z0-9_-]{1,80}',approval['ownerReference'])
                or approval['evidenceDirectory']!=str(Path(directory).resolve())): raise ValueError
        if profile['roster'] and profile['pinConfigured']:
            if not isinstance(approval['rosterId'],str) or not re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}',approval['rosterId']): raise ValueError
        elif approval['rosterId'] is not None: raise ValueError
        start,stop,end = (stamp(approval[key]) for key in ('startsAt','stopChecksAt','endsAt'))
        if not (start<=engine.utc_now()<stop and (stop-start).total_seconds()==780
                and (end-start).total_seconds()==900): raise ValueError
        proof = approval['preflight']
        if (set(proof)!={'observedAt','apiCommit','runtimeSha256','quietConfirmed'}
                or proof['apiCommit'] not in profile['proof']['equivalentApiCommits']
                or proof['runtimeSha256']!=profile['proof']['apiRuntimeSha256']
                or proof['quietConfirmed'] is not True
                or not 0 <= (engine.utc_now()-stamp(proof['observedAt'])).total_seconds() <= 1800): raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError): raise Held('exact_approval_required') from None
    return stop,end


def evidence_environment(profile, directory, *, resource_monitor=None):
    """Read-only launch checks; collecting input never creates a claim or file."""
    directory = Path(directory)
    resource_monitor=resource_observations.select(profile,resource_monitor)
    if not directory.is_dir() or any(p.is_symlink() or p.is_junction() for p in (directory,*directory.parents)):
        raise Held('evidence_directory_invalid')
    if resource_observations.enabled(profile):
        resource_monitor.check(start=True)
    if profile['mode']=='hosted':
        from read_only_probe import private_path, resources
        if git('status','--porcelain'): raise Held('clean_reviewed_checkout_required')
        if not sys.flags.isolated: raise Held('isolated_runtime_required')
        private_path(directory,directory=True)


def dispatch_window(profile, approval, actors, directory, *, resource_monitor=None):
    stop,end = check_approval(profile,approval,actors,directory)
    if 'operatorStartFloorMiB' in profile:
        from read_only_probe import resources, Held as ResourceHeld
        monitor=resource_observations.select(profile,resource_monitor)
        try:
            observed=monitor.check(start=True) if monitor.active else resources(start=True)
        except ResourceHeld:
            raise Held('resource_headroom_insufficient') from None
        if observed['freeBytes'] < profile['operatorStartFloorMiB'] * 2**20:
            raise Held('resource_headroom_insufficient')
    if (stop-engine.utc_now()).total_seconds() < MIN_DISPATCH_SECONDS:
        raise Held('window_insufficient_before_claim')
    return stop,end


def timing_ms(value):
    if type(value) not in (float,int) or not math.isfinite(value) or not 0 <= value <= 900000:
        raise Held('integrity_timing_invalid')
    return round(value,3)


class Journal:
    """Exclusive, flushed append-only metadata; an incomplete intent is consumed."""
    def __init__(self, profile, approval, actors, directory, *, require_dispatch_window=False,
                 resource_monitor=None, on_claim_start=None):
        self.stop,self.end = check_approval(profile,approval,actors,directory)
        self.profile,self.approval,self.actors = deepcopy(profile),deepcopy(approval),deepcopy(actors)
        self._approval_sha,self._actors_sha = digest(approval),digest(actors)
        self.resource_monitor=resource_observations.select(profile,resource_monitor)
        evidence_environment(profile,directory,resource_monitor=self.resource_monitor)
        directory = Path(directory)
        if profile['mode']=='hosted':
            from read_only_probe import _fresh_private_file
            opener = _fresh_private_file
        else:
            opener = lambda p: p.open('xb')
        if require_dispatch_window:
            self.stop,self.end=dispatch_window(profile,approval,actors,directory,resource_monitor=self.resource_monitor)
        # Fixed ID + bound directory: never replace an existing or partial claim.
        claim = directory/('s1-'+profile['attemptId']+'.claim')
        if on_claim_start is not None: on_claim_start()
        with opener(claim) as stream:
            stream.write((digest(approval)+'\n').encode());stream.flush();os.fsync(stream.fileno())
        self.resource_monitor.set_phase('post_claim_setup')
        self.stream = opener(directory/('s1-'+profile['attemptId']+'.jsonl'))
        self.order,self.index,self.pending = sequence(profile),0,None
        self.integrity_checks = []
        self.closed = False
        claimed={'event':'claimed','profileSha256':digest(profile)}
        if require_dispatch_window: claimed['credentialEntryRoles']=list(profile['roles'])
        try: self._append(claimed)
        except BaseException:
            self.stream.close()
            raise Held('initial_evidence_failed') from None

    def post_claim_check(self):
        # The controller must retain this journal before a resource refusal can
        # throw, so it can close the consumed claim without permitting dispatch.
        self.guard()

    def _append(self,value):
        try:
            self.stream.write((json.dumps(value,separators=(',',':'))+'\n').encode())
            self.stream.flush();os.fsync(self.stream.fileno())
        except BaseException:
            self.closed=True
            self.stream.close()
            raise Held('evidence_write_failed') from None

    def guard(self):
        if self.closed or engine.utc_now()>=self.stop: raise Held('window_closed')
        if digest(self.approval)!=self._approval_sha or digest(self.actors)!=self._actors_sha:
            raise Held('private_binding_changed')
        self.resource_monitor.check()

    def intent(self,label,*,worker_integrity_ms=None):
        self.guard()
        if worker_integrity_ms is not None: worker_integrity_ms=timing_ms(worker_integrity_ms)
        started=time.perf_counter();check_profile(self.profile)
        elapsed=timing_ms((time.perf_counter()-started)*1000)
        if self.pending or self.index>=len(self.order) or label!=self.order[self.index]: raise Held('dispatch_order_invalid')
        measurement={'request':label,'controllerMilliseconds':elapsed,'workerMilliseconds':worker_integrity_ms}
        self._append({'event':'intent','request':label,'integrityCheck':measurement})
        self.integrity_checks.append(measurement)
        self.pending=label

    def result(self,value):
        self.guard()
        if (not isinstance(value,dict) or set(value)-{'request','outcome','httpStatus','retryAfterSeconds'}
                or value.get('request')!=self.pending or value.get('outcome')!='passed'):
            raise Held('worker_result_invalid')
        expected = steps(self.profile).get(self.pending)
        fields={'request','outcome','httpStatus'} | ({'retryAfterSeconds'} if expected and expected.shape=='throttled' else set())
        if set(value)!=fields: raise Held('worker_result_invalid')
        if (type(value.get('httpStatus')) is not int or value['httpStatus']!=(expected.status if expected else 200)
                or ('retryAfterSeconds' in value and (type(value['retryAfterSeconds']) is not int
                    or not 1 <= value['retryAfterSeconds'] <= 61))): raise Held('worker_result_invalid')
        self._append({'event':'result',**value});self.pending=None;self.index+=1

    def finish(self, *, cleanup_confirmed, completed=False, failure_diagnostics=None, resource_observations=None):
        passed = completed is True and cleanup_confirmed is True and self.pending is None and self.index==len(self.order)
        diagnostic = {}
        try:
            if failure_diagnostics is not None:
                from s1_failure import validate_summary
                diagnostic['failureDiagnostics']=validate_summary(failure_diagnostics,requests=self.order)
            if resource_observations is not None:
                from s1_resources import validate_pair, quiet_gate
                diagnostic['resourceObservations']=validate_pair(resource_observations)
                diagnostic['quietWaitGate']=quiet_gate(diagnostic['resourceObservations'])
            self._append({'event':'closed','status':'passed' if passed else 'held','cleanupConfirmed':cleanup_confirmed is True,**diagnostic})
        finally: self.closed=True;self.stream.close()
        return {'status':'passed' if passed else 'held','cleanupConfirmed':cleanup_confirmed is True,
                'requestsCompleted':self.index,'requestPending':self.pending is not None,
                'clockMode':self.profile['clock'],'securityAcceptance':False,
                'claimStatus':'created','preflightSource':PREFLIGHT_SOURCE,
                'integrityChecks':deepcopy(self.integrity_checks),
                'omittedRequests':[label for label in ALL_ORDER if label not in self.order],
                'serverSideRevocation':'not_available','sessionTtlSecondsDefault':28800}


class _Capability:
    def __init__(self,key,profile,approval,actors,permit,guard,*,supervised=False):
        if key is not _KEY: raise Held('capability_invalid')
        self.profile,self.approval,self.actors=profile,approval,actors
        self.permit,self.guard,self.supervised=permit,guard,supervised
    def __repr__(self): return '<private S1 execution capability>'


class _ApprovedTransport(engine.LocalTransport):
    def __init__(self, capability, *, transport=None, tls_context=None, clock=None):
        if type(capability) is not _Capability: raise Held('capability_invalid')
        self.cap=capability;self.tls_context=tls_context
        profile=capability.profile
        if profile['mode']=='hosted' and (not capability.supervised or transport is not None or tls_context is not None):
            raise Held('supervised_production_transport_required')
        super().__init__(profile['origin'],approved=True,guard=capability.guard,
            ends_at=stamp(capability.approval['endsAt']),stop_checks_at=stamp(capability.approval['stopChecksAt']),
            transport=transport,**({'clock':clock} if clock else {}))
        self._steps=steps(profile)
        self.last_integrity_ms=None

    def _valid_pin_input(self,label,pin):
        if not self.cap.profile['pinConfigured']:
            return label=='P01' and pin=='' and self._steps[label].shape=='disabled'
        return super()._valid_pin_input(label,pin)

    def _check_destination(self,origin,transport):
        if origin!=self.cap.profile['origin']: raise Held('target_binding_invalid')
        if self.cap.profile['mode']=='hosted':
            if origin!=ORIGIN or transport is not None: raise Held('target_binding_invalid')
        elif origin.startswith('https://127.0.0.1:') and _local_origin(origin):
            if transport is not None: raise Held('rehearsal_transport_invalid')
        else: engine.LocalTransport._check_destination(origin,transport)

    def _tls_verify(self):
        return self.tls_context if self.cap.profile['mode']=='rehearsal' and self.tls_context is not None else True

    def _validate_login(self,user):
        expected=self.cap.actors[user['role']]
        if any(user.get(key)!=expected[key] for key in ('id','email','role','locations')):
            raise Held('approved_actor_mismatch')

    def _validate_me(self,value,session):
        actor=self.cap.actors[session.role]
        return (super()._validate_me(value,session) and value.get('locations')==actor['locations']
                and value.get('sub')==actor['id'])

    def _validate_roster(self,value):
        if not self.cap.profile['roster']: return True
        return any(row['id']==self.cap.approval['rosterId'] and row['role']=='owner_admin'
                   and row['active'] is True for row in value['staff'])

    async def _send(self,label,step,body=None,session=None):
        self._recovery_gate(label)
        if label in self._used: raise Held('request_already_claimed')
        started=time.perf_counter();check_profile(self.cap.profile)
        self.last_integrity_ms=timing_ms((time.perf_counter()-started)*1000)
        await self.cap.permit(label)
        return await super()._send(label,step,body,session)


def rehearsal_client(journal, *, transport=None, tls_context=None, clock=None):
    if journal.profile['mode']!='rehearsal': raise Held('supervised_operator_required')
    async def permit(label): journal.intent(label,worker_integrity_ms=client.last_integrity_ms)
    client = _ApprovedTransport(_Capability(_KEY,journal.profile,journal.approval,journal.actors,
        permit,journal.guard),transport=transport,tls_context=tls_context,clock=clock)
    return client


async def run_sequence(client, *, pin, credentials, staff_id=None, emit, wait=asyncio.sleep,
                       quiet_seconds=65, close_on_exit=True):
    """No hidden HTTP calls. Caller supplies transient input; worker owns cleanup."""
    profile=client.cap.profile
    if quiet_seconds!=65: raise Held('quiet_interval_invalid')
    if type(close_on_exit) is not bool or not close_on_exit and not client.cap.supervised:
        raise Held('supervised_operator_required')
    try:
        if not client._valid_pin_input('P01',pin): raise Held('pin_input')
        await wait(65)
        client._check()
        wrong_pin = None
        for label in sequence(profile):
            client._check()
            if label.startswith('L'):
                role=engine.ROLES[int(label[1:])-1]
                email,password=credentials[role]
                await client.login(role,email,password)
                value={'request':label,'outcome':'passed','httpStatus':200}
            else:
                if label=='P03': wrong_pin=('0' if pin[0]!='0' else '1')+pin[1:]
                if label=='P10':
                    delay=max(0,client._recovery_at-client._clock())
                    if delay: await wait(delay)
                step=client._steps[label]
                args={}
                if step.path in (engine.VERIFY,engine.IDENTIFY):
                    args['pin']=wrong_pin if label in ('P03','P04','P05','P06','P07','P08') else pin
                    if step.path==engine.IDENTIFY: args['staff_id']=staff_id
                value=await client.probe(label,**args)
            await emit(value)
    finally:
        if close_on_exit: client.close()
