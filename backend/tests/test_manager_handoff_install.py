"""Fictional local receiving installation, real restricted LOGIN and recovery."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import asyncpg
from cryptography.fernet import Fernet
import hosted_backup as old_backup
import manager_handoff as handoff
import manager_handoff_install as install
import manager_handoff_recovery as recovery
from test_native_purchases import PurchaseIntegrationTests
from test_manager_handoff import body


class InstallGuards(unittest.IsolatedAsyncioTestCase):
    def test_source_reference_and_three_explicit_nontransactional_payloads(self):
        m = install.reference(); values = install.payloads('fictional_runtime')
        self.assertEqual(len(values), 3)
        self.assertNotIn('\nCOMMIT;', values[0][1]); self.assertNotIn('\nBEGIN;', values[0][1])
        self.assertEqual(values[1][1].count('CREATE POLICY '), 4)
        self.assertNotIn('GRANT ALL', values[1][1]); self.assertNotIn('CREATE ROLE', str(values))
        self.assertEqual(len(m['proposedRuntimePrivileges']), 4)

    async def test_remote_control_and_url_options_refused_before_connect(self):
        with patch.object(asyncpg, 'connect', new_callable=AsyncMock) as connect:
            for url in ('postgresql://owner@db.example.invalid/postgres',
                        'postgresql://owner@127.0.0.1:5544/postgres',
                        'postgresql://owner@127.0.0.1:5544/native_purchase_test_control',
                        'postgresql://owner@127.0.0.1:5544/native_purchase_test_x?sslmode=disable',
                        'postgresql://owner@localhost:5544/native_purchase_test_x'):
                with self.subTest(url=url), self.assertRaises(recovery.Held):
                    await recovery.connect(url)
            connect.assert_not_awaited()

    async def test_invalid_roles_and_versions_refuse_without_network(self):
        url = 'postgresql://owner@127.0.0.1:5544/native_purchase_test_x'
        with patch.object(recovery, 'connect', new_callable=AsyncMock) as connect:
            for roles, versions in ((('owner', 'accounts'), ['20991025000001'] * 3),
                                    (('bad;role', 'accounts'), ['20991025000001'] * 3),
                                    (('runtime', 'accounts'), ['20991025000001'] * 3)):
                with self.subTest(roles=roles), self.assertRaises(install.Held):
                    await install.prepare(url, *roles, versions)
            connect.assert_not_awaited()

    def test_authenticated_profile_tamper_wrong_key_database_and_duplicate_keys_hold(self):
        key = Fernet.generate_key(); raw = b'PGDMP TEST ONLY'
        m = dict(format=recovery.FORMAT, schemas=list(recovery.SCHEMAS), sourceDatabase='fictional', postgresMajor=17)
        envelope = recovery.seal(m, raw, key)
        self.assertEqual(recovery.open_envelope(envelope, key, 'fictional')[1], raw)
        for blob, k, db in ((envelope, Fernet.generate_key(), 'fictional'),
                            (envelope[:-3] + b'bad', key, 'fictional'), (envelope, key, 'other'),
                            (recovery.seal(m | {'schemas': list(recovery.LEGACY_SCHEMAS)}, raw, key), key, 'fictional'),
                            (Fernet(key).encrypt(b'{"manifest":{},"manifest":{}}'), key, 'fictional')):
            with self.subTest(database=db), self.assertRaises(recovery.Held):
                recovery.open_envelope(blob, k, db)

    def test_import_does_not_widen_old_six_schema_archive_reader(self):
        self.assertEqual(old_backup.SCHEMAS, recovery.LEGACY_SCHEMAS)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); key = Fernet.generate_key(); raw = b'PGDMP TEST ONLY legacy'
            m = dict(format=old_backup.FORMAT, projectRef='fictional', schemas=list(old_backup.SCHEMAS),
                     archiveSha256=recovery.digest(raw), archiveBytes=len(raw))
            import base64
            (root / 'key').write_bytes(key)
            (root / 'archive').write_bytes(Fernet(key).encrypt(json.dumps({'manifest': m, 'archive': base64.b64encode(raw).decode()}).encode()))
            self.assertEqual(old_backup.open_backup(root/'archive', root/'key', 'fictional')[1], raw)


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable loopback PostgreSQL required')
class InstallDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await PurchaseIntegrationTests.asyncSetUp(self)
        self.url = os.environ['NATIVE_PURCHASE_TEST_DSN'].rsplit('/', 1)[0] + '/' + self.db
        tag = uuid4().hex[:10]; self.runtime = 'handoff_runtime_' + tag; self.accounts = 'handoff_accounts_' + tag
        self.roles = [self.runtime, self.accounts]; self.restores = []
        self.versions = ['20991025000001', '20991025000002', '20991025000003']
        async with self.pool.acquire() as c:
            for schema in ('actual_inventory', 'prep_inventory', 'integrations', 'supabase_migrations'):
                await c.execute('CREATE SCHEMA ' + schema)
            await c.execute('''CREATE TABLE supabase_migrations.schema_migrations(version text PRIMARY KEY,name text NOT NULL,statements text[] NOT NULL);
                INSERT INTO supabase_migrations.schema_migrations VALUES('19990101000001','TEST ONLY baseline',ARRAY['SELECT 1;']);
                INSERT INTO public.app_users(id,email,password_hash,role,locations)
                VALUES('usr_owner','owner@example.invalid','not-a-password','owner','{}');''')
            for role in self.roles:
                await c.execute('CREATE ROLE ' + role + " LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD 'TEST_ONLY_LOCAL_4826'")
                await c.execute('GRANT USAGE ON SCHEMA public TO ' + role)
            await c.execute('GRANT SELECT(id,active) ON public.stores TO ' + self.runtime)
            await c.execute('CREATE POLICY test_handoff_store ON public.stores FOR SELECT TO ' + self.runtime + ' USING(true)')
            await c.execute('GRANT SELECT(id,role,locations) ON public.app_users TO ' + self.accounts)
            await c.execute('CREATE POLICY test_handoff_accounts ON public.app_users FOR SELECT TO ' + self.accounts + ' USING(true)')

    async def asyncTearDown(self):
        for db in self.restores:
            await self.admin.execute('DROP DATABASE ' + db)
        await PurchaseIntegrationTests.asyncTearDown(self)
        control = await asyncpg.connect(os.environ['NATIVE_PURCHASE_TEST_DSN'])
        try:
            for role in self.roles:
                await control.execute('DROP ROLE ' + role)
        finally:
            await control.close()

    def role_url(self, role, database=None, password='TEST_ONLY_LOCAL_4826'):
        parsed = urlsplit(self.url)
        return urlunsplit((parsed.scheme, role + ':' + password + '@' + parsed.hostname + ':' + str(parsed.port),
                           '/' + (database or self.db), '', ''))

    async def plan(self):
        return await install.prepare(self.url, self.runtime, self.accounts, self.versions)

    async def installed(self):
        p = await self.plan(); result = await install.apply(self.url, p, install.sha(p))
        self.assertEqual(result['ledgerEntries'], 3); return p

    async def test_atomic_three_payloads_and_actual_restricted_logins(self):
        p = await self.installed()
        result = await install.qualify(self.role_url(self.runtime), self.role_url(self.accounts))
        self.assertTrue(result['actualRuntimeLogin']); self.assertTrue(result['actualAccountsLogin'])
        self.assertFalse(result['fallbackUsed']); self.assertFalse(result['baselineNativeAndAccountQualificationIncluded'])
        self.assertEqual((await install.reconcile(self.url, p, install.sha(p)))['outcome'], 'installed')
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM supabase_migrations.schema_migrations'), 4)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM operations.handoff_notes'), 0)
        # Actual SCRAM LOGIN failure, not a SET ROLE permission simulation.
        with self.assertRaises(asyncpg.InvalidPasswordError):
            await recovery.connect(self.role_url(self.runtime, password='TEST_ONLY_WRONG'))

    async def test_namespace_version_source_and_changed_baseline_refuse(self):
        p = await self.plan()
        for field in ('sourceHashes', 'target'):
            changed = copy.deepcopy(p); changed[field]['TEST_ONLY'] = 'changed'
            with self.subTest(field=field), self.assertRaises(install.Held):
                await install.apply(self.url, changed, install.sha(changed))
        async with self.pool.acquire() as c:
            await c.execute("UPDATE public.items SET name='TEST ONLY later change' WHERE code='test_food'")
        with self.assertRaises(install.Held): await install.apply(self.url, p, install.sha(p))
        p = await self.plan(); await install.apply(self.url, p, install.sha(p))
        with self.assertRaises(install.Held): await self.plan()

    async def test_ledger_late_failure_rolls_back_schema_permissions_and_settings(self):
        async with self.pool.acquire() as c:
            await c.execute("""CREATE FUNCTION public.test_handoff_ledger_failure() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN IF NEW.name='manager_handoff_settings' THEN RAISE EXCEPTION 'TEST ONLY late ledger failure'; END IF; RETURN NEW; END $$;
                CREATE TRIGGER test_handoff_ledger BEFORE INSERT ON supabase_migrations.schema_migrations
                FOR EACH ROW EXECUTE FUNCTION public.test_handoff_ledger_failure();""")
        p = await self.plan()
        with self.assertRaises(asyncpg.RaiseError): await install.apply(self.url, p, install.sha(p))
        async with self.pool.acquire() as c:
            self.assertIsNone(await c.fetchval("SELECT to_regnamespace('operations')"))
            self.assertEqual(await install.ledger(c), p['baseline']['ledger'])
        self.assertEqual((await install.reconcile(self.url, p, install.sha(p)))['outcome'], 'not_installed')

    async def test_unknown_commit_requires_readonly_reconciliation_and_no_retry(self):
        p = await self.plan()
        async def lost(tx):
            await tx.commit(); raise ConnectionResetError('TEST ONLY dropped acknowledgement')
        with patch.object(install, '_commit', side_effect=lost), self.assertRaises(install.Unknown):
            await install.apply(self.url, p, install.sha(p))
        result = await install.reconcile(self.url, p, install.sha(p))
        self.assertEqual(result, {'outcome': 'installed', 'retryAuthorized': False})
        with self.assertRaises(install.Held): await install.apply(self.url, p, install.sha(p))

    async def test_policy_privilege_guard_and_owner_drift_hold(self):
        await self.installed()
        changes = [
            ('GRANT DELETE ON operations.handoff_notes TO ' + self.runtime, 'REVOKE DELETE ON operations.handoff_notes FROM ' + self.runtime),
            ("ALTER POLICY handoff_backend_v1 ON operations.handoff_notes USING(false)", "ALTER POLICY handoff_backend_v1 ON operations.handoff_notes USING(true)"),
            ('ALTER TABLE operations.handoff_notes DISABLE TRIGGER handoff_notes_no_truncate', 'ALTER TABLE operations.handoff_notes ENABLE TRIGGER handoff_notes_no_truncate'),
            ('ALTER ROLE ' + self.runtime + ' BYPASSRLS', 'ALTER ROLE ' + self.runtime + ' NOBYPASSRLS'),
            ('GRANT USAGE ON SCHEMA operations TO ' + self.accounts, 'REVOKE USAGE ON SCHEMA operations FROM ' + self.accounts),
            ('GRANT SELECT(summary) ON operations.handoff_note_revisions TO ' + self.runtime + ' WITH GRANT OPTION', 'REVOKE GRANT OPTION FOR SELECT(summary) ON operations.handoff_note_revisions FROM ' + self.runtime),
            ('GRANT SELECT(summary) ON operations.handoff_note_revisions TO PUBLIC', 'REVOKE SELECT(summary) ON operations.handoff_note_revisions FROM PUBLIC')]
        for change, undo in changes:
            with self.subTest(change=change):
                async with self.pool.acquire() as c: await c.execute(change)
                try:
                    with self.assertRaises(install.Held):
                        await install.qualify(self.role_url(self.runtime), self.role_url(self.accounts))
                finally:
                    async with self.pool.acquire() as c: await c.execute(undo)
        with self.assertRaises(install.Held): await install.qualify(self.url, self.role_url(self.accounts))

    async def test_encrypted_seven_schema_restore_preserves_history_acl_guards_and_exact_replay(self):
        await self.installed()
        rp = await asyncpg.create_pool(self.role_url(self.runtime), min_size=1, max_size=1)
        original = handoff.Command(**body()); key = uuid4()
        try:
            await handoff.execute(rp, 'berts', 'usr_owner', original, key, 0)
            await handoff.execute(rp, 'berts', 'usr_owner', handoff.Command(**(body(note_id=str(original.note_id)) | {'action': 'submit'})), uuid4(), 1)
            correction = original.model_dump() | {'action': 'correct', 'summary': 'TEST ONLY encrypted correction', 'correction_reason': 'TEST ONLY verified later'}
            await handoff.execute(rp, 'berts', 'usr_owner', handoff.Command(**correction), uuid4(), 2)
        finally:
            await rp.close()
        key_bytes = Fernet.generate_key(); dump = Path(os.environ['NATIVE_BACKUP_PG_DUMP']); restore = dump.with_name('pg_restore' + dump.suffix)
        encrypted = await recovery.export(self.url, dump, key_bytes)
        m, raw = recovery.open_envelope(encrypted, key_bytes, self.db)
        self.assertEqual(m['schemas'], list(recovery.SCHEMAS)); self.assertTrue(raw.startswith(b'PGDMP'))
        db = 'native_purchase_test_handoff_restore_' + uuid4().hex; self.restores.append(db)
        await self.admin.execute('CREATE DATABASE ' + db)
        restore_url = self.url.rsplit('/', 1)[0] + '/' + db
        result = await recovery.restore(restore_url, encrypted, key_bytes, self.db, restore)
        self.assertTrue(result['sevenSchemasMatched']); self.assertFalse(result['hostedRecoveryVerified'])
        self.assertTrue((await install.qualify(self.role_url(self.runtime, db), self.role_url(self.accounts, db)))['actualAccountsLogin'])
        rp = await asyncpg.create_pool(self.role_url(self.runtime, db), min_size=1, max_size=1)
        try:
            replay = await handoff.execute(rp, 'berts', 'usr_owner', original, key, 0)
            self.assertTrue(replay['replayed']); self.assertEqual(replay['accepted']['revision'], 1)
            self.assertEqual(replay['current']['revision'], 3); self.assertEqual(replay['current']['summary'], correction['summary'])
        finally:
            await rp.close()
        with self.assertRaises(recovery.Held): await recovery.restore(restore_url, encrypted, key_bytes, self.db, restore)
        with self.assertRaises(recovery.Held): await recovery.restore(self.url, encrypted, key_bytes, self.db, restore)
        empty = 'native_purchase_test_handoff_restore_' + uuid4().hex; self.restores.append(empty)
        await self.admin.execute('CREATE DATABASE ' + empty)
        empty_url = self.url.rsplit('/', 1)[0] + '/' + empty
        c = await recovery.connect(empty_url)
        try:
            await c.execute("CREATE FUNCTION public.test_only_existing() RETURNS integer LANGUAGE sql AS 'SELECT 1'")
        finally:
            await c.close()
        with self.assertRaises(recovery.Held): await recovery.restore(empty_url, encrypted, key_bytes, self.db, restore)
