"""PO comparisons link already posted purchases, never add purchases or stock."""
from decimal import Decimal, Inexact, localcontext
from uuid import UUID

import asyncpg
from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from native_units import lock_store, profiles, ready
from purchase_api import load_version, serial
from purchase_parser import fingerprint


class ReceiptLine(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source_line_id:UUID
    po_line_id:UUID|None
    verified:bool


class ReceiptReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    document_version_id:UUID
    lines:list[ReceiptLine]=Field(min_length=1,max_length=50000)
    complete_order:bool
    variances_reviewed:bool
    note:str=Field(min_length=1,max_length=2000)

    @field_validator('note')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('Explain the delivery and any shortages/overages')
        return value


class ConfirmReceipt(ReceiptReview):
    expected_plan_hash:str=Field(pattern=r'^[0-9a-f]{64}$')


async def order(conn,store,ref,lock=False):
    po=await conn.fetchrow('SELECT * FROM public.purchase_orders WHERE store_id=$1 AND ref=$2'+(' FOR UPDATE' if lock else ''),store,ref)
    if po is None:raise HTTPException(404,'Purchase order not found at this location')
    lines=await conn.fetch('SELECT * FROM public.purchase_order_lines WHERE po_id=$1 ORDER BY position,id',po['id'])
    return dict(po),[dict(r) for r in lines]


def order_facts(po,lines):
    return serial({'id':po['id'],'ref':po['ref'],'store_id':po['store_id'],'vendor_id':po['vendor_id'],
        'lines':[{k:r[k] for k in ('id','item_code','control_number','vendor_sku','qty','unit','unit_price','extended')} for r in lines]})


async def receipt_history(conn,po_id):
    effective=await conn.fetchval("SELECT to_regclass('purchasing.effective_po_receipts') IS NOT NULL")
    relation='purchasing.effective_po_receipts' if effective else 'purchasing.po_receipts'
    rows=await conn.fetch('''SELECT r.*, NOT EXISTS(SELECT 1 FROM purchasing.current_posting_lines p
        WHERE p.document_id=r.document_id AND p.document_version_id=r.source_version_id
        AND p.correction_id IS NOT DISTINCT FROM r.source_correction_id) AS stale
        FROM '''+relation+''' r WHERE po_id=$1 ORDER BY confirmed_at,id''',po_id)
    result=[dict(r) for r in rows]
    if effective:
        revisions=await conn.fetch('SELECT * FROM purchasing.po_receipt_reconciliations WHERE po_id=$1 ORDER BY receipt_id,revision',po_id)
        for r in result:r['reconciliations']=[dict(n) for n in revisions if n['receipt_id']==r['id']]
    return result


async def expected_order(conn,store,po,lines,history):
    frozen=order_facts(po,lines)
    if history:
        first=history[0]['reviewed_plan']
        if first['orderHash']!=fingerprint(frozen).hex():raise HTTPException(409,'Ordered item details changed; receipt reconciliation is required')
        return first['orderedRows'],frozen
    current=await profiles(conn,store);result=[]
    for line in lines:
        if not line['item_code']:raise HTTPException(409,'This order has an unmapped item. Reconcile its catalog item before receiving.')
        sku=await conn.fetchval('''SELECT id FROM public.vendor_items WHERE vendor_id=$1 AND vendor_sku=$2 AND item_code=$3''',
            po['vendor_id'],line['vendor_sku'],line['item_code'])
        profile=next((p for p in current if p['profile_kind']=='purchase' and p['vendor_item_id']==sku and p['item_code']==line['item_code'] and not p['stale']),None)
        if profile is None or profile['source_unit']!=line['unit']:
            raise HTTPException(409,'Confirm this order item’s physical purchase-unit conversion in Invoice Master before receiving.')
        qty=line['qty']
        if qty<0 or not qty.is_finite():raise HTTPException(409,'Ordered quantity needs reconciliation')
        result.append(serial({'po_line_id':line['id'],'item_code':line['item_code'],'name':line['name'],
            'orderedQuantity':qty,'orderUnit':line['unit'],'orderedBaseQuantity':qty*profile['base_units_per_source_unit'],
            'baseUnit':profile['base_unit'],'unitProfileId':profile['id'],'factor':profile['base_units_per_source_unit']}))
    return result,frozen


async def make_plan(conn,store,ref,body):
    with localcontext() as ctx:
        ctx.prec=80;ctx.traps[Inexact]=True
        await ready(conn);po,lines=await order(conn,store,ref)
        header=await load_version(conn,store,body.document_version_id)
        blocks=[];history=await receipt_history(conn,po['id'])
        if po['status'] not in ('sent','receiving'):blocks.append('Only sent or partially received orders can accept a delivery')
        if not po['vendor_id'] or po['vendor_id']!=header['vendor_id']:blocks.append('Supplier does not match the purchase order')
        if header['posted_version_id']!=body.document_version_id:blocks.append('Select the current posted invoice version')
        if header['document_type']!='invoice':blocks.append('Returns and credits use invoice review, not delivery receiving')
        if any(r['stale'] for r in history):blocks.append('An earlier linked invoice changed. Reconcile this order before linking another delivery.')
        if await conn.fetchval('SELECT EXISTS(SELECT 1 FROM purchasing.po_receipts WHERE document_id=$1)',header['document_id']):blocks.append('This invoice is already linked to an order')
        if not body.variances_reviewed or any(not r.verified for r in body.lines):blocks.append('Review the entire delivery and its shortages/overages')
        source=[dict(r) for r in await conn.fetch('''SELECT p.line_id,p.mapping_id,m.item_code,m.base_unit,m.base_quantity,m.inventory_cost_amount,
            m.inventory_record_date,l.description_snapshot FROM purchasing.current_posting_lines p
            JOIN purchasing.mapping_decisions m ON m.id=p.mapping_id JOIN purchasing.document_lines l ON l.id=p.line_id
            WHERE p.document_version_id=$1 AND m.classification='food' AND m.movement_kind='receipt' ORDER BY l.line_ordinal''',body.document_version_id)]
        if not source:blocks.append('This invoice has no current purchased-food receipts')
        if len(body.lines)!=len(source) or {r.source_line_id for r in body.lines}!={r['line_id'] for r in source}:
            raise HTTPException(422,'Confirm each purchased-food receipt line exactly once')
        ordered,frozen=await expected_order(conn,store,po,lines,history)
        by_order={UUID(r['po_line_id']):r for r in ordered};by_source={r.source_line_id:r for r in body.lines}
        delivery=[]
        for row in source:
            chosen=by_source[row['line_id']].po_line_id;target=by_order.get(chosen)
            if chosen and (target is None or target['item_code']!=row['item_code'] or target['baseUnit']!=row['base_unit']):
                raise HTTPException(422,'Match each receipt to the same purchased item and fixed inventory unit on this order')
            delivery.append(serial({'source_line_id':row['line_id'],'mapping_id':row['mapping_id'],'po_line_id':chosen,
                'unit_profile_id':target['unitProfileId'] if target else None,'item_code':row['item_code'],'description':row['description_snapshot'],
                'base_quantity':row['base_quantity'],'base_unit':row['base_unit'],'foodAmount':row['inventory_cost_amount'],
                'receivedDate':row['inventory_record_date']}))
        if not any(r['po_line_id'] for r in delivery):blocks.append('Match at least one invoice receipt to this order')
        comparison=[]
        for row in ordered:
            prior=sum((Decimal(l['base_quantity']) for h in history for l in h['reviewed_plan']['receiptLines'] if l['po_line_id']==row['po_line_id']),Decimal(0))
            received=prior+sum((Decimal(l['base_quantity']) for l in delivery if l['po_line_id']==row['po_line_id']),Decimal(0))
            comparison.append({**row,'previousReceivedBase':str(prior),'receivedBase':str(received),
                'differenceBase':str(received-Decimal(row['orderedBaseQuantity']))})
        result=serial({'status':'held' if blocks else 'ready','blocks':blocks,'poId':po['id'],'poRef':ref,'storeId':store,
            'documentId':header['document_id'],'sourceVersionId':body.document_version_id,'sourceCorrectionId':header.get('current_correction_id'),
            'initialBatchId':header['posted_batch_id'],'invoiceNumber':header['document_number'],'review':body.model_dump(mode='json'),
            'orderHash':fingerprint(frozen),'orderedRows':ordered,'receiptLines':delivery,'comparison':comparison,
            'previousReceiptIds':[r['id'] for r in history],'orderStatus':po['status']})
        result['planHash']=fingerprint(result).hex()
        return result


def install_routes(router,context):
    @router.get('/{store_id}/orders/{ref}/receipt-setup')
    async def get_setup(store_id:str,ref:str,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read',readonly=True):
                await ready(conn);po,lines=await order(conn,store_id,ref)
                invoices=await conn.fetch('''SELECT DISTINCT p.document_id,p.document_version_id,i.document_number
                    FROM purchasing.current_posting_lines p JOIN purchasing.document_identities i ON i.id=p.document_id
                    JOIN purchasing.mapping_decisions m ON m.id=p.mapping_id
                    WHERE i.store_id=$1 AND i.vendor_id=$2 AND i.document_type='invoice' AND m.classification='food'
                    AND m.movement_kind='receipt' AND NOT EXISTS(SELECT 1 FROM purchasing.po_receipts r WHERE r.document_id=i.id)
                    ORDER BY i.document_number,p.document_version_id''',store_id,po['vendor_id'])
                reconciliation_ready=await conn.fetchval("SELECT to_regclass('purchasing.po_receipt_reconciliations') IS NOT NULL")
                return serial({'order':po,'lines':lines,'history':await receipt_history(conn,po['id']),'invoices':[dict(r) for r in invoices],
                    'reconciliationReady':bool(reconciliation_ready)})

    @router.post('/{store_id}/orders/{ref}/receipt-preview')
    async def preview(store_id:str,ref:str,body:ReceiptReview,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read',readonly=True):return await make_plan(conn,store_id,ref,body)

    @router.post('/{store_id}/orders/{ref}/receipts')
    async def confirm(store_id:str,ref:str,body:ConfirmReceipt,request:Request,idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True)
        digest=fingerprint(body.model_dump(mode='json'));review=ReceiptReview(**body.model_dump(exclude={'expected_plan_hash'}))
        async with pool.acquire() as conn:
            async with conn.transaction():
                await ready(conn)
                await load_version(conn,store_id,body.document_version_id,lock=True)
                await lock_store(conn,store_id);po,_=await order(conn,store_id,ref,lock=True)
                prior=await conn.fetchrow('SELECT * FROM purchasing.po_receipts WHERE request_key=$1',str(idempotency_key))
                if prior:
                    if prior['po_id']!=po['id'] or prior['request_fingerprint']!=digest:raise HTTPException(409,'Receipt key belongs to a different review')
                    return serial({'receipt':dict(prior),'replayed':True})
                plan=await make_plan(conn,store_id,ref,review)
                if plan['status']!='ready' or plan['planHash']!=body.expected_plan_hash:raise HTTPException(409,'Receiving review changed or is held. Refresh the comparison.')
                saved=await conn.fetchrow('''INSERT INTO purchasing.po_receipts(po_id,store_id,document_id,source_version_id,
                    source_correction_id,initial_batch_id,reviewed_plan,plan_hash,complete_order,request_key,request_fingerprint,confirmed_by,note)
                    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13) RETURNING *''',po['id'],store_id,UUID(plan['documentId']),
                    body.document_version_id,UUID(plan['sourceCorrectionId']) if plan['sourceCorrectionId'] else None,
                    UUID(plan['initialBatchId']),plan,bytes.fromhex(plan['planHash']),body.complete_order,str(idempotency_key),digest,actor,body.note)
                for line in plan['receiptLines']:
                    await conn.execute('''INSERT INTO purchasing.po_receipt_lines(receipt_id,po_id,po_line_id,source_line_id,mapping_id,
                        unit_profile_id,base_quantity,base_unit) VALUES($1,$2,$3,$4,$5,$6,$7,$8)''',saved['id'],po['id'],
                        UUID(line['po_line_id']) if line['po_line_id'] else None,UUID(line['source_line_id']),UUID(line['mapping_id']),
                        UUID(line['unit_profile_id']) if line['unit_profile_id'] else None,Decimal(line['base_quantity']),line['base_unit'])
                await conn.execute('''UPDATE public.purchase_orders SET status=$2,received_at=CASE WHEN $3 THEN now() ELSE NULL END,
                    invoice_number=$4,receipt_match=$5,history=history||$6::jsonb WHERE id=$1''',po['id'],
                    'received' if body.complete_order else 'receiving',body.complete_order,plan['invoiceNumber'],
                    {'native':True,'receiptId':str(saved['id']),'invoiceNumber':plan['invoiceNumber']},
                    [{'status':'received' if body.complete_order else 'receiving','by':actor,'at':str(saved['confirmed_at']),'note':body.note}])
                await conn.execute('UPDATE public.store_state SET revision=revision+1,updated_at=now() WHERE store_id=$1',store_id)
                if await conn.fetchval('SELECT count(*) FROM purchasing.po_receipt_lines WHERE receipt_id=$1',saved['id'])!=len(plan['receiptLines']):
                    raise HTTPException(500,'Receipt read-back failed; transaction rolled back')
                return serial({'receipt':dict(saved),'replayed':False})

    from native_po_reconciliation import install_routes as install_reconciliation
    install_reconciliation(router,context)
