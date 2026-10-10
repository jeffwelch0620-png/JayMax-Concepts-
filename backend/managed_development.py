"""Prepare native migration delivery and inspect an isolated Supabase target.

No SQL application, history repair, data import, reset, or release approval.
"""
import argparse
import asyncio
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse, unquote

import asyncpg
from dotenv import dotenv_values
import deployment_readiness as readiness

FORMAT = 'jaymax-managed-development-bundle-v1'
REF = r'[a-z0-9]{20}'


class DevelopmentTargetError(ValueError):
    """Fixed-text validation message safe to retain in review reports."""


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def project_identity(dsn):
    """Resolve only unambiguous direct/session owner URLs; never echo credentials."""
    try:
        uri = urlparse(dsn)
        if (uri.scheme not in ('postgres', 'postgresql') or uri.port != 5432
                or uri.path != '/postgres' or uri.query or uri.fragment
                or not uri.password or '[YOUR-PASSWORD]' in unquote(uri.password)):
            raise ValueError
        host = uri.hostname or ''
        direct = re.fullmatch(r'db\.(' + REF + r')\.supabase\.co', host)
        user = unquote(uri.username or '')
        if direct and user == 'postgres':
            return {'projectRef': direct[1], 'connectionMode': 'direct'}
        pooled = re.fullmatch(r'postgres\.(' + REF + r')', user)
        if pooled and re.fullmatch(r'[a-z0-9-]+\.pooler\.supabase\.com', host):
            return {'projectRef': pooled[1], 'connectionMode': 'session_pooler'}
    except (ValueError, TypeError):
        pass
    raise DevelopmentTargetError('Use a private Supabase owner connection on port 5432, without URL query overrides.')


def target_identity(source_dsn, target_dsn, expected_ref):
    source = project_identity(source_dsn)
    target = project_identity(target_dsn)
    if not re.fullmatch(REF, expected_ref or '') or target['projectRef'] != expected_ref:
        raise DevelopmentTargetError('Development project reference does not match the private target connection.')
    if source['projectRef'] == target['projectRef']:
        raise DevelopmentTargetError('Development validation refuses the existing source project.')
    return target


def prepare_bundle(directory, first_version='20261007000001'):
    if not re.fullmatch(r'\d{14}', first_version):
        raise ValueError('Delivery versions require a fourteen-digit timestamp.')
    start = datetime.strptime(first_version, '%Y%m%d%H%M%S')
    sources = [(name, (readiness.ROOT / 'migrations' / name).read_bytes()) for name in readiness.MIGRATIONS]
    directory = Path(directory)
    if directory.exists():
        raise ValueError('Use a new bundle directory; existing snapshots are never overwritten.')
    directory.mkdir(parents=True)
    staging = directory / 'native-migrations'; staging.mkdir()
    entries = []
    for index, (name, raw) in enumerate(sources):
        version = (start + timedelta(seconds=index)).strftime('%Y%m%d%H%M%S')
        output_name = version + '_' + name.split('_', 1)[1]
        (staging / output_name).write_bytes(raw)
        entries.append({'order': index + 1, 'deliveryVersion': version,
                        'sourceFile': 'migrations/' + name, 'deliveryFile': 'native-migrations/' + output_name,
                        'bytes': len(raw), 'sha256': digest(raw)})
    manifest = {'format': FORMAT, 'status': 'prepared_not_applied', 'migrations': entries,
                'baselineRequired': 'Reviewed current hosted public/integrations schema, loaded separately on a new isolated project.',
                'historicalMigrationReplay': False, 'automaticApply': False,
                'deliveryVersionsAreHistoricalAppliedVersions': False, 'operationalReleaseApproved': False,
                'limits': ['Native chain only; current private baseline SQL and platform state are not included.',
                           'No CLI project linking, database reset/push, hosted application, or ledger repair.',
                           'Preserve this source hash map when delivery is later reviewed and applied.']}
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    verify_bundle(directory)
    return manifest


def verify_bundle(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    entries = manifest['migrations']
    if manifest['format'] != FORMAT or len(entries) != len(readiness.MIGRATIONS):
        raise ValueError('Unknown or incomplete native bundle.')
    previous = ''; expected_files = set()
    for index, (entry, name) in enumerate(zip(entries, readiness.MIGRATIONS)):
        version = entry['deliveryVersion']
        relative = 'native-migrations/' + version + '_' + name.split('_', 1)[1]
        if (entry['order'] != index + 1 or entry['sourceFile'] != 'migrations/' + name
                or not re.fullmatch(r'\d{14}', version) or version <= previous
                or entry['deliveryFile'] != relative):
            raise ValueError('Native migration order or identity changed.')
        datetime.strptime(version, '%Y%m%d%H%M%S')
        source = (readiness.ROOT / 'migrations' / name).read_bytes()
        staged = (directory / relative).read_bytes()
        if source != staged or digest(staged) != entry['sha256'] or len(staged) != entry['bytes']:
            raise ValueError('Migration bytes no longer match the reviewed source.')
        expected_files.add(relative); previous = version
    actual_files = {p.relative_to(directory).as_posix() for p in (directory / 'native-migrations').iterdir()}
    if actual_files != expected_files:
        raise ValueError('Unexpected or missing staged migration files.')
    return {'status': 'verified_offline', 'files': len(entries), 'operationalReleaseApproved': False}


async def inspect_empty_target(conn, identity):
    """Catalog-only bootstrap check; existing application objects require review."""
    async with conn.transaction(isolation='repeatable_read', readonly=True):
        await conn.execute("SET LOCAL statement_timeout='20s'")
        role = dict(await conn.fetchrow('SELECT current_user AS name,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user'))
        objects = await conn.fetch('''SELECT n.nspname,c.relname,c.relkind::text AS kind
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=ANY($1::text[]) AND c.relkind IN ('r','p','v','m','S')
            ORDER BY n.nspname,c.relname''', ['public', 'integrations', *readiness.PRIVATE])
        functions = await conn.fetch('''SELECT n.nspname,p.proname FROM pg_proc p
            JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=ANY($1::text[])
            AND NOT EXISTS(SELECT 1 FROM pg_depend d WHERE d.classid='pg_proc'::regclass
                AND d.objid=p.oid AND d.deptype='e') ORDER BY n.nspname,p.proname''',
            ['public', 'integrations', *readiness.PRIVATE])
        extensions = [dict(row) for row in await conn.fetch('SELECT extname,extversion FROM pg_extension ORDER BY extname')]
        clients = [row['rolname'] for row in await conn.fetch("SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated') ORDER BY rolname")]
        schemas = [row['nspname'] for row in await conn.fetch("SELECT nspname FROM pg_namespace WHERE nspname IN ('auth','storage','vault','cron') ORDER BY nspname")]
    issues = []
    if objects or functions: issues.append('Existing application objects require baseline reconciliation; no blind bootstrap.')
    if role['name'] != 'postgres': issues.append('The bootstrap owner session must be reviewed.')
    if set(clients) != {'anon', 'authenticated'}: issues.append('Managed ordinary-client roles were not found.')
    return {'status': 'held' if issues else 'ready_for_baseline_review', 'target': identity,
            'readOnly': True, 'issues': issues, 'owner': role,
            'existingRelations': [dict(row) for row in objects], 'existingFunctions': [dict(row) for row in functions],
            'extensions': extensions, 'platformSchemasPresent': schemas, 'clientRoles': clients,
            'operationalRowsRead': 0, 'sqlApplied': False, 'operationalReleaseApproved': False,
            'externalChecksPending': ['Data API settings and deny requests', 'Actual owner/default grants',
                'Auth/Vault/cron/edge function configuration', 'Separate managed restore target', 'Compiled-app walkthrough']}


async def inspect_target(source_env, development_env):
    report = {'status': 'held', 'readOnly': True, 'sqlApplied': False, 'operationalReleaseApproved': False}
    conn = None
    try:
        source = dotenv_values(source_env); target = dotenv_values(development_env)
        identity = target_identity(source.get('DATABASE_URL') or '', target.get('DATABASE_URL') or '',
                                   target.get('JMAX_DEVELOPMENT_PROJECT_REF') or '')
        if target.get('USE_PG') != 'true' or any(target.get(name + '_ENABLED') != 'false' for name in readiness.FEATURES):
            raise DevelopmentTargetError('Development preparation requires PostgreSQL mode and all native features explicitly held.')
        conn = await asyncpg.connect(target['DATABASE_URL'], timeout=20, ssl='require', statement_cache_size=0,
                                     server_settings={'default_transaction_read_only': 'on'})
        report = await inspect_empty_target(conn, identity)
    except DevelopmentTargetError as exc:
        # Validation errors above are fixed text and never contain the URL.
        report['reason'] = str(exc)
    except Exception as exc:
        report.update(reason='Development inspection failed; connection material is omitted.', errorType=type(exc).__name__)
    finally:
        if conn is not None: await conn.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare'); prepare.add_argument('--directory', required=True)
    prepare.add_argument('--first-version', default='20261007000001')
    verify = sub.add_parser('verify'); verify.add_argument('--directory', required=True)
    inspect = sub.add_parser('inspect-target'); inspect.add_argument('--source-env', required=True)
    inspect.add_argument('--development-env', required=True); inspect.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        report = prepare_bundle(args.directory, args.first_version)
    elif args.command == 'verify':
        report = verify_bundle(args.directory)
    else:
        report = asyncio.run(inspect_target(args.source_env, args.development_env))
        Path(args.output).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))
    return 2 if report['status'] == 'held' else 0


if __name__ == '__main__':
    raise SystemExit(main())
