"""Enabled API workflows with retained build LOGINs and labelled invented data.

No active configuration, permissions, real invoices or integrations change.
Prep audit fixtures are retained; the exact test account is removed and forecast
writes use an outer rollback transaction. A held run must be reconciled, not rerun.
"""
import argparse
import asyncio
from contextlib import ExitStack, asynccontextmanager
from datetime import date,datetime,timedelta,timezone
import hashlib,json,os,re,secrets,time,traceback
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote,urlparse
from uuid import uuid4
import asyncpg,httpx
import auxiliary_permissions,db_auxiliary,db_pg
import hosted_install_preservation as preservation
import hosted_staff_production as production
import hosted_test_trial,runtime_permissions as candidate
from dotenv import dotenv_values

TRACK1=('actual_inventory.scopes','actual_inventory.scope_items','actual_inventory.count_snapshots',
 'actual_inventory.count_lines','actual_inventory.period_closures','actual_inventory.reopen_events',
 'actual_inventory.scope_bridges','purchasing.actual_purchase_facts')

def target_inputs(owner,overlay,provision,prior,project):
    hosted_test_trial.designated_target(owner,project)
    if provision.get('status')!='passed_retained_build_connections' or provision.get('projectRef')!=project:
        raise ValueError('Verified retained connection receipt required')
    if not db_auxiliary.same_target(owner.get('DATABASE_URL',''),overlay.get('DATABASE_URL','')) or not db_auxiliary.same_target(
            overlay.get('DATABASE_URL',''),overlay.get('AUXILIARY_DATABASE_URL','')):
        raise ValueError('Connection target mismatch')
    for kind,key in (('inventory','DATABASE_URL'),('accounts','AUXILIARY_DATABASE_URL')):
        if unquote(urlparse(overlay[key]).username).rsplit('.',1)[0]!=provision['roles'][kind]:
            raise ValueError('Recorded role identity mismatch')
    if overlay.get('USE_PG')!='true' or any(overlay.get(f+'_ENABLED')!='false' for f in candidate.readiness.FEATURES):
        raise ValueError('Staged disk flags must remain held')
    store=prior.get('workflow',{}).get('temporaryStore','')
    if not re.fullmatch(r'hosted_trial_[a-f0-9]{32}',store) or prior['workflow'].get('status')!='passed':
        raise ValueError('Verified labelled synthetic location required')
    return store

async def global_track1(conn):
    async with conn.transaction(isolation='repeatable_read',readonly=True):
        await conn.execute("SET LOCAL TIME ZONE 'UTC'")
        return {table:dict(await conn.fetchrow("SELECT count(*) AS rows,encode(sha256(convert_to(coalesce(string_agg(h,'' ORDER BY h),''),'UTF8')),'hex') AS sha256 FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS h FROM "+table+" t) x")) for table in TRACK1}

async def projected_fingerprint(conn,schema,table,columns,where,args):
    quoted=preservation.quoted
    projection=','.join(quoted(c['name']) for c in columns)
    relation=quoted(schema)+'.'+quoted(table)
    return dict(await conn.fetchrow("SELECT count(*) AS rows,encode(sha256(convert_to(coalesce(string_agg(h,'' ORDER BY h),''),'UTF8')),'hex') AS sha256 FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS h FROM (SELECT "+projection+' FROM '+relation+' WHERE '+where+") t) x",*args))

async def state_baseline(conn,columns,store):
    if not re.fullmatch(r'hosted_trial_[a-f0-9]{32}',store):raise ValueError('Synthetic state identity required')
    fields=columns[('public','store_state')]
    async with conn.transaction(isolation='repeatable_read',readonly=True):
        await conn.execute("SET LOCAL TIME ZONE 'UTC'")
        return {'nonFixtureRows':await projected_fingerprint(conn,'public','store_state',fields,'store_id<>$1',[store]),
            'fixtureStableFields':await projected_fingerprint(conn,'public','store_state',[c for c in fields if c['name'] not in ('revision','updated_at')],'store_id=$1',[store]),
            'fixtureRevision':await conn.fetchval('SELECT revision FROM public.store_state WHERE store_id=$1',store)}

async def prep_append_ids(conn,store,result):
    from uuid import UUID
    if not re.fullmatch(r'hosted_trial_[a-f0-9]{32}',store) or result.get('store')!=store or result.get('status')!='passed':
        raise ValueError('Verified synthetic production result required')
    task=await conn.fetchrow('SELECT * FROM prep_inventory.day_tasks WHERE id=$1 AND store_id=$2',UUID(result['taskId']),store)
    if task is None:raise ValueError('Exact synthetic task absent')
    version=await conn.fetchrow('SELECT list_id FROM prep_inventory.day_list_versions WHERE id=$1 AND store_id=$2',task['version_id'],store)
    root=UUID(result['rootId']);batch=UUID(result['batchId']);list_id=version['list_id']
    rows={
     'batch_events':await conn.fetch('SELECT id FROM prep_inventory.batch_events WHERE id=$1 AND store_id=$2',batch,store),
     'batch_movements':await conn.fetch('SELECT id FROM prep_inventory.batch_movements WHERE event_id=$1 AND store_id=$2',batch,store),
     'day_lists':await conn.fetch('SELECT id FROM prep_inventory.day_lists WHERE id=$1 AND store_id=$2 AND prep_date=$3',list_id,store,date.fromisoformat(result['day'])),
     'day_list_versions':await conn.fetch('SELECT id FROM prep_inventory.day_list_versions WHERE list_id=$1 AND store_id=$2',list_id,store),
     'day_tasks':await conn.fetch('SELECT id FROM prep_inventory.day_tasks WHERE version_id=$1 AND store_id=$2',task['version_id'],store),
     'execution_events':await conn.fetch('SELECT id FROM prep_inventory.execution_events WHERE list_id=$1 AND store_id=$2',list_id,store),
     'planning_versions':await conn.fetch('SELECT id FROM prep_inventory.planning_versions WHERE id=$1 AND store_id=$2',task['planning_version_id'],store),
     'staff_production_submissions':await conn.fetch('SELECT id FROM prep_inventory.staff_production_submissions WHERE root_id=$1 AND task_id=$2 AND store_id=$3',root,task['id'],store),
     'staff_production_decisions':await conn.fetch('SELECT id FROM prep_inventory.staff_production_decisions WHERE batch_event_id=$1 AND store_id=$2',batch,store),
     'task_assignments':await conn.fetch('SELECT id FROM prep_inventory.task_assignments WHERE id=$1 AND task_id=$2 AND store_id=$3',UUID(result['assignmentId']),task['id'],store)}
    expected={'batch_events':1,'batch_movements':2,'day_lists':1,'day_list_versions':1,'day_tasks':1,'execution_events':3,'planning_versions':1,'staff_production_submissions':2,'staff_production_decisions':1,'task_assignments':1}
    if {k:len(v) for k,v in rows.items()}!=expected:raise ValueError('Synthetic append graph cardinality held')
    return {k:[r['id'] for r in v] for k,v in rows.items()}

async def preserved_rows_after_prep(conn,columns,store,wrapper_actors,result):
    excluded={('public','activity_log'):('user_id',wrapper_actors+result['activityActorIds']),('public','staff_members'):('id',result['staffMemberIds'])}
    after=await preservation.fingerprints(conn,columns,exclude_synthetic=excluded)
    async with conn.transaction(isolation='repeatable_read',readonly=True):
        await conn.execute("SET LOCAL TIME ZONE 'UTC'")
        ids=await prep_append_ids(conn,store,result)
        for table,identities in ids.items():
            after['prep_inventory.'+table]=await projected_fingerprint(conn,'prep_inventory',table,columns[('prep_inventory',table)],'NOT(id=ANY($1::uuid[]))',[identities])
    return after,{table:[str(v) for v in values] for table,values in ids.items()}

def verify_forecast_response(saved):
    projection=saved.get('projection') or {}
    if (projection.get('amount')!='1234.56' or saved.get('accounting') is not False
            or projection.get('accounting') is not False
            or projection.get('basis')!='manual_sales_forecast'):
        raise AssertionError('Forecast precision/basis changed')

class BorrowedPool:
    """One authenticated connection, solely for a rollback-only forecast check."""
    def __init__(self,conn):self.conn=conn
    async def execute(self,*args):return await self.conn.execute(*args)
    @asynccontextmanager
    async def acquire(self):yield self.conn

def save_evidence(path,value):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    # Antivirus/readers can hold a Windows file briefly. Never continue a mutation
    # if the safe journal cannot be replaced after this bounded retry.
    for attempt in range(10):
        try:temporary.replace(path);return
        except PermissionError:
            if attempt==9:raise
            time.sleep(.1)

async def run(owner_file,overlay_file,provision_file,prior_file,project,output):
    owner_config=dotenv_values(owner_file);overlay=dotenv_values(overlay_file)
    provision=json.loads(provision_file.read_bytes());prior=json.loads(prior_file.read_bytes())
    store=target_inputs(owner_config,overlay,provision,prior,project)
    if output.exists():raise ValueError('Existing evidence is never overwritten')
    roles=provision['roles'];report={'format':'jaymax-retained-login-enabled-workflows-v1','status':'held','stage':'preflight',
      'projectRef':project,'syntheticStore':store,'activeConfigurationChanged':False,'databasePermissionsChanged':False,
      'realVendorFilesImported':False,'externalServicesCalled':False,'operationalReleaseApproved':False,'secretValuesIncluded':False}
    owner=None;primary=None;secondary=None;account_id=None;account_cleanup_authorized=False
    account_email='build-workflow-'+uuid4().hex+'@example.invalid'
    def emit(value):
        report.update(value);report['capturedAt']=datetime.now(timezone.utc).isoformat()
        save_evidence(output,report)
        print(json.dumps({'stage':report['stage'],'status':report['status']}),flush=True)
    async def owner_connect():
        return await asyncpg.connect(owner_config['DATABASE_URL'],ssl='require',timeout=20,command_timeout=30,statement_cache_size=0)
    async def identity(conn):
        who=await conn.fetchrow('SELECT session_user AS login,current_user AS current')
        if dict(who)!={'login':roles['inventory'],'current':roles['inventory']}:raise ValueError('Inventory LOGIN held')
    settings={'USE_PG':'true','AUTH_REQUIRED':'true','AUTH_SECRET':secrets.token_hex(32),
              **{name+'_ENABLED':'true' for name in candidate.readiness.FEATURES}}
    try:
        emit({'stage':'preflight'})
        owner=await owner_connect()
        if await owner.fetchval('SELECT name FROM public.stores WHERE id=$1',store)!='Synthetic hosted committed test':raise ValueError('Fixture label mismatch')
        columns=await preservation.original_columns(owner)
        before=await preservation.fingerprints(owner,columns)
        facts=await global_track1(owner);ledger=await preservation.ledger_fingerprints(owner)
        state_before=await state_baseline(owner,columns,store)
        params={}
        for key,day in (('opening','2026-10-01'),('closing','2026-10-08')):
            ids=await owner.fetch('SELECT id FROM actual_inventory.count_snapshots WHERE store_id=$1 AND boundary_date=$2',store,date.fromisoformat(day))
            if len(ids)!=1:raise ValueError('Synthetic physical boundaries ambiguous')
            params[key]=str(ids[0]['id'])
        emit({'stage':'baseline_saved','baselineTrack1':facts,'baselineLedger':ledger,
              'baselineOriginalColumns':[{'schema':s,'table':t,'columns':v} for (s,t),v in columns.items()],
              'baselineOriginalRows':before,'baselineState':state_before,'actualReportParams':params})
        await owner.close();owner=None
        primary=await asyncpg.create_pool(overlay['DATABASE_URL'],ssl='require',min_size=1,max_size=3,timeout=20,
          command_timeout=30,statement_cache_size=0,init=db_pg._init_connection,setup=identity)
        secondary=await asyncio.wait_for(db_auxiliary._try_connect(overlay['AUXILIARY_DATABASE_URL']),90)
        if secondary is None:raise ValueError('Auxiliary pool held')
        if await secondary.fetchval('SELECT EXISTS(SELECT 1 FROM public.app_users WHERE email=$1)',account_email):raise ValueError('Test account identity collision')
        account_cleanup_authorized=True
        async with primary.acquire() as conn:
            assessed=await asyncio.wait_for(candidate.inspect(conn,roles['inventory'],'hosted_build'),240)
            if assessed['status']!='passed_local_candidate':raise ValueError('Inventory permissions held')
        emit({'stage':'retained_login_permissions_verified','inventoryAssessment':assessed})
        with patch.dict(os.environ,settings),ExitStack() as patches:
            import server
            for name,value in (('USE_PG',True),('AUTH_SECRET',settings['AUTH_SECRET']),('AUTH_REQUIRED',True),('PUSH_ENABLED',False),
                               ('PG_STORE_IDS',server.PG_STORE_IDS|{store}),('RIDS',server.RIDS|{store})):
                patches.enter_context(patch.object(server,name,value))
            patches.enter_context(patch.dict(server.PG_STORE_TO_RESTAURANT,{store:store}))
            patches.enter_context(patch.dict(server.RESTAURANT_TO_PG_STORE,{store:store}))
            patches.enter_context(patch.object(db_pg,'_pool',primary));patches.enter_context(patch.object(db_auxiliary,'_pool',secondary))
            patches.enter_context(patch.object(db_auxiliary,'_configured',True))
            actor='build-workflow-owner-'+uuid4().hex
            emit({'stage':'wrapper_actor_recorded','wrapperActivityActorIds':[actor]})
            token=server._token({'id':actor,'email':'build-owner@example.invalid','role':'owner','locations':[store]})
            headers={'Authorization':'Bearer '+token}
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://invented-build-workflows') as client:
                async def call(method,path,body=None,expected=200,extra=None,params=None):
                    response=await asyncio.wait_for(client.request(method,path,json=body,headers=headers|(extra or {}),params=params),90)
                    if response.status_code!=expected:raise AssertionError('Workflow API status '+str(response.status_code)+' expected '+str(expected)+' at '+path.replace(store,'[synthetic-store]'))
                    return response.json()
                report_path='/api/pg/actual-inventory/'+store+'/report'
                actual=await call('GET',report_path,params=params)
                password=secrets.token_urlsafe(24)
                # Persist exact cleanup identity before issuing the account command.
                emit({'stage':'test_account_create','testAccountEmail':account_email})
                created=await call('POST','/api/auth/users',{'email':account_email,'password':password,'role':'manager','locations':[store]})
                account_id=created['id'];emit({'stage':'test_account_created','testAccountId':account_id})
                login=await call('POST','/api/auth/login',{'email':account_email,'password':password})
                if not login.get('token'):raise AssertionError('Test account login did not return a token')
                await call('DELETE','/api/auth/users/'+account_id);account_id=None
                emit({'stage':'test_account_removed','accountCreateLoginDeleteVerified':True})
                # Forecast calls use real role permissions and nested API transactions;
                # the outer transaction deliberately rolls back every forecast write.
                async with primary.acquire() as conn:
                    day=await conn.fetchval('SELECT coalesce(max(date),$2::date)+1 FROM public.store_sales_projections WHERE store_id=$1',store,date(2026,10,9))
                    reviewed=await call('GET','/api/projections/'+store+'/review',params={'date':str(day)})
                    transaction=conn.transaction();await transaction.start()
                    try:
                        with patch.object(db_pg,'_pool',BorrowedPool(conn)):
                            saved=await call('PUT','/api/projections/'+store,{'date':str(day),'amount':'1234.56','note':'Invented forecast; rollback-only'},extra={'If-Match':reviewed['sourceVersion']})
                            verify_forecast_response(saved)
                            await call('PUT','/api/projections/'+store,{'date':str(day),'amount':'1200.00'},expected=409,extra={'If-Match':reviewed['sourceVersion']})
                    finally:await transaction.rollback()
                    if await conn.fetchval('SELECT count(*) FROM public.store_sales_projections WHERE store_id=$1 AND date=$2',store,day):raise AssertionError('Rollback forecast retained a row')
                emit({'stage':'forecast_precision_stale_save_and_rollback_verified','forecastNotAccountingVerified':True})
                if await call('GET',report_path,params=params)!=actual:raise AssertionError('Account/forecast activity changed actual report')
            emit({'stage':'staff_production_begin'})
            result=await asyncio.wait_for(production.run(overlay['DATABASE_URL'],store,params,ssl='require',emit=emit,pool_setup=identity),600)
            if not result.get('track1ReportAndAllFactsUnchanged'):raise AssertionError('Production Track 1 checks absent')
            report['staffWorkflow']=result
        emit({'stage':'independent_postflight'})
        owner=await owner_connect()
        after,append_ids=await preserved_rows_after_prep(owner,columns,store,report['wrapperActivityActorIds'],result)
        state_after=await state_baseline(owner,columns,store)
        state_preserved=all(state_after[k]==state_before[k] for k in ('nonFixtureRows','fixtureStableFields'))
        if not state_preserved or state_after['fixtureRevision']<=state_before['fixtureRevision']:raise AssertionError('Expected synthetic state revision/stable fields held')
        # Only this labelled fixture may advance revision/update time. Other state rows and
        # every stable fixture field are independently compared to captured baselines.
        after['public.store_state']=before['public.store_state']
        report.update(expectedPrepAppendIds=append_ids,nonFixtureStateRowsPreserved=True,syntheticStateStableFieldsPreserved=True,syntheticStateRevisionAdvanced=True)
        report.update(globalTrack1Unchanged=await global_track1(owner)==facts,allLedgerRowsUnchanged=await preservation.ledger_fingerprints(owner)==ledger,
          existingApplicationRowsPreserved=after==before,ordinaryRetainedRoleWorkflowsVerified=True,
          forecastRolledBack=True,syntheticPrepFixturesRetained=True,sourceHashes={name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in
          ('hosted_build_workflows.py','hosted_staff_production.py','server.py','runtime_permissions.py','db_auxiliary.py')})
        if not all(report[k] for k in ('globalTrack1Unchanged','allLedgerRowsUnchanged','existingApplicationRowsPreserved')):raise AssertionError('Postflight preservation held')
        report['status']='passed_retained_login_enabled_workflows'
    except Exception as exc:
        report.update(status='held',errorType=type(exc).__name__,errorFrames=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(exc.__traceback__)])
        report['safeSystemErrorCode']=getattr(exc,'winerror',None) or getattr(exc,'errno',None)
        if isinstance(exc,(ValueError,AssertionError)):report['safeReason']=str(exc)
    finally:
        # Reconcile only this exact invented account, including lost create acknowledgment.
        if secondary and account_cleanup_authorized:
            try:
                await secondary.execute('DELETE FROM public.app_users WHERE email=$1 AND ($2::text IS NULL OR id=$2)',account_email,account_id)
                report['testAccountCleanupVerified']=not await secondary.fetchval('SELECT EXISTS(SELECT 1 FROM public.app_users WHERE email=$1)',account_email)
            except Exception as exc:report.update(status='held',accountCleanupErrorType=type(exc).__name__)
        for pool in (secondary,primary):
            if pool:
                try:await asyncio.wait_for(pool.close(),30)
                except Exception:pool.terminate()
        if owner:
            try:await asyncio.wait_for(owner.close(),10)
            except Exception:owner.terminate()
        emit({'stage':'complete' if report['status']=='passed_retained_login_enabled_workflows' else 'held_reconcile_before_retry'})
    return 0 if report['status']=='passed_retained_login_enabled_workflows' else 2

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('owner-config','overlay','provision-receipt','prior-workflow','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--expected-project',required=True);args=parser.parse_args()
    try:raise SystemExit(asyncio.run(run(args.owner_config,args.overlay,args.provision_receipt,args.prior_workflow,args.expected_project,args.output)))
    except Exception as exc:print(json.dumps({'status':'held_before_workflow','errorType':type(exc).__name__}));raise SystemExit(2)
