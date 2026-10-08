"""Synthetic native API validation over committed, separate pool connections.

Uses only an invented location and actor, without app login or external POS.
Retains immutable invented records as clearly labelled build-test evidence.
"""
import asyncio
import os
from unittest.mock import patch
import asyncpg
from fastapi import FastAPI,HTTPException
import httpx
import db_pg
import deployment_readiness as readiness
import hosted_test_trial as trial
import purchase_api as purchases
import actual_inventory_api as actual


class PoolReader:
    """Short read/seed leases; never park an idle observer during API requests."""
    def __init__(self,pool):self.pool=pool
    async def execute(self,*args):
        async with self.pool.acquire() as conn:return await conn.execute(*args)
    async def fetch(self,*args):
        async with self.pool.acquire() as conn:return await conn.fetch(*args)
    async def fetchrow(self,*args):
        async with self.pool.acquire() as conn:return await conn.fetchrow(*args)
    async def fetchval(self,*args):
        async with self.pool.acquire() as conn:return await conn.fetchval(*args)


async def fresh_pool_replay(pool, fixture):
    store=fixture['store'];app=FastAPI()
    def check(location):
        if location!=store:raise HTTPException(404)
    def actor(request,location,write):
        check(location)
        if request.headers.get('authorization')!='Bearer synthetic-hosted-trial':raise HTTPException(401)
        return 'synthetic-hosted-trial'
    app.include_router(purchases.create_router(lambda:pool,check,actor))
    app.include_router(actual.create_router(lambda:pool,check,actor))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://trial',headers={'Authorization':'Bearer synthetic-hosted-trial'}) as client:
        for prefix in ('purchase','prep'):
            response=await client.post(fixture[prefix+'Path'],json=fixture[prefix+'Body'],headers={'Idempotency-Key':fixture[prefix+'Key']})
            if response.status_code!=200:raise AssertionError('Fresh connection replay held')
            body=response.json();ident=body['batchId'] if prefix=='purchase' else body['event']['id']
            if ident!=fixture[prefix+'BatchId']:raise AssertionError('Fresh connection replay duplicated history')
        response=await client.get(fixture['actualPath'],params=fixture['reportParams'])
        if response.status_code!=200 or response.json()!=fixture['expectedActualReport']:
            raise AssertionError('Fresh connection actual report drifted')
    async with pool.acquire() as conn:
        if await conn.fetchval('SELECT count(*) FROM purchasing.actual_purchase_facts WHERE store_id=$1',store)!=1:
            raise AssertionError('Purchase facts duplicated')
        if await conn.fetchval('SELECT count(*) FROM prep_inventory.batch_events WHERE store_id=$1',store)!=1:
            raise AssertionError('Prep facts duplicated')
    return {'freshPoolPurchaseReplaySameBatch':True,'freshPoolPrepReplaySameBatch':True,
            'freshPoolTrack1ReportUnchanged':True,'exactlyOnePurchaseAndPrepBatch':True}


async def run(dsn, ssl=None, emit=None):
    settings={'USE_PG':'true',**{name+'_ENABLED':'true' for name in readiness.FEATURES}}
    # Flags are confined to this probe process; no env file or built app edit.
    with patch.dict(os.environ,settings):
        pool=await asyncpg.create_pool(dsn,min_size=2,max_size=3,ssl=ssl,statement_cache_size=0,init=db_pg._init_connection)
        try:
            proof=await trial.synthetic_workflow(PoolReader(pool),pool=pool,emit=emit)
        except BaseException:
            # Cleanup must never replace the workflow's original error.
            pool.terminate();raise
        else:
            try:await asyncio.wait_for(pool.close(),timeout=20)
            except BaseException:pool.terminate();raise
        pool=await asyncpg.create_pool(dsn,min_size=2,max_size=3,ssl=ssl,statement_cache_size=0,init=db_pg._init_connection)
        try:proof['independentReplay']=await fresh_pool_replay(pool,proof['replayFixture'])
        except BaseException:pool.terminate();raise
        else:
            try:await asyncio.wait_for(pool.close(),timeout=20)
            except BaseException:pool.terminate();raise
        # Fixture contains invented payloads only, but compact public evidence
        # needs only stable synthetic IDs and conclusions.
        proof.pop('replayFixture')
        return proof
