"""Manual, reviewed additive index installation on the designated Supabase build DB.

Preparing this adapter does not authorize hosted execution. No app configuration,
role changes, history repair, migration replay, retries or managed-service restore.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import urlsplit


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
import apply_additive_migration as engine
import hosted_backup as backup
from db_tls import connection_tls, DEFAULT_CA
from managed_development import project_identity

FORMAT = 'jaymax-hosted-additive-index-plan-v2'
REVIEW_FORMAT = 'jaymax-hosted-additive-index-review-v2'
BUDGETS = {'lockSeconds': 5, 'probeSeconds': 20, 'ddlSeconds': 30,
           'idleTransactionSeconds': 120, 'operationSeconds': 600}
LEDGER = 'supabase_migrations.schema_migrations'


class Held(ValueError):
    """Only fixed, safe messages may be attached to an operator receipt."""


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fingerprint(value):
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def utc(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        raise Held('Use explicit timezone-aware maintenance timestamps') from None


def maintenance(review, *, now=None, active=True):
    value = review.get('maintenance', {})
    start, end = utc(value.get('startsAt')), utc(value.get('endsAt'))
    now = now or datetime.now(timezone.utc)
    if (not 600 <= (end - start).total_seconds() <= 3600
            or value.get('allWritersStopped') is not True
            or value.get('inFlightDrained') is not True
            or not isinstance(value.get('reference'), str) or not value['reference'].strip()):
        raise Held('A reviewed 10-to-60 minute window with all writers drained is required')
    if active and not start <= now < end:
        raise Held('The reviewed maintenance window is not active')
    return start, end


def target(dsn, project):
    identity = project_identity(dsn)
    if identity['projectRef'] != project or not re.fullmatch(r'[a-z0-9]{20}', project or ''):
        raise Held('The designated build project does not match the owner connection')
    # No changes to the application's saved DSNs. Pin the selected administrative
    # endpoint separately; never serialize the password or the complete URL.
    url = urlsplit(dsn)
    ca = Path(os.environ.get('DATABASE_SSL_ROOT_CERT', str(DEFAULT_CA)))
    tls = connection_tls(dsn)
    if tls is False or not tls.check_hostname:
        raise Held('Certificate-verified administrative TLS is required')
    return {'projectRef': project, 'connectionMode': identity['connectionMode'],
            'host': url.hostname, 'port': url.port, 'database': 'postgres',
            'actor': 'postgres', 'caSha256': sha(ca.read_bytes())}


def roles(review):
    value = review.get('clientRoles')
    if (not isinstance(value, list)
            or any(not isinstance(r, str) or not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}', r) for r in value)
            or not {'anon', 'authenticated'} <= set(value) or len(value) != len(set(value))):
        raise Held('Hosted checks must include anon and authenticated exactly once')
    return value


def writer_roles(review):
    value = review.get('writerLoginRoles')
    if (not isinstance(value, list) or not value
            or any(not isinstance(r, str) or not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}', r) for r in value)
            or len(value) != len(set(value))):
        raise Held('A nonempty reviewed list of application LOGIN roles is required')
    return value


async def server_version(conn, binding=None):
    value = await conn.fetchval('SHOW server_version_num')
    if int(value) < 160000:
        raise Held('Hosted adapter requires PostgreSQL 16 or newer; PostgreSQL 17 is tested')
    if binding is not None and value != binding['serverVersionNum']:
        raise Held('The live PostgreSQL version differs from the reviewed backup')


async def writer_sessions(conn, review, phase, observations):
    """A refreshed observation, not proof that disconnected writers cannot return."""
    names = writer_roles(review)
    async def probe():
        await conn.execute("SET LOCAL statement_timeout='20s'")
        await conn.execute('SELECT pg_stat_clear_snapshot()')
        row = await conn.fetchrow("""WITH sessions AS (
            SELECT pid,usename,state FROM pg_stat_activity
            WHERE datname=current_database() AND pid<>pg_backend_pid()
              AND backend_type='client backend'
        ), writing AS (
            SELECT DISTINCT s.pid FROM sessions s JOIN pg_locks l ON l.pid=s.pid
              JOIN pg_class c ON c.oid=l.relation JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=ANY($2::text[]) AND l.locktype='relation'
              AND l.mode IN ('RowExclusiveLock','ShareRowExclusiveLock','ExclusiveLock','AccessExclusiveLock')
              AND s.state IN ('active','idle in transaction','idle in transaction (aborted)')
        ) SELECT
          (SELECT count(*) FROM pg_roles WHERE rolname=ANY($1::text[]) AND rolcanlogin) AS verified_roles,
          (SELECT count(*) FROM sessions WHERE usename=ANY($1::text[])) AS application_sessions,
          (SELECT count(*) FROM writing) AS write_transactions,
          (SELECT count(*) FROM sessions WHERE state IS NULL OR state='disabled') AS unobservable_sessions
        """, names, list(backup.SCHEMAS) + ['supabase_migrations'])
        observed = {'phase': phase, 'reviewedLoginCount': len(names),
                    'verifiedLoginCount': row['verified_roles'],
                    'applicationSessionCount': row['application_sessions'],
                    'applicationWriteTransactionCount': row['write_transactions'],
                    'unobservableSessionCount': row['unobservable_sessions']}
        observations.append(observed)
        if observed['verifiedLoginCount'] != len(names):
            raise Held('Reviewed application LOGIN roles are missing or no longer LOGIN roles')
        if any(observed[k] for k in ('applicationSessionCount', 'applicationWriteTransactionCount',
                                     'unobservableSessionCount')):
            raise Held('Live application sessions or write transactions remain, or visibility is incomplete')
        return observed
    if conn.is_in_transaction():
        return await probe()
    # This transaction ends before the engine starts its own repeatable-read
    # transaction, preserving the table-lock-before-first-snapshot ordering.
    async with conn.transaction(readonly=True):
        return await probe()


def checked_json(path, expected):
    raw = Path(path).read_bytes()
    if not isinstance(expected, str) or not re.fullmatch(r'[a-f0-9]{64}', expected) or sha(raw) != expected:
        raise Held('A reviewed private artifact checksum changed')
    return json.loads(raw)


def load_evidence(review, *, now=None, active=True):
    """Authenticate the backup; bind the isolated-restore receipt to that archive."""
    if review.get('format') != REVIEW_FORMAT or review.get('budgets') != BUDGETS:
        raise Held('Unsupported hosted review or unreviewed timeout budgets')
    roles(review)
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
    engine.checked_delivery(original)
    # The encrypted archive carries actual data; plans retain only fingerprints.
    facts = {key: manifest[key] for key in ('tables', 'catalog')}
    binding = {'encryptedSha256': item['encryptedSha256'], 'archiveSha256': manifest['archiveSha256'],
               'restoreReceiptSha256': item['restoreReceiptSha256'], 'factsSha256': fingerprint(facts),
               'createdAt': manifest['createdAt'], 'serverVersionNum': manifest['serverVersionNum'],
               'managedRecoveryVerified': False}
    return original, facts, binding


def validate(plan, review, reviewed_target, binding):
    writer_roles(review)
    if (plan.get('format') != FORMAT or plan.get('target') != reviewed_target
            or plan.get('reviewSha256') != fingerprint(review) or plan.get('backup') != binding
            or plan.get('budgets') != BUDGETS or plan.get('maintenance') != review['maintenance']):
        raise Held('Hosted plan does not match the reviewed target, backup or maintenance evidence')
    if plan['core'].get('clientRoles') != roles(review):
        raise Held('Hosted plan omitted or changed the mandatory client permission checks')
    if plan['core']['baseline']['identity']['actor'] != reviewed_target['actor']:
        raise Held('The live administrative actor must be postgres')
    if plan['core']['migration']['deliveryVersion'] != review['deliveryVersion']:
        raise Held('Hosted delivery version changed')
    engine.validate_plan(plan['core'])


async def backup_match(conn, facts, *, after=False):
    await conn.execute("SET LOCAL statement_timeout='20s'")
    actual = await backup.fingerprint(conn, row_hashes=True)
    if after:
        # The ledger acquires exactly one reviewed row, checked by the engine.
        # Every other original table/materialized view/sequence must match.
        left = {k: v for k, v in actual['tables'].items() if k != LEDGER}
        right = {k: v for k, v in facts['tables'].items() if k != LEDGER}
        if left != right:
            raise Held('Original backed-up rows or sequence states changed')
        for group, value in facts['catalog'].items():
            if group not in ('relations', 'columns', 'indexes') and actual['catalog'].get(group) != value:
                raise Held('Unrelated backed-up catalog metadata changed')
    elif actual != facts:
        raise Held('Live database no longer matches the restore-verified backup')
    return {'backedUpRowsAndSequencesPreserved': True, 'factsSha256': fingerprint(actual)}


async def ledger_clients(conn, clients):
    for role in clients:
        exposed = await conn.fetchval("""SELECT EXISTS(SELECT 1 FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='supabase_migrations' AND c.relkind IN ('r','p','v','m')
            AND (has_table_privilege($1,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                 OR has_any_column_privilege($1,c.oid,'SELECT,INSERT,UPDATE,REFERENCES')))""", role)
        if exposed:
            raise Held('Ordinary client access to the migration ledger is not allowed')


async def prepare(conn, original, review, reviewed_target, facts, binding, *, observations=None):
    # Preparation and backup comparison share one consistent read-only snapshot.
    maintenance(review)
    observations = observations if observations is not None else []
    await server_version(conn, binding)
    await writer_sessions(conn, review, 'prepare', observations)
    async with conn.transaction(isolation='repeatable_read', readonly=True):
        await conn.execute("SET LOCAL statement_timeout='20s'")
        await ledger_clients(conn, roles(review))
        await backup_match(conn, facts)
        core = await engine.prepare(conn, original, review['deliveryVersion'], client_roles=roles(review))
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
    maintenance(review)
    await server_version(conn, binding)
    await writer_sessions(conn, review, 'before_table_locks', observations)
    async def guard(connection, phase):
        # Recheck after acquiring the engine's table locks and before COMMIT.
        maintenance(review)
        await writer_sessions(connection, review, 'locked_' + phase, observations)
        await ledger_clients(connection, roles(review))
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
    try:
        async with conn.transaction(isolation='repeatable_read', readonly=True):
            outcome = await engine._verify_outcome(conn, plan['core'])
            await ledger_clients(conn, roles(review))
            await backup_match(conn, facts, after=outcome['sqlCommitted'])
            return outcome | {'backedUpRowsAndSequencesPreserved': True}
    finally:
        await conn.execute('SELECT pg_advisory_unlock($1::bigint)', engine.INSTALLER_LOCK)


def private_file(path):
    """Keep operational inputs outside Git/synced drives under private local storage."""
    value = Path(path)
    root = Path(os.environ['LOCALAPPDATA']) / 'JayMaxBuild'
    if not value.is_absolute() or not value.resolve().is_relative_to(root.resolve()) or not value.is_file():
        raise Held('Hosted input artifacts must be private local JayMaxBuild files')
    for parent in (value, *value.parents):
        if parent.is_symlink() or parent.is_junction():
            raise Held('Redirected operational artifact paths are refused')
        if parent == root:
            break
    verify_acl(value)
    return value


def verify_acl(path):
    shell = shutil.which('pwsh')
    if not shell:
        raise Held('PowerShell private input ACL verification is required')
    script = """$ErrorActionPreference='Stop'; $p=$env:JAYMAX_ADDITIVE_PRIVATE;
      $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User;
      $acl=Get-Acl -LiteralPath $p;
      if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $sid.Value) {exit 2};
      $allowed=@($sid.Value,'S-1-5-18');
      foreach($rule in $acl.Access) {
        if ($rule.AccessControlType -eq 'Allow' -and
          $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -notin $allowed) {exit 2}
      }; Write-Output 'verified'"""
    result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-Command', script],
        env={**os.environ, 'JAYMAX_ADDITIVE_PRIVATE': str(path)}, capture_output=True, timeout=20,
        creationflags=backup.FLAGS)
    if result.returncode or result.stdout.strip() != b'verified':
        raise Held('Private input ownership or ACL verification held')


def write_private(path, raw):
    """Only create a fresh generated artifact; never repair caller-owned inputs."""
    with Path(path).open('xb') as stream:
        stream.write(raw)
    shell = shutil.which('pwsh')
    if not shell:
        raise Held('PowerShell 7 private output preparation is required')
    script = """$ErrorActionPreference='Stop'; $p=$env:JAYMAX_ADDITIVE_PRIVATE;
      $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User;
      $acl=[Security.AccessControl.FileSecurity]::new();
      $acl.SetOwner($sid); $acl.SetAccessRuleProtection($true,$false);
      foreach($id in @($sid.Value,'S-1-5-18')) {
        $rule=[Security.AccessControl.FileSystemAccessRule]::new(
          [Security.Principal.SecurityIdentifier]::new($id),'FullControl','Allow');
        $acl.AddAccessRule($rule) }; Set-Acl -LiteralPath $p -AclObject $acl"""
    result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-Command', script],
        env={**os.environ, 'JAYMAX_ADDITIVE_PRIVATE': str(path)}, capture_output=True, timeout=20,
        creationflags=backup.FLAGS)
    if result.returncode:
        raise Held('Private output ownership or ACL preparation held')
    verify_acl(path)


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
        config = dotenv_values(private_file(args.owner_config))
        review = checked_json(private_file(args.review), args.review_sha256)
        if review['projectRef'] != args.expected_project:
            raise Held('Explicit project designation differs from the reviewed artifact')
        for key in ('encryptedFile', 'keyFile', 'restoreReceipt'):
            private_file(review['backup'][key])
        private_file(review['originalReceipt'])
        original, facts, binding = load_evidence(review, active=args.mode != 'reconcile')
        dsn = config.get('DATABASE_URL', '')
        identity = target(dsn, args.expected_project)
        plan = None
        if args.mode != 'dry-run':
            plan = checked_json(private_file(args.plan), args.plan_sha256)
            validate(plan, review, identity, binding)
            result['planSha256'] = args.plan_sha256
        if args.mode == 'apply' and args.approve_plan_sha256 != args.plan_sha256:
            raise Held('Application requires explicit approval of this exact plan SHA-256')
        tls = connection_tls(dsn)
        async def connect(readonly):
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
                result['status'] = 'passed_hosted_additive_install'
    except engine.AdditiveFailure as exc:
        result.update(exc.report)
    except Exception as exc:
        if result['status'] == 'committed_requires_independent_verification':
            result['status'] = 'committed_verification_held'
        elif result['status'] != 'apply_in_progress_outcome_unknown':
            result['status'] = 'held'
        result['errorType'] = type(exc).__name__
        if isinstance(exc, Held):
            result['reason'] = str(exc)
    finally:
        if conn is not None:
            try:
                await conn.close(timeout=5)
            except Exception:
                result['connectionCloseHeld'] = True
        result['elapsedSeconds'] = round(time.monotonic() - started, 3)
        emit()
    print(json.dumps({k: result[k] for k in ('status', 'sqlCommitted', 'planSha256', 'reason') if k in result}))
    return 0 if result['status'] in ('prepared_hosted_plan', 'passed_hosted_additive_install',
                                     'verified_applied', 'verified_not_applied') else 2


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('dry-run', 'apply', 'reconcile'))
    for name in ('owner-config', 'expected-project', 'review', 'review-sha256', 'output-directory'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--plan')
    parser.add_argument('--plan-sha256')
    parser.add_argument('--approve-plan-sha256')
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
