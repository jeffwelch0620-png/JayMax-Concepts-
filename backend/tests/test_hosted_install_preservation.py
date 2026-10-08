"""Original-row preservation across timezone, additive DDL and ledger changes."""
import asyncio
import os
import unittest
from urllib.parse import urlparse
from uuid import uuid4
import asyncpg
import hosted_test_trial as hosted
import hosted_install_preservation as preservation


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable local PostgreSQL required')
class PreservationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        dsn = os.environ['NATIVE_PURCHASE_TEST_DSN'];uri=urlparse(dsn)
        if uri.hostname!='127.0.0.1' or not uri.path.startswith('/native_purchase_test_') or uri.query or uri.fragment:
            raise RuntimeError('Local preservation test requires disposable loopback control')
        self.admin=await asyncpg.connect(dsn);self.name='native_purchase_test_'+uuid4().hex
        await self.admin.execute('CREATE DATABASE '+self.name)
        self.dsn=dsn.rsplit('/',1)[0]+'/'+self.name
        self.conn=await asyncpg.connect(self.dsn)
        await self.conn.execute('''CREATE TABLE public.food(id int,amount numeric(12,4),received_at timestamptz,note text);
            INSERT INTO public.food VALUES(1,2.5,'2026-10-08T04:00:00Z','keep raw'),(1,2.5,'2026-10-08T04:00:00Z','keep raw');
            CREATE SCHEMA supabase_migrations;
            CREATE TABLE supabase_migrations.schema_migrations(version text PRIMARY KEY,name text,statements text[]);
            INSERT INTO supabase_migrations.schema_migrations VALUES('20260929135736','original',ARRAY['SELECT 1;']);''')
        self.columns=await preservation.original_columns(self.conn)

    async def asyncTearDown(self):
        await self.conn.close();await self.admin.execute('DROP DATABASE '+self.name);await self.admin.close()

    async def test_timezone_normalization_does_not_change_session_timezone(self):
        await self.conn.execute("SET TIME ZONE 'UTC'")
        original=await hosted.row_fingerprints(self.conn)
        await self.conn.execute("SET TIME ZONE 'America/New_York'")
        self.assertEqual(await hosted.row_fingerprints(self.conn),original)
        self.assertEqual(await preservation.fingerprints(self.conn,self.columns),original)
        self.assertEqual(await self.conn.fetchval("SHOW timezone"),'America/New_York')

    async def test_additive_columns_preserve_original_projection_and_original_changes_are_detected(self):
        original=await preservation.fingerprints(self.conn,self.columns)
        await self.conn.execute("ALTER TABLE public.food ADD COLUMN control_number text DEFAULT 'new';")
        self.assertEqual(await preservation.fingerprints(self.conn,self.columns),original)
        self.assertNotEqual(await hosted.row_fingerprints(self.conn),original)
        await self.conn.execute("UPDATE public.food SET note='changed' WHERE id=1")
        self.assertNotEqual(await preservation.fingerprints(self.conn,self.columns),original)

    async def test_same_values_with_different_multiplicity_are_detected(self):
        original=await preservation.fingerprints(self.conn,self.columns)
        await self.conn.execute('DELETE FROM public.food WHERE ctid=(SELECT min(ctid) FROM public.food)')
        after=await preservation.fingerprints(self.conn,self.columns)
        self.assertEqual(after['public.food']['rows'],1)
        self.assertNotEqual(after['public.food']['sha256'],original['public.food']['sha256'])

    async def test_removed_retyped_and_missing_tables_hold(self):
        for sql in ('ALTER TABLE public.food DROP COLUMN note',
                    'ALTER TABLE public.food ALTER COLUMN amount TYPE numeric(16,4)',
                    'DROP TABLE public.food'):
            transaction=self.conn.transaction(isolation='repeatable_read');await transaction.start()
            try:
                await self.conn.execute(sql)
                with self.assertRaises(ValueError):await preservation.fingerprints(self.conn,self.columns)
            finally:await transaction.rollback()

    async def test_identifier_quoting_and_changed_columns_are_explicit(self):
        await self.conn.execute('CREATE TABLE public."odd.table"("a\"\"b" text); INSERT INTO public."odd.table" VALUES(\'retained\')')
        columns=await preservation.original_columns(self.conn)
        before=await preservation.fingerprints(self.conn,columns)
        await self.conn.execute('ALTER TABLE public."odd.table" ADD COLUMN fresh text')
        self.assertEqual(await preservation.fingerprints(self.conn,columns),before)
        corrupted=dict(columns);corrupted[('public','food')]=columns[('public','food')]*2
        with self.assertRaises(ValueError):await preservation.fingerprints(self.conn,corrupted)

    async def test_old_migration_statement_changes_cannot_hide_behind_same_version_and_name(self):
        original=await preservation.ledger_fingerprints(self.conn)
        await self.conn.execute("UPDATE supabase_migrations.schema_migrations SET statements=ARRAY['SELECT 2;']")
        self.assertEqual(set(await preservation.ledger_fingerprints(self.conn)),set(original))
        self.assertNotEqual(await preservation.ledger_fingerprints(self.conn),original)

    async def test_original_table_locks_block_writes_only_until_commit(self):
        with self.assertRaises(ValueError):await preservation.lock_original_tables(self.conn,self.columns)
        other=await asyncpg.connect(self.dsn)
        transaction=self.conn.transaction();await transaction.start()
        try:
            await preservation.lock_original_tables(self.conn,self.columns)
            await other.execute("SET lock_timeout='100ms'")
            with self.assertRaises(asyncpg.LockNotAvailableError):await other.execute('INSERT INTO public.food(id) VALUES(2)')
            await transaction.commit();transaction=None
            await other.execute('INSERT INTO public.food(id) VALUES(2)')
        finally:
            if transaction:await transaction.rollback()
            await other.close()

    async def test_only_exact_new_synthetic_identities_can_be_excluded_and_old_changes_still_detected(self):
        await self.conn.execute("CREATE TABLE public.stores(id text,name text); INSERT INTO public.stores VALUES('original','Keep original')")
        columns=await preservation.original_columns(self.conn)
        before=await preservation.fingerprints(self.conn,columns)
        await self.conn.execute("INSERT INTO public.stores VALUES('synthetic_new','Invented test')")
        exclusion={('public','stores'):('id','synthetic_new')}
        self.assertEqual(await preservation.fingerprints(self.conn,columns,exclude_synthetic=exclusion),before)
        await self.conn.execute("INSERT INTO public.stores VALUES('synthetic_second','Invented second test')")
        self.assertEqual(await preservation.fingerprints(self.conn,columns,exclude_synthetic={('public','stores'):('id',['synthetic_new','synthetic_second'])}),before)
        await self.conn.execute("UPDATE public.stores SET name='Changed original' WHERE id='original'")
        self.assertNotEqual(await preservation.fingerprints(self.conn,columns,exclude_synthetic=exclusion),before)
        for bad in ({('public','food'):('note','keep raw')},{('public','stores'):('id','')},{('public','stores'):('name','Invented test')}):
            with self.assertRaises(ValueError):await preservation.fingerprints(self.conn,columns,exclude_synthetic=bad)
