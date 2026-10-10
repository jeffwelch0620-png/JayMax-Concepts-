"""Append reviewed PO comparisons after invoice corrections; never post inventory."""
from decimal import Decimal, Inexact, localcontext
from uuid import UUID

from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from native_order_receiving import ReceiptLine, expected_order, order, receipt_history
from native_units import lock_store
from purchase_api import document_preview, load_version, serial
from purchase_parser import fingerprint


class ReconciliationReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    document_version_id:UUID
    lines:list[ReceiptLine]=Field(max_length=50000)
    variances_reviewed:bool
    note:str=Field(min_length=1,max_length=2000)

    @field_validator('note')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('Explain this corrected-invoice order comparison')
        return value


class ConfirmReconciliation(ReconciliationReview):
    expected_plan_hash:str=Field(pattern=r'^[0-9a-f]{64}$')


async def ready(conn):
    if not await conn.fetchval("SELECT to_regclass('purchasing.po_receipt_reconciliations') IS NOT NULL"):
        raise HTTPException(503,'Order reconciliation setup is awaiting enablement')


def selected_receipt(history,receipt_id):
    found=next((r for r in history if r['id']==receipt_id),None)
    if found is None:raise HTTPException(404,'Delivery link not found on this order at this location')
    return found


async def make_plan(conn,store,ref,receipt_id,body):
    with localcontext() as ctx:
        ctx.prec=80;ctx.traps[Inexact]=True
        await ready(conn);po,lines=await order(conn,store,ref)
        history=await receipt_history(conn,po['id']);receipt=selected_receipt(history,receipt_id)
        header=await load_version(conn,store,body.document_version_id)
        if header['document_id']!=receipt['document_id']:
            raise HTTPException(422,'Reconcile the same originally linked invoice; it cannot move to another order or invoice')
        blocks=[]
        if po['status'] not in ('receiving','received'):blocks.append('Only a partially received or completed order can be reconciled')
        if not receipt['stale']:blocks.append('This invoice comparison is already current')
        if header['posted_version_id']!=body.document_version_id:blocks.append('Review the current posted invoice version')
        if header['vendor_id']!=po['vendor_id']:blocks.append('Supplier does not match the frozen order')
        if not body.variances_reviewed or any(not r.verified for r in body.lines):blocks.append('Review every corrected receipt line and all variances')
        ordered,frozen=await expected_order(conn,store,po,lines,history)
        source=[dict(r) for r in await conn.fetch('''SELECT p.line_id,p.mapping_id,m.item_code,m.base_unit,m.base_quantity,
            m.inventory_cost_amount,m.inventory_record_date,l.description_snapshot
            FROM purchasing.current_posting_lines p JOIN purchasing.mapping_decisions m ON m.id=p.mapping_id
            JOIN purchasing.document_lines l ON l.id=p.line_id
            WHERE p.document_version_id=$1 AND m.classification='food' AND m.movement_kind='receipt'
            ORDER BY l.line_ordinal''',body.document_version_id)]
        if len(body.lines)!=len(source) or {r.source_line_id for r in body.lines}!={r['line_id'] for r in source}:
            raise HTTPException(422,'Review every current purchased-food receipt line exactly once, including off-order extras')
        by_order={UUID(r['po_line_id']):r for r in ordered};chosen={r.source_line_id:r.po_line_id for r in body.lines}
        delivery=[]
        for row in source:
            target_id=chosen[row['line_id']];target=by_order.get(target_id)
            if target_id and (target is None or target['item_code']!=row['item_code'] or target['baseUnit']!=row['base_unit']):
                raise HTTPException(422,'Match corrected receipts to the same frozen purchased item and fixed unit, or retain them as extras')
            delivery.append(serial({'source_line_id':row['line_id'],'mapping_id':row['mapping_id'],'po_line_id':target_id,
                'unit_profile_id':target['unitProfileId'] if target else None,'item_code':row['item_code'],
                'description':row['description_snapshot'],'base_quantity':row['base_quantity'],'base_unit':row['base_unit'],
                'foodAmount':row['inventory_cost_amount'],'receivedDate':row['inventory_record_date']}))
        comparison=[]
        for row in ordered:
            def total(entries):return sum((Decimal(l['base_quantity']) for l in entries if l['po_line_id']==row['po_line_id']),Decimal(0))
            other=sum((total(h['reviewed_plan']['receiptLines']) for h in history if h['id']!=receipt_id),Decimal(0))
            old=total(receipt['reviewed_plan']['receiptLines']);new=total(delivery)
            comparison.append({**row,'previousReceivedBase':str(other),'previousDeliveryBase':str(old),
                'replacementDeliveryBase':str(new),'beforeReceivedBase':str(other+old),'receivedBase':str(other+new),
                'differenceBase':str(other+new-Decimal(row['orderedBaseQuantity']))})
        result=serial({'status':'held' if blocks else 'ready','blocks':blocks,'poId':po['id'],'poRef':ref,'storeId':store,
            'receiptId':receipt_id,'documentId':receipt['document_id'],'initialBatchId':receipt['initial_batch_id'],
            'sourceVersionId':body.document_version_id,'sourceCorrectionId':header.get('current_correction_id'),
            'previousReconciliationId':receipt['reconciliation_id'],'revision':receipt['reconciliation_revision']+1,
            'before':receipt['reviewed_plan']['receiptLines'],'receiptLines':delivery,'orderedRows':ordered,
            'orderHash':fingerprint(frozen),'comparison':comparison,'orderStatus':po['status'],
            'review':body.model_dump(mode='json'),'otherStaleReceiptIds':[h['id'] for h in history if h['id']!=receipt_id and h['stale']],
            'receiptStates':[{'id':h['id'],'planHash':h['plan_hash'],'stale':h['stale']} for h in history],
            'warnings':[] if delivery else ['The current invoice has no purchased-food receipts. This review removes the earlier delivery quantity from the order comparison only.']})
        result['planHash']=fingerprint(result).hex()
        return result


def install_routes(router,context):
    @router.get('/{store_id}/orders/{ref}/receipts/{receipt_id}/reconciliation-setup')
    async def setup(store_id:str,ref:str,receipt_id:UUID,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read',readonly=True):
                await ready(conn);po,lines=await order(conn,store_id,ref)
                history=await receipt_history(conn,po['id']);receipt=selected_receipt(history,receipt_id)
                header=await load_version(conn,store_id,receipt['source_version_id'])
                if header['posted_version_id'] is None:raise HTTPException(409,'Linked invoice no longer has a posted version')
                return serial({'order':po,'lines':lines,'receipt':receipt,'history':history,
                    'document':await document_preview(conn,store_id,header['posted_version_id'])})

    @router.post('/{store_id}/orders/{ref}/receipts/{receipt_id}/reconciliation-preview')
    async def preview(store_id:str,ref:str,receipt_id:UUID,body:ReconciliationReview,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read',readonly=True):
                return await make_plan(conn,store_id,ref,receipt_id,body)

    @router.post('/{store_id}/orders/{ref}/receipts/{receipt_id}/reconciliations')
    async def confirm(store_id:str,ref:str,receipt_id:UUID,body:ConfirmReconciliation,request:Request,idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True)
        digest=fingerprint(body.model_dump(mode='json'))
        review=ReconciliationReview(**body.model_dump(exclude={'expected_plan_hash'}))
        async with pool.acquire() as conn:
            async with conn.transaction():
                await ready(conn)
                # Use the same identity -> store -> order lock sequence as invoice/receipt writers.
                await load_version(conn,store_id,body.document_version_id,lock=True)
                await lock_store(conn,store_id);po,_=await order(conn,store_id,ref,lock=True)
                receipt=await conn.fetchrow('SELECT * FROM purchasing.po_receipts WHERE id=$1 AND po_id=$2 FOR UPDATE',receipt_id,po['id'])
                if receipt is None:raise HTTPException(404,'Delivery link not found on this order at this location')
                prior=await conn.fetchrow('SELECT * FROM purchasing.po_receipt_reconciliations WHERE request_key=$1',str(idempotency_key))
                if prior:
                    if prior['receipt_id']!=receipt_id or prior['request_fingerprint']!=digest:
                        raise HTTPException(409,'Reconciliation key belongs to another review')
                    return serial({'reconciliation':dict(prior),'replayed':True})
                try:
                    plan=await make_plan(conn,store_id,ref,receipt_id,review)
                except HTTPException as exc:
                    if exc.status_code==422:raise HTTPException(409,'Corrected receipt lines changed. Refresh and review the comparison again.') from exc
                    raise
                if plan['status']!='ready' or plan['planHash']!=body.expected_plan_hash:
                    raise HTTPException(409,'Invoice or order comparison changed or is held. Refresh and review it again.')
                saved=await conn.fetchrow('''INSERT INTO purchasing.po_receipt_reconciliations
                    (receipt_id,po_id,store_id,document_id,initial_batch_id,revision,previous_reconciliation_id,
                    source_version_id,source_correction_id,reviewed_plan,plan_hash,request_key,request_fingerprint,confirmed_by,note)
                    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15) RETURNING *''',receipt_id,po['id'],store_id,
                    receipt['document_id'],receipt['initial_batch_id'],plan['revision'],
                    UUID(plan['previousReconciliationId']) if plan['previousReconciliationId'] else None,body.document_version_id,
                    UUID(plan['sourceCorrectionId']) if plan['sourceCorrectionId'] else None,plan,bytes.fromhex(plan['planHash']),
                    str(idempotency_key),digest,actor,body.note)
                for line in plan['receiptLines']:
                    await conn.execute('''INSERT INTO purchasing.po_receipt_reconciliation_lines
                        (reconciliation_id,po_id,po_line_id,source_line_id,mapping_id,unit_profile_id,base_quantity,base_unit)
                        VALUES($1,$2,$3,$4,$5,$6,$7,$8)''',saved['id'],po['id'],UUID(line['po_line_id']) if line['po_line_id'] else None,
                        UUID(line['source_line_id']),UUID(line['mapping_id']),UUID(line['unit_profile_id']) if line['unit_profile_id'] else None,
                        Decimal(line['base_quantity']),line['base_unit'])
                await conn.execute('''UPDATE public.purchase_orders SET history=history||$2::jsonb WHERE id=$1''',po['id'],
                    [{'status':'receipt_reconciled','by':actor,'at':str(saved['confirmed_at']),'note':body.note,'receiptId':str(receipt_id),
                        'reconciliationId':str(saved['id']),'revision':plan['revision']}])
                await conn.execute('UPDATE public.store_state SET revision=revision+1,updated_at=now() WHERE store_id=$1',store_id)
                if await conn.fetchval('SELECT count(*) FROM purchasing.po_receipt_reconciliation_lines WHERE reconciliation_id=$1',saved['id'])!=len(plan['receiptLines']):
                    raise HTTPException(500,'Reconciliation read-back failed; transaction rolled back')
                return serial({'reconciliation':dict(saved),'replayed':False})
