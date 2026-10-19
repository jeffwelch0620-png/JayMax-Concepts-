"""Fictional-only additive par DDL, security, recovery and backup boundaries."""
import asyncio
import ast
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import inspect
from decimal import Decimal
import os
from pathlib import Path
import sys
import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import asyncpg
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/ops'))
import apply_reviewed_par_migration as engine
import hosted_reviewed_pars as hosted
import test_apply_additive_migration as legacy_fixture
from test_apply_additive_migration import FaultConnection
import actual_inventory_api as actual


def review():
    now = datetime.now(timezone.utc)
    return {'format':hosted.REVIEW_FORMAT,'projectRef':'abcdefghijklmnopqrst',
            'deliveryVersion':'20261018190000','clientRoles':['anon','authenticated','test_only_par_writer'],'backendRoles':[],
            'writerLoginRoles':['test_only_par_writer'], 'budgets':hosted.BUDGETS.copy(),
            'maintenance':{'startsAt':(now-timedelta(minutes=1)).isoformat(),
                           'endsAt':(now+timedelta(minutes=29)).isoformat(),
                           'reference':'TEST ONLY local rehearsal','allWritersStopped':True,'inFlightDrained':True}}


class ParInstallGuards(unittest.TestCase):
    def test_role_groups_are_explicit_disjoint_and_never_inferred_from_names(self):
        spec=review();spec['clientRoles']=['anon','authenticated'];spec['backendRoles']=['test_only_par_writer']
        self.assertEqual(hosted.backend_roles(spec),spec['backendRoles'])
        self.assertEqual(hosted.ledger_roles(spec),['anon','authenticated','test_only_par_writer'])
        for change in ({'backendRoles':None},{'backendRoles':'test_only_par_writer'},
                       {'backendRoles':['test_only_par_writer']*2},
                       {'backendRoles':['anon']},{'backendRoles':['not_in_writer_inventory']},
                       {'backendRoles':[{}]},{'clientRoles':['authenticated']}):
            with self.subTest(change=change),self.assertRaises(hosted.Held):
                hosted.backend_roles(spec|change)
        # A backend-looking name in clientRoles keeps the denial contract.
        old=review()
        self.assertEqual(hosted.backend_roles(old),[])
        self.assertIn('test_only_par_writer',hosted.roles(old))
        unclassified=review();unclassified['clientRoles']=['anon','authenticated']
        with self.assertRaises(hosted.Held):hosted.backend_roles(unclassified)
        # Only the already-pinned administrative postgres actor is exempt.
        for actor in ('postgres','test_only_other_admin'):
            spec=review();spec['writerLoginRoles'].append(actor)
            with self.subTest(administrator=actor):
                if actor=='postgres':self.assertEqual(hosted.backend_roles(spec),[])
                else:
                    with self.assertRaises(hosted.Held):hosted.backend_roles(spec)
        for field in ('format','backendRoles'):
            old=review()
            if field=='format':old[field]='jaymax-hosted-reviewed-par-review-v1'
            else:old.pop(field)
            with self.subTest(old=field),self.assertRaises(hosted.Held):hosted.load_evidence(old)

    def test_retained_security_primitives_match_the_independently_tested_index_tool(self):
        import hosted_additive_index as original
        for name in ('require_runtime','sha','fingerprint','utc','maintenance','target','roles',
                     'writer_roles','server_version','writer_sessions','checked_json','ledger_clients',
                     'private_file','verify_acl','write_private'):
            with self.subTest(helper=name):
                self.assertEqual(ast.dump(ast.parse(inspect.getsource(getattr(original,name)))),
                                 ast.dump(ast.parse(inspect.getsource(getattr(hosted,name)))))

    def test_exact_sql_body_and_reviewed_reference_are_pinned(self):
        raw=engine.source_bytes()
        self.assertEqual(engine.digest(raw),engine.SOURCE_SHA)
        self.assertEqual(engine.digest(engine.sql_body(raw).encode()),engine.BODY_SHA)
        self.assertEqual(engine.reference()['sourceSha256'],engine.SOURCE_SHA)
        with patch.object(engine,'SOURCE_SHA','0'*64),self.assertRaises(ValueError):engine.source_bytes()
        with patch.object(engine,'REFERENCE_SHA','0'*64),self.assertRaises(ValueError):engine.reference()

    def test_old_index_engine_and_hosted_entry_refuse_par_inputs(self):
        self.assertNotEqual(engine.FORMAT,engine.prior.FORMAT)
        self.assertNotEqual(hosted.FORMAT,hosted.engine.prior.FORMAT)
        with self.assertRaises(ValueError):engine.prior.validate_plan({'format':engine.FORMAT})
        with self.assertRaises(hosted.Held):hosted.load_evidence({'format':'jaymax-hosted-additive-index-review-v2'})

    def test_core_has_no_hosted_or_arbitrary_source_cli(self):
        cases=[value for value in vars(sys.modules[__name__]).values()
               if isinstance(value,type) and issubclass(value,unittest.TestCase)]
        self.assertTrue(cases)
        self.assertTrue(all(value.__module__==__name__ for value in cases),
                        'Imported fixture classes must not become a second test collection')
        engine.local_target('postgresql://purchase_implementation_test@127.0.0.1:55439/native_purchase_test_control')
        for value in ('postgresql://postgres@db.example.supabase.co:5432/postgres',
                      'postgresql://postgres@127.0.0.1:5432/postgres',
                      'postgresql://purchase_implementation_test@127.0.0.1:5432/native_purchase_test_control?options=x'):
            with self.subTest(value=value),self.assertRaises(ValueError):engine.local_target(value)

    def test_catalog_multiset_refuses_changes_deletions_and_extra_copies(self):
        base={'relations':[{'nspname':'public','relname':'kept','owner':'owner'}]}
        for after in ({'relations':[]},{'relations':[{'nspname':'public','relname':'kept','owner':'changed'}]}):
            with self.subTest(after=after),self.assertRaises(ValueError):engine.catalog_delta(base,after)
        self.assertEqual(engine.catalog_delta(base,base),{'relations':[]})
        duplicate={'relations':base['relations']*2}
        self.assertEqual(engine.catalog_delta(base,duplicate),base)

    def test_hosted_target_tls_window_and_runtime_guards_remain_enforced(self):
        for args in (((3,11),'nt'),((3,12),'posix')):
            with self.subTest(args=args),self.assertRaises(ValueError):hosted.require_runtime(*args)
        spec=review(); hosted.maintenance(spec)
        for change in ({'allWritersStopped':False},{'inFlightDrained':False},
                       {'endsAt':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()}):
            bad=deepcopy(spec);bad['maintenance'].update(change)
            with self.subTest(change=change),self.assertRaises(hosted.Held):hosted.maintenance(bad)
        for dsn in ('postgresql://postgres@127.0.0.1:5432/postgres',
                    'postgresql://postgres.abcdefghijklmnopqrst@aws-0-us-east-1.pooler.supabase.com:6543/postgres'):
            with self.subTest(dsn=dsn),self.assertRaises(ValueError):hosted.target(dsn,spec['projectRef'])


class ParInstallReceiptTests(unittest.IsolatedAsyncioTestCase):
    async def test_lost_rollback_ack_stays_unknown_and_never_attempts_commit(self):
        tx=SimpleNamespace(start=AsyncMock(),commit=AsyncMock(),
                           rollback=AsyncMock(side_effect=ConnectionError('TEST ONLY lost rollback acknowledgement')))
        conn=SimpleNamespace(is_in_transaction=lambda:False,fetchval=AsyncMock(return_value=True),
                             execute=AsyncMock(),transaction=lambda **kwargs:tx)
        plan={'baseline':{'columns':[]},'migration':{'TEST_ONLY':True}}
        guard=AsyncMock(side_effect=RuntimeError('TEST ONLY pre-DDL guard refusal'))
        with patch.object(engine,'validate_plan',return_value='TEST ONLY DO NOT SEND'),\
             patch.object(engine,'snapshot',AsyncMock(return_value=plan['baseline'])),\
             patch.object(engine,'verify_prior',AsyncMock()),patch.object(engine,'absent',AsyncMock()),\
             patch.object(engine,'readiness_check',AsyncMock()),\
             patch.object(engine.preservation,'lock_original_tables',AsyncMock()):
            plan.update(originalInstallation={},sourceIndexPlan={},clientRoles=[],backendRoles=[])
            with self.assertRaises(engine.AdditiveFailure) as result:await engine.apply(conn,plan,guard=guard)
        self.assertEqual(result.exception.report['status'],'rollback_outcome_unknown')
        self.assertIsNone(result.exception.report['sqlCommitted'])
        self.assertFalse(result.exception.report['commitAttempted'])
        self.assertNotIn('rollbackCompleted',result.exception.report)
        self.assertFalse(result.exception.report['automaticRetry'])
        tx.commit.assert_not_awaited()
        self.assertFalse(any(call.args[0]=='TEST ONLY DO NOT SEND' for call in conn.execute.await_args_list))

    async def test_short_remaining_window_refuses_before_any_database_work(self):
        spec=review();spec['maintenance']['endsAt']=(datetime.now(timezone.utc)+timedelta(seconds=610)).isoformat()
        with patch.object(hosted,'validate'),patch.object(hosted,'server_version',new_callable=AsyncMock) as probe,\
             patch.object(engine,'apply',new_callable=AsyncMock) as send:
            with self.assertRaises(hosted.Held):await hosted.apply(None,{},spec,{}, {},{})
            probe.assert_not_awaited();send.assert_not_awaited()

    async def exercise(self, mode, *, direct=False):
        with TemporaryDirectory() as directory:
            root=Path(directory);out=root/'out';out.mkdir()
            spec=review();spec.update(originalReceipt=str(root/'original'),sourceIndexPlan=str(root/'index'),
                backup={k:str(root/k) for k in ('encryptedFile','keyFile','restoreReceipt')})
            target={'actor':'postgres','projectRef':spec['projectRef'],
                    'connectionMode':'direct' if direct else 'session_pooler'};binding={'TEST_ONLY':True}
            core={'clientRoles':spec['clientRoles'],'backendRoles':spec['backendRoles'],
                  'baseline':{'identity':{'actor':'postgres'}},
                  'migration':{'deliveryVersion':spec['deliveryVersion']}}
            plan={'format':hosted.FORMAT,'createdAt':'TEST ONLY','target':target,
                  'reviewSha256':hosted.fingerprint(spec),'backup':binding,'maintenance':spec['maintenance'],
                  'budgets':hosted.BUDGETS,'core':core,'writerObservations':[],
                  'automaticApply':False,'operationalReleaseApproved':False}
            rp=root/'review.json';pp=root/'plan.json'
            rp.write_text(json.dumps(spec));pp.write_text(json.dumps(plan))
            args=SimpleNamespace(mode='apply',owner_config=str(root/'owner'),expected_project=spec['projectRef'],
                review=str(rp),review_sha256=hosted.sha(rp.read_bytes()),plan=str(pp),
                plan_sha256=hosted.sha(pp.read_bytes()),approve_plan_sha256=hosted.sha(pp.read_bytes()),
                output_directory=str(out),maintenance_direct_ipv6=direct)
            if mode=='wrong_approval':args.approve_plan_sha256='0'*64
            conn=SimpleNamespace(close=AsyncMock())
            connect=AsyncMock(side_effect=[conn,ConnectionError('TEST ONLY private connection detail')])
            async def send(*a,**kw):
                before=json.loads((out/'receipt.json').read_text())
                self.assertEqual(before['status'],'apply_in_progress_outcome_unknown')
                self.assertIsNone(before['sqlCommitted'])
                if mode=='lost_ack':
                    raise engine.AdditiveFailure({'status':'commit_outcome_unknown','commitAttempted':True,
                        'sqlCommitted':None,'automaticRetry':False,'errorType':'ConnectionError'})
                return {'status':'committed_requires_independent_verification','commitAttempted':True,'sqlCommitted':True}
            apply=AsyncMock(side_effect=send)
            import maintenance_connection
            direct_url='postgresql://postgres:TEST_ONLY@db.'+spec['projectRef']+'.supabase.co:5432/postgres'
            config={'DATABASE_URL':'TEST ONLY APP'}
            if direct:config['MAINTENANCE_DATABASE_URL']=direct_url
            with ExitStack() as stack:
                for obj,name,value in [(hosted.backup,'private_directory',lambda p,area:out),
                    (hosted,'write_private',lambda p,raw:Path(p).write_bytes(raw)),
                    (hosted,'private_file',Path),(hosted,'dotenv_values',lambda p,**kw:config),
                    (hosted,'target',lambda *a:target),(hosted,'connection_tls',lambda x:True),
                    (hosted,'load_evidence',lambda *a,**kw:(({},{}),{},binding)),
                    (engine,'validate_plan',lambda x:None),(hosted.asyncpg,'connect',connect),(hosted,'apply',apply)]:
                    stack.enter_context(patch.object(obj,name,value))
                direct_connect=stack.enter_context(patch.object(maintenance_connection,'connect',connect if direct else AsyncMock()))
                self.assertEqual(await hosted.run(args),2)
                if direct and mode!='wrong_approval':
                    self.assertTrue(all(call.args==(direct_url,spec['projectRef']) for call in direct_connect.await_args_list))
            result=json.loads((out/'receipt.json').read_text())
            self.assertFalse(result['automaticRetry'])
            self.assertEqual(result['planSha256'],args.plan_sha256)
            self.assertNotIn('private connection detail',json.dumps(result))
            return result,apply,connect

    async def test_exact_approval_required_before_any_connection_or_send(self):
        result,send,connect=await self.exercise('wrong_approval')
        self.assertEqual(result['status'],'held');self.assertFalse(result['sqlCommitted'])
        send.assert_not_awaited();connect.assert_not_awaited()

    async def test_unknown_commit_preserves_plan_receipt_and_never_retries(self):
        result,send,_=await self.exercise('lost_ack')
        self.assertEqual(result['status'],'commit_outcome_unknown');self.assertIsNone(result['sqlCommitted'])
        self.assertEqual(send.await_count,1)

    async def test_fresh_connection_failure_retains_known_commit(self):
        result,send,_=await self.exercise('fresh_failure')
        self.assertEqual(result['status'],'committed_verification_held');self.assertTrue(result['sqlCommitted'])
        self.assertEqual(send.await_count,1)

    async def test_direct_approval_unknown_commit_and_independent_reconcile_gates_remain(self):
        for mode in ('wrong_approval','lost_ack','fresh_failure'):
            with self.subTest(mode=mode):
                result,send,connect=await self.exercise(mode,direct=True)
                if mode=='wrong_approval':
                    self.assertEqual(result['status'],'held');send.assert_not_awaited();connect.assert_not_awaited()
                elif mode=='lost_ack':
                    self.assertEqual(result['status'],'commit_outcome_unknown');self.assertIsNone(result['sqlCommitted'])
                    self.assertEqual(send.await_count,1)
                else:
                    self.assertEqual(result['status'],'committed_verification_held');self.assertTrue(result['sqlCommitted'])
                    self.assertEqual(send.await_count,1)


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PostgreSQL required')
class ParInstallDatabaseTests(unittest.IsolatedAsyncioTestCase):
    # Reuse fixture operations explicitly. Never inherit the old installer cases.
    @classmethod
    async def build_template(cls):
        original=await legacy_fixture.AdditiveDatabaseTests.build_template.__func__(cls)
        conn=await asyncpg.connect(cls.control.rsplit('/',1)[0]+'/'+cls.template)
        try:
            # Install the already-reviewed source index once in the disposable
            # template. Individual cases still get separate database clones.
            cls.index_plan=await engine.prior.prepare(conn,original,'20261015175921',client_roles=['anon','authenticated'])
            await engine.prior.apply(conn,cls.index_plan)
            return original
        except BaseException:
            await conn.close();conn=None
            admin=await asyncpg.connect(cls.control)
            try:await admin.execute('DROP DATABASE '+cls.template)
            finally:await admin.close()
            raise
        finally:
            if conn is not None:await conn.close()

    @classmethod
    def setUpClass(cls):
        cls.created_roles=[]
        cls.writer_password='TEST_ONLY_par_backend_password'
        cls.writer_login_roles=['test_only_par_'+uuid4().hex[:12]]
        async def provision():
            c=await asyncpg.connect(os.environ['NATIVE_PURCHASE_TEST_DSN'])
            try:
                for name in ['anon','authenticated']+cls.writer_login_roles:
                    if not await c.fetchval('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=$1)',name):
                        await c.execute('CREATE ROLE '+name+(
                            " LOGIN PASSWORD '"+cls.writer_password+"'" if name in cls.writer_login_roles else ' NOLOGIN'))
                        cls.created_roles.append(name)
            finally:await c.close()
        asyncio.run(provision())
        try:legacy_fixture.AdditiveDatabaseTests.setUpClass.__func__(cls)
        except Exception:
            cls.remove_roles();raise

    @classmethod
    def remove_roles(cls):
        async def remove():
            c=await asyncpg.connect(os.environ['NATIVE_PURCHASE_TEST_DSN'])
            try:
                for name in cls.created_roles:await c.execute('DROP ROLE '+name)
            finally:await c.close()
        asyncio.run(remove())

    @classmethod
    def tearDownClass(cls):
        try:legacy_fixture.AdditiveDatabaseTests.tearDownClass.__func__(cls)
        finally:cls.remove_roles()

    async def asyncSetUp(self):
        await legacy_fixture.AdditiveDatabaseTests.asyncSetUp(self)

    async def asyncTearDown(self):
        await legacy_fixture.AdditiveDatabaseTests.asyncTearDown(self)

    async def plan(self):
        return await engine.prepare(self.conn,self.original,self.index_plan,'20261018190000')

    async def verify(self,plan):
        c=await asyncpg.connect(self.dsn,server_settings={'default_transaction_read_only':'on'})
        try:return await engine.verify_outcome(c,plan)
        finally:await c.close()

    async def hosted_plan(self,backend_roles=()):
        self.spec=review();self.spec['writerLoginRoles']=self.writer_login_roles
        self.spec['backendRoles']=list(backend_roles)
        self.spec['clientRoles']=['anon','authenticated']+[role for role in self.writer_login_roles if role not in backend_roles]
        self.target={'projectRef':self.spec['projectRef'],'actor':'purchase_implementation_test',
                     'host':'127.0.0.1','port':55439,'database':self.name,'connectionMode':'TEST ONLY loopback'}
        async with self.conn.transaction(isolation='repeatable_read',readonly=True):
            self.facts=await hosted.backup.fingerprint(self.conn)
        self.binding={'factsSha256':hosted.fingerprint(self.facts),
                      'serverVersionNum':await self.conn.fetchval('SHOW server_version_num'),'TEST_ONLY':True}
        return await hosted.prepare(self.conn,(self.original,self.index_plan),self.spec,self.target,self.facts,self.binding)

    async def hosted_verify(self,plan):
        c=await asyncpg.connect(self.dsn,server_settings={'default_transaction_read_only':'on'})
        try:return await hosted.reconcile(c,plan,self.spec,self.target,self.facts,self.binding)
        finally:await c.close()

    async def backend_role(self):
        role=self.writer_login_roles[0]
        await self.conn.execute('GRANT USAGE ON SCHEMA purchasing,actual_inventory,prep_inventory TO '+role)
        await self.conn.execute('GRANT SELECT ON purchasing.item_bases TO '+role)
        await self.conn.execute('GRANT EXECUTE ON FUNCTION purchasing.text_cells(jsonb) TO '+role)
        return role

    async def test_explicit_backend_access_survives_prepare_apply_reconcile_without_new_par_access(self):
        role=await self.backend_role()
        before=await engine.snapshot(self.conn)
        params=self.workflow['actualReportParams'];store=self.workflow['temporaryStore']
        food=await actual.period_report(self.conn,store,UUID(params['opening']),UUID(params['closing']))
        # LOGIN and the existing read/function grants work on a separate client.
        backend=await asyncpg.connect(self.dsn,user=role,password=self.writer_password)
        try:
            self.assertTrue(await backend.fetchval("SELECT purchasing.text_cells('[]'::jsonb)"))
            await backend.fetchval('SELECT count(*) FROM purchasing.item_bases')
        finally:await backend.close()
        plan=await self.hosted_plan([role])
        self.assertEqual(await engine.snapshot(self.conn),before)
        self.assertEqual(plan['core']['backendRoles'],[role])
        self.assertEqual(plan['core']['clientRoles'],['anon','authenticated'])
        self.assertEqual((await self.hosted_verify(plan))['status'],'verified_not_applied')
        self.assertTrue((await hosted.apply(self.conn,plan,self.spec,self.target,self.facts,self.binding))['sqlCommitted'])
        self.assertEqual((await self.hosted_verify(plan))['status'],'verified_applied')
        self.assertTrue(await self.conn.fetchval("SELECT has_table_privilege($1,'purchasing.item_bases','SELECT')",role))
        for client in ['anon','authenticated',role]:
            self.assertFalse(await self.conn.fetchval("SELECT has_table_privilege($1,$2,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')",client,engine.TABLE))
        self.assertEqual(await actual.period_report(self.conn,store,UUID(params['opening']),UUID(params['closing'])),food)
        self.assertEqual(food['actualFoodCost'],'55.00')

    async def test_backend_classification_and_plan_bindings_cannot_be_omitted_or_relabelled(self):
        role=await self.backend_role()
        # The old combined-role list still fails closed; no prefix-based exemption.
        with self.assertRaises(ValueError):
            await engine.prepare(self.conn,self.original,self.index_plan,'20261018190000',client_roles=['anon','authenticated',role])
        plan=await self.hosted_plan([role])
        for change in ({'format':'jaymax-additive-reviewed-par-plan-v1'},{'backendRoles':None},
                       {'backendRoles':[role,role]},{'backendRoles':['anon']}):
            with self.subTest(change=change),self.assertRaises(ValueError):engine.validate_plan(plan['core']|change)
        missing=deepcopy(plan['core']);missing.pop('backendRoles')
        with self.assertRaises(ValueError):engine.validate_plan(missing)
        changed=deepcopy(plan);changed['core']['backendRoles']=[]
        with self.assertRaises(hosted.Held):hosted.validate(changed,self.spec,self.target,self.binding)
        changed=deepcopy(plan);changed['core']['clientRoles'].append(role)
        with self.assertRaises(hosted.Held):hosted.validate(changed,self.spec,self.target,self.binding)
        bad_spec=deepcopy(self.spec);bad_spec['writerLoginRoles']=[]
        with self.assertRaises(hosted.Held):hosted.validate(plan,bad_spec,self.target,self.binding)

    async def test_backend_ledger_table_and_column_exposure_hold_before_plan(self):
        role=await self.backend_role()
        for privilege in ('SELECT','SELECT(version)','INSERT','UPDATE(name)'):
            tx=self.conn.transaction(isolation='repeatable_read');await tx.start()
            try:
                await self.conn.execute('GRANT '+privilege+' ON supabase_migrations.schema_migrations TO '+role)
                with self.subTest(privilege=privilege),self.assertRaises(hosted.Held):
                    await engine.prepare(self.conn,self.original,self.index_plan,'20261018190000',backend_roles=[role])
                self.assertFalse(await self.conn.fetchval('SELECT to_regclass($1) IS NOT NULL',engine.TABLE))
            finally:await tx.rollback()

    async def test_backend_trust_never_waives_browser_private_access(self):
        role=await self.backend_role()
        for sql in ('GRANT USAGE ON SCHEMA purchasing TO anon',
                    'GRANT SELECT ON purchasing.item_bases TO authenticated',
                    'GRANT EXECUTE ON FUNCTION purchasing.text_cells(jsonb) TO anon'):
            tx=self.conn.transaction(isolation='repeatable_read');await tx.start()
            try:
                await self.conn.execute(sql)
                with self.subTest(sql=sql),self.assertRaises(ValueError):
                    await engine.prepare(self.conn,self.original,self.index_plan,'20261018190000',backend_roles=[role])
            finally:await tx.rollback()

    async def test_backend_authority_membership_and_future_defaults_are_held(self):
        role=await self.backend_role()
        changes=['ALTER ROLE '+role+' '+flag for flag in ('NOLOGIN','SUPERUSER','BYPASSRLS','CREATEDB','CREATEROLE','REPLICATION')]
        changes += ['GRANT anon TO '+role,'GRANT CREATE ON SCHEMA purchasing TO '+role,
            'GRANT '+role+' TO anon WITH INHERIT FALSE, SET TRUE',
            'GRANT CREATE ON DATABASE '+self.name+' TO '+role,
            'ALTER SCHEMA purchasing OWNER TO '+role+'; REVOKE CREATE ON SCHEMA purchasing FROM '+role,
            'ALTER DATABASE '+self.name+' OWNER TO '+role+'; REVOKE CREATE ON DATABASE '+self.name+' FROM '+role,
            'ALTER TABLE purchasing.item_bases OWNER TO '+role,
            'ALTER DEFAULT PRIVILEGES IN SCHEMA purchasing GRANT SELECT ON TABLES TO '+role,
            'ALTER DEFAULT PRIVILEGES IN SCHEMA purchasing GRANT EXECUTE ON FUNCTIONS TO '+role]
        for sql in changes:
            tx=self.conn.transaction(isolation='repeatable_read');await tx.start()
            try:
                await self.conn.execute(sql)
                with self.subTest(sql=sql),self.assertRaises(ValueError):await engine.backend_permissions(self.conn,[role])
            finally:await tx.rollback()
        with self.assertRaises(ValueError):await engine.backend_permissions(self.conn,['test_only_missing_backend'])
        tx=self.conn.transaction(isolation='repeatable_read');await tx.start()
        try:
            administrator=await self.conn.fetchval('SELECT current_user')
            await self.conn.execute('GRANT '+role+' TO '+administrator+' WITH ADMIN TRUE, INHERIT FALSE, SET FALSE')
            # PostgreSQL may retain a CREATE ROLE grant to its administrator.
            await engine.backend_permissions(self.conn,[role])
        finally:await tx.rollback()

    async def test_browser_column_only_access_is_denied_with_a_classified_backend(self):
        role=await self.backend_role()
        await self.conn.execute('CREATE SEQUENCE purchasing.test_only_ungranted_sequence')
        for client,privilege in [('anon','SELECT(item_code)'),('authenticated','UPDATE(item_code)')]:
            tx=self.conn.transaction(isolation='repeatable_read');await tx.start()
            try:
                await self.conn.execute('GRANT '+privilege+' ON purchasing.item_bases TO '+client)
                self.assertFalse(await self.conn.fetchval("SELECT has_table_privilege($1,'purchasing.item_bases','SELECT,INSERT,UPDATE,REFERENCES')",client))
                with self.subTest(client=client),self.assertRaisesRegex(ValueError,'private column access'):
                    await engine.prepare(self.conn,self.original,self.index_plan,'20261018190000',backend_roles=[role])
                self.assertFalse(await self.conn.fetchval('SELECT to_regclass($1) IS NOT NULL',engine.TABLE))
            finally:await tx.rollback()

        # Non-table relations cannot break or bypass the column-only guard.
        await engine.readiness_check(self.conn, ['anon','authenticated'], before=True, backend_roles=[role])

    async def test_new_par_access_and_late_backend_grants_stay_blocked(self):
        role=await self.backend_role();plan=await self.hosted_plan([role])
        await hosted.apply(self.conn,plan,self.spec,self.target,self.facts,self.binding)
        for sql in ('GRANT SELECT ON purchasing.inventory_par_versions TO '+role,
                    'GRANT SELECT(quantity) ON purchasing.inventory_par_versions TO '+role,
                    'GRANT EXECUTE ON FUNCTION purchasing.guard_inventory_par() TO '+role):
            tx=self.conn.transaction(isolation='repeatable_read');await tx.start()
            try:
                await self.conn.execute(sql)
                with self.subTest(sql=sql),self.assertRaisesRegex(ValueError,'New par runtime access'):
                    await engine.backend_permissions(self.conn,[role])
            finally:await tx.rollback()
        await self.conn.execute('GRANT SELECT ON purchasing.inventory_par_versions TO '+role)
        with self.assertRaises(ValueError):await self.hosted_verify(plan)

    async def test_classified_backend_still_holds_live_writers_and_changed_permissions(self):
        role=await self.backend_role();plan=await self.hosted_plan([role])
        writer=await asyncpg.connect(self.dsn,user=role,password=self.writer_password)
        try:
            with self.assertRaises(hosted.Held):
                await hosted.apply(self.conn,plan,self.spec,self.target,self.facts,self.binding)
            self.assertFalse(await self.conn.fetchval('SELECT to_regclass($1) IS NOT NULL',engine.TABLE))
        finally:await writer.close()
        await self.conn.execute('GRANT INSERT ON purchasing.item_bases TO '+role)
        with self.assertRaises(engine.AdditiveFailure) as result:
            await hosted.apply(self.conn,plan,self.spec,self.target,self.facts,self.binding)
        self.assertTrue(result.exception.report['rollbackCompleted'])
        self.assertFalse(result.exception.report['commitAttempted'])
        self.assertFalse(await self.conn.fetchval('SELECT to_regclass($1) IS NOT NULL',engine.TABLE))

    async def test_readonly_plan_atomic_install_exact_delta_and_food_cost_preserved(self):
        before=await engine.snapshot(self.conn)
        params=self.workflow['actualReportParams'];store=self.workflow['temporaryStore']
        report=await actual.period_report(self.conn,store,UUID(params['opening']),UUID(params['closing']))
        plan=await self.plan()
        self.assertEqual(await engine.snapshot(self.conn),before)
        self.assertEqual((await self.verify(plan))['status'],'verified_not_applied')
        self.assertTrue((await engine.apply(self.conn,plan))['sqlCommitted'])
        self.assertEqual((await self.verify(plan))['status'],'verified_applied')
        self.assertEqual(await self.conn.fetchval('SELECT count(*) FROM purchasing.inventory_par_versions'),0)
        self.assertEqual(len(await engine.preservation.ledger_fingerprints(self.conn)),len(before['ledger'])+1)
        self.assertEqual(await actual.period_report(self.conn,store,UUID(params['opening']),UUID(params['closing'])),report)
        self.assertEqual(report['actualFoodCost'],'55.00')

    async def test_changed_source_plan_reference_flags_or_backup_binding_are_refused(self):
        plan=await self.plan()
        for key,value in [('automaticApply',True),('operationalReleaseApproved',True),('referenceSha256','0'*64),
                          ('sourceHashes',{}),('format',engine.prior.FORMAT),('unexpected',True)]:
            with self.subTest(key=key),self.assertRaises(ValueError):engine.validate_plan(plan|{key:value})
        changed=deepcopy(plan);changed['migration']['sha256']='0'*64
        with self.assertRaises(ValueError):await engine.apply(self.conn,changed)
        changed=deepcopy(plan);changed['baseline']['identity']['database_oid']=-1
        with self.assertRaises(engine.AdditiveFailure):await engine.apply(self.conn,changed)
        async with self.conn.transaction(isolation='repeatable_read'):
            with self.assertRaises(ValueError):await engine.apply(self.conn,plan)
        hosted_plan=await self.hosted_plan()
        for changed in [hosted_plan|{'backup':{}},hosted_plan|{'target':{}},hosted_plan|{'reviewSha256':'0'*64}]:
            with self.subTest(keys=list(changed)),self.assertRaises(hosted.Held):
                hosted.validate(changed,self.spec,self.target,self.binding)

    async def test_prior_missing_changed_extra_history_and_wrong_index_are_held(self):
        for sql in ["DELETE FROM supabase_migrations.schema_migrations WHERE version='20261015175921'",
                    "UPDATE supabase_migrations.schema_migrations SET statements=ARRAY['SELECT 2;'] WHERE version='20261015175921'",
                    "UPDATE supabase_migrations.schema_migrations SET name='changed' WHERE version='20260929135736'",
                    "INSERT INTO supabase_migrations.schema_migrations VALUES('20261016000000','unreviewed',ARRAY['SELECT 1;'])",
                    'DROP INDEX purchasing.document_source_rows_version_run_idx']:
            tx=self.conn.transaction(isolation='repeatable_read');await tx.start()
            try:
                await self.conn.execute(sql)
                with self.subTest(sql=sql),self.assertRaises(ValueError):await self.plan()
            finally:await tx.rollback()

    async def test_ledger_failure_rolls_back_table_function_and_store_state(self):
        plan=await self.plan()
        with self.assertRaises(engine.AdditiveFailure) as result:
            await engine.apply(FaultConnection(self.conn,ledger_failure=True),plan)
        self.assertTrue(result.exception.report['rollbackCompleted'])
        self.assertFalse(result.exception.report['commitAttempted'])
        after=await engine.snapshot(self.conn)
        self.assertEqual([key for key in plan['baseline'] if after[key]!=plan['baseline'][key]],[])
        self.assertEqual((await self.verify(plan))['status'],'verified_not_applied')

    async def test_lost_commit_ack_reconciles_and_reapply_is_refused(self):
        plan=await self.plan()
        with self.assertRaises(engine.AdditiveFailure) as result:
            await engine.apply(FaultConnection(self.conn,commit_ack_loss=True),plan)
        self.assertEqual(result.exception.report['status'],'commit_outcome_unknown')
        self.assertIsNone(result.exception.report['sqlCommitted'])
        self.assertEqual((await self.verify(plan))['status'],'verified_applied')
        with self.assertRaises(engine.AdditiveFailure):await engine.apply(self.conn,plan)

    async def test_unresolved_transaction_blocks_false_unapplied_result_until_disconnect(self):
        plan=await self.plan()
        other=await asyncpg.connect(self.dsn)
        try:
            await other.execute('SELECT pg_advisory_lock($1::bigint)',engine.INSTALLER_LOCK)
            with self.assertRaises(ValueError):await self.verify(plan)
        finally:await other.close()
        self.assertEqual((await self.verify(plan))['status'],'verified_not_applied')

    async def test_partial_object_and_postcommit_security_tampering_are_refused(self):
        tx=self.conn.transaction(isolation='repeatable_read');await tx.start()
        try:
            await self.conn.execute('CREATE TABLE purchasing.inventory_par_versions(id uuid)')
            with self.assertRaises(ValueError):await self.plan()
        finally:await tx.rollback()
        plan=await self.plan();await engine.apply(self.conn,plan)
        await self.conn.execute("UPDATE pg_index SET indisvalid=false WHERE indexrelid='purchasing.inventory_par_root'::regclass")
        with self.assertRaises(ValueError):await self.verify(plan)
        await self.conn.execute("UPDATE pg_index SET indisvalid=true WHERE indexrelid='purchasing.inventory_par_root'::regclass")
        await self.conn.execute('ALTER TABLE purchasing.inventory_par_versions DISABLE TRIGGER valid_inventory_par')
        with self.assertRaises(ValueError):await self.verify(plan)
        await self.conn.execute('ALTER TABLE purchasing.inventory_par_versions ENABLE TRIGGER valid_inventory_par')
        await self.conn.execute('CREATE POLICY test_only_unreviewed_policy ON purchasing.inventory_par_versions FOR SELECT TO anon USING(true)')
        with self.assertRaises(ValueError):await self.verify(plan)
        await self.conn.execute('DROP POLICY test_only_unreviewed_policy ON purchasing.inventory_par_versions')
        for relation,column in [('purchasing.inventory_par_versions','quantity'),('public.stores','name')]:
            await self.conn.execute('GRANT SELECT('+column+') ON '+relation+' TO '+self.writer_login_roles[0])
        self.assertEqual(len((await engine.snapshot(self.conn))['columnAcl']),len(plan['baseline']['columnAcl'])+2)
        with self.assertRaisesRegex(ValueError,'column or default privileges'):await self.verify(plan)

    async def test_default_grant_and_unexpected_policy_cannot_hide_in_new_delta(self):
        plan=await self.plan()
        await self.conn.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA purchasing GRANT SELECT ON TABLES TO anon')
        # Revoked explicit public clients are denied by the SQL; an unrelated
        # role default grant must still be caught by the pinned catalog delta.
        await self.conn.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA purchasing GRANT SELECT ON TABLES TO '+self.writer_login_roles[0])
        with self.assertRaises(engine.AdditiveFailure) as result:await engine.apply(self.conn,plan)
        self.assertTrue(result.exception.report['rollbackCompleted'])
        self.assertFalse(await self.conn.fetchval('SELECT to_regclass($1) IS NOT NULL',engine.TABLE))

    async def test_hosted_guards_preserve_backed_up_rows_and_new_empty_table(self):
        plan=await self.hosted_plan()
        self.assertEqual((await self.hosted_verify(plan))['status'],'verified_not_applied')
        self.assertTrue((await hosted.apply(self.conn,plan,self.spec,self.target,self.facts,self.binding))['sqlCommitted'])
        self.assertEqual((await self.hosted_verify(plan))['status'],'verified_applied')
        for role in ['anon','authenticated']:
            self.assertFalse(await self.conn.fetchval('SELECT has_table_privilege($1,$2,\'SELECT,INSERT,UPDATE,DELETE,TRUNCATE\')',role,engine.TABLE))
        for sql in ['UPDATE purchasing.inventory_par_versions SET quantity=1',
                    'DELETE FROM purchasing.inventory_par_versions','TRUNCATE purchasing.inventory_par_versions']:
            # Row triggers require a row to fire; append-only behavior with
            # populated history is exercised in the existing par contract suite.
            if sql.startswith('TRUNCATE'):
                with self.assertRaises(asyncpg.RaiseError):await self.conn.execute(sql)

    async def test_drift_late_writer_and_precommit_guard_failure_roll_back(self):
        plan=await self.hosted_plan()
        async def fail(c,phase):
            if phase=='after':raise RuntimeError('TEST ONLY late guard refusal')
        with self.assertRaises(engine.AdditiveFailure) as result:await engine.apply(self.conn,plan['core'],guard=fail)
        self.assertTrue(result.exception.report['rollbackCompleted'])
        self.assertEqual((await self.verify(plan['core']))['status'],'verified_not_applied')
        await self.conn.execute("UPDATE public.stores SET name='TEST ONLY changed after backup' WHERE id='berts'")
        with self.assertRaises(engine.AdditiveFailure) as changed:
            await hosted.apply(self.conn,plan,self.spec,self.target,self.facts,self.binding)
        self.assertFalse(changed.exception.report['commitAttempted'])
        self.assertFalse(await self.conn.fetchval('SELECT to_regclass($1) IS NOT NULL',engine.TABLE))

    async def test_known_and_unknown_writer_guards_and_hidden_activity_fail_closed(self):
        plan=await self.hosted_plan();writer=await asyncpg.connect(self.dsn)
        try:
            tx=writer.transaction();await tx.start()
            await writer.execute("UPDATE public.stores SET name='TEST ONLY writer' WHERE id='berts'")
            with self.assertRaises(hosted.Held):await hosted.apply(self.conn,plan,self.spec,self.target,self.facts,self.binding)
            await tx.rollback()
            self.spec['writerLoginRoles']=['purchase_implementation_test']
            with self.assertRaises(hosted.Held):await hosted.writer_sessions(self.conn,self.spec,'TEST ONLY',[])
        finally:await writer.close()

    async def test_write_committing_during_lock_wait_invalidates_plan(self):
        plan=await self.plan();writer=await asyncpg.connect(self.dsn)
        tx=writer.transaction();await tx.start()
        await writer.execute("UPDATE public.stores SET name='TEST ONLY lock wait change' WHERE id='berts'")
        task=asyncio.create_task(engine.apply(self.conn,plan))
        try:
            await asyncio.sleep(.2);await tx.commit()
            with self.assertRaises(engine.AdditiveFailure) as result:await task
            self.assertTrue(result.exception.report['rollbackCompleted'])
            self.assertFalse(result.exception.report['commitAttempted'])
        finally:
            if not task.done():await task
            await writer.close()

    async def test_real_encrypted_export_and_restore_retain_installed_par_history_and_food_cost(self):
        import hosted_backup as backup
        # The original native fixture predates the empty hosted integrations
        # schema. Build the complete fictional backup scope; keep its guard.
        found={r['nspname'] for r in await self.conn.fetch("SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname<>'information_schema'")}
        self.assertEqual(set(backup.SCHEMAS)-found,{'integrations'})
        self.assertFalse(found-set(backup.SCHEMAS)-backup.MANAGED)
        await self.conn.execute('CREATE SCHEMA integrations')
        plan=await self.plan();await engine.apply(self.conn,plan)
        profile=await self.conn.fetchrow("SELECT p.* FROM purchasing.unit_profiles p WHERE profile_kind='count' "
            "AND NOT EXISTS(SELECT 1 FROM purchasing.unit_profiles n WHERE n.store_id=p.store_id "
            "AND n.item_code=p.item_code AND n.profile_kind=p.profile_kind AND n.revision>p.revision) LIMIT 1")
        self.assertIsNotNone(profile)
        first=uuid4();second=uuid4()
        for revision,ident,previous,quantity in [(1,first,None,Decimal('0.0000001')),(2,second,first,Decimal('0'))]:
            await self.conn.execute("""INSERT INTO purchasing.inventory_par_versions
                (id,store_id,item_code,revision,predecessor_id,unit_profile_id,source_unit,quantity,factor,
                 base_unit,base_quantity,confirmed,coverage_note,actor,request_key,request_fingerprint)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$8::numeric*$9::numeric,true,'TEST ONLY backup history',
                       'TEST ONLY reviewer',$11,$12)""",ident,profile['store_id'],profile['item_code'],revision,previous,
                profile['id'],profile['source_unit'],quantity,profile['base_units_per_source_unit'],
                profile['base_unit'],uuid4(),bytes([revision])*32)
        for statement in ('DELETE FROM purchasing.inventory_par_versions',
                          'UPDATE purchasing.inventory_par_versions SET quantity=1',
                          'TRUNCATE purchasing.inventory_par_versions'):
            with self.subTest(statement=statement),self.assertRaises(asyncpg.PostgresError):await self.conn.execute(statement)
        before=[dict(r) for r in await self.conn.fetch('SELECT * FROM purchasing.inventory_par_versions ORDER BY revision')]
        params=self.workflow['actualReportParams'];store=self.workflow['temporaryStore']
        report=await actual.period_report(self.conn,store,UUID(params['opening']),UUID(params['closing']))
        restored='native_purchase_test_backup_'+uuid4().hex
        restore_dsn=self.control.rsplit('/',1)[0]+'/'+restored
        await self.admin.execute('CREATE DATABASE '+restored+' TEMPLATE template0')
        real_connect=asyncpg.connect;real_tool=backup.tool
        source_settings=backup.native.disposable_connection(self.dsn)
        project='abcdefghijklmnopqrst';fake='postgresql://postgres.'+project+':TEST_ONLY@aws-0.pooler.supabase.com:5432/postgres'
        async def local_connect(url=None,**kwargs):
            if url is not None:
                self.assertEqual(url,fake)
                return await real_connect(**source_settings,ssl=False,timeout=kwargs['timeout'],
                    command_timeout=kwargs['command_timeout'],statement_cache_size=0,server_settings=kwargs['server_settings'])
            self.assertEqual(kwargs['database'],restored);self.assertEqual(kwargs['host'],'127.0.0.1')
            return await real_connect(**kwargs)
        async def local_tool(executable,args,settings=None,remote=False):
            return await real_tool(executable,args,source_settings if remote else settings,False)
        def directory(path,area):path.mkdir();return path
        dump=Path(os.environ['NATIVE_BACKUP_PG_DUMP']);restore=dump.with_name('pg_restore'+dump.suffix)
        try:
            with TemporaryDirectory() as temporary:
                root=Path(temporary)
                with patch.object(backup,'private_directory',side_effect=directory),\
                     patch.object(backup,'connection_tls',return_value=True),\
                     patch.object(backup.asyncpg,'connect',side_effect=local_connect),\
                     patch.object(backup,'tool',side_effect=local_tool):
                    exported=await backup.export_backup(fake,project,dump,restore,root/'archive',root/'key',engine.sources())
                    manifest,_=backup.open_backup(exported['encryptedBackup'],exported['privateKey'],project)
                    self.assertEqual(manifest['tables'][engine.TABLE]['rows'],2)
                    verified=await backup.verify_restore(restore_dsn,exported['encryptedBackup'],exported['privateKey'],project,restore,root/'restored')
                    self.assertEqual(verified['status'],'verified_application_restore')
                    self.assertEqual(verified['archiveSha256'],exported['archiveSha256'])
                restored_conn=await real_connect(restore_dsn)
                try:
                    self.assertEqual([dict(r) for r in await restored_conn.fetch('SELECT * FROM purchasing.inventory_par_versions ORDER BY revision')],before)
                    self.assertEqual(await actual.period_report(restored_conn,store,UUID(params['opening']),UUID(params['closing'])),report)
                    self.assertEqual(report['actualFoodCost'],'55.00')
                    with self.assertRaises(asyncpg.PostgresError):await restored_conn.execute('TRUNCATE purchasing.inventory_par_versions')
                finally:await restored_conn.close()
        finally:await self.admin.execute('DROP DATABASE '+restored)
