"""One reviewed par-table upgrade; never an application startup migration.

The hosted entry point is separate. This module accepts an original 29-file
receipt and the retained source-index core plan as historical evidence only.
It never replays those migrations or accepts an arbitrary replacement SQL file.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import apply_additive_migration as prior
import deployment_readiness as readiness
import hosted_install_preservation as preservation
import native_backup
import schema_reconciliation as catalog
from install_lock import INSTALLER_LOCK
from readonly_snapshot import readonly_snapshot, preserve_cleanup_failure, error_details

FORMAT = 'jaymax-additive-reviewed-par-plan-v2'
SOURCE = '20261018_reviewed_inventory_pars.sql'
SOURCE_SHA = '84814517f75bb58940a36facdbf5a7934036ff5b388e97a820038e837416506e'
BODY_SHA = '3a189a8b2a352cbd560cea88194dbde1940f160a54e7bcd4616d719c47b88c48'
TABLE = 'purchasing.inventory_par_versions'
REFERENCE = readiness.ROOT / 'docs/REVIEWED_PAR_INSTALL_CATALOG.json'
REFERENCE_SHA = '8a18effb17929604c76817ed7478b112033df4886e4434c0c1e6a4cce01e8e17'
AdditiveFailure = prior.AdditiveFailure
digest = prior.digest
sql_body = prior.sql_body
local_target = prior.local_target


class BackendPermissionHeld(ValueError):
    """Bounded operator metadata; role names belong in private receipts only."""
    MESSAGES = {
        'flags': 'Reviewed backend must be an existing unprivileged LOGIN role',
        'membership': 'Reviewed backend role membership requires separate review',
        'ddl': 'Reviewed backend DDL authority is not allowed',
        'ownership': 'Reviewed backend object ownership is not allowed',
        'default_acl': 'Future backend default grants require separate review',
        'new_par_access': 'New par runtime access requires separate review',
    }

    @classmethod
    def valid_detail(cls, role, rule):
        return (isinstance(role, str) and re.fullmatch(r'[a-z_][a-z0-9_]{0,62}', role) is not None
                and isinstance(rule, str) and rule in cls.MESSAGES)

    def __init__(self, role, rule):
        if not self.valid_detail(role, rule):
            raise ValueError('Invalid backend permission hold metadata')
        self.role, self.rule = role, rule
        super().__init__(self.MESSAGES[rule])


def backend_permission_details(error):
    """Accept only our typed, validated detail; never copy driver attributes."""
    if isinstance(error, BackendPermissionHeld):
        role, rule = getattr(error, 'role', None), getattr(error, 'rule', None)
        if BackendPermissionHeld.valid_detail(role, rule):
            return {'backendPermissionHold': {'role': role, 'rule': rule}}
    return {}


def source_bytes():
    raw = (readiness.ROOT / 'migrations' / SOURCE).read_bytes()
    if digest(raw) != SOURCE_SHA or digest(sql_body(raw).encode()) != BODY_SHA:
        raise ValueError('Reviewed par migration bytes changed')
    return raw


def sources():
    paths = ['tools/ops/apply_reviewed_par_migration.py', 'tools/ops/hosted_reviewed_pars.py',
             'tools/ops/apply_additive_migration.py', 'tools/ops/hosted_additive_index.py',
             'backend/readonly_snapshot.py', 'backend/install_lock.py',
             'backend/hosted_install_preservation.py', 'backend/hosted_native_install.py',
             'backend/hosted_test_trial.py', 'backend/deployment_readiness.py',
             'backend/native_backup.py', 'backend/hosted_backup.py', 'backend/maintenance_connection.py',
             'backend/schema_reconciliation.py', 'backend/db_tls.py',
             'backend/managed_development.py', 'docs/REVIEWED_PAR_INSTALL_CATALOG.json',
             'docs/RUNTIME_PERMISSION_CANDIDATE.json']
    paths += ['migrations/' + name for name in readiness.MIGRATIONS]
    return {path: digest((readiness.ROOT / path).read_bytes()) for path in paths}


def reference():
    raw = REFERENCE.read_bytes()
    if digest(raw) != REFERENCE_SHA:
        raise ValueError('Reviewed par catalog reference changed')
    value = json.loads(raw)
    if (value.get('format') != 'jaymax-reviewed-par-catalog-v1'
            or value.get('sourceSha256') != SOURCE_SHA or value.get('bodySha256') != BODY_SHA):
        raise ValueError('Unsupported reviewed par catalog')
    return value


def checked_prior(original, source_index):
    entries, history = prior.checked_delivery(original)
    prior.validate_plan(source_index)
    retained, earlier = prior.checked_delivery(source_index['originalInstallation'])
    if entries != retained or history != earlier:
        raise ValueError('Source-index delivery differs from original installation')
    entry = source_index['migration']
    if (set(source_index['baseline']['ledger']) != set(history) | {e['deliveryVersion'] for e in entries}
            or entry['deliveryVersion'] <= max(source_index['baseline']['ledger'])):
        raise ValueError('Source-index ledger baseline differs from original delivery')
    if any(source_index['baseline']['ledger'].get(v) != h for v, h in history.items()):
        raise ValueError('Source-index historical ledger changed')
    return entries, history, deepcopy(entry)


async def verify_prior(conn, original, source_index):
    entries, history, index = checked_prior(original, source_index)
    await prior.installer.ledger_shape(conn)
    actual = await preservation.ledger_fingerprints(conn)
    expected = {e['deliveryVersion']: e for e in entries + [index]}
    if set(actual) != set(history) | set(expected) or any(actual.get(v) != h for v, h in history.items()):
        raise ValueError('Installed prior history is missing, extra or changed')
    rows = await conn.fetch('SELECT version,name,statements FROM supabase_migrations.schema_migrations '
                            'WHERE version=ANY($1::text[])', sorted(expected))
    for row in rows:
        entry = expected[row['version']]
        name = entry.get('name') or Path(entry['deliveryFile']).name.split('_', 1)[1].removesuffix('.sql')
        if (row['name'] != name or not row['statements'] or len(row['statements']) != 1
                or digest(row['statements'][0].encode()) != entry['bodySha256']):
            raise ValueError('Installed prior migration name or body changed')


async def capture_catalog(conn):
    """All backup catalog groups, hashed definitions and no business row values."""
    result = {}
    for group, sql in native_backup.CATALOG.items():
        query = sql.replace(native_backup.NAMESPACES, 'n.nspname=ANY($1::text[])')
        if group == 'extensions':
            rows = await conn.fetch('SELECT to_jsonb(r)::text AS value FROM (' + query + ') r')
        else:
            rows = await conn.fetch('SELECT to_jsonb(r)::text AS value FROM (' + query + ') r',
                                   list(catalog.SCHEMAS))
        result[group] = sorted([catalog.safe_record(json.loads(row['value'])) for row in rows],
                               key=lambda row: json.dumps(row, sort_keys=True))
    return result


async def snapshot(conn):
    # Deparser output must not depend on a caller's search path/settings.
    # A nested savepoint retains the outer repeatable-read snapshot and writes
    # no data; a standalone call owns its consistent read-only transaction.
    async with readonly_snapshot(conn):
        await conn.execute("SET LOCAL search_path=pg_catalog; SET LOCAL quote_all_identifiers=off; "
                           "SET LOCAL TIME ZONE 'UTC'; SET LOCAL DateStyle='ISO,YMD'; "
                           "SET LOCAL IntervalStyle=postgres; SET LOCAL bytea_output=hex; "
                           "SET LOCAL extra_float_digits=3; SET LOCAL standard_conforming_strings=on")
        return await _snapshot(conn)


async def _snapshot(conn):
    # Collect the same preservation fields directly. prior.snapshot also builds
    # a different catalog/access report that this par snapshot would discard.
    identity = dict(await conn.fetchrow("SELECT current_database() AS database,current_user AS actor,"
                    "(SELECT oid::bigint FROM pg_database WHERE datname=current_database()) AS database_oid,"
                    "inet_server_addr()::text AS server_address,inet_server_port() AS server_port,"
                    "current_setting('server_version_num') AS server_version"))
    columns = await preservation.original_columns(conn)
    value = {'identity': identity, 'ledger': await preservation.ledger_fingerprints(conn),
        'ledgerCatalog': await preservation.ledger_contract(conn),
        'columns': [{'schema': k[0], 'table': k[1], 'columns': v} for k,v in sorted(columns.items())],
        'rows': await preservation.fingerprints(conn,columns),
        'catalog': await capture_catalog(conn)}
    # Table ACLs do not include column grants or schema default privileges.
    # The par migration adds neither; preserve these separately and exactly.
    value['columnAcl'] = [dict(row) for row in await conn.fetch('''SELECT n.nspname,c.relname,a.attname,
        a.attacl::text AS acl FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[])
        AND a.attnum>0 AND NOT a.attisdropped AND a.attacl IS NOT NULL ORDER BY 1,2,3''',list(catalog.SCHEMAS))]
    value['defaultAcl'] = [dict(row) for row in await conn.fetch('''SELECT
        pg_get_userbyid(d.defaclrole) AS creator,coalesce(n.nspname,'global') AS scope,
        d.defaclobjtype::text AS kind,d.defaclacl::text AS acl FROM pg_default_acl d
        LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace
        WHERE d.defaclnamespace=0 OR n.nspname=ANY($1::text[]) ORDER BY 1,2,3''',list(catalog.SCHEMAS))]
    value['serverMajor'] = int(value['identity']['server_version']) // 10000
    value['indexStates'] = [dict(row) for row in await conn.fetch('''SELECT n.nspname,c.relname,
        i.indisvalid AS valid,i.indisready AS ready,i.indislive AS live,i.indimmediate AS immediate,
        i.indisunique AS unique,i.indisprimary AS primary,i.indisexclusion AS exclusion,
        i.indisclustered AS clustered,i.indisreplident AS replica
        FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=ANY($1::text[]) ORDER BY 1,2''',list(catalog.SCHEMAS))]
    return value


def normalize_owner(records, actor):
    if not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}', actor):
        raise ValueError('Unsupported migration actor name')
    result = deepcopy(records)
    for rows in result.values():
        for row in rows:
            if row.get('owner') == actor:
                row['owner'] = '@migration_actor'
            acl = row.get('acl')
            def replace(value):
                return re.sub(r'(?<![a-z0-9_])' + re.escape(actor) + r'(?![a-z0-9_])',
                              '@migration_actor', value)
            if isinstance(acl, str):
                row['acl'] = replace(acl)
            elif isinstance(acl, list):
                row['acl'] = sorted(replace(value) for value in acl)
    return result


def catalog_delta(before, after):
    """Multiset subtraction catches changes/deletions, including FK parent triggers."""
    if before.keys() != after.keys():
        raise ValueError('Catalog group coverage changed')
    added = {}
    for group, rows in before.items():
        remaining = deepcopy(after[group])
        for row in rows:
            if row not in remaining:
                raise ValueError('An existing catalog definition or permission changed')
            remaining.remove(row)
        added[group] = sorted(remaining, key=lambda row: json.dumps(row, sort_keys=True))
    return added


def role_groups(clients, backends):
    """Explicit classification only; never infer trust from a role-name prefix."""
    for group in (clients, backends):
        if (not isinstance(group, (list, tuple))
                or any(not isinstance(role, str) or not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}', role)
                       for role in group) or len(set(group)) != len(group)):
            raise ValueError('Invalid reviewed par role group')
    if not {'anon', 'authenticated'} <= set(clients) or set(clients) & set(backends):
        raise ValueError('Browser roles are mandatory and backend groups must be disjoint')
    return list(clients), list(backends)


async def backend_permissions(conn, backends):
    """Preserve existing backend access; authorize no new runtime permissions.

    Full ACL/role/catalog snapshots still bind existing access before and after
    DDL. This narrow contract is not the deferred runtime candidate assessment.
    Backend logins must not control DDL/roles, inherit other authorities, receive
    future default grants, or gain the new par table/function through this install.
    """
    for role in backends:
        flags = await conn.fetchrow('''SELECT oid,rolcanlogin,rolsuper,rolbypassrls,
            rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=$1''', role)
        if (flags is None or not flags['rolcanlogin']
                or any(flags[key] for key in ('rolsuper','rolbypassrls','rolcreatedb','rolcreaterole','rolreplication'))):
            raise BackendPermissionHeld(role, 'flags')
        # The existing administrator may hold the grant created by CREATE ROLE.
        # All other incoming membership (including NOINHERIT + SET ROLE) holds.
        if await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM pg_auth_members
                WHERE member=$1 OR (roleid=$1 AND member<>(SELECT oid FROM pg_roles WHERE rolname=current_user)))''', flags['oid']):
            raise BackendPermissionHeld(role, 'membership')
        if (await conn.fetchval('''SELECT has_database_privilege($1,current_database(),'CREATE')
                OR EXISTS(SELECT 1 FROM pg_database WHERE datname=current_database() AND datdba=$2)''',role,flags['oid'])
                or await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM pg_namespace
                    WHERE nspname=ANY($2::text[]) AND (has_schema_privilege($1,oid,'CREATE') OR nspowner=$3))''',
                    role,list(catalog.SCHEMAS)+['supabase_migrations'],flags['oid'])):
            raise BackendPermissionHeld(role, 'ddl')
        if await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=ANY($2::text[]) AND c.relowner=$1)
            OR EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE n.nspname=ANY($2::text[]) AND p.proowner=$1)''',
                flags['oid'],list(catalog.SCHEMAS)+['supabase_migrations']):
            raise BackendPermissionHeld(role, 'ownership')
        if await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM pg_default_acl d
                LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace,
                LATERAL aclexplode(d.defaclacl) a
                WHERE (d.defaclnamespace=0 OR n.nspname=ANY($2::text[])) AND a.grantee=$1)''',
                flags['oid'],list(readiness.PRIVATE)+['supabase_migrations']):
            raise BackendPermissionHeld(role, 'default_acl')
        if await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='purchasing' AND c.relname='inventory_par_versions'
                AND (has_table_privilege($1,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                    OR has_any_column_privilege($1,c.oid,'SELECT,INSERT,UPDATE,REFERENCES')))
            OR EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE n.nspname='purchasing' AND p.proname='guard_inventory_par'
                AND has_function_privilege($1,p.oid,'EXECUTE'))''',role):
            raise BackendPermissionHeld(role, 'new_par_access')


async def readiness_check(conn, roles, before=False, *, backend_roles=()):
    clients, backends = role_groups(roles, backend_roles)
    # Reuse the historical predicate unchanged: column-level ledger exposure is
    # forbidden for both groups, even when private Inventory access is intentional.
    from hosted_additive_index import ledger_clients
    await backend_permissions(conn, backends)
    await ledger_clients(conn, clients + backends)
    # The historical readiness inspector checks table privileges separately.
    # Do not let a column-only client grant disappear when groups are split.
    for client in clients:
        if await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=ANY($2::text[]) AND CASE WHEN c.relkind IN ('r','p','v','m')
                THEN has_any_column_privilege($1,c.oid,'SELECT,INSERT,UPDATE,REFERENCES') ELSE false END)''',client,list(readiness.PRIVATE)):
            raise ValueError('Ordinary client private column access is not allowed')
    value = await readiness.inspect(conn, client_roles=clients,
                                    migration_baseline='source_index_v1' if before else 'current')
    if value['issues'] or value['warnings']:
        raise ValueError('Reviewed par installation readiness is held')
    return value


async def absent(conn):
    if (await conn.fetchval('SELECT to_regclass($1) IS NOT NULL', TABLE)
            or await conn.fetchval("SELECT to_regprocedure('purchasing.guard_inventory_par()') IS NOT NULL")):
        raise ValueError('Par storage or guard already exists; reconcile instead')
    names = [row['relname'] for row in reference()['added']['relations']]
    if await conn.fetchval("SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                           "WHERE n.nspname='purchasing' AND c.relname=ANY($1::text[]))", names):
        raise ValueError('A reviewed par relation name collides')


def validate_plan(plan):
    required = {'format', 'originalInstallation', 'sourceIndexPlan', 'clientRoles', 'baseline',
                'migration', 'sourceHashes', 'referenceSha256', 'automaticApply', 'operationalReleaseApproved',
                'backendRoles'}
    if (not isinstance(plan, dict) or set(plan) != required or plan['format'] != FORMAT
            or plan['automaticApply'] is not False or plan['operationalReleaseApproved'] is not False):
        raise ValueError('Unsupported reviewed par plan or execution flags')
    checked_prior(plan['originalInstallation'], plan['sourceIndexPlan'])
    source_bytes(); ref = reference()
    if (plan['sourceHashes'] != sources() or plan['referenceSha256'] != REFERENCE_SHA
            or plan['baseline']['serverMajor'] != ref['serverMajor']):
        raise ValueError('Reviewed par source, reference or PostgreSQL major changed')
    entry = plan['migration']
    if (set(entry) != {'sourceFile', 'sha256', 'bodySha256', 'deliveryVersion', 'name'}
            or entry['sourceFile'] != 'migrations/' + SOURCE or entry['sha256'] != SOURCE_SHA
            or entry['bodySha256'] != BODY_SHA or entry['name'] != 'reviewed_inventory_pars'):
        raise ValueError('Reviewed par SQL binding changed')
    version = entry['deliveryVersion']
    if not re.fullmatch(r'\d{14}', version) or version <= max(plan['baseline']['ledger']):
        raise ValueError('New delivery must follow every installed ledger version')
    datetime.strptime(version, '%Y%m%d%H%M%S')
    if not isinstance(plan['clientRoles'], list) or not isinstance(plan['backendRoles'], list):
        raise ValueError('Invalid client roles')
    role_groups(plan['clientRoles'], plan['backendRoles'])
    return sql_body(source_bytes())


async def prepare(conn, original, source_index, version, client_roles=('anon', 'authenticated'), *, backend_roles=()):
    clients, backends = role_groups(client_roles, backend_roles)
    checked_prior(original, source_index)
    async with readonly_snapshot(conn):
        await conn.execute("SET LOCAL statement_timeout='20s'")
        await verify_prior(conn, original, source_index)
        await absent(conn)
        await readiness_check(conn, clients, before=True, backend_roles=backends)
        baseline = await snapshot(conn)
        if any(not all(row[k] for k in ('valid','ready','live')) for row in baseline['indexStates']):
            raise ValueError('An existing application index is invalid or not ready/live')
    result = {'format': FORMAT, 'originalInstallation': deepcopy(original),
              'sourceIndexPlan': deepcopy(source_index), 'clientRoles': clients, 'backendRoles': backends,
              'baseline': baseline, 'sourceHashes': sources(), 'referenceSha256': REFERENCE_SHA,
              'migration': {'sourceFile': 'migrations/' + SOURCE, 'sha256': SOURCE_SHA,
                            'bodySha256': BODY_SHA, 'deliveryVersion': version, 'name': 'reviewed_inventory_pars'},
              'automaticApply': False, 'operationalReleaseApproved': False}
    validate_plan(result)
    return result


async def _verify_outcome(conn, plan):
    validate_plan(plan)
    async with readonly_snapshot(conn):
        await conn.execute("SET LOCAL statement_timeout='20s'")
        current = await snapshot(conn)
        base = plan['baseline']
        if current == base:
            return {'status': 'verified_not_applied', 'readOnly': True, 'sqlCommitted': False}
        if current['identity'] != base['identity'] or current['ledgerCatalog'] != base['ledgerCatalog']:
            raise ValueError('Database identity or ledger security/structure changed')
        if current['columnAcl'] != base['columnAcl'] or current['defaultAcl'] != base['defaultAcl']:
            raise ValueError('Application column or default privileges changed')
        names={row['relname'] for row in reference()['added']['indexes']}
        new_states=[row for row in current['indexStates'] if row['nspname']=='purchasing' and row['relname'] in names]
        old_states=[row for row in current['indexStates'] if row not in new_states]
        primary={row['conname'] for row in reference()['added']['constraints'] if row['contype']=='p'}
        if (old_states != base['indexStates'] or len(new_states)!=len(names)
                or any(not all(row[k] for k in ('valid','ready','live','immediate','unique'))
                       or row['primary']!=(row['relname'] in primary)
                       or any(row[k] for k in ('exclusion','clustered','replica')) for row in new_states)):
            raise ValueError('Existing or new par index state differs from review')
        version = plan['migration']['deliveryVersion']
        if (set(current['ledger']) != set(base['ledger']) | {version}
                or any(current['ledger'].get(v) != h for v, h in base['ledger'].items())):
            raise ValueError('Par or historical ledger outcome is inconsistent')
        row = await conn.fetchrow('SELECT name,statements FROM supabase_migrations.schema_migrations WHERE version=$1', version)
        if row['name'] != plan['migration']['name'] or row['statements'] != [sql_body(source_bytes())]:
            raise ValueError('Installed par ledger body changed')
        expected_columns = base['columns'] + [{'schema': 'purchasing', 'table': 'inventory_par_versions',
            'columns': [{'name':r['attname'],'type':r['type']} for r in sorted(reference()['added']['columns'], key=lambda r:r['attnum'])
                        if r['relname']=='inventory_par_versions']}]
        if sorted(current['columns'],key=lambda r:(r['schema'],r['table'])) != sorted(expected_columns,key=lambda r:(r['schema'],r['table'])):
            raise ValueError('Unexpected application columns or relations changed')
        # Only after proving identical original projections may we reuse the
        # fingerprints just collected in this same outcome snapshot. A later
        # phase/fresh connection always captures its own complete snapshot.
        old_rows = {x['schema']+'.'+x['table']: current['rows'][x['schema']+'.'+x['table']]
                    for x in base['columns']}
        if old_rows != base['rows']:
            raise ValueError('Original application rows changed')
        if await conn.fetchval('SELECT count(*) FROM purchasing.inventory_par_versions') != 0:
            raise ValueError('Par installation must not create review records')
        delta = normalize_owner(catalog_delta(base['catalog'], current['catalog']), current['identity']['actor'])
        if delta != reference()['added']:
            raise ValueError('New par catalog/security delta differs from the reviewed reference')
        check = await readiness_check(conn, plan['clientRoles'], backend_roles=plan['backendRoles'])
        return {'status': 'verified_applied', 'readOnly': True, 'sqlCommitted': True,
                'originalRowsAndCatalogPreserved': True, 'historicalLedgerPreserved': True,
                'nativeReadiness': check}


async def verify_outcome(conn, plan):
    if conn.is_in_transaction():
        raise ValueError('Independent reconciliation requires a fresh connection transaction')
    if not await conn.fetchval('SELECT pg_try_advisory_lock($1::bigint)', INSTALLER_LOCK):
        raise ValueError('An installation writer is active; retain unknown outcome')
    async with preserve_cleanup_failure(lambda:conn.execute('SELECT pg_advisory_unlock($1::bigint)',INSTALLER_LOCK),
                                        'lockReleaseErrorType'):
        return await _verify_outcome(conn, plan)


async def apply(conn, plan, *, guard=None):
    body = validate_plan(plan)
    if conn.is_in_transaction():
        raise ValueError('Par application requires its own outer transaction')
    report = {'status':'held','sqlCommitted':False,'commitAttempted':False,
              'migration':plan['migration'],'automaticRetry':False}
    locked = False; tx = None
    try:
        locked = await conn.fetchval('SELECT pg_try_advisory_lock($1::bigint)',INSTALLER_LOCK)
        if not locked: raise ValueError('Another installer is active')
        tx = conn.transaction(isolation='repeatable_read'); await tx.start()
        await conn.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'; "
                           "SET LOCAL idle_in_transaction_session_timeout='120s'")
        await conn.execute('LOCK TABLE supabase_migrations.schema_migrations IN EXCLUSIVE MODE')
        await preservation.lock_original_tables(conn,{(r['schema'],r['table']):r['columns'] for r in plan['baseline']['columns']})
        await conn.execute('SELECT pg_advisory_xact_lock($1::bigint)',INSTALLER_LOCK)
        if await snapshot(conn) != plan['baseline']:
            raise ValueError('Baseline changed or migration is already applied')
        await verify_prior(conn,plan['originalInstallation'],plan['sourceIndexPlan'])
        await absent(conn); await readiness_check(conn,plan['clientRoles'],before=True,backend_roles=plan['backendRoles'])
        if guard is not None: await guard(conn,'before')
        await conn.execute("SET LOCAL statement_timeout='30s'")
        await conn.execute(body)
        if not conn.is_in_transaction(): raise RuntimeError('Migration escaped installation transaction')
        e=plan['migration']
        await conn.execute('INSERT INTO supabase_migrations.schema_migrations(version,name,statements) VALUES($1,$2,$3::text[])',
                           e['deliveryVersion'],e['name'],[body])
        report['precommitVerification']=await _verify_outcome(conn,plan)
        if guard is not None: report['additionalPrecommitVerification']=await guard(conn,'after')
        report['commitAttempted']=True; await tx.commit(); tx=None
        report.update(status='committed_requires_independent_verification',sqlCommitted=True)
        return report
    except Exception as exc:
        report.update(error_details(exc))
        report.update(backend_permission_details(exc))
        if report['commitAttempted']: report.update(status='commit_outcome_unknown',sqlCommitted=None)
        elif tx is not None:
            try: await tx.rollback(); report['rollbackCompleted']=True
            except Exception as rollback:
                report.update(status='rollback_outcome_unknown',sqlCommitted=None,
                              rollbackErrorType=type(rollback).__name__)
        raise AdditiveFailure(report) from None
    finally:
        if locked:
            try: await conn.execute('SELECT pg_advisory_unlock($1::bigint)',INSTALLER_LOCK)
            except Exception: report['lockReleaseHeld']=True
