"""Encrypted application-scope export and disposable-only PostgreSQL restore.

No operational restore, managed-service recovery, scheduling or cloud sync.
Connection errors and dump stderr must never be printed or attached to receipts.
"""
import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import asyncpg
from cryptography.fernet import Fernet
from db_tls import connection_tls, DEFAULT_CA
import native_backup as native

SCHEMAS = ('public', 'purchasing', 'actual_inventory', 'prep_inventory', 'integrations', 'supabase_migrations')
MANAGED = {'auth', 'cron', 'extensions', 'graphql', 'graphql_public', 'net', 'realtime', 'storage', 'vault'}
FORMAT = 'jaymax-encrypted-application-backup-v1'
ROW_ALGORITHM = 'sha256-sorted-sha256-canonical-jsonb-utf8-v1'
MAX_ARCHIVE = 64 * 1024 * 1024  # Bounded build tool; larger backups need streaming encryption.
MAX_ENVELOPE = 3 * MAX_ARCHIVE
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


class BackupError(RuntimeError):
    """Safe category only: do not include source rows, URLs, SQL or driver text."""


def digest(value):
    return hashlib.sha256(value).hexdigest()


def hosted_connection(url, project):
    if not re.fullmatch(r'[a-z0-9]{20}', project):
        raise BackupError('Expected project reference required')
    u = urlsplit(url)
    if (u.scheme not in ('postgres', 'postgresql') or not u.username or not u.password
            or u.hostname is None or not u.hostname.endswith('.pooler.supabase.com')
            or u.port != 5432 or u.path != '/postgres' or u.query or u.fragment
            or unquote(u.username) != 'postgres.' + project):
        raise BackupError('Reviewed owner session-pooler connection required')
    return {'host': u.hostname, 'port': u.port, 'user': unquote(u.username),
            'password': unquote(u.password), 'database': 'postgres'}


def private_directory(path, area):
    """Fresh child directory with current-user and SYSTEM ACLs, outside synced paths."""
    if os.name != 'nt' or area not in ('backups', 'credentials'):
        raise BackupError('Windows private-directory verification required')
    root = Path(os.environ['LOCALAPPDATA']) / 'JayMaxBuild' / area
    path = Path(path)
    if (not path.is_absolute() or path.parent != root or path.exists()
            or not re.fullmatch(r'backup-[a-f0-9]{32}', path.name)):
        raise BackupError('Fresh private backup directory required')
    for parent in (root, root.parent):
        if parent.is_symlink() or parent.is_junction():
            raise BackupError('Redirected private directory refused')
    shell = shutil.which('pwsh')
    if not shell:
        raise BackupError('PowerShell 7 required')
    root.mkdir(parents=True, exist_ok=True)
    path.mkdir()
    script = '''$ErrorActionPreference='Stop'; $p=$env:JAYMAX_BACKUP_PRIVATE;
      $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User;
      $acl=[Security.AccessControl.DirectorySecurity]::new();
      $acl.SetOwner($sid); $acl.SetAccessRuleProtection($true,$false);
      foreach($id in @($sid.Value,'S-1-5-18')) {
        $identity=[Security.Principal.SecurityIdentifier]::new($id);
        $rule=[Security.AccessControl.FileSystemAccessRule]::new($identity,'FullControl','ContainerInherit,ObjectInherit','None','Allow');
        $acl.AddAccessRule($rule) };
      Set-Acl -LiteralPath $p -AclObject $acl;
      $actual=Get-Acl -LiteralPath $p;
      $ids=@($actual.Access | ForEach-Object {$_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value} | Sort-Object -Unique);
      $expected=@($sid.Value,'S-1-5-18') | Sort-Object -Unique;
      if (-not $actual.AreAccessRulesProtected -or $actual.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $sid.Value -or
        ($ids -join ',') -ne ($expected -join ',')) {exit 2}; Write-Output 'verified' '''
    checked = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-Command', script],
        env={**os.environ, 'JAYMAX_BACKUP_PRIVATE': str(path)}, capture_output=True, timeout=20, creationflags=FLAGS)
    if checked.returncode or checked.stdout.strip() != b'verified':
        raise BackupError('Private directory ACL held')
    return path


def process_env(settings, remote):
    env = {key: value for key, value in os.environ.items() if not key.startswith('PG')}
    env.update(PGHOST=settings['host'], PGPORT=str(settings['port']), PGUSER=settings['user'],
        PGPASSWORD=settings['password'], PGDATABASE=settings['database'], PGCONNECT_TIMEOUT='20',
        PGCLIENTENCODING='UTF8', PGSSLMODE='verify-full' if remote else 'disable')
    if remote:
        env.update(PGSSLROOTCERT=os.environ.get('DATABASE_SSL_ROOT_CERT', str(DEFAULT_CA)),
                   PGOPTIONS='-c default_transaction_read_only=on')
    return env


async def tool(executable, args, settings=None, remote=False):
    result = await asyncio.to_thread(subprocess.run, [str(executable), *args],
        env=process_env(settings, remote) if settings else os.environ.copy(),
        capture_output=True, timeout=240, creationflags=FLAGS)
    if result.returncode:
        error = BackupError('PostgreSQL tool failed; private diagnostic text withheld')
        error.toolErrorCategories = [label for phrase, label in (
            (b'already exists', 'existing_object'), (b'does not exist', 'missing_dependency'),
            (b'permission denied', 'permission'), (b'must be owner', 'ownership'),
            (b'unrecognized configuration parameter', 'configuration'), (b'version mismatch', 'version'))
            if phrase in result.stderr]
        raise error
    return result.stdout


async def fingerprint(conn, row_hashes=True):
    # Deparser output is session-sensitive (pg_dump uses quote_all_identifiers).
    # Normalize within the caller's snapshot, without changing role/app defaults.
    await conn.execute("SET LOCAL quote_all_identifiers=off; SET LOCAL TIME ZONE 'UTC'; SET LOCAL search_path=pg_catalog; SET LOCAL DateStyle='ISO,YMD'; SET LOCAL IntervalStyle=postgres; SET LOCAL bytea_output=hex; SET LOCAL extra_float_digits=3; SET LOCAL standard_conforming_strings=on; SET LOCAL row_security=off")
    catalog = {}
    for key, sql in native.CATALOG.items():
        if key == 'extensions':
            continue  # Dependency bootstrap is verified separately, outside application scope.
        sql = sql.replace(native.NAMESPACES, 'n.nspname=ANY($1::text[])')
        if key == 'functions':
            sql = sql.replace('p.proacl::text AS acl', "ARRAY(SELECT a::text FROM unnest(coalesce(p.proacl,acldefault('f',p.proowner))) a ORDER BY a::text) AS acl")
        sql = sql.replace('ORDER BY a::text', 'ORDER BY a::text COLLATE "C"')
        rows = await conn.fetch('SELECT to_jsonb(r)::text AS value FROM (' + sql + ') r ORDER BY to_jsonb(r)::text', list(SCHEMAS))
        # Database collations differ between hosted Linux and local Windows.
        # Compare identical records in a portable client order, not locale order.
        catalog[key] = {'objects': len(rows), 'sha256': digest('\n'.join(sorted(r['value'] for r in rows)).encode())}
    acl = await conn.fetch('''SELECT n.nspname,pg_get_userbyid(d.defaclrole) AS role,d.defaclobjtype::text AS kind,
        ARRAY(SELECT a::text FROM unnest(d.defaclacl) a ORDER BY a::text COLLATE "C") AS acl
        FROM pg_default_acl d JOIN pg_namespace n ON n.oid=d.defaclnamespace WHERE n.nspname=ANY($1::text[])
        ORDER BY 1,2,3''', list(SCHEMAS))
    catalog['default_acl'] = {'objects': len(acl), 'sha256': digest('\n'.join(sorted(json.dumps(dict(r), sort_keys=True) for r in acl)).encode())}
    tables = {}
    relations = await conn.fetch('''SELECT n.nspname,c.relname,c.relkind::text AS kind FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[])
        AND c.relkind IN ('r','p','m','S') ORDER BY 1,2''', list(SCHEMAS))
    for relation in relations:
        name = relation['nspname'] + '.' + relation['relname']
        quoted = native.quoted(relation['nspname']) + '.' + native.quoted(relation['relname'])
        sql = (f"SELECT jsonb_build_object('last_value',last_value,'is_called',is_called)::text AS value FROM {quoted}"
               if relation['kind'] == 'S' else
               (f"SELECT value FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS value FROM {quoted} t) hashed ORDER BY value COLLATE \"C\"" if row_hashes
                else f'SELECT to_jsonb(t)::text AS value FROM {quoted} t ORDER BY to_jsonb(t)::text'))
        count = 0
        sha = hashlib.sha256()
        try:
            async for row in conn.cursor(sql, prefetch=100):
                sha.update(row['value'].encode()); sha.update(b'\n'); count += 1
        except TimeoutError as exc:
            error = BackupError('Table fingerprint query timed out')
            error.failureObject = name
            raise error from exc
        tables[name] = {'rows': count, 'sha256': sha.hexdigest(), 'kind': relation['kind']}
    return {'tables': tables, 'catalog': catalog}


async def dependencies(conn):
    """Record referenced managed objects. Unsupported dependencies hold recovery."""
    rows = await conn.fetch('''WITH objects AS (
      SELECT 'pg_class'::regclass AS classid,c.oid AS objid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[])
      UNION SELECT 'pg_proc'::regclass,p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=ANY($1::text[])
      UNION SELECT 'pg_type'::regclass,t.oid FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname=ANY($1::text[])
      UNION SELECT 'pg_constraint'::regclass,k.oid FROM pg_constraint k JOIN pg_namespace n ON n.oid=k.connamespace WHERE n.nspname=ANY($1::text[])
      UNION SELECT 'pg_attrdef'::regclass,a.oid FROM pg_attrdef a JOIN pg_class c ON c.oid=a.adrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[])
      UNION SELECT 'pg_policy'::regclass,p.oid FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[])
      UNION SELECT 'pg_rewrite'::regclass,r.oid FROM pg_rewrite r JOIN pg_class c ON c.oid=r.ev_class JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[])
      UNION SELECT 'pg_trigger'::regclass,t.oid FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[]))
      SELECT DISTINCT i.type,i.schema,i.identity,e.extname AS extension,d.refclassid::regclass::text AS class,d.refobjid
      FROM pg_depend d JOIN objects o ON o.classid=d.classid AND o.objid=d.objid
      CROSS JOIN LATERAL pg_identify_object(d.refclassid,d.refobjid,d.refobjsubid) i
      LEFT JOIN pg_depend member ON member.classid=d.refclassid AND member.objid=d.refobjid AND member.deptype='e' AND member.refclassid='pg_extension'::regclass
      LEFT JOIN pg_extension e ON e.oid=member.refobjid
      WHERE i.schema IS NOT NULL AND NOT i.schema=ANY($1::text[]) AND i.schema NOT LIKE 'pg_%' ORDER BY 2,3''', list(SCHEMAS))
    facts = [dict(row) for row in rows]
    extensions = []
    functions = []
    for row in facts:
        if row['extension']:
            extension = dict(await conn.fetchrow('SELECT e.extname,e.extversion,n.nspname AS schema FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname=$1', row['extension']))
            if extension not in extensions:
                extensions.append(extension)
        elif row['schema'] == 'auth' and row['class'] == 'pg_proc':
            function = await conn.fetchrow('''SELECT p.proname,p.prosecdef,l.lanname,pg_get_function_identity_arguments(p.oid) AS args,pg_get_functiondef(p.oid) AS definition
              FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang WHERE p.oid=$1''', row['refobjid'])
            if function['proname'] not in ('uid','role','jwt') or function['prosecdef'] or function['lanname'] != 'sql' or function['args']:
                raise BackupError('Unsupported managed function dependency')
            functions.append(dict(function))
        else:
            raise BackupError('Unsupported out-of-scope dependency; no complete restore claim')
    return {'objects': facts, 'extensions': extensions, 'authFunctions': functions}


def open_backup(encrypted, key, expected_project):
    encrypted = Path(encrypted)
    if not encrypted.is_file() or encrypted.stat().st_size > MAX_ENVELOPE:
        raise BackupError('Missing or oversized encrypted backup')
    try:
        value = json.loads(Fernet(Path(key).read_bytes()).decrypt(encrypted.read_bytes()))
        manifest = value['manifest']
        archive = base64.b64decode(value['archive'], validate=True)
        if (manifest['format'] != FORMAT or manifest['projectRef'] != expected_project
            or manifest['schemas'] != list(SCHEMAS) or len(archive) > MAX_ARCHIVE
            or manifest.get('rowFingerprintAlgorithm') not in (None, ROW_ALGORITHM)
            or digest(archive) != manifest['archiveSha256'] or len(archive) != manifest['archiveBytes']):
            raise ValueError('Manifest validation failed')
    except Exception as exc:
        raise BackupError('Backup authentication or manifest validation failed') from exc
    return manifest, archive


def restore_list(toc):
    """Retain initdb's public schema and its initial privileges; keep its ACL entry."""
    lines = toc.decode('utf-8').splitlines(keepends=True)
    public = [i for i, line in enumerate(lines) if re.match(r'^\d+;\s+\d+\s+\d+\s+SCHEMA - public\s', line)]
    if len(public) != 1:
        raise BackupError('Expected public schema archive entry missing or ambiguous')
    lines[public[0]] = '; ' + lines[public[0]]
    return ''.join(lines).encode('utf-8')


async def export_backup(url, project, pg_dump, pg_restore, backup_directory, key_directory, migration_hashes):
    settings = hosted_connection(url, project)
    context = connection_tls(url)
    directory = private_directory(backup_directory, 'backups')
    private_key = private_directory(key_directory, 'credentials') / 'backup.key'
    key = Fernet.generate_key()
    with private_key.open('xb') as stream:
        stream.write(key)
    raw = directory / 'archive.partial'
    candidate = directory / 'backup.partial.enc'
    conn = None
    try:
        conn = await asyncpg.connect(url, ssl=context, timeout=20, command_timeout=60, statement_cache_size=0)
        await native.configure(conn)
        async with conn.transaction(isolation='repeatable_read', readonly=True):
            found = {r['nspname'] for r in await conn.fetch("SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname<>'information_schema'")}
            if set(SCHEMAS) - found or found - set(SCHEMAS) - MANAGED:
                raise BackupError('Missing or unclassified database schemas')
            snapshot = await conn.fetchval('SELECT pg_export_snapshot()')
            facts = await fingerprint(conn)
            dependency = await dependencies(conn)
            roles = [dict(r) for r in await conn.fetch('''SELECT rolname,rolinherit,rolconnlimit,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication,rolcanlogin,rolvaliduntil::text,rolconfig
                FROM pg_roles WHERE rolname NOT LIKE 'pg_%' ORDER BY rolname''')]
            memberships = [dict(r) for r in await conn.fetch('''SELECT pg_get_userbyid(roleid) AS role,pg_get_userbyid(member) AS member,admin_option,inherit_option,set_option FROM pg_auth_members ORDER BY 1,2''')]
            await tool(pg_dump, ['--format=custom', '--quote-all-identifiers', '--encoding=UTF8', '--lock-wait-timeout=5000',
                '--snapshot=' + snapshot, '--file=' + str(raw), '--no-password', *['--schema=' + schema for schema in SCHEMAS]], settings, True)
            if raw.stat().st_size > MAX_ARCHIVE:
                raise BackupError('Archive exceeds build encryption bound; streaming export required')
            # Sequence values are outside MVCC: compare after dump and hold on observed changes.
            for name, fact in facts['tables'].items():
                if fact['kind'] == 'S':
                    schema, table = name.split('.')
                    row = await conn.fetchval(f"SELECT jsonb_build_object('last_value',last_value,'is_called',is_called)::text FROM {native.quoted(schema)}.{native.quoted(table)}")
                    if digest((row + '\n').encode()) != fact['sha256']:
                        raise BackupError('Sequence changed during export')
            data = raw.read_bytes()
            manifest = {'format': FORMAT, 'projectRef': project, 'schemas': list(SCHEMAS),
                'rowFingerprintAlgorithm': ROW_ALGORITHM, 'databaseOwner': await conn.fetchval('SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()'),
                'schemaOwners': {r['nspname']: r['owner'] for r in await conn.fetch('SELECT nspname,pg_get_userbyid(nspowner) AS owner FROM pg_namespace WHERE nspname=ANY($1::text[])', list(SCHEMAS))},
                'createdAt': datetime.now(timezone.utc).isoformat(), 'serverVersionNum': await conn.fetchval('SHOW server_version_num'),
                'archiveBytes': len(data), 'archiveSha256': digest(data), 'dependencies': dependency,
                'rolesWithoutPasswords': roles, 'roleMemberships': memberships, 'migrationFileHashes': migration_hashes,
                'sequenceStateIsMvcc': False, 'sequencesObservedStable': True, 'managedRecoveryVerified': False, **facts}
        with candidate.open('xb') as stream:
            stream.write(Fernet(key).encrypt(json.dumps({'manifest': manifest, 'archive': base64.b64encode(data).decode()}).encode()))
        verified, archive = open_backup(candidate, private_key, project)
        if verified != manifest or archive != data:
            raise BackupError('Encrypted readback mismatch')
        await tool(pg_restore, ['--list', str(raw)])
        raw.unlink()
        final = directory / 'backup.jmax.enc'
        candidate.rename(final)
        return {'status': 'exported_not_restore_verified', 'encryptedBackup': str(final), 'privateKey': str(private_key),
            'encryptedSha256': digest(final.read_bytes()), 'archiveSha256': manifest['archiveSha256'],
            'tablesCaptured': len(facts['tables']), 'catalogGroupsCaptured': len(facts['catalog']), 'sourceReadOnly': True,
            'sequencesObservedStable': True, 'managedRecoveryVerified': False}
    finally:
        if conn:
            await conn.close()
        # Only fixed temporary names in our newly created private child directory.
        for partial in (raw, candidate):
            if partial.exists():
                partial.unlink()


async def verify_restore(dsn, encrypted, key, project, pg_restore, temporary_directory):
    settings = native.disposable_connection(dsn)
    if not re.fullmatch(r'native_purchase_test_backup_[a-f0-9]{32}', settings['database']):
        raise BackupError('Fresh UUID-named backup test database required')
    manifest, archive = open_backup(encrypted, key, project)  # Authenticate before connection or writes.
    directory = private_directory(temporary_directory, 'backups')
    raw = directory / 'restore.partial'
    listing = directory / 'restore.list.partial'
    conn = None
    try:
        with raw.open('xb') as stream:
            stream.write(archive)
        with listing.open('xb') as stream:
            stream.write(restore_list(await tool(pg_restore, ['--list', str(raw)])))
        conn = await asyncpg.connect(**settings, ssl=False)
        occupied = await conn.fetchval(f"SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE {native.NAMESPACES}) OR EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE {native.NAMESPACES}) OR EXISTS(SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE {native.NAMESPACES}) OR EXISTS(SELECT 1 FROM pg_default_acl d JOIN pg_namespace n ON n.oid=d.defaclnamespace WHERE {native.NAMESPACES}) OR EXISTS(SELECT 1 FROM pg_namespace n WHERE {native.NAMESPACES} AND n.nspname<>'public')")
        if occupied:
            raise BackupError('Nonempty restore target refused')
        if int(await conn.fetchval('SHOW server_version_num')) // 10000 != int(manifest['serverVersionNum']) // 10000:
            raise BackupError('PostgreSQL major version mismatch')
        if manifest.get('databaseOwner') and await conn.fetchval('SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()') != manifest['databaseOwner']:
            raise BackupError('Disposable database owner must match recovery metadata')
        # Required NOLOGIN role stubs are prepared separately on the dedicated
        # test cluster. This utility never changes global roles or passwords.
        for role in manifest['rolesWithoutPasswords']:
            if not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=$1)', role['rolname']):
                raise BackupError('Required recovery role missing')
        async with conn.transaction():
            owner = manifest.get('schemaOwners', {}).get('public')
            if owner:
                await conn.execute('ALTER SCHEMA public OWNER TO ' + native.quoted(owner))
            for extension in manifest['dependencies']['extensions']:
                if extension['extname'] not in ('uuid-ossp', 'pgcrypto', 'pg_trgm', 'citext', 'btree_gist', 'btree_gin') or extension['schema'] != 'extensions':
                    raise BackupError('Unreviewed recovery extension')
                if not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM pg_available_extension_versions WHERE name=$1 AND version=$2)', extension['extname'], extension['extversion']):
                    raise BackupError('Required extension version unavailable')
                await conn.execute('CREATE SCHEMA IF NOT EXISTS extensions')
                await conn.execute('CREATE EXTENSION ' + native.quoted(extension['extname']) + ' WITH SCHEMA extensions VERSION ' + "'" + extension['extversion'].replace("'", "''") + "'")
            for function in manifest['dependencies']['authFunctions']:
                # Exact definitions came from the authenticated encrypted archive;
                # these SQL/non-definer helpers only support local policy creation.
                if function['proname'] not in ('uid', 'role', 'jwt') or function['prosecdef'] or function['lanname'] != 'sql' or function['args']:
                    raise BackupError('Unreviewed auth dependency')
                await conn.execute('CREATE SCHEMA IF NOT EXISTS auth')
                await conn.execute(function['definition'])
        await conn.close(); conn = None
        # Only after UUID/loopback/empty-object gates. The default public schema
        # remains; its archive ACL entry and all application objects are restored.
        await tool(pg_restore, ['--single-transaction', '--exit-on-error', '--clean', '--if-exists', '--use-list=' + str(listing), '--no-password', '--dbname=' + settings['database'], str(raw)], settings)
        conn = await asyncpg.connect(**settings, ssl=False)
        await native.configure(conn)
        async with conn.transaction(isolation='repeatable_read', readonly=True):
            algorithm = manifest.get('rowFingerprintAlgorithm')
            if algorithm not in (None, ROW_ALGORITHM):
                raise BackupError('Unsupported row fingerprint algorithm')
            actual = await fingerprint(conn, row_hashes=algorithm == ROW_ALGORITHM)
        expected = {key: manifest[key] for key in ('tables', 'catalog')}
        differences = {group: [name for name in sorted(set(actual[group]) | set(expected[group])) if actual[group].get(name) != expected[group].get(name)] for group in expected}
        if any(differences.values()):
            # Object identities only; no recovered rows/definitions in public evidence.
            error = BackupError('Restored application fingerprints differ')
            error.differences = differences
            raise error
        return {'status': 'verified_application_restore', 'tablesMatched': len(actual['tables']),
            'catalogGroupsMatched': len(actual['catalog']), 'archiveSha256': manifest['archiveSha256'],
            'rowsMatched': sum(t['rows'] for t in actual['tables'].values() if t['kind'] != 'S'),
            'majorVersionMatched': True, 'patchVersionMatched': await conn.fetchval('SHOW server_version_num') == manifest['serverVersionNum'],
            'managedRecoveryVerified': False, 'operationalReleaseApproved': False}
    finally:
        if conn:
            await conn.close()
        for temporary in (raw, listing):
            if temporary.exists():
                temporary.unlink()
