"""Local-only S1 request boundary. No hosted activation or ambient credentials.

The future hosted adapter must be reviewed and source/approval-bound separately.
This module deliberately refuses every non-fictional/non-loopback destination.
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import getpass
import json
import re
import sys
import time
from types import MappingProxyType
from urllib.parse import urlsplit
import warnings

import httpx

CAP = 65536
ROLES = ('owner', 'manager', 'staff')
FORMAT = 's1-local-request-transport-v1'
CLEANUP_RESERVE_SECONDS = 120
SESSION_TTL_SECONDS_DEFAULT = 28800


def utc_now():
    return datetime.now(timezone.utc)


class Held(ValueError):
    """Fixed categories only; never include a request, response or exception."""


def protected_input(label):
    """Operator-owned terminal only. Refuse getpass's echoing fallback.

    No stdin pipe, environment, argument, browser storage or credential lookup.
    Python/HTTP libraries cannot promise forensic zeroization of memory copies.
    """
    if label not in ('email', 'password', 'pin') or not sys.stdin.isatty():
        raise Held('protected_input_unavailable')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            value = getpass.getpass('Fictional local rehearsal ' + label + ': ')
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        raise Held('protected_input_unavailable') from None
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise Held('protected_input_invalid')
    return value


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise Held('response_shape')
        value[key] = item
    return value


@dataclass(frozen=True)
class Step:
    method: str
    path: str
    actor: str
    status: int
    shape: str
    forwarded: str | None = None


VERIFY = '/api/pg/staff/berts/verify'
IDENTIFY = '/api/pg/staff/berts/identify'
STEPS = {
    'P01': Step('POST', VERIFY, 'anonymous', 200, 'yes'),
    'P02': Step('POST', IDENTIFY, 'anonymous', 200, 'identified'),
    'P03': Step('POST', VERIFY, 'anonymous', 200, 'no'),
    'P04': Step('POST', IDENTIFY, 'anonymous', 403, 'error'),
    'P05': Step('POST', VERIFY, 'anonymous', 200, 'no'),
    'P06': Step('POST', IDENTIFY, 'anonymous', 403, 'error'),
    'P07': Step('POST', VERIFY, 'anonymous', 200, 'no'),
    'P08': Step('POST', VERIFY, 'anonymous', 429, 'throttled', '192.0.2.19'),
    'P09': Step('POST', VERIFY, 'anonymous', 429, 'throttled'),
    'P10': Step('POST', VERIFY, 'anonymous', 200, 'yes'),
    'P11': Step('POST', IDENTIFY, 'anonymous', 200, 'identified'),
    'P12': Step('GET', '/api/auth/users', 'anonymous', 401, 'error'),
}
for _role, _a, _b in (('owner', 'R01', 'R02'), ('manager', 'R03', 'R04'), ('staff', 'R05', 'R06')):
    STEPS[_a] = Step('GET', '/api/auth/me', _role, 200, 'me')
    STEPS[_b] = Step('GET', '/api/auth/users', _role, 200 if _role == 'owner' else 403,
                     'users' if _role == 'owner' else 'error')
STEPS = MappingProxyType(STEPS)


@dataclass(repr=False)
class Session:
    token: str = field(repr=False)
    subject: str = field(repr=False)
    email: str = field(repr=False)
    role: str

    def __repr__(self):
        return '<private personal session>'


class LocalTransport:
    """Single-use ledger and isolated per-request clients; local rehearsal only.

    guard() checks the caller's local source/resource bindings. It must raise on
    failure. Wall and monotonic deadlines also run inside every request. The
    local claim is in memory: durable cross-process live claiming is NOT enabled.
    """
    @staticmethod
    def _check_destination(origin, transport):
        try:
            parsed = urlsplit(origin)
            port = parsed.port
        except (ValueError, TypeError, AttributeError):
            raise Held('hosted_execution_disabled') from None
        fixture = origin == 'https://s1-fixture.invalid' and type(transport) in (
            httpx.MockTransport, httpx.ASGITransport)
        loopback = (parsed.scheme == 'http' and parsed.hostname == '127.0.0.1'
                    and port is not None and 1024 <= port <= 65535
                    and parsed.netloc == '127.0.0.1:' + str(port)
                    and origin == 'http://127.0.0.1:' + str(port)
                    and not parsed.path and not parsed.query and not parsed.fragment
                    and transport is None)
        if not fixture and not loopback:
            raise Held('hosted_execution_disabled')

    def __init__(self, origin, *, approved, guard, ends_at, stop_checks_at,
                 transport=None, clock=time.monotonic,
                 seconds=780, request_seconds=90):
        self._check_destination(origin, transport)
        if approved is not True or not callable(guard):
            raise Held('local_approval_required')
        if not 0 < seconds <= 780 or not 0 < request_seconds <= 90:
            raise Held('invalid_deadline')
        try:
            if any(not isinstance(value, datetime) or value.utcoffset() is None
                   for value in (ends_at, stop_checks_at)):
                raise ValueError
            ends_at, stop_checks_at = (value.astimezone(timezone.utc)
                                      for value in (ends_at, stop_checks_at))
            if (stop_checks_at <= utc_now() or ends_at <= utc_now()
                    or (ends_at - stop_checks_at).total_seconds() < CLEANUP_RESERVE_SECONDS):
                raise ValueError
        except (ValueError, TypeError, OverflowError):
            raise Held('invalid_deadline') from None
        self._origin, self._transport, self._guard = origin, transport, guard
        self._clock, self._until = clock, clock() + seconds
        self._request_seconds = request_seconds
        self._budget_until = time.monotonic() + seconds
        self._ends_at, self._stop_checks_at = ends_at, stop_checks_at
        self._used, self._passed, self._sessions, self._facts = set(), set(), {}, []
        self._recovery_at = None
        self._steps = STEPS
        self._closed = False
        self._busy = False
        self._check()

    def _check(self):
        if (self._closed or self._clock() >= self._until or time.monotonic() >= self._budget_until
                or utc_now() >= self._stop_checks_at or utc_now() >= self._ends_at):
            raise Held('window_closed')
        try:
            self._guard()
        except Exception:
            raise Held('local_guard_failed') from None

    def _remaining(self):
        now = utc_now()
        return min(self._until - self._clock(), self._budget_until - time.monotonic(),
                   (self._stop_checks_at - now).total_seconds(), (self._ends_at - now).total_seconds())

    def _recovery_gate(self, label):
        self._check()
        if label not in ('P10', 'P11'):
            return
        if self._recovery_at is None:
            raise Held('throttle_sequence_required')
        delay = max(0, self._recovery_at - self._clock())
        if self._recovery_at >= self._until or delay >= self._remaining():
            raise Held('window_insufficient_for_recovery')
        if self._clock() < self._recovery_at:
            raise Held('throttle_wait_required')
        if label == 'P11' and 'P10' not in self._passed:
            raise Held('recovery_verification_required')

    async def _watch(self):
        while True:
            self._check()
            await asyncio.sleep(.05)

    async def _exchange(self, step, body, session, budget):
        headers = {'Accept': 'application/json', 'Accept-Encoding': 'identity'}
        if step.forwarded:
            headers['X-Forwarded-For'] = step.forwarded
        if session:
            headers['Authorization'] = 'Bearer ' + session.token
        # A fresh client per exchange prevents Set-Cookie from contaminating any
        # following anonymous/personal request. No arbitrary headers are accepted.
        async with httpx.AsyncClient(transport=self._transport, verify=self._tls_verify(), trust_env=False,
                follow_redirects=False, timeout=httpx.Timeout(budget, connect=min(6, budget))) as client:
            self._check()
            async with client.stream(step.method, self._origin + step.path,
                                     headers=headers, json=body) as response:
                if response.status_code != step.status:
                    raise Held('unexpected_status')
                if response.headers.get('content-encoding', 'identity') != 'identity':
                    raise Held('encoded_response')
                if response.headers.get('content-type', '').split(';')[0].strip() != 'application/json':
                    raise Held('response_type')
                size = response.headers.get('content-length')
                if size is not None and (len(size) > 8 or not size.isascii() or not size.isdigit() or int(size) > CAP):
                    raise Held('response_size')
                raw = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    self._check()
                    if len(raw) + len(chunk) > CAP:
                        raise Held('response_size')
                    raw.extend(chunk)
                try:
                    value = json.loads(raw, object_pairs_hook=unique,
                                       parse_constant=lambda _: (_ for _ in ()).throw(Held('response_shape')))
                except (ValueError, UnicodeError, RecursionError):
                    raise Held('response_shape') from None
                return value, response.headers.get('retry-after')

    def _tls_verify(self):
        return True

    async def _send(self, label, step, body=None, session=None):
        self._recovery_gate(label)
        if label in self._used or self._busy:
            raise Held('request_already_claimed')
        budget = min(self._request_seconds, 90 if label == 'P01' else 6, self._remaining())
        if budget <= 0:
            raise Held('window_closed')
        self._used.add(label)  # Ambiguous send/timeout consumes its slot too.
        self._busy = True
        exchange = asyncio.create_task(self._exchange(step, body, session, budget))
        watch = asyncio.create_task(self._watch())
        fact = {'request': label, 'outcome': 'held'}
        try:
            async with asyncio.timeout(min(budget, self._remaining())):
                done, _ = await asyncio.wait((exchange, watch), return_when=asyncio.FIRST_COMPLETED)
                if watch in done:
                    watch.result()
                result = await exchange
                self._check()
                return result, fact
        except asyncio.CancelledError:
            fact['outcome'] = 'cancelled'
            raise
        except Held:
            raise
        except Exception:
            raise Held('request_failed') from None
        finally:
            for task in (exchange, watch):
                if not task.done():
                    task.cancel()
            await asyncio.gather(exchange, watch, return_exceptions=True)
            self._busy = False
            self._facts.append(fact)

    async def login(self, role, email, password):
        """Only the existing login endpoint may populate a private session."""
        if role not in ROLES or not isinstance(email, str) or not isinstance(password, str):
            raise Held('login_input')
        if not email or len(email) > 320 or not password or len(password) > 1024:
            raise Held('login_input')
        label = 'L0' + str(ROLES.index(role) + 1)
        (value, _), fact = await self._send(label, Step('POST', '/api/auth/login',
            'anonymous', 200, 'login'), {'email': email, 'password': password})
        if not isinstance(value, dict) or set(value) != {'token', 'user'}:
            raise Held('login_shape')
        user, token = value['user'], value['token']
        if (not isinstance(user, dict) or user.get('role') != role
                or user.get('email') != email.strip().lower()
                or not isinstance(user.get('id'), str) or not user['id']
                or not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{16,8192}', token)):
            raise Held('login_identity')
        if any(other.subject == user['id'] for other in self._sessions.values()):
            raise Held('login_identity')
        self._validate_login(user)
        self._check()
        self._sessions[role] = Session(token, user['id'], user['email'], role)
        fact['outcome'] = 'passed'

    def _validate_login(self, user):
        pass

    def _validate_me(self, value, session):
        return (isinstance(value, dict) and value.get('sub') == session.subject
                and value.get('role') == session.role and value.get('email') == session.email)

    def _validate_roster(self, value):
        return True

    async def login_from_terminal(self, role):
        self._check()
        if role not in ROLES or 'L0' + str(ROLES.index(role) + 1) in self._used:
            raise Held('login_input')
        email = password = None
        try:
            email = protected_input('email')
            password = protected_input('password')
            await self.login(role, email, password)
        finally:
            email = password = None

    async def pin_from_terminal(self, label, *, staff_id=None):
        self._recovery_gate(label)
        if label not in self._steps or self._steps[label].path not in (VERIFY, IDENTIFY) or label in self._used:
            raise Held('unknown_request')
        pin = None
        try:
            pin = protected_input('pin')
            return await self.probe(label, pin=pin, staff_id=staff_id)
        finally:
            pin = None

    def _valid_pin_input(self,label,pin):
        return isinstance(pin,str) and re.fullmatch(r'[0-9]{4,8}',pin) is not None

    async def probe(self, label, *, pin=None, staff_id=None):
        if label not in self._steps:
            raise Held('unknown_request')
        self._recovery_gate(label)
        step = self._steps[label]
        session = self._sessions.get(step.actor)
        if step.actor != 'anonymous' and session is None:
            raise Held('personal_login_required')
        body = None
        if step.path in (VERIFY, IDENTIFY):
            if not self._valid_pin_input(label,pin):
                raise Held('pin_input')
            if step.path == VERIFY and staff_id is not None:
                raise Held('unexpected_input')
            body = {'pin': pin}
            if step.path == IDENTIFY:
                if not isinstance(staff_id, str) or not re.fullmatch(
                        r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', staff_id):
                    raise Held('staff_input')
                body['staffId'] = staff_id
        elif pin is not None or staff_id is not None:
            raise Held('unexpected_input')
        (value, retry), fact = await self._send(label, step, body, session)
        valid = False
        if step.shape == 'no':
            valid = isinstance(value, dict) and set(value) == {'ok'} and value['ok'] is False
        elif step.shape == 'yes':
            valid = (isinstance(value, dict) and set(value) == {'ok', 'staff'} and value['ok'] is True
                     and isinstance(value['staff'], list) and all(isinstance(v, dict)
                         and set(v) == {'id', 'name', 'role', 'active'}
                         and all(isinstance(v[k], str) for k in ('id', 'name', 'role'))
                         and type(v['active']) is bool for v in value['staff']))
            valid = valid and self._validate_roster(value)
        elif step.shape == 'identified':
            valid = (isinstance(value, dict) and set(value) == {'ok', 'name', 'role'}
                     and value['ok'] is True and isinstance(value['name'], str) and bool(value['name'])
                     and value['role'] == 'owner_admin')
        elif step.shape == 'disabled':
            valid = value == {'detail': 'Staff PIN portal is disabled. Ask a manager to set a PIN.'}
        elif step.shape in ('error', 'throttled'):
            valid = isinstance(value, dict) and set(value) == {'detail'} and isinstance(value['detail'], str)
            if step.shape == 'throttled':
                valid = valid and isinstance(retry, str) and 1 <= len(retry) <= 2 and retry.isascii() and retry.isdigit() and 1 <= int(retry) <= 61
        elif step.shape == 'me':
            valid = self._validate_me(value, session)
        elif step.shape == 'users':
            valid = isinstance(value, list) and all(isinstance(v, dict) and set(v) <= {
                'id', 'email', 'role', 'locations', 'createdAt'} and {'id', 'email', 'role'} <= set(v) for v in value)
        if not valid:
            raise Held('probe_shape')
        self._check()
        fact.update(outcome='passed', httpStatus=step.status)
        self._passed.add(label)
        if step.shape == 'throttled':
            fact['retryAfterSeconds'] = int(retry)
            if label == 'P09':
                self._recovery_at = self._clock() + int(retry) + 1
        return dict(fact)  # Never return response bodies, tokens, PINs or actors.

    def receipt(self):
        return {'format': FORMAT, 'localOnly': True, 'closed': self._closed,
                'serverSideRevocation': 'not_available',
                'sessionTtlSecondsDefault': SESSION_TTL_SECONDS_DEFAULT,
                'requests': [dict(fact) for fact in self._facts]}

    def close(self):
        self._sessions.clear()
        self._closed = True
