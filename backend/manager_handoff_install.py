"""Guarded fictional receiving installer. NO hosted execution entry point.

Three explicit ledger entries in one transaction: schema, permissions, settings.
No role creation, credentials, memberships, flags, app configuration or retry.
"""
import hashlib
import json
from pathlib import Path
import re

import manager_handoff as handoff
import manager_handoff_recovery as recovery
import runtime_permissions
from hosted_test_trial import migration_body
from native_backup import quoted

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / 'migrations/20261025_manager_handoff_notes.sql'
REFERENCE = ROOT / 'supabase/manager_handoff.manifest.json'
FORMAT = 'jaymax-local-handoff-install-plan-v1'
VERBS = ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER', 'MAINTAIN')


class Held(recovery.Held):
    pass


class Unknown(Held):
    """Commit acknowledgement uncertain; reconcile read-only, never blindly retry."""


def sha(value):
    return recovery.digest(recovery.canonical(value))


def reference():
    m = json.loads(REFERENCE.read_text(encoding='utf-8'))
    if (hashlib.sha256(MIGRATION.read_bytes()).hexdigest() != m['migrationSha256']
            or hashlib.sha256((ROOT / 'supabase/manager_handoff.schema.sql').read_bytes()).hexdigest() != m['snapshotSha256']
            or m['liveActivationApproved'] or m['applyAutomatically']):
        raise Held('Receiving source reference drift')
    return m


def sources():
    names = ('backend/manager_handoff_install.py', 'backend/manager_handoff_recovery.py',
             'backend/manager_handoff.py', 'backend/manager_actor.py', 'backend/runtime_permissions.py',
             'backend/hosted_test_trial.py', 'backend/hosted_backup.py', 'backend/native_backup.py',
             'backend/hosted_native_install.py', 'backend/hosted_install_preservation.py',
             'backend/schema_reconciliation.py',
             'migrations/20261025_manager_handoff_notes.sql', 'supabase/manager_handoff.schema.sql',
             'supabase/manager_handoff.manifest.json')
    return {name: recovery.digest((ROOT / name).read_bytes()) for name in names}


def name(value):
    if not isinstance(value, str) or not re.fullmatch('[a-z][a-z0-9_]{0,62}', value):
        raise Held('Explicit reviewed identifier required')
    return quoted(value)


def payloads(runtime):
    role = name(runtime); m = reference()
    permission = [f'GRANT USAGE ON SCHEMA operations TO {role};']
    for table, verbs in sorted(m['proposedRuntimePrivileges'].items()):
        schema, rel = table.split('.')
        target = quoted(schema) + '.' + quoted(rel)
        permission.append(f'GRANT {",".join(verbs)} ON {target} TO {role};')
        permission.append(f'CREATE POLICY handoff_backend_v1 ON {target} AS PERMISSIVE FOR ALL TO {role} USING(true) WITH CHECK(true);')
    return [('manager_handoff_schema', migration_body(MIGRATION.read_bytes())),
            ('manager_handoff_permissions', '\n'.join(permission)),
            ('manager_handoff_settings', "INSERT INTO operations.store_settings(store_id,timezone_name,revision) VALUES('berts','America/New_York',1);")]


async def identity(conn, role):
    flags = await conn.fetchrow('''SELECT oid,rolname,rolcanlogin,rolinherit,rolsuper,rolbypassrls,
        rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=$1''', role)
    if not flags or not flags['rolcanlogin'] or any(flags[k] for k in
            ('rolinherit', 'rolsuper', 'rolbypassrls', 'rolcreatedb', 'rolcreaterole', 'rolreplication')):
        raise Held('Restricted LOGIN identity required')
    if await conn.fetchval('SELECT EXISTS(SELECT 1 FROM pg_auth_members WHERE member=$1)', flags['oid']):
        raise Held('Unreviewed role membership')
    if await conn.fetchval("SELECT has_database_privilege($1,current_database(),'CREATE')", role):
        raise Held('Runtime database CREATE refused')
    return dict(flags)


async def ledger(conn):
    rows = await conn.fetch('''SELECT version::text AS version,to_jsonb(t)::text AS body
        FROM supabase_migrations.schema_migrations t ORDER BY version::text''')
    if len({r['version'] for r in rows}) != len(rows) or any(not r['version'] for r in rows):
        raise Held('Migration ledger shape held')
    return {r['version']: recovery.digest(r['body'].encode()) for r in rows}


async def baseline(conn, runtime, accounts):
    await conn.execute('SET LOCAL search_path=pg_catalog')
    if int(await conn.fetchval('SHOW server_version_num')) // 10000 != 17:
        raise Held('Reviewed PostgreSQL major required')
    if await conn.fetchval("SELECT to_regnamespace('operations') IS NOT NULL"):
        raise Held('Receiving namespace collision; no repair or reuse')
    if await conn.fetchval("SELECT active FROM public.stores WHERE id='berts'") is not True:
        raise Held('Existing active Berts store required')
    from hosted_native_install import ledger_shape
    from hosted_install_preservation import ledger_contract
    await ledger_shape(conn); await ledger_contract(conn)
    return {'database': await conn.fetchval('SELECT current_database()'),
            'installer': await conn.fetchval('SELECT current_user'),
            'runtime': await identity(conn, runtime), 'accounts': await identity(conn, accounts),
            'ledger': await ledger(conn), 'facts': await recovery.facts(conn, recovery.LEGACY_SCHEMAS)}


async def prepare(url, runtime, accounts, versions):
    settings = recovery.target(url); name(runtime); name(accounts)
    if len({settings['user'], runtime, accounts}) != 3:
        raise Held('Distinct installer, operational and accounts roles required')
    if (not isinstance(versions, (list, tuple)) or len(versions) != 3 or len(set(versions)) != 3
            or any(not isinstance(v, str) or not re.fullmatch('[0-9]{14}', v) for v in versions)):
        raise Held('Three explicit distinct delivery versions required')
    conn = await recovery.connect(url)
    try:
        async with conn.transaction(isolation='repeatable_read', readonly=True):
            state = await baseline(conn, runtime, accounts)
            if set(versions) & set(state['ledger']):
                raise Held('Delivery version collision')
    finally:
        await conn.close()
    values = payloads(runtime)
    return {'format': FORMAT, 'localOnly': True, 'applyAutomatically': False,
            'target': {k: settings[k] for k in ('host', 'port', 'user', 'database')},
            'runtimeRole': runtime, 'accountsRole': accounts, 'sourceHashes': sources(),
            'baseline': state, 'entries': [{'version': v, 'name': n, 'body': b,
                'bodySha256': recovery.digest(b.encode())} for v, (n, b) in zip(versions, values)]}


def checked(plan, expected_hash, url):
    settings = recovery.target(url)
    if (plan.get('format') != FORMAT or plan.get('localOnly') is not True or plan.get('applyAutomatically') is not False
            or sha(plan) != expected_hash or plan.get('sourceHashes') != sources()
            or plan.get('target') != {k: settings[k] for k in ('host', 'port', 'user', 'database')}):
        raise Held('Independent exact local plan binding held')
    rendered = payloads(plan['runtimeRole'])
    entries = plan['entries']
    if (len(entries) != 3 or len({e['version'] for e in entries}) != 3
            or any(not re.fullmatch('[0-9]{14}', e['version']) or e['name'] != n or e['body'] != b
                   or e['bodySha256'] != recovery.digest(b.encode()) for e, (n, b) in zip(entries, rendered))):
        raise Held('Rendered payload drift')


async def _commit(tx):
    await tx.commit()


async def installed_state(conn, plan):
    m = reference()
    actual = await runtime_permissions.catalog_contracts(conn, schemas=('operations',))
    if actual != m['catalog'] or not await handoff.installed(conn):
        raise Held('Receiving catalog or exact guard wiring differs')
    if [dict(r) for r in await conn.fetch('SELECT * FROM operations.store_settings ORDER BY store_id')] != [
            {'store_id': 'berts', 'timezone_name': 'America/New_York', 'revision': 1}]:
        raise Held('Unexpected store configuration')
    before = plan['baseline']['ledger']; after = await ledger(conn)
    expected_versions = {e['version'] for e in plan['entries']}
    if set(after) != set(before) | expected_versions or any(after.get(k) != v for k, v in before.items()):
        raise Held('Historical ledger drift')
    for e in plan['entries']:
        row = await conn.fetchrow('SELECT name,statements FROM supabase_migrations.schema_migrations WHERE version=$1', e['version'])
        if row['name'] != e['name'] or list(row['statements']) != [e['body']]:
            raise Held('Exact ledger body mismatch')
    recovery.preserved(plan['baseline']['facts'], await recovery.facts(conn, recovery.LEGACY_SCHEMAS))


async def apply(url, plan, expected_hash):
    checked(plan, expected_hash, url)
    conn = await recovery.connect(url); tx = conn.transaction(); committing = False
    try:
        await tx.start()
        await conn.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'; SET LOCAL search_path=pg_catalog")
        await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('manager-handoff-local-install',0))")
        tables = plan['baseline']['facts']['rows']
        for table in sorted(tables):
            # Sequences are fingerprinted independently, never treated as row locks.
            if await conn.fetchval("SELECT relkind='S' FROM pg_class WHERE oid=to_regclass($1)", table):
                continue
            await conn.execute('LOCK TABLE ' + '.'.join(quoted(x) for x in table.split('.')) + ' IN SHARE MODE')
        if await baseline(conn, plan['runtimeRole'], plan['accountsRole']) != plan['baseline']:
            raise Held('Prepared baseline changed')
        for e in plan['entries']:
            await conn.execute(e['body'])
            await conn.execute('INSERT INTO supabase_migrations.schema_migrations(version,name,statements) VALUES($1,$2,$3)',
                               e['version'], e['name'], [e['body']])
        await installed_state(conn, plan)
        # Effective permission and policy verification shares the apply transaction.
        await permissions(conn, plan['runtimeRole'], plan['accountsRole'], actual=False)
        committing = True
        await _commit(tx)
        return {'status': 'installed_local_only', 'ledgerEntries': 3,
                'hostedExecutionApproved': False, 'featureActivated': False}
    except BaseException as error:
        if committing:
            raise Unknown('Local commit acknowledgement unknown; read-only reconciliation required') from None
        await tx.rollback()
        raise error
    finally:
        await conn.close()


async def reconcile(url, plan, expected_hash):
    checked(plan, expected_hash, url)
    conn = await recovery.connect(url)
    try:
        async with conn.transaction(isolation='repeatable_read', readonly=True):
            await conn.execute('SET LOCAL search_path=pg_catalog')
            if not await conn.fetchval("SELECT to_regnamespace('operations') IS NOT NULL"):
                return {'outcome': 'not_installed', 'retryAuthorized': False}
            await installed_state(conn, plan)
            await permissions(conn, plan['runtimeRole'], plan['accountsRole'], actual=False)
            return {'outcome': 'installed', 'retryAuthorized': False}
    finally:
        await conn.close()


async def permissions(conn, runtime, accounts, *, actual):
    """Feature-local metadata check, not a replacement for native/account profiles."""
    runtime_info = await identity(conn, runtime); account_info = await identity(conn, accounts)
    if actual and (await conn.fetchval('SELECT current_user') != runtime
                   or await conn.fetchval('SELECT session_user') != runtime):
        raise Held('Actual operational LOGIN required; SET ROLE is not proof')
    if not await handoff.installed(conn):
        raise Held('Required receiving guards absent or disabled')
    m = reference(); oid = runtime_info['oid']
    if await runtime_permissions.catalog_contracts(conn, schemas=('operations',)) != m['catalog']:
        raise Held('Feature-local catalog drift')
    if not await conn.fetchval("SELECT has_schema_privilege($1,'operations','USAGE')", runtime):
        raise Held('Runtime schema usage missing')
    for role in (runtime, accounts):
        for r in await conn.fetch("""SELECT nspowner=(SELECT oid FROM pg_roles WHERE rolname=$1) AS owned,
            has_schema_privilege($1,oid,'CREATE') AS create_access,
            has_schema_privilege($1,oid,'USAGE WITH GRANT OPTION') AS delegate,
            has_schema_privilege($1,oid,'USAGE') AS use FROM pg_namespace WHERE nspname='operations'""", role):
            if r['owned'] or r['create_access'] or r['delegate'] or (role == accounts and r['use']):
                raise Held('Unreviewed schema authority')
    for table, allowed in m['proposedRuntimePrivileges'].items():
        for role, verbs in ((runtime, allowed), (accounts, ())):
            if await conn.fetchval('SELECT relowner=(SELECT oid FROM pg_roles WHERE rolname=$1) FROM pg_class WHERE oid=to_regclass($2)', role, table):
                raise Held('Runtime/account table ownership refused')
            for verb in VERBS:
                if await conn.fetchval('SELECT has_table_privilege($1,$2,$3)', role, table, verb) != (verb in verbs):
                    raise Held('Effective object privilege differs')
                if await conn.fetchval('SELECT has_table_privilege($1,$2,$3)', role, table, verb + ' WITH GRANT OPTION'):
                    raise Held('Runtime delegation refused')
            for verb in ('SELECT', 'INSERT', 'UPDATE', 'REFERENCES'):
                if verb not in verbs and await conn.fetchval('SELECT has_any_column_privilege($1,$2,$3)', role, table, verb):
                    raise Held('Excess column privilege')
                if await conn.fetchval('SELECT has_any_column_privilege($1,$2,$3)', role, table, verb + ' WITH GRANT OPTION'):
                    raise Held('Column delegation refused')
        policies = await conn.fetch('''SELECT polname,polcmd::text AS cmd,polpermissive,polroles,
            pg_get_expr(polqual,polrelid) AS use,pg_get_expr(polwithcheck,polrelid) AS check_expr
            FROM pg_policy WHERE polrelid=to_regclass($1)''', table)
        if len(policies) != 1 or dict(policies[0]) != {'polname': 'handoff_backend_v1', 'cmd': '*',
                'polpermissive': True, 'polroles': [oid], 'use': 'true', 'check_expr': 'true'}:
            raise Held('Exact role-addressed policy required')
    for r in await conn.fetch("""SELECT p.oid,p.proowner,p.prosecdef FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='operations'"""):
        if r['proowner'] in (oid, account_info['oid']) or r['prosecdef'] or await conn.fetchval("SELECT has_function_privilege($1::name,$2::oid,'EXECUTE')", runtime, r['oid']):
            raise Held('Unreviewed runtime function authority')
    # Any explicit receiving ACL outside owner/runtime is unreviewed, not just known browser roles.
    bad = await conn.fetchval("""SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace,
        LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a
        WHERE n.nspname='operations' AND a.grantee<>c.relowner AND a.grantee<>$1) OR
        EXISTS(SELECT 1 FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace,
        LATERAL aclexplode(a.attacl) x WHERE n.nspname='operations' AND x.grantee<>c.relowner AND x.grantee<>$1) OR
        EXISTS(SELECT 1 FROM pg_namespace n,LATERAL aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) a
        WHERE n.nspname='operations' AND a.grantee<>n.nspowner AND a.grantee<>$1) OR
        EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace,
        LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE n.nspname='operations' AND a.grantee<>p.proowner)""", oid)
    if bad:
        raise Held('Unexpected receiving ACL recipient')
    if actual:
        if await conn.fetchval("SELECT active FROM public.stores WHERE id='berts'") is not True:
            raise Held('Restricted store read failed')
        for verb in ('SELECT', 'INSERT', 'UPDATE', 'REFERENCES'):
            if await conn.fetchval("SELECT has_any_column_privilege(current_user,'public.app_users',$1)", verb):
                raise Held('Operational connection can access account columns')
    return {'status': 'passed_feature_local_only', 'actualRuntimeLogin': actual,
            'baselineNativeAndAccountQualificationIncluded': False, 'hostedActivationApproved': False}


async def qualify(runtime_url, accounts_url):
    r = recovery.target(runtime_url); a = recovery.target(accounts_url)
    if any(r[k] != a[k] for k in ('host', 'port', 'database')) or r['user'] == a['user']:
        raise Held('Explicit distinct accounts connection on same local target required')
    conn = await recovery.connect(runtime_url)
    try:
        async with conn.transaction(readonly=True):
            await conn.execute('SET LOCAL search_path=pg_catalog')
            result = await permissions(conn, r['user'], a['user'], actual=True)
    finally:
        await conn.close()
    conn = await recovery.connect(accounts_url)
    try:
        async with conn.transaction(readonly=True):
            if (await conn.fetchval('SELECT current_user') != a['user']
                    or await conn.fetchval('SELECT session_user') != a['user']):
                raise Held('Actual accounts LOGIN required')
            await identity(conn, a['user'])
            await conn.fetch('SELECT id,role,locations FROM public.app_users WHERE false')
            if await conn.fetchval("SELECT has_schema_privilege(current_user,'operations','USAGE')"):
                raise Held('Accounts namespace access refused')
    finally:
        await conn.close()
    return result | {'actualAccountsLogin': True, 'fallbackUsed': False}
