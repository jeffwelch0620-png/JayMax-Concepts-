"""Scope handoffs retain accounting facts in synthetic disposable PostgreSQL."""
import asyncio
import os
import unittest
from uuid import UUID,uuid4
import asyncpg
import httpx
import test_actual_inventory as counts
import test_actual_inventory_corrections as corrections


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PG DSN required')
class ScopeBridgeTests(unittest.IsolatedAsyncioTestCase):
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
    reopen=corrections.CorrectionTests.reopen
    preview=corrections.CorrectionTests.preview
    chain=corrections.CorrectionTests.chain

    async def measured(self,scope,day,balances,timing='before_receipts',**extra):
        body={'scope_id':scope['header']['id'],'count_date':day,'timing':timing,'note':'Verified synthetic boundary count',
              'lines':[{'item_code':i['item_code'],'counted_quantity':balances[i['item_code']][0],
                 'inventory_value':balances[i['item_code']][1],
                 'counted_unit':'case' if len(balances[i['item_code']])>2 else 'lb',
                 'base_units_per_counted_unit':balances[i['item_code']][2] if len(balances[i['item_code']])>2 else '1',
                 'confirmed':balances[i['item_code']][0] is not None and balances[i['item_code']][1] is not None,
                 'note':'Verified quantity, conversion and explicit value'} for i in scope['items']],**extra}
        result=await self.client.post('/api/pg/actual-inventory/berts/counts',json=body,headers={'Idempotency-Key':str(uuid4())})
        self.assertEqual(result.status_code,200,result.text)
        return result.json()

    async def candidate(self):
        old,a,b=await self.pair();self.assertEqual((await self.purchase())[0].status_code,200)
        x=await self.close((await self.report(a,b)).json());self.assertEqual(x.status_code,200,x.text)
        newer,_=await self.scope(('test_food','other_food'));newer=newer.json()
        target=await self.measured(newer,'2026-10-08',{'test_food':('15','45','2'),'other_food':('0','0')})
        return old,a,b,x.json()['closure'],newer,target

    async def handoff_preview(self,anchor,target,store='berts'):
        return await self.client.get(f'/api/pg/actual-inventory/{store}/scope-handoff-preview/'+anchor['id'],
            params={'target_count':target['header']['id']})

    async def accept(self,plan,key=None,**extra):
        body={'anchor_closure_id':plan['anchorClosureId'],'target_opening_id':plan['newOpeningSnapshotId'],
              'expected_plan_hash':plan['planHash'],'items_reviewed':True,'note':'Verified full item and value handoff',**extra}
        return await self.client.post('/api/pg/actual-inventory/berts/scope-handoffs',json=body,headers={'Idempotency-Key':key or str(uuid4())})

    async def test_add_zero_item_carries_value_and_closes_next_scope_with_new_purchase(self):
        _,a,b,x,newer,target=await self.candidate()
        plan=(await self.handoff_preview(x,target)).json();self.assertEqual(plan['status'],'ready',plan)
        self.assertEqual(plan['oldValue'],plan['newValue']);self.assertEqual(plan['oldValue'],'45.00')
        self.assertEqual({r['itemCode']:r['change'] for r in plan['rows']},{'test_food':'carried','other_food':'added'})
        accepted=await self.accept(plan);self.assertEqual(accepted.status_code,200,accepted.text)
        self.assertEqual((await self.purchase(received='2026-10-08',item_code='other_food'))[0].status_code,200)
        closing=await self.measured(newer,'2026-10-15',{'test_food':('20','30'),'other_food':('30','30')})
        report=(await self.report(target,closing)).json();self.assertEqual(report['actualFoodCost'],'25.00')
        self.assertEqual(report['openingBridgeId'],accepted.json()['bridge']['id'])
        closed=await self.close(report);self.assertEqual(closed.status_code,200,closed.text)
        self.assertEqual(closed.json()['closure']['opening_bridge_id'],report['openingBridgeId'])
        self.assertEqual(closed.json()['closure']['report_snapshot']['openingScopeHandoff'],plan)
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT report_snapshot FROM actual_inventory.period_closures WHERE id=$1',UUID(x['id'])),x['report_snapshot'])

    async def test_remove_zero_item_and_hold_future_out_of_scope_purchase(self):
        old,_=await self.scope(('test_food','other_food'));old=old.json()
        a=await self.measured(old,'2026-10-01',{'test_food':('40','60'),'other_food':('0','0')})
        b=await self.measured(old,'2026-10-08',{'test_food':('30','45'),'other_food':('0','0')})
        x=await self.close((await self.report(a,b)).json());x=x.json()['closure']
        new,_=await self.scope();new=new.json();target=await self.measured(new,'2026-10-08',{'test_food':('30','45')})
        plan=(await self.handoff_preview(x,target)).json();self.assertEqual(plan['status'],'ready')
        self.assertEqual(next(r for r in plan['rows'] if r['itemCode']=='other_food')['change'],'removed')
        self.assertEqual((await self.accept(plan)).status_code,200)
        c=await self.measured(new,'2026-10-15',{'test_food':('20','30')})
        self.assertEqual((await self.close((await self.report(target,c)).json())).status_code,200)
        d=await self.measured(new,'2026-10-22',{'test_food':('10','15')})
        self.assertEqual((await self.purchase(received='2026-10-16',item_code='other_food'))[0].status_code,200)
        report=(await self.report(c,d)).json();self.assertEqual(report['status'],'incomplete')
        self.assertIsNone(report['actualFoodCost']);self.assertEqual((await self.close(report)).status_code,409)

    async def test_nonzero_added_or_missing_item_is_held_without_zero_guess(self):
        _,_,_,x,new,target=await self.candidate()
        for quantity,value in [('1','0'),('1','5'),(None,None)]:
            bad=await self.measured(new,'2026-10-08',{'test_food':('30','45'),'other_food':(quantity,value)})
            plan=(await self.handoff_preview(x,bad)).json();self.assertEqual(plan['status'],'held')
            self.assertEqual((await self.accept(plan)).status_code,409)
        async with self.pool.acquire() as conn:self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.scope_bridges'),0)

    async def test_nonzero_removed_stock_cannot_disappear(self):
        old,_=await self.scope(('test_food','other_food'));old=old.json()
        a=await self.measured(old,'2026-10-01',{'test_food':('40','60'),'other_food':('5','10')})
        b=await self.measured(old,'2026-10-08',{'test_food':('30','45'),'other_food':('5','0')})
        x=await self.close((await self.report(a,b)).json());x=x.json()['closure']
        new,_=await self.scope();new=new.json();target=await self.measured(new,'2026-10-08',{'test_food':('30','45')})
        plan=(await self.handoff_preview(x,target)).json();self.assertEqual(plan['status'],'held')
        self.assertTrue(any('keep this item' in e for e in plan['errors']));self.assertEqual((await self.accept(plan)).status_code,409)

    async def test_shared_quantity_or_value_differences_are_held_even_with_same_total(self):
        old,_=await self.scope(('test_food','other_food'));old=old.json()
        a=await self.measured(old,'2026-10-01',{'test_food':('40','60'),'other_food':('10','10')})
        b=await self.measured(old,'2026-10-08',{'test_food':('30','45'),'other_food':('10','10')})
        x=await self.close((await self.report(a,b)).json());x=x.json()['closure']
        new,_=await self.scope(('test_food','other_food'));new=new.json()
        for balances in [{'test_food':('30','44'),'other_food':('10','11')},{'test_food':('29','45'),'other_food':('10','10')}]:
            target=await self.measured(new,'2026-10-08',balances);plan=(await self.handoff_preview(x,target)).json()
            self.assertEqual(plan['status'],'held');self.assertEqual((await self.accept(plan)).status_code,409)

    async def test_physical_boundary_and_newer_scope_are_required(self):
        old,_,b,x,new,target=await self.candidate()
        for day,timing in [('2026-10-09','before_receipts'),('2026-10-08','after_receipts')]:
            bad=await self.measured(new,day,{'test_food':('30','45'),'other_food':('0','0')},timing=timing)
            self.assertEqual((await self.handoff_preview(x,bad)).json()['status'],'held')
        self.assertEqual((await self.handoff_preview(x,b)).json()['status'],'held')
        self.assertEqual((await self.handoff_preview(x,target,'rudds')).status_code,409)

    async def test_accept_retry_concurrency_and_immutable_handoff(self):
        *_,x,new,target=await self.candidate();plan=(await self.handoff_preview(x,target)).json();key=str(uuid4())
        p,q=await asyncio.gather(self.accept(plan,key),self.accept(plan,key));self.assertEqual(p.status_code,200,p.text);self.assertEqual(p.json(),q.json())
        self.assertEqual((await self.accept(plan,key,note='Changed body')).status_code,409)
        self.assertEqual((await self.accept(plan)).status_code,409)
        async with self.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.scope_bridges'),1)
            with self.assertRaises(asyncpg.RaiseError):await conn.execute('DELETE FROM actual_inventory.scope_bridges')

    async def test_anchor_change_makes_preview_stale_without_writing_handoff(self):
        old,_,b,x,new,target=await self.candidate();plan=(await self.handoff_preview(x,target)).json()
        c,_=await self.count(old,'2026-10-15',quantity='1',value='30')
        self.assertEqual((await self.close((await self.report(b,c.json())).json())).status_code,200)
        self.assertEqual((await self.accept(plan)).status_code,409)
        async with self.pool.acquire() as conn:self.assertEqual(await conn.fetchval('SELECT count(*) FROM actual_inventory.scope_bridges'),0)

    async def test_accepted_handoff_cannot_be_bypassed_or_recounted_while_active(self):
        old,_,b,x,new,target=await self.candidate();await self.accept((await self.handoff_preview(x,target)).json())
        wrong=await self.client.post('/api/pg/actual-inventory/berts/counts',json={
            'scope_id':new['header']['id'],'count_date':'2026-10-08','timing':'before_receipts','note':'Attempted recount',
            'corrects_snapshot_id':target['header']['id'],'lines':[dict(item_code=l['item_code'],counted_quantity=l['counted_quantity'],
                counted_unit=l['counted_unit'],base_units_per_counted_unit=l['base_units_per_counted_unit'],inventory_value=l['inventory_value'],
                confirmed=True,note='Confirmed') for l in target['lines']]},headers={'Idempotency-Key':str(uuid4())})
        self.assertEqual(wrong.status_code,409)
        c,_=await self.count(old,'2026-10-15',quantity='1',value='30')
        self.assertEqual((await self.close((await self.report(b,c.json())).json())).status_code,409)
        alternate=await self.measured(new,'2026-10-08',{'test_food':('30','45'),'other_food':('0','0')})
        ending=await self.measured(new,'2026-10-15',{'test_food':('20','30'),'other_food':('0','0')})
        self.assertEqual((await self.close((await self.report(alternate,ending)).json())).status_code,409)

    async def test_reopening_invalidates_handoff_and_rebuild_preserves_both_scope_generations(self):
        old,a,b,x,new,target=await self.candidate();plan=(await self.handoff_preview(x,target)).json();key=str(uuid4())
        first_bridge=await self.accept(plan,key);first_bridge=first_bridge.json()['bridge']
        c=await self.measured(new,'2026-10-15',{'test_food':('20','30'),'other_food':('0','0')})
        y=await self.close((await self.report(target,c)).json());self.assertEqual(y.status_code,200,y.text)
        self.assertEqual((await self.reopen((await self.preview(x)).json())).status_code,200)
        replay=await self.accept(plan,key);self.assertEqual(replay.json()['status'],'historical')
        bb=await self.measured(old,'2026-10-08',{'test_food':('20','30')},corrects_snapshot_id=b['header']['id'])
        new_target=await self.measured(new,'2026-10-08',{'test_food':('20','30'),'other_food':('0','0')},corrects_snapshot_id=target['header']['id'])
        xx=await self.close((await self.report(a,bb)).json());self.assertEqual(xx.status_code,200,xx.text);xx=xx.json()['closure']
        before=(await self.report(new_target,c)).json();self.assertEqual((await self.close(before)).status_code,409)
        new_plan=(await self.handoff_preview(xx,new_target)).json();self.assertEqual(new_plan['status'],'ready',new_plan)
        bridge=await self.accept(new_plan);self.assertEqual(bridge.status_code,200,bridge.text)
        self.assertEqual((await self.close(before)).status_code,409)
        yy=await self.close((await self.report(new_target,c)).json());self.assertEqual(yy.status_code,200,yy.text)
        self.assertEqual(xx['report_snapshot']['actualFoodCost'],'70.00');self.assertEqual(yy.json()['closure']['report_snapshot']['actualFoodCost'],'0.00')
        history=(await self.client.get('/api/pg/actual-inventory/berts/scope-handoffs')).json()
        self.assertEqual(len(history),2);self.assertEqual(sum(h['active'] for h in history),1)
        self.assertEqual(next(h for h in history if h['id']==first_bridge['id'])['plan_snapshot'],plan)

    async def test_pending_old_scope_period_cannot_be_remapped_into_new_scope(self):
        old,a,b,c,x,y=await self.chain();await self.reopen((await self.preview(y)).json())
        new,_=await self.scope(('test_food','other_food'));new=new.json()
        target=await self.measured(new,'2026-10-08',{'test_food':('30','45'),'other_food':('0','0')})
        plan=(await self.handoff_preview(x,target)).json();self.assertEqual(plan['status'],'held')
        self.assertEqual((await self.accept(plan)).status_code,409)

    async def test_role_review_and_direct_database_mismatch_guards(self):
        *_,x,new,target=await self.candidate();plan=(await self.handoff_preview(x,target)).json()
        self.assertEqual((await self.accept(plan,items_reviewed=False)).status_code,422)
        self.assertEqual((await self.accept(plan,note=' ')).status_code,422)
        bad=await self.measured(new,'2026-10-08',{'test_food':('29','45'),'other_food':('0','0')})
        async with self.pool.acquire() as conn:
            with self.assertRaises(asyncpg.RaiseError):await conn.execute('''INSERT INTO actual_inventory.scope_bridges
             (store_id,anchor_closure_id,old_closing_snapshot_id,new_opening_snapshot_id,note,plan_snapshot,request_key,request_fingerprint,confirmed_by)
             VALUES('berts',$1,$2,$3,'mismatched',$4,$5,$6,'synthetic')''',UUID(x['id']),UUID(x['closing_snapshot_id']),UUID(bad['header']['id']),plan,uuid4(),b'0'*32)
        import server
        previous=server.db_pg._pool;server.db_pg._pool=self.pool
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://test') as client:
                for role,locations,expected in [('readonly',['berts'],403),('staff',['berts'],403),('manager',['rudds'],403),('manager',['berts'],200)]:
                    token=server._token({'id':'synthetic','email':'test@example.invalid','role':role,'locations':locations})
                    r=await client.get('/api/pg/actual-inventory/berts/scope-handoff-preview/'+x['id'],params={'target_count':target['header']['id']},headers={'Authorization':'Bearer '+token})
                    self.assertEqual(r.status_code,expected,r.text)
        finally:server.db_pg._pool=previous
