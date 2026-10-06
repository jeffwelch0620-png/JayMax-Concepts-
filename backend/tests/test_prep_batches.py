"""Invented measurements only, in isolated native PostgreSQL databases."""
import asyncio
import json
import os
import unittest
from decimal import Decimal
from uuid import UUID, uuid4
from unittest.mock import patch

import asyncpg
from fastapi import HTTPException
import prep_batches as batches
import native_backup as backup
import test_prep_mapping as foundation


class BatchBoundaryTests(unittest.TestCase):
    def test_included_loss_requires_evidence_and_cannot_exceed_gross(self):
        value=dict(recipe_line_id=uuid4(),quantity='60',source_unit='lb',factor='1',measurement_basis='measured',evidence='Scale')
        self.assertIsNone(batches.InputIn(**value).included_loss_quantity)
        self.assertEqual(batches.InputIn(**value,included_loss_quantity='0',loss_evidence='Observed no trim').included_loss_quantity,0)
        for qty,note in [('61','Trim'),('12',None),('NaN','Trim'),('-1','Trim')]:
            with self.assertRaises(ValueError): batches.InputIn(**value,included_loss_quantity=qty,loss_evidence=note)


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PG required')
class PrepBatchTests(unittest.IsolatedAsyncioTestCase):
    asyncTearDown=foundation.PrepMappingTests.asyncTearDown
    units=foundation.PrepMappingTests.units
    pair=foundation.PrepMappingTests.pair
    scope=foundation.PrepMappingTests.scope
    count=foundation.PrepMappingTests.count
    capture=foundation.PrepMappingTests.capture
    body=foundation.PrepMappingTests.body
    post=foundation.PrepMappingTests.post
    report=foundation.PrepMappingTests.report
    target=foundation.PrepMappingTests.target
    restored_client=foundation.PrepMappingTests.restored_client
    save=foundation.PrepMappingTests.save
    product=foundation.PrepMappingTests.product
    profile=foundation.PrepMappingTests.profile
    recipe=foundation.PrepMappingTests.recipe
    plan=foundation.PrepMappingTests.plan
    promote=foundation.PrepMappingTests.promote

    async def asyncSetUp(self):
        await foundation.PrepMappingTests.asyncSetUp(self)
        flag=patch.dict(os.environ,{'PREP_BATCHES_ENABLED':'true'});flag.start();self.addCleanup(flag.stop)
        async with self.pool.acquire() as c:
            await c.execute((foundation.recovery.counts.native.ROOT/'migrations/20261005_prep_batch_events.sql').read_text())
        self.p=await self.product();self.u=await self.profile(self.p)
        self.r,_=await self.promote(self.recipe(self.p,self.u))

    async def entry(self,r=None,**changes):
        r=r or self.r
        async with self.pool.acquire() as c:
            lines=await c.fetch('SELECT * FROM prep_inventory.recipe_lines WHERE recipe_version_id=$1 ORDER BY line_number',UUID(r['id']))
        return {'recipe_version_id':r['id'],'planned_batches':'1','output_quantity':'48','performed_at':'2026-10-05T10:00:00-04:00',
            'business_date':'2026-10-05','timezone_name':'America/New_York','calendar_date_confirmed':True,'single_output_confirmed':True,
            'inputs':[{'recipe_line_id':str(l['id']),'quantity':str(l['entered_quantity']),'source_unit':l['source_unit'],'factor':str(l['factor']),
                       'measurement_basis':'measured','evidence':'Invented scale observation','included_loss_quantity':'12','loss_evidence':'Trim already in gross input'} for l in lines],
            'note':'Invented prep only',**changes}

    async def preview_batch(self,body):
        return await self.client.post('/api/pg/purchases/berts/prep-batches/preview',json=body)

    async def record(self,body,key=None):
        p=await self.preview_batch(body);self.assertEqual(p.status_code,200,p.text)
        payload={'batch':body,'expected_review_hash':p.json()['reviewHash'],'reviewed':True}
        r=await self.save('prep-batches',payload,key);self.assertEqual(r.status_code,200,r.text)
        return r.json()['event'],payload

    async def change(self,event,change,key=None):
        p=await self.client.post(f"/api/pg/purchases/berts/prep-batches/{event['id']}/change-preview",json=change)
        self.assertEqual(p.status_code,200,p.text)
        payload={'change':change,'expected_review_hash':p.json()['reviewHash'],'reviewed':True}
        r=await self.save(f"prep-batches/{event['id']}/changes",payload,key);self.assertEqual(r.status_code,200,r.text)
        return r.json()['event'],payload

    async def nested(self,source,amount='20'):
        product=await self.product('Invented marinated protein');profile=await self.profile(product)
        recipe,_=await self.promote(self.recipe(product,profile,entered_yield='20',lines=[{'source_kind':'prepared','prepared_recipe_id':self.r['id'],
            'prepared_profile_id':self.u['id'],'quantity':'20','source_unit':'lb','factor':'1','evidence':'Measured prepared input'}]))
        body=await self.entry(recipe,output_quantity=amount,performed_at='2026-10-05T11:00:00-04:00')
        body['inputs'][0].update(quantity=amount,source_batch_id=source['id'],included_loss_quantity=None,loss_evidence=None)
        return body

    async def test_trim_is_included_once_and_actual_food_cost_is_unchanged(self):
        _,a,b=await self.pair();before=(await self.report(a,b)).json()
        e,_=await self.record(await self.entry())
        self.assertEqual(e['review_snapshot']['cost'],{'status':'not_calculated','amount':None})
        self.assertEqual(e['review_snapshot']['inputs'][0]['includedLossBaseQuantity'],'12')
        async with self.pool.acquire() as c:
            rows=await c.fetch('SELECT kind,quantity FROM prep_inventory.batch_movements ORDER BY ordinal')
            self.assertEqual([(x['kind'],x['quantity']) for x in rows],[('raw_input',Decimal(-60)),('output',Decimal(48))])
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_logs'),0)
        self.assertEqual((await self.report(a,b)).json(),before)
        replacement,_=await self.change(e,{'kind':'replacement','replacement':await self.entry(output_quantity='47'),'reason':'Corrected measured output'})
        await self.change(replacement,{'kind':'void','reason':'Erroneous record'})
        self.assertEqual((await self.report(a,b)).json(),before)

    async def test_safe_parallel_retry_changed_key_payload_and_replay_after_correction(self):
        body=await self.entry();p=(await self.preview_batch(body)).json();payload={'batch':body,'expected_review_hash':p['reviewHash'],'reviewed':True};key=str(uuid4())
        r=await asyncio.gather(self.save('prep-batches',payload,key),self.save('prep-batches',payload,key))
        self.assertTrue(all(x.status_code==200 for x in r),[x.text for x in r]);self.assertEqual(r[0].json()['event']['id'],r[1].json()['event']['id'])
        e=r[0].json()['event'];await self.change(e,{'kind':'void','reason':'Duplicate observation'})
        again=await self.save('prep-batches',payload,key);self.assertTrue(again.json()['replayed']);self.assertEqual(again.json()['event']['id'],e['id'])
        self.assertEqual((await self.save('prep-batches',payload|{'batch':body|{'note':'Changed'}},key)).status_code,409)

    async def test_nested_batch_consumes_recorded_prepared_lot_without_second_raw_withdrawal(self):
        source,_=await self.record(await self.entry());body=await self.nested(source);e,_=await self.record(body)
        state=(await self.client.get('/api/pg/purchases/berts/prep-batches/setup')).json()
        self.assertEqual(next(l for l in state['lots'] if l['id']==source['id'])['remainingRecordedQuantity'],'28')
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval("SELECT sum(quantity) FROM prep_inventory.batch_movements WHERE kind='raw_input'"),-60)
        self.assertEqual(e['review_snapshot']['inputs'][0]['sourceBatch']['id'],source['id'])
        denied=await self.client.post(f"/api/pg/purchases/berts/prep-batches/{source['id']}/change-preview",json={'kind':'void','reason':'Cannot erase ancestry'})
        self.assertEqual(denied.status_code,409)

    async def test_lot_overdraw_stale_preview_and_parallel_allocation_are_held(self):
        source,_=await self.record(await self.entry());body=await self.nested(source,'30');p=(await self.preview_batch(body)).json()
        payload={'batch':body,'expected_review_hash':p['reviewHash'],'reviewed':True}
        results=await asyncio.gather(self.save('prep-batches',payload),self.save('prep-batches',payload))
        self.assertEqual(sorted(x.status_code for x in results),[200,409])
        body['inputs'][0]['quantity']='19'
        self.assertEqual((await self.preview_batch(body)).status_code,409)

    async def test_replacement_and_void_append_exact_reversals_and_preserve_history(self):
        original,_=await self.record(await self.entry());body=await self.entry(output_quantity='47');body['inputs'][0]['quantity']='59'
        replacement,_=await self.change(original,{'kind':'replacement','replacement':body,'reason':'Corrected scale transcription'})
        self.assertEqual(replacement['revision'],2)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval("SELECT sum(quantity) FROM prep_inventory.batch_movements WHERE kind='raw_input'"),-59)
            self.assertEqual(await c.fetchval("SELECT sum(quantity) FROM prep_inventory.batch_movements WHERE kind='output'"),47)
        void,_=await self.change(replacement,{'kind':'void','reason':'Record entered in error; no actual batch'})
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT sum(quantity) FROM prep_inventory.batch_movements'),0)
        history=(await self.client.get(f"/api/pg/purchases/berts/prep-batches/{original['root_id']}/history")).json()['events']
        self.assertEqual([x['kind'] for x in history],['initial','replacement','void']);self.assertEqual(history[0],original)
        self.assertEqual((await self.client.post(f"/api/pg/purchases/berts/prep-batches/{void['id']}/change-preview",json={'kind':'void','reason':'Again'})).status_code,409)

    async def test_consumer_void_releases_source_and_then_producer_can_be_corrected(self):
        source,_=await self.record(await self.entry());consumer,_=await self.record(await self.nested(source))
        await self.change(consumer,{'kind':'void','reason':'Erroneous nested record'})
        replacement,_=await self.change(source,{'kind':'replacement','replacement':await self.entry(output_quantity='46'),'reason':'Output transcription'})
        lots=(await self.client.get('/api/pg/purchases/berts/prep-batches/setup')).json()['lots']
        self.assertEqual([(x['id'],x['remainingRecordedQuantity']) for x in lots],[(replacement['id'],'46')])

    async def test_timezone_date_naive_timestamp_unknown_loss_and_recipe_estimate_are_explicit(self):
        body=await self.entry()
        for changes in [{'performed_at':'2026-10-05T10:00:00'},{'business_date':'2026-10-04'},{'timezone_name':'Not/AZone'},{'calendar_date_confirmed':False},{'single_output_confirmed':False}]:
            self.assertEqual((await self.preview_batch(body|changes)).status_code,422)
        body['inputs'][0].update(measurement_basis='recipe_estimate',included_loss_quantity=None,loss_evidence=None)
        e,_=await self.record(body)
        self.assertIsNone(e['review_snapshot']['inputs'][0]['includedLossBaseQuantity'])
        self.assertEqual(e['review_snapshot']['inputs'][0]['measurement_basis'],'recipe_estimate')
        self.assertEqual((await self.preview_batch(body|{'timezone_name':'America/Chicago'})).status_code,409)

    async def test_foreign_store_lot_missing_ingredients_and_future_source_are_held(self):
        source,_=await self.record(await self.entry());body=await self.nested(source)
        self.assertEqual((await self.preview_batch(body|{'performed_at':'2026-10-05T09:00:00-04:00'})).status_code,422)
        self.assertEqual((await self.preview_batch(body|{'inputs':[]})).status_code,422)
        self.assertEqual((await self.client.post('/api/pg/purchases/rudds/prep-batches/preview',json=body)).status_code,422)
        body['inputs'][0]['source_batch_id']=str(uuid4());self.assertEqual((await self.preview_batch(body)).status_code,422)

    async def test_source_setup_change_holds_new_batch_but_retains_historical_snapshot(self):
        body=await self.entry();source,payload=await self.record(body)
        async with self.pool.acquire() as c:await c.execute("UPDATE items SET unit_qty=999 WHERE code='test_food'")
        self.assertEqual((await self.preview_batch(body)).status_code,409)
        history=(await self.client.get(f"/api/pg/purchases/berts/prep-batches/{source['root_id']}/history")).json()['events']
        self.assertEqual(history[0],source)

    async def test_atomic_failure_rolls_back_header_policy_and_movements(self):
        body=await self.entry();plan=(await self.preview_batch(body)).json()
        original=batches.persist
        async def failed(*args):
            await original(*args);raise RuntimeError('Invented failure before commit')
        with patch.object(batches,'persist',side_effect=failed):
            with self.assertRaises(RuntimeError): await self.save('prep-batches',{'batch':body,'expected_review_hash':plan['reviewHash'],'reviewed':True})
        async with self.pool.acquire() as c:
            for table in ['batch_events','batch_policies','batch_movements']:self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.'+table),0)

    async def test_sealed_children_immutable_facts_and_reviewed_movement_tampering_are_rejected(self):
        e,_=await self.record(await self.entry())
        async with self.pool.acquire() as c:
            for table in ['batch_events','batch_movements','batch_policies']:
                with self.assertRaises(asyncpg.RaiseError):await c.execute('DELETE FROM prep_inventory.'+table)
            with self.assertRaises(asyncpg.RaiseError):
                await c.execute('''INSERT INTO prep_inventory.batch_movements(event_id,store_id,ordinal,side,kind,recipe_version_id,product_id,base_unit,quantity)
                    VALUES($1,'berts',99,'apply','output',$2,$3,'lb',1)''',UUID(e['id']),UUID(self.r['id']),UUID(self.p['product_id']))
            body=await self.entry();plan=await batches.preview(c,'berts',batches.BatchIn(**body))
            plan['review']['movements'][0]['quantity']='-61'
            with self.assertRaises(asyncpg.RaiseError):
                async with c.transaction():await batches.persist(c,'berts',plan,uuid4(),bytes(32),'synthetic-manager')
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_inventory.batch_events'),1)

    async def test_legacy_writers_are_blocked_before_any_database_call_only_when_pilot_enabled(self):
        import server
        calls=[(server.complete_prep,('berts',None)),(server.apply_sales,('berts',None)),(server.use_container,('berts',None)),
            (server.pg_complete_prep,('berts',None)),(server.pg_apply_sales,('berts',None)),(server.pg_use_container,('berts',None))]
        calls.extend([(server._deduct_item_and_stock,('berts',None,None)),(server._pg_deduct_item_and_stock,(None,'berts',None,None))])
        for fn,args in calls:
            with self.assertRaises(HTTPException) as error:await fn(*args)
            self.assertEqual(error.exception.status_code,410)
        with patch.dict(os.environ,{'PREP_BATCHES_ENABLED':'false'}):batches.reject_legacy_write()

    async def test_recovery_retains_corrections_allocation_projection_and_sealed_facts(self):
        e,_=await self.record(await self.entry());replacement,_=await self.change(e,{'kind':'replacement','replacement':await self.entry(output_quantity='47'),'reason':'Measured correction'})
        await self.record(await self.nested(replacement))
        state=(await self.client.get('/api/pg/purchases/berts/prep-batches/setup')).json()
        manifest=await backup.create_backup(self.source,foundation.recovery.PG_DUMP,self.directory)
        dsn=await self.target();proof=await backup.verify_restore(dsn,self.directory);self.assertEqual(proof['status'],'verified')
        client,pool=await self.restored_client(dsn)
        self.assertEqual((await client.get('/api/pg/purchases/berts/prep-batches/setup')).json(),state)
        async with pool.acquire() as c:
            with self.assertRaises(asyncpg.RaiseError):await c.execute("UPDATE prep_inventory.batch_movements SET quantity=1")
        evidence={'status':'verified','backup_directory':str(self.directory),'tables':{k:v for k,v in manifest['tables'].items() if k.startswith('prep_inventory.')},
            'dump':manifest['dump'],'source_equals_restored':True,'batch_events':3,'operational_data':False}
        (foundation.recovery.counts.native.ROOT.parent/'prep-batches-restore-evidence.json').write_text(json.dumps(evidence,indent=2))

    async def test_old_producing_recipe_lot_remains_usable_under_current_standard_recipe(self):
        source,_=await self.record(await self.entry())
        self.r,_=await self.promote(self.recipe(self.p,self.u,predecessor_id=self.r['id'],entered_yield='46'))
        body=await self.nested(source);e,_=await self.record(body)
        snapshot=e['review_snapshot']['inputs'][0]
        self.assertNotEqual(snapshot['sourceBatch']['recipe_version_id'],snapshot['definition']['prepared_recipe_id'])
        self.assertEqual(snapshot['sourceBatch']['recipe_version_id'],source['recipe_version_id'])

    async def test_consumer_replacement_releases_its_own_prior_allocations_atomically(self):
        source,_=await self.record(await self.entry());body=await self.nested(source,'40');consumer,_=await self.record(body)
        body['inputs'][0]['quantity']='45';body['output_quantity']='45'
        await self.change(consumer,{'kind':'replacement','replacement':body,'reason':'Corrected input measurement'})
        lots=(await self.client.get('/api/pg/purchases/berts/prep-batches/setup')).json()['lots']
        self.assertEqual(next(x for x in lots if x['id']==source['id'])['remainingRecordedQuantity'],'3')
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval("SELECT sum(quantity) FROM prep_inventory.batch_movements WHERE kind='raw_input'"),-60)

    async def test_any_lot_balance_change_requires_fresh_review_even_when_output_remains_sufficient(self):
        source,_=await self.record(await self.entry());body=await self.nested(source,'10');p=(await self.preview_batch(body)).json()
        payload={'batch':body,'expected_review_hash':p['reviewHash'],'reviewed':True}
        first=await self.save('prep-batches',payload);self.assertEqual(first.status_code,200,first.text)
        self.assertEqual((await self.save('prep-batches',payload)).status_code,409)
        second,_=await self.record(body);self.assertNotEqual(second['id'],first.json()['event']['id'])

    async def test_parallel_corrections_cannot_fork_and_retries_keep_the_original_event(self):
        e,_=await self.record(await self.entry());change={'kind':'void','reason':'Incorrect record'}
        p=(await self.client.post(f"/api/pg/purchases/berts/prep-batches/{e['id']}/change-preview",json=change)).json()
        payload={'change':change,'expected_review_hash':p['reviewHash'],'reviewed':True};key=str(uuid4())
        path=f"prep-batches/{e['id']}/changes"
        results=await asyncio.gather(self.save(path,payload,key),self.save(path,payload))
        self.assertEqual(sorted(x.status_code for x in results),[200,409])
        winner=next(x.json()['event'] for x in results if x.status_code==200)
        # Whichever key won, replaying that request remains safe after the void.
        if results[0].status_code==200:
            retry=await self.save(path,payload,key);self.assertEqual(retry.json()['event']['id'],winner['id'])

    async def test_raw_piece_and_prepared_bag_have_distinct_identities_without_false_loss_math(self):
        async with self.pool.acquire() as c:
            await c.execute("UPDATE public.items SET item_type='raw' WHERE code='other_food'")
            await c.execute("INSERT INTO purchasing.item_bases(store_id,item_code,base_unit) VALUES('berts','other_food','each')")
        p=await self.product('Invented eight-piece bags','each');u=await self.profile(p,'bag','1')
        recipe,_=await self.promote(self.recipe(p,u,entered_yield='15',lines=[{'source_kind':'raw','raw_item_code':'other_food','quantity':'120','source_unit':'each','factor':'1','evidence':'Eight pieces per separate prepared bag'}]))
        body=await self.entry(recipe,output_quantity='15');body['inputs'][0].update(included_loss_quantity='0',loss_evidence='All 120 pieces portioned')
        e,_=await self.record(body)
        self.assertEqual([(x['kind'],x['quantity']) for x in e['review_snapshot']['movements']],[('raw_input','-120'),('output','15')])
        self.assertEqual(e['review_snapshot']['inputs'][0]['includedLossBaseQuantity'],'0')
        self.assertNotIn('inferredLoss',e['review_snapshot']['inputs'][0])

    async def test_dst_repeated_hour_preserves_offset_and_large_exact_quantities_do_not_round(self):
        body=await self.entry(performed_at='2026-11-01T01:30:00-04:00',business_date='2026-11-01')
        body['inputs'][0].update(quantity='9999999999999999.123456789012',included_loss_quantity=None,loss_evidence=None)
        early,_=await self.record(body)
        late,_=await self.record(body|{'performed_at':'2026-11-01T01:30:00-05:00'})
        self.assertNotEqual(early['performed_at'],late['performed_at'])
        self.assertEqual(early['review_snapshot']['movements'][0]['quantity'],'-9999999999999999.123456789012')

    async def test_restored_transaction_identifier_collision_cannot_append_old_batch_or_recipe_children(self):
        event,_=await self.record(await self.entry())
        async with self.pool.acquire() as c:
            # Simulate old restored timestamps with a transaction ID equal to the
            # current cluster's ID. Trusted SQL fixtures only; API cannot set these.
            with self.assertRaises(asyncpg.RaiseError) as error:
                async with c.transaction():
                    ident=uuid4()
                    await c.execute('''INSERT INTO prep_inventory.batch_events(id,store_id,root_id,revision,kind,recipe_version_id,product_id,product_version_id,
                        base_unit,performed_at,business_date,timezone_name,reason,review_snapshot,review_hash,recorded_by,recorded_at,request_key,request_fingerprint)
                        SELECT $1,store_id,$1,1,'initial',recipe_version_id,product_id,product_version_id,base_unit,performed_at,business_date,timezone_name,
                         reason,review_snapshot,review_hash,recorded_by,now()-interval '1 day',$2,request_fingerprint FROM prep_inventory.batch_events WHERE id=$3''',ident,uuid4(),UUID(event['id']))
                    await c.execute('''INSERT INTO prep_inventory.batch_movements(event_id,store_id,ordinal,side,kind,recipe_version_id,product_id,base_unit,quantity)
                        VALUES($1,'berts',1,'apply','output',$2,$3,'lb',48)''',ident,UUID(self.r['id']),UUID(self.p['product_id']))
            self.assertIn('sealed',str(error.exception))
            with self.assertRaises(asyncpg.RaiseError) as error:
                async with c.transaction():
                    recipe=await c.fetchval('''INSERT INTO prep_inventory.recipe_versions(product_id,product_version_id,store_id,revision,predecessor_id,output_profile_id,
                        entered_yield,usable_base_yield,method,note,review_snapshot,review_hash,recorded_at,request_key,request_fingerprint)
                        SELECT product_id,product_version_id,store_id,2,id,output_profile_id,entered_yield,usable_base_yield,method,note,review_snapshot,
                         review_hash,now()-interval '1 day',$2,request_fingerprint FROM prep_inventory.recipe_versions WHERE id=$1 RETURNING id''',UUID(self.r['id']),uuid4())
                    await c.execute('''INSERT INTO prep_inventory.promotion_decisions(recipe_version_id,store_id,review_hash,graph_snapshot,confirmed_by)
                        VALUES($1,'berts',$2,'[]','synthetic')''',recipe,bytes(32))
            self.assertIn('sealed',str(error.exception))

    async def test_parallel_cross_store_key_reuse_returns_conflict_without_a_database_error(self):
        async with self.pool.acquire() as c:
            await c.execute("INSERT INTO public.store_items(store_id,item_code,count_unit,base_per_count_unit) VALUES('rudds','test_food','lb',1)")
            await c.execute("INSERT INTO purchasing.item_bases(store_id,item_code,base_unit) VALUES('rudds','test_food','lb')")
        p=await self.product(store='rudds');u=await self.profile(p,store='rudds');recipe=self.recipe(p,u)
        plan=await self.plan(recipe,store='rudds');self.assertEqual(plan.status_code,200,plan.text)
        saved=await self.save('prep-recipes',{'recipe':recipe,'expected_review_hash':plan.json()['reviewHash'],'reviewed':True},store='rudds')
        self.assertEqual(saved.status_code,200,saved.text)
        payloads=[]
        for store,r in [('berts',self.r),('rudds',saved.json()['recipe'])]:
            body=await self.entry(r)
            preview=await self.client.post(f'/api/pg/purchases/{store}/prep-batches/preview',json=body)
            self.assertEqual(preview.status_code,200,preview.text)
            payloads.append({'batch':body,'expected_review_hash':preview.json()['reviewHash'],'reviewed':True})
        key=str(uuid4())
        responses=await asyncio.gather(self.save('prep-batches',payloads[0],key,store='berts'),self.save('prep-batches',payloads[1],key,store='rudds'))
        self.assertEqual(sorted(r.status_code for r in responses),[200,409])
