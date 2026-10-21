"""Read-only permission observations, not an installer or hosted entry point.

The caller owns and must close the connection. No connection, credentials,
service controls, approval, backup or executable migration plan is created here.
Reports contain role names and belong in private operator evidence only.
"""
import asyncio
from datetime import datetime, timezone
import hashlib
from pathlib import Path

import apply_reviewed_par_migration as engine
from hosted_additive_index import Held, ledger_clients
from readonly_snapshot import error_details, readonly_snapshot

FORMAT = 'jaymax-par-role-preflight-v1'
RULES = ('flags', 'membership', 'ddl', 'ownership', 'default_acl', 'new_par_access')
MANAGED_SCOPES = ('public', 'extensions')
MAX_ROLES = 32
OPERATION_SECONDS = 60


def source_hashes():
    sources = engine.sources()
    sources['tools/ops/par_role_preflight.py'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return sources


async def backend_result(conn, role):
    checks = {rule: 'not_evaluated' for rule in RULES}
    try:
        # A refusal rolls back only this read-only savepoint. Continue with other
        # explicitly reviewed roles, without weakening the installer's short circuit.
        async with readonly_snapshot(conn, rollback_timeout=5):
            await engine.backend_permissions(conn, [role])
    except engine.BackendPermissionHeld as error:
        if (getattr(error, 'snapshotCleanupErrorType', None)
                or error.role != role or error.rule not in RULES):
            raise
        for rule in RULES:
            checks[rule] = 'held' if rule == error.rule else 'passed'
            if rule == error.rule:
                break
    else:
        checks = dict.fromkeys(RULES, 'passed')
    return checks


async def managed_observations(conn, role):
    """Supplemental observations; never change the installer's checked scope."""
    result = []
    for schema in MANAGED_SCOPES:
        row = await conn.fetchrow('''SELECT n.oid IS NOT NULL AS present,
            CASE WHEN n.oid IS NULL THEN false ELSE has_schema_privilege($1,n.oid,'CREATE') END AS can_create,
            COALESCE(n.nspowner=r.oid,false) AS owns_schema,
            EXISTS(SELECT 1 FROM pg_class c WHERE c.relnamespace=n.oid AND c.relowner=r.oid) AS owns_relation,
            EXISTS(SELECT 1 FROM pg_proc p WHERE p.pronamespace=n.oid AND p.proowner=r.oid) AS owns_function,
            EXISTS(SELECT 1 FROM pg_default_acl d,LATERAL aclexplode(d.defaclacl) a
                WHERE d.defaclnamespace=n.oid AND a.grantee IN (0,r.oid)) AS future_grant
            FROM pg_roles r LEFT JOIN pg_namespace n ON n.nspname=$2 WHERE r.rolname=$1''', role, schema)
        if row is None:
            raise ValueError('Reviewed role disappeared during preflight')
        result.append({'schema': schema, **dict(row)})
    # PUBLIC future grants are not represented by an explicit per-role grant.
    public_default = await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM pg_default_acl d,
        LATERAL aclexplode(d.defaclacl) a WHERE d.defaclnamespace=0 AND a.grantee=0)''')
    return {'status': 'observed', 'schemas': result, 'globalPublicDefaultGrant': public_default}


async def collect(conn, clients, backends):
    """Collect one bounded, consistent snapshot; propagate infrastructure failures.

    Accept a dedicated idle connection only. The caller must bound connection
    setup/close and validate its target/TLS before hosted use under
    separate approval. No deployment readiness or writer-drain claim is made.
    """
    try:
        async with asyncio.timeout(OPERATION_SECONDS):
            return await _collect(conn, clients, backends)
    except TimeoutError as error:
        # asyncio translates cancellation into a new TimeoutError. Preserve only
        # the bounded cleanup category already attached to the original failure.
        cleanup = error_details(error.__cause__)['snapshotCleanupErrorType']
        if cleanup is not None:
            error.snapshotCleanupErrorType = cleanup
        raise


async def _collect(conn, clients, backends):
    clients, backends = engine.role_groups(clients, backends)
    if not backends or len(clients) + len(backends) > MAX_ROLES:
        raise ValueError('Preflight requires reviewed backends and at most 32 roles')
    if tuple(engine.BackendPermissionHeld.MESSAGES) != RULES:
        raise ValueError('Installer rule contract changed; review preflight mapping')
    if conn.is_in_transaction():
        raise ValueError('Preflight requires an idle dedicated connection')
    report = {'format': FORMAT, 'createdAt': datetime.now(timezone.utc).isoformat(),
              'sourceHashes': source_hashes(), 'backendRoles': [], 'ledgerRoles': [],
              'automaticApply': False, 'operationalReleaseApproved': False,
              'scope': {'installerBackendRules': list(RULES),
                        'ddlAndOwnershipSchemas': list(engine.catalog.SCHEMAS) + ['supabase_migrations'],
                        'defaultAclSchemas': list(engine.readiness.PRIVATE) + ['supabase_migrations'],
                        'globalBackendDefaultAcls': True, 'managedObservations': list(MANAGED_SCOPES),
                        'clientPrivateAccess': 'not_evaluated', 'fullReadiness': 'not_evaluated',
                        'writerDrain': 'not_evaluated', 'backupAndRestore': 'not_evaluated',
                        'runtimeRlsCutover': 'not_evaluated'}}
    async with readonly_snapshot(conn, rollback_timeout=5):
        await conn.execute("SET LOCAL search_path=pg_catalog; "
                           "SET LOCAL statement_timeout='20s'; SET LOCAL lock_timeout='5s'; "
                           "SET LOCAL idle_in_transaction_session_timeout='30s'")
        report['snapshot'] = {'readOnly': await conn.fetchval('SHOW transaction_read_only'),
                              'isolation': await conn.fetchval('SHOW transaction_isolation'),
                              'searchPath': await conn.fetchval('SHOW search_path')}
        if report['snapshot'] != {'readOnly': 'on', 'isolation': 'repeatable read', 'searchPath': 'pg_catalog'}:
            raise ValueError('Reviewed read-only snapshot settings were not established')
        for role in backends:
            checks = await backend_result(conn, role)
            observations = ({'status': 'not_evaluated'} if checks['flags'] != 'passed'
                            else await managed_observations(conn, role))
            report['backendRoles'].append({'role': role, 'checks': checks,
                                           'managedObservations': observations})
        for role in clients + backends:
            if not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=$1)', role):
                report['ledgerRoles'].append({'role': role, 'status': 'held', 'reason': 'missing_role'})
                continue
            try:
                async with readonly_snapshot(conn, rollback_timeout=5):
                    await ledger_clients(conn, [role])
            except Held as error:
                if getattr(error, 'snapshotCleanupErrorType', None):
                    raise
                status = 'held'
            else:
                status = 'passed'
            report['ledgerRoles'].append({'role': role, 'status': status})
    # This is an observation receipt, not a successful installer preflight. Even
    # all passed narrow checks leave the explicitly excluded release gates open.
    report['status'] = 'observations_recorded'
    return report


def public_summary(report):
    """Only fixed counts/categories; never echo role names or driver messages."""
    if report.get('format') != FORMAT or report.get('status') != 'observations_recorded':
        raise ValueError('Unsupported preflight receipt')
    counts = dict.fromkeys(('passed', 'held', 'not_evaluated'), 0)
    for item in report['backendRoles']:
        for value in item['checks'].values():
            counts[value] += 1
    for item in report['ledgerRoles']:
        counts[item['status']] += 1
    return {'format': FORMAT, 'status': 'observations_recorded', 'checks': counts,
            'managedObservationRoles': sum(item['managedObservations']['status'] == 'observed'
                                           for item in report['backendRoles']),
            'managedFindings': sum(
                sum(bool(schema[field]) for schema in item['managedObservations'].get('schemas', [])
                    for field in ('can_create', 'owns_schema', 'owns_relation', 'owns_function', 'future_grant'))
                + bool(item['managedObservations'].get('globalPublicDefaultGrant'))
                for item in report['backendRoles']),
            'fullReadinessEvaluated': False, 'automaticApply': False,
            'operationalReleaseApproved': False}
