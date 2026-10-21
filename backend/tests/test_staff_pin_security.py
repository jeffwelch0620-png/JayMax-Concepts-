"""Fictional offline PIN security tests; no app pools or hosted connections."""
import asyncio
import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from types import SimpleNamespace

os.environ.setdefault('MONGO_URL', 'mongodb://127.0.0.1:27017')
os.environ.setdefault('DB_NAME', 'fictional_pin_review')
os.environ.setdefault('AUTH_SECRET', 'fictional-pin-review-secret-only')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request
import server
import staff_pin_security as security
from uvicorn import Config
import uvicorn

MEMBER = {'id': '11111111-1111-4111-8111-111111111111', 'name': 'TEST ONLY Claimed Manager',
          'role': 'owner_admin', 'active': True, 'store_id': 'berts'}


def request(path='/api/pg/staff/berts/verify', *, host='192.0.2.10', token=None, extra=()):
    headers = [(b'authorization', ('Bearer ' + token).encode())] if token else []
    return Request({'type': 'http', 'method': 'POST', 'path': path, 'query_string': b'',
                    'headers': headers + list(extra), 'scheme': 'https',
                    'server': ('testserver', 443), 'client': (host, 1)})


class Cursor:
    def __init__(self, rows): self.rows = rows
    def sort(self, *args): return self
    async def to_list(self, *args): return self.rows


class Collection:
    def __init__(self, kind, pin): self.kind, self.pin = kind, pin
    async def find_one(self, query, *args, **kwargs):
        if self.kind == 'settings': return {'staffPin': self.pin} if self.pin is not None else None
        if self.kind == 'staff_members': return dict(MEMBER)
        return None
    def find(self, *args, **kwargs): return Cursor([dict(MEMBER)] if self.kind == 'staff_members' else [])


class Connection:
    def __init__(self, pin): self.pin = pin
    async def fetchrow(self, query, *args):
        if 'staff_pins' in query: return {'pin': self.pin} if self.pin is not None else None
        if 'staff_members' in query: return dict(MEMBER)
        return None
    async def fetch(self, query, *args): return [dict(MEMBER)] if 'staff_members' in query else []
    async def fetchval(self, query, *args): return False


class Pool:
    def __init__(self, conn): self.conn = conn
    async def acquire(self): return self.conn
    async def release(self, conn): assert conn is self.conn
    async def fetchrow(self, query, *args): return await self.conn.fetchrow(query, *args)


@pytest.fixture
def portal(monkeypatch, tmp_path):
    monkeypatch.setattr(security, 'limiter', security.PinAttemptLimiter(tmp_path / 'limits.sqlite3'))
    monkeypatch.setattr(server, 'AUTH_SECRET', 'fictional-pin-review-secret-only')
    monkeypatch.setattr(server, 'AUTH_REQUIRED', True)
    conn = Connection('4826')
    mongo = SimpleNamespace(**{kind: Collection(kind, '4826') for kind in
                              ('settings', 'staff_members', 'prep_lists', 'staff_tasks', 'items')})
    monkeypatch.setattr(server.db_pg, 'pool', lambda: Pool(conn))
    monkeypatch.setattr(server, 'db', mongo)
    async def no_activity(*args): pass
    monkeypatch.setattr(server, '_record_activity', no_activity)
    return conn, mongo


async def post(path, body, token=None, *, app=None, host='127.0.0.1', headers=None):
    transport = httpx.ASGITransport(app=app or server.app, client=(host, 1))
    async with httpx.AsyncClient(transport=transport, base_url='https://testserver') as client:
        return await client.post(path, json=body,
                                 headers={'Authorization': 'Bearer ' + token} if token else headers or {})


@pytest.mark.parametrize('pg', [False, True])
@pytest.mark.parametrize('role', ['owner_admin', 'cook'])
def test_claimed_roster_role_is_not_a_personal_session(portal, monkeypatch, pg, role):
    monkeypatch.setitem(MEMBER, 'role', role)
    monkeypatch.setattr(server, 'USE_PG', pg)
    prefix = '/api/pg' if pg else '/api'
    response = asyncio.run(post(prefix + '/staff/berts/identify', {'pin': '4826', 'staffId': MEMBER['id']}))
    assert response.status_code == 200
    assert response.json() == {'ok': True, 'name': MEMBER['name'], 'role': role}
    assert not ({'token', 'session', 'user'} & response.json().keys())
    with pytest.raises(HTTPException):
        server._require_owner(request())


@pytest.mark.parametrize('pg', [False, True])
@pytest.mark.parametrize('pin', [None, '', ' ', '12', '１２３４', 'bad-pin'])
def test_unset_or_invalid_stored_pin_disables_verify_and_identify(portal, monkeypatch, pg, pin):
    conn, mongo = portal
    conn.pin = mongo.settings.pin = pin
    monkeypatch.setattr(server, 'USE_PG', pg)
    cases = [('/api/pg/staff/berts/verify', {'pin': ''}),
             ('/api/pg/staff/berts/identify', {'pin': '1234', 'staffId': MEMBER['id']})] if pg else [
             ('/api/staff/verify', {'restaurantId': 'berts', 'pin': ''}),
             ('/api/staff/berts/identify', {'pin': '1234', 'staffId': MEMBER['id']})]
    for path, body in cases:
        response = asyncio.run(post(path, body))
        assert response.status_code == 403
        assert 'disabled' in response.json()['detail']


@pytest.mark.parametrize('pg', [False, True])
def test_wrong_pin_budget_is_shared_between_verify_identify_and_direct_checks(portal, monkeypatch, pg):
    monkeypatch.setattr(server, 'USE_PG', pg)
    # Same ASGI client + canonical store; changing endpoints cannot reset failures.
    verify = '/api/pg/staff/berts/verify' if pg else '/api/staff/verify'
    identify = ('/api/pg' if pg else '/api') + '/staff/berts/identify'
    for index in range(5):
        path = verify if index % 2 == 0 else identify
        body = {'pin': '0000', 'restaurantId': 'berts', 'staffId': MEMBER['id']}
        response = asyncio.run(post(path, body))
        assert response.status_code in (200, 403)
        if response.status_code == 200: assert response.json()['ok'] is False
    response = asyncio.run(post(verify, {'pin': '4826', 'restaurantId': 'berts'}))
    assert response.status_code == 429 and int(response.headers['retry-after']) > 0


@pytest.mark.parametrize('pg', [False, True])
def test_configured_pin_verification_and_personal_login_access_remain(portal, monkeypatch, pg):
    monkeypatch.setattr(server, 'USE_PG', pg)
    verify = '/api/pg/staff/berts/verify' if pg else '/api/staff/verify'
    for _ in range(8):
        response = asyncio.run(post(verify, {'pin': '4826', 'restaurantId': 'berts'}))
        assert response.status_code == 200 and response.json()['staff'][0]['id'] == MEMBER['id']
    token = server._token({'id': 'usr_fictional_owner', 'email': 'owner@example.test', 'role': 'owner', 'locations': []})
    portal[0].pin = portal[1].settings.pin = None
    response = asyncio.run(post(verify, {'pin': '', 'restaurantId': 'berts'}, token))
    assert response.status_code == 200 and response.json()['ok'] is True
    assert server._require_owner(request(token=token))['sub'] == 'usr_fictional_owner'


@pytest.mark.parametrize('pg', [False, True])
def test_manager_pin_read_has_no_default(portal, pg):
    token = server._token({'id': 'usr_fictional_owner', 'email': 'owner@example.test', 'role': 'owner'})
    portal[0].pin = portal[1].settings.pin = None
    read = server.pg_get_staff_pin if pg else server.get_pin
    assert asyncio.run(read('berts', request(token=token))) == {'staffPin': '', 'custom': False, 'enabled': False}
    # A stored value equal to the former default is explicit configuration, not fallback.
    portal[0].pin = portal[1].settings.pin = '1234'
    assert asyncio.run(read('berts', request(token=token))) == {'staffPin': '1234', 'custom': True, 'enabled': True}


@pytest.mark.parametrize('pg', [False, True])
@pytest.mark.parametrize('flow', ['prepsheet', 'counts', 'tasks'])
def test_direct_staff_flows_keep_configured_access_and_refuse_disabled_pin(portal, monkeypatch, pg, flow):
    monkeypatch.setattr(server, 'USE_PG', pg)
    path = ('/api/pg' if pg else '/api') + '/staff/berts/' + flow
    response = asyncio.run(post(path, {'pin': '4826'}))
    assert response.status_code == 200
    portal[0].pin = portal[1].settings.pin = None
    response = asyncio.run(post(path, {'pin': ''}))
    assert response.status_code == 403 and 'disabled' in response.json()['detail']


@pytest.mark.parametrize('pg', [False, True])
@pytest.mark.parametrize('flow', ['prepsheet', 'counts', 'tasks'])
def test_direct_routes_cannot_bypass_attempt_limit(portal, monkeypatch, pg, flow):
    monkeypatch.setattr(server, 'USE_PG', pg)
    path = ('/api/pg' if pg else '/api') + '/staff/berts/' + flow
    for _ in range(5):
        assert asyncio.run(post(path, {'pin': '0000'})).status_code == 403
    response = asyncio.run(post(path, {'pin': '0000'}))
    assert response.status_code == 429 and int(response.headers['retry-after']) > 0


def test_native_staff_actor_stays_claimed_and_uses_same_failure_budget(portal):
    conn = portal[0]
    actor = asyncio.run(server._staff_count_actor(request(), conn, 'berts', '4826'))
    assert actor == ('shared-pin', 'shared_pin')
    for _ in range(5):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(server._staff_count_actor(request(), conn, 'berts', '0000'))
        assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.pg_verify_pin('berts', server.PgPinBodyIn(pin='4826'), request()))
    assert exc.value.status_code == 429


def test_mongo_and_pg_store_aliases_cannot_split_the_failure_budget(portal):
    for index in range(3):
        assert not asyncio.run(server._verify_legacy_staff_pin(request(host=f'192.0.2.{index}'), 'papa_leonis', '0000'))
    for index in range(2):
        assert not asyncio.run(server._verify_pg_staff_pin(request(host=f'198.51.100.{index}'), portal[0], 'papa', '0000'))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server._verify_legacy_staff_pin(request(host='2001:db8::1'), 'papa_leonis', '4826'))
    assert exc.value.status_code == 429


def test_previous_pin_session_is_rejected_without_changing_personal_credentials(portal):
    payload = {'sub': MEMBER['id'], 'email': 'staff:' + MEMBER['id'], 'role': 'manager',
               'locations': ['berts'], 'exp': int(time.time()) + 3600}
    raw = server._b64(json.dumps(payload).encode())
    token = raw + '.' + server._b64(hmac.new(server.AUTH_SECRET.encode(), raw.encode(), hashlib.sha256).digest())
    assert server._decode_token(token) is None
    with pytest.raises(HTTPException): server._require_manager(request(token=token))
    with pytest.raises(HTTPException) as exc: server._purchase_actor(request(token=token), 'berts', True)
    assert exc.value.status_code == 401
    with pytest.raises(HTTPException): server._token({'id': MEMBER['id'], 'email': payload['email'], 'role': 'manager'})
    personal = server._token({'id': 'usr_real_model', 'email': 'personal@example.test', 'role': 'manager', 'locations': ['berts']})
    assert server._decode_token(personal)['sub'] == 'usr_real_model'


def test_all_direct_pin_consumers_use_the_shared_check():
    tree = ast.parse(Path(server.__file__).read_text(encoding='utf-8'))
    allowed = {'_verify_legacy_staff_pin', '_verify_pg_staff_pin'}
    for function in [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        for node in ast.walk(function):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ('_get_pin', '_pg_get_staff_pin'):
                assert function.name in allowed, function.name
    assert 'DEFAULT_STAFF_PIN' not in Path(server.__file__).read_text(encoding='utf-8')


def test_shared_counter_expiry_isolation_success_and_capacity(tmp_path):
    now = [100.0]
    a = security.PinAttemptLimiter(tmp_path / 'counter.sqlite3', limit=2, window=60, capacity=2, clock=lambda: now[0])
    b = security.PinAttemptLimiter(a.path, limit=2, window=60, capacity=2, clock=lambda: now[0])
    ticket = a.reserve('store-client-a'); a.refund(ticket)
    a.reserve('store-client-a'); b.reserve('store-client-a')
    with pytest.raises(HTTPException) as exc: a.reserve('store-client-a')
    assert exc.value.status_code == 429
    b.reserve('store-client-b')
    with pytest.raises(HTTPException) as exc: a.reserve('new-client')
    assert exc.value.status_code == 429
    now[0] = 161
    fresh = a.reserve('store-client-a')
    a.refund(ticket)  # An old completion cannot refund the new window.
    b.reserve('store-client-a')
    with pytest.raises(HTTPException): a.reserve('store-client-a')
    assert fresh.expires == 221


def test_counter_coordinates_threads_and_another_process(tmp_path):
    a = security.PinAttemptLimiter(tmp_path / 'counter.sqlite3')
    def attempt(_):
        try: a.reserve('same-key'); return 200
        except HTTPException as exc: return exc.status_code
    with ThreadPoolExecutor(max_workers=8) as workers: results = list(workers.map(attempt, range(8)))
    assert sorted(results) == [200] * 5 + [429] * 3
    code = '''from staff_pin_security import PinAttemptLimiter
from fastapi import HTTPException
import sys
try: PinAttemptLimiter(sys.argv[1]).reserve('same-key')
except HTTPException as exc: print(exc.status_code)
'''
    process = subprocess.run([sys.executable, '-c', code, str(a.path)], capture_output=True, text=True,
                             timeout=20, check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert process.stdout.strip() == '429'


def test_store_key_is_namespaced_and_separates_stores():
    assert security.store_key('berts') != security.store_key('rudds')
    assert security.store_key('berts') != security.store_key('papa')
    assert security.store_key('berts') == security.store_key('berts')
    assert len(security.store_key('berts')) == 64
    # Do not reinterpret old per-client entries as store-wide reservations.
    previous = hashlib.sha256(json.dumps(['berts', '127.0.0.1'], separators=(',', ':')).encode()).hexdigest()
    assert security.store_key('berts') != previous


@pytest.mark.parametrize('pg', [False, True])
@pytest.mark.parametrize('profile', ['provider-wildcard', 'exact-proxy', 'no-proxy'])
def test_store_budget_survives_server_proxy_pipeline(portal, monkeypatch, pg, profile):
    monkeypatch.setattr(server, 'USE_PG', pg)
    monkeypatch.setattr(security.limiter, 'clock', lambda: 1000)
    # Exercise the dependency actually pinned by this repository, including its
    # environment-configured middleware. Direct Request tests omit this boundary.
    pinned = next(line.split('==')[1] for line in
                  Path(server.__file__).with_name('requirements.txt').read_text().splitlines()
                  if line.startswith('uvicorn=='))
    assert uvicorn.__version__ == pinned
    monkeypatch.setenv('FORWARDED_ALLOW_IPS', '*')  # Synthetic provider profile.
    seen_clients = []
    async def observed_app(scope, receive, send):
        seen_clients.append(scope.get('client'))
        await server.app(scope, receive, send)
    config = Config(observed_app, proxy_headers=profile != 'no-proxy',
                    forwarded_allow_ips='192.0.2.10' if profile == 'exact-proxy' else None,
                    lifespan='off', http='h11', ws='none', interface='asgi3', log_config=None)
    assert config.forwarded_allow_ips == ('192.0.2.10' if profile == 'exact-proxy' else '*')
    config.load()
    app = config.loaded_app
    verify = '/api/pg/staff/berts/verify' if pg else '/api/staff/verify'
    identify = ('/api/pg' if pg else '/api') + '/staff/berts/identify'
    body = {'pin': '000', 'restaurantId': 'berts', 'staffId': MEMBER['id']}
    original_headers = [(b'x-forwarded-for', b'198.51.100.10')]
    for index in range(5):
        response = asyncio.run(post(verify if index % 2 == 0 else identify, body,
                                    app=app, host='192.0.2.10', headers=original_headers))
        assert response.status_code in (200, 403)
        if response.status_code == 200: assert response.json()['ok'] is False
    # Unchanged / changed / unchanged controls, followed by malformed, duplicate
    # and IPv6 attribution. All must remain blocked without reading the PIN.
    variants = [
        ('192.0.2.10', original_headers),
        ('192.0.2.10', [(b'x-forwarded-for', b'203.0.113.123, 198.51.100.10')]),
        ('192.0.2.10', original_headers),
        ('192.0.2.11', []),
        ('2001:db8::10', [(b'x-forwarded-for', b'2001:db8::20')]),
        ('not-an-address', [(b'x-forwarded-for', b'unknown')]),
        ('192.0.2.10', [(b'x-forwarded-for', b'203.0.113.1'),
                       (b'x-forwarded-for', b'203.0.113.2')]),
        ('192.0.2.12', [(b'forwarded', b'for=203.0.113.5;proto=https')]),
    ]
    async def must_not_read(*args): raise AssertionError('Blocked admission read a PIN')
    monkeypatch.setattr(server, '_pg_get_staff_pin' if pg else '_get_pin', must_not_read)
    for host, headers in variants:
        response = asyncio.run(post(verify, body, app=app, host=host, headers=headers))
        assert response.status_code == 429 and int(response.headers['retry-after']) == 61
    expected_original = '192.0.2.10' if profile == 'no-proxy' else '198.51.100.10'
    expected_changed = ('203.0.113.123' if profile == 'provider-wildcard' else expected_original)
    assert seen_clients[5][0] == seen_clients[7][0] == expected_original
    assert seen_clients[6][0] == expected_changed
    assert len({client[0] for client in seen_clients}) > 1
    # Personal authority bypasses the PIN check, not its own authorization rules.
    token = server._token({'id': 'usr_fictional_owner', 'email': 'owner@example.test', 'role': 'owner'})
    response = asyncio.run(post(verify, body, token, app=app, host='192.0.2.10'))
    assert response.status_code == 200 and response.json()['ok'] is True


def test_different_clients_share_failures_but_not_different_stores(portal):
    for index in range(5):
        assert not asyncio.run(server._verify_legacy_staff_pin(request(host=f'192.0.2.{index}'), 'berts', '0000'))
    assert asyncio.run(server._verify_legacy_staff_pin(request(host='192.0.2.99'), 'rudds', '4826'))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server._verify_legacy_staff_pin(request(host='192.0.2.99'), 'berts', '4826'))
    assert exc.value.status_code == 429


def test_success_from_another_client_refunds_only_its_own_reservation(portal):
    for index in range(4):
        assert not asyncio.run(server._verify_legacy_staff_pin(request(host=f'192.0.2.{index}'), 'berts', '0000'))
    assert asyncio.run(server._verify_legacy_staff_pin(request(host='2001:db8::1'), 'berts', '4826'))
    assert not asyncio.run(server._verify_legacy_staff_pin(request(host='192.0.2.50'), 'berts', '0000'))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server._verify_legacy_staff_pin(request(host='2001:db8::2'), 'berts', '4826'))
    assert exc.value.status_code == 429


def test_concurrent_clients_reserve_one_store_budget_before_pin_reads(portal):
    async def run():
        entered = 0
        release = asyncio.Event()
        async def load():
            nonlocal entered
            entered += 1
            if entered == 5: release.set()
            await asyncio.wait_for(release.wait(), 10)
            return '4826'
        async def attempt(index):
            try:
                assert not await security.verify(request(host=f'192.0.2.{index}'), 'berts', '0000', load)
                return 200
            except HTTPException as error: return error.status_code
        results = await asyncio.gather(*(attempt(index) for index in range(8)))
        assert sorted(results) == [200] * 5 + [429] * 3
        assert entered == 5
    asyncio.run(run())


def test_disabled_pin_budget_is_shared_and_expiry_reopens_only_next_window(portal, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(security.limiter, 'clock', lambda: now[0])
    portal[0].pin = portal[1].settings.pin = None
    for index in range(5):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(server._verify_legacy_staff_pin(request(host=f'192.0.2.{index}'), 'berts', ''))
        assert exc.value.status_code == 403
    now[0] = 159
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server._verify_legacy_staff_pin(request(host='192.0.2.99'), 'berts', ''))
    assert exc.value.status_code == 429
    now[0] = 160
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server._verify_legacy_staff_pin(request(host='192.0.2.99'), 'berts', ''))
    assert exc.value.status_code == 403


def test_pin_refund_storage_failure_never_authenticates(portal, monkeypatch):
    def unavailable(ticket): raise HTTPException(503, 'Fictional unavailable counter')
    monkeypatch.setattr(security.limiter, 'refund', unavailable)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server._verify_legacy_staff_pin(request(), 'berts', '4826'))
    assert exc.value.status_code == 503


def test_unavailable_counter_fails_closed(tmp_path):
    bad = tmp_path / 'not-a-directory'; bad.write_text('fictional', encoding='utf-8')
    with pytest.raises(HTTPException) as exc: security.PinAttemptLimiter(bad / 'counter.sqlite3').reserve('key')
    assert exc.value.status_code == 503


@pytest.mark.parametrize('supplied', [None, True, 4826, {}, '１２３４', '\ud800'])
def test_malformed_supplied_pin_refuses_without_encoding_errors(portal, supplied):
    assert asyncio.run(server._verify_legacy_staff_pin(request(), 'berts', supplied)) is False


def test_pin_reader_failure_refunds_reservation(portal):
    for index in range(4):
        assert not asyncio.run(server._verify_legacy_staff_pin(request(host=f'192.0.2.{index}'), 'berts', '0000'))
    async def unavailable(): raise RuntimeError('fictional-read-failure')
    with pytest.raises(RuntimeError):
        asyncio.run(security.verify(request(), 'berts', '4826', unavailable))
    assert not asyncio.run(server._verify_legacy_staff_pin(request(host='2001:db8::1'), 'berts', '0000'))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server._verify_legacy_staff_pin(request(), 'berts', '0000'))
    assert exc.value.status_code == 429
