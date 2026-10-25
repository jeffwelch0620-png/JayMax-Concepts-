"""Fictional-only resource rehearsal and closed-vocabulary diagnostics."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import sys

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/ops'))
import s1_activation as activation
import s1_failure as failure
import s1_operator as operator
import s1_resources as observations
import read_only_probe as probe
import s1_activation_workers as workers
from test_s1_activation import actors, approval, fixture_server

HIGH={'freeBytes':2048*2**20,'totalBytes':6144*2**20}


@pytest.mark.parametrize('error,kind,reason',[
    (PermissionError('C:/private/x'),'PermissionError','permission_error'),
    (FileNotFoundError('PRIVATE'),'FileNotFoundError','not_found'),
    (ConnectionResetError('PRIVATE'),'ConnectionError','connection_error'),
    (BrokenPipeError('PRIVATE'),'BrokenPipeError','connection_error'),
    (ModuleNotFoundError('PRIVATE'),'ImportError','import_error'),
    (type('X',(OSError,),{})('PRIVATE'),'OSError','io_error'),
    (type('Y',(Exception,),{})('PRIVATE'),'OtherError','unknown_error'),
    (activation.Held('window_closed'),'Held','window_closed'),
    (type('ChildHeld',(activation.Held,),{})('window_closed'),'ValueError','value_error')])
def test_exception_ancestry_retains_only_fixed_categories(error,kind,reason):
    detail=failure.describe(error,'worker_input',trusted_types=(activation.Held,))
    assert (detail['errorType'],detail['reason'])==(kind,reason)
    assert failure.validate(detail)==detail
    assert 'PRIVATE' not in json.dumps(detail) and 'private/x' not in json.dumps(detail)


def test_hostile_instance_class_and_text_are_not_inspected():
    class PrivateError(OSError):
        @property
        def __class__(self):raise AssertionError('private property')
        def __str__(self):raise AssertionError('private text')
    assert failure.describe(PrivateError('PRIVATE'),'worker_input')['reason']=='io_error'


def test_real_rehearsal_is_digest_bound_and_virtual_profiles_unchanged():
    virtual=activation.prepare()
    assert 'rehearsalResources' not in virtual and virtual['clock']=='virtual'
    real=activation.prepare(real_time_resources=True)
    assert real['clock']=='real' and real['rehearsalResources']=='real'
    assert activation.check_profile(real)==activation.digest(real)
    for key,value in (('clock','virtual'),('rehearsalResources','fake')):
        changed=deepcopy(real);changed[key]=value
        with pytest.raises(activation.Held):activation.check_profile(changed)


@pytest.mark.parametrize('mode,origin,flag',[
    ('hosted',activation.ORIGIN,True),('rehearsal',activation.ORIGIN,True),
    ('rehearsal','https://outside.invalid',True),('rehearsal','http://localhost:48260',True),
    ('rehearsal','http://127.0.0.1:48260',1)])
def test_resource_flag_never_authorizes_hosted_or_ambiguous_destinations(mode,origin,flag):
    with pytest.raises(activation.Held):activation.prepare(mode=mode,origin=origin,real_time_resources=flag)


def test_monitor_keeps_failing_observation_and_cleanup_never_blocks(monkeypatch):
    monitor=observations.Monitor(True)
    monkeypatch.setattr(probe,'memory',lambda:HIGH)
    monitor.check(start=True)
    monitor.set_phase('quiet_wait');monitor.check()
    monkeypatch.setattr(probe,'memory',lambda:{**HIGH,'freeBytes':400*2**20})
    with pytest.raises(probe.Held):monitor.check()
    monitor.observe_cleanup()
    values=monitor.snapshot()
    assert values['quiet_wait']=={'samples':2,'minFreeMiB':400.0,'minFreePercent':100*400/6144}
    assert values['cleanup']['samples']==1 and monitor.failed
    assert observations.validate(values)==values


@pytest.mark.parametrize('free,start,held',[(914,True,True),(914,False,False),(610,False,True),
                                         (1024,True,False),(615,False,False)])
def test_both_absolute_and_percentage_floors_are_unchanged(monkeypatch,free,start,held):
    monkeypatch.setattr(probe,'memory',lambda:{**HIGH,'freeBytes':free*2**20})
    monitor=observations.Monitor(True)
    if held:
        with pytest.raises(probe.Held):monitor.check(start=start)
    else:monitor.check(start=start)
    assert monitor.snapshot()['input']['minFreeMiB']==free


@pytest.mark.parametrize('bad',['extra','bool','nan','negative','partial','no_samples','count_bound'])
def test_resource_metadata_refuses_untrusted_shapes_and_numbers(bad):
    value=observations.Monitor(True).snapshot()
    if bad=='extra':value['password']='PRIVATE'
    elif bad=='partial':del value['requests']
    else:
        value['input']={'samples':1,'minFreeMiB':2048.0,'minFreePercent':33.0}
        if bad=='bool':value['input']['minFreeMiB']=True
        if bad=='nan':value['input']['minFreePercent']=float('nan')
        if bad=='negative':value['input']['samples']=-1
        if bad=='no_samples':value['input']['samples']=0
        if bad=='count_bound':value['input']['samples']=observations.MAX_SAMPLES+1
    with pytest.raises(ValueError):observations.validate(value)


def test_resource_snapshot_cannot_erase_a_prior_dip(monkeypatch):
    monitor=observations.Monitor(True);monkeypatch.setattr(probe,'memory',lambda:HIGH)
    monitor.check();old=monitor.snapshot();new=deepcopy(old)
    new['input']['minFreeMiB']+=1
    with pytest.raises(ValueError):observations.validate(new,old)
    with pytest.raises(ValueError):observations.validate(observations.Monitor(True).snapshot(),old)


def test_real_wait_samples_throughout_quiet_and_recovery_and_records_dip(monkeypatch):
    clock=[0.0];monitor=observations.Monitor(True)
    def memory():return {**HIGH,'freeBytes':(400 if clock[0]>=.1 else 2048)*2**20}
    monkeypatch.setattr(probe,'memory',memory)
    async def sleep(seconds):clock[0]+=seconds
    monitor.set_phase('quiet_wait')
    with pytest.raises(probe.Held):
        asyncio.run(operator.guarded_wait(65,monitor.check,clock=lambda:clock[0],sleep=sleep))
    assert clock[0]==.1 and monitor.snapshot()['quiet_wait']['minFreeMiB']==400
    monkeypatch.setattr(probe,'memory',lambda:HIGH)
    monitor.set_phase('recovery_wait')
    asyncio.run(operator.guarded_wait(.2,monitor.check,clock=lambda:clock[0],sleep=sleep))
    assert monitor.snapshot()['recovery_wait']['samples']>=4


def test_real_mode_start_floor_refuses_before_claim(tmp_path,monkeypatch):
    monkeypatch.setattr(probe,'memory',lambda:{**HIGH,'freeBytes':400*2**20})
    profile=activation.prepare(real_time_resources=True)
    result=operator.execute_approved(profile,approval(profile,tmp_path),actors(profile),
                                    evidence_directory=tmp_path,owner_reference='TEST_ONLY_OWNER_APPROVAL',input_mode='fixture')
    assert result['claimStatus']=='not_created' and result['cleanupConfirmed']
    assert result['failureDiagnostics']['primaryFailure']['reason']=='resource_guard_failed'
    assert result['resourceObservations']['supervisor']['input']['minFreeMiB']==400
    assert not list(tmp_path.iterdir())


def test_supervisor_quiet_dip_keeps_phase_and_minimum(tmp_path,monkeypatch):
    monkeypatch.setattr(probe,'memory',lambda:HIGH)
    profile=activation.prepare(origin='http://127.0.0.1:48260',roles=('owner',),roster=False,real_time_resources=True)
    summary=observations.Monitor(True).snapshot()
    def supervise(_target,args,*,on_event,guard,seconds):
        try:
            on_event({'event':'inputs_ready'})
            on_event({'event':'stage','stage':'quiet_wait','request':None,'resourceSummary':summary})
            monkeypatch.setattr(probe,'memory',lambda:{**HIGH,'freeBytes':400*2**20})
            guard()
        except BaseException as error:
            error.ownedCleanupConfirmed=True
            raise
        pytest.fail('guard should hold')
    monkeypatch.setattr(operator,'supervise',supervise)
    result=operator.execute_approved(profile,approval(profile,tmp_path),actors(profile),
        evidence_directory=tmp_path,owner_reference='TEST_ONLY_OWNER_APPROVAL',input_mode='fixture')
    assert result['failureDiagnostics']['primaryFailure']['reason']=='resource_guard_failed'
    assert result['failureDiagnostics']['workerPosition']=={'stage':'quiet_wait','request':None}
    assert result['resourceObservations']['supervisor']['quiet_wait']['minFreeMiB']==400
    assert result['status']=='held' and result['cleanupConfirmed'] and result['requestsCompleted']==0


def test_virtual_mode_never_calls_memory_and_invalid_resource_ipc_never_claims(tmp_path,monkeypatch):
    monkeypatch.setattr(probe,'memory',lambda:pytest.fail('virtual memory read'))
    profile=activation.prepare(roles=('owner',),roster=False)
    def supervise(_target,args,*,on_event,guard,seconds):
        try:on_event({'event':'stage','stage':'worker_profile','request':None,'resourceSummary':{'password':'PRIVATE'}})
        except BaseException as error:
            error.ownedCleanupConfirmed=True
            raise
        pytest.fail('metadata accepted')
    monkeypatch.setattr(operator,'supervise',supervise)
    result=operator.execute_approved(profile,approval(profile,tmp_path),actors(profile),
        evidence_directory=tmp_path,owner_reference='TEST_ONLY_OWNER_APPROVAL')
    assert result['status']=='held' and result['claimStatus']=='not_created'
    assert 'PRIVATE' not in json.dumps(result) and not list(tmp_path.iterdir())


def test_final_resource_summary_keeps_exact_done_protocol_and_closes_journal(tmp_path,monkeypatch):
    if os.name!='nt':return
    monkeypatch.setattr(probe,'memory',lambda:HIGH)
    monkeypatch.setattr(operator,'_operator_worker',workers.resource_complete_operator)
    base=activation.prepare(roles=('owner',),roster=False,pin_configured=False,real_time_resources=True)
    with fixture_server(base) as (origin,seen,errors):
        profile=activation.prepare(origin=origin,roles=('owner',),roster=False,pin_configured=False,real_time_resources=True)
        result=operator.execute_approved(profile,approval(profile,tmp_path),actors(profile),
            evidence_directory=tmp_path,owner_reference='TEST_ONLY_OWNER_APPROVAL',input_mode='fixture')
    assert result['status']=='passed' and result['cleanupConfirmed'] and result['evidenceClosureConfirmed']
    assert result['requestsCompleted']==5 and len(seen)==5 and not errors
    assert result['failureDiagnostics']['primaryFailure'] is None
    assert result['resourceObservations']['worker']['cleanup']['samples']==1
    closed=json.loads(next(tmp_path.glob('*.jsonl')).read_text().splitlines()[-1])
    assert closed['status']=='passed' and closed['resourceObservations']==result['resourceObservations']


def test_cleanup_sampling_failure_never_overwrites_primary(monkeypatch):
    monitor=observations.Monitor(True)
    monkeypatch.setattr(probe,'memory',lambda:(_ for _ in ()).throw(OSError('PRIVATE')))
    monitor.observe_cleanup()
    assert monitor.snapshot()['cleanup']['samples']==0 and not monitor.failed


@pytest.mark.parametrize('mode',('hosted','rehearsal'))
def test_active_resource_profile_cannot_take_a_disabled_monitor(tmp_path,mode,monkeypatch):
    profile=activation.prepare(mode=mode,origin=activation.ORIGIN if mode=='hosted' else 'http://127.0.0.1:48260',
                               real_time_resources=mode=='rehearsal')
    monkeypatch.setattr(probe,'memory',lambda:pytest.fail('invalid monitor must refuse before observation'))
    with pytest.raises(ValueError,match='resource_mode_invalid'):
        activation.evidence_environment(profile,tmp_path,resource_monitor=observations.Monitor(False))
    assert not list(tmp_path.iterdir())


def test_evidence_acl_failure_is_not_mislabeled_as_memory_failure(tmp_path,monkeypatch):
    profile=activation.prepare(real_time_resources=True)
    def held(*_,**__):raise probe.Held('PRIVATE ACL PATH')
    monkeypatch.setattr(activation,'evidence_environment',held)
    result=operator.execute_approved(profile,approval(profile,tmp_path),actors(profile),
        evidence_directory=tmp_path,owner_reference='TEST_ONLY_OWNER_APPROVAL',input_mode='fixture')
    assert result['failureDiagnostics']['primaryFailure']['reason']=='held'
    assert 'PRIVATE' not in json.dumps(result) and not list(tmp_path.iterdir())


def test_real_owned_worker_quiet_dip_has_reason_minimum_and_no_request(tmp_path,monkeypatch):
    if os.name!='nt':return
    monkeypatch.setattr(probe,'memory',lambda:HIGH)
    monkeypatch.setattr(operator,'_operator_worker',workers.resource_dip_operator)
    profile=activation.prepare(origin='http://127.0.0.1:48260',roles=('owner',),roster=False,real_time_resources=True)
    result=operator.execute_approved(profile,approval(profile,tmp_path),actors(profile),
        evidence_directory=tmp_path,owner_reference='TEST_ONLY_OWNER_APPROVAL',input_mode='fixture')
    assert result['status']=='held' and result['cleanupConfirmed'] and result['requestsCompleted']==0
    assert result['failureDiagnostics']['primaryFailure']['stage']=='quiet_wait'
    assert result['failureDiagnostics']['primaryFailure']['reason']=='resource_guard_failed'
    summary=result['resourceObservations']
    assert summary['worker']['quiet_wait']['minFreeMiB']==400
    assert summary['supervisor']['cleanup']['samples']==1
    closed=json.loads(next(tmp_path.glob('*.jsonl')).read_text().splitlines()[-1])
    assert closed['resourceObservations']==summary
    assert 'TEST-ONLY-S1-password' not in json.dumps(result)
