"""Stored, unclassified prep history on invented local databases only."""
import os
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4
import asyncpg
import server
import purchase_api
import hosted_staff_production as accounting
import deployment_readiness as readiness
import runtime_role_fixture as permissions
from test_runtime_task_cutover import TaskHistoryFixture
from test_legacy_prep_cutover import LegacyPrepCutoverTests


class ArchiveHistoryFixture(TaskHistoryFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        try:
            await self.seed_archive()
        except BaseException:
            await super().asyncTearDown()
            raise

    async def seed_archive(self):
        async with self.pool.acquire() as conn:
            for store, day, kind in [('berts','2026-10-03',None), ('berts','2026-10-04','commissary'), ('berts','2026-10-05','monthly_high_value'), ('berts','2026-10-06','full_inventory'), ('rudds','2026-10-01',None)]:
                await conn.execute("INSERT INTO prep_lists(store_id,prep_date,count_type,status) VALUES($1,$2::text::date,$3,'draft')",store,day,kind)
            await conn.execute("""UPDATE prep_list_lines SET yield_qty=123456789012345.000000000001,
                on_hand=NULL,make_qty=0.000000000001,note='Invented <note>\nsecond line',done_by_name=NULL
                WHERE recipe_id=$1""",self.retained['prep_list_lines'])
            self.headers = purchase_api.serial([dict(r) for r in await conn.fetch("SELECT * FROM prep_lists WHERE store_id='berts' ORDER BY prep_date,id")])
            self.lines = purchase_api.serial([dict(r) for r in await conn.fetch("SELECT l.* FROM prep_list_lines l JOIN prep_lists p ON p.id=l.list_id WHERE p.store_id='berts' ORDER BY l.list_id,l.id")])


class PrepListArchiveTests(permissions.RuntimeRoleMixin,ArchiveHistoryFixture):
    async def test_prep_archive_all_classifications_and_exact_stored_values_preserve_track1(self):
        _, opening, closing = await self.pair()
        source,*_ = await self.capture()
        self.assertEqual((await self.post(source['documents'][0])).status_code,200)
        report = (await self.report(opening,closing)).json()
        async with self.pool.acquire() as conn:
            facts = await accounting.accounting_fingerprints(conn,'berts')
        with patch.dict(os.environ,{name+'_ENABLED':'false' for name in readiness.FEATURES}):
            result = await self.catalog.get('/api/pg/prep-list-archive/berts')
            self.assertEqual(result.status_code,200,result.text)
            data = result.json();self.assertEqual(data['storeId'],'berts')
            self.assertTrue(data['archived']);self.assertFalse(data['operational']);self.assertIsNone(data['nextCursor'])
            rows = data['records'];self.assertEqual(len(rows),6)
            self.assertEqual([r['header'] for r in rows],self.headers)
            self.assertEqual(sorted([line for r in rows for line in r['lines']],key=lambda r:(r['list_id'],r['id'])),self.lines)
            self.assertEqual({r['classification'] for r in rows},{'daily','bulk','unclassified','other'})
            for row in rows:
                self.assertEqual(row['countType'],row['header']['count_type'])
                self.assertEqual(row['storeId'],'berts');self.assertEqual(row['basis'],'legacy_prep_archive')
                self.assertTrue(row['archived']);self.assertFalse(row['operational'])
                if row['countType'] is None:
                    self.assertEqual(row['classification'],'unclassified');self.assertIsNone(row['track'])
                elif row['classification']=='other':self.assertIsNone(row['track'])
            line=next(line for r in rows for line in r['lines'])
            self.assertEqual(line['yield_qty'],'123456789012345.000000000001')
            self.assertIsNone(line['on_hand']);self.assertIsInstance(line['make_qty'],str)
            self.assertEqual(Decimal(line['make_qty']),Decimal('0.000000000001'))
            self.assertEqual((await self.catalog.get('/api/pg/preplists/berts')).status_code,410)
        async with self.pool.acquire() as conn:
            self.assertEqual(await accounting.accounting_fingerprints(conn,'berts'),facts)
            self.assertEqual(purchase_api.serial([dict(r) for r in await conn.fetch("SELECT * FROM prep_lists WHERE store_id='berts' ORDER BY prep_date,id")]),self.headers)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM prep_inventory.task_assignments'),0)
        self.assertEqual((await self.report(opening,closing)).json(),report)

    async def test_prep_archive_pagination_filter_and_cursor_validation(self):
        all_rows=[];cursor={}
        for _ in range(4):
            result=await self.catalog.get('/api/pg/prep-list-archive/berts',params={'limit':2,**cursor})
            self.assertEqual(result.status_code,200,result.text)
            data=result.json();all_rows+=data['records']
            if not data['nextCursor']:break
            cursor=data['nextCursor']
        self.assertEqual([r['id'] for r in all_rows],[r['id'] for r in self.headers])
        self.assertEqual(len({r['id'] for r in all_rows}),6)
        for classification,size in [('unclassified',2),('daily',1),('bulk',1),('other',2)]:
            result=await self.catalog.get('/api/pg/prep-list-archive/berts',params={'classification':classification})
            self.assertEqual(result.status_code,200,result.text);self.assertEqual(len(result.json()['records']),size)
        result=await self.catalog.get('/api/pg/prep-list-archive/berts',params={'date_from':'2026-10-02','date_through':'2026-10-02'})
        self.assertEqual(len(result.json()['records']),1)
        for params in ({'limit':201},{'classification':'guessed'},{'after_date':'2026-10-01'},
                       {'after_id':str(uuid4())},{'after_date':'2026-10-01','after_id':str(uuid4())},
                       {'after_date':'2026-10-01','after_id':'invalid'},
                       {'date_from':'2026-10-02','date_through':'2026-10-01'},
                       {'date_from':'invalid'}):
            result=await self.catalog.get('/api/pg/prep-list-archive/berts',params=params)
            self.assertEqual(result.status_code,422,result.text)
        async with self.pool.acquire() as conn:
            other=await conn.fetchval("SELECT id FROM prep_lists WHERE store_id='rudds'")
        self.assertEqual((await self.catalog.get('/api/pg/prep-list-archive/berts',params={'after_date':'2026-10-01','after_id':str(other)})).status_code,422)

    async def test_prep_archive_manager_scope_and_no_mutation_routes(self):
        for role,locations in [('manager',['rudds']),('staff',['berts']),('readonly',['berts'])]:
            token=server._token({'id':'invented-scope','email':'scope@example.invalid','role':role,'locations':locations})
            self.assertEqual((await self.catalog.get('/api/pg/prep-list-archive/berts',headers={'Authorization':'Bearer '+token})).status_code,403)
        self.assertEqual((await self.catalog.get('/api/pg/prep-list-archive/berts',headers={'Authorization':''})).status_code,401)
        self.assertEqual((await self.catalog.post('/api/pg/prep-list-archive/berts',json={})).status_code,405)
        self.assertEqual((await self.catalog.put('/api/pg/prep-list-archive/berts',json={})).status_code,405)
        with patch('server.USE_PG',False):
            self.assertEqual((await self.catalog.get('/api/pg/prep-list-archive/berts')).status_code,503)
        self.assertEqual((await self.catalog.post('/api/pg/preplists/berts/generate',json={'date':'2026-10-01'})).status_code,409)
        async with self.pool.acquire() as conn:
            for table in ('prep_lists','prep_list_lines'):
                for privilege in ('INSERT','UPDATE','DELETE'):
                    self.assertFalse(await conn.fetchval('SELECT has_table_privilege(current_user,$1,$2)','public.'+table,privilege))


class PrecutoverArchiveTests(LegacyPrepCutoverTests):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        # This router holds db_pg.pool's callable, which reads the live pool.
        # Bind the disposable pool as well as the inherited function mock.
        current = patch('server.db_pg._pool', self.pool)
        current.start(); self.addCleanup(current.stop)

    async def test_prep_archive_before_installation_is_readonly_and_empty_is_confirmed(self):
        listing=uuid4()
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO prep_lists(id,store_id,prep_date,count_type) VALUES($1,'berts','2026-10-01',NULL)",listing)
        result=await self.web.get('/api/pg/prep-list-archive/berts')
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['records'][0]['classification'],'unclassified')
        self.assertEqual(result.json()['records'][0]['lines'],[])
        self.assertEqual((await self.web.get('/api/pg/prep-list-archive/rudds')).json()['records'],[])
        self.assertEqual((await self.web.get('/api/pg/preplists/berts',params={'date':'2026-10-01'})).status_code,200)
        async with self.pool.acquire() as conn:self.assertIsNone(await conn.fetchval('SELECT count_type FROM prep_lists WHERE id=$1',listing))
