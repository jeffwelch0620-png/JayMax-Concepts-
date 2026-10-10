"""Rotate exact retained build LOGINs with private staging and owner-assisted recovery.

No application cutover, SQL migrations, business writes or external integrations.
Every mutation is preceded by safe evidence; failures restore the prior credentials.
"""
import argparse,asyncio,hashlib,json,os,re,secrets,traceback
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlparse,urlunparse,quote,unquote
from unittest.mock import patch
import asyncpg
from dotenv import dotenv_values
import db_pg,db_auxiliary,auxiliary_permissions,runtime_permissions as candidate
import hosted_build_workflows as workflows
import hosted_install_preservation as preservation
import provision_build_connections as provision
from hosted_auxiliary_trial import quoted,snapshot

KEYS={'inventory':'DATABASE_URL','accounts':'AUXILIARY_DATABASE_URL'}

def inputs(owner,overlay,receipt,workflow,project):
    target=provision.hosted_test_trial.designated_target(owner,project)
    if target['connectionMode']!='session_pooler':raise ValueError('Recorded session pooler required')
    if receipt.get('status')!='passed_retained_build_connections' or receipt.get('projectRef')!=project:
        raise ValueError('Verified retained provisioning receipt required')
    if workflow.get('status')!='passed_retained_login_enabled_workflows' or workflow.get('projectRef')!=project:
        raise ValueError('Passing retained workflow receipt required')
    roles=receipt['roles']
    if set(roles)!=set(KEYS) or len(set(roles.values()))!=2:raise ValueError('Two distinct recorded roles required')
    for kind,key in KEYS.items():
        if not re.fullmatch('jaymax_build_'+kind+'_[a-f0-9]{12}',roles[kind]):raise ValueError('Generated role identity required')
        uri=urlparse(overlay.get(key,''))
        if not db_auxiliary.same_target(owner['DATABASE_URL'],overlay.get(key,'')) or unquote(uri.username or '').rsplit('.',1)[0]!=roles[kind]:
            raise ValueError('Recorded role or endpoint mismatch')
        if not uri.password or len(unquote(uri.password))<40:raise ValueError('Strong existing private credential required')
    if overlay.get('USE_PG')!='true' or any(overlay.get(f+'_ENABLED')!='false' for f in candidate.readiness.FEATURES):
        raise ValueError('Staged disk flags must remain held')
    return roles

def replacement_overlay(original,passwords):
    result=dict(original)
    for kind,key in KEYS.items():
        uri=urlparse(original[key]);result[key]=urlunparse(uri._replace(netloc=uri.username+':'+quote(passwords[kind],safe='')+'@'+uri.hostname+':'+str(uri.port)))
    return result

def write_private(path,config):
    value=''.join(key+'="'+config[key]+'"\n' for key in KEYS.values())+'USE_PG=true\n'
    value+=''.join(f+'_ENABLED=false\n' for f in candidate.readiness.FEATURES)
    with path.open('x',encoding='utf-8') as handle:handle.write(value);handle.flush();os.fsync(handle.fileno())

async def role_attributes(conn,roles):
    records=await conn.fetch("SELECT oid,rolname,rolcanlogin,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication,rolinherit,rolconnlimit,rolvaliduntil::text AS valid_until FROM pg_roles WHERE rolname=ANY($1::text[]) ORDER BY rolname",list(roles.values()))
    if len(records)!=2:raise ValueError('Recorded roles absent')
    for row in records:
        if not row['rolcanlogin'] or any(row[k] for k in ('rolsuper','rolbypassrls','rolcreatedb','rolcreaterole','rolreplication','rolinherit')) or row['rolconnlimit']!=6 or row['valid_until']!='infinity':
            raise ValueError('Retained role attributes held')
    return [dict(r) for r in records]

async def connect(url,role):
    conn=await asyncpg.connect(url,ssl='require',timeout=20,command_timeout=30,statement_cache_size=0)
    try:
        await db_pg._init_connection(conn)
        await conn.execute('SET default_transaction_read_only=on')
        identity=dict(await conn.fetchrow('SELECT session_user AS login,current_user AS current'))
        if identity!={'login':role,'current':role}:raise ValueError('Actual LOGIN identity held')
        return conn
    except BaseException:await conn.close();raise

async def refreshed_connection(url,role,attempts=3):
    # The hosted shared pooler documents transient credential-cache lag. Trigger
    # refresh with replacement credentials, bounded retries, and no owner fallback.
    for attempt in range(attempts):
        try:return await connect(url,role)
        except asyncpg.InvalidPasswordError:
            if attempt==attempts-1:raise
            await asyncio.sleep(15)

async def denied(url,role):
    try:conn=await connect(url,role)
    except (asyncpg.InvalidPasswordError,asyncpg.InvalidAuthorizationSpecificationError) as exc:return type(exc).__name__
    else:await conn.close();raise AssertionError('Replaced or disabled credential accepted by fresh client')

async def disabled_denial(url,role):
    try:return {'denialType':await denied(url,role),'transientInternalErrorRetried':False}
    except asyncpg.InternalServerError:
        # An internal pooler failure never counts as authentication denial. Allow
        # one bounded propagation retry; only a subsequent 28P01/28000 qualifies.
        await asyncio.sleep(15)
        return {'denialType':await denied(url,role),'transientInternalErrorRetried':True}

async def run(owner_path,overlay_path,receipt_path,workflow_path,project,directory,output):
    owner_config=dotenv_values(owner_path);old=dotenv_values(overlay_path)
    receipt=json.loads(receipt_path.read_bytes());workflow=json.loads(workflow_path.read_bytes())
    roles=inputs(owner_config,old,receipt,workflow,project)
    if output.exists():raise ValueError('Existing evidence is never overwritten')
    private=provision.private_directory(directory)
    passwords={kind:secrets.token_urlsafe(48) for kind in KEYS};new=replacement_overlay(old,passwords)
    report={'format':'jaymax-retained-login-rotation-v1','status':'held','projectRef':project,'roles':roles,
      'previousPrivateConfigPath':str(overlay_path),'replacementPrivateConfigPath':str(private),
      'activeApplicationCutover':False,'applicationConfigurationChanged':False,'businessRowsWritten':False,
      'databaseObjectPermissionsChanged':False,'externalServicesCalled':False,'operationalReleaseApproved':False,'secretValuesIncluded':False}
    owner=None;clients={};pools=[];mutation_attempted=False;passed=False
    def emit(stage,**values):
        report.update(stage=stage,capturedAt=datetime.now(timezone.utc).isoformat(),**values)
        workflows.save_evidence(output,report);print(json.dumps({'stage':stage,'status':report['status']}),flush=True)
    async def owner_connect():return await asyncpg.connect(owner_config['DATABASE_URL'],ssl='require',timeout=20,command_timeout=30,statement_cache_size=0)
    async def set_passwords(config):
        async with owner.transaction():
            await owner.execute("SET LOCAL statement_timeout='20s'; SET LOCAL lock_timeout='5s'")
            for kind,role in roles.items():
                password=unquote(urlparse(config[KEYS[kind]]).password)
                # Credential characters are generated/reviewed, never arbitrary SQL literals.
                if not re.fullmatch(r'[A-Za-z0-9_-]{40,}',password):raise ValueError('Credential literal held')
                await owner.execute('ALTER ROLE '+quoted(role)+" LOGIN PASSWORD '"+password+"' VALID UNTIL 'infinity'")
    try:
        emit('preflight');owner=await owner_connect()
        before_roles=await role_attributes(owner,roles);before=await snapshot(owner)
        columns=await preservation.original_columns(owner);rows=await preservation.fingerprints(owner,columns)
        facts=await workflows.global_track1(owner);ledger=await preservation.ledger_fingerprints(owner)
        report.update(baselineRoleAttributes=before_roles,baselineSnapshot={k:v for k,v in before.items() if k!='catalog'},baselineCatalogSha256=candidate.digest(before['catalog']),baselineOriginalRows=rows,baselineTrack1=facts,baselineLedger=ledger)
        for kind,key in KEYS.items():clients[kind]=await connect(old[key],roles[kind])
        emit('prior_credentials_authenticated')
        write_private(private,new);emit('replacement_credentials_staged',privateAclVerified=True)
        mutation_attempted=True;emit('password_rotation_attempt')
        await set_passwords(new);emit('password_rotation_committed')
        for kind,conn in clients.items():
            if await conn.fetchval('SELECT 1')!=1:raise AssertionError('Existing session continuity held')
        emit('already_open_sessions_remain_authorized',existingSessionsNotRevokedByPasswordChange=True)
        for conn in clients.values():await conn.close()
        clients.clear()
        emit('replacement_authentication_refresh')
        for kind,key in KEYS.items():
            fresh=await refreshed_connection(new[key],roles[kind]);await fresh.close()
        emit('replacement_credentials_freshly_authenticated',replacementCredentialsAuthenticatedBeforeOldRejection=True)
        denial={kind:await denied(old[key],roles[kind]) for kind,key in KEYS.items()}
        emit('replaced_credentials_denied',replacedCredentialDenialTypes=denial)
        # Exercise both real pool constructors after fresh authentication.
        primary=await asyncpg.create_pool(new['DATABASE_URL'],ssl='require',min_size=1,max_size=2,timeout=20,command_timeout=30,statement_cache_size=0,init=db_pg._init_connection);pools.append(primary)
        secondary=await db_auxiliary._try_connect(new['AUXILIARY_DATABASE_URL'])
        if secondary is None:raise ValueError('Rotated auxiliary startup gate held')
        pools.append(secondary)
        for kind,pool in (('inventory',primary),('accounts',secondary)):
            async with pool.acquire() as conn:
                await conn.execute('SET default_transaction_read_only=on')
                if dict(await conn.fetchrow('SELECT session_user AS login,current_user AS current'))!={'login':roles[kind],'current':roles[kind]}:raise AssertionError('Rotated pool identity held')
        emit('replacement_pools_reconnected',replacementPoolsReconnected=True)
        for pool in reversed(pools):await pool.close()
        pools.clear()
        # Disable one exact LOGIN at a time, with no live test sessions or owner fallback.
        for kind,key in KEYS.items():
            emit('disable_'+kind+'_login')
            await owner.execute('ALTER ROLE '+quoted(roles[kind])+' NOLOGIN')
            try:
                # Allow one bounded cache propagation interval before verifying NOLOGIN.
                await asyncio.sleep(15)
                if await owner.fetchval('SELECT rolcanlogin FROM pg_roles WHERE rolname=$1',roles[kind]) is not False:raise AssertionError('Exact LOGIN disable not confirmed')
                denial_type=await disabled_denial(new[key],roles[kind])
                other='accounts' if kind=='inventory' else 'inventory'
                other_conn=await connect(new[KEYS[other]],roles[other]);await other_conn.close()
                report.setdefault('disabledLoginDenialTypes',{})[kind]=denial_type
                emit(kind+'_disabled_other_pool_available')
            finally:await owner.execute('ALTER ROLE '+quoted(roles[kind])+' LOGIN')
            recovered=await connect(new[key],roles[kind]);await recovered.close()
            emit(kind+'_owner_reenabled_and_reconnected')
        # Actual accessors hold an unavailable configured pool; never route to owner.
        from fastapi import HTTPException
        with patch.object(db_pg,'_pool',None),patch.object(db_auxiliary,'_pool',None),patch.object(db_auxiliary,'_configured',True):
            for accessor in (db_pg.pool,db_auxiliary.pool):
                try:accessor()
                except HTTPException as exc:
                    if exc.status_code!=503:raise
                else:raise AssertionError('Unavailable pool did not hold')
        emit('unavailable_pool_accessors_hold',unavailablePoolsReturn503WithoutFallback=True)
        for kind,key in KEYS.items():clients[kind]=await connect(new[key],roles[kind])
        main=await asyncio.wait_for(candidate.inspect(clients['inventory'],roles['inventory'],'hosted_build'),240)
        aux=await asyncio.wait_for(auxiliary_permissions.inspect(clients['accounts']),60)
        if main['status']!='passed_local_candidate' or aux['status']!='passed':raise ValueError('Post-recovery permission assessment held')
        emit('recovered_permission_profiles_passed',inventoryAssessment=main,auxiliaryAssessment=aux)
        for conn in clients.values():await conn.close()
        clients.clear()
        after=await snapshot(owner)
        preserved=after==before and await role_attributes(owner,roles)==before_roles and await preservation.fingerprints(owner,columns)==rows and await workflows.global_track1(owner)==facts and await preservation.ledger_fingerprints(owner)==ledger
        if not preserved:raise AssertionError('Independent post-rotation preservation held')
        report.update(status='passed_retained_login_rotation_recovery',allApplicationRowsUnchanged=True,allGlobalTrack1RowsUnchanged=True,allLedgerRowsUnchanged=True,catalogGrantsPoliciesAndRoleAttributesUnchanged=True,replacementPrivateConfigIsCurrent=True,previousCredentialsRejected=True,bothOwnerAssistedLoginRecoveryVerified=True)
        passed=True
    except Exception as exc:
        report.update(errorType=type(exc).__name__,errorFrames=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(exc.__traceback__)])
        if isinstance(exc,(ValueError,AssertionError)):report['safeReason']=str(exc)
    finally:
        for pool in pools:
            try:await asyncio.wait_for(pool.close(),20)
            except Exception:pool.terminate()
        for conn in clients.values():
            try:await conn.close()
            except Exception:conn.terminate()
        if mutation_attempted and not passed:
            try:
                if owner is None or owner.is_closed():owner=await owner_connect()
                # Restore only the two recorded strong old passwords and LOGIN ability.
                # Original private file stays intact, so recovery does not depend on a new file swap.
                await set_passwords(old)
                for kind,key in KEYS.items():
                    conn=await connect(old[key],roles[kind]);await conn.close()
                recovered_preserved=await snapshot(owner)==before and await role_attributes(owner,roles)==before_roles and await preservation.fingerprints(owner,columns)==rows and await workflows.global_track1(owner)==facts and await preservation.ledger_fingerprints(owner)==ledger
                if not recovered_preserved:raise AssertionError('Recovered baseline preservation held')
                report.update(priorCredentialsRestoredAndReconnected=True,recoveryBaselinePreserved=True,replacementPrivateConfigIsCurrent=False)
            except Exception as exc:report.update(priorCredentialsRestoredAndReconnected=False,recoveryErrorType=type(exc).__name__)
        if owner:
            try:await owner.close()
            except Exception:owner.terminate()
        report['sourceHashes']={n:hashlib.sha256((Path(__file__).parent/n).read_bytes()).hexdigest() for n in ('rotate_build_connections.py','db_pg.py','db_auxiliary.py','runtime_permissions.py','auxiliary_permissions.py')}
        emit('complete' if passed else 'held_review_recovery_receipt')
    return 0 if passed else 2

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('owner-config','overlay','provision-receipt','workflow-receipt','private-directory','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--expected-project',required=True);args=parser.parse_args()
    try:raise SystemExit(asyncio.run(run(args.owner_config,args.overlay,args.provision_receipt,args.workflow_receipt,args.expected_project,args.private_directory,args.output)))
    except Exception as exc:print(json.dumps({'status':'held_before_or_after_journal','errorType':type(exc).__name__}));raise SystemExit(2)
