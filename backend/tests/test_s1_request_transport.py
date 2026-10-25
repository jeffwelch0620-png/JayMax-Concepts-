"""Fictional S1 requests only; includes actual TCP and real app login routes."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import getpass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import logging
import os
from pathlib import Path
import sys
import threading
import warnings

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/ops'))
import s1_request_transport as boundary

MEMBER = '11111111-1111-4111-8111-111111111111'
PASSWORD = 'TEST-ONLY-personal-password-20261024'
TOKEN = 'TEST-ONLY-private-session-value.0123456789'
EMAIL = 'fictional-owner@example.invalid'


def run(awaitable):
    return asyncio.run(awaitable)


def window(**overrides):
    now = boundary.utc_now()
    result = {'ends_at': now + timedelta(seconds=900),
              'stop_checks_at': now + timedelta(seconds=780)}
    result.update(overrides)
    return result


def client(handler, **kwargs):
    return boundary.LocalTransport('https://s1-fixture.invalid', approved=True,
        guard=lambda: None, transport=httpx.MockTransport(handler), **window(**kwargs))


def response(value=None, status=200, headers=None):
    return httpx.Response(status, json=value if value is not None else {'ok': True, 'staff': []}, headers=headers)


def test_hosted_and_ambiguous_destinations_are_disabled_before_client_creation(monkeypatch):
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **_: pytest.fail('client created'))
    for origin in ('https://jaymax-api.onrender.com', 'https://s1-fixture.invalid',
                   'http://localhost:9123', 'http://127.0.0.1:9123/',
                   'http://127.0.0.1:9123\n', 'http://127.0.0.1:bad',
                   'http://127.0.0.1:9123?x=1', 'http://user:secret@127.0.0.1:9123',
                   'http://127.0.0.1.evil.invalid:9123', 'http://127.0.0.1:80'):
        with pytest.raises(boundary.Held, match='hosted_execution_disabled'):
            boundary.LocalTransport(origin, approved=True, guard=lambda: None, **window())


@pytest.mark.parametrize('approved,guard', [(False, lambda: None), (None, lambda: None), (True, None)])
def test_local_approval_and_guard_are_required(approved, guard):
    with pytest.raises(boundary.Held, match='local_approval_required'):
        boundary.LocalTransport('http://127.0.0.1:9123', approved=approved, guard=guard, **window())


def test_missing_inputs_and_unknown_routes_refuse_before_transport():
    seen = []
    c = client(lambda r: seen.append(r) or response())
    async def scenario():
        for label, inputs in [('R01', {}), ('POST /api/delete', {}), ('P01', {}),
                              ('P02', {'pin': '4826', 'staff_id': '../../elsewhere'}),
                              ('P12', {'pin': '4826'})]:
            with pytest.raises(boundary.Held):
                await c.probe(label, **inputs)
    run(scenario())
    assert not seen and not c.receipt()['requests']


def test_terminal_input_refuses_pipes_and_echo_fallback(monkeypatch):
    monkeypatch.setattr(sys, 'stdin', io.StringIO('never read'))
    monkeypatch.setattr(getpass, 'getpass', lambda _: pytest.fail('prompt called'))
    with pytest.raises(boundary.Held, match='protected_input_unavailable'):
        boundary.protected_input('pin')
    monkeypatch.setattr(sys, 'stdin', type('TTY', (), {'isatty': lambda _: True})())
    def fallback(_):
        warnings.warn('echo fallback', getpass.GetPassWarning)
        pytest.fail('must stop before echo input')
    monkeypatch.setattr(getpass, 'getpass', fallback)
    with pytest.raises(boundary.Held, match='protected_input_unavailable'):
        boundary.protected_input('password')
    monkeypatch.setattr(getpass, 'getpass', lambda _: PASSWORD)
    assert boundary.protected_input('password') == PASSWORD


def test_unknown_input_label_never_prompts(monkeypatch):
    monkeypatch.setattr(getpass, 'getpass', lambda _: pytest.fail('prompt called'))
    with pytest.raises(boundary.Held):
        boundary.protected_input('token from browser')


def test_terminal_input_is_connected_to_login_and_pin_without_saved_secret(monkeypatch):
    values = iter([EMAIL, PASSWORD, '4826'])
    monkeypatch.setattr(sys, 'stdin', type('TTY', (), {'isatty': lambda _: True})())
    monkeypatch.setattr(getpass, 'getpass', lambda _: next(values))
    def handler(r):
        if r.url.path == '/api/auth/login':
            assert json.loads(r.content) == {'email': EMAIL, 'password': PASSWORD}
            return response({'token': TOKEN, 'user': {'id': 'fictional-owner', 'email': EMAIL, 'role': 'owner'}})
        assert json.loads(r.content) == {'pin': '4826'}
        return response()
    c = client(handler)
    async def scenario():
        await c.login_from_terminal('owner')
        await c.pin_from_terminal('P01')
    run(scenario())
    c.close()
    assert len(c.receipt()['requests']) == 2
    assert not any(secret in json.dumps(c.receipt()) for secret in (EMAIL, PASSWORD, TOKEN, '4826'))


def test_expired_or_duplicate_terminal_request_does_not_ask_for_input(monkeypatch):
    c = client(lambda _: response())
    run(c.probe('P01', pin='4826'))
    monkeypatch.setattr(getpass, 'getpass', lambda _: pytest.fail('prompt called'))
    with pytest.raises(boundary.Held): run(c.pin_from_terminal('P01'))
    c.close()
    with pytest.raises(boundary.Held): run(c.login_from_terminal('owner'))


@pytest.mark.parametrize('value', [{'ok': 1}, {'ok': 0}, {'ok': 'true'}, {'ok': True, 'token': TOKEN}])
def test_pin_boolean_shape_is_exact(value):
    c = client(lambda _: response(value))
    with pytest.raises(boundary.Held, match='probe_shape'):
        run(c.probe('P01', pin='4826'))


@pytest.mark.parametrize('value,reason', [
    ({'ok': False}, 'pin_verification_rejected'),
    ({'ok': 0}, 'probe_shape'),
    ({'ok': 'false'}, 'probe_shape'),
    ({'ok': None}, 'probe_shape'),
    ({'ok': False, 'token': TOKEN}, 'probe_shape'),
    ({'ok': False, 'detail': PASSWORD}, 'probe_shape'),
    ({'ok': True}, 'probe_shape'),
    ({'ok': True, 'staff': None}, 'probe_shape'),
    ({'ok': True, 'staff': [], 'token': TOKEN}, 'probe_shape'),
    ({'ok': True, 'staff': [{'id': MEMBER, 'name': EMAIL,
                           'role': 'cook', 'active': 1}]}, 'probe_shape'),
])
def test_first_pin_verification_classifies_only_exact_negative_without_leaks_or_retry(value, reason, caplog):
    import s1_failure as failure
    seen = []
    c = client(lambda r: seen.append(r.url.path) or response(value))
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(boundary.Held) as caught:
            run(c.probe('P01', pin='4826'))
        assert caught.value.args == (reason,)
        descriptor = failure.describe(caught.value, 'request', 'P01', trusted_types=(boundary.Held,))
        assert failure.validate(descriptor)['reason'] == reason
        with pytest.raises(boundary.Held, match='request_already_claimed'):
            run(c.probe('P01', pin='4826'))
    c.close()
    assert seen == [boundary.VERIFY]
    assert c.receipt()['requests'] == [{'request': 'P01', 'outcome': 'held'}]
    public = json.dumps([c.receipt(), descriptor]) + caplog.text + str(caught.value)
    assert all(secret not in public for secret in (EMAIL, PASSWORD, TOKEN, MEMBER, '4826'))


def test_first_positive_pin_verification_still_validates_roster_and_passes():
    c = client(lambda _: response({'ok': True, 'staff': [
        {'id': MEMBER, 'name': 'TEST ONLY', 'role': 'cook', 'active': True}]}))
    try:
        assert run(c.probe('P01', pin='4826')) == {
            'request': 'P01', 'outcome': 'passed', 'httpStatus': 200}
    finally:
        c.close()


def test_negative_expected_wrong_pin_stays_successful_without_new_diagnostic():
    c = client(lambda _: response({'ok': False}))
    try:
        assert run(c.probe('P03', pin='0000'))['outcome'] == 'passed'
    finally:
        c.close()


@pytest.mark.parametrize('retry', [None, '0', '62', '1.5', '６０', '-1'])
def test_retry_after_is_bounded_ascii_integer(retry):
    def handler(request):
        assert request.headers['X-Forwarded-For'] == '192.0.2.19'
        assert 'authorization' not in request.headers and 'cookie' not in request.headers
        return response({'detail': 'wait'}, 429, {'Retry-After': retry} if retry is not None else {})
    c = client(handler)
    with pytest.raises(boundary.Held):
        run(c.probe('P08', pin='0000'))


def test_request_table_cannot_be_extended_by_caller():
    with pytest.raises(TypeError): boundary.STEPS['another'] = boundary.STEPS['P01']


@pytest.mark.parametrize('value', [None, '', '１２３４', '12', '4826\n', 'a-secret'])
def test_invalid_pin_never_sends(value):
    c = client(lambda _: pytest.fail('sent'))
    with pytest.raises(boundary.Held, match='pin_input'):
        run(c.probe('P01', pin=value))


def test_sessions_are_role_bound_and_anonymous_never_inherits_cookie_or_bearer(caplog, monkeypatch):
    seen = []
    def handler(r):
        seen.append((r.url.path, dict(r.headers)))
        assert 'cookie' not in r.headers
        if r.url.path == '/api/auth/login':
            assert 'authorization' not in r.headers
            return response({'token': TOKEN, 'user': {'id': 'fictional-owner', 'email': EMAIL, 'role': 'owner'}},
                            headers={'Set-Cookie': 'ambient=TEST-ONLY-COOKIE; Path=/'})
        if r.url.path == '/api/auth/me':
            assert r.headers['authorization'] == 'Bearer ' + TOKEN
            return response({'sub': 'fictional-owner', 'email': EMAIL, 'role': 'owner'})
        assert 'authorization' not in r.headers
        return response({'detail': 'Authentication required'}, 401)
    monkeypatch.setenv('HTTPS_PROXY', 'http://secret:password@proxy.invalid:9123')
    c = client(handler)
    async def scenario():
        await c.login('owner', EMAIL, PASSWORD)
        await c.probe('R01')
        await c.probe('P12')
        with pytest.raises(boundary.Held, match='personal_login_required'):
            await c.probe('R03')
    with caplog.at_level(logging.DEBUG):
        run(scenario())
    public = json.dumps(c.receipt()) + caplog.text + repr(c._sessions)
    assert all(secret not in public for secret in (TOKEN, PASSWORD, EMAIL, 'TEST-ONLY-COOKIE'))
    assert len(seen) == 3
    c.close()
    assert not c._sessions and c.receipt()['closed']
    with pytest.raises(boundary.Held, match='window_closed'):
        run(c.probe('P12'))


@pytest.mark.parametrize('value', [
    {'token': TOKEN, 'user': {'id': 'x', 'email': EMAIL, 'role': 'manager'}},
    {'token': TOKEN + '\r\nInjected: x', 'user': {'id': 'x', 'email': EMAIL, 'role': 'owner'}},
    {'token': TOKEN, 'user': {'id': 'x', 'email': 'wrong@example.invalid', 'role': 'owner'}},
    {'ok': True, 'role': 'owner_admin', 'name': 'roster'}])
def test_login_rejects_wrong_role_identity_header_injection_and_pin_identification(value):
    c = client(lambda _: response(value))
    with pytest.raises(boundary.Held):
        run(c.login('owner', EMAIL, PASSWORD))
    assert not c._sessions and c.receipt()['requests'][0]['outcome'] == 'held'
    with pytest.raises(boundary.Held, match='request_already_claimed'):
        run(c.login('owner', EMAIL, PASSWORD))


@pytest.mark.parametrize('kind', ['redirect', 'large_header', 'large_stream', 'encoded', 'mime',
                                  'duplicate', 'nan', 'deep', 'token_minted', 'wrong_status'])
def test_response_refusals_close_stream_and_consume_slot(kind):
    class Stream(httpx.AsyncByteStream):
        closed = False
        async def __aiter__(self):
            raw = {'large_stream': b' ' * (boundary.CAP + 1), 'duplicate': b'{"ok":true,"ok":true}',
                   'nan': b'{"ok":NaN}', 'deep': b'[' * 2000 + b']' * 2000,
                   'token_minted': b'{"ok":true,"token":"TEST-ONLY-leak"}'}.get(kind, b'{"ok":true}')
            for i in range(0, len(raw), 4096):
                yield raw[i:i + 4096]
        async def aclose(self): self.closed = True
    stream = Stream()
    seen = []
    def handler(r):
        seen.append(r)
        headers = {'content-type': 'application/json'}
        if kind == 'large_header': headers['content-length'] = str(boundary.CAP + 1)
        if kind == 'encoded': headers['content-encoding'] = 'gzip'
        if kind == 'mime': headers['content-type'] = 'text/html'
        if kind == 'redirect': headers['location'] = 'https://outside.invalid/secret'
        return httpx.Response(302 if kind == 'redirect' else 503 if kind == 'wrong_status' else 200,
                              headers=headers, stream=stream)
    c = client(handler)
    with pytest.raises(boundary.Held): run(c.probe('P01', pin='4826'))
    assert stream.closed and len(seen) == 1
    with pytest.raises(boundary.Held, match='request_already_claimed'):
        run(c.probe('P01', pin='4826'))
    assert len(seen) == 1 and c.receipt()['requests'] == [{'request': 'P01', 'outcome': 'held'}]


def test_timeout_and_unsafe_exception_are_redacted_and_not_retried():
    calls = []
    async def slow(r):
        calls.append(r)
        await asyncio.sleep(1)
        return response()
    c = client(slow, request_seconds=.02)
    with pytest.raises(boundary.Held, match='request_failed'):
        run(c.probe('P01', pin='4826'))
    assert len(calls) == 1
    def unsafe(_): raise RuntimeError(PASSWORD + TOKEN)
    c = client(unsafe)
    with pytest.raises(boundary.Held) as error: run(c.probe('P01', pin='4826'))
    assert PASSWORD not in str(error.value) and TOKEN not in str(error.value)


def test_resource_or_source_guard_failure_cancels_inflight_and_later_send():
    good = True
    closed = []
    def guard():
        if not good: raise RuntimeError('private-resource-details')
    async def stalled(_):
        nonlocal good
        good = False
        try: await asyncio.sleep(5)
        finally: closed.append(True)
    c = boundary.LocalTransport('https://s1-fixture.invalid', approved=True,
        guard=guard, transport=httpx.MockTransport(stalled), **window())
    with pytest.raises(boundary.Held, match='local_guard_failed'):
        run(c.probe('P01', pin='4826'))
    assert closed
    with pytest.raises(boundary.Held, match='local_guard_failed'):
        run(c.probe('P03', pin='0000'))
    assert len(c.receipt()['requests']) == 1


def test_deadline_cancel_and_concurrent_requests_have_no_implicit_retry():
    now = [0]
    c = client(lambda _: pytest.fail('sent'), clock=lambda: now[0])
    now[0] = 781
    with pytest.raises(boundary.Held, match='window_closed'):
        run(c.probe('P12'))
    calls = []
    async def slow(r): calls.append(r); await asyncio.sleep(5)
    c = client(slow)
    async def scenario():
        task = asyncio.create_task(c.probe('P01', pin='4826'))
        await asyncio.sleep(.01)
        with pytest.raises(boundary.Held, match='request_already_claimed'):
            await c.probe('P03', pin='0000')
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
    run(scenario())
    assert len(calls) == 1 and c.receipt()['requests'][0]['outcome'] == 'cancelled'


@pytest.mark.parametrize('field,value', [
    ('ends_at', None), ('ends_at', '2026-10-24T12:00:00Z'),
    ('ends_at', datetime(2026, 1, 1)), ('stop_checks_at', datetime(2026, 1, 1)),
    ('ends_at', datetime(2000, 1, 1, tzinfo=timezone.utc)),
    ('stop_checks_at', datetime(2000, 1, 1, tzinfo=timezone.utc)),
])
def test_absolute_deadlines_refuse_naive_missing_invalid_and_past_values(field, value, monkeypatch):
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **_: pytest.fail('client created'))
    with pytest.raises(boundary.Held, match='invalid_deadline'):
        client(lambda _: pytest.fail('sent'), **{field: value})


def test_both_absolute_deadlines_are_required_and_cleanup_reserve_is_preserved():
    limits = window()
    with pytest.raises(TypeError):
        boundary.LocalTransport('http://127.0.0.1:9123', approved=True, guard=lambda: None,
                                ends_at=limits['ends_at'])
    with pytest.raises(TypeError):
        boundary.LocalTransport('http://127.0.0.1:9123', approved=True, guard=lambda: None,
                                stop_checks_at=limits['stop_checks_at'])
    with pytest.raises(boundary.Held, match='invalid_deadline'):
        client(lambda _: pytest.fail('sent'), ends_at=limits['stop_checks_at'] + timedelta(seconds=119))
    with pytest.raises(boundary.Held, match='invalid_deadline'):
        client(lambda _: pytest.fail('sent'), ends_at=limits['stop_checks_at'] - timedelta(seconds=1))
    eastern = timezone(timedelta(hours=-4))
    c = client(lambda _: response(), **{k: v.astimezone(eastern) for k, v in limits.items()})
    assert c._ends_at == limits['ends_at'] and c._stop_checks_at == limits['stop_checks_at']
    c.close()


@pytest.mark.parametrize('cutoff', ['stop_checks', 'hard_end'])
def test_wall_clock_crossing_cutoff_midstream_cancels_and_closes(cutoff, monkeypatch):
    wall = [datetime.now(timezone.utc)]
    monkeypatch.setattr(boundary, 'utc_now', lambda: wall[0])
    closed = []
    limits = window()
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"ok":true,'
            wall[0] = limits['stop_checks_at' if cutoff == 'stop_checks' else 'ends_at']
            await asyncio.sleep(.1)
            yield b'"staff":[]}'
        async def aclose(self): closed.append(True)
    c = client(lambda _: httpx.Response(200, headers={'content-type': 'application/json'}, stream=Stream()))
    with pytest.raises(boundary.Held, match='window_closed'):
        run(c.probe('P01', pin='4826'))
    assert closed and c._used == {'P01'} and c.receipt()['requests'][0]['outcome'] == 'held'
    with pytest.raises(boundary.Held, match='window_closed'):
        run(c.probe('P03', pin='0000'))
    assert c._used == {'P01'}


@pytest.mark.parametrize('utc_remaining,relative,request_limit,expected', [
    (2, 780, 90, 2), (60, 780, .5, .5), (60, .75, 90, .75)])
def test_client_and_total_timeout_use_smallest_remaining_budget(
        utc_remaining, relative, request_limit, expected, monkeypatch):
    wall = datetime.now(timezone.utc)
    monkeypatch.setattr(boundary, 'utc_now', lambda: wall)
    original_client, original_timeout = httpx.AsyncClient, asyncio.timeout
    client_budgets, total_budgets = [], []
    def observed_client(**kwargs):
        client_budgets.append(kwargs['timeout'])
        return original_client(**kwargs)
    def observed_timeout(seconds):
        total_budgets.append(seconds)
        return original_timeout(seconds)
    monkeypatch.setattr(httpx, 'AsyncClient', observed_client)
    monkeypatch.setattr(asyncio, 'timeout', observed_timeout)
    stop = wall + timedelta(seconds=utc_remaining)
    c = client(lambda _: response(), seconds=relative, request_seconds=request_limit,
               stop_checks_at=stop, ends_at=stop + timedelta(seconds=120))
    run(c.probe('P01', pin='4826'))
    assert client_budgets and total_budgets
    assert all(0 < timeout.read <= expected and 0 < timeout.connect <= expected for timeout in client_budgets)
    assert all(0 < seconds <= expected for seconds in total_budgets)


def recovery_client(**kwargs):
    now, seen = [0.0], []
    def handler(request):
        seen.append(request.url.path)
        if now[0] < 61:
            return response({'detail': 'TEST ONLY wait'}, 429, {'Retry-After': '60'})
        if request.url.path == boundary.IDENTIFY:
            return response({'ok': True, 'name': 'TEST ONLY', 'role': 'owner_admin'})
        return response()
    return client(handler, clock=lambda: now[0], **kwargs), now, seen


@pytest.mark.parametrize('label', ['P10', 'P11'])
def test_recovery_without_validated_p09_never_consumes_or_sends(label, monkeypatch):
    c, _, seen = recovery_client()
    with pytest.raises(boundary.Held, match='throttle_sequence_required'):
        run(c.probe(label, pin='4826', **({'staff_id': MEMBER} if label == 'P11' else {})))
    monkeypatch.setattr(getpass, 'getpass', lambda _: pytest.fail('prompt called'))
    with pytest.raises(boundary.Held, match='throttle_sequence_required'):
        run(c.pin_from_terminal(label, staff_id=MEMBER if label == 'P11' else None))
    assert not seen and not c._used


def test_early_recovery_keeps_slots_then_exact_wait_and_successful_p10_allow_p11(monkeypatch):
    c, now, seen = recovery_client()
    run(c.probe('P09', pin='4826'))
    assert c._recovery_at == 61
    monkeypatch.setattr(getpass, 'getpass', lambda _: pytest.fail('prompt called'))
    for label in ('P10', 'P11'):
        with pytest.raises(boundary.Held, match='throttle_wait_required'):
            run(c.probe(label, pin='4826', **({'staff_id': MEMBER} if label == 'P11' else {})))
        with pytest.raises(boundary.Held, match='throttle_wait_required'):
            run(c.pin_from_terminal(label, staff_id=MEMBER if label == 'P11' else None))
    assert c._used == {'P09'} and len(seen) == 1
    now[0] = 61
    with pytest.raises(boundary.Held, match='recovery_verification_required'):
        run(c.probe('P11', pin='4826', staff_id=MEMBER))
    assert c._used == {'P09'}
    assert run(c.probe('P10', pin='4826'))['outcome'] == 'passed'
    assert run(c.probe('P11', pin='4826', staff_id=MEMBER))['outcome'] == 'passed'
    assert len(seen) == 3


@pytest.mark.parametrize('label', ['P10', 'P11'])
@pytest.mark.parametrize('limit', ['relative', 'absolute'])
def test_insufficient_recovery_window_refuses_before_wait_input_or_consumption(label, limit):
    kwargs = {'seconds': 30} if limit == 'relative' else window(
        stop_checks_at=boundary.utc_now() + timedelta(seconds=30))
    c, _, seen = recovery_client(**kwargs)
    run(c.probe('P09', pin='4826'))
    with pytest.raises(boundary.Held, match='window_insufficient_for_recovery'):
        run(c.probe(label, pin='4826', **({'staff_id': MEMBER} if label == 'P11' else {})))
    assert c._used == {'P09'} and len(seen) == 1


def test_malformed_p09_does_not_authorize_recovery():
    c = client(lambda _: response({'detail': 'wait'}, 429))
    with pytest.raises(boundary.Held, match='probe_shape'):
        run(c.probe('P09', pin='4826'))
    with pytest.raises(boundary.Held, match='throttle_sequence_required'):
        run(c.probe('P10', pin='4826'))
    assert c._used == {'P09'}


def test_failed_p10_never_authorizes_p11():
    now = [0.0]
    def handler(_):
        return (response({'detail': 'wait'}, 429, {'Retry-After': '60'}) if now[0] == 0
                else response({'ok': True, 'staff': [], 'token': TOKEN}))
    c = client(handler, clock=lambda: now[0])
    run(c.probe('P09', pin='4826'))
    now[0] = 61
    with pytest.raises(boundary.Held, match='probe_shape'):
        run(c.probe('P10', pin='4826'))
    with pytest.raises(boundary.Held, match='recovery_verification_required'):
        run(c.probe('P11', pin='4826', staff_id=MEMBER))
    assert c._used == {'P09', 'P10'}


@contextmanager
def local_http():
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            seen.append((self.path, dict(self.headers)))
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path == '/api/auth/login':
                assert body == {'email': EMAIL, 'password': PASSWORD}
                value = {'token': TOKEN, 'user': {'id': 'fictional-owner', 'email': EMAIL, 'role': 'owner'}}
            else:
                if self.path == boundary.IDENTIFY:
                    assert body == {'pin': '4826', 'staffId': MEMBER}
                    value = {'ok': True, 'name': 'TEST ONLY', 'role': 'owner_admin'}
                else:
                    assert body == {'pin': '4826'}
                    value = {'ok': True, 'staff': []}
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Set-Cookie', 'do-not-replay=fictional; Path=/')
            self.end_headers()
            self.wfile.write(json.dumps(value).encode())
        def do_GET(self):
            seen.append((self.path, dict(self.headers)))
            assert self.path == '/api/auth/me' and self.headers['Authorization'] == 'Bearer ' + TOKEN
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'sub': 'fictional-owner', 'email': EMAIL, 'role': 'owner'}).encode())
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try: yield 'http://127.0.0.1:' + str(server.server_port), seen
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
        assert not thread.is_alive()


def test_actual_httpx_socket_boundary_has_no_proxy_cookie_or_ambient_authorization(monkeypatch, caplog):
    monkeypatch.setenv('HTTP_PROXY', 'http://unreachable.invalid:9123')
    monkeypatch.setenv('ALL_PROXY', 'http://unreachable.invalid:9123')
    monkeypatch.setenv('NO_PROXY', '')
    with local_http() as (origin, seen):
        c = boundary.LocalTransport(origin, approved=True, guard=lambda: None, **window())
        async def scenario():
            await c.login('owner', EMAIL, PASSWORD)
            await c.probe('R01')
            await c.probe('P01', pin='4826')
            await c.probe('P02', pin='4826', staff_id=MEMBER)
        with caplog.at_level(logging.DEBUG): run(scenario())
        assert len(seen) == 4
        assert all(not ({k.lower() for k in headers} & {'cookie', 'proxy-authorization'}) for _, headers in seen)
        assert all('authorization' not in {k.lower() for k in headers}
                   for path, headers in seen if path != '/api/auth/me')
        assert all(secret not in caplog.text for secret in (EMAIL, PASSWORD, TOKEN, '4826'))
        c.close()


def test_real_app_login_pin_lockout_and_personal_role_matrix(monkeypatch, tmp_path):
    # No synthetic token creation: obtain every token through the real login
    # route and real password verification against fictional fake-DB rows.
    os.environ.setdefault('MONGO_URL', 'mongodb://127.0.0.1:27017')
    os.environ.setdefault('DB_NAME', 'fictional_s1_transport')
    import server
    import staff_pin_security as security
    from test_staff_pin_security import Connection, Pool
    now = [1000.0]
    monkeypatch.setattr(security, 'limiter', security.PinAttemptLimiter(tmp_path / 'limits.sqlite3', clock=lambda: now[0]))
    monkeypatch.setattr(server, 'USE_PG', True)
    monkeypatch.setattr(server, 'AUTH_REQUIRED', True)
    monkeypatch.setattr(server, 'AUTH_SECRET', 'TEST-ONLY-S1-transport-signing-key')
    monkeypatch.setattr(server, 'SESSION_TTL', 37)  # Receipt reports the default, not observed runtime config.
    users = {role + '@example.invalid': {'id': 'fictional-' + role, 'role': role,
             'email': role + '@example.invalid', 'locations': ['berts'],
             'password_hash': server._password_hash(PASSWORD), 'created_at': datetime.now(timezone.utc)}
             for role in boundary.ROLES}
    class Auxiliary:
        async def fetchrow(self, _, email): return users.get(email)
        async def fetch(self, _): return list(users.values())
    monkeypatch.setattr(server.db_auxiliary, 'pool', lambda: Auxiliary())
    pool = Pool(Connection('4826'))
    monkeypatch.setattr(server.db_pg, 'pool', lambda: pool)
    async def no_activity(*args): pass
    monkeypatch.setattr(server, '_record_activity', no_activity)
    c = boundary.LocalTransport('https://s1-fixture.invalid', approved=True,
        guard=lambda: None, transport=httpx.ASGITransport(app=server.app),
        clock=lambda: now[0], **window())
    async def scenario():
        await c.probe('P01', pin='4826')
        await c.probe('P02', pin='4826', staff_id=MEMBER)
        for label in ('P03', 'P04', 'P05', 'P06', 'P07'):
            await c.probe(label, pin='0000', staff_id=MEMBER if label in ('P04', 'P06') else None)
        await c.probe('P08', pin='0000')
        await c.probe('P09', pin='4826')
        for role in boundary.ROLES:
            await c.login(role, role + '@example.invalid', PASSWORD)
        for label in ('R01', 'R02', 'R03', 'R04', 'R05', 'R06', 'P12'):
            await c.probe(label)
        now[0] += 62  # Fictional limiter clock, no minute-long sleep or reset.
        await c.probe('P10', pin='4826')
        await c.probe('P11', pin='4826', staff_id=MEMBER)
    run(scenario())
    fictional_tokens = [session.token for session in c._sessions.values()]
    c.close()
    receipt = c.receipt()
    assert not c._sessions and all(server._decode_token(token) for token in fictional_tokens)
    assert receipt['serverSideRevocation'] == 'not_available' and receipt['sessionTtlSecondsDefault'] == 28800
    assert len(receipt['requests']) == 21
    assert all(fact['outcome'] == 'passed' for fact in receipt['requests'])
    public = json.dumps(receipt)
    assert all(value not in public for value in (PASSWORD, '4826', MEMBER, '@example.invalid', 'token', 'Bearer'))
