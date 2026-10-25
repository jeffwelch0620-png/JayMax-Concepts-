"""Claim-boundary and pre-live evidence gates; fictional data and targets only."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/ops'))
import s1_activation as activation
import s1_operator as operator
import s1_resources as observations
import read_only_probe as probe
import s1_activation_workers as workers
from test_s1_activation import actors, approval

HIGH={'freeBytes':2048*2**20,'totalBytes':6144*2**20}


@pytest.mark.parametrize('stage,expected',[
    ('worker_input','input'),('worker_dispatch_wait','pre_claim'),('controller_claim','pre_claim'),
    ('worker_dispatch_check','post_claim_setup'),('worker_transport','post_claim_setup'),
    ('worker_sequence','post_claim_setup'),('quiet_wait','quiet_wait')])
def test_claim_boundary_stage_mapping(stage,expected):
    assert observations.phase(stage)==expected


@pytest.mark.parametrize('legacy',['six_phases','unversioned','old_version','bool_version','extra'])
def test_legacy_shapes_never_qualify_as_version_two_evidence(legacy):
    rows=observations.Monitor(True).snapshot()
    pair={'version':2,'supervisor':rows,'worker':deepcopy(rows)}
    if legacy=='six_phases':
        del rows['post_claim_setup']
    elif legacy=='unversioned':del pair['version']
    elif legacy=='old_version':pair['version']=1
    elif legacy=='bool_version':pair['version']=True
    else:pair['password']='PRIVATE'
    with pytest.raises(ValueError):observations.quiet_gate(pair)


@pytest.mark.parametrize('supervisor,worker,passed',[(1536,1536,True),(2048,1600,True),
    (1535.999,2048,False),(2048,1535.999,False),(1149,1149,False),(None,2048,False),(2048,None,False)])
def test_quiet_gate_requires_observed_minimum_on_both_sides(monkeypatch,supervisor,worker,passed):
    pair={'version':2}
    for name,value in (('supervisor',supervisor),('worker',worker)):
        if value is None:pair[name]=None;continue
        monitor=observations.Monitor(True);monitor.set_phase('quiet_wait')
        monkeypatch.setattr(probe,'memory',lambda v=value:{**HIGH,'freeBytes':int(v*2**20)})
        monitor.check();pair[name]=monitor.snapshot()
    gate=observations.quiet_gate(pair)
    assert gate['passed'] is passed and gate['requiredFreeMiB']==1536
    assert all(type(v) in (int,float,bool) or v is None for v in gate.values())


def test_unobserved_quiet_phase_never_passes():
    rows=observations.Monitor(True).snapshot()
    gate=observations.quiet_gate({'version':2,'supervisor':rows,'worker':rows})
    assert not gate['passed'] and gate['supervisorSamples']==0 and gate['supervisorMinFreeMiB'] is None


@pytest.mark.parametrize('bad',[True,False,1023,8193,1536.0,'1536',-1])
def test_operator_floor_is_raise_only_bounded_integer(bad):
    with pytest.raises(activation.Held):activation.prepare(operator_start_floor_mib=bad)


@pytest.mark.parametrize('floor',[1024,1536,8192])
def test_valid_floor_is_profile_and_approval_bound(tmp_path,floor):
    profile=activation.prepare(operator_start_floor_mib=floor)
    assert profile['operatorStartFloorMiB']==floor
    assert activation.check_profile(profile)==activation.digest(profile)
    bound=approval(profile,tmp_path)
    changed=deepcopy(profile);changed['operatorStartFloorMiB']=1537 if floor!=1537 else 1538
    with pytest.raises(activation.Held):activation.check_approval(changed,bound,actors(profile),tmp_path)
    assert not list(tmp_path.iterdir())


def test_default_profile_has_no_operator_floor_and_virtual_remains_memory_free(tmp_path,monkeypatch):
    profile=activation.prepare()
    assert 'operatorStartFloorMiB' not in profile and profile['clock']=='virtual'
    monkeypatch.setattr(probe,'memory',lambda:pytest.fail('default virtual memory read'))
    activation.dispatch_window(profile,approval(profile,tmp_path),actors(profile),tmp_path)


def test_explicit_null_operator_floor_is_not_a_default_profile_field():
    profile=activation.prepare();profile['operatorStartFloorMiB']=None
    with pytest.raises(activation.Held):activation.check_profile(profile)


def fake_ready_supervisor(_target,args,*,on_event,guard,seconds):
    try:
        on_event({'event':'inputs_ready'})
        raise operator.ProcessHeld('worker_held')
    except BaseException as error:
        error.ownedCleanupConfirmed=True
        raise


@pytest.mark.parametrize('dip_on_second',[False,True])
def test_higher_floor_refuses_before_claim_even_if_memory_drops_between_checks(tmp_path,monkeypatch,dip_on_second):
    memory=[2048 if dip_on_second else 1400]
    monkeypatch.setattr(probe,'memory',lambda:{**HIGH,'freeBytes':memory[0]*2**20})
    profile=activation.prepare(real_time_resources=True,operator_start_floor_mib=1536)
    bound=approval(profile,tmp_path)
    original=activation.dispatch_window;calls=[0]
    def check(*args,**kwargs):
        calls[0]+=1
        if dip_on_second and calls[0]==2:memory[0]=1400
        return original(*args,**kwargs)
    monkeypatch.setattr(activation,'dispatch_window',check)
    monkeypatch.setattr(operator,'supervise',fake_ready_supervisor)
    result=operator.execute_approved(profile,bound,actors(profile),evidence_directory=tmp_path,
                                    owner_reference=bound['ownerReference'],input_mode='fixture')
    assert result['claimStatus']=='not_created' and result['requestsCompleted']==0
    assert result['evidenceClosureConfirmed'] and result['cleanupConfirmed']
    assert result['failureDiagnostics']['primaryFailure']['reason']=='resource_headroom_insufficient'
    assert not list(tmp_path.iterdir()) and not result['quietWaitGate']['passed']


def test_operator_floor_never_waives_existing_percentage_guard(tmp_path,monkeypatch):
    profile=activation.prepare(operator_start_floor_mib=1024)
    monkeypatch.setattr(probe,'memory',lambda:{'freeBytes':2048*2**20,'totalBytes':32768*2**20})
    with pytest.raises(activation.Held,match='resource_headroom_insufficient'):
        activation.Journal(profile,approval(profile,tmp_path),actors(profile),tmp_path,require_dispatch_window=True)
    assert not list(tmp_path.iterdir())


def test_above_operator_floor_claims_and_marks_post_setup(tmp_path,monkeypatch):
    monkeypatch.setattr(probe,'memory',lambda:HIGH)
    profile=activation.prepare(real_time_resources=True,operator_start_floor_mib=1536)
    monitor=observations.Monitor(True);monitor.set_phase('pre_claim')
    started=[]
    journal=activation.Journal(profile,approval(profile,tmp_path),actors(profile),tmp_path,
        require_dispatch_window=True,resource_monitor=monitor,on_claim_start=lambda:started.append(True))
    try:
        assert started==[True] and monitor.current=='post_claim_setup'
        assert monitor.snapshot()['post_claim_setup']['samples']>=1
        assert len(list(tmp_path.glob('*.claim')))==1
    finally:journal.finish(cleanup_confirmed=True)


def test_post_claim_journal_open_failure_keeps_claim_uncertain_and_correct_phase(tmp_path,monkeypatch):
    monkeypatch.setattr(probe,'memory',lambda:HIGH)
    profile=activation.prepare(real_time_resources=True)
    original=Path.open
    def open_file(path,*args,**kwargs):
        if path.suffix=='.jsonl':raise PermissionError('PRIVATE journal path')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',open_file)
    monkeypatch.setattr(operator,'supervise',fake_ready_supervisor)
    bound=approval(profile,tmp_path)
    result=operator.execute_approved(profile,bound,actors(profile),evidence_directory=tmp_path,
                                    owner_reference=bound['ownerReference'],input_mode='fixture')
    assert result['claimStatus']=='creation_unconfirmed' and not result['evidenceClosureConfirmed']
    assert len(list(tmp_path.glob('*.claim')))==1
    assert result['resourceObservations']['supervisor']['post_claim_setup']['samples']>=1
    assert 'PRIVATE' not in json.dumps(result)


def test_post_claim_resource_failure_has_fixed_reason_and_preserves_claim(tmp_path,monkeypatch):
    low=[False];original=observations.Monitor.check
    monkeypatch.setattr(probe,'memory',lambda:{**HIGH,'freeBytes':(400 if low[0] else 2048)*2**20})
    def check(monitor,**kwargs):
        if monitor.current=='post_claim_setup':low[0]=True
        return original(monitor,**kwargs)
    monkeypatch.setattr(observations.Monitor,'check',check)
    monkeypatch.setattr(operator,'supervise',fake_ready_supervisor)
    profile=activation.prepare(real_time_resources=True,operator_start_floor_mib=1536)
    bound=approval(profile,tmp_path)
    result=operator.execute_approved(profile,bound,actors(profile),evidence_directory=tmp_path,
                                    owner_reference=bound['ownerReference'],input_mode='fixture')
    assert result['failureDiagnostics']['primaryFailure']['reason']=='resource_guard_failed'
    assert result['claimStatus']=='creation_unconfirmed' and not result['evidenceClosureConfirmed']
    assert len(list(tmp_path.glob('*.claim')))==1
    assert result['resourceObservations']['supervisor']['post_claim_setup']['minFreeMiB']==400


def test_actual_worker_transport_dip_is_post_claim_setup_not_pre_claim(tmp_path,monkeypatch):
    if os.name!='nt':return
    monkeypatch.setattr(probe,'memory',lambda:HIGH)
    monkeypatch.setattr(operator,'_operator_worker',workers.post_claim_transport_dip_operator)
    profile=activation.prepare(origin='http://127.0.0.1:48260',roles=('owner',),roster=False,
                               real_time_resources=True,operator_start_floor_mib=1536)
    bound=approval(profile,tmp_path)
    result=operator.execute_approved(profile,bound,actors(profile),evidence_directory=tmp_path,
                                    owner_reference=bound['ownerReference'],input_mode='fixture')
    d=result['failureDiagnostics']
    assert d['primaryFailure']['stage']=='worker_transport' and d['primaryFailure']['reason']=='resource_guard_failed'
    assert d['version']==1 and result['resourceObservations']['version']==2
    assert result['resourceObservations']['worker']['post_claim_setup']['minFreeMiB']==400
    assert result['status']=='held' and result['cleanupConfirmed'] and result['requestsCompleted']==0
    assert result['claimStatus']=='created' and len(list(tmp_path.glob('*.claim')))==1


def test_full_fictional_phase_order_and_seven_sampled_phases(tmp_path,monkeypatch):
    if os.name!='nt':return
    monkeypatch.setattr(probe,'memory',lambda:HIGH)
    monkeypatch.setattr(operator,'_operator_worker',workers.fast_real_phase_operator)
    order=[];original=observations.Monitor.set_phase
    def phase(monitor,name):order.append(name);return original(monitor,name)
    monkeypatch.setattr(observations.Monitor,'set_phase',phase)
    profile=activation.prepare(origin='http://127.0.0.1:48260',roles=('owner',),roster=False,
                               real_time_resources=True,operator_start_floor_mib=1536)
    bound=approval(profile,tmp_path)
    result=operator.execute_approved(profile,bound,actors(profile),evidence_directory=tmp_path,
                                    owner_reference=bound['ownerReference'],input_mode='fixture')
    assert result['status']=='passed' and result['requestsCompleted']==13 and result['cleanupConfirmed']
    expected=('pre_claim','post_claim_setup','quiet_wait','requests','recovery_wait','cleanup')
    assert [order.index(name) for name in expected]==sorted(order.index(name) for name in expected)
    assert result['quietWaitGate']['passed']
    for side in ('supervisor','worker'):
        assert all(row['samples']>=1 for row in result['resourceObservations'][side].values())
    closed=json.loads(next(tmp_path.glob('*.jsonl')).read_text().splitlines()[-1])
    assert closed['quietWaitGate']==result['quietWaitGate'] and closed['resourceObservations']['version']==2
