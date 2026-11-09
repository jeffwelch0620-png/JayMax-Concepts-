"""Open manager sessions follow their login (data-safety audit 2026-11-08): removing a store, changing the
position or deleting the login ends sessions already open, instead of waiting up to 8 hours for the token."""
import asyncio

import httpx
from fastapi import Response
from starlette.requests import Request

import deployment_readiness
import server

KM = {'id': 'usr_km', 'email': 'km@example.invalid', 'role': 'manager', 'locations': ['berts', 'rudds'], 'position': 'KM'}
OWNER = {'id': 'usr_owner', 'email': 'owner@example.invalid', 'role': 'owner', 'locations': ['berts', 'rudds', 'papa_leonis']}


class Accounts:
    """The account pool, holding invented logins by id."""
    def __init__(self, *users, fail=False):
        self.rows = {u['id']: {**u, 'position': u.get('position')} for u in users}
        self.fail = fail; self.reads = 0

    async def fetchrow(self, _, user_id):
        self.reads += 1
        if self.fail: raise OSError('account database unreachable')
        return self.rows.get(user_id)

    async def fetchval(self, _, user_id):  # DELETE ... RETURNING id
        return self.rows.pop(user_id, {}).get('id')


def setup(monkeypatch, accounts):
    monkeypatch.setattr(server, 'AUTH_SECRET', 'TEST-ONLY-account-recheck-secret')
    monkeypatch.setattr(server, 'AUTH_REQUIRED', True)
    monkeypatch.setattr(server, 'USE_PG', True)
    monkeypatch.setattr(server, 'ACCOUNT_RECHECK', True)
    monkeypatch.setattr(server, '_account_cache', {})
    monkeypatch.setattr(server.db_auxiliary, 'pool', lambda: accounts)
    async def no_activity(*args): pass
    monkeypatch.setattr(server, '_record_activity', no_activity)


def call(token, path='/api/pg/purchases/rudds/documents', method='POST'):
    request = Request({'type': 'http', 'method': method, 'path': path, 'query_string': b'',
                       'headers': [(b'authorization', ('Bearer ' + token).encode())],
                       'scheme': 'http', 'server': ('testserver', 80), 'client': ('127.0.0.1', 1)})
    async def ok(_): return Response(status_code=204)
    return asyncio.run(server.collaboration_security(request, ok))


def test_a_current_login_passes_and_is_read_once_per_window(monkeypatch):
    accounts = Accounts(KM); setup(monkeypatch, accounts)
    token = server._token(KM)
    assert [call(token).status_code for _ in range(3)] == [204, 204, 204]
    assert accounts.reads == 1


def test_a_removed_store_a_new_position_or_a_deleted_login_ends_open_sessions(monkeypatch):
    for change in (lambda r: r.update(locations=['berts']), lambda r: r.update(position='SL-BOH'), None):
        accounts = Accounts(KM); setup(monkeypatch, accounts)
        token = server._token(KM)
        if change: change(accounts.rows['usr_km'])
        else: accounts.rows.clear()
        refused = call(token)
        assert (refused.status_code, b'Sign in again' in refused.body) == (401, True)
        # Signing in again issues a session that matches the login as it is now.
        if change:
            assert call(server._token(accounts.rows['usr_km'])).status_code in (204, 403)


def test_deleting_a_login_ends_its_session_at_once_despite_the_cache(monkeypatch):
    accounts = Accounts(KM, OWNER); setup(monkeypatch, accounts)
    km, owner = server._token(KM), server._token(OWNER)
    assert call(km).status_code == 204  # now cached

    async def delete():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url='http://test') as client:
            return await client.delete('/api/auth/users/usr_km', headers={'Authorization': 'Bearer ' + owner})
    assert asyncio.run(delete()).status_code == 200
    assert call(km).status_code == 401


def test_an_unreachable_account_store_refuses_rather_than_trusting_the_token(monkeypatch):
    setup(monkeypatch, Accounts(KM, fail=True))
    assert call(server._token(KM)).status_code == 503


def test_tokens_are_never_accepted_with_an_empty_signing_key(monkeypatch):
    monkeypatch.setattr(server, 'AUTH_SECRET', 'TEST-ONLY-account-recheck-secret')
    token = server._token(OWNER)
    monkeypatch.setattr(server, 'AUTH_SECRET', '')
    forged = token.split('.')[0] + '.' + server._b64(server.hmac.new(b'', token.split('.')[0].encode(), server.hashlib.sha256).digest())
    assert server._decode_token(forged) is None and server._decode_token(token) is None


def test_readiness_holds_a_deploy_that_turns_the_check_off():
    base = {'USE_PG': 'true'}, {'REACT_APP_USE_PG': 'true'}
    assert deployment_readiness.configuration(*base)['status'] == 'passed'
    held = deployment_readiness.configuration({**base[0], 'ACCOUNT_RECHECK': 'false'}, base[1])
    assert {'key': 'ACCOUNT_RECHECK', 'reason': 'Open sessions must follow store, position and login changes'} in held['problems']
