"""The sign-in gate decides from the path the router uses, never from the Host header (Starlette
advisory GHSA-86qp: a crafted Host header could make request.url.path read as a public path while
the request still reached a protected route)."""
import asyncio

import httpx
import pytest

import server

FORGED_HOSTS = ['testserver/api/health?', 'testserver/api/health#', 'testserver/api/auth/login?x=']


def send(host, path='/api/pg/purchases/berts/documents', token=None):
    async def go():
        headers = {'host': host}
        if token:
            headers['authorization'] = 'Bearer ' + token
        transport = httpx.ASGITransport(app=server.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url='http://testserver') as client:
            return await client.get(path, headers=headers)
    return asyncio.run(go())


@pytest.fixture
def gate(monkeypatch):
    monkeypatch.setattr(server, 'AUTH_SECRET', 'TEST-ONLY-host-header-secret')
    monkeypatch.setattr(server, 'AUTH_REQUIRED', True)
    monkeypatch.setattr(server, 'USE_PG', True)
    monkeypatch.setattr(server, 'ACCOUNT_RECHECK', False)
    async def no_activity(*args): pass
    monkeypatch.setattr(server, '_record_activity', no_activity)


@pytest.mark.parametrize('host', FORGED_HOSTS)
def test_a_forged_host_header_never_opens_a_protected_route(gate, host):
    response = send(host)
    assert response.status_code == 401, (host, response.status_code, response.text[:200])


@pytest.mark.parametrize('host', FORGED_HOSTS)
def test_a_forged_host_header_never_lifts_store_limits(gate, host):
    rudds_only = server._token({'id': 'usr_km', 'email': 'km@example.invalid', 'role': 'manager', 'locations': ['rudds']})
    response = send(host, token=rudds_only)
    assert response.status_code == 403, (host, response.status_code, response.text[:200])


def test_public_paths_stay_public(gate):
    assert send('testserver', '/api/health').status_code == 200
