"""Manual, reviewed par-table installation on the designated Supabase build DB.

Preparing this adapter does not authorize hosted execution. No app configuration,
role changes, history repair, migration replay, retries or managed-service restore.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time


def require_runtime(version=None, platform=None):
    if (version or sys.version_info) < (3, 12):
        raise ValueError('Hosted adapter requires Python 3.12 or newer')
    if (platform or os.name) != 'nt':
        raise ValueError('Hosted adapter requires Windows and PowerShell 7')


# Check before third-party imports or any output/connection preparation.
if __name__ == '__main__':
    try:
        require_runtime()
    except ValueError as exc:
        print(json.dumps({'status': 'invocation_held', 'reason': str(exc), 'sqlCommitted': False}))
        raise SystemExit(2)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import asyncpg
from dotenv import dotenv_values
import apply_reviewed_par_migration as engine
from hosted_additive_index import (
    Held, sha, fingerprint, utc, maintenance, target, roles, writer_roles, server_version, writer_sessions, checked_json, ledger_clients, private_file, verify_acl, write_private)
from readonly_snapshot import readonly_snapshot, preserve_cleanup_failure, error_details
import hosted_backup as backup
from db_tls import connection_tls
from maintenance_connection import MaintenanceConnectionError

FORMAT = 'jaymax-hosted-reviewed-par-plan-v2'
REVIEW_FORMAT = 'jaymax-hosted-reviewed-par-review-v2'
BUDGETS = {'lockSeconds': 5, 'probeSeconds': 20, 'ddlSeconds': 30,
           'idleTransactionSeconds': 120, 'operationSeconds': 600}
LEDGER = 'supabase_migrations.schema_migrations'


def backend_roles(review):
    clients = roles(review)
    backends = review.get('backendRoles')
    if not isinstance(backends, list):
        raise Held('An explicit reviewed backend role list is required, including when empty')
    try:
        engine.role_groups(clients, backends)
    except ValueError:
        raise Held('Client and backend role groups are invalid or overlap') from None
    writers = set(writer_roles(review))
    if not set(backends) <= writers:
        raise Held('Every reviewed backend must remain in the writer LOGIN inventory')
    # postgres is the separately pinned administrative actor, not an ordinary
    # client to deny ledger access. Every other writer needs an explicit policy.
    if writers - {'postgres'} - set(clients) - set(backends):
        raise Held('Every non-administrative writer must have an explicit permission classification')
    return backends


def ledger_roles(review):
    return roles(review) + backend_roles(review)


def load_evidence(review, *, now=None, active=True):
    """Authenticate the backup; bind the isolated-restore receipt to that archive."""
    if review.get('format') != REVIEW_FORMAT or review.get('budgets') != BUDGETS:
        raise Held('Unsupported hosted review or unreviewed timeout budgets')
    backend_roles(review)
    writer_roles(review)
    now = now or datetime.now(timezone.utc)
    start, end = maintenance(review, now=now, active=active)
    item = review['backup']
    encrypted = Path(item['encryptedFile']).read_bytes()
    if sha(encrypted) != item['encryptedSha256']:
        raise Held('The reviewed encrypted backup changed')
    manifest, _ = backup.open_backup(item['encryptedFile'], item['keyFile'], review['projectRef'])
    restored = checked_json(item['restoreReceipt'], item['restoreReceiptSha256'])
    if (manifest.get('rowFingerprintAlgorithm') != backup.ROW_ALGORITHM
            or not re.fullmatch(r'[0-9]{6}', str(manifest.get('serverVersionNum', '')))
            or not start <= utc(manifest.get('createdAt')) <= now
            or utc(manifest.get('createdAt')) >= end
            or restored.get('status') != 'verified_application_restore'
            or restored.get('archiveSha256') != manifest['archiveSha256']
            or restored.get('majorVersionMatched') is not True
            or restored.get('tablesMatched') != len(manifest['tables'])
            or restored.get('catalogGroupsMatched') != len(manifest['catalog'])
            or LEDGER not in manifest['tables']):
        raise Held('A fresh matching application-and-ledger isolated restore is required')
    expected_hashes = {'migrations/' + name: sha((engine.readiness.ROOT / 'migrations' / name).read_bytes())
                       for name in engine.readiness.MIGRATIONS}
    if any(manifest.get('migrationFileHashes', {}).get(k) != v for k, v in expected_hashes.items()):
        raise Held('The backup was not captured against the current reviewed migration sources')
    original = checked_json(review['originalReceipt'], review['originalReceiptSha256'])
    source_index = checked_json(review['sourceIndexPlan'], review['sourceIndexPlanSha256'])
    engine.checked_prior(original, source_index)
    # The encrypted archive carries actual data; plans retain only fingerprints.
    facts = {key: manifest[key] for key in ('tables', 'catalog')}
    binding = {'encryptedSha256': item['encryptedSha256'], 'archiveSha256': manifest['archiveSha256'],
               'restoreReceiptSha256': item['restoreReceiptSha256'], 'factsSha256': fingerprint(facts),
               'createdAt': manifest['createdAt'], 'serverVersionNum': manifest['serverVersionNum'],
               'managedRecoveryVerified': False}
    return (original, source_index), facts, binding


def validate(plan, review, reviewed_target, binding):
    backend_roles(review)
    if review.get('format') != REVIEW_FORMAT:
        raise Held('A newly reviewed v2 par role classification is required')
    fields = {'format', 'createdAt', 'target', 'reviewSha256', 'backup', 'maintenance',
              'budgets', 'core', 'writerObservations', 'automaticApply', 'operationalReleaseApproved'}
    if (set(plan) != fields or plan.get('automaticApply') is not False
            or plan.get('operationalReleaseApproved') is not False
            or plan.get('format') != FORMAT or plan.get('target') != reviewed_target
            or plan.get('reviewSha256') != fingerprint(review) or plan.get('backup') != binding
            or plan.get('budgets') != BUDGETS or plan.get('maintenance') != review['maintenance']):
        raise Held('Hosted plan does not match the reviewed target, backup or maintenance evidence')
    if plan['core'].get('clientRoles') != roles(review):
        raise Held('Hosted plan omitted or changed the mandatory client permission checks')
    if plan['core'].get('backendRoles') != backend_roles(review):
        raise Held('Hosted plan omitted or changed the reviewed backend permission checks')
    if plan['core']['baseline']['identity']['actor'] != reviewed_target['actor']:
        raise Held('The live administrative actor must be postgres')
    if plan['core']['migration']['deliveryVersion'] != review['deliveryVersion']:
        raise Held('Hosted delivery version changed')
    engine.validate_plan(plan['core'])


async def backup_match(conn, facts, *, after=False):
    await conn.execute("SET LOCAL statement_timeout='20s'")
    actual = await backup.fingerprint(conn, row_hashes=True)
    if after:
        # The core proves the exact new table/catalog and one ledger row.
        new = actual['tables'].get(engine.TABLE)
        if new != {'rows': 0, 'sha256': sha(b''), 'kind': 'r'}:
            raise Held('The new par table must be empty at installation reconciliation')
        left = {k: v for k, v in actual['tables'].items() if k not in (LEDGER, engine.TABLE)}
        right = {k: v for k, v in facts['tables'].items() if k != LEDGER}
        if left != right:
            raise Held('Original backed-up rows or sequence states changed')
        for group, value in facts['catalog'].items():
            if not engine.reference()['added'].get(group) and actual['catalog'].get(group) != value:
                raise Held('Unrelated backed-up catalog metadata changed')
    elif actual != facts:
        raise Held('Live database no longer matches the restore-verified backup')
    return {'backedUpRowsAndSequencesPreserved': True, 'factsSha256': fingerprint(actual)}


async def prepare(conn, original, review, reviewed_target, facts, binding, *, observations=None):
    # Preparation and backup comparison share one consistent read-only snapshot.
    backend_roles(review)
    maintenance(review)
    observations = observations if observations is not None else []
    await server_version(conn, binding)
    await writer_sessions(conn, review, 'prepare', observations)
    async with readonly_snapshot(conn):
        await conn.execute("SET LOCAL statement_timeout='20s'")
        await ledger_clients(conn, ledger_roles(review))
        await backup_match(conn, facts)
        core = await engine.prepare(conn, *original, review['deliveryVersion'], client_roles=roles(review),
                                    backend_roles=backend_roles(review))
    result = {'format': FORMAT, 'createdAt': datetime.now(timezone.utc).isoformat(),
              'target': reviewed_target, 'reviewSha256': fingerprint(review), 'backup': binding,
              'maintenance': review['maintenance'], 'budgets': BUDGETS, 'core': core,
              'writerObservations': observations.copy(),
              'automaticApply': False, 'operationalReleaseApproved': False}
    validate(result, review, reviewed_target, binding)
    return result


async def apply(conn, plan, review, reviewed_target, facts, binding, *, observations=None):
    validate(plan, review, reviewed_target, binding)
    observations = observations if observations is not None else []
    _, end = maintenance(review)
    if (end - datetime.now(timezone.utc)).total_seconds() < BUDGETS['operationSeconds'] + 60:
        raise Held('Reserve the full operation budget and at least one minute for recovery before application')
    await server_version(conn, binding)
    await writer_sessions(conn, review, 'before_table_locks', observations)
    async def guard(connection, phase):
        # Recheck after acquiring the engine's table locks and before COMMIT.
        maintenance(review)
        await writer_sessions(connection, review, 'locked_' + phase, observations)
        await ledger_clients(connection, ledger_roles(review))
        checked = await backup_match(connection, facts, after=phase == 'after')
        maintenance(review)
        return checked
    return await engine.apply(conn, plan['core'], guard=guard)


async def reconcile(conn, plan, review, reviewed_target, facts, binding):
    validate(plan, review, reviewed_target, binding)
    await server_version(conn, binding)
    if conn.is_in_transaction():
        raise Held('Hosted reconciliation requires an independent connection without a transaction')
    # Hold the same session lock throughout the engine and broader backup reads.
    # Re-entrant engine lock is balanced independently; no snapshot predates it.
    if not await conn.fetchval('SELECT pg_try_advisory_lock($1::bigint)', engine.INSTALLER_LOCK):
        raise Held('An original writer is still active; reconciliation remains held')
    async with preserve_cleanup_failure(
            lambda: conn.execute('SELECT pg_advisory_unlock($1::bigint)', engine.INSTALLER_LOCK),
            'lockReleaseErrorType'):
        async with readonly_snapshot(conn):
            outcome = await engine._verify_outcome(conn, plan['core'])
            await ledger_clients(conn, ledger_roles(review))
            await backup_match(conn, facts, after=outcome['sqlCommitted'])
            return outcome | {'backedUpRowsAndSequencesPreserved': True}


async def run(args):
    # Create/ACL-verify a fresh output folder and initial receipt BEFORE connecting.
    directory = backup.private_directory(Path(args.output_directory), 'backups')
    output = directory / 'receipt.json'
    result = {'status': 'held', 'mode': args.mode, 'commitAttempted': False,
              'sqlCommitted': None if args.mode == 'reconcile' else False,
              'automaticRetry': False, 'operationalReleaseApproved': False, 'writerObservations': []}
    def emit():
        # This is our fresh private receipt, never an existing caller artifact.
        temporary = directory / 'receipt.partial'
        write_private(temporary, (json.dumps(result, indent=2, sort_keys=True) + '\n').encode())
        temporary.replace(output)
    emit()
    conn = None
    started = time.monotonic()
    try:
        direct = getattr(args, 'maintenance_direct_ipv6', False)
        if type(direct) is not bool:
            raise Held('Explicit boolean maintenance mode required')
        config = dotenv_values(private_file(args.owner_config), **({'interpolate': False} if direct else {}))
        review = checked_json(private_file(args.review), args.review_sha256)
        if review['projectRef'] != args.expected_project:
            raise Held('Explicit project designation differs from the reviewed artifact')
        for key in ('encryptedFile', 'keyFile', 'restoreReceipt'):
            private_file(review['backup'][key])
        private_file(review['originalReceipt'])
        private_file(review['sourceIndexPlan'])
        original, facts, binding = load_evidence(review, active=args.mode != 'reconcile')
        if direct:
            import maintenance_connection
            dsn = maintenance_connection.config_url(config)
            maintenance_connection.direct_settings(dsn, args.expected_project)
        else:
            dsn = config.get('DATABASE_URL', '')
        identity = target(dsn, args.expected_project)
        if not direct and identity.get('connectionMode') == 'direct':
            raise Held('Direct maintenance requires explicit IPv6 opt-in and separate configuration')
        plan = None
        if args.mode != 'dry-run':
            plan = checked_json(private_file(args.plan), args.plan_sha256)
            validate(plan, review, identity, binding)
            result['planSha256'] = args.plan_sha256
        if args.mode == 'apply' and args.approve_plan_sha256 != args.plan_sha256:
            raise Held('Application requires explicit approval of this exact plan SHA-256')
        tls = connection_tls(dsn)
        async def connect(readonly):
            if direct:
                return await maintenance_connection.connect(dsn, args.expected_project,
                    readonly=readonly, timeout=20, command_timeout=30)
            return await asyncpg.connect(dsn, ssl=tls, timeout=20, command_timeout=30,
                statement_cache_size=0, server_settings={'default_transaction_read_only': 'on' if readonly else 'off'})
        async with asyncio.timeout(BUDGETS['operationSeconds']):
            conn = await connect(args.mode != 'apply')
            if args.mode == 'dry-run':
                plan = await prepare(conn, original, review, identity, facts, binding,
                                     observations=result['writerObservations'])
                raw = (json.dumps(plan, indent=2, sort_keys=True) + '\n').encode()
                write_private(directory / 'plan.json', raw)
                result.update(status='prepared_hosted_plan', planSha256=sha(raw), sqlCommitted=False)
            elif args.mode == 'reconcile':
                result.update(await reconcile(conn, plan, review, identity, facts, binding))
            else:
                # A process kill/timeout from here is ambiguous until independently
                # reconciled. Preserve the exact reviewed plan/hash before sending SQL.
                result.update(status='apply_in_progress_outcome_unknown', sqlCommitted=None,
                              planSha256=args.plan_sha256, commitAttempted=None)
                emit()
                result.update(await apply(conn, plan, review, identity, facts, binding,
                                          observations=result['writerObservations']))
                emit()
                await conn.close()
                conn = None
                conn = await connect(True)
                result['independentVerification'] = await reconcile(conn, plan, review, identity, facts, binding)
                result['status'] = 'passed_hosted_reviewed_par_install'
    except engine.AdditiveFailure as exc:
        result.update(exc.report)
    except Exception as exc:
        if result['status'] == 'committed_requires_independent_verification':
            result['status'] = 'committed_verification_held'
        elif result['status'] != 'apply_in_progress_outcome_unknown':
            result['status'] = 'held'
        result.update(error_details(exc))
        result.update(engine.backend_permission_details(exc))
        if isinstance(exc, (Held, MaintenanceConnectionError)):
            result['reason'] = str(exc)
    finally:
        if conn is not None:
            try:
                await conn.close(timeout=5)
            except Exception as close_error:
                result['connectionCloseHeld'] = True
                if result.get('errorType'):
                    result['connectionCloseErrorType'] = error_details(close_error)['errorType']
                else:
                    result.update(error_details(close_error))
                    result['connectionCloseErrorType'] = result['errorType']
                    if result['status'] not in ('apply_in_progress_outcome_unknown', 'commit_outcome_unknown'):
                        result['status'] = 'committed_verification_held' if result.get('sqlCommitted') is True else 'held'
        result['elapsedSeconds'] = round(time.monotonic() - started, 3)
        emit()
    print(json.dumps({k: result[k] for k in ('status', 'sqlCommitted', 'planSha256', 'reason') if k in result}))
    return 0 if result['status'] in ('prepared_hosted_plan', 'passed_hosted_reviewed_par_install',
                                     'verified_applied', 'verified_not_applied') else 2


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('dry-run', 'apply', 'reconcile'))
    for name in ('owner-config', 'expected-project', 'review', 'review-sha256', 'output-directory'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--plan')
    parser.add_argument('--plan-sha256')
    parser.add_argument('--approve-plan-sha256')
    parser.add_argument('--maintenance-direct-ipv6', action='store_true',
        help='Use separate MAINTENANCE_DATABASE_URL for operator-only direct IPv6')
    args = parser.parse_args()
    if args.mode != 'dry-run' and (not args.plan or not args.plan_sha256):
        parser.error('Apply/reconcile require the retained plan and exact SHA-256')
    if args.mode == 'apply' and not args.approve_plan_sha256:
        parser.error('Applying hosted SQL requires separate approval of the exact plan SHA-256')
    return args


if __name__ == '__main__':
    try:
        raise SystemExit(asyncio.run(run(arguments())))
    except Exception as exc:
        # A receipt write/close failure could occur AFTER COMMIT; never assert
        # that an unexpected outer exception proves no SQL was sent.
        print(json.dumps({'status': 'invocation_held', 'sqlCommitted': None,
                          'automaticRetry': False, 'errorType': type(exc).__name__}))
        raise SystemExit(2)
