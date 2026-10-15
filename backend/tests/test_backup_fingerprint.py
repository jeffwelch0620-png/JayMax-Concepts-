"""Bounded hash aggregation and cursor compatibility; fictional loopback data only."""
import hashlib
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import asyncpg
import hosted_backup as backup
from apply_additive_migration import local_target


class FingerprintGuards(unittest.IsolatedAsyncioTestCase):
    async def test_aggregate_errors_hold_without_retrying_a_cursor(self):
        for error in (ConnectionError('TEST ONLY private disconnect'), TimeoutError()):
            with self.subTest(error=type(error).__name__):
                conn=SimpleNamespace(fetchrow=AsyncMock(side_effect=error),cursor=MagicMock())
                with self.assertRaises(type(error)) as caught:
                    await backup.relation_fingerprint(conn,'"public"."test_only"','r')
                self.assertIs(caught.exception,error)
                conn.cursor.assert_not_called()

    async def test_full_probe_discards_partial_digest_and_streams_every_row(self):
        hashes=['a'*64,'b'*64,'b'*64,'c'*64,'d'*64]
        async def rows():
            for value in hashes:yield {'value':value}
        conn=SimpleNamespace(fetchrow=AsyncMock(return_value={'rows':3,'sha256':'TEST ONLY partial digest'}),
            cursor=MagicMock(side_effect=lambda *args,**kwargs:rows()))
        with patch.object(backup,'MAX_FINGERPRINT_AGGREGATE_BYTES',3*65):
            fact=await backup.relation_fingerprint(conn,'"public"."test_only"','r')
        self.assertEqual(conn.fetchrow.await_args.args[1],3)
        self.assertEqual(fact,{'rows':5,'sha256':hashlib.sha256(('\n'.join(hashes)+'\n').encode()).hexdigest()})
        conn.cursor.assert_called_once()


class CountingConnection:
    def __init__(self,conn):
        self.conn=conn
        self.cursors=[]
        self.aggregates=[]
    def __getattr__(self,name):return getattr(self.conn,name)
    def cursor(self,sql,**kwargs):
        self.cursors.append(sql)
        return self.conn.cursor(sql,**kwargs)
    async def fetchrow(self,sql,*args):
        if 'string_agg' in sql:self.aggregates.append(sql)
        return await self.conn.fetchrow(sql,*args)
    def clear(self):
        self.cursors.clear();self.aggregates.clear()


@unittest.skipUnless(os.environ.get('NATIVE_PURCHASE_TEST_DSN'),'Dedicated disposable PostgreSQL required')
class FingerprintDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_server_cursor_fallback_and_legacy_fingerprints_are_equivalent(self):
        control=os.environ['NATIVE_PURCHASE_TEST_DSN'];local_target(control)
        name='native_purchase_test_bfp_'+uuid4().hex
        dsn=control.rsplit('/',1)[0]+'/'+name
        settings=backup.native.disposable_connection(dsn)
        controller=await asyncpg.connect(control,ssl=False)
        conn=None;created=False
        try:
            await controller.execute('CREATE DATABASE '+backup.native.quoted(name)+' WITH TEMPLATE template0')
            created=True
            conn=await asyncpg.connect(**settings,ssl=False)
            for schema in backup.SCHEMAS:
                if schema!='public':await conn.execute('CREATE SCHEMA '+backup.native.quoted(schema))
            await conn.execute('''CREATE TABLE public.test_only_empty(label text);
                CREATE TABLE public.test_only_values(id integer,label text,amount numeric,payload jsonb,raw bytea);
                CREATE TABLE public.test_only_below(n integer);
                CREATE TABLE public.test_only_at(n integer);
                CREATE TABLE public.test_only_above(n integer);
                INSERT INTO public.test_only_below SELECT generate_series(1,2);
                INSERT INTO public.test_only_at SELECT generate_series(1,3);
                INSERT INTO public.test_only_above SELECT generate_series(1,4);
                CREATE TABLE public.test_only_partitioned(n integer) PARTITION BY RANGE(n);
                CREATE TABLE public.test_only_partition PARTITION OF public.test_only_partitioned FOR VALUES FROM (0) TO (100);
                INSERT INTO public.test_only_partitioned VALUES(3),(1),(2);
                CREATE SEQUENCE public.test_only_sequence START 7;
                SELECT nextval('public.test_only_sequence');''')
            duplicate=(2,'TEST ONLY café 🍕\r\nnext line', '1.2300', '{"empty":"","nested":[null,true,"é"]}',b'\x00\xff')
            # Preserve duplicates, SQL nulls, empty strings, multibyte UTF-8 and
            # embedded newlines. No PK deliberately: duplicate rows must count.
            from decimal import Decimal
            values=[duplicate,duplicate,(None,None,None,None,None),(1,'', '0','{}',b''),
                    (3,'TEST ONLY Z / ä / Ω','-2.500','{"null":null}',b'\r\n')]
            await conn.executemany('INSERT INTO public.test_only_values VALUES($1,$2,$3,$4,$5)',
                [(i,label,Decimal(amount) if amount is not None else None,payload,raw) for i,label,amount,payload,raw in values])
            await conn.execute('CREATE MATERIALIZED VIEW public.test_only_materialized AS SELECT * FROM public.test_only_values')
            tracked=CountingConnection(conn)
            async with backup.readonly_snapshot(conn):
                fast=await backup.fingerprint(tracked)
                self.assertEqual(len(tracked.aggregates),sum(f['kind']!='S' for f in fast['tables'].values()))
                self.assertEqual(len(tracked.cursors),1)  # Sequence byte rules stay unchanged.
                self.assertEqual(fast['tables']['public.test_only_empty']['sha256'],hashlib.sha256(b'').hexdigest())
                self.assertEqual(fast['tables']['public.test_only_values']['rows'],5)
                self.assertEqual(fast['tables']['public.test_only_sequence']['rows'],1)
                tracked.clear()
                streamed=await backup.fingerprint(tracked,server_aggregation=False)
                self.assertEqual(fast,streamed)
                self.assertFalse(tracked.aggregates)
                tracked.clear()
                with patch.object(backup,'MAX_FINGERPRINT_AGGREGATE_BYTES',3*65):
                    bounded=await backup.fingerprint(tracked)
                self.assertEqual(bounded,streamed)
                streamed_sql='\n'.join(tracked.cursors)
                self.assertNotIn('"test_only_below"',streamed_sql)
                self.assertIn('"test_only_at"',streamed_sql)
                self.assertIn('"test_only_above"',streamed_sql)
                tracked.clear()
                legacy=await backup.fingerprint(tracked,row_hashes=False)
                self.assertFalse(tracked.aggregates)
                legacy_streamed=await backup.fingerprint(tracked,row_hashes=False,server_aggregation=False)
                self.assertEqual(legacy,legacy_streamed)
                self.assertNotEqual(legacy['tables']['public.test_only_values']['sha256'],fast['tables']['public.test_only_values']['sha256'])
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM public.test_only_values'),5)
        finally:
            if conn is not None:await conn.close()
            if created:await controller.execute('DROP DATABASE '+backup.native.quoted(name)+' WITH (FORCE)')
            await controller.close()
