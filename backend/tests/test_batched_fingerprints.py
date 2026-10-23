"""Independent frozen pre-batch oracles and fictional disposable parity checks."""
import ast
import asyncio
from copy import deepcopy
import hashlib
import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import asyncpg
import hosted_backup as backup
import hosted_install_preservation as preservation
from readonly_snapshot import readonly_snapshot, error_details
from apply_additive_migration import local_target
from local_query_metrics import MeasuredConnection, finish, instrument_functions, par_attribution_bindings

original_columns = preservation.original_columns
quoted = preservation.quoted
native = backup.native
SCHEMAS = backup.SCHEMAS
digest = backup.digest
BackupError = backup.BackupError
record_fingerprint_path = backup.record_fingerprint_path

FROZEN_FUNCTION_SHA256 = {'backend/hosted_install_preservation.py:fingerprints': '1023ddfa1851bde1295e4a268d3c82ee97aa4dfa15a50ac4d9328838d773e7ef', 'backend/hosted_backup.py:relation_fingerprint': '158e9bd5b5b3c89b226c79424a1580dc6215df7b65a42071f6bc57f991103b3e', 'backend/hosted_backup.py:fingerprint': 'f017bce91d347c408c04b460a85550d2f752e2e236632ca36a6f40b7e72ad4a8'}


async def _oracle_preservation(conn, baseline, *, exclude_synthetic=None):
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


async def _oracle_backup_relation(conn, quoted, kind, row_hashes=True, *, server_aggregation=True):
    path = 'cursorOnlyRelations'
    if kind != 'S' and row_hashes and server_aggregation:
        probe_rows = backup.MAX_FINGERPRINT_AGGREGATE_BYTES // backup.ROW_HASH_LINE_BYTES
        if probe_rows < 1:
            raise BackupError('Fingerprint aggregate bound must allow a row')
        # LIMIT bounds the aggregate even when this table is far larger than the
        # limit. A full probe is inconclusive and must stream the entire relation
        # in the same caller-owned snapshot. No estimates or error fallback.
        fact = await conn.fetchrow(f"""SELECT count(*) AS rows,
            encode(sha256(convert_to(coalesce(string_agg(value || E'\\n', ''
                ORDER BY value COLLATE "C"), ''), 'UTF8')), 'hex') AS sha256
            FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS value
                FROM {quoted} t LIMIT $1::bigint) hashed""", probe_rows)
        if fact['rows'] < probe_rows:
            record_fingerprint_path('serverAggregateRelations')
            return {'rows': fact['rows'], 'sha256': fact['sha256']}
        path = 'cursorFallbackRelations'
    # Sequences and pre-row-hash archives retain their existing byte/order rules.
    sql = (f"SELECT jsonb_build_object('last_value',last_value,'is_called',is_called)::text AS value FROM {quoted}"
           if kind == 'S' else
           (f"SELECT value FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS value FROM {quoted} t) hashed ORDER BY value COLLATE \"C\"" if row_hashes
            else f'SELECT to_jsonb(t)::text AS value FROM {quoted} t ORDER BY to_jsonb(t)::text'))
    count = 0
    sha = hashlib.sha256()
    async for row in conn.cursor(sql, prefetch=100):
        sha.update(row['value'].encode()); sha.update(b'\n'); count += 1
    record_fingerprint_path(path)
    return {'rows': count, 'sha256': sha.hexdigest()}


async def _oracle_backup(conn, row_hashes=True, *, server_aggregation=True):
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
        try:
            fact = await _oracle_backup_relation(conn, quoted, relation['kind'], row_hashes,
                                              server_aggregation=server_aggregation)
        except TimeoutError as exc:
            error = BackupError('Table fingerprint query timed out')
            error.failureObject = name
            raise error from exc
        tables[name] = {**fact, 'kind': relation['kind']}
    return {'tables': tables, 'catalog': catalog}


class BatchedFingerprintGuards(unittest.TestCase):
    def test_historical_functions_remain_byte_identical_to_frozen_sources(self):
        root = Path(__file__).resolve().parents[2]
        for target, expected in FROZEN_FUNCTION_SHA256.items():
            path, name = target.split(':')
            source = (root / path).read_text(encoding='utf-8')
            node = next(n for n in ast.parse(source).body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
            with self.subTest(function=name):
                self.assertEqual(hashlib.sha256(ast.get_source_segment(source, node).encode()).hexdigest(), expected)

    def test_fixed_small_chunk_bounds_and_result_coverage(self):
        for count in (True, False, 0, 5, -1, '4', None, 1.5):
            with self.subTest(size=count), self.assertRaises(ValueError):
                preservation.checked_fingerprint_chunk_size(count)
        for count in (1, 2, 3, 4):
            self.assertEqual(preservation.checked_fingerprint_chunk_size(count), count)
        valid = [{'position': 2, 'rows': 0, 'sha256': hashlib.sha256(b'').hexdigest()}]
        self.assertEqual(preservation.checked_fingerprint_chunk(valid, [2]),
                         {2: {'rows': 0, 'sha256': hashlib.sha256(b'').hexdigest()}})
        for rows in ([], valid * 2, valid + [{**valid[0], 'position': 3}],
                     [{**valid[0], 'position': True}], [{**valid[0], 'rows': True}],
                     [{**valid[0], 'rows': -1}], [{**valid[0], 'rows': 4}],
                     [{**valid[0], 'sha256': 'TEST ONLY invalid'}],
                     [{**valid[0], 'extra': 'TEST ONLY'}], [{k:v for k,v in valid[0].items() if k != 'rows'}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                preservation.checked_fingerprint_chunk(rows, [2], max_rows=3)


    def test_private_timeout_context_is_bounded_typed_and_not_in_public_details(self):
        for cause in (TimeoutError('TEST ONLY secret driver text'), asyncpg.QueryCanceledError('TEST ONLY SQL')):
            cause.snapshotCleanupErrorType='ConnectionError'
            error=preservation.wrap_fingerprint_timeout(cause,'original_projection',(('public','test_only_private'),))
            self.assertEqual(error_details(error)['sqlState'],getattr(cause,'sqlstate',None))
            self.assertEqual(error_details(error)['snapshotCleanupErrorType'],'ConnectionError')
            error.failureObjects.append('TEST ONLY spoofed name')
            private=preservation.private_fingerprint_timeout_details(error)
            self.assertEqual(private['fingerprintTimeout']['candidateObjects'],['public.test_only_private'])
            self.assertNotIn('test_only_private',json.dumps(error_details(error)))
            self.assertNotIn('TEST ONLY',str(error))
        spoof=TimeoutError('TEST ONLY')
        spoof.fingerprintTimeout={'family':'backup','candidateObjects':['TEST ONLY fake']}
        self.assertEqual(preservation.private_fingerprint_timeout_details(spoof),{})
        for members in ((), (('public','a'),)*2, (('public','x'*64),), [('public','a')],
                        (('public','a'),('public','b'),('public','c'),('public','d'),('public','e'))):
            with self.subTest(members=members),self.assertRaises(ValueError):
                preservation.wrap_fingerprint_timeout(TimeoutError(),'backup',members)


class MutatingConnection:
    def __init__(self, connection, mutate=None, *, timeout=False, error=None):
        self.connection, self.mutate, self.timeout = connection, mutate, timeout
        self.cursor_calls = 0
        self.error, self.batch_calls = error, 0

    def __getattr__(self, name): return getattr(self.connection, name)

    async def execute(self, query, *args):
        result = await self.connection.execute(query, *args)
        if self.timeout and "statement_timeout='20s'" in query:
            await self.connection.execute("SET LOCAL statement_timeout='25ms'")
        return result

    async def fetch(self, query, *args):
        if '::integer AS position' not in query:
            return await self.connection.fetch(query, *args)
        self.batch_calls += 1
        if self.error is not None:
            raise self.error
        if self.timeout:
            query = 'SELECT f.* FROM (' + query + ') f CROSS JOIN (SELECT pg_sleep(.2)) slow'
        rows = await self.connection.fetch(query, *args)
        return self.mutate([dict(r) for r in rows]) if self.mutate else rows

    def cursor(self, *args, **kwargs):
        self.cursor_calls += 1
        return self.connection.cursor(*args, **kwargs)


@unittest.skipUnless(os.environ.get('NATIVE_PURCHASE_TEST_DSN'), 'Disposable loopback PostgreSQL required')
class BatchedFingerprintDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        dsn = os.environ['NATIVE_PURCHASE_TEST_DSN']; local_target(dsn)
        self.controller = await asyncpg.connect(dsn, ssl=False, timeout=10, command_timeout=20)
        self.name = 'native_purchase_test_batched_' + uuid4().hex
        self.conn = None; self.created = False
        self.addAsyncCleanup(self.cleanup)
        await self.controller.execute('CREATE DATABASE ' + quoted(self.name) + ' TEMPLATE template0')
        self.created = True
        self.dsn = dsn.rsplit('/', 1)[0] + '/' + self.name
        self.conn = await asyncpg.connect(self.dsn, ssl=False, timeout=10, command_timeout=20)
        for schema in backup.SCHEMAS:
            if schema != 'public': await self.conn.execute('CREATE SCHEMA ' + quoted(schema))

    async def cleanup(self):
        try:
            if self.conn is not None: await self.conn.close(timeout=10)
            if self.created: await self.controller.execute('DROP DATABASE ' + quoted(self.name))
        finally:
            await self.controller.close(timeout=10)

    async def fixtures(self):
        await self.conn.execute('''CREATE TABLE public.stores(id text,label text);
            INSERT INTO public.stores VALUES('TEST KEEP','café Ω'),('TEST EXCLUDE','removed'),(NULL,'null identity');
            CREATE TABLE public.items(code text,label text);
            INSERT INTO public.items VALUES('TEST KEEP','🍕'),('TEST EXCLUDE','removed');
            CREATE TABLE public.activity_log(user_id text,payload jsonb);
            INSERT INTO public.activity_log VALUES('TEST KEEP','{"nested":[null,true,"ä"]}'),('TEST EXCLUDE','{}');
            CREATE TABLE public.staff_members(id uuid,label text);
            INSERT INTO public.staff_members VALUES('11111111-1111-4111-8111-111111111111','keep'),
                ('22222222-2222-4222-8222-222222222222','exclude');
            CREATE TABLE public.test_only_empty(n integer);
            CREATE TABLE public.test_only_mixed(n integer,label text,amount numeric,payload jsonb,raw bytea);
            INSERT INTO public.test_only_mixed VALUES(1,'Ω café 🍕',1.2300,'{"empty":""}','\\x00ff'),
                (1,'Ω café 🍕',1.2300,'{"empty":""}','\\x00ff'),(NULL,NULL,NULL,NULL,NULL),(2,'',0,'{}','\\x');
            CREATE TABLE public.test_only_below AS SELECT generate_series(1,2) AS n;
            CREATE TABLE public.test_only_at AS SELECT generate_series(1,3) AS n;
            CREATE TABLE public.test_only_large AS SELECT generate_series(1,250) AS n;
            CREATE TABLE public.test_only_partitioned(n integer) PARTITION BY RANGE(n);
            CREATE TABLE public.test_only_partition PARTITION OF public.test_only_partitioned FOR VALUES FROM (0) TO (10);
            INSERT INTO public.test_only_partitioned VALUES(2),(1),(1);
            CREATE MATERIALIZED VIEW public.test_only_materialized AS SELECT * FROM public.test_only_mixed;
            CREATE SEQUENCE public.test_only_sequence START 7;
            SELECT nextval('public.test_only_sequence');''')

    async def relations(self):
        return await self.conn.fetch('''SELECT n.nspname,c.relname,c.relkind::text AS kind FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[])
            AND c.relkind IN ('r','p','m','S') ORDER BY 1,2''', list(backup.SCHEMAS))

    async def test_original_projection_oracle_exclusions_and_chunk_boundaries(self):
        await self.fixtures()
        baseline = await preservation.original_columns(self.conn)
        excluded = {('public','stores'): ('id', ['TEST EXCLUDE']),
                    ('public','items'): ('code', 'TEST EXCLUDE'),
                    ('public','activity_log'): ('user_id', 'TEST EXCLUDE'),
                    ('public','staff_members'): ('id', '22222222-2222-4222-8222-222222222222')}
        async with readonly_snapshot(self.conn):
            for size in (1, 2, 4):
                for count in sorted({max(1,size-1), size, size+1, len(baseline)}):
                    selected = dict(list(baseline.items())[:count])
                    exclusions = {k:v for k,v in excluded.items() if k in selected}
                    with self.subTest(size=size, count=count):
                        expected = await _oracle_preservation(self.conn, selected, exclude_synthetic=exclusions)
                        actual = await preservation.fingerprints_batched(self.conn, selected,
                            exclude_synthetic=exclusions, chunk_size=size)
                        self.assertEqual(actual, expected)
            self.assertEqual(await preservation.fingerprints_batched(self.conn, {}), {})
        for exclusions in ({('public','stores'): ('label','bad')},
                           {('public','staff_members'): ('id','NOT A UUID')},
                           {('public','stores'): ('id',['same','same'])}):
            with self.subTest(exclusions=exclusions):
                for function in (_oracle_preservation, preservation.fingerprints_batched):
                    with self.assertRaises(ValueError): await function(self.conn,baseline,exclude_synthetic=exclusions)

    async def test_backup_oracle_fallback_sequences_and_path_counters(self):
        await self.fixtures()
        async def measured(function, **kwargs):
            diagnostics = backup.ExportDiagnostics()
            token = backup.EXPORT_CONTROL.set(backup.ExportControl(diagnostics))
            try: return await function(self.conn, **kwargs), diagnostics.report()['fingerprintPaths']
            finally: backup.EXPORT_CONTROL.reset(token)
        with patch.object(backup, 'MAX_FINGERPRINT_AGGREGATE_BYTES', 3 * 65):
            async with readonly_snapshot(self.conn):
                for kwargs in ({}, {'server_aggregation':False}, {'row_hashes':False}):
                    with self.subTest(options=kwargs):
                        expected, paths = await measured(_oracle_backup, **kwargs)
                        actual, actual_paths = await measured(backup.fingerprint_batched, **kwargs)
                        self.assertEqual(actual, expected); self.assertEqual(actual_paths, paths)
                relations = await self.relations()
                for count in (3,4,5):
                    with self.subTest(boundary=count):
                        selected = relations[:count]
                        actual = await backup.relation_fingerprints_batched(self.conn, selected)
                        for relation in selected:
                            name = relation['nspname'] + '.' + relation['relname']
                            q = quoted(relation['nspname']) + '.' + quoted(relation['relname'])
                            self.assertEqual(actual[name], {**await _oracle_backup_relation(self.conn,q,relation['kind']), 'kind':relation['kind']})

    async def test_late_rows_and_original_columns_detect_drift(self):
        await self.conn.execute('CREATE TABLE public.test_only_values(n integer); INSERT INTO public.test_only_values VALUES(1)')
        baseline = await preservation.original_columns(self.conn)
        before = await preservation.fingerprints_batched(self.conn, baseline)
        await self.conn.execute("ALTER TABLE public.test_only_values ADD COLUMN extra text DEFAULT 'TEST ONLY new field'")
        self.assertEqual(await preservation.fingerprints_batched(self.conn, baseline), before)
        await self.conn.execute('UPDATE public.test_only_values SET n=2')
        self.assertNotEqual(await preservation.fingerprints_batched(self.conn, baseline), before)
        self.assertEqual(await preservation.fingerprints_batched(self.conn, baseline), await _oracle_preservation(self.conn,baseline))
        for command in ('ALTER TABLE public.test_only_values ALTER COLUMN n TYPE bigint',
                        'ALTER TABLE public.test_only_values DROP COLUMN n',
                        'DROP TABLE public.test_only_values'):
            with self.subTest(command=command):
                await self.conn.execute(command)
                for function in (_oracle_preservation, preservation.fingerprints_batched):
                    with self.assertRaises(ValueError): await function(self.conn, baseline)

    async def test_missing_duplicate_extra_malformed_positions_refuse_without_fallback(self):
        await self.fixtures()
        baseline = await preservation.original_columns(self.conn)
        relations = [r for r in await self.relations() if r['kind'] != 'S']
        mutations = {
            'missing': lambda rows: rows[1:],
            'duplicate': lambda rows: rows + [rows[0]],
            'extra': lambda rows: rows + [{**rows[0], 'position':999}],
            'boolean': lambda rows: [{**r,'position':True} for r in rows],
            'negative_count': lambda rows: [{**r,'rows':-1} for r in rows],
            'malformed_hash': lambda rows: [{**r,'sha256':'TEST ONLY invalid'} for r in rows],
        }
        for label, mutate in mutations.items():
            for family in ('original','backup'):
                conn = MutatingConnection(self.conn, mutate)
                with self.subTest(family=family, mutation=label), self.assertRaises(ValueError):
                    async with readonly_snapshot(conn):
                        if family == 'original': await preservation.fingerprints_batched(conn, baseline)
                        else: await backup.relation_fingerprints_batched(conn, relations)
                self.assertEqual(conn.cursor_calls, 0)
                self.assertEqual(await self.conn.fetchval('SELECT 1'), 1)
        # A timed-out full cursor/sequence read must retain attribution too,
        # without re-probing or trying a different relation path.
        async def failed_cursor():
            raise TimeoutError('TEST ONLY private cursor text')
            yield
        for relation in [r for r in await self.relations() if r['relname'] in ('test_only_large','test_only_sequence')]:
            conn=MutatingConnection(self.conn)
            with self.subTest(cursor_kind=relation['kind']), patch.object(backup,'MAX_FINGERPRINT_AGGREGATE_BYTES',65), \
                    patch.object(conn,'cursor',return_value=failed_cursor()) as cursor:
                with self.assertRaises(backup.BackupError) as caught:
                    async with readonly_snapshot(conn):
                        await backup.relation_fingerprints_batched(conn,[relation])
                self.assertEqual(caught.exception.failureObjects,[relation['nspname']+'.'+relation['relname']])
                self.assertEqual(preservation.private_fingerprint_timeout_details(caught.exception)['fingerprintTimeout']['family'],'backup')
                self.assertEqual(cursor.call_count,1)
                self.assertEqual(await self.conn.fetchval('SELECT 1'),1)

    async def test_timeout_fails_closed_and_recovers_same_connection(self):
        await self.fixtures()
        baseline = await preservation.original_columns(self.conn)
        relations = [r for r in await self.relations() if r['kind'] != 'S']
        for family in ('original','backup'):
            for injected in (None, TimeoutError('TEST ONLY private driver text'), asyncio.CancelledError()):
                conn = MutatingConnection(self.conn, timeout=injected is None, error=injected)
                expected_type=(asyncio.CancelledError if isinstance(injected,asyncio.CancelledError)
                    else preservation.FingerprintBatchTimeout if family=='original' else backup.BackupError)
                with self.subTest(family=family,error=type(injected).__name__), self.assertRaises(expected_type) as caught:
                    async with readonly_snapshot(conn):
                        if family == 'original': await preservation.fingerprints_batched(conn, baseline)
                        else: await backup.relation_fingerprints_batched(conn, relations)
                if isinstance(injected,asyncio.CancelledError):
                    self.assertIs(caught.exception,injected)
                else:
                    members=list(baseline)[:2] if family=='original' else [(r['nspname'],r['relname']) for r in relations[:2]]
                    self.assertEqual(caught.exception.failureObjects,['.'.join(k) for k in members])
                    self.assertEqual(error_details(caught.exception)['sqlState'],'57014' if injected is None else None)
                    self.assertNotIn('test_only',str(caught.exception))
                    self.assertNotIn('private driver text',str(caught.exception))
                self.assertEqual(conn.batch_calls,1)
                self.assertEqual(conn.cursor_calls, 0)
                self.assertEqual(await self.conn.fetchval('SELECT 1'), 1)

    async def test_new_metric_bindings_attribute_both_families(self):
        import hosted_reviewed_pars as adapter
        await self.fixtures()
        baseline = await preservation.original_columns(self.conn)
        metrics = {}; conn = MeasuredConnection(self.conn, metrics)
        with instrument_functions(par_attribution_bindings(adapter)):
            await preservation.fingerprints_batched(conn, baseline)
            async with readonly_snapshot(self.conn): await backup.fingerprint_batched(conn)
        finish(metrics)
        self.assertGreater(metrics['exclusiveGroups']['fingerprints']['queryCalls'], 0)
        self.assertLess(metrics['exclusiveGroups']['fingerprints']['queryCalls'], len(baseline))
        self.assertGreater(metrics['exclusiveGroups']['backup_fingerprints']['queryCalls'], 0)
        self.assertGreater(metrics['exclusiveGroups']['backup_catalog']['queryCalls'], 0)
        self.assertEqual(metrics['driverOperationGroups']['sequences']['cursor_next']['completed'], 1)
        self.assertNotIn('test_only',json.dumps(metrics))

    async def test_snapshot_phases_do_not_reuse_digests(self):
        await self.conn.execute('CREATE TABLE public.test_only_values(n integer); INSERT INTO public.test_only_values VALUES(1)')
        baseline = await preservation.original_columns(self.conn)
        writer = await asyncpg.connect(self.dsn, ssl=False, timeout=10, command_timeout=20)
        try:
            async with readonly_snapshot(self.conn):
                original = await preservation.fingerprints_batched(self.conn, baseline)
                full = await backup.fingerprint_batched(self.conn)
                await writer.execute('UPDATE public.test_only_values SET n=2')
                self.assertEqual(await preservation.fingerprints_batched(self.conn, baseline), original)
                self.assertEqual(await backup.fingerprint_batched(self.conn), full)
            async with readonly_snapshot(self.conn):
                self.assertNotEqual(await preservation.fingerprints_batched(self.conn, baseline), original)
                self.assertNotEqual(await backup.fingerprint_batched(self.conn), full)
                self.assertEqual(await preservation.fingerprints_batched(self.conn,baseline), await _oracle_preservation(self.conn,baseline))
        finally: await writer.close(timeout=10)
