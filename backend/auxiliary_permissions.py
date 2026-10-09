"""Read-only assessment of a server-only account/notification connection.

No installer: grants and role-addressed policies require separate review.
Application authorization still controls users, locations and staff PINs.
"""
import transition_permissions as transition_checks

TABLES = ('app_users', 'push_subscriptions')
PRIVATE = ('purchasing', 'actual_inventory', 'prep_inventory', 'integrations')
VERBS = ('SELECT', 'INSERT', 'UPDATE', 'DELETE')


async def inspect(conn, *, transition=None):
    if conn.is_in_transaction():
        raise ValueError('Dedicated connection outside a transaction required')
    issues = []
    async with conn.transaction(isolation='repeatable_read', readonly=True):
        await conn.execute("SET LOCAL search_path=pg_catalog")
        await conn.execute("SET LOCAL statement_timeout='20s'")
        identity = await conn.fetchrow('''SELECT current_user AS current_role,session_user AS login_role,
            oid,rolinherit,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication
            FROM pg_roles WHERE rolname=current_user''')
        if identity['current_role'] != identity['login_role'] or any(identity[k] for k in
                ('rolsuper', 'rolbypassrls', 'rolcreatedb', 'rolcreaterole', 'rolreplication', 'rolinherit')):
            issues.append('Privileged or selected role')
        cohort = (await transition_checks.live_cohort(conn, transition, 'accounts', identity['current_role'])
                  if transition is not None else (identity['oid'],))
        if await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM pg_auth_members
            WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user))'''):
            issues.append('Role membership')
        if await conn.fetchval("SELECT has_database_privilege(current_user,current_database(),'CREATE')"):
            issues.append('Database CREATE')
        schemas = await conn.fetch('''SELECT nspname,has_schema_privilege(current_user,oid,'USAGE') AS use,
            has_schema_privilege(current_user,oid,'CREATE') AS create,
            has_schema_privilege(current_user,oid,'USAGE WITH GRANT OPTION') AS delegate,
            nspowner=(SELECT oid FROM pg_roles WHERE rolname=current_user) AS owner
            FROM pg_namespace WHERE nspname=ANY($1::text[])''', ['public', *PRIVATE])
        for row in schemas:
            if row['create'] or row['owner'] or row['delegate'] or (row['nspname'] in PRIVATE and row['use']):
                issues.append('Schema access: ' + row['nspname'])
        if not any(r['nspname'] == 'public' and r['use'] for r in schemas):
            issues.append('Public schema USAGE missing')
        grants = await conn.fetch('''SELECT n.nspname,c.relname,c.relkind::text AS relkind,c.relrowsecurity,
            c.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user) AS owner,
            verb,has_table_privilege(current_user,c.oid,verb) AS allowed,
            has_table_privilege(current_user,c.oid,verb||' WITH GRANT OPTION') AS delegate,
            CASE WHEN verb=ANY(ARRAY['SELECT','INSERT','UPDATE','REFERENCES'])
                THEN has_any_column_privilege(current_user,c.oid,verb) ELSE false END AS column_allowed,
            CASE WHEN verb=ANY(ARRAY['SELECT','INSERT','UPDATE','REFERENCES'])
                THEN has_any_column_privilege(current_user,c.oid,verb||' WITH GRANT OPTION') ELSE false END AS column_delegate
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            CROSS JOIN unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN']) AS verb
            WHERE n.nspname=ANY($1::text[]) AND c.relkind IN ('r','p','v','m','f')''', ['public', *PRIVATE])
        for row in grants:
            expected = row['nspname'] == 'public' and row['relname'] in TABLES and row['verb'] in VERBS
            if row['owner'] or row['delegate'] or row['column_delegate'] or row['allowed'] != expected or (row['column_allowed'] and not expected):
                issues.append('Table privilege: ' + row['nspname'] + '.' + row['relname'] + ':' + row['verb'])
        for table in TABLES:
            selected = [r for r in grants if r['nspname'] == 'public' and r['relname'] == table]
            if not selected or not all(r['relkind'] in ('r', 'p') and r['relrowsecurity'] for r in selected):
                issues.append('Required RLS table missing: ' + table)
        policies = await conn.fetch('''SELECT n.nspname||'.'||c.relname AS table_name,
            p.polname,p.polcmd::text AS polcmd,p.polpermissive,p.polroles,
            pg_get_expr(p.polqual,p.polrelid) AS using_expr,
            pg_get_expr(p.polwithcheck,p.polrelid) AS check_expr
            FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=ANY($1::text[]) AND (0=ANY(p.polroles)
                OR p.polroles && $2::oid[] OR EXISTS(SELECT 1 FROM unnest(p.polroles) r
                    WHERE r<>0 AND pg_has_role((SELECT oid FROM pg_roles WHERE rolname=current_user),r,'USAGE')))''',
            ['public', *PRIVATE], list(cohort))
        found = set()
        for row in policies:
            key = (row['table_name'], row['polname'])
            if not transition_checks.policy_valid(row, {name: VERBS for name in TABLES}, 'auxiliary_candidate_', cohort) or key in found:
                issues.append('Unreviewed applicable policy: ' + '.'.join(key))
            else:
                found.add(key)
        for table in TABLES:
            for verb in VERBS:
                if ('public.' + table, 'auxiliary_candidate_' + verb.lower()) not in found:
                    issues.append('Role policy missing: ' + table + ':' + verb)
        if await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE c.relkind='S' AND n.nspname=ANY($1::text[])
            AND (c.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)
                 OR has_sequence_privilege(current_user,c.oid,'USAGE,SELECT,UPDATE')))''', ['public', *PRIVATE]):
            issues.append('Sequence access')
        if await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname=ANY($1::text[]) AND
            (p.proowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)
             OR ((n.nspname<>'public' OR p.prosecdef) AND has_function_privilege(current_user,p.oid,'EXECUTE'))))''', ['public', *PRIVATE]):
            issues.append('Native/definer function access or ownership')
        readonly = await conn.fetchval('SHOW transaction_read_only') == 'on'
    return {'status': 'held' if issues else 'passed', 'issues': sorted(set(issues)),
            'policyMode': 'reviewed_overlap' if transition is not None else 'single_role',
            'transitionRecordSha256': transition.record_sha256 if transition is not None else None,
            'readOnly': readonly, 'operationalReleaseApproved': False}
