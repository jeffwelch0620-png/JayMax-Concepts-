"""Snapshot-consistent native SQL backup and disposable-only restore verification.

This build tool deliberately refuses operational/remote database destinations.
It does not implement the app's legacy JSON export or an operational restore UI.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlparse

import asyncpg

SCHEMAS=('public','purchasing','actual_inventory')
REQUIRED=('purchasing.import_files','purchasing.posting_batches','purchasing.corrections',
          'purchasing.correction_lines','actual_inventory.count_snapshots',
          'actual_inventory.period_closures','actual_inventory.reopen_events','actual_inventory.scope_bridges')
NAMESPACES="n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%' AND n.nspname NOT LIKE 'pg_temp_%'"
CATALOG={
 'schemas':f"SELECT n.nspname,pg_get_userbyid(n.nspowner) AS owner,ARRAY(SELECT a::text FROM unnest(coalesce(n.nspacl,acldefault('n',n.nspowner))) a ORDER BY a::text) AS acl FROM pg_namespace n WHERE {NAMESPACES}",
 'relations':f"SELECT n.nspname,c.relname,c.relkind,c.relpersistence,c.relrowsecurity,c.relforcerowsecurity,c.relreplident,c.reloptions,ARRAY(SELECT a::text FROM unnest(coalesce(c.relacl,acldefault(CASE WHEN c.relkind='S' THEN 's'::\"char\" ELSE 'r'::\"char\" END,c.relowner))) a ORDER BY a::text) AS acl,pg_get_userbyid(c.relowner) AS owner FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE {NAMESPACES}",
 'columns':f"SELECT n.nspname,c.relname,a.attnum,a.attname,format_type(a.atttypid,a.atttypmod) AS type,a.attnotnull,a.attidentity,a.attgenerated,pg_get_expr(d.adbin,d.adrelid) AS default_expr FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum WHERE {NAMESPACES} AND a.attnum>0 AND NOT a.attisdropped",
 'constraints':f"SELECT n.nspname,c.relname,k.conname,k.contype,k.convalidated,pg_get_constraintdef(k.oid,true) AS definition FROM pg_constraint k JOIN pg_namespace n ON n.oid=k.connamespace LEFT JOIN pg_class c ON c.oid=k.conrelid WHERE {NAMESPACES}",
 'functions':f"SELECT n.nspname,p.proname,pg_get_function_identity_arguments(p.oid) AS args,pg_get_functiondef(p.oid) AS definition,p.proacl::text AS acl,pg_get_userbyid(p.proowner) AS owner FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE {NAMESPACES} AND p.prokind IN ('f','p')",
 'triggers':f"SELECT n.nspname,c.relname,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid,true) AS definition FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE {NAMESPACES} AND NOT t.tgisinternal",
 'internal_trigger_states':f"SELECT n.nspname,c.relname,k.conname,t.tgenabled,t.tgtype,t.tgdeferrable,t.tginitdeferred,p.proname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_proc p ON p.oid=t.tgfoid LEFT JOIN pg_constraint k ON k.oid=t.tgconstraint WHERE {NAMESPACES} AND t.tgisinternal",
 'indexes':f"SELECT n.nspname,c.relname,pg_get_indexdef(c.oid) AS definition FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE {NAMESPACES} AND c.relkind='i'",
 'views':f"SELECT n.nspname,c.relname,pg_get_viewdef(c.oid,true) AS definition FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE {NAMESPACES} AND c.relkind IN ('v','m')",
 'policies':f"SELECT n.nspname,c.relname,p.polname,p.polcmd,p.polpermissive,ARRAY(SELECT CASE WHEN r=0 THEN 'PUBLIC' ELSE pg_get_userbyid(r) END FROM unnest(p.polroles) r ORDER BY 1) AS roles,pg_get_expr(p.polqual,p.polrelid) AS using_expr,pg_get_expr(p.polwithcheck,p.polrelid) AS check_expr FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE {NAMESPACES}",
 'extensions':"SELECT e.extname,e.extversion,e.extrelocatable,n.nspname,pg_get_userbyid(e.extowner) AS owner FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace",
 'types':f"SELECT n.nspname,t.typname,t.typtype,t.typnotnull,format_type(t.typbasetype,t.typtypmod) AS base_type,t.typdefault,ARRAY(SELECT e.enumlabel FROM pg_enum e WHERE e.enumtypid=t.oid ORDER BY e.enumsortorder) AS labels FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE {NAMESPACES} AND t.typtype IN ('e','d')",
 'sequence_definitions':f"SELECT n.nspname,c.relname,s.seqstart,s.seqincrement,s.seqmax,s.seqmin,s.seqcache,s.seqcycle,format_type(s.seqtypid,NULL) AS type FROM pg_sequence s JOIN pg_class c ON c.oid=s.seqrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE {NAMESPACES}",
}


class BackupError(RuntimeError):
    pass


def disposable_connection(dsn):
    u=urlparse(dsn)
    database=unquote(u.path.lstrip('/'))
    if (u.scheme not in ('postgres','postgresql') or u.hostname not in ('127.0.0.1','::1')
        or not u.username or u.query or u.fragment
        or not re.fullmatch(r'native_purchase_test_[a-z0-9_]+',database)
        or database=='native_purchase_test_control'):
        raise BackupError('Use an explicitly disposable loopback native_purchase_test_* database; control, remote and operational databases are refused')
    return {'host':u.hostname,'port':u.port or 5432,'user':unquote(u.username),
            'password':unquote(u.password or ''),'database':database}


def digest_file(path):
    sha=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):sha.update(chunk)
    return sha.hexdigest()


def quoted(identifier):
    return '"'+identifier.replace('"','""')+'"'


async def configure(conn):
    await conn.execute("SET TIME ZONE 'UTC'; SET search_path=pg_catalog")


async def schema_ready(conn):
    missing=[name for name in REQUIRED if not await conn.fetchval('SELECT to_regclass($1) IS NOT NULL',name)]
    if missing:raise BackupError('Apply all five native inventory migrations before this backup verification: '+', '.join(missing))


async def snapshot_manifest(conn):
    """Called in the same repeatable-read snapshot used by pg_dump."""
    catalog={}
    for key,sql in CATALOG.items():
        rows=await conn.fetch('SELECT to_jsonb(r)::text AS value FROM ('+sql+') r ORDER BY to_jsonb(r)::text')
        text='\n'.join(row['value'] for row in rows)
        catalog[key]={'objects':len(rows),'sha256':hashlib.sha256(text.encode()).hexdigest()}
    tables={}
    relations=await conn.fetch(f"SELECT n.nspname,c.relname,c.relkind::text AS relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE {NAMESPACES} AND c.relkind IN ('r','p','m','S') ORDER BY 1,2")
    for r in relations:
        name=r['nspname']+'.'+r['relname'];sha=hashlib.sha256();count=0
        table=quoted(r['nspname'])+'.'+quoted(r['relname'])
        # Sequence state is not MVCC; included for comparison but separately disclosed.
        if r['relkind']=='S':
            # Sequences have no composite row type. WAL log_cnt is an internal
            # cache, not restored business state; compare the next-value state.
            sql=f"SELECT jsonb_build_object('last_value',last_value,'is_called',is_called)::text AS value FROM {table}"
        else:
            sql=f'SELECT to_jsonb(t)::text AS value FROM {table} t ORDER BY to_jsonb(t)::text'
        async for row in conn.cursor(sql,prefetch=100):
            sha.update(row['value'].encode());sha.update(b'\n');count+=1
        tables[name]={'rows':count,'sha256':sha.hexdigest(),'kind':r['relkind']}
    return {'tables':tables,'catalog':catalog}


async def run_dump(executable,args,connection):
    env=os.environ.copy()
    # Do not inherit unrelated PostgreSQL service/database settings.
    for key in list(env):
        if key.startswith('PG'):env.pop(key)
    env.update(PGHOST=connection['host'],PGPORT=str(connection['port']),PGUSER=connection['user'],
               PGPASSWORD=connection['password'],PGDATABASE=connection['database'],PGCLIENTENCODING='UTF8',PGCONNECT_TIMEOUT='10')
    try:
        result=await asyncio.to_thread(subprocess.run,[str(executable),*args],env=env,capture_output=True,timeout=180,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    except (OSError,subprocess.TimeoutExpired) as exc:raise BackupError('The PostgreSQL backup tool could not complete') from exc
    if result.returncode:raise BackupError('Native PostgreSQL backup failed; no verified backup was produced')
    return result


async def create_backup(dsn,pg_dump,output_directory):
    settings=disposable_connection(dsn)
    directory=Path(output_directory)
    directory.mkdir(parents=True,exist_ok=False)  # Never overwrite an earlier recovery snapshot.
    conn=await asyncpg.connect(**settings)
    try:
        await configure(conn)
        async with conn.transaction(isolation='repeatable_read',readonly=True):
            await schema_ready(conn)
            snapshot=await conn.fetchval('SELECT pg_export_snapshot()')
            facts=await snapshot_manifest(conn)
            dump=directory/'database.sql'
            await run_dump(pg_dump,['--format=plain','--inserts','--rows-per-insert=100','--quote-all-identifiers',
                '--encoding=UTF8','--lock-wait-timeout=5000','--snapshot='+snapshot,'--file='+str(dump)],settings)
            manifest={'format':'jaymax-native-sql-backup-v1','status':'captured_not_yet_restore_verified',
                'createdAt':datetime.now(timezone.utc).isoformat(),'database':settings['database'],
                'serverVersion':await conn.fetchval('SHOW server_version_num'),
                'scope':'Whole PostgreSQL database, including public and every application private schema',
                'ownerAndAclStatementsRetained':True,'globalRolesOrPasswordsBackedUp':False,
                'exportedSnapshot':snapshot,'sequenceStateIsMvcc':False,
                'dump':{'filename':dump.name,'bytes':dump.stat().st_size,'sha256':digest_file(dump)},**facts}
            (directory/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
            return manifest
    finally:await conn.close()


def validated_sql(directory,manifest):
    dump=Path(directory)/'database.sql'
    info=manifest.get('dump',{})
    if (manifest.get('format')!='jaymax-native-sql-backup-v1' or info.get('filename')!='database.sql'
        or not dump.is_file() or dump.stat().st_size!=info.get('bytes') or digest_file(dump)!=info.get('sha256')):
        raise BackupError('Backup is missing, incomplete or its checksum changed; restore was refused')
    lines=dump.read_text(encoding='utf-8').splitlines(keepends=True)
    # Only remove pg_dump's outer psql guards. Never filter invoice text inside SQL literals.
    edges=[i for i,line in enumerate(lines) if line.strip() and not line.startswith('--')]
    if not edges:raise BackupError('Empty backup')
    first,last=edges[0],edges[-1]
    start=re.fullmatch(r'\\restrict ([A-Za-z0-9]+)\s*',lines[first])
    end=re.fullmatch(r'\\unrestrict ([A-Za-z0-9]+)\s*',lines[last])
    if start or end:
        if not start or not end or start.group(1)!=end.group(1):raise BackupError('Incomplete native SQL input guards')
        lines[first]=lines[last]=''
    return ''.join(lines)


async def verify_restore(dsn,backup_directory):
    settings=disposable_connection(dsn)
    directory=Path(backup_directory)
    try:manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    except (OSError,ValueError) as exc:raise BackupError('A complete backup manifest is required') from exc
    sql=validated_sql(directory,manifest)  # Refuse damage before connecting or writing anything.
    if settings['database']==manifest['database']:raise BackupError('Restore must use a different, empty disposable database')
    conn=await asyncpg.connect(**settings)
    try:
        await configure(conn)
        # Any user objects make this an existing database, even if its tables are empty.
        occupied=await conn.fetchval(f"SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE {NAMESPACES}) OR EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE {NAMESPACES}) OR EXISTS(SELECT 1 FROM pg_namespace n WHERE {NAMESPACES} AND n.nspname<>'public')")
        if occupied:raise BackupError('Restore requires an empty disposable database; existing data and schema are never overwritten')
        if await conn.fetchval('SHOW server_version_num')!=manifest['serverVersion']:
            raise BackupError('Use the same PostgreSQL version for this build verification; cross-version recovery is not yet verified')
        try:
            async with conn.transaction():
                # PostgreSQL 17 omits CREATE for the standard public schema.
                # Keep the verified empty default schema; never clean or drop existing objects.
                await conn.execute(sql)
        except asyncpg.PostgresError as exc:
            raise BackupError('Native restore failed and its transaction was rolled back') from exc
        await configure(conn)  # Dump session settings must not affect deterministic comparisons.
        async with conn.transaction(isolation='repeatable_read',readonly=True):
            await schema_ready(conn)
            actual=await snapshot_manifest(conn)
        if actual!={'tables':manifest['tables'],'catalog':manifest['catalog']}:
            mismatch={group:sorted(key for key in set(actual[group])|set(manifest[group])
                if actual[group].get(key)!=manifest[group].get(key)) for group in ('tables','catalog')}
            (directory/('verification-failed-'+settings['database']+'.json')).write_text(
                json.dumps({'status':'verification_failed','mismatch':mismatch,'actual':actual},indent=2),encoding='utf-8')
            raise BackupError('Restored data/schema did not match: '+str(mismatch)+'; keep this disposable database for inspection')
        result={'status':'verified','database':settings['database'],'dumpSha256':manifest['dump']['sha256'],
            'tablesMatched':len(actual['tables']),'rowsMatched':sum(t['rows'] for t in actual['tables'].values()),
            'catalogGroupsMatched':len(actual['catalog']),'verifiedAt':datetime.now(timezone.utc).isoformat(),
            'scope':'Disposable application database only; no operational or managed-platform recovery claim'}
        path=directory/'restore-verifications'
        path.mkdir(exist_ok=True)
        (path/(settings['database']+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
        return result
    finally:await conn.close()


async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    create=sub.add_parser('create');create.add_argument('--connection-env',required=True)
    create.add_argument('--pg-dump',required=True);create.add_argument('--output',required=True)
    restore=sub.add_parser('verify-restore');restore.add_argument('--connection-env',required=True);restore.add_argument('--backup',required=True)
    args=parser.parse_args()
    dsn=os.getenv(args.connection_env)
    if not dsn:raise BackupError('The selected connection environment variable is missing')
    result=await create_backup(dsn,args.pg_dump,args.output) if args.action=='create' else await verify_restore(dsn,args.backup)
    # No connection URL/password or source row data is printed.
    print(json.dumps({'status':result['status'],'tables':len(result['tables']) if 'tables' in result else result['tablesMatched']}))


if __name__=='__main__':
    try:asyncio.run(main())
    except BackupError as exc:raise SystemExit(str(exc))
