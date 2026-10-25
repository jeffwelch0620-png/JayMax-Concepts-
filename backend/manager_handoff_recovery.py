"""Explicit receiving recovery rehearsal. Loopback disposable targets ONLY.

No hosted adapter, live configuration, global schema mutation or key-file writer.
The old encrypted six-schema reader is retained unchanged in hosted_backup.
"""
import base64
import hashlib
import json
from pathlib import Path
import tempfile

import asyncpg
from cryptography.fernet import Fernet
import hosted_backup as legacy
import native_backup as native

LEGACY_SCHEMAS = ('public', 'purchasing', 'actual_inventory', 'prep_inventory',
                  'integrations', 'supabase_migrations')
SCHEMAS = LEGACY_SCHEMAS + ('operations',)
FORMAT = 'jaymax-local-handoff-encrypted-recovery-v1'
MAX_BYTES = 64 * 1024 * 1024


class Held(ValueError):
    pass


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()


def target(url):
    try:
        settings = native.disposable_connection(url)
        if settings['port'] < 1024:
            raise ValueError()
        return settings
    except (ValueError, native.BackupError):
        raise Held('Explicit disposable loopback database required') from None


async def connect(url):
    target(url)  # Refuse remote names/IPs, control DBs and URL options before network.
    return await asyncpg.connect(url, timeout=10, command_timeout=30,
                                 statement_cache_size=0, server_settings={'application_name': 'handoff-local-only'})


async def facts(conn, schemas=SCHEMAS):
    if tuple(schemas) not in (SCHEMAS, LEGACY_SCHEMAS):
        raise Held('Explicit receiving or historical schema profile required')
    await conn.execute('SET LOCAL search_path=pg_catalog')
    found = set(await conn.fetchval("SELECT array_agg(nspname::text) FROM pg_namespace WHERE nspname=ANY($1::text[])", list(schemas)) or [])
    if found != set(schemas):
        raise Held('Recovery profile schemas missing')
    catalog = {}
    for name, query in native.CATALOG.items():
        if name == 'extensions':
            query += " WHERE e.extname='plpgsql'"
            rows = await conn.fetch('SELECT to_jsonb(r)::text AS value FROM (' + query + ') r')
        else:
            query = query.replace(native.NAMESPACES, 'n.nspname=ANY($1::text[])')
            rows = await conn.fetch('SELECT to_jsonb(r)::text AS value FROM (' + query + ') r', list(schemas))
        catalog[name] = sorted(digest(r['value'].encode()) for r in rows)
    # Use the exact jsonb serialization used for catalog fingerprints.
    foreign_hashes = sorted(digest(r['value'].encode()) for r in await conn.fetch("""SELECT to_jsonb(r)::text AS value FROM (
        SELECT n.nspname,c.relname,k.conname,t.tgenabled,t.tgtype,t.tgdeferrable,t.tginitdeferred,p.proname
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_proc p ON p.oid=t.tgfoid LEFT JOIN pg_constraint k ON k.oid=t.tgconstraint
        WHERE t.tgisinternal AND n.nspname='public' AND c.relname='stores'
        AND k.conname='store_settings_store_id_fkey' AND k.conrelid=to_regclass('operations.store_settings')) r"""))
    rows = {}
    for r in await conn.fetch("""SELECT n.nspname,c.relname,c.relkind::text AS kind FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[]) AND c.relkind IN ('r','p','m','S') ORDER BY 1,2""", list(schemas)):
        name = r['nspname'] + '.' + r['relname']
        quoted = native.quoted(r['nspname']) + '.' + native.quoted(r['relname'])
        query = ('SELECT jsonb_build_object(\'last_value\',last_value,\'is_called\',is_called)::text AS value FROM ' + quoted
                 if r['kind'] == 'S' else 'SELECT to_jsonb(t)::text AS value FROM ' + quoted + ' t')
        hashes = []
        async for row in conn.cursor(query):
            hashes.append(digest(row['value'].encode()))
            if len(hashes) > 100000:
                raise Held('Local rehearsal row bound exceeded')
        rows[name] = {'count': len(hashes), 'sha256': digest(canonical(sorted(hashes)))}
    return {'catalog': catalog, 'rows': rows, 'receivingPublicForeignTriggers': foreign_hashes}


def preserved(before, after):
    """No legacy value/DDL change except ledger inserts and the reviewed FK triggers."""
    left = dict(before['rows']); right = dict(after['rows'])
    left.pop('supabase_migrations.schema_migrations', None)
    right.pop('supabase_migrations.schema_migrations', None)
    if left != right:
        raise Held('Existing application values or relations changed')
    for group, hashes in before['catalog'].items():
        actual = list(after['catalog'][group])
        if group == 'internal_trigger_states':
            added = set(after['receivingPublicForeignTriggers']) - set(before['receivingPublicForeignTriggers'])
            if len(added) not in (0, 2):
                raise Held('Unexpected receiving foreign-key guard delta')
            for value in added:
                actual.remove(value)
        if hashes != actual:
            raise Held('Existing catalog changed')


def seal(manifest, archive, key):
    if len(archive) > MAX_BYTES:
        raise Held('Local archive size bound exceeded')
    value = {'manifest': manifest | {'archiveSha256': digest(archive), 'archiveBytes': len(archive)},
             'archive': base64.b64encode(archive).decode()}
    return Fernet(key).encrypt(canonical(value))


def open_envelope(encrypted, key, expected_database):
    if not isinstance(encrypted, bytes) or len(encrypted) > 3 * MAX_BYTES:
        raise Held('Bounded authenticated archive required')
    try:
        def unique(pairs):
            out = {}
            for k, v in pairs:
                if k in out:
                    raise ValueError()
                out[k] = v
            return out
        value = json.loads(Fernet(key).decrypt(encrypted), object_pairs_hook=unique)
        m = value['manifest']; raw = base64.b64decode(value['archive'], validate=True)
        if (set(value) != {'manifest', 'archive'} or m['format'] != FORMAT or m['schemas'] != list(SCHEMAS)
                or m['sourceDatabase'] != expected_database or m['archiveSha256'] != digest(raw)
                or m['archiveBytes'] != len(raw) or len(raw) > MAX_BYTES or m['postgresMajor'] != 17):
            raise ValueError()
        return m, raw
    except Exception:
        raise Held('Archive authentication or receiving profile held') from None


async def export(url, pg_dump, key):
    settings = target(url)
    conn = await connect(url)
    try:
        async with conn.transaction(isolation='repeatable_read', readonly=True):
            await conn.execute("SET LOCAL statement_timeout='30s'")
            found = set(await conn.fetchval("SELECT array_agg(nspname::text) FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname<>'information_schema'"))
            if found != set(SCHEMAS):
                raise Held('Missing, managed or unclassified local schema; no complete recovery claim')
            if int(await conn.fetchval('SHOW server_version_num')) // 10000 != 17:
                raise Held('Reviewed PostgreSQL major required')
            # This local profile refuses extension/managed dependencies rather than skipping them.
            if await conn.fetchval("SELECT count(*) FROM pg_extension WHERE extname<>'plpgsql'"):
                raise Held('Extension dependency requires separately reviewed recovery support')
            if await conn.fetchval('SELECT EXISTS(SELECT 1 FROM pg_foreign_server)'):
                raise Held('Foreign server recovery requires separate review')
            before = await facts(conn)
            snap = await conn.fetchval('SELECT pg_export_snapshot()')
            archive = await legacy.tool(pg_dump, ['--format=custom', '--no-owner', '--snapshot=' + snap,
                '--encoding=UTF8', '--lock-wait-timeout=5000', *['--schema=' + x for x in SCHEMAS]], settings)
            if await facts(conn) != before:
                raise Held('Recovery source changed')
            manifest = {'format': FORMAT, 'schemas': list(SCHEMAS), 'sourceDatabase': settings['database'],
                        'postgresMajor': 17, 'facts': before, 'localOnly': True,
                        'rolePasswordRecoveryVerified': False, 'hostedRecoveryVerified': False}
        # Publish bytes only after the read transaction and connection close succeed.
    finally:
        await conn.close()
    return seal(manifest, archive, key)


async def restore(url, encrypted, key, expected_source, pg_restore):
    settings = target(url)
    manifest, archive = open_envelope(encrypted, key, expected_source)
    if settings['database'] == expected_source:
        raise Held('Restore into source refused')
    conn = await connect(url)
    try:
        # Refuse existing objects, including objects outside the expected schemas.
        if await conn.fetchval("""SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname<>'information_schema') OR
                EXISTS(SELECT 1 FROM pg_namespace WHERE nspname NOT LIKE 'pg_%'
                AND nspname NOT IN ('public','information_schema')) OR
                EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public') OR
                EXISTS(SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
                WHERE n.nspname='public' AND t.typtype IN ('e','d')) OR
                EXISTS(SELECT 1 FROM pg_default_acl) OR
                EXISTS(SELECT 1 FROM pg_extension WHERE extname<>'plpgsql')"""):
            raise Held('Nonempty disposable restore target refused')
        await conn.close(); conn = None
        with tempfile.TemporaryDirectory(prefix='handoff-fictional-restore-') as folder:
            dump = Path(folder) / 'archive.dump'; listing = Path(folder) / 'restore.list'
            dump.write_bytes(archive)
            toc = await legacy.tool(pg_restore, ['--list', str(dump)])
            listing.write_bytes(legacy.restore_list(toc))
            await legacy.tool(pg_restore, ['--exit-on-error', '--single-transaction', '--no-owner',
                '--use-list=' + str(listing), '--dbname=' + settings['database'], str(dump)], settings)
        conn = await connect(url)
        async with conn.transaction(readonly=True):
            if await facts(conn) != manifest['facts']:
                raise Held('Restored catalog, ownership, ACLs or values differ')
        return {'status': 'passed_local_only', 'sevenSchemasMatched': True,
                'encryptedArchiveAuthenticated': True, 'hostedRecoveryVerified': False,
                'passwordRecoveryVerified': False}
    finally:
        if conn is not None:
            await conn.close()
