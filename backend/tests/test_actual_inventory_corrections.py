"""Correction chains use invented data in isolated local PostgreSQL only."""
import asyncio
import os
import unittest
from decimal import Decimal
from uuid import UUID,uuid4

import asyncpg
import httpx
from unittest.mock import patch
import test_actual_inventory as counts
import actual_inventory_api as actual


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PG DSN required')
class CorrectionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=counts.ActualInventoryTests.asyncSetUp
    asyncTearDown=counts.ActualInventoryTests.asyncTearDown
    capture=counts.ActualInventoryTests.capture
    body=counts.ActualInventoryTests.body
    post=counts.ActualInventoryTests.post
    scope=counts.ActualInventoryTests.scope
    count=counts.ActualInventoryTests.count
    pair=counts.ActualInventoryTests.pair
    purchase=counts.ActualInventoryTests.purchase
    report=counts.ActualInventoryTests.report
    close=counts.ActualInventoryTests.close

    async def chain(self):
        scope,a,b=await self.pair()
        self.assertEqual((await self.purchase())[0].status_code,200)
        c,_=await self.count(scope,'2026-10-15',quantity='1',value='30');c=c.json()
        r1=(await self.report(a,b)).json();x=await self.close(r1);self.assertEqual(x.status_code,200,x.text)
        r2=(await self.report(b,c)).json();y=await self.close(r2);self.assertEqual(y.status_code,200,y.text)
        return scope,a,b,c,x.json()['closure'],y.json()['closure']

    async def preview(self,closure,store='berts'):
        return await self.client.get(f'/api/pg/actual-inventory/{store}/reopen-preview/'+closure['id'])

    async def reopen(self,plan,key=None,**extra):
        body={'first_closure_id':plan['firstClosureId'],'expected_plan_hash':plan['planHash'],
              'affected_periods_reviewed':True,'reason':'Verified count correction',**extra}
        return await self.client.post('/api/pg/actual-inventory/berts/reopen',json=body,headers={'Idempotency-Key':key or str(uuid4())})

    async def test_shared_count_correction_preserves_reports_and_recloses_in_order(self):
        scope,a,b,c,x,y=await self.chain()
        plan=(await self.preview(x)).json();self.assertEqual([p['id'] for p in plan['affectedPeriods']],[x['id'],y['id']])
        event=await self.reopen(plan);self.assertEqual(event.status_code,200,event.text)
        replacement,_=await self.count(scope,'2026-10-08',quantity='1',value='30',corrects_snapshot_id=b['header']['id'])
        self.assertEqual(replacement.status_code,200,replacement.text);replacement=replacement.json()
        later=(await self.report(replacement,c)).json();self.assertEqual((await self.close(later)).status_code,409)
        first=(await self.report(a,replacement)).json();self.assertEqual(first['supersedesClosureId'],x['id'])
        xx=await self.close(first);self.assertEqual(xx.status_code,200,xx.text)
        yy=await self.close((await self.report(replacement,c)).json());self.assertEqual(yy.status_code,200,yy.text)
        self.assertEqual(xx.json()['closure']['supersedes_closure_id'],x['id'])
        self.assertEqual(yy.json()['closure']['opening_snapshot_id'],xx.json()['closure']['closing_snapshot_id'])
        self.assertEqual(Decimal(xx.json()['closure']['report_snapshot']['actualFoodCost']),Decimal('70'))
        self.assertEqual(Decimal(yy.json()['closure']['report_snapshot']['actualFoodCost']),Decimal('0'))
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.pending_reclosures'),0)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.active_period_closures'),2)
            self.assertEqual(await conn.fetchval('SELECT report_snapshot FROM actual_inventory.period_closures WHERE id=$1',UUID(x['id'])),x['report_snapshot'])
        history=(await self.client.get('/api/pg/actual-inventory/berts/closed-periods')).json()
        self.assertEqual(sum(h['period_status']=='superseded' for h in history),2)
        self.assertEqual(sum(h['period_status']=='closed' for h in history),2)

    async def test_late_purchase_and_linked_credit_allow_unchanged_counts_reclose(self):
        _,a,b,c,x,y=await self.chain()
        blocked,doc=await self.purchase();self.assertEqual(blocked.status_code,409)
        self.assertEqual((await self.reopen((await self.preview(x)).json())).status_code,200)
        late=await self.post(doc);self.assertEqual(late.status_code,200,late.text)
        file,*_=await self.capture(amounts=('-5',),overrides={'document_type_raw':'Credit'})
        credit=file['documents'][0]
        credit_body=self.body(credit,movement_kind='price_credit',received_quantity=None,base_units_per_received_unit=None,
                              original_line_id=doc['lines'][0]['id'],movement_date='2026-10-05')
        self.assertEqual((await self.post(credit,credit_body)).status_code,200)
        report=(await self.report(a,b)).json();self.assertEqual(Decimal(report['actualFoodCost']),Decimal('90'))
        self.assertEqual((await self.close(report)).status_code,200)
        self.assertEqual((await self.close((await self.report(b,c)).json())).status_code,200)
        self.assertEqual((await self.purchase())[0].status_code,409)
        self.assertEqual(x['report_snapshot']['actualFoodCost'],'55.00')

    async def test_reopen_is_atomic_idempotent_and_frozen(self):
        *_,x,y=await self.chain();plan=(await self.preview(x)).json();key=str(uuid4())
        p,q=await asyncio.gather(self.reopen(plan,key),self.reopen(plan,key))
        self.assertEqual(p.status_code,200,p.text);self.assertEqual(p.json(),q.json())
        self.assertEqual((await self.reopen(plan,key,reason='Changed reason')).status_code,409)
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.reopen_events'),1)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.active_period_closures'),0)
            for action in ('UPDATE actual_inventory.reopen_events SET reason=\'rewritten\'','DELETE FROM actual_inventory.reopen_events'):
                with self.assertRaises(asyncpg.RaiseError):await conn.execute(action)

    async def test_stale_preview_after_new_close_rolls_back(self):
        scope,a,b=await self.pair();x=await self.close((await self.report(a,b)).json());x=x.json()['closure']
        plan=(await self.preview(x)).json()
        c,_=await self.count(scope,'2026-10-15',quantity='1',value='30')
        self.assertEqual((await self.close((await self.report(b,c.json())).json())).status_code,200)
        self.assertEqual((await self.reopen(plan)).status_code,409)
        async with self.pool.acquire() as conn:self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.reopen_events'),0)
        self.assertEqual(len((await self.preview(x)).json()['affectedPeriods']),2)

    async def test_opening_shared_with_active_previous_period_is_protected(self):
        scope,a,b,c,x,y=await self.chain()
        self.assertEqual((await self.reopen((await self.preview(y)).json())).status_code,200)
        wrong,_=await self.count(scope,'2026-10-08',quantity='1',value='30',corrects_snapshot_id=b['header']['id'])
        self.assertEqual(wrong.status_code,409)
        corrected,_=await self.count(scope,'2026-10-15',quantity='0.5',value='15',corrects_snapshot_id=c['header']['id'])
        self.assertEqual(corrected.status_code,200,corrected.text)
        self.assertEqual((await self.close((await self.report(b,corrected.json())).json())).status_code,200)

    async def test_recounts_cannot_fork_shift_boundaries_or_replace_unrelated_counts(self):
        scope,a,b,c,x,y=await self.chain();await self.reopen((await self.preview(x)).json())
        moved,_=await self.count(scope,'2026-10-09',corrects_snapshot_id=b['header']['id']);self.assertEqual(moved.status_code,422)
        first,_=await self.count(scope,'2026-10-08',quantity='1',value='30',corrects_snapshot_id=b['header']['id'])
        fork,_=await self.count(scope,'2026-10-08',corrects_snapshot_id=b['header']['id']);self.assertEqual(fork.status_code,409)
        unrelated,_=await self.count(scope,'2026-10-08',quantity='1',value='30')
        self.assertEqual((await self.close((await self.report(a,unrelated.json())).json())).status_code,409)
        self.assertEqual((await self.close((await self.report(a,first.json())).json())).status_code,200)

    async def test_replacement_can_itself_be_reopened_without_double_counting_history(self):
        _,a,b,c,x,y=await self.chain();await self.reopen((await self.preview(x)).json())
        xx=await self.close((await self.report(a,b)).json());xx=xx.json()['closure']
        yy=await self.close((await self.report(b,c)).json());yy=yy.json()['closure']
        plan=(await self.preview(xx)).json();self.assertEqual([p['id'] for p in plan['affectedPeriods']],[xx['id'],yy['id']])
        await self.reopen(plan)
        self.assertEqual((await self.close((await self.report(a,b)).json())).status_code,200)
        self.assertEqual((await self.close((await self.report(b,c)).json())).status_code,200)
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.period_closures'),6)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.active_period_closures'),2)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.pending_reclosures'),0)

    async def test_permissions_location_reason_and_database_suffix_guards(self):
        *_,x,y=await self.chain();plan=(await self.preview(x)).json()
        self.assertEqual((await self.preview(x,'rudds')).status_code,409)
        self.assertEqual((await self.reopen(plan,reason=' ')).status_code,422)
        self.assertEqual((await self.reopen(plan,affected_periods_reviewed=False)).status_code,422)
        async with self.pool.acquire() as conn:
            with self.assertRaises(asyncpg.RaiseError):
                await conn.execute('''INSERT INTO actual_inventory.reopen_events
                  (store_id,first_closure_id,closure_ids,reason,plan_snapshot,request_key,request_fingerprint,reopened_by)
                  VALUES('berts',$1,$2,'partial',$3,$4,$5,'synthetic')''',UUID(x['id']),[UUID(x['id'])],plan,uuid4(),b'0'*32)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.active_period_closures'),2)
        import server
        previous=server.db_pg._pool;server.db_pg._pool=self.pool
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://test') as client:
                for role,locations,expected in [('readonly',['berts'],403),('staff',['berts'],403),('manager',['rudds'],403),('manager',['berts'],200)]:
                    token=server._token({'id':'synthetic-manager','email':'test@example.invalid','role':role,'locations':locations})
                    r=await client.get('/api/pg/actual-inventory/berts/reopen-preview/'+x['id'],headers={'Authorization':'Bearer '+token})
                    self.assertEqual(r.status_code,expected,r.text)
        finally:server.db_pg._pool=previous

    async def test_delayed_close_retry_reports_history_after_reopening(self):
        _,a,b=await self.pair();report=(await self.report(a,b)).json();key=str(uuid4())
        original=await self.close(report,key);original=original.json()['closure']
        await self.reopen((await self.preview(original)).json())
        replay=await self.close(report,key)
        self.assertEqual(replay.status_code,200);self.assertEqual(replay.json()['status'],'historical')
        self.assertEqual(replay.json()['closure']['id'],original['id'])

    async def test_concurrent_new_close_and_reopen_cannot_omit_a_period(self):
        scope,a,b=await self.pair();first=await self.close((await self.report(a,b)).json());first=first.json()['closure']
        plan=(await self.preview(first)).json()
        c,_=await self.count(scope,'2026-10-15',quantity='1',value='30');report=(await self.report(b,c.json())).json()
        reopened,closed=await asyncio.gather(self.reopen(plan),self.close(report))
        self.assertIn((reopened.status_code,closed.status_code),((200,409),(409,200)))
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.active_period_closures'),0 if reopened.status_code==200 else 2)


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PG DSN required')
class CorrectionUpgradeTests(unittest.IsolatedAsyncioTestCase):
    apply_corrections=False
    asyncSetUp=counts.ActualInventoryTests.asyncSetUp
    asyncTearDown=counts.ActualInventoryTests.asyncTearDown

    async def test_upgrade_preserves_existing_count_and_closed_report_facts(self):
        scope_body=actual.ScopeInput(scope_kind='purchased_items_only',valuation_method='explicit_count_values',note='Verified synthetic scope',
            items=[{'item_code':'test_food','base_unit':'lb','location_notes':'All raw stock'}])
        scope_id=await actual.configure_scope(self.pool,'berts','synthetic',scope_body,uuid4())
        async def count(day,quantity,value):
            body=actual.CountInput(scope_id=scope_id,count_date=day,timing='before_receipts',note='Measured synthetic inventory',
              lines=[{'item_code':'test_food','counted_quantity':quantity,'counted_unit':'lb','base_units_per_counted_unit':'1',
                      'inventory_value':value,'confirmed':True,'note':'Verified quantity and explicit value'}])
            return await actual.save_count(self.pool,'berts','synthetic',body,uuid4())
        a=await count('2026-10-01','40','60');b=await count('2026-10-08','30','45')
        saved={'actualFoodCost':'15.00','reportHash':'a'*64,'rows':[{'itemCode':'test_food','actualFoodCost':'15.00'}]}
        async with self.pool.acquire() as conn:
            old_id=await conn.fetchval('''INSERT INTO actual_inventory.period_closures
             (store_id,opening_snapshot_id,closing_snapshot_id,period_start,period_end_exclusive,report_snapshot,request_key,request_fingerprint,closed_by)
             VALUES('berts',$1,$2,'2026-10-01','2026-10-08',$3,$4,$5,'synthetic') RETURNING id''',a,b,saved,uuid4(),b'0'*32)
            await conn.execute((counts.native.ROOT/'migrations/20261004_actual_inventory_corrections.sql').read_text())
            await conn.execute((counts.native.ROOT/'migrations/20261004_actual_inventory_scope_bridges.sql').read_text())
            self.assertEqual(await conn.fetchval('SELECT report_snapshot FROM actual_inventory.active_period_closures WHERE id=$1',old_id),saved)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.count_lines'),2)
        report=await self.client.get('/api/pg/actual-inventory/berts/report',params={'opening':str(a),'closing':str(b)})
        self.assertEqual(report.status_code,200,report.text);self.assertEqual(report.json()['actualFoodCost'],'15.00')
