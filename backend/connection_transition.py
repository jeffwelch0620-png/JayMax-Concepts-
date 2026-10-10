"""Explicit paired-pool preparation; no global pool or active configuration swap.

Only a verified overlap and a bound, immutable client revision permit overlap.
URL fingerprints stay in memory, excluded from repr and all public receipts.
"""
import asyncio
from dataclasses import dataclass, field
import hashlib
import re
from urllib.parse import unquote, urlsplit
from uuid import UUID
import transition_permissions as permissions

CHECK_TIMEOUT = {'inventory': 240, 'accounts': 60}
_BOUND = object()


@dataclass(frozen=True)
class ClientRevision:
    context: permissions.VerifiedOverlap
    client_id: str
    revision_id: str
    reference: str
    roles: tuple
    _url_digests: tuple = field(repr=False)
    _proof: object = field(repr=False, compare=False)

    def validate(self, url, profile):
        if self._proof is not _BOUND or profile not in permissions.PROFILES:
            raise permissions.TransitionError('Bound client revision required')
        if hashlib.sha256(url.encode()).digest() != dict(self._url_digests)[profile]:
            raise permissions.TransitionError('Connection differs from bound client revision')
        role = _endpoint(self.context, url, profile, self.reference)
        if role != dict(self.roles)[profile]:
            raise permissions.TransitionError('Client role binding differs')
        return role


def _endpoint(context, url, profile, reference):
    if reference == 'hosted_build':
        return permissions.endpoint_role(context, url, profile)
    if reference != 'local':
        raise permissions.TransitionError('Explicit reviewed catalog reference required')
    uri = urlsplit(url)
    if (uri.scheme not in ('postgres', 'postgresql') or uri.hostname != '127.0.0.1'
            or uri.port is None or uri.query or uri.fragment
            or not re.fullmatch(r'/native_purchase_test_[a-f0-9]{32}', uri.path)):
        raise permissions.TransitionError('Unique disposable loopback target required')
    role = unquote(uri.username or '')
    context.cohort(profile, role)
    return role


def bind_revision(context, urls, *, client_id, revision_id, reference='hosted_build'):
    """Bind the controller's registered client/config revision; never read env.

    The trusted controller must obtain registration and configuration provenance
    independently. This factory does not authorize applying policies or retiring
    roles, and is not a persistent registration or a deployment approval.
    """
    if (not isinstance(context, permissions.VerifiedOverlap) or set(urls) != set(permissions.PROFILES)
            or not re.fullmatch(r'[a-z][a-z0-9_-]{1,63}', client_id or '')):
        raise permissions.TransitionError('Exact registered client pair required')
    try:
        if str(UUID(revision_id)) != revision_id:
            raise ValueError
        roles = {kind: _endpoint(context, urls[kind], kind, reference) for kind in permissions.PROFILES}
        endpoints = [urlsplit(urls[kind]) for kind in permissions.PROFILES]
        if len({(uri.hostname, uri.port or 5432, uri.path) for uri in endpoints}) != 1:
            raise permissions.TransitionError('Paired clients must share the exact endpoint')
        identities = context.identities()
        phases = {phase for kind, role in roles.items() for phase, value in identities[kind].items() if value['name'] == role}
        if len(phases) != 1:
            raise permissions.TransitionError('Mixed original and replacement revision held')
        return ClientRevision(context, client_id, revision_id, reference, tuple(roles.items()),
            tuple((kind, hashlib.sha256(urls[kind].encode()).digest()) for kind in permissions.PROFILES), _BOUND)
    except (ValueError, TypeError, AttributeError):
        raise permissions.TransitionError('Client revision target or identity held') from None


async def inspect_connection(conn, url, profile, revision):
    if not isinstance(revision, ClientRevision):
        raise permissions.TransitionError('Bound client revision required')
    role = revision.validate(url, profile)
    if dict(await conn.fetchrow('SELECT session_user AS login,current_user AS current')) != {'login': role, 'current': role}:
        raise permissions.TransitionError('Actual client LOGIN differs from revision')
    import runtime_permissions
    import auxiliary_permissions
    assessment = (runtime_permissions.inspect(conn, role, revision.reference, transition=revision.context)
                  if profile == 'inventory' else auxiliary_permissions.inspect(conn, transition=revision.context))
    report = await asyncio.wait_for(assessment, CHECK_TIMEOUT[profile])
    expected = 'passed_local_candidate' if profile == 'inventory' else 'passed'
    if (report['status'] != expected or not report['readOnly'] or report['policyMode'] != 'reviewed_overlap'
            or report['transitionRecordSha256'] != revision.context.record_sha256
            or report['issues'] or report['operationalReleaseApproved']):
        raise permissions.TransitionError('Client transition permission assessment held')
    if profile == 'inventory' and report.get('catalogReference') != revision.reference:
        raise permissions.TransitionError('Inventory catalog reference differs from client revision')
    return report


async def close_owned(pool):
    """Bounded cleanup of a pool created by this attempt only."""
    try:
        await asyncio.wait_for(pool.close(), 20)
    except BaseException:
        pool.terminate()
        raise


@dataclass
class PreparedPools:
    revision: ClientRevision
    inventory: object = field(repr=False)
    accounts: object = field(repr=False)
    _closed: bool = field(default=False, repr=False)

    def receipt(self):
        return {'format': 'jaymax-prepared-transition-pools-v1', 'clientId': self.revision.client_id,
                'revisionId': self.revision.revision_id, 'projectRef': self.revision.context.project,
                'roles': dict(self.revision.roles), 'transitionRecordSha256': self.revision.context.record_sha256,
                'catalogReference': self.revision.reference, 'ownedPoolsClosed': self._closed,
                'globalPoolsChanged': False, 'applicationConfigurationChanged': False,
                'oldRolesRetired': False, 'operationalReleaseApproved': False}

    async def close(self):
        if self._closed:
            return
        failed = False
        interrupted = None
        for pool in (self.accounts, self.inventory):
            try:
                await close_owned(pool)
            except BaseException as exc:
                if isinstance(exc, Exception):
                    failed = True
                else:
                    interrupted = interrupted or exc
        self._closed = True
        if interrupted is not None:
            raise interrupted
        if failed:
            raise permissions.TransitionError('Owned transition pool cleanup held')

    async def __aenter__(self):
        if self._closed:
            raise permissions.TransitionError('Prepared pools already closed')
        return self

    async def __aexit__(self, *unused):
        await self.close()


async def prepare_pair(revision, urls):
    """Use both actual constructors; return all-or-none without promoting pools."""
    if not isinstance(revision, ClientRevision) or set(urls) != set(permissions.PROFILES):
        raise permissions.TransitionError('Exact bound revision pair required')
    for kind in permissions.PROFILES:
        revision.validate(urls[kind], kind)
    import db_pg
    import db_auxiliary
    owned = []
    try:
        inventory = await db_pg._try_connect(urls['inventory'], transition=revision)
        if inventory is None:
            raise permissions.TransitionError('Inventory transition pool held')
        owned.append(inventory)
        accounts = await db_auxiliary._try_connect(urls['accounts'], transition=revision)
        if accounts is None:
            raise permissions.TransitionError('Account transition pool held')
        owned.append(accounts)
        return PreparedPools(revision, inventory, accounts)
    except BaseException:
        for pool in reversed(owned):
            try:
                await close_owned(pool)
            except BaseException:
                pass
        raise
