"""Explicit S1 operator launcher. Prepare/check are inert; live execution is opt-in.

No real credentials are used by rehearsal. Never run approved-hosted mode without
a new exact owner approval. No app/Render/Supabase setup is performed here.
"""
import argparse
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import time
import re

if sys.flags.isolated:
    sys.path.insert(0,str(Path(__file__).resolve().parent))

import s1_activation as activation
from s1_console import console_input
from s1_process import ProcessHeld, receive, send, supervise
import s1_failure as failure
import s1_resources as observations
from read_only_probe import Held as ResourceHeld

FICTIONAL_PASSWORD = 'TEST-ONLY-S1-password-4826'
MAX_FIELD_ENTRIES = 3


async def guarded_wait(seconds, guard, *, clock=time.monotonic, sleep=asyncio.sleep):
    until=clock()+seconds
    while clock()<until:
        guard()
        await sleep(min(.05,max(0,until-clock())))
    guard()


def read_json(path):
    path=Path(path)
    if any(p.is_symlink() or p.is_junction() for p in (path,*path.parents)):
        raise activation.Held('input_path_redirected')
    with path.open('rb') as stream: raw=stream.read(512*1024+1)
    if len(raw)>512*1024: raise activation.Held('input_file_bound')
    try:
        return json.loads(raw,object_pairs_hook=activation.engine.unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError,UnicodeError,RecursionError): raise activation.Held('input_json_invalid') from None


def collect_inputs(profile,actors,*,read,guard):
    """Network-free, bounded local re-entry; never return values across IPC."""
    prefix='FICTIONAL ONLY ' if profile['mode']=='rehearsal' else 'APPROVED S1 '
    def field(label,valid):
        for index in range(MAX_FIELD_ENTRIES):
            guard()
            value=read(prefix+label+' (hidden, entry '+str(index+1)+'/3): ')
            guard()
            if isinstance(value,str) and valid(value): return value
            value=None
        raise activation.Held('local_input_entries_exhausted')
    pin='';credentials={}
    try:
        if profile['pinConfigured']:
            pin=field("Bert's PIN",lambda v: re.fullmatch('[0-9]{4,8}',v) is not None
                and (profile['mode']!='rehearsal' or v=='4826'))
        for role in profile['roles']:
            email=field(role+' account holder email',lambda v:len(v)<=320 and v==actors[role]['email']
                and (profile['mode']!='rehearsal' or v.endswith('@example.invalid')))
            password=field(role+' account holder password',lambda v:0<len(v)<=1024
                and (profile['mode']!='rehearsal' or v==FICTIONAL_PASSWORD))
            credentials[role]=(email,password)
            email=password=None
        return pin,credentials
    except BaseException:
        credentials.clear();pin=None
        raise


def _operator_worker(channel,profile,approval,actors,input_mode):
    monitor=observations.Monitor(observations.enabled(profile))
    def metadata(): return {'resourceSummary':monitor.snapshot()} if monitor.active else {}
    current = failure.position('worker_profile')
    def stage(name, request=None):
        nonlocal current
        current = failure.position(name, request)
        monitor.set_phase(observations.phase(name))
        send(channel, {'event':'stage', **current, **metadata()})
        if receive(channel) != {'stage_recorded':True}:
            raise activation.Held('dispatch_not_granted')
    async def permit(label):
        await asyncio.to_thread(stage, 'request', label)
        send(channel,{'event':'permit','request':label,'integrityMilliseconds':client.last_integrity_ms})
        answer=await asyncio.to_thread(receive,channel)
        if answer!={'grant':label}: raise activation.Held('dispatch_not_granted')
    def guard():
        if activation.engine.utc_now()>=activation.stamp(approval['stopChecksAt']):
            raise activation.Held('window_closed')
        try: monitor.check()
        except ResourceHeld: raise activation.Held('resource_guard_failed') from None
    async def emit(value):
        send(channel,{'event':'result','value':value})
        if await asyncio.to_thread(receive,channel)!={'continue':True}:
            raise activation.Held('result_not_acknowledged')
    credentials={};pin=None;client=None;primary=None;cleanup_failure=None
    try:
        stage('worker_profile')
        activation.check_profile(profile)
        stage('worker_approval')
        activation.check_approval(profile,approval,actors,approval['evidenceDirectory'])
        monitor.check(start=True)
        stage('worker_input')
        if input_mode=='fixture':
            if profile['mode']!='rehearsal' or any(not a['email'].endswith('@example.invalid') for a in actors.values()):
                raise activation.Held('fictional_inputs_required')
            pin='4826' if profile['pinConfigured'] else ''
            credentials={role:(actor['email'],FICTIONAL_PASSWORD) for role,actor in actors.items()}
        else:
            pin,credentials=collect_inputs(profile,actors,read=console_input,guard=guard)
        stage('worker_dispatch_wait');guard()
        send(channel,{'event':'inputs_ready'})
        if receive(channel)!={'start_dispatch':True}: raise activation.Held('dispatch_not_granted')
        monitor.set_phase('post_claim_setup')
        stage('worker_dispatch_check')
        guard()
        stage('worker_transport')
        cap=activation._Capability(activation._KEY,profile,approval,actors,permit,guard,supervised=True)
        virtual=[time.monotonic()]
        client=activation._ApprovedTransport(cap,clock=(lambda:virtual[0]) if profile['clock']=='virtual' else None)
        async def wait(seconds):
            await asyncio.to_thread(stage, 'quiet_wait' if seconds==65 else 'recovery_wait',
                                    None if seconds==65 else 'P10')
            if profile['clock']=='virtual':
                virtual[0]+=seconds;await asyncio.sleep(0)
            else:
                await guarded_wait(seconds,guard)
        stage('worker_sequence')
        asyncio.run(activation.run_sequence(client,pin=pin,credentials=credentials,
                    staff_id=approval['rosterId'],emit=emit,wait=wait,close_on_exit=False))
    except BaseException as error:
        if monitor.failed: error=activation.Held('resource_guard_failed')
        primary = failure.describe(error, **current, trusted_types=(activation.Held, ProcessHeld))
    finally:
        try:
            if primary is None: stage('worker_cleanup')
        except BaseException as error:
            cleanup_failure = failure.describe(error, 'worker_cleanup', trusted_types=(activation.Held, ProcessHeld))
        try:
            if client: client.close()
        except BaseException as error:
            if cleanup_failure is None:
                cleanup_failure = failure.describe(error, 'worker_cleanup', trusted_types=(activation.Held, ProcessHeld))
        finally:
            credentials.clear();pin=None
            monitor.observe_cleanup()
    if monitor.active:
        send(channel,{'event':'resource_summary',**metadata()})
        if receive(channel)!={'resources_recorded':True}:raise ProcessHeld('worker_message_invalid')
    if primary is not None or cleanup_failure is not None:
        send(channel, {'event':'failure', 'primaryFailure':primary, 'cleanupFailure':cleanup_failure})
        raise ProcessHeld('worker_held')
    send(channel,{'event':'done'})


def execute_approved(profile,approval,actors,*,evidence_directory,owner_reference,input_mode='terminal'):
    if owner_reference!=approval.get('ownerReference') or input_mode not in ('terminal','fixture'):
        raise activation.Held('explicit_operator_attestation_required')
    if profile.get('mode')=='hosted' and input_mode!='terminal':
        raise activation.Held('protected_terminal_required')
    profile,approval,actors=deepcopy(profile),deepcopy(approval),deepcopy(actors)
    monitor=observations.Monitor(observations.enabled(profile))
    stop,_=activation.check_approval(profile,approval,actors,evidence_directory)
    try:
        activation.evidence_environment(profile,evidence_directory,resource_monitor=monitor)
    except ResourceHeld as error:
        monitor.observe_cleanup()
        detail=( {**failure.position('controller_evidence'),'reason':'resource_guard_failed','errorType':'Held'}
                 if monitor.failed else failure.describe(error,'controller_evidence',trusted_types=(ResourceHeld,)))
        resource_pair={'version':observations.VERSION,'supervisor':monitor.snapshot(),'worker':None}
        return {'status':'held','cleanupConfirmed':True,'evidenceClosureConfirmed':True,
            'claimStatus':'not_created','requestsCompleted':0,'securityAcceptance':False,
            'preflightSource':activation.PREFLIGHT_SOURCE,
            'failureDiagnostics':failure.validate_summary({'version':1,'workerPosition':None,
                'controllerStage':'controller_evidence','primaryFailure':detail,
                'workerCleanupFailure':None,'supervisorFailure':None,'supervisorCleanupFailure':None,'closureFailure':None}),
            **({'resourceObservations':resource_pair,'quietWaitGate':observations.quiet_gate(resource_pair)}
               if monitor.active else {})}
    claim=Path(evidence_directory)/('s1-'+profile['attemptId']+'.claim')
    if claim.exists(): raise FileExistsError('attempt_already_claimed')
    binding=activation.digest([profile,approval,actors])
    journal=None
    state={'inputsReady':False,'claimStarted':False,'workerPosition':None,'stageCount':0,
           'controllerStage':'controller_guard','primaryFailure':None,'workerCleanupFailure':None,
           'supervisorFailure':None,'supervisorCleanupFailure':None,'closureFailure':None,'workerReported':False,
           'workerResources':None,'resourceFinal':False}
    cleanup=False;failed=False;uncertain_writer=False
    def claim_started():state['claimStarted']=True
    def describe(error, stage):
        if type(error) is ResourceHeld and (stage=='controller_guard' or monitor.failed):
            return {**failure.position(stage),'reason':'resource_guard_failed','errorType':'Held'}
        return failure.describe(error, stage, trusted_types=(activation.Held, ProcessHeld, ResourceHeld))
    def guard():
        try:
            if activation.digest([profile,approval,actors])!=binding: raise activation.Held('private_binding_changed')
            if activation.engine.utc_now()>=stop: raise activation.Held('window_closed')
            if journal is not None: journal.guard()
            else: monitor.check()
        except BaseException as error:
            if state['primaryFailure'] is None: state['primaryFailure']=describe(error,'controller_guard')
            raise
    def handle_event(value):
        nonlocal journal
        if type(value) is not dict: raise ProcessHeld('worker_message_invalid')
        if value.get('event')=='resource_summary' and set(value)!={'event','resourceSummary'}:
            raise ProcessHeld('worker_message_invalid')
        if state['resourceFinal'] and value.get('event') not in ('failure','done'):
            raise ProcessHeld('worker_message_invalid')
        if profile.get('rehearsalResources')=='real':
            if (value.get('event')=='stage' and 'resourceSummary' not in value
                    or value.get('event') in ('failure','done') and not state['resourceFinal']):
                raise ProcessHeld('worker_message_invalid')
        if 'resourceSummary' in value:
            if not monitor.active or value.get('event') not in ('stage','resource_summary'):
                raise ProcessHeld('worker_message_invalid')
            try: state['workerResources']=observations.validate(value['resourceSummary'],state['workerResources'])
            except ValueError: raise ProcessHeld('worker_message_invalid') from None
            value={k:v for k,v in value.items() if k!='resourceSummary'}
        if value=={'event':'resource_summary'}:
            if not monitor.active or state['workerResources'] is None:raise ProcessHeld('worker_message_invalid')
            state['resourceFinal']=True
            return {'resources_recorded':True}
        state['controllerStage']='controller_message'
        if set(value)=={'event','stage','request'} and value['event']=='stage':
            try: pos=failure.position(value['stage'],value['request'])
            except ValueError: raise ProcessHeld('worker_message_invalid') from None
            before=('worker_profile','worker_approval','worker_input','worker_dispatch_wait')
            after=('worker_dispatch_check','worker_transport','worker_sequence','quiet_wait','recovery_wait','request','worker_cleanup')
            if (state['stageCount']>=64 or pos['stage'] not in (before if journal is None else after)
                    or pos['request'] is not None and pos['request'] not in activation.sequence(profile)):
                raise ProcessHeld('worker_message_invalid')
            if pos['stage'] in ('request','recovery_wait'):
                if (journal.pending is not None or journal.index>=len(journal.order)
                        or journal.order[journal.index]!=pos['request']):
                    raise ProcessHeld('worker_message_invalid')
            elif journal is not None and pos['stage']!='worker_cleanup' and (journal.index or journal.pending):
                raise ProcessHeld('worker_message_invalid')
            if pos['stage']=='worker_cleanup' and (journal.pending or journal.index!=len(journal.order)):
                raise ProcessHeld('worker_message_invalid')
            state['workerPosition']=pos;state['stageCount']+=1
            monitor.set_phase(observations.phase(pos['stage']))
            return {'stage_recorded':True}
        if set(value)=={'event','primaryFailure','cleanupFailure'} and value['event']=='failure':
            try:
                primary=(failure.validate(value['primaryFailure'],requests=activation.sequence(profile))
                         if value['primaryFailure'] is not None else None)
                worker_cleanup=(failure.validate(value['cleanupFailure'],requests=activation.sequence(profile))
                                if value['cleanupFailure'] is not None else None)
            except ValueError: raise ProcessHeld('worker_message_invalid') from None
            if (state['workerReported'] or primary is None and worker_cleanup is None
                    or primary is not None and {k:primary[k] for k in ('stage','request')}!=state['workerPosition']
                    or primary is None and worker_cleanup is not None and state['workerPosition']!=failure.position('worker_cleanup')
                    or worker_cleanup is not None and (worker_cleanup['stage']!='worker_cleanup' or worker_cleanup['request'] is not None)):
                raise ProcessHeld('worker_message_invalid')
            state['workerReported']=True
            if state['primaryFailure'] is None: state['primaryFailure']=primary
            state['workerCleanupFailure']=worker_cleanup
            raise ProcessHeld('worker_held')
        if value=={'event':'held'}: return
        if value=={'event':'inputs_ready'} and not state['inputsReady'] and journal is None:
            state['controllerStage']='controller_claim'
            monitor.set_phase('pre_claim')
            state['inputsReady']=True
            guard()
            activation.dispatch_window(profile,approval,actors,evidence_directory,resource_monitor=monitor)
            journal=activation.Journal(profile,approval,actors,evidence_directory,require_dispatch_window=True,
                                      resource_monitor=monitor,on_claim_start=claim_started)
            return {'start_dispatch':True}
        if journal is None: raise ProcessHeld('worker_message_invalid')
        if value=={'event':'done'} and journal.pending is None and journal.index==len(journal.order): return
        if set(value)=={'event','request','integrityMilliseconds'} and value['event']=='permit':
            state['controllerStage']='controller_intent'
            journal.intent(value['request'],worker_integrity_ms=activation.timing_ms(value['integrityMilliseconds']))
            return {'grant':value['request']}
        if set(value)=={'event','value'} and value['event']=='result':
            state['controllerStage']='controller_result'
            journal.result(value['value']);return {'continue':True}
        raise ProcessHeld('worker_message_invalid')
    def event(value):
        try: return handle_event(value)
        except BaseException as error:
            if not state['workerReported'] and state['primaryFailure'] is None:
                state['primaryFailure']=describe(error,state['controllerStage'])
            raise
    def diagnostics():
        return failure.validate_summary({'version':1,'workerPosition':state['workerPosition'],
            'controllerStage':state['controllerStage'],**{key:state[key] for key in
            ('primaryFailure','workerCleanupFailure','supervisorFailure','supervisorCleanupFailure','closureFailure')}},
            requests=activation.sequence(profile))
    def resource_metadata():
        if not monitor.active: return {}
        pair=observations.validate_pair(
            {'version':observations.VERSION,'supervisor':monitor.snapshot(),'worker':state['workerResources']})
        return {'resourceObservations':pair,'quietWaitGate':observations.quiet_gate(pair)}
    try:
        outcome=supervise(_operator_worker,(profile,approval,actors,input_mode),on_event=event,
            guard=guard,seconds=max(.001,(stop-activation.engine.utc_now()).total_seconds()))
        cleanup=outcome['ownedCleanupConfirmed']
    except BaseException as error:
        failed=True
        cleanup=getattr(error,'ownedCleanupConfirmed',False) is True
        for attr,key in (('supervisorFailure','supervisorFailure'),('cleanupFailure','supervisorCleanupFailure')):
            value=getattr(error,attr,None)
            if value is not None:
                try: state[key]=failure.validate(value,requests=activation.sequence(profile))
                except ValueError: state[key]=describe(RuntimeError(),'unknown')
        if state['primaryFailure'] is None and not state['workerReported']:
            state['primaryFailure']=state['supervisorFailure'] or describe(error,state['controllerStage'])
        # Writer may still be stalled: never race another write or call it closed.
        uncertain_writer=type(error) is ProcessHeld and BaseException.args.__get__(error)==('controller_callback_unconfirmed',)
    monitor.observe_cleanup()
    if uncertain_writer:
        return {'status':'held','cleanupConfirmed':False,'evidenceClosureConfirmed':False,
                'claimStatus':'unconfirmed','preflightSource':activation.PREFLIGHT_SOURCE,'securityAcceptance':False,
                'failureDiagnostics':diagnostics(),**resource_metadata()}
    if journal is None:
        return {'status':'held','cleanupConfirmed':cleanup,'evidenceClosureConfirmed':not state['claimStarted'],
                'claimStatus':'creation_unconfirmed' if state['claimStarted'] else 'not_created',
                'inputStage':('inputs_collected_claim_unconfirmed' if state['claimStarted'] else
                              'inputs_collected_no_claim' if state['inputsReady'] else 'inputs_not_ready_no_claim'),
                'requestsCompleted':0,'preflightSource':activation.PREFLIGHT_SOURCE,'securityAcceptance':False,
                'failureDiagnostics':diagnostics(),**resource_metadata()}
    try:
        state['controllerStage']='controller_finish'
        result=journal.finish(cleanup_confirmed=cleanup,completed=not failed,failure_diagnostics=diagnostics(),
                              **({'resource_observations':resource_metadata()['resourceObservations']} if monitor.active else {}))
        result['credentialEntryRoles']=list(profile['roles'])
        result['evidenceClosureConfirmed']=True
        result['failureDiagnostics']=diagnostics()
        result.update(resource_metadata())
        return result
    except BaseException as error:
        state['closureFailure']=describe(error,'controller_finish')
        return {'status':'held','cleanupConfirmed':cleanup,'evidenceClosureConfirmed':False,
                'claimStatus':'created','preflightSource':activation.PREFLIGHT_SOURCE,'securityAcceptance':False,
                'failureDiagnostics':diagnostics(),**resource_metadata()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest='command',required=True)
    prep=subs.add_parser('prepare');prep.add_argument('--mode',choices=('rehearsal','hosted'),default='rehearsal')
    prep.add_argument('--origin',default='https://s1-fixture.invalid');prep.add_argument('--output',type=Path,required=True)
    prep.add_argument('--real-time-resources',action='store_true',help='Fictional rehearsal only: real clock and unchanged memory guards')
    prep.add_argument('--operator-start-floor-mib',type=int,help='Optional raise-only pre-claim floor: integer 1024..8192 MiB')
    check=subs.add_parser('check');check.add_argument('--profile',type=Path,required=True)
    for command in ('rehearse','run-approved'):
        run=subs.add_parser(command)
        for name in ('profile','approval','actors','evidence'): run.add_argument('--'+name,type=Path,required=True)
        run.add_argument('--owner-reference',required=True)
    args=parser.parse_args()
    stage='controller_profile'
    try:
        if args.command=='prepare':
            profile=activation.prepare(mode=args.mode,origin=args.origin,real_time_resources=args.real_time_resources,
                                       operator_start_floor_mib=args.operator_start_floor_mib)
            with args.output.open('x',encoding='utf-8') as stream: json.dump(profile,stream,indent=2);stream.write('\n')
            print('Inert S1 profile saved; executionApproved remains false.');return 0
        if args.command=='check':
            print(activation.check_profile(read_json(args.profile)));return 0
        profile=read_json(args.profile)
        activation.check_profile(profile)
        if profile['mode']!=('hosted' if args.command=='run-approved' else 'rehearsal'):
            raise activation.Held('stage_mismatch')
        if args.command=='run-approved':
            stage='controller_evidence'
            if not sys.flags.isolated: raise activation.Held('isolated_runtime_required')
            from read_only_probe import private_path
            # Explicit input files only. No discovery, .env, password or PIN read.
            for path in (args.approval,args.actors): private_path(path)
        stage='controller_approval'
        bound=read_json(args.approval)
        if (bound.get('approved') is not True or bound.get('profileSha256')!=activation.digest(profile)
                or bound.get('ownerReference')!=args.owner_reference):
            raise activation.Held('explicit_operator_attestation_required')
        people=read_json(args.actors)
        stage='controller_execute'
        result=execute_approved(profile,bound,people,
            evidence_directory=args.evidence,owner_reference=args.owner_reference,
            input_mode='fixture' if args.command=='rehearse' else 'terminal')
        print(json.dumps(result));return 0 if result['status']=='passed' else 1
    except BaseException as error:
        detail=failure.describe(error,stage,trusted_types=(activation.Held,ProcessHeld,ResourceHeld))
        print(json.dumps({'status':'held','failureDiagnostics':failure.validate_summary({
            'version':1,'workerPosition':None,'controllerStage':stage,'primaryFailure':detail,
            'workerCleanupFailure':None,'supervisorFailure':None,'supervisorCleanupFailure':None,'closureFailure':None})}))
        print('S1 held. No retry is authorized; retain the private attempt evidence.');return 1


if __name__=='__main__': raise SystemExit(main())
