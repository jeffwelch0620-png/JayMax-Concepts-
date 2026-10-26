"""Opt-in seven-schema recovery engine. No app routes, configuration or startup hook.

Scope-sensitive code is independent of the frozen six-schema engine. Only its
scope-independent filesystem, process, quoting and row-fingerprint primitives
are reused. All remote routing is the existing direct IPv6/TLS maintenance path.
"""
import asyncio
import base64
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from uuid import uuid4

import asyncpg
from cryptography.fernet import Fernet
import hosted_backup as legacy
import maintenance_connection as maintenance
import native_backup as native
from application_backup_profiles import (Held, LEGACY6, RECEIVING7, MAX_ARCHIVE,
    MAX_ENVELOPE, ROW_ALGORITHM, canonical, checked_profile, digest, scope, sha256, strict_json)
import journal_backup_receipts as receipts
from readonly_snapshot import readonly_snapshot, preserve_cleanup_failure

NORMALIZE = "SET LOCAL quote_all_identifiers=off; SET LOCAL TIME ZONE 'UTC'; SET LOCAL search_path=pg_catalog; SET LOCAL DateStyle='ISO,YMD'; SET LOCAL IntervalStyle=postgres; SET LOCAL bytea_output=hex; SET LOCAL extra_float_digits=3; SET LOCAL standard_conforming_strings=on; SET LOCAL row_security=off; SET LOCAL statement_timeout='20s'"
SCHEMA_SQL = "SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname<>'information_schema'"
ROLE_SQL = "SELECT rolname,rolinherit,rolconnlimit,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication,rolcanlogin,rolvaliduntil::text,rolconfig FROM pg_roles WHERE rolname NOT LIKE 'pg_%' ORDER BY rolname"
MEMBER_SQL = 'SELECT pg_get_userbyid(roleid) AS role,pg_get_userbyid(member) AS member,admin_option,inherit_option,set_option FROM pg_auth_members ORDER BY 1,2'
EXTENSIONS = frozenset(('uuid-ossp','pgcrypto','pg_trgm','citext','btree_gist','btree_gin'))
SOURCE_NAMES = tuple(receipts.SOURCE_FILES)
CATALOG_GROUPS = frozenset(native.CATALOG)-{'extensions'}|{'default_acl','type_security'}


async def fingerprint(conn, selected):
    """Explicit scope, one caller-owned snapshot, portable frozen row-hash oracle."""
    selected = checked_profile(selected)
    if not conn.is_in_transaction():
        raise Held('snapshot_required')
    await conn.execute(NORMALIZE)
    catalog = {}
    for key, original in native.CATALOG.items():
        if key == 'extensions':
            continue
        sql = original.replace(native.NAMESPACES, 'n.nspname=ANY($1::text[])')
        if key == 'functions':
            sql = sql.replace('p.proacl::text AS acl', "ARRAY(SELECT a::text FROM unnest(coalesce(p.proacl,acldefault('f',p.proowner))) a ORDER BY a::text) AS acl")
        sql = sql.replace('ORDER BY a::text', 'ORDER BY a::text COLLATE "C"')
        rows = await conn.fetch('SELECT to_jsonb(r)::text AS value FROM (' + sql + ') r', list(selected.schemas))
        catalog[key] = dict(objects=len(rows), sha256=digest('\n'.join(sorted(r['value'] for r in rows)).encode()))
    rows = await conn.fetch('''SELECT n.nspname,pg_get_userbyid(d.defaclrole) AS role,d.defaclobjtype::text AS kind,
        ARRAY(SELECT a::text FROM unnest(d.defaclacl) a ORDER BY a::text COLLATE "C") AS acl
        FROM pg_default_acl d JOIN pg_namespace n ON n.oid=d.defaclnamespace WHERE n.nspname=ANY($1::text[])''', list(selected.schemas))
    # Keep the legacy JSON serialization exactly for oracle compatibility.
    import json
    catalog['default_acl'] = dict(objects=len(rows), sha256=digest('\n'.join(sorted(json.dumps(dict(r), sort_keys=True) for r in rows)).encode()))
    if selected == RECEIVING7:
        # The old oracle omits type owners/ACLs. New v2 evidence includes them;
        # the legacy comparison path remains exactly byte-compatible.
        rows=await conn.fetch('''SELECT to_jsonb(r)::text AS value FROM (
            SELECT n.nspname,t.typname,pg_get_userbyid(t.typowner) AS owner,t.typtype,
            ARRAY(SELECT a::text FROM unnest(coalesce(t.typacl,acldefault('T',t.typowner))) a ORDER BY a::text COLLATE "C") AS acl
            FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname=ANY($1::text[])) r''',list(selected.schemas))
        catalog['type_security']=dict(objects=len(rows),sha256=digest('\n'.join(sorted(r['value'] for r in rows)).encode()))
    tables = {}
    rows = await conn.fetch('''SELECT n.nspname,c.relname,c.relkind::text AS kind FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[])
        AND c.relkind IN ('r','p','m','S') ORDER BY 1,2''', list(selected.schemas))
    for r in rows:
        name = r['nspname'] + '.' + r['relname']
        if name in tables or '.' in r['nspname'] or '.' in r['relname']:
            raise Held('ambiguous_relation_identity')
        fact = await legacy.relation_fingerprint(conn, native.quoted(r['nspname']) + '.' + native.quoted(r['relname']), r['kind'])
        tables[name] = dict(fact, kind=r['kind'])
    return dict(tables=tables, catalog=catalog)


async def check_scope(conn, selected):
    scope((r['nspname'] for r in await conn.fetch(SCHEMA_SQL)), selected, legacy.MANAGED)
    # pg_dump does not contain foreign table data or material outside this contract.
    if await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=ANY($1::text[]) AND c.relkind='f') OR EXISTS(SELECT 1 FROM pg_foreign_server)''', list(selected.schemas)):
        raise Held('foreign_data_outside_profile')
    if await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace
        WHERE n.nspname=ANY($1::text[])) OR EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        JOIN pg_language l ON l.oid=p.prolang WHERE n.nspname=ANY($1::text[]) AND l.lanname NOT IN ('sql','plpgsql'))''',list(selected.schemas)):
        raise Held('unreviewed_in_scope_extension_or_language')
    if await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
        WHERE n.nspname=ANY($1::text[]) AND (t.typtype NOT IN ('b','c','d','e') OR (t.typtype='b' AND t.typelem=0)))
        OR EXISTS(SELECT 1 FROM pg_default_acl WHERE defaclnamespace=0)''',list(selected.schemas)):
        raise Held('unreviewed_type_or_global_default_acl')


async def dependencies(conn, selected):
    selected = checked_profile(selected)
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
      WHERE i.schema IS NOT NULL AND NOT i.schema=ANY($1::text[]) AND i.schema NOT LIKE 'pg_%' ORDER BY 2,3''', list(selected.schemas))
    extensions, functions = {}, {}
    for r in rows:
        if r['extension']:
            e = dict(await conn.fetchrow('SELECT e.extname,e.extversion,n.nspname AS schema FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname=$1', r['extension']))
            extensions[e['extname']] = e
        elif r['schema'] == 'auth' and r['class'] == 'pg_proc':
            f = dict(await conn.fetchrow('''SELECT p.proname,p.prosecdef,l.lanname,pg_get_function_identity_arguments(p.oid) AS args,pg_get_functiondef(p.oid) AS definition
                FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang WHERE p.oid=$1''', r['refobjid']))
            if f['proname'] not in ('uid','role','jwt') or f['prosecdef'] or f['lanname'] != 'sql' or f['args']:
                raise Held('unsupported_managed_function')
            functions[f['proname']] = f
        else:
            raise Held('unsupported_out_of_scope_dependency')
    return dict(extensions=[extensions[k] for k in sorted(extensions)], authFunctions=[functions[k] for k in sorted(functions)])


def dependency_policy(value):
    if not isinstance(value, dict) or set(value) != {'extensions', 'authFunctions'}:
        raise Held('dependency_policy_required')
    if any(not isinstance(value[k],list) for k in value):
        raise Held('dependency_lists_required')
    seen = set()
    for e in value['extensions']:
        if (not isinstance(e, dict) or set(e) != {'extname','extversion','schema'}
                or e['extname'] not in EXTENSIONS or e['schema'] != 'extensions'
                or not isinstance(e['extversion'], str) or not re.fullmatch(r'[0-9][0-9A-Za-z_.-]{0,63}', e['extversion'])
                or e['extname'] in seen):
            raise Held('unreviewed_extension')
        seen.add(e['extname'])
    seen = set()
    for f in value['authFunctions']:
        if (not isinstance(f, dict) or set(f) != {'proname','definitionSha256'}
                or f['proname'] not in ('uid','role','jwt') or f['proname'] in seen):
            raise Held('unreviewed_auth_function')
        sha256(f['definitionSha256']); seen.add(f['proname'])
    return value


def check_dependencies(actual, policy):
    policy = dependency_policy(policy)
    if (not isinstance(actual,dict) or set(actual) != {'extensions','authFunctions'}
            or not isinstance(actual['extensions'],list) or not isinstance(actual['authFunctions'],list)):
        raise Held('dependency_facts_invalid')
    for f in actual['authFunctions']:
        if (not isinstance(f,dict) or set(f) != {'proname','prosecdef','lanname','args','definition'}
                or f['proname'] not in ('uid','role','jwt') or f['prosecdef'] is not False
                or f['lanname'] != 'sql' or f['args'] != '' or not isinstance(f['definition'],str)):
            raise Held('unsupported_managed_function')
    simplified = {'extensions': actual['extensions'], 'authFunctions': [
        dict(proname=f['proname'], definitionSha256=digest(f['definition'].encode())) for f in actual['authFunctions']]}
    if canonical(simplified) != canonical(policy):
        raise Held('dependency_binding_differs')
    return actual


async def authority(conn, selected):
    """Private role metadata only; no password catalog is queried or reconstructed."""
    roles = [dict(r) for r in await conn.fetch(ROLE_SQL)]
    memberships = [dict(r) for r in await conn.fetch(MEMBER_SQL)]
    owners = {r['nspname']:r['owner'] for r in await conn.fetch('SELECT nspname,pg_get_userbyid(nspowner) AS owner FROM pg_namespace WHERE nspname=ANY($1::text[])', list(selected.schemas))}
    database_owner = await conn.fetchval('SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()')
    # pg_shdepend covers ACL grantor/grantee, owner, policy and default-ACL roles.
    # Filter to the selected namespaces, not all provider/global role metadata.
    required = await conn.fetch('''WITH objects AS (
      SELECT 'pg_namespace'::regclass classid,oid objid FROM pg_namespace WHERE nspname=ANY($1::text[])
      UNION SELECT 'pg_class'::regclass,c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[])
      UNION SELECT 'pg_proc'::regclass,p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=ANY($1::text[])
      UNION SELECT 'pg_type'::regclass,t.oid FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname=ANY($1::text[])
      UNION SELECT 'pg_policy'::regclass,p.oid FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[])
      UNION SELECT 'pg_default_acl'::regclass,d.oid FROM pg_default_acl d JOIN pg_namespace n ON n.oid=d.defaclnamespace WHERE n.nspname=ANY($1::text[]))
      SELECT DISTINCT pg_get_userbyid(d.refobjid) AS role FROM pg_shdepend d JOIN objects o USING(classid,objid)
      WHERE d.dbid=(SELECT oid FROM pg_database WHERE datname=current_database()) AND d.refclassid='pg_authid'::regclass''', list(selected.schemas))
    names = sorted({r['role'] for r in required} | set(owners.values()) | {database_owner})
    return dict(databaseOwner=database_owner, schemaOwners=owners, rolesWithoutPasswords=roles,
                roleMemberships=memberships, requiredRoles=names)


def validate_manifest(m, expected, policy):
    receipts.expected_binding(expected)
    fields = {'format','profile','profileSha256','schemas','binding','createdAt','serverVersionNum',
              'archiveBytes','archiveSha256','rowFingerprintAlgorithm','facts','authority','dependencies',
              'migrationFileHashes','sourceSystemIdentifier','sourceDatabaseOid','ownershipMode',
              'sequenceStateIsMvcc','sequencesObservedStable','managedRecoveryVerified'}
    if not isinstance(m, dict) or set(m) != fields:
        raise Held('manifest_shape_differs')
    fixed = dict(format=RECEIVING7.format, profile=RECEIVING7.name, profileSha256=RECEIVING7.sha256,
                 schemas=list(RECEIVING7.schemas), binding=expected, rowFingerprintAlgorithm=ROW_ALGORITHM,
                 ownershipMode='preserve', sequenceStateIsMvcc=False, sequencesObservedStable=True,
                 managedRecoveryVerified=False)
    for k,v in fixed.items():
        if type(m[k]) is not type(v) or m[k] != v:
            raise Held('manifest_binding_differs')
    check_dependencies(m['dependencies'], policy)
    if (not isinstance(m['serverVersionNum'], str) or not re.fullmatch(r'[0-9]{6}', m['serverVersionNum'])
            or type(m['archiveBytes']) is not int or not 0 < m['archiveBytes'] <= MAX_ARCHIVE
            or type(m['sourceDatabaseOid']) is not int or m['sourceDatabaseOid'] <= 0
            or not isinstance(m['sourceSystemIdentifier'], str) or not m['sourceSystemIdentifier'].isdigit()):
        raise Held('manifest_bounds_invalid')
    sha256(m['archiveSha256'])
    created = receipts.instant(m['createdAt'])
    if not receipts.instant(expected['window']['startsAt']) <= created < receipts.instant(expected['window']['expiresAt']):
        raise Held('capture_outside_window')
    if not isinstance(m['migrationFileHashes'], dict) or not m['migrationFileHashes']:
        raise Held('migration_inventory_required')
    for name,h in m['migrationFileHashes'].items():
        if not isinstance(name,str) or not re.fullmatch(r'(migrations|supabase/migrations)/[A-Za-z0-9_.-]+\.sql',name):
            raise Held('migration_inventory_invalid')
        sha256(h)
    facts = m['facts']
    if not isinstance(facts,dict) or set(facts) != {'tables','catalog'} or set(facts['catalog']) != CATALOG_GROUPS:
        raise Held('fact_coverage_differs')
    for name,t in facts['tables'].items():
        if (not isinstance(name,str) or name.split('.',1)[0] not in RECEIVING7.schemas
                or name.count('.') != 1 or set(t) != {'rows','sha256','kind'}
                or type(t['rows']) is not int or t['rows'] < 0 or t['kind'] not in ('r','p','m','S')):
            raise Held('table_fact_invalid')
        sha256(t['sha256'])
    for t in facts['catalog'].values():
        if set(t) != {'objects','sha256'} or type(t['objects']) is not int or t['objects'] < 0:
            raise Held('catalog_fact_invalid')
        sha256(t['sha256'])
    a=m['authority']
    if (not isinstance(a,dict) or set(a) != {'databaseOwner','schemaOwners','requiredRoles','rolesWithoutPasswords','roleMemberships'}
            or set(a['schemaOwners']) != set(RECEIVING7.schemas) or not a['requiredRoles']
            or a['requiredRoles'] != sorted(set(a['requiredRoles']))
            or not set(a['schemaOwners'].values()) | {a['databaseOwner']} <= set(a['requiredRoles'])):
        raise Held('authority_coverage_differs')
    return m


def seal(manifest, archive, key):
    if not isinstance(archive,bytes) or not 0 < len(archive) <= MAX_ARCHIVE or not archive.startswith(b'PGDMP'):
        raise Held('archive_bounds_invalid')
    return Fernet(key).encrypt(canonical(dict(manifest=manifest,archive=base64.b64encode(archive).decode('ascii'))))


def open_envelope(encrypted, key, *, expected, expected_encrypted_sha, policy):
    """An independently held artifact digest is mandatory, even with a valid key."""
    if not isinstance(encrypted,bytes) or not 0 < len(encrypted) <= MAX_ENVELOPE or digest(encrypted) != sha256(expected_encrypted_sha):
        raise Held('encrypted_artifact_differs')
    try:
        value = strict_json(Fernet(key).decrypt(encrypted))
        if not isinstance(value,dict) or set(value) != {'manifest','archive'}:
            raise Held('envelope_shape_differs')
        m = validate_manifest(value['manifest'],expected,policy)
        data = base64.b64decode(value['archive'],validate=True)
        if len(data) != m['archiveBytes'] or digest(data) != m['archiveSha256'] or not data.startswith(b'PGDMP'):
            raise Held('archive_binding_differs')
        return m,data
    except Exception:
        raise Held('envelope_authentication_or_binding_failed') from None


def open_profile(selected, encrypted, key, **expected):
    """Explicit compatibility dispatch; never relabel a v2 archive as v1."""
    selected=checked_profile(selected)
    if selected == LEGACY6:
        if set(expected) != {'expected_project'}:
            raise Held('legacy_reader_arguments_differ')
        return legacy.open_backup(encrypted,key,expected['expected_project'])
    return open_envelope(encrypted,key,**expected)


async def sequence_check(conn,facts):
    for name,t in facts['tables'].items():
        if t['kind']=='S':
            schema,table=name.split('.')
            value=await legacy.relation_fingerprint(conn,native.quoted(schema)+'.'+native.quoted(table),'S')
            if dict(value,kind='S') != t:
                raise Held('sequence_changed_during_capture')


@asynccontextmanager
async def bounded_run(timeout_seconds):
    """Own the legacy helper diagnostic context without sharing schema state."""
    if type(timeout_seconds) not in (int,float) or not 0 < timeout_seconds <= 600:
        raise Held('budget_invalid')
    diagnostics=legacy.ExportDiagnostics(timeout_seconds,None)
    control=legacy.ExportControl(diagnostics)
    token=legacy.EXPORT_CONTROL.set(control)
    try:
        async with asyncio.timeout(timeout_seconds):
            yield control
    finally:
        legacy.EXPORT_CONTROL.reset(token)


async def close_owned(conn):
    try:
        await conn.close(timeout=5)
    except BaseException as original:
        try:
            conn.terminate()
        except BaseException as cleanup:
            original.connectionTerminateErrorType=type(cleanup).__name__
        raise


async def capture(conn, settings, pg_dump, raw, expected, policy, migration_hashes, *, remote):
    """Internal snapshot worker. Tests inject only the connection/tool boundary."""
    dependency_policy(policy)
    async with readonly_snapshot(conn,rollback_timeout=5):
        await check_scope(conn,RECEIVING7)
        if await conn.fetchval("SHOW transaction_read_only") != 'on':
            raise Held('source_not_readonly')
        snap=await conn.fetchval('SELECT pg_export_snapshot()')
        facts=await fingerprint(conn,RECEIVING7)
        dep=check_dependencies(await dependencies(conn,RECEIVING7),policy)
        roles=await authority(conn,RECEIVING7)
        source_id=await conn.fetchval('SELECT system_identifier::text FROM pg_control_system()')
        source_oid=await conn.fetchval('SELECT oid::bigint FROM pg_database WHERE datname=current_database()')
        version=await conn.fetchval('SHOW server_version_num')
        await legacy.tool(pg_dump,['--format=custom','--quote-all-identifiers','--encoding=UTF8',
            '--lock-wait-timeout=5000','--snapshot='+snap,'--file='+str(raw),'--no-password',
            *['--schema='+s for s in RECEIVING7.schemas]],settings,remote)
        if not raw.is_file() or raw.stat().st_size > MAX_ARCHIVE:
            raise Held('archive_bounds_invalid')
        await sequence_check(conn,facts)
        if await authority(conn,RECEIVING7) != roles:
            raise Held('global_role_metadata_changed')
        await check_scope(conn,RECEIVING7)
        data=raw.read_bytes()
        m=dict(format=RECEIVING7.format,profile=RECEIVING7.name,profileSha256=RECEIVING7.sha256,
            schemas=list(RECEIVING7.schemas),binding=expected,createdAt=datetime.now(timezone.utc).isoformat(),
            serverVersionNum=version,archiveBytes=len(data),archiveSha256=digest(data),facts=facts,
            authority=roles,dependencies=dep,migrationFileHashes=migration_hashes,
            rowFingerprintAlgorithm=ROW_ALGORITHM,sourceSystemIdentifier=source_id,
            sourceDatabaseOid=source_oid,ownershipMode='preserve',sequenceStateIsMvcc=False,
            sequencesObservedStable=True,managedRecoveryVerified=False)
        validate_manifest(m,expected,policy)
    # Catalog/global role rows are MVCC-visible. Re-read after ending the source
    # snapshot; a repeatable-read recheck alone could hide concurrent DDL/roles.
    if await authority(conn,RECEIVING7) != roles:
        raise Held('global_role_metadata_changed')
    await check_scope(conn,RECEIVING7)
    return m,data


async def _export_backup(url, project, pg_dump, pg_restore, backup_directory,key_directory,
                        migration_hashes, *, execution_packet, packet_sha, timeout_seconds=600):
    """Only entry point that opens a source. Packet/source/profile checks precede DNS."""
    p=receipts.packet(execution_packet,packet_sha,'export')
    if p['projectRef'] != project:
        raise Held('project_binding_differs')
    dependency_policy(p['dependencyPolicy'])
    settings_before_dns=maintenance.direct_settings(url,project)  # No app/pooler fallback.
    expected=p['binding']
    if expected['sourceBinding'] != source_binding(settings_before_dns,project):
        raise Held('source_target_binding_differs')
    remaining=(receipts.check_window(expected['window'])-datetime.now(timezone.utc)).total_seconds()
    timeout_seconds=min(timeout_seconds,remaining)
    async with bounded_run(timeout_seconds) as control:
        settings=await maintenance.dump_settings(url,project)
        directory=legacy.private_directory(backup_directory,'backups')
        key_path=legacy.private_directory(key_directory,'credentials')/'backup.key'
        key=Fernet.generate_key()
        with key_path.open('xb') as stream:
            stream.write(key)
        raw=directory/'archive.partial'; partial=directory/'backup.partial.enc'; final=directory/'backup.jmax.enc'
        conn=None; body_ready=False
        async def clean():
            if control.tool_cleanup_held:
                raise Held('owned_tool_cleanup_held')
            await legacy.remove_partial_files((raw,) if body_ready else (raw,partial))
        async def close():
            if conn is not None:
                await close_owned(conn)
        async with preserve_cleanup_failure(clean,'partialCleanupErrorType'):
            async with preserve_cleanup_failure(close,'connectionCloseErrorType'):
                conn=await maintenance.connect(url,project,readonly=True,timeout=20,command_timeout=60,
                    label=control.application_name)
                m,data=await capture(conn,settings,pg_dump,raw,expected,p['dependencyPolicy'],migration_hashes,remote=True)
                await legacy.tool(pg_restore,['--list',str(raw)])
                encrypted=seal(m,data,key)
                with partial.open('xb') as stream:
                    stream.write(encrypted)
                if open_envelope(partial.read_bytes(),key,expected=expected,
                    expected_encrypted_sha=digest(encrypted),policy=p['dependencyPolicy']) != (m,data):
                    raise Held('encrypted_readback_differs')
            # Close succeeded; remove plaintext before publication.
            await legacy.remove_partial_files((raw,))
            control.check_deadline(); receipts.check_window(expected['window'])
            body_ready=True
        # Both cleanup contexts completed. Publishing cannot precede a later
        # failing cleanup pass. The enclosing deadline is checked before rename.
        control.check_deadline(); receipts.check_window(expected['window'])
        if receipts.source_hashes() != expected['sourceHashes']:
            raise Held('toolchain_source_changed')
        partial.rename(final)
        return dict(receipts.receipt(m,digest(encrypted)), encryptedBackup=str(final),privateKey=str(key_path))


async def export_backup(url,project,pg_dump,pg_restore,backup_directory,key_directory,migration_hashes,
                        *,execution_packet,packet_sha,timeout_seconds=600):
    try:
        return await _export_backup(url,project,pg_dump,pg_restore,backup_directory,key_directory,migration_hashes,
            execution_packet=execution_packet,packet_sha=packet_sha,timeout_seconds=timeout_seconds)
    except BaseException as exc:
        # Fixed booleans disclose incomplete cleanup/custody without paths/data.
        # Validation can fail before directories exist; never create or repair them.
        directory,key_directory=Path(backup_directory),Path(key_directory)
        flags={}
        for k,path in (('privateKeyRetained',key_directory/'backup.key'),
                       ('rawPartialRetained',directory/'archive.partial'),
                       ('encryptedPartialRetained',directory/'backup.partial.enc'),
                       ('finalBackupPresent',directory/'backup.jmax.enc')):
            try:flags[k]=path.exists()
            except OSError:flags['artifactInspectionHeld']=True
        exc.backupArtifacts=flags
        raise


def source_binding(settings,project):
    return digest(canonical(dict(projectRef=project,host=settings['host'],port=settings['port'],
                                 database=settings['database'],user=settings['user'])))


@dataclass(frozen=True)
class RestoreTarget:
    url: str
    control_url: str
    system_identifier: str
    database_oid: int


def restore_settings(target):
    if not isinstance(target,RestoreTarget):
        raise Held('owned_restore_target_required')
    settings=native.disposable_connection(target.url)
    if not re.fullmatch('native_purchase_test_backup_[a-f0-9]{32}',settings['database']) or settings['port']<1024:
        raise Held('uuid_owned_restore_database_required')
    from urllib.parse import urlsplit,unquote
    u=urlsplit(target.control_url)
    if (u.scheme not in ('postgres','postgresql') or u.hostname != settings['host']
            or (u.port or 5432) != settings['port'] or unquote(u.path) != '/native_purchase_test_control'
            or unquote(u.username or '') != settings['user'] or u.query or u.fragment
            or not isinstance(target.system_identifier,str) or not target.system_identifier.isdigit()
            or type(target.database_oid) is not int or target.database_oid <= 0):
        raise Held('dedicated_cluster_binding_required')
    return settings


async def empty_target(conn,target,settings,m):
    system=await conn.fetchval('SELECT system_identifier::text FROM pg_control_system()')
    row=await conn.fetchrow('SELECT oid::bigint AS oid,pg_get_userbyid(datdba) AS owner FROM pg_database WHERE datname=current_database()')
    if (system != target.system_identifier or row['oid'] != target.database_oid
            or row['owner'] != m['authority']['databaseOwner']
            or (system==m['sourceSystemIdentifier'] and row['oid']==m['sourceDatabaseOid'])):
        raise Held('restore_identity_differs')
    occupied=await conn.fetchval(f'''SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE {native.NAMESPACES})
        OR EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE {native.NAMESPACES})
        OR EXISTS(SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE {native.NAMESPACES})
        OR EXISTS(SELECT 1 FROM pg_default_acl d JOIN pg_namespace n ON n.oid=d.defaclnamespace WHERE {native.NAMESPACES})
        OR EXISTS(SELECT 1 FROM pg_namespace n WHERE {native.NAMESPACES} AND n.nspname<>'public')''')
    if occupied:
        raise Held('nonempty_restore_target')
    version=await conn.fetchval('SHOW server_version_num')
    if int(version)//10000 != int(m['serverVersionNum'])//10000:
        raise Held('major_version_differs')
    active=await conn.fetchval('SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()')
    if active:
        raise Held('restore_target_in_use')
    return version


async def bootstrap(conn,m,policy):
    check_dependencies(m['dependencies'],policy)
    current=await conn.fetchval('SELECT current_user')
    for name in m['authority']['requiredRoles']:
        role=await conn.fetchrow('SELECT rolcanlogin,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=$1',name)
        if role is None:
            raise Held('preprovisioned_role_missing')
        # The dedicated local cluster's current owner is the only privileged LOGIN
        # exception; all other required roles must already be inert NOLOGIN stubs.
        if name != current and (any(role.values()) or await conn.fetchval('SELECT EXISTS(SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=$1))',name)):
            raise Held('recovery_role_not_inert')
    async with conn.transaction():
        await conn.execute('ALTER SCHEMA public OWNER TO '+native.quoted(m['authority']['schemaOwners']['public']))
        for e in m['dependencies']['extensions']:
            if not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM pg_available_extension_versions WHERE name=$1 AND version=$2)',e['extname'],e['extversion']):
                raise Held('extension_version_unavailable')
            await conn.execute('CREATE SCHEMA IF NOT EXISTS extensions')
            await conn.execute('CREATE EXTENSION '+native.quoted(e['extname'])+' WITH SCHEMA extensions VERSION '+"'"+e['extversion']+"'")
        for f in m['dependencies']['authFunctions']:
            await conn.execute('CREATE SCHEMA IF NOT EXISTS auth')
            await conn.execute(f['definition'])  # Independently expected definition hash checked first.


async def verify_restore(target, encrypted,key,pg_restore,temporary_directory, *, expected,
                         expected_encrypted_sha,policy,execution_window,timeout_seconds=600):
    """Owned disposable only. No production restore, role creation or role alteration."""
    settings=restore_settings(target)
    m,data=open_envelope(encrypted,key,expected=expected,expected_encrypted_sha=expected_encrypted_sha,policy=policy)
    if receipts.source_hashes() != expected['sourceHashes']:
        raise Held('toolchain_source_changed')
    async with bounded_run(min(timeout_seconds,(receipts.check_window(execution_window)-datetime.now(timezone.utc)).total_seconds())) as control:
        # Bind the separately supplied control connection before any target SQL.
        conn=await asyncpg.connect(target.control_url,ssl=False,timeout=20,command_timeout=60)
        try:
            if await conn.fetchval('SELECT system_identifier::text FROM pg_control_system()') != target.system_identifier:
                raise Held('control_cluster_differs')
        finally:
            await close_owned(conn)
        directory=legacy.private_directory(temporary_directory,'backups')
        raw=directory/'restore.partial'; listing=directory/'restore.list.partial'; conn=None
        async def close():
            if conn is not None:
                await close_owned(conn)
        async with preserve_cleanup_failure(lambda: legacy.remove_partial_files((raw,listing)),'partialCleanupErrorType'):
            async with preserve_cleanup_failure(close,'connectionCloseErrorType'):
                raw.write_bytes(data)
                listing.write_bytes(legacy.restore_list(await legacy.tool(pg_restore,['--list',str(raw)])))
                conn=await asyncpg.connect(**settings,ssl=False,timeout=20,command_timeout=60)
                version=await empty_target(conn,target,settings,m)
                await bootstrap(conn,m,policy)
                await close_owned(conn); conn=None
                await legacy.tool(pg_restore,['--single-transaction','--exit-on-error','--clean','--if-exists',
                    '--use-list='+str(listing),'--no-password','--dbname='+settings['database'],str(raw)],settings)
                conn=await asyncpg.connect(**settings,ssl=False,timeout=20,command_timeout=60)
                async with readonly_snapshot(conn,rollback_timeout=5):
                    await check_scope(conn,RECEIVING7)
                    actual=await fingerprint(conn,RECEIVING7)
                    if actual != m['facts']:
                        raise Held('restored_facts_differ')
                    check_dependencies(await dependencies(conn,RECEIVING7),policy)
            control.check_deadline(); receipts.check_window(execution_window)
        if receipts.source_hashes() != expected['sourceHashes']:
            raise Held('toolchain_source_changed')
        return receipts.receipt(m,expected_encrypted_sha,restored=True,patch_matched=version==m['serverVersionNum'],verification_window=execution_window,
            topology='same_cluster' if target.system_identifier==m['sourceSystemIdentifier'] else 'cross_cluster')
