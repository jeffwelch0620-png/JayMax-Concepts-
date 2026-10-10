"""Read-only application catalog capture and offline baseline comparison.

Never applies SQL, repairs migration history, imports rows, or approves deployment.
Snapshots contain schema metadata and definition hashes, not function bodies,
connection material, business rows, or migration statement bodies.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import asyncpg
from dotenv import dotenv_values

from deployment_readiness import connection_configured
from native_backup import CATALOG, NAMESPACES

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ('public', 'integrations', 'purchasing', 'actual_inventory', 'prep_inventory')
FORMAT = 'jaymax-schema-catalog-v1'
KEYS = {
    'schemas': ('nspname',), 'relations': ('nspname', 'relname'),
    'columns': ('nspname', 'relname', 'attname'),
    'constraints': ('nspname', 'relname', 'conname'),
    'functions': ('nspname', 'proname', 'args'),
    'triggers': ('nspname', 'relname', 'tgname'),
    'indexes': ('nspname', 'relname'), 'views': ('nspname', 'relname'),
    'policies': ('nspname', 'relname', 'polname'),
    'types': ('nspname', 'typname'), 'sequence_definitions': ('nspname', 'relname'),
}
# Owner/grant differences between managed Supabase and disposable PostgreSQL
# are reported independently; they are never treated as structural equivalence.
ACCESS_FIELDS = {'owner', 'acl'}
DEFINITION_FIELDS = {'definition', 'default_expr', 'using_expr', 'check_expr', 'typdefault', 'body', 'settings'}


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def safe_record(record):
    result = dict(record)
    for field in DEFINITION_FIELDS & result.keys():
        value = result.pop(field)
        result[field + '_sha256'] = None if value is None else digest(value)
    return result


def reference_history():
    text = (ROOT / 'supabase/README.md').read_text(encoding='utf-8')
    return [{'version': version, 'name': name.split(' (', 1)[0].strip()}
            for version, name in re.findall(r'^\| (\d{14}) \| ([^|]+) \|', text, re.M)]


async def migration_history(conn):
    table = 'supabase_migrations.schema_migrations'
    if not await conn.fetchval('SELECT to_regclass($1) IS NOT NULL', table):
        return {'status': 'unavailable', 'reason': 'Hosted migration ledger is absent', 'entries': []}
    columns = set(await conn.fetchval("SELECT array_agg(attname::text) FROM pg_attribute WHERE attrelid=to_regclass($1) AND attnum>0 AND NOT attisdropped", table) or [])
    if not {'version', 'name'} <= columns:
        return {'status': 'unavailable', 'reason': 'Ledger version/name columns cannot be checked', 'entries': []}
    # Read only migration identities, not SQL statement bodies or business data.
    entries = [dict(row) for row in await conn.fetch('SELECT version::text AS version,name::text AS name FROM supabase_migrations.schema_migrations ORDER BY version::text,name::text')]
    expected = reference_history()
    actual = {row['version']: row['name'] for row in entries}
    missing = [row for row in expected if row['version'] not in actual]
    renamed = [{'version': row['version'], 'referenceName': row['name'], 'hostedName': actual[row['version']]}
               for row in expected if row['version'] in actual and row['name'] != actual[row['version']]]
    versions = {row['version'] for row in expected}
    return {'status': 'identities_match' if not missing and not renamed else 'different',
            'entries': entries, 'missingReferenceVersions': missing, 'renamedReferenceVersions': renamed,
            'additionalVersions': [row for row in entries if row['version'] not in versions],
            'statementChecksumsVerified': False,
            'limit': 'Version/name identity is not proof of applied SQL contents or completeness.'}


async def capture(conn):
    catalog = {}
    async with conn.transaction(isolation='repeatable_read', readonly=True):
        await conn.execute("SET LOCAL statement_timeout='20s'")
        await conn.execute('SET LOCAL search_path=pg_catalog')
        version = await conn.fetchval("SELECT current_setting('server_version')")
        for group in KEYS:
            # Reuse only metadata SQL, never native_backup.snapshot_manifest,
            # which reads business rows and is intentionally disposable-only.
            query = CATALOG[group].replace(NAMESPACES, 'n.nspname=ANY($1::text[])')
            if group == 'functions':
                query = query.replace('p.proacl::text AS acl',
                    "p.prosrc AS body,array_to_json(p.proconfig)::text AS settings,p.prosecdef AS security_definer,"
                    "p.provolatile::text AS volatility,p.proisstrict AS strict,"
                    "pg_get_function_result(p.oid) AS result_type,l.lanname AS language,p.proacl::text AS acl")
                query = query.replace('JOIN pg_namespace n ON n.oid=p.pronamespace',
                                      'JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_language l ON l.oid=p.prolang')
            rows = await conn.fetch('SELECT to_jsonb(r)::text AS value FROM (' + query + ') r', list(SCHEMAS))
            catalog[group] = [safe_record(json.loads(row['value'])) for row in rows]
            catalog[group].sort(key=lambda row: json.dumps(row, sort_keys=True))
        history = await migration_history(conn)
        access = []
        for role in ('anon', 'authenticated'):
            if not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=$1)', role):
                access.append({'role': role, 'status': 'role_absent'}); continue
            functions = await conn.fetch("SELECT n.nspname,p.proname,pg_get_function_identity_arguments(p.oid) AS args,has_function_privilege($1,p.oid,'EXECUTE') AS can_execute FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=ANY($2::text[]) AND p.prokind='f'", role, list(SCHEMAS))
            views = await conn.fetch("SELECT n.nspname,c.relname,c.reloptions,has_schema_privilege($1,n.oid,'USAGE') AS schema_usage,has_table_privilege($1,c.oid,'SELECT') AS can_select FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($2::text[]) AND c.relkind IN ('v','m')", role, list(SCHEMAS))
            access.append({'role': role, 'status': 'checked', 'functions': [dict(row) for row in functions], 'views': [dict(row) for row in views]})
    return {'format': FORMAT, 'capturedAt': datetime.now(timezone.utc).isoformat(),
            'serverVersion': version, 'schemasRequested': list(SCHEMAS),
            'catalog': catalog, 'migrationHistory': history, 'clientAccess': access, 'readOnly': True,
            'businessRowsIncluded': False, 'secretValuesIncluded': False,
            'operationalReleaseApproved': False}


def compare(reference, hosted):
    if reference.get('format') != FORMAT or hosted.get('format') != FORMAT:
        raise ValueError('Use schema catalog snapshots of the supported format')
    differences = []; access = []; counts = {}
    for group, keys in KEYS.items():
        # The retained baseline covers public only. Extra private schemas are
        # summarized separately; their absence from the reference is not drift.
        def indexed(snapshot):
            records = snapshot['catalog'][group]
            result = {}
            for row in records:
                if row['nspname'] != 'public':
                    continue
                key = tuple(row[k] for k in keys)
                if key in result:
                    raise ValueError('Duplicate catalog identity')
                result[key] = row
            return result
        left, right = indexed(reference), indexed(hosted)
        matched = 0
        for key in sorted(left.keys() | right.keys(), key=str):
            label = '.'.join(str(part) for part in key)
            if key not in left or key not in right:
                differences.append({'group': group, 'object': label,
                                    'kind': 'hosted_addition' if key not in left else 'missing_on_hosted'})
                continue
            a, b = left[key], right[key]
            changed = {field: {'reference': a.get(field), 'hosted': b.get(field)}
                       for field in a.keys() | b.keys() if field not in ACCESS_FIELDS and a.get(field) != b.get(field)}
            grants = {field: {'reference': a.get(field), 'hosted': b.get(field)}
                      for field in ACCESS_FIELDS if a.get(field) != b.get(field)}
            if changed:
                differences.append({'group': group, 'object': label, 'kind': 'definition_changed', 'fields': changed})
            else:
                matched += 1
            if grants:
                access.append({'group': group, 'object': label, 'fields': grants})
        counts[group] = {'reference': len(left), 'hosted': len(right), 'structurallyMatched': matched}
    return {'format': 'jaymax-schema-reconciliation-v1',
            'status': 'differences_require_review' if differences else 'public_structure_matches_reference',
            'counts': counts, 'differences': differences, 'ownershipAndAclDifferences': access,
            'hostedMigrationHistory': hosted['migrationHistory'],
            'hostedClientAccess': hosted.get('clientAccess', []),
            'additionalSchemaObjects': {schema: {group: sum(row['nspname'] == schema for row in records)
                                                 for group, records in hosted['catalog'].items()}
                                        for schema in SCHEMAS if schema != 'public'},
            'referenceServerVersion': reference['serverVersion'], 'hostedServerVersion': hosted['serverVersion'],
            'operationalReleaseApproved': False,
            'limits': ['Canonical catalog definitions may differ across PostgreSQL versions; review differences before changing anything.',
                       'Owner/ACL changes are separate findings, not automatic fixes.',
                       'Not a backup or proof of Data API exposure, business data compatibility, or hosted restore.',
                       'No SQL application or migration history repair is performed.']}


async def main(args):
    if args.command == 'compare':
        report = compare(json.loads(Path(args.reference).read_text()), json.loads(Path(args.hosted).read_text()))
    else:
        values = dotenv_values(args.backend_env)
        dsn = values.get('DATABASE_URL') or ''
        report = {'status': 'held', 'reason': 'Configure the private PostgreSQL connection', 'operationalReleaseApproved': False}
        if connection_configured(dsn):
            conn = None
            try:
                conn = await asyncpg.connect(dsn, timeout=20, statement_cache_size=0, ssl='require',
                                             server_settings={'default_transaction_read_only': 'on'})
                report = await capture(conn)
            except Exception as exc:
                # Database exceptions can embed credentials; emit only the class.
                report = {'status': 'held', 'reason': 'Read-only schema capture failed', 'errorType': type(exc).__name__, 'operationalReleaseApproved': False}
            finally:
                if conn is not None:
                    await conn.close()
    Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return 2 if report.get('status') in ('held', 'differences_require_review') else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    live = sub.add_parser('capture'); live.add_argument('--backend-env', required=True)
    offline = sub.add_parser('compare'); offline.add_argument('--reference', required=True); offline.add_argument('--hosted', required=True)
    for command in (live, offline):
        command.add_argument('--output', required=True)
    raise SystemExit(asyncio.run(main(parser.parse_args())))
