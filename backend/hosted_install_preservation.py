"""Original-column fingerprints for additive native migrations.

Metadata and digests only; no rows, SQL defaults or connection values returned.
New fields are excluded explicitly, while removed/retyped original fields hold.
"""
import asyncpg
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
    async with conn.transaction(isolation='repeatable_read',readonly=True):
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


async def ledger_fingerprints(conn):
    """Hash entire existing ledger rows so old statements cannot change silently."""
    return {row['version']:row['sha256'] for row in await conn.fetch("""SELECT version::text,
        encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS sha256
        FROM supabase_migrations.schema_migrations t ORDER BY version::text""")}


async def lock_original_tables(conn, baseline):
    if not conn.is_in_transaction(): raise ValueError('Original-table locks require the installation transaction')
    # Serializes against writes only during installation; lock_timeout is set
    # by the caller. No triggers/jobs are disabled, called or reconstructed.
    tables = ','.join('.'.join(quoted(value) for value in key) for key in sorted(baseline))
    if not tables: raise ValueError('Reviewed application baseline is absent')
    await conn.execute('LOCK TABLE '+tables+' IN SHARE MODE')
