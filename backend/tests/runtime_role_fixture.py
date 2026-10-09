"""Candidate runtime grants, ONLY on unique loopback disposable databases.

No hosted apply path. Frozen SQL/object manifest fails closed on source drift.
Public RLS uses a dedicated trusted backend role; user scope stays in app gates.
"""
import os,re
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
import asyncpg,db_pg,deployment_readiness as readiness

import runtime_permissions as candidate
MANIFEST=candidate.MANIFEST
PRIVATE_UPDATES=candidate.PRIVATE_UPDATES
PUBLIC=candidate.PUBLIC
manifest=candidate.manifest

async def apply(conn,role,reference='local'):
    address=await conn.fetchval('SELECT inet_server_addr()::text')
    database=await conn.fetchval('SELECT current_database()')
    if address!='127.0.0.1/32' and address!='127.0.0.1':raise ValueError('Runtime fixture requires loopback')
    if not re.fullmatch(r'native_purchase_test_[a-f0-9]{32}',database):raise ValueError('Unique disposable database required')
    if not re.fullmatch(r'native_runtime_test_[a-f0-9]{32}',role):raise ValueError('Unique invented role required')
    flags=await conn.fetchrow('SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=$1',role)
    if not flags or any(flags.values()):raise ValueError('Unprivileged role required')
    profile=manifest();present=[]
    allowed=candidate.table_privileges(profile)
    expected=candidate.contract(profile,reference)
    async with conn.transaction(readonly=True):
        await conn.execute('SET LOCAL search_path=pg_catalog')
        live=await candidate.catalog_contracts(conn)
    if live['functions']!=expected['functions']:raise ValueError('Reviewed function signature/body drift')
    for schema in readiness.PRIVATE:await conn.execute('GRANT USAGE ON SCHEMA '+schema+' TO '+role)
    for name in profile['tables']+profile['views']:
        if not await conn.fetchval('SELECT to_regclass($1) IS NOT NULL',name):continue
        privileges=allowed[name]
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
        # The installer preserves exact SQL bytes. Older workflow fixtures use
        # read_text(), which normalizes CRLF even within a function body/literal.
        # Keep that reference identical ONLY for reviewed fixture SQL paths.
        reviewed={readiness.ROOT/'supabase/schema.sql'} | {readiness.ROOT/'migrations'/name for name in readiness.MIGRATIONS}
        original_read=Path.read_text
        def exact_sql(path,*args,**kwargs):
            if path in reviewed:
                encoding=kwargs.get('encoding') or (args[0] if args else None) or 'utf-8'
                return path.read_bytes().decode(encoding,errors=kwargs.get('errors') or 'strict')
            return original_read(path,*args,**kwargs)
        with patch.object(Path,'read_text',exact_sql):
            await super().asyncSetUp()
        try:
            await self.prepare_runtime()
        except BaseException:
            # unittest skips asyncTearDown when asyncSetUp fails. This fixture's
            # parent setup completed, so close its own clients/pools and drop its
            # exact invented DB before the registered DROP ROLE cleanup.
            await super().asyncTearDown()
            raise

    async def prepare_runtime(self):
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
                if not installed:await conn.execute((readiness.ROOT/'migrations'/entry['file']).read_bytes().decode('utf-8'))
            # Revoke inherited PUBLIC/native RPC access before testing the profile.
            await conn.execute((readiness.ROOT/'migrations/20261007_native_private_access.sql').read_bytes().decode('utf-8'))
            self.permission_result=await apply(conn,self.runtime_role)
            if not self.permission_result['completeNativeObjectSet']:raise AssertionError('Complete reviewed native fixture required')
        old_pool=self.pool
        import server
        server_bound=server.db_pg._pool is old_pool
        await old_pool.close()
        dsn=os.environ['NATIVE_PURCHASE_TEST_DSN'].rsplit('/',1)[0]+'/'+self.db
        self.pool=await self.runtime_pool(dsn)
        # Actual server fixtures hold a direct pool reference in addition to routers.
        if server_bound:server.db_pg._pool=self.pool

    async def runtime_pool(self,dsn):
        async def setup(conn):await role_setup(conn,self.runtime_role)
        return await asyncpg.create_pool(dsn,min_size=1,max_size=5,init=db_pg._init_connection,setup=setup)
