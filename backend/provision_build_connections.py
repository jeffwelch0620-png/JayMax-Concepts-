"""Stage retained build LOGINs and a private local connection file; no app cutover.

The designated owner target must have native features held. Credentials are
written exclusively inside a verified Windows-private directory before grants.
No business rows, migrations, active .env files or integration services change.
"""
import argparse
import asyncio
from contextlib import AsyncExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
from urllib.parse import quote, urlparse, urlunparse
import asyncpg
import auxiliary_permissions as auxiliary
import db_auxiliary
import db_pg
import hosted_test_trial
import runtime_permissions as candidate
from hosted_auxiliary_trial import quoted, snapshot
from dotenv import dotenv_values

def plan(config, project):
    target=hosted_test_trial.designated_target(config,project)
    if target['connectionMode']!='session_pooler': raise ValueError('Session pooler required')
    manifest=candidate.manifest(); expected=candidate.contract(manifest,'hosted_build')
    matrix=candidate.table_privileges(manifest)
    functions=[s for s,v in expected['functions'].items() if v['name'].split('.')[0] in candidate.readiness.PRIVATE
               and not v['trigger'] and not v['securityDefiner']]
    policies=[('inventory',table,verb,'runtime_candidate_'+verb.lower()) for table,verbs in candidate.PUBLIC.items() for verb in verbs]
    policies += [('accounts',table,verb,'auxiliary_candidate_'+verb.lower()) for table in auxiliary.TABLES for verb in auxiliary.VERBS]
    return target,expected,matrix,functions,policies

def private_directory(directory):
    root=Path(os.environ['LOCALAPPDATA'])/'JayMaxBuild'/'credentials'
    directory=Path(directory)
    if not directory.is_absolute() or not directory.is_dir() or directory.is_symlink() or directory.is_junction():
        raise ValueError('Existing private directory required')
    if not directory.resolve().is_relative_to(root.resolve()) or directory.resolve()==root.resolve():
        raise ValueError('Private target must be a child of the local credential directory')
    if os.name!='nt': raise ValueError('This credential writer requires the Windows ACL check')
    shell=shutil.which('pwsh')
    if not shell: raise ValueError('PowerShell 7 required for the verified ACL check')
    script='''$ErrorActionPreference='Stop'; $acl=Get-Acl -LiteralPath $env:JAYMAX_PRIVATE_DIR -ErrorAction Stop;
      $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;
      $allowed=@($sid,'S-1-5-18') | Sort-Object -Unique;
      $actual=@($acl.Access | ForEach-Object {$_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value} | Sort-Object -Unique);
      $safe=$acl.AreAccessRulesProtected -and ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -eq $sid) -and (($actual -join ',') -eq ($allowed -join ',')) -and
        -not @($acl.Access | Where-Object {$_.AccessControlType -ne 'Allow'}).Count;
      if (-not $safe) {exit 2}; Write-Output 'verified' '''
    checked=subprocess.run([shell,'-NoProfile','-NonInteractive','-Command',script],
      env={**os.environ,'JAYMAX_PRIVATE_DIR':str(directory)},capture_output=True,timeout=20)
    if checked.returncode!=0 or checked.stdout.strip()!=b'verified': raise ValueError('Private directory ACL held')
    target=directory/'runtime-connections.env'
    if target.exists(): raise ValueError('Existing credential files are never overwritten')
    return target

async def access_without_roles(conn, role_oids=()):
    """Compare pre-existing application object ACLs/policies, excluding new grantees."""
    rows=await conn.fetch('''
      SELECT 'schema' AS kind,nspname AS name,a.grantor,a.grantee,a.privilege_type,a.is_grantable
      FROM pg_namespace CROSS JOIN LATERAL aclexplode(coalesce(nspacl,acldefault('n',nspowner))) a
      WHERE nspname=ANY($1::text[]) AND NOT a.grantee=ANY($2::oid[])
      UNION ALL SELECT 'relation',n.nspname||'.'||c.relname,a.grantor,a.grantee,a.privilege_type,a.is_grantable
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault(CASE WHEN c.relkind='S' THEN 's'::"char" ELSE 'r'::"char" END,c.relowner))) a
      WHERE n.nspname=ANY($1::text[]) AND c.relkind IN ('r','p','v','m','f','S') AND NOT a.grantee=ANY($2::oid[])
      UNION ALL SELECT 'function',n.nspname||'.'||p.oid::text,a.grantor,a.grantee,a.privilege_type,a.is_grantable
      FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
      CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
      WHERE n.nspname=ANY($1::text[]) AND NOT a.grantee=ANY($2::oid[])''', ['public',*auxiliary.PRIVATE],list(role_oids))
    policies=await conn.fetch('''SELECT n.nspname,c.relname,p.polname,p.polcmd::text,p.polpermissive,p.polroles,
      pg_get_expr(p.polqual,p.polrelid) AS using,pg_get_expr(p.polwithcheck,p.polrelid) AS check
      FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname=ANY($1::text[]) AND NOT p.polroles && $2::oid[] ORDER BY 1,2,3''',['public',*auxiliary.PRIVATE],list(role_oids))
    return {'aclSha256':candidate.digest(sorted([dict(r) for r in rows],key=lambda r:json.dumps(r,sort_keys=True))),
            'policySha256':candidate.digest([dict(r) for r in policies])}

async def run(owner_config, project, directory, output):
    config=dotenv_values(owner_config)
    target,expected,matrix,functions,policies=plan(config,project)
    private=private_directory(directory)
    roles={kind:'jaymax_build_'+kind+'_'+secrets.token_hex(6) for kind in ('inventory','accounts')}
    passwords={kind:secrets.token_urlsafe(48) for kind in roles}
    uri=urlparse(config['DATABASE_URL'])
    urls={kind:urlunparse(uri._replace(netloc=quote(role+'.'+project,safe='')+':'+quote(passwords[kind],safe='')+
      '@'+uri.hostname+':'+str(uri.port))) for kind,role in roles.items()}
    if not db_auxiliary.same_target(urls['inventory'],urls['accounts']): raise ValueError('Connection target held')
    report={'format':'jaymax-retained-build-connections-v1','status':'held','projectRef':project,'roles':roles,
      'privateConfigPath':str(private),'privateAclVerified':True,'applicationConfigurationChanged':False,
      'businessRowsWritten':False,'externalServicesCalled':False,'operationalReleaseApproved':False,
      'secretValuesIncluded':False,'credentialsWritten':False,'grantAttempted':False,'rolesRetained':False}
    owner=None; pools=[]; baseline=None
    def progress(stage):
        report['stage']=stage
        safe={k:v for k,v in report.items() if k not in ('inventoryAssessment','auxiliaryAssessment')}
        safe['capturedAt']=datetime.now(timezone.utc).isoformat()
        journal=output.with_suffix('.progress.json'); temporary=journal.with_suffix('.tmp')
        try:
            temporary.write_text(json.dumps(safe,indent=2)+'\n',encoding='utf-8'); temporary.replace(journal)
        except OSError:
            if not report['grantAttempted']: raise
        print(json.dumps({'stage':stage}),flush=True)
    async def connect_owner():
        return await asyncpg.connect(config['DATABASE_URL'],ssl='require',timeout=20,command_timeout=25,statement_cache_size=0)
    try:
        progress('preflight'); owner=await connect_owner()
        baseline=await snapshot(owner)
        if baseline['catalog']!={g:expected[g] for g in ('functions','relations')}: raise ValueError('Hosted contract held')
        existing_access=await access_without_roles(owner)
        if await owner.fetchval('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=ANY($1::text[]))',list(roles.values())):
            raise ValueError('Role collision')
        if await owner.fetchval("SELECT EXISTS(SELECT 1 FROM pg_policy WHERE polname LIKE 'runtime_candidate_%' OR polname LIKE 'auxiliary_candidate_%')"):
            raise ValueError('Policy collision; review existing provisioned access')
        report['baseline']={k:v for k,v in baseline.items() if k!='catalog'}
        report['baseline']['catalogSha256']=candidate.digest(baseline['catalog'])
        report['existingAccessBaseline']=existing_access
        # Durable secrets precede any committed role change, exclusively under the verified ACL.
        text='DATABASE_URL="'+urls['inventory']+'"\nAUXILIARY_DATABASE_URL="'+urls['accounts']+'"\nUSE_PG=true\n'
        text+=''.join(name+'_ENABLED=false\n' for name in candidate.readiness.FEATURES)
        with private.open('x',encoding='utf-8') as handle:
            handle.write(text); handle.flush(); os.fsync(handle.fileno())
        report['credentialsWritten']=True; progress('private_credentials_staged')
        report['grantAttempted']=True; progress('provision_retained_roles')
        async with owner.transaction():
            await owner.execute("SET LOCAL statement_timeout='20s'; SET LOCAL lock_timeout='5s'")
            for kind,role in roles.items():
                await owner.execute('CREATE ROLE '+quoted(role)+' NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT CONNECTION LIMIT 6')
                await owner.execute('GRANT USAGE ON SCHEMA public TO '+quoted(role))
            for schema in candidate.readiness.PRIVATE:
                await owner.execute('GRANT USAGE ON SCHEMA '+quoted(schema)+' TO '+quoted(roles['inventory']))
            for name,verbs in matrix.items():
                await owner.execute('GRANT '+','.join(verbs)+' ON '+'.'.join(map(quoted,name.split('.')))+' TO '+quoted(roles['inventory']))
            for signature in functions:await owner.execute('GRANT EXECUTE ON FUNCTION '+signature+' TO '+quoted(roles['inventory']))
            for table in auxiliary.TABLES:
                await owner.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON public.'+quoted(table)+' TO '+quoted(roles['accounts']))
            for kind,table,verb,name in policies:
                clauses='WITH CHECK (true)' if verb=='INSERT' else 'USING (true) WITH CHECK (true)' if verb=='UPDATE' else 'USING (true)'
                await owner.execute('CREATE POLICY '+quoted(name)+' ON public.'+quoted(table)+' FOR '+verb+' TO '+quoted(roles[kind])+' '+clauses)
            for kind,role in roles.items():
                await owner.execute('ALTER ROLE '+quoted(role)+" LOGIN PASSWORD '"+passwords[kind]+"' VALID UNTIL 'infinity'")
        report['rolesRetained']=True; progress('retained_roles_committed')
        await owner.close(); owner=None
        primary=await asyncpg.create_pool(urls['inventory'],ssl='require',min_size=1,max_size=5,statement_cache_size=0,
          init=db_pg._init_connection,timeout=20,command_timeout=25); pools.append(primary)
        secondary=await asyncio.wait_for(db_auxiliary._try_connect(urls['accounts']),90)
        if secondary is None: raise ValueError('Auxiliary connection held')
        pools.append(secondary); progress('actual_login_assessments')
        async with AsyncExitStack() as stack:
            clients={kind:[await stack.enter_async_context(pool.acquire()) for _ in range(number)]
                for kind,pool,number in (('inventory',primary,5),('accounts',secondary,3))}
            identities=[]
            for kind,connections in clients.items():
                for conn in connections:
                    # Permanent roles support later writes; this verification session stays read-only.
                    await conn.execute('SET default_transaction_read_only=on')
                    who=dict(await conn.fetchrow("SELECT current_user AS current_role,session_user AS login_role,current_setting('transaction_read_only') AS read_only"))
                    if who!=dict(current_role=roles[kind],login_role=roles[kind],read_only='on'): raise ValueError('LOGIN identity held')
                    if await conn.fetchval("SELECT '{\"kind\":\"invented\"}'::jsonb")!={'kind':'invented'}: raise ValueError('JSON codec held')
                    identities.append({'connectionKind':kind,**who,'jsonCodecVerified':True})
            main=await asyncio.wait_for(candidate.inspect(clients['inventory'][0],roles['inventory'],'hosted_build'),240)
            aux=await asyncio.wait_for(auxiliary.inspect(clients['accounts'][0]),60)
            report['inventoryAssessment']=main; report['auxiliaryAssessment']=aux
            if main['status']!='passed_local_candidate' or aux['status']!='passed': raise ValueError('Permission assessment held')
            for kind,sql in (('inventory','SELECT count(*) FROM public.app_users'),('accounts','SELECT count(*) FROM purchasing.posting_batches'),('accounts','SELECT count(*) FROM public.staff_pins')):
                try:
                    async with clients[kind][0].transaction(readonly=True): await clients[kind][0].fetchval(sql)
                except asyncpg.InsufficientPrivilegeError: pass
                else: raise ValueError('Cross-boundary access held')
            report['authenticatedClients']=identities; report['crossBoundaryReadsDenied']=True
        for pool in reversed(pools):await asyncio.wait_for(pool.close(),30)
        pools.clear(); progress('independent_post_provision_verification')
        owner=await connect_owner(); after=await snapshot(owner)
        role_oids=[r['oid'] for r in await owner.fetch('SELECT oid FROM pg_roles WHERE rolname=ANY($1::text[])',list(roles.values()))]
        existing_after=await access_without_roles(owner,role_oids)
        report['existingAccessAfter']=existing_after
        report['postProvision']={k:v for k,v in after.items() if k!='catalog'}
        report['postProvision']['catalogSha256']=candidate.digest(after['catalog'])
        unchanged=after['catalog']==baseline['catalog'] and after['ledgerSha256']==baseline['ledgerSha256'] and after['observedRowCounts']==baseline['observedRowCounts']
        if len(role_oids)!=2 or not unchanged or existing_after!=existing_access: raise ValueError('Post-provision preservation held')
        report.update(status='passed_retained_build_connections',preExistingPermissionsUnchanged=True,catalogLedgerAndCountsUnchanged=True,
          sourceContractSha256=candidate.digest(expected),activeApplicationCutover=False)
    except Exception as exc:
        report.update(status='held',errorType=type(exc).__name__)
        if report['grantAttempted']:
            try:
                if owner is None or owner.is_closed(): owner=await connect_owner()
                present=[r['rolname'] for r in await owner.fetch('SELECT rolname FROM pg_roles WHERE rolname=ANY($1::text[])',list(roles.values()))]
                for role in present:await owner.execute('ALTER ROLE '+quoted(role)+' NOLOGIN')
                report.update(rolesRetained=bool(present),retainedLoginsDisabled=True)
            except Exception as cleanup:
                report.update(retainedLoginsDisabled=False,containmentErrorType=type(cleanup).__name__)
    finally:
        progress('close_verification_sessions')
        for pool in reversed(pools):
            try:await asyncio.wait_for(pool.close(),30)
            except Exception:pool.terminate()
        if owner:
            try:await owner.close()
            except Exception:owner.terminate()
        report['sourceHashes']={name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in
          ('provision_build_connections.py','runtime_permissions.py','auxiliary_permissions.py','db_auxiliary.py','hosted_auxiliary_trial.py')}
        report['capturedAt']=datetime.now(timezone.utc).isoformat()
        with output.open('x',encoding='utf-8') as handle:handle.write(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'report':str(output),'status':report['status'],'rolesRetained':report['rolesRetained'],
      'privateConfigPath':str(private),'errorType':report.get('errorType'),'activeApplicationCutover':False}),flush=True)
    return 0 if report['status']=='passed_retained_build_connections' else 2

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner-config',type=Path,required=True);parser.add_argument('--expected-project',required=True)
    parser.add_argument('--private-directory',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise SystemExit('Existing evidence is never overwritten')
    try:raise SystemExit(asyncio.run(run(args.owner_config,args.expected_project,args.private_directory,args.output)))
    except Exception as exc:
        safe={'status':'held','errorType':type(exc).__name__,'secretValuesIncluded':False}
        if not args.output.exists():args.output.write_text(json.dumps(safe,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(safe));raise SystemExit(2)
