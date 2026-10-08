"""Candidate runtime grants, ONLY on unique loopback disposable databases.

No hosted apply path. Frozen SQL/object manifest fails closed on source drift.
Public RLS uses a dedicated trusted backend role; user scope stays in app gates.
"""
import hashlib,json,os,re
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
import asyncpg,db_pg,deployment_readiness as readiness

MANIFEST=readiness.ROOT/'docs/RUNTIME_PERMISSION_CANDIDATE.json'
PRIVATE_UPDATES={'purchasing.import_files','purchasing.document_identities','purchasing.document_versions',
    'purchasing.po_receipts','actual_inventory.scopes','actual_inventory.count_snapshots',
    'purchasing.store_vendor_items','purchasing.store_supplier_contacts'}
PUBLIC={
    'stores':('SELECT',),'items':('SELECT','INSERT','UPDATE'),
    'store_items':('SELECT','INSERT','UPDATE'),'vendor_items':('SELECT','INSERT','UPDATE'),
    'vendors':('SELECT','INSERT','UPDATE'),'dishes':('SELECT','INSERT','UPDATE'),
    'dish_lines':('SELECT','INSERT','UPDATE','DELETE'),'prep_items':('SELECT','INSERT','UPDATE'),
    'staff_members':('SELECT','INSERT','UPDATE'),'store_state':('SELECT','INSERT','UPDATE'),
    'activity_log':('SELECT','INSERT'),'purchase_orders':('SELECT','INSERT','UPDATE'),
    'purchase_order_lines':('SELECT','INSERT','UPDATE','DELETE'),
    'invoices':('SELECT',),'invoice_lines':('SELECT',),'prep_logs':('SELECT',),
    'count_sessions':('SELECT',),'count_lines':('SELECT',),'reporting_periods':('SELECT',),'store_vendor_contacts':('SELECT',),
    'staff_pins':('SELECT',)}

def manifest():
    value=json.loads(MANIFEST.read_text())
    if value['publication']!='candidate; local test only':raise ValueError('Unreviewed profile')
    for name,digest in value['migrationSha256'].items():
        if hashlib.sha256((readiness.ROOT/'migrations'/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Reviewed runtime SQL drift')
    if set(value['migrationSha256'])!=set(readiness.MIGRATIONS):raise ValueError('Reviewed runtime migration list drift')
    return value

async def apply(conn,role):
    address=await conn.fetchval('SELECT inet_server_addr()::text')
    database=await conn.fetchval('SELECT current_database()')
    if address!='127.0.0.1/32' and address!='127.0.0.1':raise ValueError('Runtime fixture requires loopback')
    if not re.fullmatch(r'native_purchase_test_[a-f0-9]{32}',database):raise ValueError('Unique disposable database required')
    if not re.fullmatch(r'native_runtime_test_[a-f0-9]{32}',role):raise ValueError('Unique invented role required')
    flags=await conn.fetchrow('SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=$1',role)
    if not flags or any(flags.values()):raise ValueError('Unprivileged role required')
    profile=manifest();present=[]
    for schema in readiness.PRIVATE:await conn.execute('GRANT USAGE ON SCHEMA '+schema+' TO '+role)
    for name in profile['tables']+profile['views']:
        if not await conn.fetchval('SELECT to_regclass($1) IS NOT NULL',name):continue
        privileges=['SELECT']
        if name in profile['tables'] and name!='purchasing.base_units':privileges.append('INSERT')
        if name in PRIVATE_UPDATES:privileges.append('UPDATE')
        await conn.execute('GRANT '+','.join(privileges)+' ON '+name+' TO '+role);present.append(name)
    functions=await conn.fetch("SELECT n.nspname||'.'||p.proname AS name,p.oid::regprocedure::text AS signature,p.prosecdef FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=ANY($1::text[]) AND p.prorettype<>'trigger'::regtype",list(readiness.PRIVATE))
    for row in functions:
        if row['name'] not in profile['functionNames'] or row['prosecdef']:raise ValueError('Unreviewed runtime function')
        await conn.execute('GRANT EXECUTE ON FUNCTION '+row['signature']+' TO '+role)
    await conn.execute('GRANT USAGE ON SCHEMA public TO '+role)
    for table,privileges in PUBLIC.items():
        await conn.execute('GRANT '+','.join(privileges)+' ON public.'+table+' TO '+role)
        for verb in privileges:
            clauses='WITH CHECK (true)' if verb=='INSERT' else 'USING (true) WITH CHECK (true)' if verb=='UPDATE' else 'USING (true)'
            await conn.execute('CREATE POLICY runtime_candidate_'+verb.lower()+' ON public.'+table+' FOR '+verb+' TO '+role+' '+clauses)
    return {'nativeObjects':len(present),'functions':len(functions),'completeNativeObjectSet':set(present)==set(profile['tables']+profile['views'])}

async def role_setup(conn,role):
    await conn.execute('SET ROLE '+role)
    flags=dict(await conn.fetchrow('SELECT current_user AS name,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=current_user'))
    if flags['name']!=role or any(flags[k] for k in flags if k!='name'):raise AssertionError('Runtime acquisition is privileged')
    if await conn.fetchval('SELECT count(*) FROM pg_class WHERE relnamespace=ANY(SELECT oid FROM pg_namespace WHERE nspname=ANY($1::text[])) AND relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)',list(readiness.PRIVATE)):
        raise AssertionError('Runtime role owns private objects')

class RuntimeRoleMixin:
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.runtime_role='native_runtime_test_'+uuid4().hex
        await self.admin.execute('CREATE ROLE '+self.runtime_role+' NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT')
        async def cleanup():
            conn=await asyncpg.connect(os.environ['NATIVE_PURCHASE_TEST_DSN'])
            try:await conn.execute('DROP ROLE '+self.runtime_role)
            finally:await conn.close()
        self.addAsyncCleanup(cleanup)
        async with self.pool.acquire() as conn:
            # Existing fixture classes install only their own workflow chain.
            # Complete the reviewed native chain as administrator before grants.
            for entry in readiness.migration_plan()['migrations'][:-1]:
                present=[bool(await conn.fetchval('SELECT to_regclass($1) IS NOT NULL',name)) for name in entry['tables']]
                if present and any(present) and not all(present):raise ValueError('Partially installed fixture migration')
                if present:installed=all(present)
                else:
                    installed=all([bool(await conn.fetchval("SELECT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=$1 AND p.proname=$2)",*name.split('.'))) for name in entry['functions']])
                if not installed:await conn.execute((readiness.ROOT/'migrations'/entry['file']).read_text())
            # Revoke inherited PUBLIC/native RPC access before testing the profile.
            await conn.execute((readiness.ROOT/'migrations/20261007_native_private_access.sql').read_text())
            self.permission_result=await apply(conn,self.runtime_role)
            if not self.permission_result['completeNativeObjectSet']:raise AssertionError('Complete reviewed native fixture required')
        old_pool=self.pool
        import server
        server_bound=server.db_pg._pool is old_pool
        await old_pool.close()
        dsn=os.environ['NATIVE_PURCHASE_TEST_DSN'].rsplit('/',1)[0]+'/'+self.db
        async def setup(conn):await role_setup(conn,self.runtime_role)
        self.pool=await asyncpg.create_pool(dsn,min_size=1,max_size=5,init=db_pg._init_connection,setup=setup)
        # Actual server fixtures hold a direct pool reference in addition to routers.
        if server_bound:server.db_pg._pool=self.pool
