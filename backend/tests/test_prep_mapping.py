"""Invented definitions against disposable PG; no operational prep or invoice import."""
import asyncio
import json
import os
import unittest
from decimal import Decimal
from uuid import UUID, uuid4
from unittest.mock import patch

import asyncpg
import httpx
from fastapi import HTTPException
import native_backup as backup
import prep_mapping as mapping
import test_native_order_receiving as fixtures
import test_native_backup as recovery


class PrepConversionTests(unittest.TestCase):
    def test_physical_conversion_is_explicit_and_dimension_checked(self):
        mapping.conversion('oz','lb',Decimal('.0625'))
        mapping.conversion('fl_oz','gal',Decimal('.0078125'))
        for source,base,factor in [('oz','lb','1'),('lb','gal','1'),('pan','lb','1')]:
            with self.assertRaises(HTTPException):mapping.conversion(source,base,Decimal(factor))

    def test_large_exact_line_quantity_is_not_rounded_by_default_decimal_context(self):
        self.assertEqual(mapping.times(Decimal('9999999999999999.123456789012'),Decimal('9999999999999999.123456789012')),
            Decimal('99999999999999982469135780240000.768328000729153483936144'))


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PG required')
class PrepMappingTests(unittest.IsolatedAsyncioTestCase):
    asyncTearDown=fixtures.NativeOrderReceivingTests.asyncTearDown
    units=fixtures.NativeOrderReceivingTests.units
    pair=fixtures.NativeOrderReceivingTests.pair
    scope=fixtures.NativeOrderReceivingTests.scope
    count=fixtures.NativeOrderReceivingTests.count
    capture=fixtures.NativeOrderReceivingTests.capture if hasattr(fixtures.NativeOrderReceivingTests,'capture') else recovery.NativeBackupTests.capture
    body=fixtures.NativeOrderReceivingTests.body
    post=fixtures.NativeOrderReceivingTests.post
    report=fixtures.NativeOrderReceivingTests.report
    target=fixtures.NativeOrderReceivingTests.target
    restored_client=fixtures.NativeOrderReceivingTests.restored_client

    async def asyncSetUp(self):
        await fixtures.NativeOrderReceivingTests.asyncSetUp(self)
        self.prep_flag=patch.dict(os.environ,{'PREP_SETUP_ENABLED':'true'});self.prep_flag.start();self.addCleanup(self.prep_flag.stop)
        async with self.pool.acquire() as conn:
            await conn.execute((recovery.counts.native.ROOT/'migrations/20261005_prep_mapping_foundation.sql').read_text())
        self.assertEqual((await self.units('count'))[0].status_code,200)

    async def save(self,path,body,key=None,store='berts'):
        return await self.client.post(f'/api/pg/purchases/{store}/{path}',json=body,headers={'Idempotency-Key':key or str(uuid4())})

    async def product(self,name='Prepared protein',base='lb',store='berts'):
        body={'name':name,'base_unit':base,'note':'Invented measured output identity','verified':True}
        r=await self.save('prep-products',body,store=store);self.assertEqual(r.status_code,200,r.text)
        return r.json()['product']

    async def profile(self,p,unit=None,factor='1',predecessor=None,store='berts'):
        body={'product_version_id':p['id'],'source_unit':unit or p['base_unit'],'factor':factor,'predecessor_id':predecessor,'note':'Invented verified fill conversion','verified':True}
        r=await self.save('prep-unit-profiles',body,store=store);self.assertEqual(r.status_code,200,r.text)
        return r.json()['profile']

    def recipe(self,p,u,**patches):
        return {'product_version_id':p['id'],'output_profile_id':u['id'],'entered_yield':'48','method':'Trim measured input; retain usable output','note':'Invented recipe version',
            'lines':[{'source_kind':'raw','raw_item_code':'test_food','quantity':'60','source_unit':'lb','factor':'1','evidence':'Measured gross input; trim included'}],**patches}

    async def plan(self,body,store='berts'):
        return await self.client.post(f'/api/pg/purchases/{store}/prep-recipes/preview',json=body)

    async def promote(self,body,key=None):
        plan=await self.plan(body);self.assertEqual(plan.status_code,200,plan.text)
        commit={'recipe':body,'expected_review_hash':plan.json()['reviewHash'],'reviewed':True}
        r=await self.save('prep-recipes',commit,key);self.assertEqual(r.status_code,200,r.text)
        return r.json()['recipe'],commit

    async def legacy(self,uom=None):
        async with self.pool.acquire() as c:
            ident=await c.fetchval("INSERT INTO public.dishes(store_id,name,recipe_type,yield_qty,yield_uom,procedure) VALUES('berts','Invented legacy protein','prep',48,'lb','Keep\nall source details') RETURNING id")
            await c.execute("INSERT INTO public.dish_lines(dish_id,source_type,item_code,qty,uom) VALUES($1,'item','test_food',60,$2)",ident,uom)
            await c.execute("INSERT INTO public.prep_items(store_id,name,item_code,container,vessel_capacity) VALUES('berts','Invented bags','test_food','bag',8)")
        sources=(await self.client.get('/api/pg/purchases/berts/prep-setup')).json()['legacySources']
        source=next(s for s in sources if s['sourceId']==str(ident))
        return ident,{'source_type':'dish','source_id':str(ident),'expected_source_hash':source['hash']},source

    async def test_identity_versions_and_profiles_leave_actual_counts_purchases_and_legacy_stock_unchanged(self):
        _,a,b=await self.pair();before=(await self.report(a,b)).json()
        p=await self.product();u=await self.profile(p);r,_=await self.promote(self.recipe(p,u))
        edited={k:p[k] for k in ('base_unit',)}|{'product_id':p['product_id'],'predecessor_id':p['id'],'name':'Prepared protein renamed','note':'Same physical identity; new label','verified':True}
        v=await self.save('prep-products',edited);self.assertEqual(v.status_code,200,v.text)
        self.assertNotEqual(v.json()['product']['id'],p['id'])
        self.assertEqual((await self.report(a,b)).json(),before)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_logs'),0)
            self.assertEqual(await c.fetchval('SELECT current_stock FROM store_items WHERE item_code=$1 AND store_id=$2','test_food','berts'),0)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.recipe_lines WHERE recipe_version_id=$1',UUID(r['id'])),1)

    async def test_parallel_definition_retry_and_changed_payload(self):
        body={'name':'Eight piece bag','base_unit':'each','note':'Distinct from one raw piece','verified':True};key=str(uuid4())
        r=await asyncio.gather(self.save('prep-products',body,key),self.save('prep-products',body,key))
        self.assertTrue(all(x.status_code==200 for x in r),[x.text for x in r]);self.assertEqual(r[0].json()['product']['id'],r[1].json()['product']['id'])
        self.assertEqual((await self.save('prep-products',body|{'base_unit':'lb'},key)).status_code,409)
        self.assertEqual((await self.save('prep-products',body)).status_code,409)

    async def test_fixed_units_cannot_be_changed_and_cross_store_versions_are_held(self):
        p=await self.product()
        body={'product_id':p['product_id'],'predecessor_id':p['id'],'name':p['name'],'base_unit':'each','note':'Changed unit forbidden','verified':True}
        self.assertEqual((await self.save('prep-products',body)).status_code,409)
        body['base_unit']='lb'
        self.assertEqual((await self.save('prep-products',body,store='rudds')).status_code,422)
        self.assertEqual((await self.save('prep-products',body)).status_code,200)
        self.assertEqual((await self.save('prep-products',body)).status_code,409)

    async def test_unit_profile_revisions_preserve_old_factors_and_require_current_predecessor(self):
        p=await self.product(base='each');u=await self.profile(p,'bag','1')
        v=await self.profile(p,'bag','2',u['id']);self.assertEqual(v['revision'],2)
        body={'product_version_id':p['id'],'source_unit':'bag','factor':'3','predecessor_id':u['id'],'note':'Stale version','verified':True}
        self.assertEqual((await self.save('prep-unit-profiles',body)).status_code,409)
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT base_units_per_source_unit FROM prep_inventory.unit_profiles WHERE id=$1',UUID(u['id'])),1)

    async def test_invalid_numbers_confirmation_unknown_fields_and_physical_factors_held(self):
        p=await self.product();body={'product_version_id':p['id'],'source_unit':'lb','factor':'1','note':'Verified','verified':True}
        for patcher in ({'factor':'0'},{'factor':'NaN'},{'factor':'Infinity'},{'factor':'-1'},{'factor':'2'},{'source_unit':'gal'},{'verified':False},{'note':' '},{'surprise':'x'}):
            self.assertEqual((await self.save('prep-unit-profiles',body|patcher)).status_code,422,patcher)

    async def test_raw_recipe_keeps_unit_and_exact_physical_quantity(self):
        p=await self.product();u=await self.profile(p)
        body=self.recipe(p,u);body['lines'][0].update(quantity='16',source_unit='oz',factor='.0625')
        r,_=await self.promote(body)
        self.assertEqual(Decimal(r['review_snapshot']['lines'][0]['base_quantity']),1)
        async with self.pool.acquire() as c:
            line=await c.fetchrow('SELECT * FROM prep_inventory.recipe_lines WHERE recipe_version_id=$1',UUID(r['id']))
            self.assertEqual((line['entered_quantity'],line['source_unit'],line['factor'],line['base_quantity']),(16,'oz',Decimal('.0625'),1))

    async def test_unverified_raw_identity_missing_yield_and_ambiguous_ingredients_held(self):
        p=await self.product();u=await self.profile(p);body=self.recipe(p,u)
        for patcher in ({'entered_yield':'0'},{'entered_yield':None},{'lines':[]},{'lines':[body['lines'][0]|{'raw_item_code':'other_food'}]}, {'lines':[body['lines'][0]|{'source_unit':'gal'}]}, {'lines':[body['lines'][0]|{'prepared_recipe_id':str(uuid4())}]}):
            self.assertEqual((await self.plan(body|patcher)).status_code,422,patcher)

    async def test_nested_prepared_recipe_consumes_identity_not_another_raw_withdrawal_and_cycle_held(self):
        a=await self.product('Sauce A','gal');ap=await self.profile(a);ar,_=await self.promote(self.recipe(a,ap,entered_yield='6'))
        b=await self.product('Sauce B','gal');bp=await self.profile(b)
        line={'source_kind':'prepared','prepared_recipe_id':ar['id'],'prepared_profile_id':ap['id'],'quantity':'2','source_unit':'gal','factor':'1','evidence':'Use two gallons of existing A'}
        br,_=await self.promote(self.recipe(b,bp,entered_yield='3',lines=[line]))
        self.assertEqual(len(br['review_snapshot']['graph']),1)
        loop=line|{'prepared_recipe_id':br['id'],'prepared_profile_id':bp['id']}
        self.assertEqual((await self.plan(self.recipe(a,ap,predecessor_id=ar['id'],lines=[loop]))).status_code,422)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM purchasing.actual_purchase_facts'),0)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_recipe_stock'),0)

    async def test_prepared_recipe_unit_and_store_identity_mismatch_held(self):
        a=await self.product('A');ap=await self.profile(a);ar,_=await self.promote(self.recipe(a,ap))
        b=await self.product('B');bp=await self.profile(b)
        line={'source_kind':'prepared','prepared_recipe_id':ar['id'],'prepared_profile_id':bp['id'],'quantity':'2','source_unit':'lb','factor':'1','evidence':'Wrong product profile'}
        self.assertEqual((await self.plan(self.recipe(b,bp,lines=[line]))).status_code,422)
        self.assertEqual((await self.plan(self.recipe(a,ap),store='rudds')).status_code,422)

    async def test_changed_raw_ancestor_holds_nested_recipe_promotion_and_cascades_review_status(self):
        a=await self.product('Sauce A','gal');ap=await self.profile(a);ar,_=await self.promote(self.recipe(a,ap,entered_yield='6'))
        b=await self.product('Sauce B','gal');bp=await self.profile(b)
        line={'source_kind':'prepared','prepared_recipe_id':ar['id'],'prepared_profile_id':ap['id'],'quantity':'2','source_unit':'gal','factor':'1','evidence':'Existing sauce lot'}
        br,_=await self.promote(self.recipe(b,bp,entered_yield='3',lines=[line]))
        async with self.pool.acquire() as c:await c.execute("UPDATE items SET unit_qty=999 WHERE code='test_food'")
        current=(await self.client.get('/api/pg/purchases/berts/prep-setup')).json()['recipes']
        self.assertTrue(all(r['reviewNeeded'] for r in current))
        revised=self.recipe(b,bp,entered_yield='3',predecessor_id=br['id'],lines=[line])
        self.assertEqual((await self.plan(revised)).status_code,409)

    async def test_legacy_review_preserves_every_source_field_and_does_not_adopt_missing_units(self):
        ident,link,source=await self.legacy();self.assertEqual(source['mappingState'],'unreviewed')
        self.assertIsNone(source['snapshot']['lines'][0]['uom']);self.assertIn('physical unit is missing',' '.join(source['issues']))
        p=await self.product();u=await self.profile(p);r,_=await self.promote(self.recipe(p,u,legacy=link))
        refreshed=(await self.client.get('/api/pg/purchases/berts/prep-setup')).json()
        s=next(s for s in refreshed['legacySources'] if s['sourceId']==str(ident))
        self.assertEqual(s['mappingState'],'reviewed');self.assertEqual(s['mapping']['source_snapshot'],source['snapshot'])
        self.assertEqual(s['mapping']['source_snapshot']['header']['procedure'],'Keep\nall source details')
        self.assertEqual(r['review_snapshot']['legacy']['snapshot'],source['snapshot'])
        async with self.pool.acquire() as c:self.assertIsNone(await c.fetchval('SELECT uom FROM dish_lines WHERE dish_id=$1',ident))

    async def test_source_drift_stales_legacy_review_and_stale_preview_cannot_promote(self):
        ident,link,_=await self.legacy('lb');p=await self.product();u=await self.profile(p);body=self.recipe(p,u,legacy=link)
        plan=(await self.plan(body)).json()
        async with self.pool.acquire() as c:await c.execute('UPDATE dishes SET yield_qty=54 WHERE id=$1',ident)
        self.assertEqual((await self.save('prep-recipes',{'recipe':body,'expected_review_hash':plan['reviewHash'],'reviewed':True})).status_code,409)
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.recipe_versions'),0)

    async def test_raw_catalog_changes_invalidate_preview_but_exact_saved_retry_stays_saved(self):
        p=await self.product();u=await self.profile(p);body=self.recipe(p,u)
        r,commit=await self.promote(body,key='00000000-0000-0000-0000-000000000101')
        async with self.pool.acquire() as c:await c.execute("UPDATE items SET unit_qty=123 WHERE code='test_food'")
        replay=await self.save('prep-recipes',commit,'00000000-0000-0000-0000-000000000101')
        self.assertEqual(replay.json()['recipe'],r)
        revised=body|{'predecessor_id':r['id']};plan=(await self.plan(revised)).json()
        async with self.pool.acquire() as c:await c.execute("UPDATE items SET unit_qty=124 WHERE code='test_food'")
        self.assertEqual((await self.save('prep-recipes',{'recipe':revised,'expected_review_hash':plan['reviewHash'],'reviewed':True})).status_code,409)

    async def test_parallel_recipe_promotions_replay_once_and_conflicting_successor_held(self):
        p=await self.product();u=await self.profile(p);body=self.recipe(p,u);plan=(await self.plan(body)).json()
        commit={'recipe':body,'expected_review_hash':plan['reviewHash'],'reviewed':True};key=str(uuid4())
        r=await asyncio.gather(self.save('prep-recipes',commit,key),self.save('prep-recipes',commit,key))
        self.assertTrue(all(x.status_code==200 for x in r),[x.text for x in r]);self.assertEqual(r[0].json()['recipe']['id'],r[1].json()['recipe']['id'])
        self.assertEqual((await self.save('prep-recipes',commit)).status_code,409)
        self.assertEqual((await self.save('prep-recipes',commit|{'expected_review_hash':'0'*64},key)).status_code,409)

    async def test_updated_output_profile_and_stale_product_versions_require_new_review(self):
        p=await self.product(base='each');u=await self.profile(p,'bag','1');body=self.recipe(p,u)
        await self.profile(p,'bag','2',u['id'])
        self.assertEqual((await self.plan(body)).status_code,409)

    async def test_atomic_failure_rolls_back_recipe_and_all_children(self):
        p=await self.product();u=await self.profile(p);body=self.recipe(p,u);plan=(await self.plan(body)).json()
        async with self.pool.acquire() as c:
            await c.execute("CREATE FUNCTION public.fail_prep_decision() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Synthetic failure'; END $$; CREATE TRIGGER synthetic_failure BEFORE INSERT ON prep_inventory.promotion_decisions FOR EACH ROW EXECUTE FUNCTION public.fail_prep_decision()")
        with self.assertRaises(asyncpg.RaiseError):await self.save('prep-recipes',{'recipe':body,'expected_review_hash':plan['reviewHash'],'reviewed':True})
        async with self.pool.acquire() as c:
            for table in ('recipe_versions','recipe_lines','promotion_decisions','legacy_crosswalks'):
                self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.'+table),0)

    async def test_database_definitions_and_recipe_children_are_immutable_and_sealed(self):
        _,link,_=await self.legacy('lb');p=await self.product();u=await self.profile(p);r,_=await self.promote(self.recipe(p,u,legacy=link))
        async with self.pool.acquire() as c:
            for table in ('products','product_versions','unit_profiles','recipe_versions','recipe_lines','promotion_decisions','legacy_crosswalks'):
                with self.assertRaises(asyncpg.RaiseError):await c.execute('DELETE FROM prep_inventory.'+table)
            with self.assertRaises(asyncpg.RaiseError):await c.execute("UPDATE prep_inventory.unit_profiles SET base_units_per_source_unit=9")
            with self.assertRaises(asyncpg.RaiseError):await c.execute('''INSERT INTO prep_inventory.recipe_lines(recipe_version_id,store_id,line_number,source_kind,raw_item_code,entered_quantity,source_unit,base_unit,factor,base_quantity,source_snapshot,evidence)
                VALUES($1,'berts',2,'raw','test_food',1,'lb','lb',1,1,'{}','Later insert forbidden')''',UUID(r['id']))

    async def test_missing_confirmation_and_empty_schema_are_held(self):
        with patch.dict(os.environ,{'PREP_SETUP_ENABLED':'false'}):self.assertEqual((await self.client.get('/api/pg/purchases/berts/prep-setup')).status_code,503)
        async with self.pool.acquire() as c:await c.execute('DROP SCHEMA prep_inventory CASCADE')
        self.assertEqual((await self.client.get('/api/pg/purchases/berts/prep-setup')).status_code,503)

    async def test_history_and_stale_review_status_preserve_old_recipe_snapshot(self):
        p=await self.product();u=await self.profile(p);r,_=await self.promote(self.recipe(p,u))
        async with self.pool.acquire() as c:await c.execute("UPDATE items SET unit_qty=124 WHERE code='test_food'")
        setup=(await self.client.get('/api/pg/purchases/berts/prep-setup')).json()
        self.assertTrue(setup['recipes'][0]['reviewNeeded'])
        self.assertIn('Purchased ingredient setup changed',setup['recipes'][0]['reviewIssues'])
        r2,_=await self.promote(self.recipe(p,u,predecessor_id=r['id'],entered_yield='54'))
        history=(await self.client.get('/api/pg/purchases/berts/prep-products/'+p['product_id']+'/history')).json()
        self.assertEqual([x['id'] for x in history['recipeVersions']],[r['id'],r2['id']])
        self.assertEqual(history['recipeVersions'][0]['review_snapshot'],r['review_snapshot'])
        self.assertFalse((await self.client.get('/api/pg/purchases/berts/prep-setup')).json()['recipes'][0]['reviewNeeded'])
        self.assertEqual((await self.client.get('/api/pg/purchases/rudds/prep-products/'+p['product_id']+'/history')).status_code,404)

    async def test_nonfinite_legacy_measurements_remain_visible_and_unverified(self):
        ident,_,_=await self.legacy()
        async with self.pool.acquire() as c:await c.execute("UPDATE dishes SET yield_qty='NaN' WHERE id=$1;",ident)
        r=await self.client.get('/api/pg/purchases/berts/prep-setup');self.assertEqual(r.status_code,200,r.text)
        source=next(s for s in r.json()['legacySources'] if s['sourceId']==str(ident))
        self.assertEqual(source['snapshot']['header']['yield_qty'],'NaN')
        self.assertIn('Positive finite usable yield is missing',source['issues'])

    async def test_database_refuses_an_unsealed_recipe_header_at_commit(self):
        p=await self.product();u=await self.profile(p)
        async with self.pool.acquire() as c:
            with self.assertRaises(asyncpg.RaiseError):
                async with c.transaction():
                    await c.execute('''INSERT INTO prep_inventory.recipe_versions(product_id,product_version_id,store_id,revision,output_profile_id,entered_yield,usable_base_yield,method,note,review_snapshot,review_hash,request_key,request_fingerprint)
                        VALUES($1,$2,'berts',1,$3,1,1,'Invented','No decision','{}',$4,$5,$4)''',UUID(p['product_id']),UUID(p['id']),UUID(u['id']),bytes(32),uuid4())
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.recipe_versions'),0)

    async def test_database_rejects_reviewed_line_mismatch_and_version_gaps(self):
        p=await self.product();u=await self.profile(p);r,_=await self.promote(self.recipe(p,u))
        async with self.pool.acquire() as c:
            with self.assertRaises(asyncpg.RaiseError):
                async with c.transaction():
                    header=await c.fetchval('''INSERT INTO prep_inventory.recipe_versions(product_id,product_version_id,store_id,revision,predecessor_id,output_profile_id,entered_yield,usable_base_yield,method,note,review_snapshot,review_hash,request_key,request_fingerprint)
                        VALUES($1,$2,'berts',2,$3,$4,48,48,'Trim','Tamper check',$5,$6,$7,$6) RETURNING id''',UUID(p['product_id']),UUID(p['id']),UUID(r['id']),UUID(u['id']),r['review_snapshot'],bytes.fromhex(r['review_hash']),uuid4())
                    await c.execute('''INSERT INTO prep_inventory.recipe_lines(recipe_version_id,store_id,line_number,source_kind,raw_item_code,entered_quantity,source_unit,base_unit,factor,base_quantity,source_snapshot,evidence)
                        VALUES($1,'berts',1,'raw','test_food',61,'lb','lb',1,61,$2,'Measured gross input; trim included')''',header,r['review_snapshot']['lines'][0]['source_snapshot'])
                    await c.execute('INSERT INTO prep_inventory.promotion_decisions(recipe_version_id,store_id,review_hash,graph_snapshot,confirmed_by) VALUES($1,$2,$3,$4,$5)',header,'berts',bytes.fromhex(r['review_hash']),[],'synthetic-manager')
            with self.assertRaises(asyncpg.RaiseError):
                await c.execute('''INSERT INTO prep_inventory.unit_profiles(product_version_id,store_id,source_unit,base_units_per_source_unit,revision,predecessor_id,note,confirmed_by,request_key,request_fingerprint)
                    VALUES($1,'berts','lb',1,4,$2,'Gap forbidden','synthetic-manager',$3,$4)''',UUID(p['id']),UUID(u['id']),uuid4(),bytes(32))
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.recipe_versions'),1)

    async def test_cross_store_catalog_edit_waits_until_recipe_source_capture_commits(self):
        p=await self.product();u=await self.profile(p);body=self.recipe(p,u);plan=(await self.plan(body)).json()
        reached=asyncio.Event();release=asyncio.Event();original=mapping.preview
        async def paused(*args):
            reached.set();await release.wait();return await original(*args)
        async with self.pool.acquire() as writer:
            pid=await writer.fetchval('SELECT pg_backend_pid()')
            with patch.object(mapping,'preview',side_effect=paused):
                promotion=asyncio.create_task(self.save('prep-recipes',{'recipe':body,'expected_review_hash':plan['reviewHash'],'reviewed':True}))
                try:
                    await asyncio.wait_for(reached.wait(),5)
                    edit=asyncio.create_task(writer.execute("UPDATE public.items SET unit_qty=999 WHERE code='test_food'"))
                    try:
                        async with self.pool.acquire() as observer:
                            for _ in range(100):
                                if await observer.fetchval("SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=$1",pid):break
                                await asyncio.sleep(.02)
                            else:self.fail('Global catalog edit did not wait for the reviewed snapshot')
                        release.set();result=await promotion;self.assertEqual(result.status_code,200,result.text);await edit
                    finally:
                        release.set()
                        if not edit.done():await edit
                finally:
                    release.set()
                    if not promotion.done():await promotion
        state=(await self.client.get('/api/pg/purchases/berts/prep-setup')).json()
        self.assertTrue(state['recipes'][0]['reviewNeeded'])

    async def test_real_server_role_and_location_authority_confines_definition_writes(self):
        import server
        from starlette.requests import Request
        def request():return Request({'type':'http','headers':[(b'authorization',b'Bearer synthetic')]})
        for user,write in [({'role':'staff','locations':['berts']},False),({'role':'readonly','locations':['berts']},True),({'role':'manager','locations':['rudds']},True)]:
            with patch.object(server,'_decode_token',return_value=user):
                with self.assertRaises(HTTPException) as denied:server._purchase_actor(request(),'berts',write)
                self.assertEqual(denied.exception.status_code,403)
        for role,write in [('manager',True),('readonly',False),('owner',True)]:
            with patch.object(server,'_decode_token',return_value={'role':role,'locations':['berts']}):self.assertEqual(server._purchase_actor(request(),'berts',write),role)

    async def test_fresh_whole_database_recovery_retains_private_definitions_sources_and_seals(self):
        ident,link,_=await self.legacy('lb');p=await self.product();u=await self.profile(p);r,_=await self.promote(self.recipe(p,u,legacy=link))
        revised=self.recipe(p,u,predecessor_id=r['id'],entered_yield='54');r2,_=await self.promote(revised)
        source=(await self.client.get('/api/pg/purchases/berts/prep-setup')).json()
        manifest=await backup.create_backup(self.source,recovery.PG_DUMP,self.directory)
        dsn=await self.target();proof=await backup.verify_restore(dsn,self.directory);self.assertEqual(proof['status'],'verified')
        client,pool=await self.restored_client(dsn)
        self.assertEqual((await client.get('/api/pg/purchases/berts/prep-setup')).json(),source)
        async with pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.recipe_versions'),2)
            with self.assertRaises(asyncpg.RaiseError):await c.execute("UPDATE prep_inventory.recipe_versions SET entered_yield=99")
        evidence={'status':'verified','backup_directory':str(self.directory),'definitions':{k:v for k,v in manifest['tables'].items() if k.startswith('prep_inventory.')},'dump':manifest['dump'],'source_equals_restored':True,'recipe_versions':2,'operational_data':False}
        (recovery.counts.native.ROOT.parent/'prep-mapping-restore-evidence.json').write_text(json.dumps(evidence,indent=2))
