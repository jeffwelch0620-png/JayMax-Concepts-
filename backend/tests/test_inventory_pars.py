"""Fictional inventory targets: explicit units, retries, isolation and recovery."""
import asyncio,json,os,unittest
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID,uuid4
import asyncpg,httpx
from pydantic import ValidationError
import server,inventory_pars as pars,native_backup as backup
import test_order_commands as orders
import test_shared_catalog as shared
import test_native_backup as recovery


class InventoryParValidationTests(unittest.TestCase):
    def test_recovery_identity_preserves_decimal_scale_and_actor_version(self):
        unit=uuid4();key_body=dict(unit_profile_id=unit,quantity='1.00',coverage_note='Fictional coverage',verified=True)
        body=pars.Review(**key_body)
        digest=pars.request_digest('berts','F01','actor',body,0)
        self.assertEqual(digest,pars.fingerprint(pars.serial(dict(store='berts',item='F01',actor='actor',expected=0,body=body.model_dump()))))
        for changed in [pars.request_digest('berts','F01','other',body,0),pars.request_digest('berts','F01','actor',body,1),
                        pars.request_digest('berts','F01','actor',pars.Review(**(key_body|{'quantity':'1.0'})),0)]:
            with self.subTest():self.assertNotEqual(digest,changed)

    def test_response_decimals_are_fixed_without_mutating_evidence_or_fingerprints(self):
        value=dict(legacy_quantity=Decimal('0E-10'),review=dict(quantity=Decimal('1E-7'),factor=Decimal('1E-7'),base_quantity=Decimal('1E-14')))
        before=pars.fingerprint(pars.serial(value))
        result=pars.par_response(value)
        self.assertEqual(result,dict(legacy_quantity='0.0000000000',review=dict(quantity='0.0000001',factor='0.0000001',base_quantity='0.00000000000001')))
        self.assertEqual(pars.par_response([value]),[result])
        self.assertIsInstance(value['review']['quantity'],Decimal)
        self.assertEqual(pars.fingerprint(pars.serial(value)),before)

    def test_confirmation_quantities_and_notes_are_explicit(self):
        body=dict(unit_profile_id=str(uuid4()),quantity='0',coverage_note='Through the next fictional delivery',verified=True)
        self.assertEqual(pars.Review(**body).quantity,Decimal(0))
        for changes in ({'quantity':True},{'quantity':'NaN'},{'quantity':'Infinity'},{'quantity':'-1'},
                        {'quantity':'1.1234567890123'},{'verified':1},{'verified':False},{'coverage_note':' '},{'base_quantity':'30'}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):pars.Review(**(body|changes))


@unittest.skipUnless(os.getenv('NATIVE_PURCHASE_TEST_DSN'),'Disposable PostgreSQL required')
class InventoryParTests(unittest.IsolatedAsyncioTestCase):
    target=orders.OrderCommandTests.target
    units=orders.OrderCommandTests.units
    pair=orders.OrderCommandTests.pair
    scope=orders.OrderCommandTests.scope
    count=orders.OrderCommandTests.count
    report=orders.OrderCommandTests.report
    body=orders.OrderCommandTests.body
    post=orders.OrderCommandTests.post
    capture=orders.OrderCommandTests.capture
    restored_client=shared.SharedCatalogTests.restored_client

    async def asyncSetUp(self):
        await orders.OrderCommandTests.asyncSetUp(self)
        self.before_install=(await self.catalog.get('/api/pg/purchases/berts/inventory-pars')).json()
        async with self.pool.acquire() as c:
            self.legacy=await c.fetchval("SELECT par FROM store_items WHERE store_id='berts' AND item_code='test_food'")
            await c.execute((recovery.counts.native.ROOT/'migrations/20261018_reviewed_inventory_pars.sql').read_text())
        result,_=await self.units('count');self.assertEqual(result.status_code,200,result.text)
        self.profile=result.json()['profile']

    async def asyncTearDown(self):
        await orders.OrderCommandTests.asyncTearDown(self)

    def review(self,**changes):
        return dict(action='confirm',unit_profile_id=self.profile['id'],quantity='1.5',
                    coverage_note='Target through next fictional delivery, including buffer',verified=True)|changes

    async def edit(self,body=None,version=0,key=None,store='berts',client=None,code='test_food'):
        return await (client or self.owner_client).put(f'/api/pg/purchases/{store}/inventory-pars/{code}',json=body or self.review(),
            headers={'If-Match':str(version),'Idempotency-Key':key or str(uuid4())})

    async def read(self):
        r=await self.catalog.get('/api/pg/purchases/berts/inventory-pars');self.assertEqual(r.status_code,200,r.text);return r.json()

    async def status(self,body,key,version=0,store='berts',client=None):
        return await (client or self.owner_client).post(f'/api/pg/purchases/{store}/inventory-pars/test_food/status',json=body,
            headers={'If-Match':str(version),'Idempotency-Key':key})

    async def test_recovery_status_is_readonly_and_exact_retries_preserve_accounting(self):
        _,a,b=await self.pair();report=(await self.report(a,b)).json()
        key=str(uuid4());body=self.review(quantity='0');original=pars.review_values
        async def checked_reader(conn,*args):
            self.assertEqual(await conn.fetchval('SHOW transaction_read_only'),'on')
            self.assertEqual(await conn.fetchval('SHOW transaction_isolation'),'repeatable read')
            return await original(conn,*args)
        async with self.pool.acquire() as c:
            before=await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'")
        with patch.object(pars,'review_values',checked_reader):status=await self.status(body,key)
        self.assertEqual(status.status_code,200,status.text);self.assertEqual(status.json()['outcome'],'retry_available')
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'"),before)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM purchasing.inventory_par_versions'),0)
        posted=await self.edit(body,key=key);self.assertEqual(posted.status_code,200,posted.text)
        self.assertEqual((await self.status(body,key)).json()['outcome'],'saved_current')
        replay=await self.edit(body,key=key);self.assertTrue(replay.json()['replayed'])
        self.assertEqual(posted.json()['review'],replay.json()['review'])
        self.assertEqual(report,(await self.report(a,b)).json())

    async def test_recovery_distinguishes_saved_superseded_and_unsaved_fenced_requests(self):
        body=self.review();key=str(uuid4());missing=str(uuid4())
        self.assertEqual((await self.edit(body,key=key)).status_code,200)
        self.assertEqual((await self.edit(self.review(quantity='2'),version=1)).status_code,200)
        saved=(await self.status(body,key)).json();self.assertEqual(saved['outcome'],'saved_superseded')
        self.assertEqual(saved['review']['revision'],1);self.assertEqual(saved['current_review']['revision'],2)
        absent=(await self.status(body,missing)).json();self.assertEqual(absent['outcome'],'not_saved_superseded')
        self.assertIsNone(absent['review']);self.assertEqual(absent['current_review']['revision'],2)
        self.assertEqual((await self.edit(body,key=missing)).status_code,409)

    async def test_recovery_rejects_changed_identity_and_holds_changed_profiles(self):
        key=str(uuid4());body=self.review()
        self.assertEqual((await self.edit(body,key=key)).status_code,200)
        for attempted,client in [(self.review(quantity='9'),self.catalog),(body,self.other)]:
            held=(await self.status(attempted,key,client=client)).json()
            self.assertEqual(held['outcome'],'held');self.assertIsNone(held['review']);self.assertIsNone(held['current_review'])
        async with self.pool.acquire() as c:
            await c.execute("UPDATE store_items SET count_unit='bag' WHERE store_id='berts' AND item_code='test_food'")
        self.assertEqual((await self.status(body,str(uuid4()),version=1)).json()['outcome'],'held')
        self.assertEqual((await self.status(body,key)).json()['outcome'],'saved_current')

    async def test_recovery_withdrawal_authorization_and_missing_storage(self):
        self.assertEqual((await self.edit()).status_code,200)
        body=dict(action='withdraw',coverage_note='Fictional review withdrawal',verified=True);key=str(uuid4())
        self.assertEqual((await self.status(body,key,version=1)).json()['outcome'],'retry_available')
        self.assertEqual((await self.edit(body,key=key,version=1)).status_code,200)
        result=(await self.status(body,key,version=1)).json()
        self.assertEqual(result['outcome'],'saved_current');self.assertFalse(result['review']['confirmed'])
        for role,locations in [('readonly',['berts']),('manager',['rudds'])]:
            token=server._token(dict(id='synthetic-denied',role=role,locations=locations,email='test@example.invalid'))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://test',headers={'Authorization':'Bearer '+token}) as client:
                self.assertEqual((await self.status(body,key,version=1,client=client)).status_code,403)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://test') as client:
            self.assertEqual((await self.status(body,key,version=1,client=client)).status_code,401)
        with patch.object(pars,'installed',return_value=False):
            self.assertEqual((await self.status(body,key,version=1)).json()['outcome'],'held')

    async def test_unconfirmed_legacy_default_and_missing_installation_are_not_zero_targets(self):
        self.assertFalse(self.before_install['available'])
        self.assertTrue(all(r['status']=='unconfirmed' and r['review'] is None for r in self.before_install['items']))
        row=next(r for r in (await self.read())['items'] if r['code']=='test_food')
        self.assertEqual(row['status'],'unconfirmed');self.assertIsNone(row['review'])
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM purchasing.inventory_par_versions'),0)
            self.assertEqual(await c.fetchval("SELECT par FROM store_items WHERE store_id='berts' AND item_code='test_food'"),self.legacy)

    async def test_exact_target_zero_withdrawal_and_actor_are_metadata_only(self):
        _,a,b=await self.pair();report=(await self.report(a,b)).json()
        first=await self.edit();self.assertEqual(first.status_code,200,first.text)
        p=first.json()['review'];self.assertEqual(p['quantity'],'1.5');self.assertEqual(Decimal(p['base_quantity']),Decimal('30'))
        self.assertEqual(p['base_unit'],'lb');self.assertEqual(p['actor'],'synthetic-owner')
        self.assertEqual(next(r for r in (await self.read())['items'] if r['code']=='test_food')['status'],'confirmed')
        zero=await self.edit(self.review(quantity='0'),version=1);self.assertEqual(zero.status_code,200,zero.text)
        self.assertEqual(zero.json()['review']['base_quantity'],'0')
        withdrawn=await self.edit(dict(action='withdraw',coverage_note='Hold this target',verified=True),version=2)
        self.assertEqual(withdrawn.status_code,200,withdrawn.text)
        row=next(r for r in (await self.read())['items'] if r['code']=='test_food')
        self.assertEqual(row['status'],'unconfirmed');self.assertFalse(row['review']['confirmed'])
        self.assertEqual(report,(await self.report(a,b)).json())
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM purchase_orders'),0)
            self.assertEqual(await c.fetchval('SELECT count(*) FROM prep_logs'),0)
            self.assertEqual(await c.fetchval("SELECT par FROM store_items WHERE store_id='berts' AND item_code='test_food'"),self.legacy)

    async def test_parallel_retries_and_stale_versions_never_replace_a_newer_target(self):
        key=str(uuid4());same=await asyncio.gather(self.edit(key=key),self.edit(key=key))
        for r in same:self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(same[0].json()['review'],same[1].json()['review'])
        raced=await asyncio.gather(self.edit(self.review(quantity='2'),version=1),self.edit(self.review(quantity='3'),version=1))
        self.assertEqual(sorted(r.status_code for r in raced),[200,409])
        replay=await self.edit(key=key);self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json()['review']['revision'],1);self.assertEqual(replay.json()['current_review']['revision'],2)
        self.assertEqual((await self.edit(self.review(quantity='9'),key=key)).status_code,409)
        self.assertEqual((await self.edit(key=key,client=self.other)).status_code,409)

    async def test_changed_supplier_keeps_target_and_changed_count_conversion_requires_review(self):
        self.assertEqual((await self.edit()).status_code,200)
        async with self.pool.acquire() as c:await c.execute('UPDATE vendor_items SET pack_count=9 WHERE id=$1',self.sku)
        row=next(r for r in (await self.read())['items'] if r['code']=='test_food')
        self.assertEqual(row['status'],'confirmed');self.assertEqual(Decimal(row['review']['base_quantity']),Decimal('30'))
        async with self.pool.acquire() as c:await c.execute("UPDATE store_items SET count_unit='bag' WHERE store_id='berts' AND item_code='test_food'")
        row=next(r for r in (await self.read())['items'] if r['code']=='test_food')
        self.assertEqual(row['status'],'needs_review');self.assertEqual(Decimal(row['review']['base_quantity']),Decimal('30'));self.assertIsNone(row['count_profile'])
        self.assertEqual((await self.edit(version=1)).status_code,409)
        new,_=await self.units('count',factor='5');self.assertEqual(new.status_code,200,new.text)
        confirmed=await self.edit(self.review(unit_profile_id=new.json()['profile']['id'],quantity='6'),version=1)
        self.assertEqual(confirmed.status_code,200,confirmed.text);self.assertEqual(confirmed.json()['review']['base_quantity'],'30')

    async def test_missing_units_wrong_location_access_and_missing_revision_are_refused(self):
        for body in (self.review(unit_profile_id=None),self.review(quantity=None)):
            self.assertEqual((await self.edit(body)).status_code,422)
        purchase,_=await self.units('purchase');self.assertEqual(purchase.status_code,200,purchase.text)
        self.assertEqual((await self.edit(self.review(unit_profile_id=purchase.json()['profile']['id']))).status_code,409)
        self.assertEqual((await self.edit(store='rudds')).status_code,422)
        self.assertEqual((await self.edit(code='prep_sauce')).status_code,422)
        missing=await self.owner_client.put('/api/pg/purchases/berts/inventory-pars/test_food',json=self.review(),headers={'Idempotency-Key':str(uuid4())})
        self.assertEqual(missing.status_code,428)
        for role,locations in [('readonly',['berts']),('manager',['rudds'])]:
            token=server._token(dict(id='synthetic-denied',role=role,locations=locations,email='test@example.invalid'))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://test',headers={'Authorization':'Bearer '+token}) as client:
                self.assertEqual((await self.edit(client=client)).status_code,403)
        async with self.pool.acquire() as c:self.assertEqual(await c.fetchval('SELECT count(*) FROM purchasing.inventory_par_versions'),0)

    async def test_history_guards_and_failed_insert_roll_back_review_and_store_revision(self):
        self.assertEqual((await self.edit()).status_code,200)
        async with self.pool.acquire() as c:
            revision=await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'")
            for sql in ('DELETE FROM purchasing.inventory_par_versions','UPDATE purchasing.inventory_par_versions SET quantity=9','TRUNCATE purchasing.inventory_par_versions'):
                with self.assertRaises(asyncpg.PostgresError):await c.execute(sql)
            await c.execute("""CREATE FUNCTION public.fail_inventory_par_test() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Fictional failure'; END $$;
                CREATE TRIGGER failed_inventory_par_test AFTER INSERT ON purchasing.inventory_par_versions FOR EACH ROW EXECUTE FUNCTION public.fail_inventory_par_test();""")
        with self.assertRaises(asyncpg.PostgresError):await self.edit(version=1)
        async with self.pool.acquire() as c:
            self.assertEqual(await c.fetchval('SELECT count(*) FROM purchasing.inventory_par_versions'),1)
            self.assertEqual(await c.fetchval("SELECT revision FROM store_state WHERE store_id='berts'"),revision)
            self.assertTrue(await c.fetchval("SELECT relrowsecurity FROM pg_class WHERE oid='purchasing.inventory_par_versions'::regclass"))

    async def test_review_history_exact_retry_and_accounting_survive_disposable_restore(self):
        _,a,b=await self.pair();report=(await self.report(a,b)).json()
        key=str(uuid4());first=await self.edit(key=key);self.assertEqual(first.status_code,200,first.text)
        self.assertEqual((await self.edit(self.review(quantity='0'),version=1)).status_code,200)
        before=await self.read();manifest=await backup.create_backup(self.source,recovery.PG_DUMP,self.directory)
        self.assertEqual(manifest['tables']['purchasing.inventory_par_versions']['rows'],2)
        dsn=await self.target();self.assertEqual((await backup.verify_restore(dsn,self.directory))['status'],'verified')
        pool=await asyncpg.create_pool(dsn,min_size=1,max_size=2,init=recovery.db_pg._init_connection)
        old=server.db_pg._pool;server.db_pg._pool=pool
        try:
            self.assertEqual(await self.read(),before)
            replay=await self.edit(key=key);self.assertEqual(replay.status_code,200,replay.text)
            self.assertEqual(replay.json()['review']['revision'],1);self.assertEqual(replay.json()['current_review']['revision'],2)
            async with pool.acquire() as c:
                restored=await recovery.actual.period_report(c,'berts',UUID(a['header']['id']),UUID(b['header']['id']))
            self.assertEqual(server.purchase_api.serial(restored),report)
        finally:server.db_pg._pool=old;await pool.close()

    async def test_small_and_large_exact_targets_roundtrip_without_float_rounding(self):
        profile,_=await self.units('count',factor='20.000000000000000000')
        self.assertEqual(profile.status_code,200,profile.text);self.profile=profile.json()['profile']
        for index,quantity in enumerate(('0.000000000001','123456789012345.123456789012','1.000000000000000000','9999999999999999.999999999999')):
            saved=await self.edit(self.review(quantity=quantity),version=index);self.assertEqual(saved.status_code,200,saved.text)
            value=saved.json()['review']
            self.assertEqual(Decimal(value['quantity']),Decimal(quantity))
            with __import__('decimal').localcontext() as ctx:
                ctx.prec=80;expected=Decimal(quantity)*Decimal(20)
            self.assertEqual(Decimal(value['base_quantity']),expected)
            self.assertEqual(next(r for r in (await self.read())['items'] if r['code']=='test_food')['status'],'confirmed')

    async def test_fixed_decimal_save_replay_reads_and_history_preserve_exact_request_identity(self):
        async with self.pool.acquire() as c:
            await c.execute("UPDATE store_items SET par=0.0000001 WHERE store_id='berts' AND item_code='test_food'")
        profile,_=await self.units('count',factor='0.0000001')
        self.assertEqual(profile.status_code,200,profile.text);self.profile=profile.json()['profile']
        first_key=str(uuid4());first_body=self.review(quantity='0.0000001')
        for index,quantity in enumerate(('0.0000001','0E-10')):
            key=first_key if index==0 else str(uuid4());body=self.review(quantity=quantity)
            saved=await self.edit(body,version=index,key=key);self.assertEqual(saved.status_code,200,saved.text)
            expected=dict(quantity=format(Decimal(quantity),'f'),factor='0.0000001',base_quantity=format(Decimal(quantity)*Decimal('0.0000001'),'f'))
            for field,text in expected.items():self.assertEqual(saved.json()['review'][field],text)
            row=next(r for r in (await self.read())['items'] if r['code']=='test_food')
            self.assertEqual(row['legacy_quantity'],'0.0000001')
            for field,text in expected.items():self.assertEqual(row['review'][field],text)
            replay=await self.edit(body,version=index,key=key);self.assertEqual(replay.status_code,200,replay.text)
            self.assertEqual(replay.json()['review'],saved.json()['review'])
            digest=pars.fingerprint(pars.serial(dict(store='berts',item='test_food',actor='synthetic-owner',expected=index,body=pars.Review(**body).model_dump())))
            async with self.pool.acquire() as c:
                stored=await c.fetchrow('SELECT quantity,request_fingerprint FROM purchasing.inventory_par_versions WHERE request_key=$1',UUID(key))
            self.assertEqual(stored['quantity'],Decimal(quantity));self.assertEqual(stored['request_fingerprint'],digest)
        history=await self.catalog.get('/api/pg/purchases/berts/inventory-pars/test_food/history')
        self.assertEqual(history.status_code,200,history.text)
        self.assertEqual([p['quantity'] for p in history.json()],['0.0000001','0.0000000000'])
        replay=await self.edit(first_body,key=first_key);self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json()['review']['quantity'],'0.0000001')
        self.assertEqual(replay.json()['current_review']['quantity'],'0.0000000000')
