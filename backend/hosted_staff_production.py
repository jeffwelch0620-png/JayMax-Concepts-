"""Invented staff assignment/production over the actual application routes.

Uses only a previously labelled synthetic location, no startup/login or POS.
Retains pending submissions, independent acceptance and explicit task finish.
"""
import asyncio,json,os,re,secrets
from contextlib import ExitStack
from datetime import date,datetime,timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID,uuid4
import asyncpg,httpx
import db_pg,deployment_readiness as readiness


async def accounting_fingerprints(conn,store):
    tables=('actual_inventory.scopes','actual_inventory.scope_items','actual_inventory.count_snapshots',
        'actual_inventory.count_lines','actual_inventory.period_closures','actual_inventory.reopen_events',
        'actual_inventory.scope_bridges','purchasing.actual_purchase_facts')
    result={}
    async with conn.transaction(isolation='repeatable_read',readonly=True):
        await conn.execute("SET LOCAL TIME ZONE 'UTC'")
        for table in tables:
            result[table]=dict(await conn.fetchrow("SELECT count(*) AS rows,encode(sha256(convert_to(coalesce(string_agg(h,'' ORDER BY h),''),'UTF8')),'hex') AS sha256 FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS h FROM "+table+" t WHERE store_id=$1) x",store))
    return result


async def run(dsn,store,actual_params,ssl=None,emit=None,pool_setup=None):
    if not re.fullmatch(r'hosted_trial_[a-f0-9]{32}',store):raise ValueError('Invented store required')
    emit=emit or (lambda value:None)
    settings={'USE_PG':'true','AUTH_REQUIRED':'true','AUTH_SECRET':secrets.token_hex(32),
              **{name+'_ENABLED':'true' for name in readiness.FEATURES}}
    with patch.dict(os.environ,settings):
        import server
        pool=await asyncpg.create_pool(dsn,min_size=2,max_size=3,ssl=ssl,statement_cache_size=0,timeout=20,command_timeout=30,init=db_pg._init_connection,setup=pool_setup)
        try:
            async with pool.acquire() as conn:
                if await conn.fetchval('SELECT name FROM public.stores WHERE id=$1',store)!='Synthetic hosted committed test':raise ValueError('Invented fixture label required')
                before=await accounting_fingerprints(conn,store)
                emit({'stage':'track1_baseline_captured','track1FactFingerprintsBefore':before})
                recipes=await conn.fetch('SELECT * FROM prep_inventory.recipe_versions WHERE store_id=$1 ORDER BY revision DESC',store)
                if len(recipes)!=1:raise ValueError('Single retained invented recipe required')
                recipe=recipes[0]
                lines=await conn.fetch('SELECT * FROM prep_inventory.recipe_lines WHERE recipe_version_id=$1 ORDER BY line_number',recipe['id'])
                if len(lines)!=1 or lines[0]['source_kind']!='raw':raise ValueError('Single invented purchased ingredient required')
                old=await conn.fetchval('SELECT max(prep_date) FROM prep_inventory.day_lists WHERE store_id=$1',store)
                day=max(date(2026,10,9),old+timedelta(days=1) if old else date(2026,10,9))
                revision=await conn.fetchval('SELECT coalesce(max(revision),0) FROM prep_inventory.planning_versions WHERE product_id=$1',recipe['product_id'])
                batch_count=await conn.fetchval('SELECT count(*) FROM prep_inventory.batch_events WHERE store_id=$1',store)
                member=uuid4();nonce=uuid4().hex
                identities={name:'synthetic-production-'+name+'-'+nonce for name in ('author','counter','reviewer','readonly','wrong_location')}
                identities['roster_author']=str(member)
                emit({'stage':'invented_production_identities','activityActorIds':list(identities.values()),'staffMemberIds':[str(member)],'day':str(day)})
                await conn.execute("INSERT INTO public.staff_members(id,store_id,name) VALUES($1,$2,'Invented production cook')",member,store)
            with ExitStack() as patches:
                patches.enter_context(patch.object(server,'AUTH_SECRET',settings['AUTH_SECRET']))
                patches.enter_context(patch.object(server,'AUTH_REQUIRED',True))
                patches.enter_context(patch.object(server,'PG_STORE_IDS',server.PG_STORE_IDS|{store}))
                patches.enter_context(patch.dict(server.PG_STORE_TO_RESTAURANT,{store:store}))
                patches.enter_context(patch.dict(server.RESTAURANT_TO_PG_STORE,{store:store}))
                patches.enter_context(patch.object(db_pg,'_pool',pool))
                roles={'author':'owner','counter':'staff','reviewer':'owner','readonly':'readonly','wrong_location':'staff','roster_author':'owner'}
                tokens={name:server._token({'id':ident,'email':name+'@example.invalid','role':roles[name],
                    'locations':['berts'] if name=='wrong_location' else [store]}) for name,ident in identities.items()}
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://synthetic-production-probe') as client:
                    async def request(actor,method,path,body=None,key=None,version=None,expected=200,params=None):
                        if store not in path:raise ValueError('Request must target invented location')
                        headers={'Authorization':'Bearer '+tokens[actor]}
                        if method in ('POST','PUT'):headers['Idempotency-Key']=key or str(uuid4())
                        if version is not None:headers['If-Match']=str(version)
                        response=await client.request(method,path,json=body,headers=headers,params=params)
                        if response.status_code!=expected:raise AssertionError('Synthetic production API status '+str(response.status_code)+' expected '+str(expected)+' at '+path.split(store)[-1])
                        return response.json()
                    base='/api/pg/purchases/'+store;staff='/api/pg/staff/'+store
                    report='/api/pg/actual-inventory/'+store+'/report'
                    actual=await request('author','GET',report,params=actual_params)
                    plan=await request('author','PUT',base+'/prep-planning/'+str(recipe['product_id']),
                        {'action':'save','recipe_version_id':str(recipe['id']),'unit_profile_id':str(recipe['output_profile_id']),
                         'track':'daily','schedule':'daily','weekday_par':'4','weekend_par':'4','note':'Invented production trial','verified':True},version=revision)
                    draft={'track':'daily','day_group':'weekday','count_event_id':None,'overrides':[
                        {'planning_version_id':plan['plan']['id'],'kind':'fixed_quantity','quantity':'4','reason':'Explicit synthetic production target'}],
                        'note':'Invented assigned service day'}
                    path=base+'/prep-day-drafts/'+str(day)
                    preview=await request('author','POST',path+'/preview',draft,version=0)
                    saved=await request('author','PUT',path,{'draft':draft,'expected_review_hash':preview['reviewHash'],'reviewed':True},version=0)
                    draft_id=saved['draft']['id'];execution=base+'/prep-execution/'+str(day)
                    command={'action':'release','draft_version_id':draft_id,'reason':'Reviewed invented service day'}
                    preview=await request('author','POST',execution+'/preview',command,version=0)
                    released=await request('author','POST',execution+'/commands',{'command':command,'expected_review_hash':preview['reviewHash'],'reviewed':True},version=0)
                    task=released['current']['tasks'][0]
                    assignment_path=base+'/staff-prep-tasks/'+str(day)
                    assignment={'task_id':task['id'],'expected_revision':0,'staff_member_id':str(member),'note':'Invented reviewed roster assignment'}
                    preview=await request('author','POST',assignment_path+'/preview',assignment)
                    assignment_body={'assignment':assignment,'expected_review_hash':preview['reviewHash'],'reviewed':True};assignment_key=str(uuid4())
                    race=await asyncio.gather(request('author','POST',assignment_path+'/assignments',assignment_body,assignment_key),request('author','POST',assignment_path+'/assignments',assignment_body,assignment_key))
                    assigned=race[0]['assignment']
                    if race[1]['assignment']['id']!=assigned['id']:raise AssertionError('Assignment retry duplicated history')
                    portal_body={'pin':'','day':str(day),'track':'daily','staff_member_id':str(member)}
                    portal=await request('counter','POST',staff+'/prep-task-plan',portal_body)
                    if portal['identity_verified'] or len(portal['tasks'])!=1 or portal['tasks'][0]['assignment']!=assigned['id']:raise AssertionError('Claimed roster assignment was lost or marked verified')
                    await request('wrong_location','POST',staff+'/prep-task-plan',portal_body,expected=403)
                    await request('readonly','POST',assignment_path+'/preview',assignment,expected=403)
                    await request('counter','POST',assignment_path+'/preview',assignment,expected=403)
                    batch={'recipe_version_id':str(recipe['id']),'planned_batches':'1','output_quantity':'2.000000000001',
                        'performed_at':str(day)+'T10:00:00-04:00','business_date':str(day),'timezone_name':'America/New_York',
                        'calendar_date_confirmed':True,'single_output_confirmed':True,'note':'Invented measured partial production',
                        'inputs':[{'recipe_line_id':str(lines[0]['id']),'quantity':'2.5','source_unit':lines[0]['source_unit'],'factor':str(lines[0]['factor']),
                                   'measurement_basis':'measured','evidence':'Invented scale measurement'}]}
                    submission={'root_id':str(uuid4()),'expected_revision':0,'task_id':task['id'],'staff_member_id':str(member),
                        'assignment_id':assigned['id'],'kind':'submit','batch':batch,'note':'Invented measured production'}
                    production=staff+'/prep-production/'+str(day);decisions=base+'/staff-prep-production/'+str(day)
                    preview=await request('author','POST',production+'/preview',{'pin':'','submission':submission})
                    first=await request('author','POST',production+'/submissions',{'pin':'','submission':submission,'expected_review_hash':preview['reviewHash'],'reviewed':True})
                    submission=submission|{'expected_revision':1,'note':'Staff independently supplied final measurement'}
                    preview=await request('counter','POST',production+'/preview',{'pin':'','submission':submission})
                    body={'pin':'','submission':submission,'expected_review_hash':preview['reviewHash'],'reviewed':True};key=str(uuid4())
                    race=await asyncio.gather(request('counter','POST',production+'/submissions',body,key),request('counter','POST',production+'/submissions',body,key))
                    measured=race[0]
                    if race[1]['submission']['id']!=measured['submission']['id']:raise AssertionError('Production retry duplicated submission')
                    async with pool.acquire() as conn:
                        if await conn.fetchval('SELECT count(*) FROM prep_inventory.batch_events WHERE store_id=$1',store)!=batch_count:raise AssertionError('Pending staff submission created production')
                    emit({'stage':'pending_staff_production_created_no_batch','rootId':submission['root_id'],'taskId':task['id']})
                    await request('counter','POST',production+'/submissions',body|{'submission':submission|{'note':'Different body'}},key,expected=409)
                    await request('counter','POST',production+'/submissions',body,expected=409)
                    decision={'submission_id':measured['submission']['id'],'decision':'accepted','task_complete':False,'note':'Independent inspected measured batch'}
                    await request('author','POST',decisions+'/preview',decision,expected=403)
                    await request('roster_author','POST',decisions+'/preview',decision,expected=403)
                    await request('counter','POST',decisions+'/preview',decision,expected=403)
                    preview=await request('reviewer','POST',decisions+'/preview',decision)
                    payload=decision|{'expected_review_hash':preview['reviewHash'],'reviewed':True};decision_key=str(uuid4())
                    await request('author','POST',decisions+'/decisions',payload,expected=403)
                    race=await asyncio.gather(request('reviewer','POST',decisions+'/decisions',payload,decision_key),request('reviewer','POST',decisions+'/decisions',payload,decision_key))
                    accepted=race[0]
                    if race[1]['batch_event']['id']!=accepted['batch_event']['id'] or accepted['finish_event'] is not None:raise AssertionError('Partial acceptance duplicated or finished production')
                    progress=accepted['current']['execution']['task_progress'][0]
                    if progress['status']!='in_progress' or progress['reviewed_base_quantity']!='2.000000000001':raise AssertionError('Partial measured progress was lost')
                    emit({'stage':'independent_partial_acceptance_verified','batchId':accepted['batch_event']['id']})
                    command={'action':'finish','draft_version_id':draft_id,'task_id':task['id'],'reason':'Manager explicitly finished partial service task'}
                    version=accepted['current']['execution']['revision']
                    preview=await request('reviewer','POST',execution+'/preview',command,version=version)
                    finished=await request('reviewer','POST',execution+'/commands',{'command':command,'expected_review_hash':preview['reviewHash'],'reviewed':True},version=version)
                    if finished['current']['task_progress'][0]['status']!='complete':raise AssertionError('Explicit task finish was not recorded')
                    emit({'stage':'explicit_task_finish_verified','finishEventId':finished['event']['id']})
                    if await request('reviewer','GET',report,params=actual_params)!=actual:raise AssertionError('Staff production changed Track 1 report')
                    async with pool.acquire() as conn:
                        if await accounting_fingerprints(conn,store)!=before:raise AssertionError('Staff production changed accounting facts')
                        count=await conn.fetchval('SELECT count(*) FROM prep_inventory.batch_events WHERE store_id=$1',store)
                        if count!=batch_count+1:raise AssertionError('Acceptance created extra batches')
                        audit=await conn.fetchrow('SELECT submitted_by,review_snapshot FROM prep_inventory.staff_production_submissions WHERE id=$1',UUID(measured['submission']['id']))
                        if audit['submitted_by']!=identities['counter'] or 'pin' in audit['review_snapshot'] or 'pin' in audit['review_snapshot']['submission']:raise AssertionError('Private audit or credential retention failed')
                        audit_rows=await conn.fetchval('SELECT count(*) FROM public.activity_log WHERE user_id=ANY($1::text[])',list(identities.values()))
                        if audit_rows<20:raise AssertionError('Application activity logging was not verified')
                    result={'status':'passed','store':store,'day':str(day),'staffMemberIds':[str(member)],'activityActorIds':list(identities.values()),
                        'rootId':submission['root_id'],'taskId':task['id'],'batchId':accepted['batch_event']['id'],
                        'assignmentId':assigned['id'],'actualFoodCost':actual['actualFoodCost'],'track1ReportAndAllFactsUnchanged':True,
                        'pendingSubmissionCreatesNoBatch':True,'concurrentAssignmentSubmissionAcceptanceVerified':True,
                        'independentAuthorAndRosterReviewHeld':True,'exactMeasuredOutput':'2.000000000001',
                        'partialProgressThenExplicitFinishVerified':True,'identityVerified':False,'loginVerified':False,
                        'applicationRoutesAndMiddlewareUsed':True,'applicationFlagsChanged':False,'activityRowsBeforeRestart':audit_rows}
                await asyncio.wait_for(pool.close(),20)
                pool=await asyncpg.create_pool(dsn,min_size=2,max_size=3,ssl=ssl,statement_cache_size=0,timeout=20,command_timeout=30,init=db_pg._init_connection,setup=pool_setup)
                with patch.object(db_pg,'_pool',pool):
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://synthetic-production-probe') as client:
                        replay=await request('counter','POST',production+'/submissions',body,key)
                        reviewed=await request('reviewer','POST',decisions+'/decisions',payload,decision_key)
                        if not replay['replayed'] or replay['submission']!=measured['submission'] or not reviewed['replayed'] or reviewed['batch_event']['id']!=result['batchId']:raise AssertionError('Fresh pool retry changed production history')
                        if any(ident in json.dumps(replay) for name,ident in identities.items() if name!='roster_author'):raise AssertionError('Staff retry exposed private audit identity')
                        if reviewed['current']['execution']['task_progress'][0]['status']!='complete':raise AssertionError('Replay lost current completed task')
                        async with pool.acquire() as conn:
                            if await accounting_fingerprints(conn,store)!=before:raise AssertionError('Fresh pool retry changed accounting facts')
                result['freshPoolReplayAndPrivateStaffProjectionVerified']=True
                emit({'stage':'staff_production_and_fresh_pool_replay_passed'})
        except BaseException:pool.terminate();raise
        else:
            try:await asyncio.wait_for(pool.close(),20)
            except BaseException:pool.terminate();raise
        return result
