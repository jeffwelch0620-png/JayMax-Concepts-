"""Reviewed prep definitions only: no stock, accounting, production or sales writes."""
import os
import json
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from typing import Literal
from uuid import UUID

from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

from native_units import lock_store
from purchase_api import serial
from purchase_parser import fingerprint

UNITS=Literal['lb','oz','g','kg','fl_oz','ml','l','gal','each']
DIMENSIONS={'lb':'mass','oz':'mass','g':'mass','kg':'mass','fl_oz':'volume','ml':'volume','l':'volume','gal':'volume','each':'count'}
# US customary liquid units, matching the purchased inventory's gal/fl_oz labels.
SIZES={'lb':Decimal('453.59237'),'oz':Decimal('28.349523125'),'g':Decimal('1'),'kg':Decimal('1000'),
       'fl_oz':Decimal('29.5735295625'),'gal':Decimal('3785.411784'),'ml':Decimal('1'),'l':Decimal('1000'),'each':Decimal('1')}
POSITIVE=Field(gt=0,max_digits=28,decimal_places=12)


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)


class ProductIn(Strict):
    product_id:UUID|None=None
    predecessor_id:UUID|None=None
    name:str=Field(min_length=1,max_length=160)
    base_unit:UNITS
    note:str=Field(min_length=1,max_length=2000)
    verified:Literal[True]

    @model_validator(mode='after')
    def ancestry(self):
        if (self.product_id is None)!=(self.predecessor_id is None):raise ValueError('Updating a product requires its current version')
        return self


class ProfileIn(Strict):
    product_version_id:UUID
    source_unit:str=Field(min_length=1,max_length=80)
    factor:Decimal=POSITIVE
    predecessor_id:UUID|None=None
    note:str=Field(min_length=1,max_length=2000)
    verified:Literal[True]

    @field_validator('source_unit')
    @classmethod
    def normalized_unit(cls,value):return value.casefold()


class IngredientIn(Strict):
    source_kind:Literal['raw','prepared']
    raw_item_code:str|None=None
    prepared_recipe_id:UUID|None=None
    prepared_profile_id:UUID|None=None
    quantity:Decimal=POSITIVE
    source_unit:str=Field(min_length=1,max_length=80)
    factor:Decimal=POSITIVE
    evidence:str=Field(min_length=1,max_length=2000)

    @field_validator('source_unit')
    @classmethod
    def normalized_unit(cls,value):return value.casefold()

    @model_validator(mode='after')
    def exactly_one_source(self):
        raw=self.raw_item_code is not None and bool(self.raw_item_code) and self.prepared_recipe_id is None and self.prepared_profile_id is None
        prepared=self.raw_item_code is None and self.prepared_recipe_id is not None and self.prepared_profile_id is not None
        if not ((self.source_kind=='raw' and raw) or (self.source_kind=='prepared' and prepared)):raise ValueError('Select exactly one purchased or prepared ingredient')
        return self


class LegacyIn(Strict):
    source_type:Literal['dish','prep_item']
    source_id:UUID
    expected_source_hash:str=Field(pattern=r'^[0-9a-f]{64}$')


class RecipeIn(Strict):
    product_version_id:UUID
    output_profile_id:UUID
    entered_yield:Decimal=POSITIVE
    predecessor_id:UUID|None=None
    method:str=Field(min_length=1,max_length=10000)
    note:str=Field(min_length=1,max_length=2000)
    lines:list[IngredientIn]=Field(min_length=1,max_length=200)
    legacy:LegacyIn|None=None


class PromotionIn(Strict):
    recipe:RecipeIn
    expected_review_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    reviewed:Literal[True]


def enabled():return os.getenv('PREP_SETUP_ENABLED','false').lower()=='true'


async def ready(conn):
    if not await conn.fetchval("SELECT to_regclass('prep_inventory.legacy_crosswalks') IS NOT NULL"):
        raise HTTPException(503,'Prep mapping foundation is awaiting schema setup')


def conversion(source,base,factor):
    if source not in DIMENSIONS or DIMENSIONS[source]!=DIMENSIONS[base]:
        raise HTTPException(422,'Use a physical unit in the same dimension. Container or density mappings require separate verification.')
    with localcontext() as ctx:
        ctx.prec=80
        expected=(SIZES[source]/SIZES[base]).quantize(Decimal('0.000000000001'),rounding=ROUND_HALF_EVEN)
    if factor!=expected:raise HTTPException(422,'Physical unit factor does not match the declared units (12 decimal places)')


def times(a,b):
    with localcontext() as ctx:
        ctx.prec=max(80,len(a.as_tuple().digits)+len(b.as_tuple().digits))
        return a*b


async def current_product(conn,store,version_id):
    version=await conn.fetchrow('SELECT * FROM prep_inventory.product_versions WHERE id=$1 AND store_id=$2',version_id,store)
    if not version:raise HTTPException(422,'Prepared product version is not at this location')
    latest=await conn.fetchval('SELECT id FROM prep_inventory.product_versions WHERE product_id=$1 ORDER BY revision DESC LIMIT 1',version['product_id'])
    if latest!=version_id:raise HTTPException(409,'Prepared product definition changed. Refresh its current version.')
    return dict(version)


async def current_profile(conn,store,profile_id,version_id):
    p=await conn.fetchrow('SELECT * FROM prep_inventory.unit_profiles WHERE id=$1 AND store_id=$2 AND product_version_id=$3',profile_id,store,version_id)
    if not p:raise HTTPException(422,'Choose a verified unit belonging to this prepared product version')
    latest=await conn.fetchval('SELECT id FROM prep_inventory.unit_profiles WHERE product_version_id=$1 AND source_unit=$2 ORDER BY revision DESC LIMIT 1',version_id,p['source_unit'])
    if latest!=profile_id:raise HTTPException(409,'Prepared unit conversion changed. Refresh its current version.')
    return dict(p)


async def legacy_sources(conn,store):
    dishes=await conn.fetch('SELECT to_jsonb(d)::text AS value FROM public.dishes d WHERE store_id=$1 ORDER BY id',store)
    result=[]
    for d in dishes:
        source=json.loads(d['value'],parse_float=Decimal)
        lines=await conn.fetch('SELECT to_jsonb(l)::text AS value FROM public.dish_lines l WHERE dish_id=$1 ORDER BY id',UUID(source['id']))
        snapshot=serial({'header':source,'lines':[json.loads(l['value'],parse_float=Decimal) for l in lines]})
        issues=['Legacy quantity, yield and portion conversions have not been adopted']
        if not source.get('yield_uom'):issues.append('Usable yield unit is missing')
        yield_value=Decimal(str(source['yield_qty'])) if source.get('yield_qty') is not None else None
        if yield_value is None or not yield_value.is_finite() or yield_value<=0:issues.append('Positive finite usable yield is missing')
        if not lines:issues.append('Ingredient list is empty')
        for l in snapshot['lines']:
            if not l.get('uom'):issues.append('Ingredient '+l['id']+': physical unit is missing')
            if (l.get('item_code') is not None)+(l.get('prep_dish_id') is not None)!=1:issues.append('Ingredient '+l['id']+': source identity is ambiguous')
            qty=Decimal(str(l['qty']))
            if not qty.is_finite() or qty<=0:issues.append('Ingredient '+l['id']+': positive finite quantity is missing')
        result.append({'sourceType':'dish','sourceId':source['id'],'name':source['name'],'snapshot':snapshot,'hash':fingerprint(snapshot).hex(),'issues':issues})
    for row in await conn.fetch('SELECT to_jsonb(p)::text AS value FROM public.prep_items p WHERE store_id=$1 ORDER BY id',store):
        source=serial(json.loads(row['value'],parse_float=Decimal));snapshot={'header':source}
        result.append({'sourceType':'prep_item','sourceId':source['id'],'name':source['name'],'snapshot':snapshot,'hash':fingerprint(snapshot).hex(),
                       'issues':['Container labels and vessel capacity are unverified physical conversions','Review raw item or linked recipe identity; do not import prior stock automatically']})
    crosswalks=await conn.fetch('SELECT * FROM prep_inventory.legacy_crosswalks WHERE store_id=$1 ORDER BY confirmed_at,id',store)
    for source in result:
        mappings=[dict(x) for x in crosswalks if x['source_type']==source['sourceType'] and str(x['source_id'])==source['sourceId']]
        current=next((x for x in mappings if not any(y['predecessor_id']==x['id'] for y in mappings)),None)
        source['mapping']=current
        source['mappingState']='unreviewed' if current is None else ('source_changed' if current['source_hash'].hex()!=source['hash'] else 'reviewed')
    return result


async def ancestry(conn,recipe_id):
    return await conn.fetch('''WITH RECURSIVE nodes AS (
        SELECT id FROM prep_inventory.recipe_versions WHERE id=$1
        UNION SELECT r.id FROM nodes a JOIN prep_inventory.recipe_lines l ON l.recipe_version_id=a.id
            JOIN prep_inventory.recipe_versions r ON r.id=l.prepared_recipe_id
        ) SELECT r.* FROM nodes n JOIN prep_inventory.recipe_versions r ON r.id=n.id ORDER BY r.id''',recipe_id)


async def ancestry_changed(conn,store,versions,sources):
    """Current review eligibility includes every producing ancestor, not only its ID."""
    try:
        for r in versions:
            await current_product(conn,store,r['product_version_id'])
            await current_profile(conn,store,r['output_profile_id'],r['product_version_id'])
            latest=await conn.fetchval('SELECT id FROM prep_inventory.recipe_versions WHERE product_id=$1 ORDER BY revision DESC LIMIT 1',r['product_id'])
            if latest!=r['id']:return True
            for l in r['review_snapshot']['lines']:
                if l['source_kind']=='raw':
                    raw=await conn.fetchrow('''SELECT i.code,i.name,i.item_type,i.base_unit AS catalog_unit,i.pack_count,i.unit_qty,i.unit_uom,ib.base_unit
                        FROM public.items i JOIN purchasing.item_bases ib ON ib.item_code=i.code AND ib.store_id=$1 WHERE i.code=$2 AND i.item_type='raw' ''',store,l['raw_item_code'])
                    if raw is None or fingerprint(serial(dict(raw)))!=fingerprint(l['source_snapshot']['raw']):return True
                else:
                    await current_profile(conn,store,UUID(l['prepared_profile_id']),UUID(l['prepared_product_version_id']))
            legacy=r['review_snapshot']['legacy']
            if legacy:
                s=next((s for s in sources if s['sourceType']==legacy['source_type'] and s['sourceId']==legacy['source_id']),None)
                if s is None or s['hash']!=legacy['hash']:return True
    except HTTPException:return True
    return False


async def setup(conn,store):
    await ready(conn)
    products=await conn.fetch('''SELECT DISTINCT ON(product_id) * FROM prep_inventory.product_versions WHERE store_id=$1 ORDER BY product_id,revision DESC''',store)
    profiles=await conn.fetch('''SELECT DISTINCT ON(product_version_id,source_unit) * FROM prep_inventory.unit_profiles WHERE store_id=$1 ORDER BY product_version_id,source_unit,revision DESC''',store)
    recipes=await conn.fetch('''SELECT DISTINCT ON(product_id) * FROM prep_inventory.recipe_versions WHERE store_id=$1 ORDER BY product_id,revision DESC''',store)
    raw=await conn.fetch('''SELECT i.code,i.name,ib.base_unit FROM public.items i JOIN public.store_items si ON si.item_code=i.code AND si.store_id=$1
        LEFT JOIN purchasing.item_bases ib ON ib.store_id=si.store_id AND ib.item_code=i.code WHERE i.item_type='raw' ORDER BY i.code''',store)
    recipe_results=[]
    sources=await legacy_sources(conn,store)
    for row in recipes:
        recipe=dict(row);issues=[];review=recipe['review_snapshot']
        try:
            await current_product(conn,store,recipe['product_version_id'])
            await current_profile(conn,store,recipe['output_profile_id'],recipe['product_version_id'])
            for line in review['lines']:
                if line['source_kind']=='raw':
                    current=await conn.fetchrow('''SELECT i.code,i.name,i.item_type,i.base_unit AS catalog_unit,i.pack_count,i.unit_qty,i.unit_uom,ib.base_unit
                        FROM public.items i JOIN purchasing.item_bases ib ON ib.item_code=i.code AND ib.store_id=$1 WHERE i.code=$2 AND i.item_type='raw' ''',store,line['raw_item_code'])
                    if current is None or fingerprint(serial(dict(current)))!=fingerprint(line['source_snapshot']['raw']):issues.append('Purchased ingredient setup changed')
                else:
                    v=UUID(line['prepared_product_version_id']);await current_product(conn,store,v)
                    await current_profile(conn,store,UUID(line['prepared_profile_id']),v)
                    latest=await conn.fetchval('SELECT id FROM prep_inventory.recipe_versions WHERE product_id=$1 ORDER BY revision DESC LIMIT 1',UUID(line['source_snapshot']['recipe']['product_id']))
                    if str(latest)!=line['prepared_recipe_id']:issues.append('Prepared ingredient recipe changed')
            if review['legacy']:
                source=next((s for s in sources if s['sourceType']==review['legacy']['source_type'] and s['sourceId']==review['legacy']['source_id']),None)
                if source is None or source['hash']!=review['legacy']['hash']:issues.append('Legacy source changed or was removed')
        except HTTPException as exc:issues.append(str(exc.detail))
        parents=[a for a in await ancestry(conn,row['id']) if a['id']!=row['id']]
        if parents and await ancestry_changed(conn,store,parents,sources):issues.append('Prepared ingredient ancestry changed; review producing recipes first')
        recipe['reviewIssues']=issues;recipe['reviewNeeded']=bool(issues);recipe_results.append(recipe)
    return serial({'enabled':True,'definitionsOnly':True,'products':[dict(x) for x in products],'profiles':[dict(x) for x in profiles],'recipes':recipe_results,
                   'rawItems':[dict(x) for x in raw],'legacySources':sources,'baseUnits':list(DIMENSIONS),'costPolicy':'Not selected; no batch costs written'})


async def preview(conn,store,body):
    product=await current_product(conn,store,body.product_version_id)
    output=await current_profile(conn,store,body.output_profile_id,body.product_version_id)
    prior=await conn.fetchrow('SELECT id,revision FROM prep_inventory.recipe_versions WHERE product_id=$1 ORDER BY revision DESC LIMIT 1',product['product_id'])
    if (prior['id'] if prior else None)!=body.predecessor_id:raise HTTPException(409,'Recipe version changed. Refresh before reviewing a replacement.')
    resolved=[];graph=[]
    for index,line in enumerate(body.lines,1):
        if line.source_kind=='raw':
            raw=await conn.fetchrow('''SELECT i.code,i.name,i.item_type,i.base_unit AS catalog_unit,i.pack_count,i.unit_qty,i.unit_uom,
                ib.base_unit FROM public.items i JOIN purchasing.item_bases ib ON ib.item_code=i.code AND ib.store_id=$1 WHERE i.code=$2 AND i.item_type='raw' ''',store,line.raw_item_code)
            if not raw:raise HTTPException(422,'Verify the purchased item fixed inventory unit before using it as a recipe ingredient')
            conversion(line.source_unit,raw['base_unit'],line.factor)
            value={'raw':dict(raw)};base=raw['base_unit'];prepared_version=None
        else:
            recipe=await conn.fetchrow('SELECT * FROM prep_inventory.recipe_versions WHERE id=$1 AND store_id=$2',line.prepared_recipe_id,store)
            if not recipe:raise HTTPException(422,'Prepared ingredient recipe is not approved at this location')
            latest=await conn.fetchval('SELECT id FROM prep_inventory.recipe_versions WHERE product_id=$1 ORDER BY revision DESC LIMIT 1',recipe['product_id'])
            if latest!=recipe['id']:raise HTTPException(409,'Prepared ingredient recipe changed. Review its current version.')
            version=await current_product(conn,store,recipe['product_version_id'])
            profile=await current_profile(conn,store,line.prepared_profile_id,version['id'])
            if line.source_unit!=profile['source_unit'] or line.factor!=profile['base_units_per_source_unit']:raise HTTPException(422,'Prepared ingredient quantity must use its selected verified unit')
            ancestors=await ancestry(conn,recipe['id'])
            if any(a['product_id']==product['product_id'] for a in ancestors):raise HTTPException(422,'Prepared recipe graph cannot return to its output identity')
            if await ancestry_changed(conn,store,ancestors,await legacy_sources(conn,store)):raise HTTPException(409,'Prepared ingredient ancestry changed. Review its producing recipes first.')
            graph.extend({'id':a['id'],'product_id':a['product_id']} for a in ancestors)
            value={'recipe':{k:recipe[k] for k in ('id','product_id','product_version_id','revision','usable_base_yield','review_hash')},'product':version,'profile':profile};base=version['base_unit'];prepared_version=version['id']
        resolved.append({'line_number':index,**line.model_dump(mode='json'),'prepared_product_version_id':prepared_version,'base_unit':base,'base_quantity':times(line.quantity,line.factor),'source_snapshot':value})
    legacy=None
    if body.legacy:
        candidate=next((s for s in await legacy_sources(conn,store) if s['sourceType']==body.legacy.source_type and s['sourceId']==str(body.legacy.source_id)),None)
        if candidate is None:raise HTTPException(422,'Legacy source is not at this location')
        if candidate['sourceType']=='dish' and candidate['snapshot']['header']['recipe_type']!='prep':raise HTTPException(422,'Menu dishes require a later sales mapping; select a prep recipe')
        if candidate['hash']!=body.legacy.expected_source_hash:raise HTTPException(409,'Legacy source changed. Refresh its complete source snapshot.')
        mapping=candidate['mapping']
        if mapping and mapping['product_id']!=product['product_id']:raise HTTPException(409,'Legacy source already maps to a different prepared identity')
        legacy={'source_type':candidate['sourceType'],'source_id':candidate['sourceId'],'snapshot':candidate['snapshot'],'hash':candidate['hash'],'predecessor_id':mapping['id'] if mapping else None}
    review=serial({'recipe':body.model_dump(mode='json'),'product':product,'outputProfile':output,'usableBaseYield':times(body.entered_yield,output['base_units_per_source_unit']),
                   'lines':resolved,'graph':sorted({str(a['id']):a for a in graph}.values(),key=lambda a:str(a['id'])),'legacy':legacy,'revision':prior['revision']+1 if prior else 1})
    return {'review':review,'reviewHash':fingerprint(review).hex(),'definitionsOnly':True}


async def replay(conn,table,store,key,digest):
    # table names are internal constants supplied below, never request values.
    row=await conn.fetchrow(f'SELECT * FROM prep_inventory.{table} WHERE request_key=$1',key)
    if row and (row['store_id']!=store or row['request_fingerprint']!=digest):raise HTTPException(409,'Review key already belongs to a different request')
    return dict(row) if row else None


def install_routes(router,context):
    async def ctx(request,store,write=False):
        actor,pool=await context(request,store,write)
        if not enabled():raise HTTPException(503,'Prepared inventory setup is awaiting enablement')
        return actor,pool

    @router.get('/{store_id}/prep-setup')
    async def get_setup(store_id:str,request:Request):
        _,pool=await ctx(request,store_id)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read',readonly=True):return await setup(conn,store_id)

    @router.post('/{store_id}/prep-products')
    async def save_product(store_id:str,body:ProductIn,request:Request,idempotency_key:UUID=Header(...)):
        actor,pool=await ctx(request,store_id,True);digest=fingerprint(body.model_dump(mode='json'))
        async with pool.acquire() as conn:
            async with conn.transaction():
                await ready(conn);await lock_store(conn,store_id)
                old=await replay(conn,'product_versions',store_id,idempotency_key,digest)
                if old:return serial({'product':old,'replayed':True})
                if body.product_id:
                    old=await current_product(conn,store_id,body.predecessor_id)
                    if old['product_id']!=body.product_id or old['base_unit']!=body.base_unit:raise HTTPException(409,'Prepared identity and fixed base unit cannot be changed by a version update')
                    product_id=body.product_id;revision=old['revision']+1
                else:
                    if await conn.fetchval('SELECT 1 FROM prep_inventory.products WHERE store_id=$1 AND identity_key=$2',store_id,body.name.casefold()):raise HTTPException(409,'This prepared identity already exists. Use its current version.')
                    product_id=await conn.fetchval('''INSERT INTO prep_inventory.products(store_id,identity_key,base_unit,created_by,request_key,request_fingerprint)
                        VALUES($1,$2,$3,$4,$5,$6) RETURNING id''',store_id,body.name.casefold(),body.base_unit,actor,idempotency_key,digest);revision=1
                saved=await conn.fetchrow('''INSERT INTO prep_inventory.product_versions(product_id,store_id,base_unit,revision,name,note,predecessor_id,confirmed_by,request_key,request_fingerprint)
                    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING *''',product_id,store_id,body.base_unit,revision,body.name,body.note,body.predecessor_id,actor,idempotency_key,digest)
                return serial({'product':dict(saved),'replayed':False})

    @router.get('/{store_id}/prep-products/{product_id}/history')
    async def product_history(store_id:str,product_id:UUID,request:Request):
        _,pool=await ctx(request,store_id)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read',readonly=True):
                await ready(conn)
                if not await conn.fetchval('SELECT 1 FROM prep_inventory.products WHERE id=$1 AND store_id=$2',product_id,store_id):raise HTTPException(404,'Prepared product not at this location')
                versions=await conn.fetch('SELECT * FROM prep_inventory.product_versions WHERE product_id=$1 ORDER BY revision',product_id)
                profiles=await conn.fetch('''SELECT p.* FROM prep_inventory.unit_profiles p JOIN prep_inventory.product_versions v ON v.id=p.product_version_id WHERE v.product_id=$1 ORDER BY p.confirmed_at,p.id''',product_id)
                recipes=await conn.fetch('SELECT * FROM prep_inventory.recipe_versions WHERE product_id=$1 ORDER BY revision',product_id)
                return serial({'productVersions':[dict(x) for x in versions],'unitProfiles':[dict(x) for x in profiles],'recipeVersions':[dict(x) for x in recipes]})

    @router.post('/{store_id}/prep-unit-profiles')
    async def save_profile(store_id:str,body:ProfileIn,request:Request,idempotency_key:UUID=Header(...)):
        actor,pool=await ctx(request,store_id,True);digest=fingerprint(body.model_dump(mode='json'))
        async with pool.acquire() as conn:
            async with conn.transaction():
                await ready(conn);await lock_store(conn,store_id)
                old=await replay(conn,'unit_profiles',store_id,idempotency_key,digest)
                if old:return serial({'profile':old,'replayed':True})
                product=await current_product(conn,store_id,body.product_version_id)
                if body.source_unit in DIMENSIONS:conversion(body.source_unit,product['base_unit'],body.factor)
                prior=await conn.fetchrow('SELECT id,revision FROM prep_inventory.unit_profiles WHERE product_version_id=$1 AND source_unit=$2 ORDER BY revision DESC LIMIT 1',body.product_version_id,body.source_unit)
                if (prior['id'] if prior else None)!=body.predecessor_id:raise HTTPException(409,'Prepared unit version changed. Refresh before saving another conversion.')
                saved=await conn.fetchrow('''INSERT INTO prep_inventory.unit_profiles(product_version_id,store_id,source_unit,base_units_per_source_unit,revision,predecessor_id,note,confirmed_by,request_key,request_fingerprint)
                    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING *''',body.product_version_id,store_id,body.source_unit,body.factor,prior['revision']+1 if prior else 1,body.predecessor_id,body.note,actor,idempotency_key,digest)
                return serial({'profile':dict(saved),'replayed':False})

    @router.post('/{store_id}/prep-recipes/preview')
    async def recipe_preview(store_id:str,body:RecipeIn,request:Request):
        _,pool=await ctx(request,store_id,True)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read',readonly=True):
                await ready(conn);return await preview(conn,store_id,body)

    @router.post('/{store_id}/prep-recipes')
    async def promote(store_id:str,body:PromotionIn,request:Request,idempotency_key:UUID=Header(...)):
        actor,pool=await ctx(request,store_id,True);digest=fingerprint(body.model_dump(mode='json'))
        async with pool.acquire() as conn:
            async with conn.transaction():
                await ready(conn);await lock_store(conn,store_id)
                old=await replay(conn,'recipe_versions',store_id,idempotency_key,digest)
                if old:return serial({'recipe':old,'replayed':True})
                # Legacy editors are not yet on the native store lock. Hold their tables
                # while verifying and capturing the reviewed source, including line deletes.
                await conn.execute('LOCK TABLE public.items,public.store_items,public.dishes,public.dish_lines,public.prep_items IN SHARE MODE')
                plan=await preview(conn,store_id,body.recipe)
                if plan['reviewHash']!=body.expected_review_hash:raise HTTPException(409,'Prep source or mapping changed. Review a fresh preview.')
                p=plan['review'];b=body.recipe;product=p['product']
                saved=await conn.fetchrow('''INSERT INTO prep_inventory.recipe_versions(product_id,product_version_id,store_id,revision,predecessor_id,output_profile_id,
                    entered_yield,usable_base_yield,method,note,review_snapshot,review_hash,request_key,request_fingerprint)
                    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14) RETURNING *''',UUID(product['product_id']),b.product_version_id,store_id,p['revision'],b.predecessor_id,b.output_profile_id,
                    b.entered_yield,Decimal(p['usableBaseYield']),b.method,b.note,p,bytes.fromhex(plan['reviewHash']),idempotency_key,digest)
                for line in p['lines']:
                    await conn.execute('''INSERT INTO prep_inventory.recipe_lines(recipe_version_id,store_id,line_number,source_kind,raw_item_code,prepared_recipe_id,
                        prepared_product_version_id,prepared_profile_id,entered_quantity,source_unit,base_unit,factor,base_quantity,source_snapshot,evidence)
                        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)''',saved['id'],store_id,line['line_number'],line['source_kind'],line['raw_item_code'],
                        UUID(line['prepared_recipe_id']) if line['prepared_recipe_id'] else None,UUID(line['prepared_product_version_id']) if line['prepared_product_version_id'] else None,
                        UUID(line['prepared_profile_id']) if line['prepared_profile_id'] else None,Decimal(line['quantity']),line['source_unit'],line['base_unit'],Decimal(line['factor']),Decimal(line['base_quantity']),line['source_snapshot'],line['evidence'])
                await conn.execute('INSERT INTO prep_inventory.promotion_decisions(recipe_version_id,store_id,review_hash,graph_snapshot,confirmed_by) VALUES($1,$2,$3,$4,$5)',saved['id'],store_id,bytes.fromhex(plan['reviewHash']),p['graph'],actor)
                if p['legacy']:
                    l=p['legacy']
                    await conn.execute('''INSERT INTO prep_inventory.legacy_crosswalks(store_id,source_type,source_id,product_id,recipe_version_id,predecessor_id,source_snapshot,source_hash,confirmed_by)
                        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)''',store_id,l['source_type'],UUID(l['source_id']),UUID(product['product_id']),saved['id'],UUID(l['predecessor_id']) if l['predecessor_id'] else None,l['snapshot'],bytes.fromhex(l['hash']),actor)
                return serial({'recipe':dict(saved),'replayed':False})
