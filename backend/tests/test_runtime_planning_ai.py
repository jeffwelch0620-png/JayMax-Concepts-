"""Invented forecast/chat history and accounting isolation under the local role."""
import asyncio,os
from unittest.mock import patch
import asyncpg
import server
import hosted_staff_production as accounting
import runtime_role_fixture as permissions
from test_runtime_manager_workflows import MenuHistoryFixture

class PlanningAIFixture(MenuHistoryFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("INSERT INTO store_sales_projections(store_id,date,amount,note) VALUES('berts','2026-10-09',321.09,'Invented forecast')")
                await conn.execute("INSERT INTO ai_chat_messages(id,store_id,role,content,ts) VALUES('00000000-0000-0000-0000-000000000002','berts','assistant','Invented answer','2026-10-01T12:00Z'),('00000000-0000-0000-0000-000000000001','berts','user','Invented history','2026-10-01T12:00Z')")
        except BaseException:
            await super().asyncTearDown()
            raise

class PlanningAITests(permissions.RuntimeRoleMixin,PlanningAIFixture):
    async def test_planning_ai_reproduction_forecast_read(self):
        result=await self.catalog.get('/api/projections/berts')
        self.assertEqual(result.status_code,200,result.text)
        row=result.json()[0]
        self.assertEqual(row['amount'],'321.09')
        self.assertEqual(row['basis'],'manual_sales_forecast')
        self.assertFalse(row['accounting'])

    async def test_planning_ai_reproduction_history_read(self):
        result=await self.catalog.get('/api/ai/history/berts')
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual([m['content'] for m in result.json()],['Invented history','Invented answer'])
        status=await self.catalog.get('/api/ai/capabilities/berts')
        self.assertEqual(status.json(),dict(storeId='berts',basis='ai_conversation_storage',historyAvailable=True,chatAvailable=False,clearAvailable=False,accounting=False))
        with patch('server._ai') as provider:
            chat=await self.catalog.post('/api/ai/chat',json={'restaurantId':'berts','message':'Invented request'})
            self.assertEqual(chat.status_code,503,chat.text)
            provider.assert_not_called()
        clear=await self.catalog.delete('/api/ai/history/berts')
        self.assertEqual(clear.status_code,503,clear.text)
        self.assertEqual((await self.catalog.get('/api/ai/history/berts')).json(),result.json())

    async def test_planning_ai_reproduction_owner_forecast_requires_review(self):
        owner=await asyncpg.create_pool(os.environ['NATIVE_PURCHASE_TEST_DSN'].rsplit('/',1)[0]+'/'+self.db,init=server.db_pg._init_connection)
        try:
            with patch('server.db_pg._pool',owner):
                result=await self.catalog.put('/api/projections/berts',json={'date':'2026-10-09','amount':'999','note':'Unreviewed overwrite'})
                self.assertEqual(result.status_code,428,result.text)
        finally:await owner.close()

    async def review(self,day='2026-10-09',store='berts'):
        result=await self.catalog.get('/api/projections/'+store+'/review',params={'date':day})
        self.assertEqual(result.status_code,200,result.text)
        return result.json()

    async def forecast(self,body,version=None,store='berts',**kwargs):
        headers=kwargs.pop('headers',{})
        if version is not None:headers['If-Match']=version
        return await self.catalog.put('/api/projections/'+store,json=body,headers=headers,**kwargs)

    async def test_planning_ai_versions_decimal_validation_and_scopes(self):
        before=await self.review()
        base=dict(date='2026-10-09',amount='0',note='Invented zero',enteredBy='spoofed actor')
        self.assertEqual((await self.forecast(base)).status_code,428)
        self.assertEqual((await self.forecast(base,'not-a-version')).status_code,422)
        for amount in (True,'-1','NaN','Infinity','1.001','10000000000.00'):
            result=await self.forecast({**base,'amount':amount},before['sourceVersion'])
            self.assertEqual(result.status_code,422,result.text)
        self.assertEqual((await self.forecast({**base,'date':'not-a-date'},before['sourceVersion'])).status_code,422)
        self.assertEqual((await self.forecast({**base,'note':'x'*2001},before['sourceVersion'])).status_code,422)
        self.assertEqual((await self.forecast(base,(await self.review('2026-10-10'))['sourceVersion'])).status_code,409)
        self.assertEqual((await self.forecast(base,(await self.review(store='rudds'))['sourceVersion'])).status_code,409)
        for role,locations in (('staff',['berts']),('readonly',['berts']),('manager',['rudds'])):
            token=server._token(dict(id='invented-'+role,role=role,email='invented@example.invalid',locations=locations))
            result=await self.forecast(base,before['sourceVersion'],headers={'Authorization':'Bearer '+token})
            self.assertEqual(result.status_code,403,result.text)
            if locations==['rudds']:
                for path in ('/api/ai/history/berts','/api/ai/capabilities/berts','/api/projections/berts/review?date=2026-10-09'):
                    self.assertEqual((await self.catalog.get(path,headers={'Authorization':'Bearer '+token})).status_code,403)
        self.assertEqual(await self.review(),before)
        saved=await self.forecast(base,before['sourceVersion'])
        self.assertEqual(saved.status_code,200,saved.text)
        self.assertEqual(saved.json()['projection']['amount'],'0.00')
        self.assertEqual(saved.json()['projection']['enteredBy'],'synthetic-catalog-reviewer')
        self.assertEqual((await self.forecast(base,before['sourceVersion'])).status_code,409)

    async def test_planning_ai_concurrent_existing_missing_and_accounting_isolation(self):
        _,opening,closing=await self.pair()
        source,*_=await self.capture()
        self.assertEqual((await self.post(source['documents'][0])).status_code,200)
        report=(await self.report(opening,closing)).json()
        async with self.pool.acquire() as conn:facts=await accounting.accounting_fingerprints(conn,'berts')
        revision=await self.revision()
        for day in ('2026-10-09','2026-10-10'):
            reviewed=await self.review(day)
            responses=await asyncio.gather(*(self.forecast(dict(date=day,amount=amount,note='Invented concurrent forecast'),reviewed['sourceVersion']) for amount in ('12.01','12.02')))
            self.assertEqual(sorted(r.status_code for r in responses),[200,409],[r.text for r in responses])
            accepted=next(r for r in responses if r.status_code==200).json()
            self.assertEqual(await self.review(day),{k:v for k,v in accepted.items() if k!='ok'})
        self.assertEqual(await self.revision(),revision)
        self.assertEqual((await self.report(opening,closing)).json(),report)
        async with self.pool.acquire() as conn:
            self.assertEqual(await accounting.accounting_fingerprints(conn,'berts'),facts)
        async with self.pool.acquire() as conn:
            for table,privileges in [('public.store_sales_projections',{'SELECT','INSERT','UPDATE'}),('public.ai_chat_messages',{'SELECT'})]:
                for privilege in ('SELECT','INSERT','UPDATE','DELETE','TRUNCATE'):
                    self.assertEqual(await conn.fetchval('SELECT has_table_privilege(current_user,$1,$2)',table,privilege),privilege in privileges)
