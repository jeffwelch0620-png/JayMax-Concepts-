"""Invented staff counts, real API boundaries, concurrency and isolated recovery."""
import asyncio
import json
import os
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import unittest
from uuid import UUID, uuid4

import asyncpg
import httpx
import native_backup as backup
import test_native_order_receiving as fixtures


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'), 'Disposable PostgreSQL required')
class StaffCountDraftTests(unittest.IsolatedAsyncioTestCase):
    scope = fixtures.NativeOrderReceivingTests.scope
    units = fixtures.NativeOrderReceivingTests.units
    count = fixtures.NativeOrderReceivingTests.count
    target = fixtures.NativeOrderReceivingTests.target
    restored_client = fixtures.NativeOrderReceivingTests.restored_client

    async def asyncSetUp(self):
        await fixtures.NativeOrderReceivingTests.asyncSetUp(self)
        async with self.pool.acquire() as conn:
            await conn.execute((fixtures.recovery.counts.native.ROOT/'migrations/20261005_staff_count_drafts.sql').read_text())
            await conn.execute("INSERT INTO staff_pins(store_id,pin) VALUES('berts','4826'),('rudds','7193')")
        self.scope_record = (await self.scope())[0].json()
        self.assertEqual((await self.units('count'))[0].status_code, 200)
        import server
        self.server=server; self.previous_pool=server.db_pg._pool; server.db_pg._pool=self.pool
        owner=server._token({'id':'invented-owner','email':'owner@example.invalid','role':'owner','locations':[]})
        self.real=httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app,raise_app_exceptions=False),base_url='http://test',headers={'Authorization':'Bearer '+owner})
        self.pin_client=httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app,raise_app_exceptions=False),base_url='http://test')

    async def asyncTearDown(self):
        await self.real.aclose(); await self.pin_client.aclose(); self.server.db_pg._pool=self.previous_pool
        await fixtures.NativeOrderReceivingTests.asyncTearDown(self)

    async def issue(self, key=None, **changes):
        body={'scope_id':self.scope_record['header']['id'],'count_date':'2026-10-05','timing':'before_receipts','note':'Invented full physical count, all raw storage',**changes}
        return await self.real.post('/api/pg/actual-inventory/berts/staff-sheets',json=body,headers={'Idempotency-Key':key or str(uuid4())}),body

    async def submit(self, review, quantity='3', key=None, **changes):
        body={'pin':'4826','expected_review_hash':review['reviewHash'],'counter_name':'Invented Counter','note':'Invented physical measurement',
              'lines':[{'item_code':'test_food','counted_quantity':quantity,'note':'All raw storage measured'}],**changes}
        response=await self.pin_client.post(f"/api/pg/staff/berts/count-drafts/{review['sheet']['id']}/submit",json=body,headers={'Idempotency-Key':key or str(uuid4())})
        return response,body

    async def decision(self, review, key=None, **changes):
        body={'expected_review_hash':review['reviewHash'],'decision':'accepted','quantities_reviewed':True,'note':'Reviewed physical quantity and explicit total value',
              'values':[{'item_code':'test_food','inventory_value':'45.00','confirmed':True,'note':'Invented explicit total inventory value'}],**changes}
        return await self.real.post(f"/api/pg/actual-inventory/berts/staff-sheets/{review['sheet']['id']}/decision",json=body,headers={'Idempotency-Key':key or str(uuid4())}),body

    async def current(self):
        response=await self.real.get('/api/pg/actual-inventory/berts/staff-sheets')
        self.assertEqual(response.status_code,200,response.text)
        return response.json()[0]

    async def submitted(self):
        issued=(await self.issue())[0]; self.assertEqual(issued.status_code,200,issued.text)
        response=(await self.submit(issued.json()))[0]; self.assertEqual(response.status_code,200,response.text)
        return response.json()['review']

    async def test_quantities_are_separate_and_acceptance_is_explicit_and_idempotent(self):
        issue_key=str(uuid4()); issued,body=await self.issue(key=issue_key); self.assertEqual(issued.status_code,200,issued.text)
        retry,_=await self.issue(key=issue_key); self.assertEqual(retry.json()['sheet']['id'],issued.json()['sheet']['id'])
        self.assertEqual((await self.issue(key=issue_key,note='Changed request'))[0].status_code,409)
        submit_key=str(uuid4()); saved,_=await self.submit(issued.json(),key=submit_key); self.assertEqual(saved.status_code,200,saved.text)
        repeat,_=await self.submit(issued.json(),key=submit_key); self.assertEqual(repeat.json()['submission']['id'],saved.json()['submission']['id'])
        self.assertEqual((await self.submit(issued.json(),quantity='4',key=submit_key))[0].status_code,409)
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.count_snapshots'),0)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.actual_purchase_facts'),0)
        decision_key=str(uuid4()); result,_=await self.decision(saved.json()['review'],key=decision_key)
        self.assertEqual(result.status_code,200,result.text)
        count=result.json()['count']; self.assertEqual(count['header']['status'],'complete')
        self.assertEqual(count['lines'][0]['base_quantity'],'60'); self.assertEqual(count['lines'][0]['inventory_value'],'45.00')
        self.assertEqual(count['header']['counted_by'],'invented-owner')
        repeat,_=await self.decision(saved.json()['review'],key=decision_key)
        self.assertEqual(repeat.json()['count']['header']['id'],count['header']['id'])
        self.assertEqual((await self.decision(saved.json()['review'],key=decision_key,note='Changed'))[0].status_code,409)
        self.assertEqual((await self.pin_client.post('/api/pg/staff/berts/count-drafts',json={'pin':'4826'})).json(),[])
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.count_snapshots'),1)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM purchasing.actual_purchase_facts'),0)

    async def test_partial_zero_invalid_and_staff_value_or_conversion_injection(self):
        review=(await self.issue())[0].json()
        for quantity in ('-1','NaN','Infinity'):
            self.assertEqual((await self.submit(review,quantity=quantity))[0].status_code,422)
        for injected in ('inventory_value','base_units_per_counted_unit','counted_unit'):
            line={'item_code':'test_food','counted_quantity':'3','note':'Measured',injected:'99'}
            self.assertEqual((await self.submit(review,lines=[line]))[0].status_code,422)
        partial=(await self.submit(review,quantity=None))[0].json()['review']
        self.assertEqual((await self.decision(partial))[0].status_code,422)
        zero=(await self.submit(partial,quantity='0'))[0].json()['review']
        self.assertEqual((await self.decision(zero))[0].status_code,422)
        values=[{'item_code':'test_food','inventory_value':'0','confirmed':True,'note':'Measured empty locations'}]
        accepted=(await self.decision(zero,values=values))[0]
        self.assertEqual(accepted.status_code,200,accepted.text); self.assertEqual(accepted.json()['count']['lines'][0]['base_quantity'],'0')

    async def test_stale_review_and_concurrent_submissions_and_acceptances(self):
        review=(await self.issue())[0].json()
        responses=await asyncio.gather(self.submit(review,quantity='3'),self.submit(review,quantity='4'))
        self.assertEqual(sorted(r[0].status_code for r in responses),[200,409])
        current=await self.current()
        next_revision=(await self.submit(current,quantity='5'))[0].json()['review']
        self.assertEqual((await self.decision(current))[0].status_code,409)
        responses=await asyncio.gather(self.decision(next_revision),self.decision(next_revision))
        self.assertEqual(sorted(r[0].status_code for r in responses),[200,409])
        saved=next(r[0].json() for r in responses if r[0].status_code==200)
        self.assertEqual(saved['count']['lines'][0]['base_quantity'],'100')
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.staff_submissions'),2)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.count_snapshots'),1)

    async def test_unit_revisions_and_catalog_changes_hold_drafts_and_allow_rejection(self):
        review=await self.submitted()
        self.assertEqual((await self.units('count',factor='20'))[0].status_code,200)
        self.assertEqual((await self.decision(review))[0].status_code,409)
        current=await self.current(); self.assertTrue(current['errors'])
        self.assertEqual((await self.submit(current))[0].status_code,409)
        rejected=(await self.decision(current,decision='rejected',values=[]))[0]
        self.assertEqual(rejected.status_code,200,rejected.text); self.assertIsNone(rejected.json()['count'])
        issued=(await self.issue())[0]; self.assertEqual(issued.status_code,200,issued.text)
        async with self.pool.acquire() as conn: await conn.execute("UPDATE store_items SET count_unit='bag' WHERE store_id='berts' AND item_code='test_food'")
        self.assertEqual((await self.submit(issued.json()))[0].status_code,409)

    async def test_scope_changes_unverified_units_and_duplicate_boundaries_are_held(self):
        issued=(await self.issue())[0]; self.assertEqual((await self.issue())[0].status_code,409)
        changed=(await self.scope())[0].json(); self.scope_record=changed
        self.assertEqual((await self.submit(issued.json()))[0].status_code,409)
        async with self.pool.acquire() as conn: await conn.execute("UPDATE store_items SET base_per_count_unit=7 WHERE store_id='berts' AND item_code='test_food'")
        self.assertEqual((await self.issue())[0].status_code,409)
        self.assertEqual((await self.units('count',factor='7'))[0].status_code,200)
        issued=(await self.issue())[0]; self.assertEqual(issued.status_code,200,issued.text)
        response=(await self.count(changed,'2026-10-05'))[0]; self.assertEqual(response.status_code,200,response.text)
        self.assertEqual((await self.submit(issued.json()))[0].status_code,409)

    async def test_acceptance_rolls_back_both_count_and_decision_when_review_write_fails(self):
        review=await self.submitted(); key=str(uuid4())
        async with self.pool.acquire() as conn:
            revision=await conn.fetchval("SELECT revision FROM store_state WHERE store_id='berts'")
            await conn.execute("CREATE FUNCTION public.synthetic_fail_decision() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Invented write failure'; END $$; CREATE TRIGGER synthetic_failure BEFORE INSERT ON actual_inventory.staff_decisions FOR EACH ROW EXECUTE FUNCTION public.synthetic_fail_decision()")
        failed,_=await self.decision(review,key=key); self.assertEqual(failed.status_code,500)
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.count_snapshots'),0)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.staff_decisions'),0)
            self.assertEqual(await conn.fetchval("SELECT revision FROM store_state WHERE store_id='berts'"),revision)
            await conn.execute('DROP TRIGGER synthetic_failure ON actual_inventory.staff_decisions; DROP FUNCTION public.synthetic_fail_decision()')
        self.assertEqual((await self.decision(review,key=key))[0].status_code,200)

    async def test_real_authorization_locations_and_disabled_flags(self):
        review=(await self.issue())[0].json()
        for pin in ('','bad','7193'):
            self.assertEqual((await self.pin_client.post('/api/pg/staff/berts/count-drafts',json={'pin':pin})).status_code,403)
        for role,locations,expected in [('staff',['berts'],200),('manager',['rudds'],403),('readonly',['berts'],403)]:
            token=self.server._token({'id':'invented-'+role,'email':role+'@example.invalid','role':role,'locations':locations})
            headers={'Authorization':'Bearer '+token}
            listing=await self.pin_client.post('/api/pg/staff/berts/count-drafts',json={'pin':'4826'},headers=headers)
            self.assertEqual(listing.status_code,expected,listing.text)
            if role=='staff':
                response=await self.pin_client.post('/api/pg/actual-inventory/berts/staff-sheets',json={'scope_id':review['sheet']['scope_id'],'count_date':'2026-10-06','timing':'before_receipts','note':'Forbidden'},headers={**headers,'Idempotency-Key':str(uuid4())})
                self.assertEqual(response.status_code,403)
                body={'expected_review_hash':review['reviewHash'],'counter_name':'Invented staff','note':'Measured','lines':[{'item_code':'test_food','counted_quantity':'2'}]}
                response=await self.pin_client.post(f"/api/pg/staff/berts/count-drafts/{review['sheet']['id']}/submit",json=body,headers={**headers,'Idempotency-Key':str(uuid4())})
                self.assertEqual(response.status_code,200,response.text)
        wrong=await self.pin_client.post(f"/api/pg/staff/rudds/count-drafts/{review['sheet']['id']}/submit",json={'pin':'7193','expected_review_hash':review['reviewHash'],'counter_name':'Counter','note':'Wrong store','lines':[{'item_code':'test_food','counted_quantity':'2'}]},headers={'Idempotency-Key':str(uuid4())})
        self.assertEqual(wrong.status_code,404)
        with patch.dict(os.environ,{'ACTUAL_INVENTORY_ENABLED':'false'}):
            self.assertEqual((await self.real.get('/api/pg/actual-inventory/berts/staff-sheets')).status_code,503)

    async def test_immutable_audit_and_precise_verified_conversion(self):
        self.assertEqual((await self.units('count',factor='20.000000000001'))[0].status_code,200)
        review=await self.submitted(); accepted=(await self.decision(review))[0]
        self.assertEqual(accepted.status_code,200,accepted.text)
        self.assertEqual(accepted.json()['count']['lines'][0]['base_quantity'],'60.000000000003')
        async with self.pool.acquire() as conn:
            for table in ('staff_sheets','staff_submissions','staff_decisions'):
                with self.assertRaises(asyncpg.RaiseError): await conn.execute('DELETE FROM actual_inventory.'+table)
                with self.assertRaises(asyncpg.RaiseError): await conn.execute('UPDATE actual_inventory.'+table+" SET note='Changed'")
                self.assertFalse(await conn.fetchval('SELECT has_table_privilege($1,$2,$3)','public','actual_inventory.'+table,'SELECT'))

    async def test_shared_catalog_edit_is_resolved_before_manager_acceptance(self):
        review=await self.submitted()
        writer=await self.pool.acquire(); transaction=writer.transaction(); await transaction.start()
        task=None
        try:
            await writer.execute("UPDATE items SET pack_count=9 WHERE code='test_food'")
            task=asyncio.create_task(self.decision(review))
            done,_=await asyncio.wait({task},timeout=.1)
            self.assertFalse(done,'Acceptance must wait for a shared catalog edit to resolve')
            await transaction.commit(); transaction=None
            response,_=await asyncio.wait_for(task,10)
            self.assertEqual(response.status_code,409,response.text)
            async with self.pool.acquire() as conn:
                self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.count_snapshots'),0)
        finally:
            if transaction is not None: await transaction.rollback()
            if task and not task.done(): await task
            await self.pool.release(writer)

    async def test_isolated_backup_restores_drafts_decisions_and_accounting_count(self):
        review=await self.submitted()
        review=(await self.submit(review,quantity='4'))[0].json()['review']
        accepted=(await self.decision(review))[0]; self.assertEqual(accepted.status_code,200,accepted.text)
        manifest=await backup.create_backup(self.source,fixtures.recovery.PG_DUMP,self.directory)
        destination=await self.target(); verified=await backup.verify_restore(destination,self.directory)
        self.assertEqual(verified['status'],'verified')
        _,pool=await self.restored_client(destination)
        import staff_count_drafts as drafts
        async with pool.acquire() as conn:
            restored=await drafts.detail(conn,'berts',UUID(review['sheet']['id']))
            self.assertEqual(restored,accepted.json()['review'])
            count=await self.server.actual_inventory_api.get_count(conn,'berts',UUID(restored['decision']['snapshot_id']))
            self.assertEqual(count['lines'][0]['base_quantity'],Decimal(80))
        evidence={'status':'verified','scope':'Invented staff count only; isolated loopback restore',
                  'backup_directory':str(self.directory),
                  'tables':{k:v for k,v in manifest['tables'].items() if k.startswith('actual_inventory.staff_')},
                  'dump':manifest['dump'],'restored_accounting_count':accepted.json()['count']['header']['id'],
                  'staff_submission_revisions':len(restored['history'])}
        (fixtures.recovery.counts.native.ROOT.parent/'staff-count-restore-evidence.json').write_text(json.dumps(evidence,indent=2))
