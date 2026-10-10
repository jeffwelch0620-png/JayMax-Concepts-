"""Actual isolated pool constructors and deliberate original-singleton return."""
from uuid import uuid4
from unittest.mock import AsyncMock, patch
import connection_transition as startup
import transition_permissions as permissions
import db_pg
import db_auxiliary
import runtime_permissions as runtime
import auxiliary_permissions as auxiliary
import hosted_install_preservation as preservation
import schema_reconciliation as reconciliation
import test_transition_permission_catalog as fixture


class PairedStartupTests(fixture.OverlapCatalogTests):
    async def test_actual_pair_reconnect_privilege_denial_partial_cleanup_and_original_return(self):
        columns = await preservation.original_columns(self.conn)
        rows = await preservation.fingerprints(self.conn, columns)
        ledger = await preservation.ledger_fingerprints(self.conn)
        catalog = (await reconciliation.capture(self.conn))['catalog']
        globals_before = (db_pg._pool, db_auxiliary._pool, db_pg._retry_task, db_auxiliary._retry_task)
        for phase in ('original', 'replacement'):
            urls = {kind: self.url(kind, phase) for kind in permissions.PROFILES}
            revision = startup.bind_revision(self.context, urls, client_id='local_registered_backend', revision_id=str(uuid4()), reference='local')
            async with await startup.prepare_pair(revision, urls) as owned:
                self.assertFalse(owned.receipt()['globalPoolsChanged'])
                for kind in permissions.PROFILES:
                    pool = getattr(owned, kind)
                    # Two concurrent physical connections must run the initializer.
                    async with pool.acquire() as one, pool.acquire() as two:
                        expected_role = self.pairs[kind][phase]['name']
                        for conn in (one, two):
                            self.assertEqual(await conn.fetchval('SELECT session_user'), expected_role)
                            self.assertEqual(await conn.fetchval('SELECT $1::jsonb', {'invented': [1, 2]}), {'invented': [1, 2]})
                        if kind == 'accounts':
                            for query in ('SELECT count(*) FROM public.staff_pins', 'SELECT count(*) FROM purchasing.posting_batches'):
                                with self.assertRaises(fixture.asyncpg.InsufficientPrivilegeError):
                                    await one.fetchval(query)
                    await pool.expire_connections()
                    async with pool.acquire() as conn:
                        self.assertEqual(await conn.fetchval('SELECT session_user'), self.pairs[kind][phase]['name'])
            self.assertTrue(owned.receipt()['ownedPoolsClosed'])
        # A failed account peer closes the actual primary candidate, not a global.
        urls = {kind: self.url(kind) for kind in permissions.PROFILES}
        revision = startup.bind_revision(self.context, urls, client_id='local_registered_backend', revision_id=str(uuid4()), reference='local')
        with patch.object(db_auxiliary, '_try_connect', AsyncMock(return_value=None)):
            with self.assertRaises(permissions.TransitionError):
                await startup.prepare_pair(revision, urls)
        role_names = [value['name'] for pair in self.pairs.values() for value in pair.values()]
        self.assertEqual(await self.admin.fetchval('SELECT count(*) FROM pg_stat_activity WHERE usename=ANY($1::text[])', role_names), 0)
        self.assertEqual((db_pg._pool, db_auxiliary._pool, db_pg._retry_task, db_auxiliary._retry_task), globals_before)
        self.assertEqual((await reconciliation.capture(self.conn))['catalog'], catalog)
        self.assertEqual(await preservation.fingerprints(self.conn, columns), rows)
        self.assertEqual(await preservation.ledger_fingerprints(self.conn), ledger)
        # All overlap probes are closed before restoring singleton policies.
        for kind, pair in self.pairs.items():
            tables = runtime.PUBLIC if kind == 'inventory' else {name: auxiliary.VERBS for name in auxiliary.TABLES}
            prefix = 'runtime_candidate_' if kind == 'inventory' else 'auxiliary_candidate_'
            for table, verbs in tables.items():
                for verb in verbs:
                    await self.conn.execute('ALTER POLICY ' + prefix + verb.lower() + ' ON public.' + table + ' TO ' + pair['original']['name'])
        original_pools = []
        try:
            for kind, module in (('inventory', db_pg), ('accounts', db_auxiliary)):
                pool = await module._try_connect(self.url(kind, 'original'))
                self.assertIsNotNone(pool); original_pools.append(pool)
                async with pool.acquire() as conn:
                    report = (await runtime.inspect(conn, self.pairs[kind]['original']['name'])
                              if kind == 'inventory' else await auxiliary.inspect(conn))
                    self.assertEqual(report['status'], 'passed_local_candidate' if kind == 'inventory' else 'passed', report)
                    self.assertEqual(report['policyMode'], 'single_role')
            # New roles are disabled only after original singleton verification.
            for kind in permissions.PROFILES:
                await self.admin.execute('ALTER ROLE ' + self.pairs[kind]['replacement']['name'] + ' NOLOGIN')
                self.assertFalse(await self.admin.fetchval('SELECT rolcanlogin FROM pg_roles WHERE oid=$1', self.pairs[kind]['replacement']['oid']))
        finally:
            for pool in reversed(original_pools):
                await startup.close_owned(pool)
        self.assertEqual(await preservation.fingerprints(self.conn, columns), rows)
        self.assertEqual(await preservation.ledger_fingerprints(self.conn), ledger)
        self.assertEqual(await self.admin.fetchval('SELECT count(*) FROM pg_stat_activity WHERE usename=ANY($1::text[])', role_names), 0)
