"""Recovery proof uses fresh synthetic source/target databases, never live data."""
import os
from pathlib import Path
import unittest
from tempfile import TemporaryDirectory
from uuid import UUID,uuid4
from unittest.mock import patch

import asyncpg
from fastapi import FastAPI,HTTPException
import httpx

import actual_inventory_api as actual
import db_pg
import native_backup as backup
import purchase_api as purchases
import test_actual_inventory as counts
import test_actual_inventory_corrections as periods
import test_actual_inventory_scope_bridges as bridges
import test_posted_invoice_corrections as invoices

PG_DUMP=Path(os.getenv('NATIVE_BACKUP_PG_DUMP',''))
EVIDENCE=Path(os.getenv('NATIVE_BACKUP_EVIDENCE',str(counts.native.ROOT.parent/'native-backup-verification')))


class BackupSafetyTests(unittest.TestCase):
    def test_validated_sql_preserves_literal_crlf_and_internal_psql_like_text(self):
        sql = "SELECT 'first\r\n\\restrict InvoiceText\r\nlast';\r\n"
        raw = ("-- dump\n\\restrict OuterGuard123\n" + sql + "\\unrestrict OuterGuard123\n").encode('utf-8')
        with TemporaryDirectory() as directory:
            dump = Path(directory) / 'database.sql'; dump.write_bytes(raw)
            manifest = {'format': 'jaymax-native-sql-backup-v1', 'dump': {
                'filename': 'database.sql', 'bytes': len(raw), 'sha256': backup.digest_file(dump)}}
            restored = backup.validated_sql(directory, manifest)
            self.assertIn(sql, restored)
            self.assertNotIn('OuterGuard123', restored)
            self.assertIn('\\restrict InvoiceText', restored)

    def test_remote_operational_control_and_ambiguous_connections_refused(self):
        for dsn in ('postgresql://test@example.com/native_purchase_test_demo',
                    'postgresql://test@127.0.0.1/operational',
                    'postgresql://test@127.0.0.1/native_purchase_test_control',
                    'postgresql://test@localhost/native_purchase_test_demo',
                    'postgresql://test@127.0.0.1/native_purchase_test_demo?service=remote'):
            with self.assertRaises(backup.BackupError):backup.disposable_connection(dsn)
        self.assertEqual(backup.disposable_connection('postgresql://test@127.0.0.1:55439/native_purchase_test_demo')['database'],'native_purchase_test_demo')


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN') and PG_DUMP.is_file(),'Disposable PG and pg_dump required')
class NativeBackupTests(unittest.IsolatedAsyncioTestCase):
    capture=counts.ActualInventoryTests.capture
    body=counts.ActualInventoryTests.body
    post=counts.ActualInventoryTests.post
    scope=counts.ActualInventoryTests.scope
    count=counts.ActualInventoryTests.count
    pair=counts.ActualInventoryTests.pair
    report=counts.ActualInventoryTests.report
    close=counts.ActualInventoryTests.close
    reopen=periods.CorrectionTests.reopen
    measured=bridges.ScopeBridgeTests.measured
    handoff_preview=bridges.ScopeBridgeTests.handoff_preview
    accept=bridges.ScopeBridgeTests.accept
    plan=invoices.PostedInvoiceCorrectionTests.plan
    correct=invoices.PostedInvoiceCorrectionTests.correct
    initial=invoices.PostedInvoiceCorrectionTests.initial

    async def asyncSetUp(self):
        await invoices.PostedInvoiceCorrectionTests.asyncSetUp(self)
        self.targets=[];self.target_pools=[];self.target_clients=[]
        self.directory=EVIDENCE/('case-'+uuid4().hex[:12])
        self.base=os.environ['NATIVE_PURCHASE_TEST_DSN'].rsplit('/',1)[0]
        self.source=self.base+'/'+self.db
        self.excluded_prep_seeded=False

    async def seed_excluded_prep(self):
        if self.excluded_prep_seeded:return
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO public.prep_logs(store_id,kind,name,produced,total_cost) VALUES('berts','batch','Synthetic excluded prep',999,123)")
        self.excluded_prep_seeded=True

    async def asyncTearDown(self):
        for client in self.target_clients:await client.aclose()
        for pool in self.target_pools:await pool.close()
        for name in self.targets:
            self.assertTrue(name.startswith('native_purchase_test_restore_'))
            await self.admin.execute('DROP DATABASE '+name)
        await counts.ActualInventoryTests.asyncTearDown(self)

    async def target(self):
        name='native_purchase_test_restore_'+uuid4().hex
        await self.admin.execute('CREATE DATABASE '+name);self.targets.append(name)
        return self.base+'/'+name

    async def restored_client(self,dsn):
        pool=await asyncpg.create_pool(dsn,min_size=1,max_size=3,init=db_pg._init_connection);self.target_pools.append(pool)
        app=FastAPI()
        def check(store):
            if store not in ('berts','rudds'):raise HTTPException(404,'Unknown store')
        def actor(request,store,write):
            if request.headers.get('authorization')!='Bearer synthetic-manager':raise HTTPException(401,'Authentication required')
            return 'synthetic-manager'
        app.include_router(purchases.create_router(lambda:pool,check,actor));app.include_router(actual.create_router(lambda:pool,check,actor))
        client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers={'Authorization':'Bearer synthetic-manager'})
        self.target_clients.append(client)
        return client,pool

    async def rich_history(self):
        old,a,b=await self.pair()
        pfg_file,source_pfg,*_=await self.capture(number='RECOVERY-PFG',extra=True,
            overrides={'description_snapshot':'Synthetic multiline food\r\n\\restrict InvoiceText\r\nPreserve every character'})
        pfg=pfg_file['documents'][0]
        self.assertEqual((await self.post(pfg)).status_code,200)
        x=(await self.close((await self.report(a,b)).json())).json()['closure']
        new=(await self.scope(('test_food','other_food')))[0].json()
        opening=await self.measured(new,'2026-10-08',{'test_food':('30','45'),'other_food':('0','0')})
        handoff=(await self.handoff_preview(x,opening)).json();self.assertEqual((await self.accept(handoff)).status_code,200)
        us_file,source_us,*_=await self.capture(vendor='US Foods',number='RECOVERY-US',amounts=('20',),extra=True)
        us=us_file['documents'][0];body=self.body(us,item_code='other_food',received_quantity='1');body['received_date']='2026-10-09'
        self.assertEqual((await self.post(us,body)).status_code,200)
        returned_file,*_=await self.capture(vendor='US Foods',number='RECOVERY-US-RETURN',amounts=('-2',),overrides={'document_type_raw':'Credit'},extra=True)
        returned=returned_file['documents'][0]
        body=self.body(returned,item_code='other_food',movement_kind='physical_return',received_quantity='-1',received_unit='lb',
                       base_units_per_received_unit='1',movement_date='2026-10-12',original_line_id=us['lines'][0]['id'])
        self.assertEqual((await self.post(returned,body)).status_code,200)
        closing=await self.measured(new,'2026-10-15',{'test_food':('20','30'),'other_food':('10','10')})
        y=(await self.close((await self.report(opening,closing)).json())).json()['closure']
        plan=(await self.client.get('/api/pg/actual-inventory/berts/reopen-preview/'+x['id'])).json()
        self.assertEqual((await self.reopen(plan)).status_code,200)
        reissue_file,*_=await self.capture(number='RECOVERY-PFG',amounts=('50',),extra=True);reissue=reissue_file['documents'][0]
        body=self.body(reissue,received_quantity='3');body.update(received_date='2026-10-03',reason='Verified supplier reissue and received date')
        plan=(await self.client.post(f"/api/pg/purchases/berts/documents/{reissue['id']}/correction-preview",json=body)).json()
        corrected=await self.correct(reissue,plan);self.assertEqual(corrected.status_code,200,corrected.text)
        credit_file,*_=await self.capture(number='RECOVERY-PFG-CREDIT',amounts=('-5',),overrides={'document_type_raw':'Credit'},extra=True)
        credit=credit_file['documents'][0]
        body=self.body(credit,movement_kind='price_credit',received_quantity=None,base_units_per_received_unit=None,
            movement_date='2026-10-05',original_line_id=reissue['lines'][0]['id'])
        self.assertEqual((await self.post(credit,body)).status_code,200)
        xx=(await self.close((await self.report(a,b)).json())).json()['closure']
        new_handoff=(await self.handoff_preview(xx,opening)).json();self.assertEqual((await self.accept(new_handoff)).status_code,200)
        yy=(await self.close((await self.report(opening,closing)).json())).json()['closure']
        plan=(await self.client.get('/api/pg/actual-inventory/berts/reopen-preview/'+yy['id'])).json()
        self.assertEqual((await self.reopen(plan)).status_code,200)
        recount=await self.measured(new,'2026-10-15',{'test_food':('20','30'),'other_food':('12','12')},corrects_snapshot_id=closing['header']['id'])
        zz=(await self.close((await self.report(opening,recount)).json())).json()['closure']
        self.assertEqual(xx['report_snapshot']['actualFoodCost'],'60.00')
        self.assertEqual(zz['report_snapshot']['actualFoodCost'],'21.00')
        await self.seed_excluded_prep()
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE public.store_state SET sales_period='{\"dishSales\":{\"synthetic\":999}}'::jsonb WHERE store_id='berts'")
        return {'pfg':pfg,'reissue':reissue,'us':us,'opening':opening,'closing':recount,'oldOpening':a,'oldClosing':b,
                'sourceFiles':[(pfg_file['id'],source_pfg),(us_file['id'],source_us)],'originalClosures':[x,y],
                'correction':corrected.json(),'finalClosures':[xx,zz]}

    async def test_full_recovery_preserves_rows_schema_acl_reports_and_write_guards(self):
        fixture=await self.rich_history()
        paths=['/api/pg/purchases/berts/history','/api/pg/actual-inventory/berts/closed-periods',
               '/api/pg/actual-inventory/berts/scope-handoffs',f"/api/pg/purchases/berts/documents/{fixture['reissue']['id']}/corrections"]
        before={p:(await self.client.get(p)).json() for p in paths}
        report_before=(await self.report(fixture['opening'],fixture['closing'])).json()
        manifest=await backup.create_backup(self.source,PG_DUMP,self.directory)
        self.assertGreater(manifest['tables']['purchasing.import_files']['rows'],0)
        self.assertEqual(manifest['tables']['actual_inventory.period_closures']['rows'],5)
        self.assertEqual(manifest['tables']['actual_inventory.scope_bridges']['rows'],2)
        dsn=await self.target();verified=await backup.verify_restore(dsn,self.directory);self.assertEqual(verified['status'],'verified')
        client,pool=await self.restored_client(dsn)
        for p in paths:self.assertEqual((await client.get(p)).json(),before[p],p)
        report=(await client.get('/api/pg/actual-inventory/berts/report',params={'opening':fixture['opening']['header']['id'],'closing':fixture['closing']['header']['id']})).json()
        self.assertEqual(report,report_before);self.assertEqual(report['actualFoodCost'],'21.00')
        for file_id,source in fixture['sourceFiles']:
            self.assertEqual((await client.get(f'/api/pg/purchases/berts/files/{file_id}/source')).content,source)
        async with pool.acquire() as conn:
            self.assertEqual(await conn.fetchval("SELECT count(*) FROM public.prep_logs WHERE name='Synthetic excluded prep' AND produced=999 AND total_cost=123"),1)
            for table in ('purchasing.corrections','purchasing.document_lines','actual_inventory.period_closures'):
                with self.assertRaises(asyncpg.RaiseError):await conn.execute('DELETE FROM '+table)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.active_period_closures'),2)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.active_scope_bridges'),1)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.pending_reclosures'),0)
        # Native posting still holds closed dates after restore; no partial new mappings.
        original_client=self.client;self.client=client
        try:
            file,*_=await self.capture(number='POST-RESTORE-LATE');self.assertEqual((await self.post(file['documents'][0])).status_code,409)
            held=(await self.plan(fixture['reissue'],received_quantity='4')).json()
            self.assertEqual(held['status'],'held');self.assertTrue(held['affectedPeriods']);self.assertTrue(held['linkedDocuments'])
            self.assertEqual((await self.correct(fixture['reissue'],held)).status_code,409)
            replay_body={**fixture['correction']['correction']['reviewed_plan']['review'],
                'expected_plan_hash':fixture['correction']['correction']['reviewed_plan']['planHash'],
                'expected_initial_batch_id':fixture['correction']['correction']['initial_batch_id'],'expected_correction_id':None}
            replay=await client.post(f"/api/pg/purchases/berts/documents/{fixture['reissue']['id']}/correct",json=replay_body,
                headers={'Idempotency-Key':fixture['correction']['correction']['idempotency_key']})
            self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(replay.json()['correctionId'],fixture['correction']['correctionId'])
        finally:self.client=original_client
        (self.directory/'api-verification.json').write_text(__import__('json').dumps({'status':'verified',
            'reportsEqual':True,'originalBytesEqual':True,'historicalGenerationsEqual':True,'retryAndWriteGuardsPassed':True,
            'actualFoodCostByPeriod':['60.00','21.00'],'fixture':'Invented PFG/US Foods sources only'},indent=2))

    async def test_dump_and_manifest_use_one_exported_snapshot_despite_concurrent_write(self):
        await self.initial()
        async with self.pool.acquire() as conn:old=await conn.fetchval("SELECT revision FROM public.store_state WHERE store_id='berts'")
        original=backup.run_dump
        async def concurrent_dump(executable,args,settings):
            async with self.pool.acquire() as conn:await conn.execute("UPDATE public.store_state SET revision=revision+999 WHERE store_id='berts'")
            return await original(executable,args,settings)
        with patch.object(backup,'run_dump',concurrent_dump):manifest=await backup.create_backup(self.source,PG_DUMP,self.directory)
        dsn=await self.target();self.assertEqual((await backup.verify_restore(dsn,self.directory))['status'],'verified')
        conn=await asyncpg.connect(dsn)
        try:self.assertEqual(await conn.fetchval("SELECT revision FROM public.store_state WHERE store_id='berts'"),old)
        finally:await conn.close()
        async with self.pool.acquire() as conn:self.assertEqual(await conn.fetchval("SELECT revision FROM public.store_state WHERE store_id='berts'"),old+999)

    async def test_damaged_missing_backup_and_nonempty_target_are_refused_before_writes(self):
        await self.initial();await backup.create_backup(self.source,PG_DUMP,self.directory)
        dsn=await self.target();conn=await asyncpg.connect(dsn)
        try:await conn.execute('CREATE TABLE public.synthetic_keep(value integer); INSERT INTO public.synthetic_keep VALUES(77)')
        finally:await conn.close()
        with self.assertRaisesRegex(backup.BackupError,'empty disposable'):await backup.verify_restore(dsn,self.directory)
        conn=await asyncpg.connect(dsn)
        try:self.assertEqual(await conn.fetchval('SELECT value FROM public.synthetic_keep'),77)
        finally:await conn.close()
        empty=await self.target();dump=self.directory/'database.sql';original=dump.read_bytes();dump.write_bytes(original[:-50])
        with self.assertRaisesRegex(backup.BackupError,'checksum'):await backup.verify_restore(empty,self.directory)
        conn=await asyncpg.connect(empty)
        try:self.assertIsNone(await conn.fetchval("SELECT to_regclass('purchasing.import_files')"))
        finally:await conn.close()
        with self.assertRaisesRegex(backup.BackupError,'manifest'):await backup.verify_restore(empty,self.directory/'missing')
        dump.write_bytes(original)
        with self.assertRaisesRegex(backup.BackupError,'different'):await backup.verify_restore(self.source,self.directory)
        with self.assertRaises(FileExistsError):await backup.create_backup(self.source,PG_DUMP,self.directory)

    async def test_invalid_restore_sql_rolls_back_ddl_and_preserves_default_schema(self):
        import json
        await self.initial();await backup.create_backup(self.source,PG_DUMP,self.directory)
        dump=self.directory/'database.sql';sql=backup.validated_sql(self.directory,json.loads((self.directory/'manifest.json').read_text()))
        dump.write_text(sql+'\nSELECT 1/0;\n',encoding='utf-8')
        manifest=json.loads((self.directory/'manifest.json').read_text());manifest['dump'].update(bytes=dump.stat().st_size,sha256=backup.digest_file(dump))
        (self.directory/'manifest.json').write_text(json.dumps(manifest))
        dsn=await self.target()
        with self.assertRaisesRegex(backup.BackupError,'rolled back'):await backup.verify_restore(dsn,self.directory)
        conn=await asyncpg.connect(dsn)
        try:
            self.assertTrue(await conn.fetchval("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='public')"))
            self.assertIsNone(await conn.fetchval("SELECT to_regclass('purchasing.import_files')"))
        finally:await conn.close()

    async def test_data_verification_mismatch_never_claims_verified_recovery(self):
        import json
        await self.initial();await backup.create_backup(self.source,PG_DUMP,self.directory)
        path=self.directory/'manifest.json';manifest=json.loads(path.read_text())
        manifest['tables']['purchasing.import_files']['rows']+=1;path.write_text(json.dumps(manifest))
        dsn=await self.target()
        with self.assertRaisesRegex(backup.BackupError,'did not match'):await backup.verify_restore(dsn,self.directory)
        self.assertFalse((self.directory/'restore-verifications').exists())
        evidence=list(self.directory.glob('verification-failed-*.json'));self.assertEqual(len(evidence),1)
        self.assertEqual(json.loads(evidence[0].read_text())['status'],'verification_failed')
