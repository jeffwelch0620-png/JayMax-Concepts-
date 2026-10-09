"""Temporary two-LOGIN canary on the explicitly designated hosted build database.

Only generated roles, exact grants and role-addressed policies are committed.
Clients default to read-only. No account, invoice, push or native business writes.
Connection material stays in memory; diagnostics retain types and frames only.
"""
import argparse
import asyncio
from contextlib import AsyncExitStack
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import traceback
from urllib.parse import quote, urlparse, urlunparse
import asyncpg
import auxiliary_permissions as auxiliary
import db_auxiliary
import db_pg
import hosted_test_trial
import runtime_permissions as candidate
from dotenv import dotenv_values

def quoted(value):
    return '"' + value.replace('"', '""') + '"'

async def snapshot(conn):
    """Hash effective object ACL entries, policies and ledger; retain no business rows."""
    namespaces=['public', *auxiliary.PRIVATE]
    async with conn.transaction(isolation='repeatable_read', readonly=True):
        await conn.execute("SET LOCAL search_path=pg_catalog; SET LOCAL statement_timeout='20s'")
        catalog=await candidate.catalog_contracts(conn)
        acl=await conn.fetch('''
          SELECT 'schema' AS kind,nspname AS name,a.grantor,a.grantee,a.privilege_type,a.is_grantable
          FROM pg_namespace CROSS JOIN LATERAL aclexplode(coalesce(nspacl,acldefault('n',nspowner))) a
          WHERE nspname=ANY($1::text[])
          UNION ALL SELECT 'relation',n.nspname||'.'||c.relname,a.grantor,a.grantee,a.privilege_type,a.is_grantable
          FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
          CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault(CASE WHEN c.relkind='S' THEN 's'::"char" ELSE 'r'::"char" END,c.relowner))) a
          WHERE n.nspname=ANY($1::text[]) AND c.relkind IN ('r','p','v','m','f','S')
          UNION ALL SELECT 'function',n.nspname||'.'||p.oid::text,a.grantor,a.grantee,a.privilege_type,a.is_grantable
          FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
          CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
          WHERE n.nspname=ANY($1::text[])''', namespaces)
        policies=[dict(r) for r in await conn.fetch('''SELECT n.nspname,c.relname,p.polname,p.polcmd::text,
          p.polpermissive,p.polroles,pg_get_expr(p.polqual,p.polrelid) AS using,
          pg_get_expr(p.polwithcheck,p.polrelid) AS check FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid
          JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[]) ORDER BY 1,2,3''', namespaces)]
        ledger=[dict(r) for r in await conn.fetch('SELECT version::text,name::text FROM supabase_migrations.schema_migrations ORDER BY version')]
        counts={name:await conn.fetchval('SELECT count(*) FROM '+name) for name in (
          'public.app_users','public.push_subscriptions','purchasing.posting_batches',
          'actual_inventory.count_snapshots','prep_inventory.batch_events')}
    canonical=sorted([dict(r) for r in acl],key=lambda r:json.dumps(r,sort_keys=True))
    return {'catalog':catalog,'aclSha256':candidate.digest(canonical),
            'policySha256':candidate.digest(policies),'ledgerSha256':candidate.digest(ledger),
            'observedRowCounts':counts}

async def run(config_path, expected_project, output):
    config=dotenv_values(config_path)
    identity=hosted_test_trial.designated_target(config,expected_project)
    if identity['connectionMode']!='session_pooler':
        raise ValueError('This reviewed canary requires the session pooler')
    manifest=candidate.manifest(); expected=candidate.contract(manifest,'hosted_build')
    matrix=candidate.table_privileges(manifest)
    functions=[s for s,v in expected['functions'].items() if v['name'].split('.')[0] in candidate.readiness.PRIVATE
               and not v['trigger'] and not v['securityDefiner']]
    roles={kind:'jaymax_'+kind+'_trial_'+secrets.token_hex(8) for kind in ('runtime','auxiliary')}
    assert all(re.fullmatch(r'jaymax_(runtime|auxiliary)_trial_[a-f0-9]{16}',v) for v in roles.values())
    passwords={kind:secrets.token_urlsafe(36) for kind in roles}
    uri=urlparse(config['DATABASE_URL'])
    urls={kind:urlunparse(uri._replace(netloc=quote(role+'.'+identity['projectRef'],safe='')+':'+
          quote(passwords[kind],safe='')+'@'+uri.hostname+':'+str(uri.port))) for kind,role in roles.items()}
    assert db_auxiliary.same_target(urls['runtime'],urls['auxiliary'])
    policies=[('runtime',table,verb,'runtime_candidate_'+verb.lower()) for table,verbs in candidate.PUBLIC.items() for verb in verbs]
    policies += [('auxiliary',table,verb,'auxiliary_candidate_'+verb.lower()) for table in auxiliary.TABLES for verb in auxiliary.VERBS]
    report={'format':'jaymax-hosted-two-pool-trial-v1','capturedAt':datetime.now(timezone.utc).isoformat(),
      'projectRef':identity['projectRef'],'connectionMode':identity['connectionMode'],'roles':roles,
      'status':'held','stage':'preflight','grantAttempted':False,'rolesRemoved':False,
      'operationalReleaseApproved':False,'businessRowsWritten':False,'externalServicesCalled':False,
      'permanentCredentialsConfigured':False,'applicationConfigurationChanged':False,'secretValuesIncluded':False}
    owner=None; pools=[]; baseline=None
    def progress(stage):
        report['stage']=stage
        safe={'status':'in_progress','stage':stage,'roles':roles,
              'capturedAt':datetime.now(timezone.utc).isoformat(),'secretValuesIncluded':False}
        if baseline:
            safe['baselineSnapshot']={k:v for k,v in baseline.items() if k!='catalog'}
            safe['baselineSnapshot']['catalogSha256']=candidate.digest(baseline['catalog'])
        journal=output.with_suffix('.progress.json')
        temporary=journal.with_suffix('.tmp')
        try:
            temporary.write_text(json.dumps(safe,indent=2)+'\n',encoding='utf-8')
            temporary.replace(journal)
        except OSError:
            if stage=='temporary_roles': raise
            report['progressJournalWriteHeld']=True
        print(json.dumps({'stage':stage}),flush=True)
    async def owner_connect():
        return await asyncpg.connect(config['DATABASE_URL'],ssl='require',timeout=20,command_timeout=25,statement_cache_size=0)
    try:
        progress('preflight')
        owner=await owner_connect(); baseline=await snapshot(owner)
        assert baseline['catalog']=={g:expected[g] for g in ('functions','relations')}, 'Hosted catalog held'
        assert not await owner.fetchval('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=ANY($1::text[]))',list(roles.values()))
        assert not await owner.fetchval("SELECT EXISTS(SELECT 1 FROM pg_policy WHERE polname LIKE 'runtime_candidate_%' OR polname LIKE 'auxiliary_candidate_%')")
        progress('temporary_roles'); report['grantAttempted']=True
        async with owner.transaction():
            await owner.execute("SET LOCAL statement_timeout='20s'; SET LOCAL lock_timeout='5s'")
            expiry=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
            for kind,role in roles.items():
                await owner.execute('CREATE ROLE '+quoted(role)+" LOGIN PASSWORD '"+passwords[kind]+
                    "' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT CONNECTION LIMIT 6 VALID UNTIL '"+expiry+"'")
                await owner.execute('ALTER ROLE '+quoted(role)+' SET default_transaction_read_only=on')
                await owner.execute('GRANT USAGE ON SCHEMA public TO '+quoted(role))
            for schema in candidate.readiness.PRIVATE:
                await owner.execute('GRANT USAGE ON SCHEMA '+quoted(schema)+' TO '+quoted(roles['runtime']))
            for name,verbs in matrix.items():
                await owner.execute('GRANT '+','.join(verbs)+' ON '+'.'.join(map(quoted,name.split('.')))+' TO '+quoted(roles['runtime']))
            for signature in functions:
                await owner.execute('GRANT EXECUTE ON FUNCTION '+signature+' TO '+quoted(roles['runtime']))
            for table in auxiliary.TABLES:
                await owner.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON public.'+quoted(table)+' TO '+quoted(roles['auxiliary']))
            for kind,table,verb,name in policies:
                clauses='WITH CHECK (true)' if verb=='INSERT' else 'USING (true) WITH CHECK (true)' if verb=='UPDATE' else 'USING (true)'
                await owner.execute('CREATE POLICY '+quoted(name)+' ON public.'+quoted(table)+' FOR '+verb+' TO '+quoted(roles[kind])+' '+clauses)
        report['temporaryPermissionsCommitted']=True
        progress('temporary_roles_committed')
        await owner.close(); owner=None
        sessions=[]
        for round_number in (1,2):
            progress('ordinary_login_pools_'+str(round_number))
            primary=await asyncpg.create_pool(urls['runtime'],ssl='require',min_size=1,max_size=5,statement_cache_size=0,
              init=db_pg._init_connection,timeout=20,command_timeout=25)
            pools.append(primary)
            secondary=await asyncio.wait_for(db_auxiliary._try_connect(urls['auxiliary']),90)
            assert secondary is not None, 'Auxiliary connection held'
            pools.append(secondary)
            async with AsyncExitStack() as stack:
                clients={kind:[await stack.enter_async_context(pool.acquire()) for _ in range(number)]
                    for kind,pool,number in (('runtime',primary,5),('auxiliary',secondary,3))}
                for kind,connections in clients.items():
                    for conn in connections:
                        # Pooler startup settings are not relied on for the read-only boundary.
                        await conn.execute('SET default_transaction_read_only=on')
                        who=dict(await conn.fetchrow("SELECT current_user AS current_role,session_user AS login_role,current_setting('transaction_read_only') AS read_only"))
                        assert who==dict(current_role=roles[kind],login_role=roles[kind],read_only='on')
                        assert await conn.fetchval("SELECT '{\"kind\":\"invented\"}'::jsonb")=={'kind':'invented'}
                        sessions.append({'poolRound':round_number,'connectionKind':kind,**who,'jsonCodecVerified':True})
                progress('permission_assessments_'+str(round_number))
                if round_number==1:
                    main=await asyncio.wait_for(candidate.inspect(clients['runtime'][0],roles['runtime'],'hosted_build'),240)
                    report['inventoryAssessment']=main
                    assert main['status']=='passed_local_candidate'
                aux=await asyncio.wait_for(auxiliary.inspect(clients['auxiliary'][0]),60)
                report['auxiliaryAssessment']=aux
                assert aux['status']=='passed'
                progress('boundary_reads_'+str(round_number))
                for kind,sql in (('runtime','SELECT count(*) FROM public.app_users'),
                                 ('auxiliary','SELECT count(*) FROM purchasing.posting_batches'),
                                 ('auxiliary','SELECT count(*) FROM public.staff_pins')):
                    try:
                        async with clients[kind][0].transaction(readonly=True): await clients[kind][0].fetchval(sql)
                    except asyncpg.InsufficientPrivilegeError: pass
                    else: raise AssertionError('Cross-boundary access was allowed')
                for table in auxiliary.TABLES:
                    await clients['auxiliary'][0].fetchval('SELECT count(*) FROM public.'+table)
                await clients['runtime'][0].fetchval('SELECT count(*) FROM actual_inventory.count_snapshots')
            progress('closing_client_pools_'+str(round_number))
            for pool in reversed(pools): await asyncio.wait_for(pool.close(),30)
            pools.clear()
        report.update(status='passed_hosted_two_pool_trial',stage='verified',authenticatedClients=sessions,
          sourceContractSha256=candidate.digest(expected),crossBoundaryReadsDenied=True)
    except Exception as exc:
        report.update(status='held',errorType=type(exc).__name__,errorFrames=[
          {'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(exc.__traceback__)])
    finally:
        progress('cleanup')
        for pool in reversed(pools):
            try: await asyncio.wait_for(pool.close(),30)
            except Exception: pool.terminate()
        if report['grantAttempted']:
            try:
                if owner is None or owner.is_closed(): owner=await owner_connect()
                present=[r['rolname'] for r in await owner.fetch('SELECT rolname FROM pg_roles WHERE rolname=ANY($1::text[])',list(roles.values()))]
                if present:
                    assert set(present)==set(roles.values()), 'Uncertain partial role creation'
                    async with owner.transaction():
                        await owner.execute("SET LOCAL statement_timeout='20s'; SET LOCAL lock_timeout='5s'")
                        for kind,table,verb,name in policies:
                            oid=await owner.fetchval('SELECT oid FROM pg_roles WHERE rolname=$1',roles[kind])
                            row=await owner.fetchrow('SELECT polroles FROM pg_policy WHERE polrelid=to_regclass($1) AND polname=$2','public.'+table,name)
                            assert row and list(row['polroles'])==[oid], 'Trial policy changed'
                            await owner.execute('DROP POLICY '+quoted(name)+' ON public.'+quoted(table))
                        for name,verbs in matrix.items():
                            await owner.execute('REVOKE '+','.join(verbs)+' ON '+'.'.join(map(quoted,name.split('.')))+' FROM '+quoted(roles['runtime']))
                        for signature in functions:
                            await owner.execute('REVOKE EXECUTE ON FUNCTION '+signature+' FROM '+quoted(roles['runtime']))
                        for table in auxiliary.TABLES:
                            await owner.execute('REVOKE SELECT,INSERT,UPDATE,DELETE ON public.'+quoted(table)+' FROM '+quoted(roles['auxiliary']))
                        for kind,role in roles.items():
                            for schema in (('public',*candidate.readiness.PRIVATE) if kind=='runtime' else ('public',)):
                                await owner.execute('REVOKE USAGE ON SCHEMA '+quoted(schema)+' FROM '+quoted(role))
                            await owner.execute('DROP ROLE '+quoted(role))
                report['rolesRemoved']=not await owner.fetchval('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=ANY($1::text[]))',list(roles.values()))
            except Exception as exc:
                report.update(status='held',cleanupErrorType=type(exc).__name__)
                for role in roles.values():
                    try: await owner.execute('ALTER ROLE '+quoted(role)+' NOLOGIN')
                    except Exception: pass
        if owner:
            try: await owner.close()
            except Exception: owner.terminate()
        # A new owner connection independently verifies cleanup and original ACLs.
        progress('independent_cleanup_verification')
        try:
            verifier=await owner_connect()
            try:
                after=await snapshot(verifier)
                absent=not await verifier.fetchval('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=ANY($1::text[]))',list(roles.values()))
            finally: await verifier.close()
            report.update(independentRoleAbsenceVerified=absent,baselineSnapshot=baseline,postTrialSnapshot=after,
                          catalogAclPoliciesLedgerAndCountsUnchanged=baseline==after)
            if not absent or baseline!=after: report['status']='held'
        except Exception as exc: report.update(status='held',verificationErrorType=type(exc).__name__)
        if report['grantAttempted'] and not report['rolesRemoved']: report['status']='held'
        report['sourceHashes']={name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
            for name in ('hosted_auxiliary_trial.py','db_auxiliary.py','auxiliary_permissions.py','runtime_permissions.py')}
        # Only hashes and object counts from catalog snapshots are retained.
        for key in ('baselineSnapshot','postTrialSnapshot'):
            if report.get(key):
                report[key]['catalogSha256']=candidate.digest(report[key].pop('catalog'))
        with output.open('x',encoding='utf-8') as handle: handle.write(json.dumps(report,indent=2,sort_keys=True)+'\n')
        journal=output.with_suffix('.progress.json')
        try:
            journal.write_text(json.dumps({'status':'completed','resultStatus':report['status'],
                'resultFile':output.name,'roles':roles,'secretValuesIncluded':False},indent=2)+'\n',encoding='utf-8')
        except OSError: pass
    print(json.dumps({'report':str(output),'status':report['status'],'stage':report['stage'],
      'rolesRemoved':report['rolesRemoved'],'independentRoleAbsenceVerified':report.get('independentRoleAbsenceVerified'),
      'catalogAclPoliciesLedgerAndCountsUnchanged':report.get('catalogAclPoliciesLedgerAndCountsUnchanged'),
      'errorType':report.get('errorType'),'cleanupErrorType':report.get('cleanupErrorType')}),flush=True)
    return 0 if report['status']=='passed_hosted_two_pool_trial' else 2

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--expected-project',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): raise SystemExit('Evidence path already exists')
    try: raise SystemExit(asyncio.run(run(args.config,args.expected_project,args.output)))
    except Exception as exc:
        safe={'status':'held','errorType':type(exc).__name__,'secretValuesIncluded':False}
        if not args.output.exists(): args.output.write_text(json.dumps(safe,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(safe)); raise SystemExit(2)
