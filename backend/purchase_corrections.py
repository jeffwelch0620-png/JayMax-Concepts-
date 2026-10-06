"""Review-first, immutable whole-invoice corrections in the native purchase ledger."""
from decimal import Decimal, localcontext
from uuid import UUID

import asyncpg
from fastapi import Header, HTTPException, Request
from pydantic import Field, field_validator

from purchase_api import (PostDocument, append_review_mappings, document_preview,
                          load_version, serial)
from purchase_parser import document_totals, fingerprint


class CorrectionReview(PostDocument):
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator('reason')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():raise ValueError('Explain the correction')
        return value


class ConfirmCorrection(CorrectionReview):
    expected_plan_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    expected_initial_batch_id: UUID
    expected_correction_id: UUID | None


async def require_corrections(conn):
    if not await conn.fetchval("SELECT to_regclass('purchasing.corrections') IS NOT NULL"):
        raise HTTPException(503,'Posted invoice correction setup has not been applied yet')


async def proposed_lines(conn, store, header, body):
    source={r['id']:dict(r) for r in await conn.fetch(
        'SELECT * FROM purchasing.document_lines WHERE document_version_id=$1',header['id'])}
    if len(body.lines)!=len(source) or {r.line_id for r in body.lines}!=set(source):
        raise HTTPException(422,'Confirm every source line exactly once')
    result=[]
    for r in sorted(body.lines,key=lambda x:str(x.line_id)):
        food=r.classification=='food'; movement=r.movement_kind; amount=source[r.line_id]['extended_amount_source']
        record_date=body.received_date if movement=='receipt' else r.movement_date
        quantity=r.received_quantity if food and movement in ('receipt','physical_return') else None
        factor=r.base_units_per_received_unit if food and movement in ('receipt','physical_return') else None
        if not food and movement!='no_inventory':raise HTTPException(422,'Non-food, tax and fee lines require no inventory movement')
        if food and movement!='no_inventory':
            if not r.item_code or not r.base_unit or not record_date:
                raise HTTPException(422,'Confirm the item, canonical unit and inventory date for every food movement')
        if food and movement=='no_inventory' and amount!=0:raise HTTPException(422,'Nonzero food cost requires an inventory disposition')
        if food and movement in ('receipt','physical_return'):
            if quantity is None or factor is None or factor<=0 or not r.received_unit:
                raise HTTPException(422,'Confirm quantity, received unit and positive conversion')
            if movement=='receipt' and (quantity<0 or amount<0) or movement=='physical_return' and (quantity>=0 or amount>0):
                raise HTTPException(422,'Receipt/return quantity and cost signs must agree')
        if food and movement=='price_credit':
            if amount>0 or r.received_quantity not in (None,0) or not r.original_line_id:
                raise HTTPException(422,'Price credit needs nonpositive cost, zero quantity and its original receipt')
            match=await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM purchasing.current_purchase_facts f
                JOIN purchasing.mapping_decisions m ON m.id=f.mapping_id WHERE f.store_id=$1 AND f.vendor_id=$2
                AND f.line_id=$3 AND f.item_code=$4 AND f.base_unit=$5 AND m.movement_kind='receipt')''',
                store,header['vendor_id'],r.original_line_id,r.item_code,r.base_unit)
            if not match:raise HTTPException(422,'Credit must reference the current matching receipt from this vendor and location')
        if food and r.item_code:
            item=await conn.fetchrow('''SELECT si.item_code,b.base_unit FROM public.store_items si
                LEFT JOIN purchasing.item_bases b ON b.store_id=si.store_id AND b.item_code=si.item_code
                WHERE si.store_id=$1 AND si.item_code=$2''',store,r.item_code)
            if item is None:raise HTTPException(422,'Item is not registered at this location')
            if item['base_unit'] and item['base_unit']!=r.base_unit:raise HTTPException(409,'Convert to the item’s fixed inventory unit')
        with localcontext() as ctx:
            ctx.prec=80
            base_quantity=quantity*factor if quantity is not None else Decimal(0)
        result.append({'line_id':r.line_id,'classification':r.classification,'movement_kind':movement,
            'item_code':r.item_code if food else None,'base_unit':r.base_unit if food else None,
            'received_quantity':quantity,'received_unit':r.received_unit if food else None,
            'base_units_per_received_unit':factor,
            'base_quantity':base_quantity,'inventory_cost_amount':amount if food else Decimal(0),
            'inventory_record_date':record_date if food and movement!='no_inventory' else None,
            'credit_original_line_id':r.original_line_id,'vendor_line_amount':amount,
            'description':source[r.line_id]['description_snapshot']})
    return source,result


async def build_plan(conn, store, version, body):
    await require_corrections(conn)
    header=await load_version(conn,store,version)
    if not header['posted_batch_id']:raise HTTPException(409,'Post an initial invoice before correcting it')
    latest=await conn.fetchval('SELECT max(revision) FROM purchasing.document_versions WHERE document_id=$1',header['document_id'])
    if header['revision']!=latest:raise HTTPException(409,'Review the latest captured source version')
    preview=await document_preview(conn,store,version)
    if preview['sourceErrors']:raise HTTPException(409,{'message':'Source needs review','reasons':preview['sourceErrors']})
    _,after=await proposed_lines(conn,store,header,body)
    before=[dict(r) for r in await conn.fetch('''SELECT m.line_id,m.id AS mapping_id,m.classification,m.movement_kind,
        m.item_code,m.base_unit,m.base_quantity,m.inventory_cost_amount,m.inventory_record_date,m.credit_original_line_id,
        m.received_quantity,m.received_unit,m.base_units_per_received_unit,
        l.extended_amount_source AS vendor_line_amount,l.description_snapshot AS description
        FROM purchasing.current_posting_lines p JOIN purchasing.mapping_decisions m ON m.id=p.mapping_id
        JOIN purchasing.document_lines l ON l.id=p.line_id WHERE p.initial_batch_id=$1 ORDER BY m.line_id''',header['posted_batch_id'])]
    relevant=('classification','movement_kind','item_code','base_unit','base_quantity','inventory_cost_amount',
              'inventory_record_date','credit_original_line_id','received_quantity','received_unit','base_units_per_received_unit')
    unchanged=header['posted_version_id']==version and all(
        {k:a[k] for k in relevant}=={k:b[k] for k in relevant} for a,b in zip(before,after)) and len(before)==len(after)
    dates=sorted({r['inventory_record_date'] for r in before+after if r['inventory_record_date'] is not None})
    affected=[dict(r) for r in await conn.fetch('''SELECT id,period_start,period_end_exclusive FROM actual_inventory.active_period_closures
        WHERE store_id=$1 AND EXISTS(SELECT 1 FROM unnest($2::date[]) d WHERE d>=period_start AND d<period_end_exclusive)
        ORDER BY period_start,id''',store,dates)]
    legacy=[dict(r) for r in await conn.fetch('''SELECT id,period_start,period_end FROM public.reporting_periods WHERE store_id=$1 AND status='closed'
        AND EXISTS(SELECT 1 FROM unnest($2::date[]) d WHERE d BETWEEN period_start AND period_end) ORDER BY period_start,id''',store,dates)]
    dependents=[dict(r) for r in await conn.fetch('''SELECT DISTINCT p.document_id,i.document_number,m.line_id,m.credit_original_line_id
        FROM purchasing.current_posting_lines p JOIN purchasing.mapping_decisions m ON m.id=p.mapping_id
        JOIN purchasing.document_identities i ON i.id=p.document_id WHERE p.document_id<>$1
        AND m.credit_original_line_id=ANY($2::uuid[]) ORDER BY p.document_id,m.line_id''',header['document_id'],[r['line_id'] for r in before])]
    old_header=await conn.fetchrow('SELECT d.* FROM purchasing.document_versions d WHERE id=$1',header['posted_version_id'])
    blocks=[]
    if unchanged:blocks.append('No inventory disposition or supplier source changed')
    if affected:blocks.append('Reopen the affected closed Actual Inventory periods and their later periods before correcting')
    if legacy:blocks.append('A legacy closed period requires separate reconciliation')
    if dependents:blocks.append('Linked credits or returns require reconciliation; this correction is held')
    # Include all requested notes/conversions/source identity, not just net amounts, in the review fingerprint.
    review=body.model_dump(include=set(CorrectionReview.model_fields),mode='python')
    review['lines']=sorted(review['lines'],key=lambda r:str(r['line_id']))
    plan=serial({'versionId':version,'documentId':header['document_id'],'initialBatchId':header['posted_batch_id'],
        'previousCorrectionId':header.get('current_correction_id'),'before':before,'after':after,'review':review,
        'affectedPeriods':affected,'legacyClosedPeriods':legacy,'linkedDocuments':dependents,'blocks':blocks,
        'sourceVersions':{'before':header['posted_version_id'],'after':version},
        'separateComponents':{'before':{k:old_header[k] for k in ('fees_source','tax_source','discount_source','delivery_adjustment_source')},
                              'after':{k:header[k] for k in ('fees_source','tax_source','discount_source','delivery_adjustment_source')}},
        'status':'held' if blocks else 'ready'})
    plan['planHash']=fingerprint(plan).hex()
    return plan


async def commit_correction(pool, store, actor, version, body, key):
    payload=body.model_dump(mode='python');payload['lines']=sorted(payload['lines'],key=lambda r:str(r['line_id']))
    digest=fingerprint(serial(payload))
    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_corrections(conn)
            header=await load_version(conn,store,version,lock=True)
            prior=await conn.fetchrow('SELECT * FROM purchasing.corrections WHERE idempotency_key=$1',key)
            if prior:
                if prior['initial_batch_id']==header['posted_batch_id'] and prior['request_fingerprint']==digest:return prior['id']
                raise HTTPException(409,'Retry key belongs to a different correction review')
            # Serialize with initial posting, credit validation, closing and reopening.
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext('purchase-invoice'),hashtext(concat_ws('|',$1::text,$2::text,$3::text)))",store,header['vendor_id'],header['document_number'])
            await conn.execute('INSERT INTO public.store_state(store_id) VALUES($1) ON CONFLICT DO NOTHING',store)
            await conn.fetchval('SELECT revision FROM public.store_state WHERE store_id=$1 FOR UPDATE',store)
            plan=await build_plan(conn,store,version,body)
            if plan['initialBatchId']!=str(body.expected_initial_batch_id) or plan['previousCorrectionId']!=serial(body.expected_correction_id) or plan['planHash']!=body.expected_plan_hash:
                raise HTTPException(409,'The invoice or period status changed; preview the correction again')
            if plan['status']!='ready':raise HTTPException(409,{'message':'Correction held','reasons':plan['blocks']})
            source,_=await proposed_lines(conn,store,header,body)
            await append_review_mappings(conn,store,actor,header,body,source)
            totals=document_totals(header,list(source.values()))
            revision=await conn.fetchval('SELECT coalesce(max(revision),0)+1 FROM purchasing.reconciliation_checks WHERE document_version_id=$1',version)
            await conn.execute('''INSERT INTO purchasing.reconciliation_checks
                (document_version_id,revision,line_total,expected_document_total,stated_document_total,status,component_explanation,confirmed_by)
                VALUES($1,$2,$3,$4,$5,'balanced',$6,$7)''',version,revision,totals['lineTotal'],totals['expectedTotal'],totals['statedTotal'],
                {'tax':'separate','fees':'separate','correctionPlanHash':plan['planHash']},actor)
            cid=await conn.fetchval('SELECT purchasing.correct_document($1,$2,$3,$4,$5,$6,$7,$8)',version,key,actor,digest,
                body.expected_initial_batch_id,body.expected_correction_id,plan,body.reason)
            sizes={r['polarity']:r['n'] for r in await conn.fetch('SELECT polarity,count(*) AS n FROM purchasing.correction_lines WHERE correction_id=$1 GROUP BY polarity',cid)}
            if sizes!={-1:len(plan['before']),1:len(plan['after'])}:raise HTTPException(500,'Correction read-back failed; transaction rolled back')
            await conn.execute('UPDATE public.store_state SET revision=revision+1,updated_at=now() WHERE store_id=$1',store)
            return cid


def install_routes(router, context):
    @router.post('/{store_id}/documents/{version_id}/correction-preview')
    async def preview(store_id:str,version_id:UUID,body:CorrectionReview,request:Request):
        _,pool=await context(request,store_id,True)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read',readonly=True):
                return await build_plan(conn,store_id,version_id,body)

    @router.post('/{store_id}/documents/{version_id}/correct')
    async def correct(store_id:str,version_id:UUID,body:ConfirmCorrection,request:Request,idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True)
        try:cid=await commit_correction(pool,store_id,actor,version_id,body,str(idempotency_key))
        except (asyncpg.CheckViolationError,asyncpg.ForeignKeyViolationError,asyncpg.UniqueViolationError,asyncpg.RaiseError) as exc:
            raise HTTPException(409,'Correction validation failed; no reversal or replacement was saved') from exc
        async with pool.acquire() as conn:
            correction=dict(await conn.fetchrow('SELECT * FROM purchasing.corrections WHERE id=$1',cid))
            current=not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM purchasing.corrections WHERE previous_correction_id=$1)',cid)
            document=await document_preview(conn,store_id,version_id)
        return serial({'correctionId':cid,'correction':correction,'isCurrent':current,'document':document})

    @router.get('/{store_id}/documents/{version_id}/corrections')
    async def history(store_id:str,version_id:UUID,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn:
            await require_corrections(conn);header=await load_version(conn,store_id,version_id)
            return serial([dict(r) for r in await conn.fetch('SELECT * FROM purchasing.corrections WHERE initial_batch_id=$1 ORDER BY corrected_at,id',header['posted_batch_id'])])
