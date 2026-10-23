"""Original-column fingerprints for additive native migrations.

Metadata and digests only; no rows, SQL defaults or connection values returned.
New fields are excluded explicitly, while removed/retyped original fields hold.
"""
import asyncpg
from readonly_snapshot import readonly_snapshot
import json
import re
from uuid import UUID
import schema_reconciliation as reconciliation


def quoted(value):
    return '"'+value.replace('"','""')+'"'


async def original_columns(conn):
    rows = await conn.fetch("""SELECT n.nspname,c.relname,a.attname,
        format_type(a.atttypid,a.atttypmod) AS type
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid
        WHERE n.nspname=ANY($1::text[]) AND c.relkind IN ('r','p')
          AND a.attnum>0 AND NOT a.attisdropped ORDER BY 1,2,a.attnum""",list(reconciliation.SCHEMAS))
    tables = {}
    for row in rows:
        key = (row['nspname'],row['relname'])
        tables.setdefault(key,[]).append({'name':row['attname'],'type':row['type']})
    return tables


async def fingerprints(conn, baseline, *, exclude_synthetic=None):
    """Compare the same original projection before/after an additive change."""
    result = {};exclude_synthetic=exclude_synthetic or {}
    permitted={('public','stores'):'id',('public','items'):'code',('public','store_items'):'store_id',('public','store_state'):'store_id',('public','activity_log'):'user_id',('public','staff_members'):'id'}
    for key,(field,value) in exclude_synthetic.items():
        values=[value] if isinstance(value,str) else value
        if permitted.get(key)!=field or not isinstance(values,list) or not values or any(not isinstance(v,str) or not v for v in values) or len(set(values))!=len(values) or key not in baseline:
            raise ValueError('Only exact invented store/item/audit identities may be excluded')
    async with readonly_snapshot(conn):
        await conn.execute("SET LOCAL statement_timeout='20s'; SET LOCAL TIME ZONE 'UTC'")
        current = await original_columns(conn)
        for key, columns in baseline.items():
            if key not in current: raise ValueError('Original application table was removed')
            actual = {column['name']:column['type'] for column in current[key]}
            if not columns or len({c['name'] for c in columns}) != len(columns):
                raise ValueError('Original column identity is ambiguous')
            if any(actual.get(c['name']) != c['type'] for c in columns):
                raise ValueError('Original application column was removed or retyped')
            table = '.'.join(quoted(value) for value in key)
            projection = ','.join(quoted(c['name']) for c in columns)
            suffix='';args=[]
            if key in exclude_synthetic:
                field,value=exclude_synthetic[key]
                identity_type=actual.get(field)
                if identity_type not in ('text','uuid'):raise ValueError('Synthetic identity must use an original text/UUID column')
                values=[value] if isinstance(value,str) else value
                if identity_type=='uuid':
                    if key!=('public','staff_members') or any(str(UUID(v))!=v for v in values):raise ValueError('Synthetic roster identity must be a canonical UUID')
                    values=[UUID(v) for v in values]
                suffix=' WHERE NOT coalesce('+quoted(field)+'=ANY($1::'+identity_type+'[]),false)';args=[values]
            row = await conn.fetchrow("SELECT count(*) AS rows,encode(sha256(convert_to(coalesce(string_agg(h,'' ORDER BY h),''),'UTF8')),'hex') AS sha256 FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS h FROM (SELECT "+projection+' FROM '+table+suffix+") t) x",*args)
            result['.'.join(key)] = dict(row)
    return result


def checked_fingerprint_chunk_size(value):
    """Fixed small statement bound, independent of data/aggregate memory size."""
    if type(value) is not int or not 1 <= value <= 4:
        raise ValueError('Fingerprint chunk size must be between one and four')
    return value


def checked_fingerprint_chunk(rows, positions, *, max_rows=None):
    """Refuse missing/duplicate/extra positions and malformed digest facts."""
    expected = set(positions)
    if len(expected) != len(positions) or any(type(p) is not int for p in positions):
        raise ValueError('Ambiguous fingerprint positions')
    result = {}
    for row in rows:
        value = dict(row)
        if set(value) != {'position', 'rows', 'sha256'}:
            raise ValueError('Fingerprint result shape differs')
        position, count, digest = value['position'], value['rows'], value['sha256']
        if (type(position) is not int or position not in expected or position in result
                or type(count) is not int or count < 0
                or max_rows is not None and count > max_rows
                or not isinstance(digest, str) or re.fullmatch('[a-f0-9]{64}', digest) is None):
            raise ValueError('Fingerprint result is incomplete or ambiguous')
        result[position] = {'rows': count, 'sha256': digest}
    if set(result) != expected:
        raise ValueError('Fingerprint result coverage differs')
    return result


async def fingerprints_batched(conn, baseline, *, exclude_synthetic=None, chunk_size=2):
    """Par-only original projections; the historical algorithm above is intact.

    No probe, row limit or cursor fallback is added to this hash format. The
    relation-count bound is not a memory bound. Each statement retains 20s SQL
    enforcement and every phase owns/retains the same repeatable-read snapshot.
    """
    chunk_size = checked_fingerprint_chunk_size(chunk_size)
    result = {}; exclude_synthetic = exclude_synthetic or {}
    permitted = {('public','stores'):'id', ('public','items'):'code',
        ('public','store_items'):'store_id', ('public','store_state'):'store_id',
        ('public','activity_log'):'user_id', ('public','staff_members'):'id'}
    for key, (field, value) in exclude_synthetic.items():
        values = [value] if isinstance(value, str) else value
        if (permitted.get(key) != field or not isinstance(values, list) or not values
                or any(not isinstance(v, str) or not v for v in values)
                or len(set(values)) != len(values) or key not in baseline):
            raise ValueError('Only exact invented store/item/audit identities may be excluded')
    async with readonly_snapshot(conn):
        await conn.execute("SET LOCAL statement_timeout='20s'; SET LOCAL TIME ZONE 'UTC'")
        current = await original_columns(conn)
        entries = list(baseline.items())
        # Validate the entire original projection before building query chunks.
        identities = {}
        for key, columns in entries:
            if key not in current:
                raise ValueError('Original application table was removed')
            actual = {column['name']:column['type'] for column in current[key]}
            if not columns or len({c['name'] for c in columns}) != len(columns):
                raise ValueError('Original column identity is ambiguous')
            if any(actual.get(c['name']) != c['type'] for c in columns):
                raise ValueError('Original application column was removed or retyped')
            if key in exclude_synthetic:
                field, value = exclude_synthetic[key]
                identity_type = actual.get(field)
                if identity_type not in ('text', 'uuid'):
                    raise ValueError('Synthetic identity must use an original text/UUID column')
                values = [value] if isinstance(value, str) else value
                if identity_type == 'uuid':
                    if key != ('public','staff_members') or any(str(UUID(v)) != v for v in values):
                        raise ValueError('Synthetic roster identity must be a canonical UUID')
                    values = [UUID(v) for v in values]
                identities[key] = field, identity_type, values
        for start in range(0, len(entries), chunk_size):
            queries, args = [], []
            chunk = entries[start:start + chunk_size]
            for offset, (key, columns) in enumerate(chunk):
                table = '.'.join(quoted(value) for value in key)
                projection = ','.join(quoted(c['name']) for c in columns)
                suffix = ''
                if key in identities:
                    field, identity_type, values = identities[key]
                    args.append(values)
                    suffix = (' WHERE NOT coalesce(' + quoted(field) + '=ANY($' +
                              str(len(args)) + '::' + identity_type + '[]),false)')
                queries.append('(SELECT ' + str(start + offset) + '::integer AS position, '
                    "count(*) AS rows,encode(sha256(convert_to(coalesce(string_agg(h,'' ORDER BY h),''),'UTF8')),'hex') AS sha256 "
                    "FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS h FROM (SELECT "
                    + projection + ' FROM ' + table + suffix + ') t) x)')
            facts = checked_fingerprint_chunk(await conn.fetch(' UNION ALL '.join(queries), *args),
                                              list(range(start, start + len(chunk))))
            for offset, (key, _) in enumerate(chunk):
                result['.'.join(key)] = facts[start + offset]
    return result


async def ledger_fingerprints(conn):
    """Hash entire existing ledger rows so old statements cannot change silently."""
    rows = await conn.fetch("""SELECT version::text,
        encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS sha256
        FROM supabase_migrations.schema_migrations t ORDER BY version::text""")
    if any(r['version'] is None for r in rows) or len({r['version'] for r in rows}) != len(rows):
        raise ValueError('Migration versions must be non-null and unique')
    return {row['version']: row['sha256'] for row in rows}


async def ledger_contract(conn):
    """Pin ledger defaults, uniqueness, ownership and access without SQL bodies."""
    unique = await conn.fetchval("""SELECT EXISTS(SELECT 1 FROM pg_index i
        JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attname='version'
        WHERE i.indrelid=to_regclass('supabase_migrations.schema_migrations')
        AND a.attnotnull AND i.indisunique AND i.indisvalid AND i.indisready AND i.indislive
        AND i.indimmediate AND i.indnkeyatts=1 AND i.indkey[0]=a.attnum
        AND i.indpred IS NULL AND i.indexprs IS NULL)""")
    if not unique:
        raise ValueError('Migration ledger requires immediate valid unique non-null versions')
    result = {}
    from native_backup import CATALOG, NAMESPACES
    for group in ('schemas', 'relations', 'columns', 'constraints', 'indexes', 'triggers',
                  'internal_trigger_states', 'policies', 'functions'):
        sql = CATALOG[group].replace(NAMESPACES, "n.nspname='supabase_migrations'")
        rows = await conn.fetch('SELECT to_jsonb(r)::text AS value FROM (' + sql + ') r')
        result[group] = sorted((reconciliation.safe_record(json.loads(r['value'])) for r in rows),
                               key=lambda r: json.dumps(r, sort_keys=True))
    result['indexState'] = [dict(r) for r in await conn.fetch("""SELECT c.relname,
        i.indisunique,i.indisvalid,i.indisready,i.indislive,i.indimmediate,
        i.indnkeyatts,i.indnatts,i.indkey::text AS keys
        FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='supabase_migrations'
        ORDER BY c.relname""")]
    result['defaultAcl'] = [dict(r) for r in await conn.fetch("""SELECT
        pg_get_userbyid(d.defaclrole) AS creator,coalesce(n.nspname,'global') AS scope,
        d.defaclobjtype::text AS kind,d.defaclacl::text AS acl FROM pg_default_acl d
        LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace
        WHERE d.defaclnamespace=0 OR n.nspname='supabase_migrations' ORDER BY 1,2,3""")]
    result['columnAcl'] = [dict(r) for r in await conn.fetch("""SELECT c.relname,a.attname,
        a.attacl::text AS acl FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='supabase_migrations'
        AND a.attnum>0 AND NOT a.attisdropped ORDER BY 1,2""")]
    # Roles and memberships affect effective grants. Never select password catalogs.
    result['roles'] = [dict(r) for r in await conn.fetch("""SELECT rolname,rolsuper,
        rolinherit,rolcreaterole,rolcreatedb,rolcanlogin,rolreplication,rolbypassrls
        FROM pg_roles ORDER BY rolname""")]
    result['memberships'] = [dict(r) for r in await conn.fetch("""SELECT
        pg_get_userbyid(roleid) AS role,pg_get_userbyid(member) AS member,
        pg_get_userbyid(grantor) AS grantor,admin_option,inherit_option,set_option
        FROM pg_auth_members ORDER BY 1,2,3""")]
    return result


async def lock_original_tables(conn, baseline):
    if not conn.is_in_transaction(): raise ValueError('Original-table locks require the installation transaction')
    # Serializes against writes only during installation; lock_timeout is set
    # by the caller. No triggers/jobs are disabled, called or reconstructed.
    tables = ','.join('.'.join(quoted(value) for value in key) for key in sorted(baseline))
    if not tables: raise ValueError('Reviewed application baseline is absent')
    await conn.execute('LOCK TABLE '+tables+' IN SHARE MODE')
