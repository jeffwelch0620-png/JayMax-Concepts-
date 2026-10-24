"""Explicit S1 operator launcher. Prepare/check are inert; live execution is opt-in.

No real credentials are used by rehearsal. Never run approved-hosted mode without
a new exact owner approval. No app/Render/Supabase setup is performed here.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time

if sys.flags.isolated:
    sys.path.insert(0,str(Path(__file__).resolve().parent))

import s1_activation as activation
from s1_console import console_input
from s1_process import ProcessHeld, receive, send, supervise

FICTIONAL_PASSWORD = 'TEST-ONLY-S1-password-4826'


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


def _operator_worker(channel,profile,approval,actors,input_mode):
    async def permit(label):
        send(channel,{'event':'permit','request':label})
        answer=await asyncio.to_thread(receive,channel)
        if answer!={'grant':label}: raise activation.Held('dispatch_not_granted')
    def guard():
        if activation.engine.utc_now()>=activation.stamp(approval['stopChecksAt']):
            raise activation.Held('window_closed')
        if profile['mode']=='hosted':
            from read_only_probe import resources
            resources()
    async def emit(value):
        send(channel,{'event':'result','value':value})
        if await asyncio.to_thread(receive,channel)!={'continue':True}:
            raise activation.Held('result_not_acknowledged')
    credentials={};pin=None;client=None
    try:
        activation.check_profile(profile)
        activation.check_approval(profile,approval,actors,approval['evidenceDirectory'])
        if input_mode=='fixture':
            if profile['mode']!='rehearsal' or any(not a['email'].endswith('@example.invalid') for a in actors.values()):
                raise activation.Held('fictional_inputs_required')
            pin='4826'
            credentials={role:(actor['email'],FICTIONAL_PASSWORD) for role,actor in actors.items()}
        else:
            prefix='FICTIONAL ONLY ' if profile['mode']=='rehearsal' else 'APPROVED S1 '
            pin=console_input(prefix+'Bert\'s PIN (hidden): ') if profile['pinConfigured'] else '0000'
            for role in profile['roles']:
                guard()
                email=console_input(prefix+role+' email (hidden): ')
                password=console_input(prefix+role+' password (hidden): ')
                if email!=actors[role]['email']: raise activation.Held('approved_actor_mismatch')
                if profile['mode']=='rehearsal' and (password!=FICTIONAL_PASSWORD or not email.endswith('@example.invalid')):
                    raise activation.Held('fictional_inputs_required')
                credentials[role]=(email,password)
            if profile['mode']=='rehearsal' and profile['pinConfigured'] and pin!='4826':
                raise activation.Held('fictional_inputs_required')
        cap=activation._Capability(activation._KEY,profile,approval,actors,permit,guard,supervised=True)
        virtual=[time.monotonic()]
        client=activation._ApprovedTransport(cap,clock=(lambda:virtual[0]) if profile['clock']=='virtual' else None)
        async def wait(seconds):
            if profile['clock']=='virtual':
                virtual[0]+=seconds;await asyncio.sleep(0)
            else: await asyncio.sleep(seconds)
        asyncio.run(activation.run_sequence(client,pin=pin,credentials=credentials,
                    staff_id=approval['rosterId'],emit=emit,wait=wait))
        send(channel,{'event':'done'})
    finally:
        if client: client.close()
        credentials.clear();pin=None


def execute_approved(profile,approval,actors,*,evidence_directory,owner_reference,input_mode='terminal'):
    if owner_reference!=approval.get('ownerReference') or input_mode not in ('terminal','fixture'):
        raise activation.Held('explicit_operator_attestation_required')
    if profile.get('mode')=='hosted' and input_mode!='terminal':
        raise activation.Held('protected_terminal_required')
    journal=activation.Journal(profile,approval,actors,evidence_directory)
    cleanup=False;failed=False;uncertain_writer=False
    def event(value):
        if value=={'event':'done'}: return
        if set(value)=={'event','request'} and value['event']=='permit':
            journal.intent(value['request']);return {'grant':value['request']}
        if set(value)=={'event','value'} and value['event']=='result':
            journal.result(value['value']);return {'continue':True}
        raise ProcessHeld('worker_message_invalid')
    try:
        outcome=supervise(_operator_worker,(profile,approval,actors,input_mode),on_event=event,
            guard=journal.guard,seconds=max(.001,(journal.stop-activation.engine.utc_now()).total_seconds()))
        cleanup=outcome['ownedCleanupConfirmed']
    except BaseException as error:
        failed=True
        cleanup=getattr(error,'ownedCleanupConfirmed',False) is True
        # Writer may still be stalled: never race another write or call it closed.
        uncertain_writer=type(error) is ProcessHeld and str(error)=='controller_callback_unconfirmed'
    if uncertain_writer:
        return {'status':'held','cleanupConfirmed':False,'evidenceClosureConfirmed':False}
    try:
        result=journal.finish(cleanup_confirmed=cleanup,completed=not failed)
        result['evidenceClosureConfirmed']=True
        return result
    except BaseException:
        return {'status':'held','cleanupConfirmed':cleanup,'evidenceClosureConfirmed':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest='command',required=True)
    prep=subs.add_parser('prepare');prep.add_argument('--mode',choices=('rehearsal','hosted'),default='rehearsal')
    prep.add_argument('--origin',default='https://s1-fixture.invalid');prep.add_argument('--output',type=Path,required=True)
    check=subs.add_parser('check');check.add_argument('--profile',type=Path,required=True)
    for command in ('rehearse','run-approved'):
        run=subs.add_parser(command)
        for name in ('profile','approval','actors','evidence'): run.add_argument('--'+name,type=Path,required=True)
        run.add_argument('--owner-reference',required=True)
    args=parser.parse_args()
    try:
        if args.command=='prepare':
            profile=activation.prepare(mode=args.mode,origin=args.origin)
            with args.output.open('x',encoding='utf-8') as stream: json.dump(profile,stream,indent=2);stream.write('\n')
            print('Inert S1 profile saved; executionApproved remains false.');return 0
        if args.command=='check':
            print(activation.check_profile(read_json(args.profile)));return 0
        profile=read_json(args.profile)
        activation.check_profile(profile)
        if profile['mode']!=('hosted' if args.command=='run-approved' else 'rehearsal'):
            raise activation.Held('stage_mismatch')
        if args.command=='run-approved':
            if not sys.flags.isolated: raise activation.Held('isolated_runtime_required')
            from read_only_probe import private_path
            # Explicit input files only. No discovery, .env, password or PIN read.
            for path in (args.approval,args.actors): private_path(path)
        bound=read_json(args.approval)
        if (bound.get('approved') is not True or bound.get('profileSha256')!=activation.digest(profile)
                or bound.get('ownerReference')!=args.owner_reference):
            raise activation.Held('explicit_operator_attestation_required')
        result=execute_approved(profile,bound,read_json(args.actors),
            evidence_directory=args.evidence,owner_reference=args.owner_reference,
            input_mode='fixture' if args.command=='rehearse' else 'terminal')
        print(json.dumps(result));return 0 if result['status']=='passed' else 1
    except BaseException:
        print('S1 held. No retry is authorized; retain the private attempt evidence.');return 1


if __name__=='__main__': raise SystemExit(main())
