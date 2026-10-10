"""Actual app routes: synthetic staff counts and independent review on native PG.

No login/bootstrap, external service, real restaurant writes or startup hooks.
The already retained synthetic location is temporarily registered in this probe
process; signed synthetic identities use the application's actual role gates.
"""
import asyncio
from contextlib import ExitStack
from decimal import Decimal
import os
import secrets
from unittest.mock import patch
from uuid import UUID,uuid4
import asyncpg
import httpx
import db_pg
import deployment_readiness as readiness


async def run(dsn,store,actual_params,ssl=None,emit=None,pool_setup=None):
    if not __import__('re').fullmatch(r'hosted_trial_[a-f0-9]{32}',store):
        raise ValueError('Staff probe accepts only a labelled invented location')
    settings={'USE_PG':'true','AUTH_REQUIRED':'true','AUTH_SECRET':secrets.token_hex(32),
              **{name+'_ENABLED':'true' for name in readiness.FEATURES}}
    emit=emit or (lambda stage:None)
    with patch.dict(os.environ,settings):
        import server
        pool=await asyncpg.create_pool(dsn,min_size=2,max_size=3,ssl=ssl,statement_cache_size=0,
                                      init=db_pg._init_connection,setup=pool_setup)
        try:
            async with pool.acquire() as conn:
                if await conn.fetchval('SELECT name FROM public.stores WHERE id=$1',store)!='Synthetic hosted committed test':
                    raise ValueError('Selected location is not the retained invented build fixture')
                database_role=dict(await conn.fetchrow('SELECT current_user AS name,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user'))
            nonce=uuid4().hex
            identities={name:'synthetic-staff-'+name+'-'+nonce for name in ('author','counter','reviewer','readonly','wrong_location')}
            emit({'stage':'synthetic_identities_created','activityActorIds':list(identities.values())})
            with ExitStack() as patches:
                patches.enter_context(patch.object(server,'AUTH_SECRET',settings['AUTH_SECRET']))
                patches.enter_context(patch.object(server,'AUTH_REQUIRED',True))
                patches.enter_context(patch.object(server,'PG_STORE_IDS',server.PG_STORE_IDS|{store}))
                patches.enter_context(patch.dict(server.PG_STORE_TO_RESTAURANT,{store:store}))
                patches.enter_context(patch.dict(server.RESTAURANT_TO_PG_STORE,{store:store}))
                patches.enter_context(patch.object(db_pg,'_pool',pool))
                roles={'author':'owner','counter':'staff','reviewer':'owner','readonly':'readonly','wrong_location':'staff'}
                tokens={name:server._token({'id':ident,'email':ident+'@example.invalid','role':roles[name],
                    'locations':['berts'] if name=='wrong_location' else [store]}) for name,ident in identities.items()}
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://synthetic-staff-probe') as client:
                    async def request(actor,method,path,body=None,key=None,expected=200,params=None):
                        # The sole non-fixture path is a staff-denied location check.
                        if store not in path and not (actor=='counter' and '/staff/berts/' in path):
                            raise ValueError('Probe request must target its invented location')
                        headers={'Authorization':'Bearer '+tokens[actor]}
                        if method=='POST':headers['Idempotency-Key']=key or str(uuid4())
                        response=await client.request(method,path,json=body,headers=headers,params=params)
                        if response.status_code!=expected:
                            raise AssertionError('Synthetic staff API status '+str(response.status_code)+' expected '+str(expected)+' at '+path.split(store)[-1])
                        return response
                    manager='/api/pg/purchases/'+store+'/staff-prep-counts'
                    staff='/api/pg/staff/'+store+'/prep-count-drafts'
                    actual='/api/pg/actual-inventory/'+store+'/report'
                    baseline=(await request('author','GET',actual,params=actual_params)).json()
                    setup=(await request('author','GET',manager)).json()
                    units=[{'product_version_id':p['id'],'profile_id':next(u['id'] for u in setup['profiles'] if u['product_version_id']==p['id'] and Decimal(u['base_units_per_source_unit'])==1)}
                           for p in setup['products']]
                    if not units:raise ValueError('Retained synthetic prep fixture lacks verified units')
                    # Unique boundary: never overwrite existing native counts.
                    from datetime import datetime,timezone
                    stamp=datetime.now(timezone.utc).astimezone(__import__('zoneinfo').ZoneInfo('America/New_York')).replace(microsecond=0)
                    sheet={'performed_at':stamp.isoformat(),'business_date':stamp.date().isoformat(),'timezone_name':'America/New_York',
                           'calendar_date_confirmed':True,'note':'Invented staff probe; Track 2 only','units':units}
                    preview=(await request('author','POST',manager+'/preview',sheet)).json()
                    issued=(await request('author','POST',manager,{'sheet':sheet,'expected_review_hash':preview['reviewHash'],'reviewed':True})).json()
                    review=issued['current'];ident=issued['sheet']['id'];submit=staff+'/'+ident+'/submit';decision=manager+'/'+ident
                    emit({'stage':'sheet_issued','sheetId':ident})
                    def submission(current,quantity):
                        return {'pin':'','expected_review_hash':current['reviewHash'],'counter_name':'Invented physical counter',
                            'note':'Synthetic measured quantities','lines':[{'product_id':i['product_id'],'quantity':quantity,'evidence':'Invented scale measurement'} for i in current['sheet']['sheet_snapshot']['items']]}
                    unknown=(await request('author','POST',submit,submission(review,None))).json()
                    command={'decision':'accepted','note':'Independent synthetic physical review','reviewed':True}
                    await request('reviewer','POST',decision+'/decision-preview',command,expected=422)
                    emit('unknown_quantity_held')
                    await request('readonly','POST',staff,{'pin':''},expected=403)
                    await request('wrong_location','POST',staff,{'pin':''},expected=403)
                    await request('counter','POST','/api/pg/staff/berts/prep-count-drafts',{'pin':''},expected=403)
                    await request('counter','POST',manager+'/preview',sheet,expected=403)
                    key=str(uuid4());body=submission(unknown['current'],'48.123456789012')
                    responses=await asyncio.gather(request('counter','POST',submit,body,key),request('counter','POST',submit,body,key))
                    measured=responses[0].json()
                    if responses[1].json()['submission']['id']!=measured['submission']['id']:raise AssertionError('Staff concurrent retry duplicated a revision')
                    await request('counter','POST',submit,submission(review,'48.123456789012'),expected=409)
                    changed=body|{'note':'Different body on same key'}
                    await request('counter','POST',submit,changed,key,expected=409)
                    await request('author','POST',decision+'/decision-preview',command,expected=403)
                    plan=(await request('reviewer','POST',decision+'/decision-preview',command)).json()
                    payload=command|{'expected_review_hash':plan['current']['reviewHash'],'expected_observation_hash':plan['observation']['reviewHash']}
                    await request('author','POST',decision+'/decision',payload,expected=403)
                    async with pool.acquire() as conn:
                        if await conn.fetchval('SELECT count(*) FROM prep_inventory.staff_decisions WHERE sheet_id=$1',UUID(ident))!=0:
                            raise AssertionError('Failed author acceptance changed history')
                    emit('author_and_stale_requests_held')
                    decision_key=str(uuid4())
                    accepted=await asyncio.gather(request('reviewer','POST',decision+'/decision',payload,decision_key),request('reviewer','POST',decision+'/decision',payload,decision_key))
                    saved=accepted[0].json()
                    if accepted[1].json()['observation']['id']!=saved['observation']['id']:raise AssertionError('Acceptance retry duplicated a physical observation')
                    retry=(await request('counter','POST',submit,body,key)).json()
                    if not retry['replayed'] or retry['submission']!=measured['submission'] or retry['current']['decision'] is None:
                        raise AssertionError('Post-acceptance staff retry lost original revision or current decision')
                    if any(value in __import__('json').dumps(retry) for value in identities.values()):
                        raise AssertionError('Staff response leaked private audit attribution')
                    final=(await request('reviewer','GET',actual,params=actual_params)).json()
                    if final!=baseline:raise AssertionError('Reviewed Track 2 count changed Track 1')
                    async with pool.acquire() as conn:
                        revisions=await conn.fetchval('SELECT count(*) FROM prep_inventory.staff_submissions WHERE sheet_id=$1',UUID(ident))
                        decisions=await conn.fetchval('SELECT count(*) FROM prep_inventory.staff_decisions WHERE sheet_id=$1',UUID(ident))
                        quantities=await conn.fetch('SELECT quantity,base_quantity FROM prep_inventory.count_observations WHERE event_id=$1',UUID(saved['observation']['id']))
                        if revisions!=2 or decisions!=1 or not quantities or any(r['quantity']!=Decimal('48.123456789012') or r['base_quantity']!=Decimal('48.123456789012') for r in quantities):
                            raise AssertionError('Accepted staff count lost exact quantity or journal cardinality')
                        audit=await conn.fetchrow('SELECT submitted_by,submitted_body FROM prep_inventory.staff_submissions WHERE id=$1',UUID(measured['submission']['id']))
                        if audit['submitted_by']!=identities['counter'] or 'pin' in audit['submitted_body']:
                            raise AssertionError('Audit actor was lost or PIN retained')
                        reviewer=await conn.fetchval('SELECT reviewed_by FROM prep_inventory.staff_decisions WHERE sheet_id=$1',UUID(ident))
                        if reviewer!=identities['reviewer']:raise AssertionError('Independent review attribution was lost')
                    emit('independent_review_exact_quantity_and_track1_passed')
                    result={'status':'passed','store':store,'sheetId':ident,'observationId':saved['observation']['id'],
                        'applicationRoutesAndMiddlewareUsed':True,'syntheticSignedIdentitiesOnly':True,'loginVerified':False,
                        'databaseRole':database_role,'unknownQuantityHeld':True,'independentAuthorReviewHeld':True,
                        'staffRoleAndLocationBoundariesHeld':True,'staleAndChangedKeyRequestsHeld':True,
                        'concurrentSubmissionAndDecisionReplayVerified':True,'exactAcceptedQuantity':'48.123456789012',
                        'privateAuditRetainedAndStaffProjectionVerified':True,'track1Unchanged':True,
                        'actualFoodCost':baseline['actualFoodCost'],'submissions':revisions,'decisions':decisions,
                        'activityActorIds':list(identities.values()),'applicationFlagsChanged':False}
                # All request leases have ended. Replay immutable receipts through
                # an entirely new pool while retaining the same synthetic session.
                await asyncio.wait_for(pool.close(),timeout=20)
                pool=await asyncpg.create_pool(dsn,min_size=2,max_size=3,ssl=ssl,statement_cache_size=0,
                    init=db_pg._init_connection,setup=pool_setup)
                with patch.object(db_pg,'_pool',pool):
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url='http://synthetic-staff-probe') as client:
                        replay=(await request('counter','POST',submit,body,key)).json()
                        review_replay=(await request('reviewer','POST',decision+'/decision',payload,decision_key)).json()
                        if not replay['replayed'] or replay['submission']!=measured['submission'] or not review_replay['replayed'] or review_replay['observation']['id']!=saved['observation']['id']:
                            raise AssertionError('Fresh pool replay changed staff or review history')
                        if any(value in __import__('json').dumps(replay) for value in identities.values()):
                            raise AssertionError('Fresh pool staff replay leaked audit attribution')
                        if (await request('reviewer','GET',actual,params=actual_params)).json()!=baseline:
                            raise AssertionError('Fresh pool staff replay changed Track 1')
                result['freshPoolStaffAndReviewReplayVerified']=True
                emit('fresh_pool_staff_and_review_replay_passed')
        except BaseException:
            pool.terminate();raise
        else:
            try:await asyncio.wait_for(pool.close(),timeout=20)
            except BaseException:pool.terminate();raise
        return result
