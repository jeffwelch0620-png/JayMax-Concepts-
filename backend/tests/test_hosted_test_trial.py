"""Offline guards for the explicitly designated rollback-only hosted trial."""
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch
from contextlib import asynccontextmanager
import os
from uuid import uuid4
from urllib.parse import urlparse
import asyncpg
import hosted_test_trial as hosted
import deployment_readiness as readiness
from managed_development import DevelopmentTargetError


class HostedTrialGuards(unittest.TestCase):
    def config(self):
        return {'DATABASE_URL':'postgresql://postgres:synthetic-secret@db.'+'a'*20+'.supabase.co:5432/postgres','USE_PG':'true'}

    def test_explicit_project_identity_and_held_native_flags_required(self):
        self.assertEqual(hosted.designated_target(self.config(),'a'*20)['projectRef'],'a'*20)
        for expected, config in (('',self.config()),('b'*20,self.config()),('a'*20,self.config()|{'USE_PG':'false'}),
                                 ('a'*20,self.config()|{'PREP_BATCHES_ENABLED':'true'})):
            with self.assertRaises(DevelopmentTargetError) as error: hosted.designated_target(config,expected)
            self.assertNotIn('synthetic-secret',str(error.exception))

    def test_all_reviewed_migrations_have_one_rollback_safe_outer_transaction(self):
        self.assertEqual(len(readiness.MIGRATIONS),29)
        for filename in readiness.MIGRATIONS:
            body = hosted.migration_body((readiness.ROOT/'migrations'/filename).read_bytes())
            self.assertTrue(body.strip(),filename)

    def test_literals_dollar_bodies_comments_and_crlf_do_not_escape_transaction(self):
        body = "\r\n-- COMMIT;\r\nDO $x$ BEGIN PERFORM 'COMMIT;'; END $x$;\r\n/* nested /* COMMIT; */ comment */ SELECT 'literal\r\nROLLBACK;', E'escaped\\\' COMMIT;', \"COMMIT;\";\r\n"
        raw = ('-- outer\r\nBEGIN;'+body+'COMMIT; -- trailing\r\n').encode()
        self.assertEqual(hosted.migration_body(raw),body)
        for text in ('BEGIN; SELECT 1; COMMIT; SELECT 2; COMMIT;', 'BEGIN; ROLLBACK; SELECT 1; COMMIT;',
                     'BEGIN; SAVEPOINT x; SELECT 1; COMMIT;', 'SELECT 1;', 'BEGIN; SELECT 1; COMMIT; SELECT 2',
                     'BEGIN; SELECT $x$unclosed; COMMIT;', "BEGIN; SELECT 'unclosed; COMMIT;"):
            with self.assertRaises(ValueError): hosted.migration_body(text.encode())


class TrialPoolTests(unittest.IsolatedAsyncioTestCase):
    async def test_lost_transaction_and_concurrent_use_refused(self):
        conn = AsyncMock(); conn.is_in_transaction = lambda: True
        pool = hosted.TrialPool(conn)
        async with pool.acquire() as current:
            self.assertIs(current,conn)
            with self.assertRaises(RuntimeError):
                async with pool.acquire(): pass
        conn.is_in_transaction = lambda: False
        with self.assertRaises(RuntimeError):
            async with pool.acquire(): pass

    async def test_only_reviewed_timestamp_triggers_allowed(self):
        conn = AsyncMock()
        conn.fetch.return_value = [dict(prosrc='begin new.updated_at = now(); return new; end',lanname='plpgsql',prosecdef=False)]
        self.assertEqual(await hosted.verify_baseline_triggers(conn),1)
        for change in ({'prosecdef':True},{'prosrc':"begin perform net.http_post('private'); return new; end"}, {'lanname':'sql'}):
            conn.fetch.return_value = [dict(prosrc='begin new.updated_at = now(); return new; end',lanname='plpgsql',prosecdef=False)|change]
            with self.assertRaises(ValueError): await hosted.verify_baseline_triggers(conn)

    async def test_backup_refuses_workspace_before_process_launch(self):
        with patch.object(hosted.subprocess,'run') as run:
            with self.assertRaises(ValueError): hosted.private_backup('unused','unused',readiness.ROOT/'private-backup')
            run.assert_not_called()

    async def test_failed_role_selection_cannot_count_as_a_denied_select(self):
        conn = AsyncMock()
        @asynccontextmanager
        async def transaction(): yield
        conn.transaction = transaction
        conn.execute.side_effect = asyncpg.InsufficientPrivilegeError('Invented SET ROLE refusal')
        with self.assertRaises(asyncpg.InsufficientPrivilegeError): await hosted.client_query_denied(conn,'anon')
        conn.fetchval.assert_not_awaited()
        conn.execute.side_effect = None
        conn.fetchval.side_effect = ['anon',asyncpg.InsufficientPrivilegeError('Invented denied SELECT')]
        self.assertTrue(await hosted.client_query_denied(conn,'anon'))


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable local PostgreSQL required')
class RollbackWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_native_sql_and_synthetic_workflow_are_rolled_back(self):
        dsn = os.environ['NATIVE_PURCHASE_TEST_DSN']; uri = urlparse(dsn)
        if uri.hostname != '127.0.0.1' or not uri.path.startswith('/native_purchase_test_') or uri.query or uri.fragment:
            raise RuntimeError('Local harness refuses non-disposable control')
        admin = await asyncpg.connect(dsn); name = 'native_purchase_test_'+uuid4().hex; conn = None; created_anon = False
        try:
            if not await admin.fetchval("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon')"):
                await admin.execute('CREATE ROLE anon NOLOGIN'); created_anon = True
            await admin.execute('CREATE DATABASE '+name)
            conn = await asyncpg.connect(dsn.rsplit('/',1)[0]+'/'+name)
            await conn.execute((readiness.ROOT/'supabase/schema.sql').read_bytes().decode())
            self.assertEqual(await hosted.verify_baseline_triggers(conn),5)
            original = await hosted.row_fingerprints(conn)
            transaction = conn.transaction(isolation='repeatable_read'); await transaction.start()
            try:
                for filename in readiness.MIGRATIONS:
                    await conn.execute(hosted.migration_body((readiness.ROOT/'migrations'/filename).read_bytes()))
                with patch.dict(os.environ,{'USE_PG':'true',**{name+'_ENABLED':'true' for name in readiness.FEATURES}}):
                    result = await hosted.synthetic_workflow(conn)
                    self.assertEqual(result['status'],'passed')
            finally: await transaction.rollback()
            self.assertFalse(await conn.fetchval("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='purchasing')"))
            self.assertFalse(await conn.fetchval("SELECT EXISTS(SELECT 1 FROM public.stores WHERE id LIKE 'hosted_trial_%')"))
            self.assertEqual(await hosted.row_fingerprints(conn),original)
        finally:
            if conn: await conn.close()
            await admin.execute('DROP DATABASE IF EXISTS '+name)
            if created_anon: await admin.execute('DROP ROLE anon')
            await admin.close()
