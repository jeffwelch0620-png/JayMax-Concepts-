"""Read-only assessment of the LOCAL, unapproved runtime permission candidate.

Never grants access or clears deployment_readiness's independent owner gate.
Only catalog metadata and privilege predicates are read; no business rows.
"""
import hashlib
import json
from pathlib import Path

import deployment_readiness as readiness

MANIFEST = readiness.ROOT / 'docs/RUNTIME_PERMISSION_CANDIDATE.json'
CONTRACT = readiness.ROOT / 'docs/RUNTIME_CATALOG_CONTRACT.json'
READ_ONLY_TABLES = {
    'purchasing.base_units', 'purchasing.legacy_supplier_contacts',
    'prep_inventory.legacy_planning_sources', 'prep_inventory.legacy_count_sources',
    'prep_inventory.legacy_container_sources', 'prep_inventory.legacy_day_sources',
}
PRIVATE_UPDATES = {
    'purchasing.import_files', 'purchasing.document_identities', 'purchasing.document_versions',
    'purchasing.po_receipts', 'actual_inventory.scopes', 'actual_inventory.count_snapshots',
    'purchasing.store_vendor_items', 'purchasing.store_supplier_contacts',
}
PUBLIC = {
    'stores': ('SELECT',), 'items': ('SELECT', 'INSERT', 'UPDATE'),
    'store_items': ('SELECT', 'INSERT', 'UPDATE'), 'vendor_items': ('SELECT', 'INSERT', 'UPDATE'),
    'vendors': ('SELECT', 'INSERT', 'UPDATE'), 'dishes': ('SELECT', 'INSERT', 'UPDATE', 'DELETE'),
    # UPDATE permits native SHARE locks; retained metadata triggers reject DML.
    'dish_lines': ('SELECT', 'INSERT', 'UPDATE', 'DELETE'), 'prep_items': ('SELECT', 'UPDATE'),
    'staff_members': ('SELECT', 'INSERT', 'UPDATE', 'DELETE'), 'store_state': ('SELECT', 'INSERT', 'UPDATE'),
    'activity_log': ('SELECT', 'INSERT'), 'purchase_orders': ('SELECT', 'INSERT', 'UPDATE'),
    'purchase_order_lines': ('SELECT', 'INSERT', 'UPDATE', 'DELETE'),
    'invoices': ('SELECT',), 'invoice_lines': ('SELECT',), 'prep_logs': ('SELECT',),
    'adjustments': ('SELECT',),
    'count_sessions': ('SELECT',), 'count_lines': ('SELECT',), 'reporting_periods': ('SELECT',),
    'store_vendor_contacts': ('SELECT',), 'staff_pins': ('SELECT',),
    'prep_list_lines': ('SELECT',), 'prep_recipe_stock': ('SELECT',),
    'prep_overrides': ('SELECT',), 'par_recommendations': ('SELECT',),
    'prep_lists': ('SELECT',), 'staff_tasks': ('SELECT',),
}
SCHEMAS = ('public', 'integrations', *readiness.PRIVATE)
TABLE_PRIVILEGES = ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER', 'MAINTAIN')
COLUMN_PRIVILEGES = ('SELECT', 'INSERT', 'UPDATE', 'REFERENCES')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def manifest():
    value = json.loads(MANIFEST.read_text())
    if value['publication'] != 'candidate; local test only':
        raise ValueError('Unreviewed profile')
    if set(value['migrationSha256']) != set(readiness.MIGRATIONS):
        raise ValueError('Reviewed runtime migration list drift')
    for name, expected in value['migrationSha256'].items():
        if hashlib.sha256((readiness.ROOT / 'migrations' / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Reviewed runtime SQL drift')
    return value


def table_privileges(profile):
    result = {}
    for name in profile['tables'] + profile['views']:
        privileges = ['SELECT']
        if name in profile['tables'] and name not in READ_ONLY_TABLES:
            privileges.append('INSERT')
        if name in PRIVATE_UPDATES:
            privileges.append('UPDATE')
        result[name] = privileges
    result.update({'public.' + name: list(privileges) for name, privileges in PUBLIC.items()})
    return result


async def catalog_contracts(conn):
    """Metadata fingerprints; caller must set search_path=pg_catalog in a read-only transaction.

    Used to compare a frozen independently installed LOCAL reference, never to
    silently accept the catalog of the target being assessed as its own baseline.
    Function bodies are hashed in memory and never returned or written.
    """
    functions = {}
    rows = await conn.fetch('''SELECT n.nspname AS schema, p.proname AS name,
        format('%I.%I(%s)',n.nspname,p.proname,oidvectortypes(p.proargtypes)) AS signature,
        pg_get_functiondef(p.oid) AS definition, p.prosecdef,
        p.prorettype='pg_catalog.trigger'::regtype AS trigger
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname=ANY($1::text[]) AND p.prokind IN ('f','p')
        AND NOT EXISTS(SELECT 1 FROM pg_depend d WHERE d.classid='pg_proc'::regclass
            AND d.objid=p.oid AND d.deptype='e') ORDER BY 3''', list(SCHEMAS))
    for row in rows:
        functions[row['signature']] = {
            'name': row['schema'] + '.' + row['name'],
            'definitionSha256': hashlib.sha256(row['definition'].encode()).hexdigest(),
            'securityDefiner': row['prosecdef'], 'trigger': row['trigger'],
        }
    relations = {}
    rows = await conn.fetch('''SELECT c.oid,n.nspname||'.'||c.relname AS name,c.relkind::text AS relkind,
        c.relrowsecurity,c.relforcerowsecurity,c.reloptions,
        CASE WHEN c.relkind IN ('v','m') THEN pg_get_viewdef(c.oid,false) END AS view
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=ANY($1::text[]) AND c.relkind IN ('r','p','v','m','S','f')
        AND NOT EXISTS(SELECT 1 FROM pg_depend d WHERE d.classid='pg_class'::regclass
            AND d.objid=c.oid AND d.deptype='e') ORDER BY 2''', list(SCHEMAS))
    for row in rows:
        columns = await conn.fetch('''SELECT a.attname,format_type(a.atttypid,a.atttypmod) AS type,
            a.attnotnull,a.attidentity::text AS attidentity,a.attgenerated::text AS attgenerated,pg_get_expr(d.adbin,d.adrelid) AS default_expr
            FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
            WHERE a.attrelid=$1 AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum''', row['oid'])
        constraints = await conn.fetch('''SELECT conname,contype::text AS contype,convalidated,condeferrable,condeferred,
            pg_get_constraintdef(oid,false) AS definition FROM pg_constraint WHERE conrelid=$1 ORDER BY conname''', row['oid'])
        triggers = await conn.fetch('''SELECT tgname,tgenabled::text AS tgenabled,pg_get_triggerdef(oid,false) AS definition
            FROM pg_trigger WHERE tgrelid=$1 AND NOT tgisinternal ORDER BY tgname''', row['oid'])
        value = {'kind': row['relkind'], 'rls': row['relrowsecurity'], 'forceRls': row['relforcerowsecurity'],
                 'options': row['reloptions'], 'view': row['view'],
                 'columns': [dict(r) for r in columns], 'constraints': [dict(r) for r in constraints],
                 'triggers': [dict(r) for r in triggers]}
        relations[row['name']] = {'kind': row['relkind'], 'shapeSha256': digest(value)}
    return {'functions': functions, 'relations': relations}


def contract(profile):
    value = json.loads(CONTRACT.read_text())
    if value.get('format') != 'jaymax-runtime-catalog-contract-v1' or value.get('sourceProfileSha256') != digest(profile):
        raise ValueError('Unreviewed catalog contract')
    if value.get('permissionMatrixSha256') != digest(table_privileges(profile)):
        raise ValueError('Reviewed permission matrix drift')
    if value.get('publicSchemaSha256') != hashlib.sha256((readiness.ROOT / 'supabase/schema.sql').read_bytes()).hexdigest():
        raise ValueError('Reviewed public reference drift')
    return value


async def inspect(conn, role):
    """Assess a named role without SET ROLE, DDL, grants, business reads or writes.

    A catalog-reader connection may assess a different runtime role. Its identity
    is reported separately; success does not prove actual LOGIN/pool behavior.
    An existing transaction is refused to guarantee our own read-only snapshot.
    """
    if conn.is_in_transaction():
        raise ValueError('Dedicated connection outside a transaction required')
    profile = manifest()
    expected = contract(profile)
    allowed = table_privileges(profile)
    issues = []
    def issue(kind, name, privilege=None):
        value = {'kind': kind, 'object': name}
        if privilege:
            value['privilege'] = privilege
        issues.append(value)

    async with conn.transaction(isolation='repeatable_read', readonly=True):
        await conn.execute('SET LOCAL search_path=pg_catalog')
        await conn.execute("SET LOCAL statement_timeout='20s'")
        reader = await conn.fetchval('SELECT current_user')
        version = int(await conn.fetchval('SHOW server_version_num')) // 10000
        if version != expected['postgresMajor']:
            issue('unreviewed_postgres_major', str(version))
        flags = await conn.fetchrow('''SELECT oid,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication
            FROM pg_roles WHERE rolname=$1''', role)
        if not flags:
            issue('missing_runtime_role', role)
        else:
            for key, value in dict(flags).items():
                if key != 'oid' and value:
                    issue('privileged_runtime_role', role, key)
            # NOINHERIT does not prevent assuming a granted role. Hold all role
            # membership until separately reviewed rather than overlooking SET ROLE.
            memberships = await conn.fetch('''WITH RECURSIVE memberships(roleid) AS (
                SELECT roleid FROM pg_auth_members WHERE member=$1
                UNION SELECT m.roleid FROM pg_auth_members m JOIN memberships x ON m.member=x.roleid)
                SELECT r.rolname FROM memberships x JOIN pg_roles r ON r.oid=x.roleid''', flags['oid'])
            for row in memberships:
                issue('unreviewed_role_membership', row['rolname'])
            if await conn.fetchval("SELECT has_database_privilege($1,current_database(),'CREATE')", role):
                issue('database_create_access', role)
            schemas = await conn.fetch('''SELECT nspname,nspowner=$1 AS owned,
                has_schema_privilege($1,oid,'USAGE') AS usage,
                has_schema_privilege($1,oid,'CREATE') AS create_access,
                has_schema_privilege($1,oid,'USAGE WITH GRANT OPTION') AS delegate_access
                FROM pg_namespace WHERE nspname=ANY($2::text[])''', flags['oid'], list(SCHEMAS))
            for name in {'public', *readiness.PRIVATE} - {r['nspname'] for r in schemas}:
                issue('missing_schema', name)
            for row in schemas:
                if not row['usage'] and row['nspname'] != 'integrations':
                    issue('missing_schema_usage', row['nspname'])
                if row['usage'] and row['nspname'] == 'integrations':
                    issue('excess_schema_usage', row['nspname'])
                if row['owned'] or row['create_access']:
                    issue('schema_ddl_access', row['nspname'])
                if row['delegate_access']:
                    issue('schema_grant_option', row['nspname'])
            # Effective privileges include PUBLIC and inherited grants. Column
            # ACLs are checked independently: table-level predicates miss them.
            rows = await conn.fetch('''SELECT c.oid,n.nspname||'.'||c.relname AS name,c.relkind::text AS relkind,
                c.relowner=$1 AS owned FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=ANY($2::text[]) AND c.relkind IN ('r','p','v','m','S','f') ORDER BY 2''', flags['oid'], list(SCHEMAS))
            for row in rows:
                name = row['name']
                if row['owned']:
                    issue('runtime_object_ownership', name)
                privileges = ('USAGE', 'SELECT', 'UPDATE') if row['relkind'] == 'S' else TABLE_PRIVILEGES
                predicate = 'has_sequence_privilege' if row['relkind'] == 'S' else 'has_table_privilege'
                actual = await conn.fetch('SELECT p, ' + predicate + '($1::name,$2::oid,p) AS permitted, '
                    + predicate + "($1::name,$2::oid,p||' WITH GRANT OPTION') AS delegate_access FROM unnest($3::text[]) p", role, row['oid'], list(privileges))
                for access in actual:
                    required = access['p'] in allowed.get(name, ())
                    if required != access['permitted']:
                        issue('missing_object_privilege' if required else 'excess_object_privilege', name, access['p'])
                    if access['delegate_access']:
                        issue('object_grant_option', name, access['p'])
                if row['relkind'] != 'S':
                    columns = await conn.fetch('''SELECT a.attname,p,
                        has_column_privilege($1::name,$2::oid,a.attnum,p) AS permitted,
                        has_column_privilege($1::name,$2::oid,a.attnum,p||' WITH GRANT OPTION') AS delegate_access FROM pg_attribute a
                        CROSS JOIN unnest($3::text[]) p WHERE a.attrelid=$2::oid AND a.attnum>0 AND NOT a.attisdropped
                        AND (has_column_privilege($1::name,$2::oid,a.attnum,p) OR
                             has_column_privilege($1::name,$2::oid,a.attnum,p||' WITH GRANT OPTION'))''', role, row['oid'], list(COLUMN_PRIVILEGES))
                    for column in columns:
                        if column['p'] not in allowed.get(name, ()):
                            issue('excess_column_privilege', name + '.' + column['attname'], column['p'])
                        if column['delegate_access']:
                            issue('column_grant_option', name + '.' + column['attname'], column['p'])
            functions = await conn.fetch('''SELECT n.nspname AS schema,p.oid,
                format('%I.%I(%s)',n.nspname,p.proname,oidvectortypes(p.proargtypes)) AS signature,
                has_function_privilege($1,p.oid,'EXECUTE') AS permitted,p.prosecdef,
                has_function_privilege($1,p.oid,'EXECUTE WITH GRANT OPTION') AS delegate_access,
                p.prorettype='pg_catalog.trigger'::regtype AS trigger,p.proowner=(SELECT oid FROM pg_roles WHERE rolname=$1) AS owned
                FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE n.nspname=ANY($2::text[])
                AND NOT EXISTS(SELECT 1 FROM pg_depend d WHERE d.classid='pg_proc'::regclass AND d.objid=p.oid AND d.deptype='e')''', role, list(SCHEMAS))
            for row in functions:
                if row['owned']:
                    issue('runtime_function_ownership', row['signature'])
                if row['delegate_access']:
                    issue('function_grant_option', row['signature'])
                reference = expected['functions'].get(row['signature'])
                required = bool(reference and not reference['securityDefiner'] and
                                (row['schema'] == 'public' or not reference['trigger']))
                if required != row['permitted']:
                    issue('missing_function_execute' if required else 'excess_function_execute', row['signature'])
            # Require the exact per-verb backend policies; inherited/public
            # applicable policies are held, including restrictive policies that
            # could silently prevent writes despite apparent table privileges.
            policies = await conn.fetch('''SELECT n.nspname||'.'||c.relname AS table_name,p.polname,
                p.polcmd::text AS polcmd,p.polpermissive,p.polroles,
                pg_get_expr(p.polqual,p.polrelid) AS using_expr,
                pg_get_expr(p.polwithcheck,p.polrelid) AS check_expr
                FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=ANY($2::text[]) AND
                (0=ANY(p.polroles) OR $1=ANY(p.polroles) OR EXISTS(
                    SELECT 1 FROM unnest(p.polroles) r WHERE r<>0 AND pg_has_role($1,r,'USAGE')))''', flags['oid'], list(SCHEMAS))
            found = set()
            commands = {'SELECT': 'r', 'INSERT': 'a', 'UPDATE': 'w', 'DELETE': 'd'}
            for row in policies:
                key = (row['table_name'], row['polname'])
                verb = row['polname'].removeprefix('runtime_candidate_').upper()
                valid = row['table_name'].startswith('public.') and verb in PUBLIC.get(row['table_name'][7:], ())
                valid = valid and row['polname'] == 'runtime_candidate_' + verb.lower()
                valid = valid and list(row['polroles']) == [flags['oid']] and row['polpermissive'] and row['polcmd'] == commands.get(verb)
                valid = valid and row['using_expr'] == (None if verb == 'INSERT' else 'true')
                valid = valid and row['check_expr'] == ('true' if verb in ('INSERT', 'UPDATE') else None)
                if not valid:
                    issue('unreviewed_applicable_policy', row['table_name'] + '.' + row['polname'])
                else:
                    found.add(key)
            for name, privileges in PUBLIC.items():
                for verb in privileges:
                    key = ('public.' + name, 'runtime_candidate_' + verb.lower())
                    if key not in found:
                        issue('missing_backend_policy', '.'.join(key))
        actual_contract = await catalog_contracts(conn)
        for group in ('functions', 'relations'):
            for name in set(expected[group]) | set(actual_contract[group]):
                if expected[group].get(name) != actual_contract[group].get(name):
                    issue('catalog_' + group + '_drift', name)
        readonly = await conn.fetchval('SHOW transaction_read_only') == 'on'
    return {'format': 'jaymax-runtime-permission-assessment-v1', 'status': 'held' if issues else 'passed_local_candidate',
            'readOnly': readonly, 'catalogReader': reader, 'assessedRole': role,
            'issues': sorted(issues, key=lambda value: json.dumps(value, sort_keys=True)),
            'operationalReleaseApproved': False, 'hostedRoleLoginVerified': False,
            'candidatePublication': profile['publication'], 'contractSha256': digest(expected)}
