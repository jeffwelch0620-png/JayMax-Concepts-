"""Rehearse one checksum-reviewed source index upgrade on disposable PostgreSQL.

The CLI deliberately accepts only a loopback test database. Hosted invocation,
backup approval and designation are a later adapter, not an implicit deployment.
"""
import argparse
import asyncio
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import traceback
import sys
from urllib.parse import urlsplit

# Operations run from the repository checkout, outside Render's backend root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import asyncpg
import deployment_readiness as readiness
import hosted_install_preservation as preservation
import hosted_native_install as installer
import hosted_test_trial as trial
import schema_reconciliation as catalog
from install_lock import INSTALLER_LOCK
from readonly_snapshot import readonly_snapshot, preserve_cleanup_failure, error_details

FORMAT = 'jaymax-additive-source-index-plan-v2'
SOURCE = '20261013_purchase_source_lookup_index.sql'
INDEX = 'purchasing.document_source_rows_version_run_idx'
SHA = re.compile(r'[a-f0-9]{64}')


class AdditiveFailure(RuntimeError):
    def __init__(self, report):
        super().__init__('Additive installation held; inspect the redacted receipt')
        self.report = report


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


@lru_cache(maxsize=32)
def sql_body(raw):
    # Cache parsing by immutable bytes, never path or metadata. Every invocation
    # still rereads and hashes the files; changed bytes receive a different key.
    return trial.migration_body(raw)


def local_target(dsn):
    try:
        value = urlsplit(dsn)
        allowed = (value.scheme in ('postgres', 'postgresql') and value.hostname == '127.0.0.1'
                   and value.port is not None and value.username == 'purchase_implementation_test'
                   and re.fullmatch(r'/native_purchase_test_[a-z0-9_]+', value.path)
                   and not value.query and not value.fragment)
    except ValueError:
        allowed = False
    if not allowed:
        raise ValueError('Only the designated loopback disposable PostgreSQL test connection is supported')


def source_bytes():
    raw = (readiness.ROOT / 'migrations' / SOURCE).read_bytes()
    manifest = json.loads((readiness.ROOT / 'docs/RUNTIME_PERMISSION_CANDIDATE.json').read_text())
    if manifest['migrationSha256'].get(SOURCE) != digest(raw):
        raise ValueError('Additive SQL differs from the pinned runtime source manifest')
    return raw


def checked_delivery(receipt):
    """Verify the historical delivery mapping, not a regenerated 30-file bundle."""
    if (receipt.get('status') != 'passed_durable_native_install'
            or receipt.get('sqlCommitted') is not True
            or len(readiness.ORIGINAL_NATIVE_MIGRATIONS) != 29 or readiness.RUNTIME_CANDIDATE_MIGRATIONS[-1] != SOURCE):
        raise ValueError('A completed original 29-file installation receipt is required')
    entries = receipt.get('delivery', [])
    historical = receipt.get('historicalLedgerFingerprints', {})
    if len(entries) != 29 or not isinstance(historical, dict) or not historical:
        raise ValueError('Original delivery and complete earlier history are required')
    if any(not re.fullmatch(r'\d{14}', v) or not SHA.fullmatch(h) for v, h in historical.items()):
        raise ValueError('Invalid historical ledger fingerprint')
    previous = max(historical)
    reviewed = []
    for order, (entry, source) in enumerate(zip(entries, readiness.ORIGINAL_NATIVE_MIGRATIONS), 1):
        version = entry['deliveryVersion']
        if not re.fullmatch(r'\d{14}', version) or version <= previous:
            raise ValueError('Original delivery versions must follow the complete earlier history')
        datetime.strptime(version, '%Y%m%d%H%M%S')
        raw = (readiness.ROOT / 'migrations' / source).read_bytes()
        body = sql_body(raw)
        name = source.split('_', 1)[1].removesuffix('.sql')
        if (entry['order'] != order or entry['sourceFile'] != 'migrations/' + source
                or entry['deliveryFile'] != 'native-migrations/' + version + '_' + name + '.sql'
                or entry['sha256'] != digest(raw) or entry['bodySha256'] != digest(body.encode())):
            raise ValueError('Original delivery source/body checksum or mapping changed')
        reviewed.append({k: entry[k] for k in ('order', 'sourceFile', 'deliveryVersion',
                                               'deliveryFile', 'sha256', 'bodySha256')})
        previous = version
    return reviewed, historical


def validate_plan(plan):
    # Plans and receipts are distinct artifacts. A held dry-run receipt must not
    # become executable merely because an operator hashes its retained contents.
    required = {'format', 'originalInstallation', 'clientRoles', 'baseline', 'migration'}
    allowed = required | {'createdAt', 'automaticApply', 'hostedInvocationSupported', 'operationalReleaseApproved'}
    if not isinstance(plan, dict) or not required <= plan.keys() or plan.keys() - allowed:
        raise ValueError('Additive plan schema excludes receipts and unreviewed fields')
    for flag in ('automaticApply', 'hostedInvocationSupported', 'operationalReleaseApproved'):
        if flag in plan and plan[flag] is not False:
            raise ValueError('Additive plan cannot authorize automatic or operational execution')
    if plan.get('format') != FORMAT:
        raise ValueError('Unsupported additive plan')
    checked_delivery(plan['originalInstallation'])
    raw = source_bytes()
    body = sql_body(raw)
    entry = plan['migration']
    if (entry['sourceFile'] != 'migrations/' + SOURCE or entry['sha256'] != digest(raw)
            or entry['bodySha256'] != digest(body.encode())
            or entry['name'] != SOURCE.split('_', 1)[1].removesuffix('.sql')):
        raise ValueError('Additive migration checksum changed')
    version = entry['deliveryVersion']
    if not re.fullmatch(r'\d{14}', version) or version <= max(plan['baseline']['ledger']):
        raise ValueError('Additive version must follow all actual installed history')
    datetime.strptime(version, '%Y%m%d%H%M%S')
    if not isinstance(plan['clientRoles'], list) or any(not isinstance(r, str) for r in plan['clientRoles']):
        raise ValueError('Invalid reviewed client roles')
    return body


async def verify_prior(conn, receipt):
    entries, historical = checked_delivery(receipt)
    await installer.ledger_shape(conn)
    fingerprints = await preservation.ledger_fingerprints(conn)
    versions = {e['deliveryVersion'] for e in entries}
    if set(fingerprints) != set(historical) | versions:
        raise ValueError('Installed history is missing, partial or contains unreviewed versions')
    if any(fingerprints.get(v) != h for v, h in historical.items()):
        raise ValueError('Earlier historical migration rows changed')
    rows = await conn.fetch('SELECT version,name,statements FROM supabase_migrations.schema_migrations '
                            'WHERE version=ANY($1::text[])', sorted(versions))
    expected = {e['deliveryVersion']: e for e in entries}
    for row in rows:
        e = expected[row['version']]
        statements = row['statements']
        if (row['name'] != Path(e['deliveryFile']).name.split('_', 1)[1].removesuffix('.sql')
                or not statements or len(statements) != 1
                or digest(statements[0].encode()) != e['bodySha256']):
            raise ValueError('An installed native SQL body or name differs from original delivery')


async def snapshot(conn):
    identity = dict(await conn.fetchrow("SELECT current_database() AS database,current_user AS actor,"
                    "(SELECT oid::bigint FROM pg_database WHERE datname=current_database()) AS database_oid,"
                    "inet_server_addr()::text AS server_address,inet_server_port() AS server_port,"
                    "current_setting('server_version_num') AS server_version"))
    columns = await preservation.original_columns(conn)
    return {'identity': identity, 'ledger': await preservation.ledger_fingerprints(conn),
            'ledgerCatalog': await preservation.ledger_contract(conn),
            'columns': [{'schema': k[0], 'table': k[1], 'columns': v} for k, v in sorted(columns.items())],
            'rows': await preservation.fingerprints(conn, columns),
            'catalog': (await catalog.capture(conn))['catalog']}


async def require_readiness(conn, roles, *, before=False):
    check = await readiness.inspect(conn, client_roles=roles, migration_baseline='source_index_v1')
    issues = check['issues']
    if before:
        expected = [
            {'kind': 'schema', 'file': SOURCE,
             'missingObjects': ['purchasing.document_source_rows:document_source_rows_version_run_idx']},
            {'kind': 'index_contract', 'object': INDEX, 'reason': 'missing'}]
        if issues != expected:
            raise ValueError('Readiness must be clean except for the unapplied source index')
    elif issues:
        raise ValueError('Installed readiness is held')
    return check


async def prepare(conn, original_receipt, version, client_roles=('anon', 'authenticated')):
    """Read-only dry run. No locks that block writers, index creation or ledger writes."""
    entries, historical = checked_delivery(original_receipt)
    # Retain only reviewed, redacted fields; old SQL/connection material stays private.
    original = {'status': 'passed_durable_native_install', 'sqlCommitted': True,
                'delivery': entries, 'historicalLedgerFingerprints': historical}
    async with readonly_snapshot(conn):
        await conn.execute("SET LOCAL statement_timeout='20s'")
        await verify_prior(conn, original)
        if await conn.fetchval('SELECT to_regclass($1) IS NOT NULL', INDEX):
            raise ValueError('Index already exists without the reviewed additive ledger outcome')
        await require_readiness(conn, client_roles, before=True)
        baseline = await snapshot(conn)
    raw = source_bytes()
    plan = {'format': FORMAT, 'createdAt': datetime.now(timezone.utc).isoformat(),
            'originalInstallation': original, 'clientRoles': list(client_roles), 'baseline': baseline,
            'migration': {'sourceFile': 'migrations/' + SOURCE, 'sha256': digest(raw),
                          'bodySha256': digest(sql_body(raw).encode()),
                          'deliveryVersion': version, 'name': SOURCE.split('_', 1)[1].removesuffix('.sql')},
            'automaticApply': False, 'hostedInvocationSupported': False,
            'operationalReleaseApproved': False}
    validate_plan(plan)
    return plan


async def verify_outcome(conn, plan):
    """Reconcile after commit using a fresh connection; never reapply SQL."""
    if conn.is_in_transaction():
        raise ValueError('Independent reconciliation requires a fresh transaction')
    # Acquire before starting the snapshot: an unresolved original writer must
    # not appear unapplied merely because its transaction is still invisible.
    if not await conn.fetchval('SELECT pg_try_advisory_lock($1::bigint)', INSTALLER_LOCK):
        raise ValueError('An installation writer is still active; retain the unknown outcome')
    async with preserve_cleanup_failure(
            lambda: conn.execute('SELECT pg_advisory_unlock($1::bigint)', INSTALLER_LOCK),
            'lockReleaseErrorType'):
        return await _verify_outcome(conn, plan)


async def _verify_outcome(conn, plan):
    validate_plan(plan)
    async with readonly_snapshot(conn):
        await conn.execute("SET LOCAL statement_timeout='20s'")
        current = await snapshot(conn)
        baseline = plan['baseline']
        if current['identity'] != baseline['identity']:
            raise ValueError('Plan targets a different database identity or actor')
        if current['ledgerCatalog'] != baseline['ledgerCatalog']:
            raise ValueError('Migration ledger structure or access changed')
        version = plan['migration']['deliveryVersion']
        if current == baseline:
            return {'status': 'verified_not_applied', 'readOnly': True, 'sqlCommitted': False}
        if (set(current['ledger']) != set(baseline['ledger']) | {version}
                or any(current['ledger'].get(v) != h for v, h in baseline['ledger'].items())):
            raise ValueError('Additive or earlier migration history is inconsistent')
        row = await conn.fetchrow('SELECT name,statements FROM supabase_migrations.schema_migrations WHERE version=$1', version)
        if (row['name'] != plan['migration']['name'] or not row['statements'] or len(row['statements']) != 1
                or digest(row['statements'][0].encode()) != plan['migration']['bodySha256']):
            raise ValueError('Recorded additive SQL body differs from review')
        if current['columns'] != baseline['columns'] or current['rows'] != baseline['rows']:
            raise ValueError('Original application rows or columns changed')
        actual_catalog = current['catalog']
        for group, count in (('relations', 1), ('indexes', 1), ('columns', 2)):
            found = [r for r in actual_catalog[group] if r['nspname'] == 'purchasing'
                     and r['relname'] == INDEX.split('.')[1]]
            if len(found) != count:
                raise ValueError('Unexpected new index catalog entries')
            if group == 'columns' and [r['attname'] for r in sorted(found, key=lambda r: r['attnum'])] != [
                    'document_version_id', 'parse_run_id']:
                raise ValueError('Unexpected new index catalog attributes')
            actual_catalog[group] = [r for r in actual_catalog[group] if r not in found]
        if actual_catalog != baseline['catalog']:
            raise ValueError('Unrelated catalog or permissions changed')
        check = await require_readiness(conn, plan['clientRoles'])
        return {'status': 'verified_applied', 'readOnly': True, 'sqlCommitted': True,
                'originalRowsAndCatalogPreserved': True, 'historicalLedgerPreserved': True,
                'nativeReadiness': check}


async def apply(conn, plan, *, guard=None):
    """One outer transaction for index plus ledger. Refuse already-applied plans."""
    body = validate_plan(plan)
    if conn.is_in_transaction():
        raise ValueError('Additive application requires its own outer transaction')
    report = {'status': 'held', 'sqlCommitted': False, 'commitAttempted': False,
              'migration': plan['migration'], 'automaticRetry': False}
    tx = None
    session_locked = False
    try:
        # Serialize with every older installer BEFORE starting repeatable read.
        # A SELECT inside that transaction would freeze its snapshot before a
        # blocking table lock. LOCK/SET themselves do not take that snapshot.
        session_locked = await conn.fetchval('SELECT pg_try_advisory_lock($1::bigint)', INSTALLER_LOCK)
        if not session_locked:
            raise ValueError('Another installer is active; application remains held')
        tx = conn.transaction(isolation='repeatable_read')
        await tx.start()
        await conn.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'; "
                           "SET LOCAL idle_in_transaction_session_timeout='120s'")
        await conn.execute('LOCK TABLE supabase_migrations.schema_migrations IN EXCLUSIVE MODE')
        columns = {(r['schema'], r['table']): r['columns'] for r in plan['baseline']['columns']}
        await preservation.lock_original_tables(conn, columns)
        # Re-entrant acquisition cannot wait: our session already owns this key.
        # This first SELECT freezes the snapshot only AFTER all row writers drain.
        await conn.execute('SELECT pg_advisory_xact_lock($1::bigint)', INSTALLER_LOCK)
        if await snapshot(conn) != plan['baseline']:
            raise ValueError('Reviewed database baseline changed or migration is already applied')
        await verify_prior(conn, plan['originalInstallation'])
        await require_readiness(conn, plan['clientRoles'], before=True)
        if guard is not None:
            await guard(conn, 'before')
        await conn.execute("SET LOCAL statement_timeout='30s'")
        # The outer BEGIN/COMMIT have been validated and removed, preserving body bytes.
        await conn.execute(body)
        if not conn.is_in_transaction():
            raise RuntimeError('Additive migration escaped the installation transaction')
        e = plan['migration']
        await conn.execute('INSERT INTO supabase_migrations.schema_migrations(version,name,statements) '
                           'VALUES($1,$2,$3::text[])', e['deliveryVersion'], e['name'], [body])
        report['precommitVerification'] = await _verify_outcome(conn, plan)
        if guard is not None:
            report['additionalPrecommitVerification'] = await guard(conn, 'after')
        report['commitAttempted'] = True
        await tx.commit()
        tx = None
        report.update(status='committed_requires_independent_verification', sqlCommitted=True)
        return report
    except Exception as exc:
        report.update(error_details(exc))
        report['errorFrames'] = [{'file': Path(f.filename).name, 'function': f.name, 'line': f.lineno}
                                 for f in traceback.extract_tb(exc.__traceback__)]
        if report['commitAttempted']:
            report.update(status='commit_outcome_unknown', sqlCommitted=None)
        elif tx is not None:
            try:
                await tx.rollback()
                report['rollbackCompleted'] = True
            except Exception:
                report.update(status='rollback_outcome_unknown', sqlCommitted=None)
        raise AdditiveFailure(report) from None
    finally:
        if session_locked:
            try:
                await conn.execute('SELECT pg_advisory_unlock($1::bigint)', INSTALLER_LOCK)
            except Exception:
                # Lost release acknowledgement cannot change a known COMMIT or
                # rollback into the opposite outcome. Close/reconcile explicitly.
                report['lockReleaseHeld'] = True


async def main(args):
    dsn = os.environ.get('NATIVE_PURCHASE_TEST_DSN', '')
    local_target(dsn)
    if Path(args.output).exists():
        raise ValueError('Preserve old evidence; choose a new output path')
    conn = await asyncpg.connect(dsn, timeout=20, statement_cache_size=0,
                                 server_settings={'default_transaction_read_only': 'off' if args.mode == 'apply' else 'on'})
    result = {'status': 'held', 'commitAttempted': False, 'sqlCommitted': False}
    try:
        async with preserve_cleanup_failure(lambda: conn.close(), 'connectionCloseErrorType'):
            if args.mode == 'dry-run':
                receipt = json.loads(Path(args.original_install_receipt).read_text(encoding='utf-8-sig'))
                result = await prepare(conn, receipt, args.delivery_version, client_roles=())
            else:
                raw = Path(args.plan).read_bytes()
                if digest(raw) != args.plan_sha256:
                    raise ValueError('Reviewed plan checksum changed')
                plan = json.loads(raw)
                if args.mode == 'reconcile':
                    result = await verify_outcome(conn, plan)
                else:
                    result = await apply(conn, plan)
                    await conn.close()
                    conn = await asyncpg.connect(dsn, timeout=20, statement_cache_size=0,
                                                 server_settings={'default_transaction_read_only': 'on'})
                    result['independentVerification'] = await verify_outcome(conn, plan)
                    result['status'] = 'passed_local_additive_install'
    except AdditiveFailure as exc:
        result = exc.report
        # Close failure may be attached to the wrapper; retain the report's
        # original driver category, SQLSTATE and known/unknown SQL outcome.
        result.update({key: value for key, value in error_details(exc).items()
                       if key != 'errorType' and key.endswith('ErrorType') and value is not None})
    except Exception as exc:
        result.update(status='committed_verification_held' if result.get('commitAttempted') else 'held',
                      **error_details(exc))
    with Path(args.output).open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write('\n')
    print(json.dumps({k: result[k] for k in ('status', 'format', 'sqlCommitted') if k in result}))
    return 0 if (result.get('format') == FORMAT and not result.get('status')) or result.get('status') in (
        'passed_local_additive_install', 'verified_applied', 'verified_not_applied') else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('dry-run', 'apply', 'reconcile'))
    parser.add_argument('--output', required=True)
    parser.add_argument('--original-install-receipt')
    parser.add_argument('--delivery-version')
    parser.add_argument('--plan')
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    if args.mode == 'dry-run' and (not args.original_install_receipt or not args.delivery_version):
        parser.error('Dry run requires the original installation receipt and a new delivery version')
    if args.mode != 'dry-run' and (not args.plan or not args.plan_sha256):
        parser.error('Apply/reconcile require the exact reviewed plan and its SHA-256')
    try:
        raise SystemExit(asyncio.run(main(args)))
    except (ValueError, OSError):
        raise SystemExit('Local additive invocation held; check target and private file arguments')
