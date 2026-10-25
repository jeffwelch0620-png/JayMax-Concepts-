"""Fixed diagnostic vocabularies and real owned-worker faults; fictional data only."""
import json
import asyncio
import os
from pathlib import Path
import sys

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/ops'))
import s1_failure as failure
import s1_activation as activation
import s1_operator as operator
import s1_process as processes
import s1_activation_workers as workers
from test_s1_activation import actors, approval

PRIVATE='TEST-ONLY-PRIVATE-PASSWORD-DSN'


@pytest.mark.parametrize('error,kind,reason',[(ValueError(PRIVATE),'ValueError','value_error'),
    (OSError(PRIVATE),'OSError','io_error'),(RuntimeError(PRIVATE),'RuntimeError','runtime_error'),
    (TimeoutError(PRIVATE),'TimeoutError','timeout'),(KeyboardInterrupt(PRIVATE),'KeyboardInterrupt','interrupted')])
def test_describe_builtins_never_uses_error_text(error,kind,reason):
    value=failure.describe(error,'worker_transport')
    assert value=={'stage':'worker_transport','request':None,'reason':reason,'errorType':kind}
    assert PRIVATE not in json.dumps(value)


def test_unknown_exception_and_string_subclass_are_constant_fallbacks():
    class PrivateError(RuntimeError):
        def __str__(self): raise AssertionError('must not stringify private exception')
    assert failure.describe(PrivateError(PRIVATE),'worker_input')['errorType']=='OtherError'
    class PrivateString(str):
        def __hash__(self):raise AssertionError('must not inspect private string subclass')
    error=activation.Held(PrivateString(PRIVATE))
    assert failure.describe(error,'worker_input',trusted_types=(activation.Held,))['reason']=='held'


@pytest.mark.parametrize('category,expected',[('window_closed','window_closed'),(PRIVATE,'held'),('unexpected_status','unexpected_status')])
def test_only_exact_trusted_reason_constants_are_retained(category,expected):
    value=failure.describe(activation.Held(category),'quiet_wait',trusted_types=(activation.Held,))
    assert value['reason']==expected and PRIVATE not in json.dumps(value)
    assert failure.describe(activation.Held(category),'quiet_wait')['reason']=='unknown_error'


@pytest.mark.parametrize('change',[{'stage':PRIVATE},{'request':PRIVATE},{'reason':PRIVATE},
    {'errorType':PRIVATE},{'password':PRIVATE},{'request':'P02'}])
def test_malformed_or_out_of_profile_diagnostics_are_refused(change):
    value={**failure.describe(RuntimeError(),'request','P01'),**change}
    with pytest.raises(ValueError):failure.validate(value,requests=('P01','L01'))


def mock_failure(tmp_path,monkeypatch,events,*,after=None):
    profile=activation.prepare(roles=('owner',),roster=False);bound=approval(profile,tmp_path)
    def supervise(_target,args,*,on_event,guard,seconds):
        try:
            for value in events:on_event(value)
            if after:after(guard)
        except BaseException as error:
            error.ownedCleanupConfirmed=True
            raise
        raise AssertionError('fault fixture must stop')
    monkeypatch.setattr(operator,'supervise',supervise)
    return operator.execute_approved(profile,bound,actors(profile),evidence_directory=tmp_path,owner_reference=bound['ownerReference'])


@pytest.mark.parametrize('value',[
    {'event':'stage','stage':PRIVATE,'request':None},
    {'event':'stage','stage':'worker_input','request':None,'password':PRIVATE},
    {'event':'stage','stage':'worker_transport','request':None},
    {'event':'failure','primaryFailure':{'stage':'worker_input','request':None,'reason':PRIVATE,'errorType':'Held'},'cleanupFailure':None},
    {'event':'failure','primaryFailure':None,'cleanupFailure':None},
    {'event':'failure','primaryFailure':None,'cleanupFailure':{'stage':'worker_cleanup','request':None,'reason':'io_error','errorType':'OSError'}},
    {'event':'stage','stage':'request','request':'P01'},
])
def test_untrusted_stage_or_failure_messages_do_not_create_claims(tmp_path,monkeypatch,value):
    result=mock_failure(tmp_path,monkeypatch,[value])
    assert result['claimStatus']=='not_created' and not list(tmp_path.iterdir())
    assert result['failureDiagnostics']['primaryFailure']['reason']=='worker_message_invalid'
    assert PRIVATE not in json.dumps(result)


def test_stage_budget_is_bounded_without_authorizing_dispatch(tmp_path,monkeypatch):
    result=mock_failure(tmp_path,monkeypatch,[{'event':'stage','stage':'worker_profile','request':None}]*65)
    assert result['claimStatus']=='not_created' and result['failureDiagnostics']['primaryFailure']['reason']=='worker_message_invalid'
    assert not list(tmp_path.iterdir())


def test_parent_resource_failure_after_inputs_retains_safe_reason(tmp_path,monkeypatch):
    from read_only_probe import Held as ResourceHeld
    def fail_guard(self):raise ResourceHeld(PRIVATE)
    monkeypatch.setattr(activation.Journal,'guard',fail_guard)
    result=mock_failure(tmp_path,monkeypatch,[{'event':'inputs_ready'}],after=lambda guard:guard())
    assert result['requestsCompleted']==0 and result['claimStatus']=='created'
    assert result['failureDiagnostics']['primaryFailure']=={
        'stage':'controller_guard','request':None,'reason':'resource_guard_failed','errorType':'Held'}
    assert PRIVATE not in json.dumps(result)+next(tmp_path.glob('*.jsonl')).read_text()


def test_closure_error_does_not_replace_worker_primary(tmp_path,monkeypatch):
    def finish(journal,**kwargs):journal.stream.close();raise OSError(PRIVATE)
    monkeypatch.setattr(activation.Journal,'finish',finish)
    result=mock_failure(tmp_path,monkeypatch,[{'event':'inputs_ready'},
        {'event':'stage','stage':'worker_transport','request':None},
        {'event':'failure','primaryFailure':failure.describe(RuntimeError(),'worker_transport'),'cleanupFailure':None}])
    d=result['failureDiagnostics']
    assert d['primaryFailure']['stage']=='worker_transport' and d['closureFailure']['reason']=='io_error'
    assert result['evidenceClosureConfirmed'] is False and PRIVATE not in json.dumps(result)


def test_invalid_summary_closes_journal_without_serializing_private_fields(tmp_path):
    profile=activation.prepare();journal=activation.Journal(profile,approval(profile,tmp_path),actors(profile),tmp_path)
    with pytest.raises(ValueError):journal.finish(cleanup_confirmed=True,failure_diagnostics={'password':PRIVATE})
    assert journal.closed and journal.stream.closed and PRIVATE not in next(tmp_path.glob('*.jsonl')).read_text()


@pytest.mark.parametrize('fault,completed,primary_stage,primary_reason,cleanup_reason',[
    ('constructor',0,'worker_transport','runtime_error',None),
    ('quiet',0,'quiet_wait','runtime_error',None),
    ('window',0,'worker_dispatch_check','window_closed',None),
    ('password',1,'request','unexpected_status',None),
    ('primary_cleanup',0,'quiet_wait','runtime_error','io_error'),
    ('cleanup',13,None,None,'io_error'),
    ('success',13,None,None,None),
])
def test_real_owned_worker_reports_stages_and_independent_cleanup(tmp_path,monkeypatch,fault,completed,primary_stage,primary_reason,cleanup_reason):
    if os.name!='nt':return
    real_supervise=operator.supervise
    def supervise(target,args,**kwargs):return real_supervise(target,(*args[:-1],fault),**kwargs)
    monkeypatch.setattr(operator,'supervise',supervise)
    monkeypatch.setattr(operator,'_operator_worker',workers.diagnostic_operator)
    profile=activation.prepare(origin='http://127.0.0.1:48260',roles=('owner',),roster=False)
    bound=approval(profile,tmp_path)
    result=operator.execute_approved(profile,bound,actors(profile),evidence_directory=tmp_path,owner_reference=bound['ownerReference'],input_mode='terminal')
    assert result['cleanupConfirmed'] and result['evidenceClosureConfirmed'] and result['requestsCompleted']==completed
    assert result['status']==('passed' if fault=='success' else 'held')
    d=result['failureDiagnostics'];primary=d['primaryFailure'];cleanup=d['workerCleanupFailure']
    if primary_stage:
        assert (primary['stage'],primary['reason'])==(primary_stage,primary_reason)
        assert primary['request']==('L01' if fault=='password' else None)
    else:assert primary is None
    assert (cleanup['reason'] if cleanup else None)==cleanup_reason
    raw=next(tmp_path.glob('*.jsonl')).read_text();closed=json.loads(raw.splitlines()[-1])
    assert closed['failureDiagnostics']==d
    assert PRIVATE not in raw+json.dumps(result) and actors(profile)['owner']['email'] not in raw
    assert result['claimStatus']=='created' and result['securityAcceptance'] is False


def test_supervisor_primary_survives_owned_cleanup_failure(monkeypatch):
    if os.name!='nt':return
    original=processes.OwnedJob.terminate
    def terminate(job):original(job);raise OSError(PRIVATE)
    monkeypatch.setattr(processes.OwnedJob,'terminate',terminate)
    def event(_):raise RuntimeError(PRIVATE)
    with pytest.raises(processes.ProcessHeld,match='owned_cleanup_unconfirmed') as caught:
        processes.supervise(workers.stalled,on_event=event,guard=lambda:None,seconds=5)
    error=caught.value
    assert error.supervisorFailure['stage']=='controller_callback'
    assert error.supervisorFailure['reason']=='runtime_error' and error.cleanupFailure['reason']=='io_error'
    assert error.ownedCleanupConfirmed is False and PRIVATE not in json.dumps([error.supervisorFailure,error.cleanupFailure])


@pytest.mark.parametrize('close_policy',[False,None,0])
def test_unsupervised_sequence_cannot_delegate_or_omit_cleanup(tmp_path,close_policy):
    import httpx
    profile=activation.prepare(roles=('owner',),roster=False)
    journal=activation.Journal(profile,approval(profile,tmp_path),actors(profile),tmp_path)
    client=activation.rehearsal_client(journal,transport=httpx.MockTransport(lambda _:pytest.fail('HTTP dispatch')))
    try:
        with pytest.raises(activation.Held,match='supervised_operator_required'):
            asyncio.run(activation.run_sequence(client,pin='4826',credentials={},emit=lambda _:None,close_on_exit=close_policy))
        assert journal.pending is None
    finally:client.close();journal.finish(cleanup_confirmed=True)


def test_cli_preflight_failure_has_safe_stage_without_private_path_or_exception_text(monkeypatch,capsys):
    monkeypatch.setattr(operator,'read_json',lambda _:(_ for _ in ()).throw(OSError(PRIVATE)))
    monkeypatch.setattr(sys,'argv',['operator','check','--profile','TEST-ONLY-PATH'])
    assert operator.main()==1
    text=capsys.readouterr().out;value=json.loads(text.splitlines()[0])
    assert value['failureDiagnostics']['primaryFailure']=={
        'stage':'controller_profile','request':None,'reason':'io_error','errorType':'OSError'}
    assert PRIVATE not in text and 'TEST-ONLY-PATH' not in text


def test_unconfirmed_callback_does_not_close_evidence_or_release_claim(tmp_path,monkeypatch):
    profile=activation.prepare(roles=('owner',),roster=False);bound=approval(profile,tmp_path)
    def fail(*args,**kwargs):
        error=processes.ProcessHeld('controller_callback_unconfirmed');error.ownedCleanupConfirmed=True
        error.supervisorFailure=failure.describe(RuntimeError(),'controller_callback')
        raise error
    monkeypatch.setattr(operator,'supervise',fail)
    result=operator.execute_approved(profile,bound,actors(profile),evidence_directory=tmp_path,owner_reference=bound['ownerReference'])
    assert result['claimStatus']=='unconfirmed' and not result['cleanupConfirmed'] and not result['evidenceClosureConfirmed']
    assert result['failureDiagnostics']['primaryFailure']['stage']=='controller_callback'
    assert not list(tmp_path.iterdir())
