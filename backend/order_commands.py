"""Atomic, versioned purchasing intent; never creates stock or accounting facts."""
import os
from decimal import Decimal, localcontext, ROUND_HALF_UP
from typing import Literal
from uuid import UUID, uuid4
from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
import catalog_mapping
from native_units import lock_store
from purchase_api import serial
from purchase_parser import fingerprint


def enabled():
    requested=os.getenv('ORDER_WORKFLOW_ENABLED','false').lower()=='true'
    if requested and not catalog_mapping.enabled():raise HTTPException(503,'Order commands require shared native catalog setup')
    return requested


async def ready(conn):
    if not enabled():raise HTTPException(503,'Versioned order workflow is awaiting enablement')
    if not await conn.fetchval("SELECT to_regclass('purchasing.order_commands') IS NOT NULL"):
        raise HTTPException(503,'Order command migration is awaiting enablement')


async def hold_legacy(pool):
    if enabled() or await pool.fetchval("SELECT to_regclass('purchasing.order_commands') IS NOT NULL"):
        raise HTTPException(409,'Use the versioned order workflow. Legacy order and supplier-email writes are held.')


def version(request):
    raw=request.headers.get('if-match','').strip('"')
    if not raw:raise HTTPException(428,'Refresh the order and supply its version')
    if not raw.isdigit() or not 0<int(raw)<2**63:raise HTTPException(422,'Supply a valid positive order version')
    return int(raw)


class OrderLine(BaseModel):
    model_config=ConfigDict(extra='forbid')
    itemCode:str=Field(min_length=1,max_length=200)
    controlNumber:str=Field(min_length=1,max_length=100)
    name:str=Field(default='',max_length=500)
    vendorSku:str=Field(min_length=1,max_length=200)
    qty:Decimal=Field(gt=0,max_digits=28,decimal_places=12,allow_inf_nan=False)
    purchaseUnit:str=Field(min_length=1,max_length=40)
    unitCost:Decimal|None=Field(default=None,ge=0,max_digits=28,decimal_places=18,allow_inf_nan=False)


class Draft(BaseModel):
    model_config=ConfigDict(extra='forbid')
    vendor:str=Field(min_length=1,max_length=300)
    vendorId:str|None=Field(default=None,max_length=200)
    createdBy:str=Field(default='',max_length=200) # legacy display input; actor comes from the session
    note:str=Field(default='',max_length=2000)
    lines:list[OrderLine]=Field(default_factory=list,max_length=500)


class Transition(BaseModel):
    model_config=ConfigDict(extra='forbid')
    action:Literal['submit','approve','reject','reopen','send','archive','reorder']
    note:str=Field(default='',max_length=2000)

    @field_validator('note')
    @classmethod
    def strip_note(cls,value):return value.strip()


async def order(conn,store,ref):
    row=await conn.fetchrow('SELECT * FROM public.purchase_orders WHERE store_id=$1 AND ref=$2 FOR UPDATE',store,ref)
    if row is None or row['archived_at'] is not None:raise HTTPException(404,'Active order not found at this location')
    return row


async def result(conn,po_id):
    import server
    row=await conn.fetchrow('SELECT * FROM public.purchase_orders WHERE id=$1',po_id)
    lines=await conn.fetch('SELECT * FROM public.purchase_order_lines WHERE po_id=$1 ORDER BY position,id',po_id)
    return serial(server._pg_po_doc(row,lines))


async def content(conn,store,body):
    vendors=await conn.fetch('SELECT * FROM public.vendors WHERE active AND '+('id=$1' if body.vendorId else 'lower(name)=lower($1)'),body.vendorId or body.vendor)
    if len(vendors)!=1:raise HTTPException(422,'Choose one active registered supplier by identity')
    vendor=vendors[0];lines=[];seen=set()
    with localcontext() as ctx:
        ctx.prec=70
        for entry in body.lines:
            sku=await conn.fetchrow('''SELECT vi.*,i.name AS product_name,si.control_number FROM public.vendor_items vi
                JOIN purchasing.store_vendor_items s ON s.vendor_item_id=vi.id AND s.store_id=$1 AND s.available
                JOIN public.store_items si ON si.store_id=s.store_id AND si.item_code=s.item_code AND si.active AND si.order_enabled
                JOIN public.items i ON i.code=si.item_code AND i.item_type='raw'
                WHERE vi.vendor_id=$2 AND vi.vendor_sku=$3 AND vi.item_code=$4''',store,vendor['id'],entry.vendorSku,entry.itemCode)
            if sku is None:raise HTTPException(422,'Choose an available supplier SKU for an active purchased product here')
            if sku['purchase_unit']!=entry.purchaseUnit or sku['control_number']!=entry.controlNumber:
                raise HTTPException(409,'Product alias or supplier purchase unit changed; refresh and review the draft')
            if sku['id'] in seen:raise HTTPException(422,'Combine quantities for each supplier SKU into one order line')
            seen.add(sku['id'])
            extended=(entry.qty*entry.unitCost).quantize(Decimal('.01'),rounding=ROUND_HALF_UP) if entry.unitCost is not None else None
            lines.append({**entry.model_dump(),'name':sku['product_name'],'vendor_item_id':sku['id'],'extended':extended})
        total=sum((l['extended'] for l in lines),Decimal(0)) if all(l['extended'] is not None for l in lines) else None
        if total is not None and total>=Decimal('10000000000'):raise HTTPException(422,'Order estimate exceeds the supported total range')
    return vendor,lines,total


async def write_lines(conn,po_id,lines):
    await conn.execute('DELETE FROM public.purchase_order_lines WHERE po_id=$1',po_id)
    for pos,line in enumerate(lines):
        await conn.execute('''INSERT INTO public.purchase_order_lines(po_id,position,item_code,control_number,name,vendor_item_id,vendor_sku,
            qty,unit,unit_price,extended,received_qty) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,0)''',po_id,pos,line['itemCode'],
            line['controlNumber'],line['name'],line['vendor_item_id'],line['vendorSku'],line['qty'],line['purchaseUnit'],line['unitCost'],line['extended'])


async def execute(pool,store,actor,action,body,key,ref=None,expected=None):
    digest=fingerprint(serial({'store':store,'actor':actor,'action':action,'ref':ref,'expected':expected,'body':body.model_dump(mode='python')}))
    async with pool.acquire() as conn,conn.transaction():
        await ready(conn);await catalog_mapping.lock_catalog(conn);await lock_store(conn,store)
        prior=await conn.fetchrow('SELECT * FROM purchasing.order_commands WHERE request_key=$1',key)
        if prior:
            if prior['store_id']!=store or prior['actor']!=actor or prior['request_fingerprint']!=digest:raise HTTPException(409,'Command key belongs to a different order request')
            return {'order':prior['result_snapshot'],'current_order':await result(conn,prior['po_id']),'request_key':str(key),'replayed':True}
        po=None
        if ref:
            po=await order(conn,store,ref)
            if po['order_version']!=expected:raise HTTPException(409,'Order changed; refresh and review its current version')
        note=body.note
        if action=='reorder':
            import server
            previous=await result(conn,po['id'])
            body=Draft(vendor=po['vendor_name'],vendorId=po['vendor_id'],note=note or 'Reviewed reorder from '+ref,
                lines=[{k:l[k] for k in ('itemCode','controlNumber','name','vendorSku','qty','purchaseUnit','unitCost')} for l in previous['lines']])
        if action in ('create','edit','reorder'):
            if action=='edit' and po['status']!='draft':raise HTTPException(409,'Only a current draft can be edited')
            vendor,lines,total=await content(conn,store,body)
            if action=='edit':
                po_id=po['id']
                await conn.execute('UPDATE public.purchase_orders SET vendor_id=$2,vendor_name=$3,note=$4,total=$5 WHERE id=$1',po_id,vendor['id'],vendor['name'],body.note,total)
            else:
                po_id=await conn.fetchval('''INSERT INTO public.purchase_orders(store_id,ref,vendor_id,vendor_name,status,created_by,creator_actor,note,total,history)
                    VALUES($1,$2,$3,$4,'draft',$5,$5,$6,$7,$8) RETURNING id''',store,'po_'+uuid4().hex,vendor['id'],vendor['name'],actor,body.note,total,
                    [{'status':'draft','by':actor,'at':(await conn.fetchval('SELECT now()')).isoformat(),'note':'Reviewed reorder from '+ref if action=='reorder' else 'Created draft'}])
            await write_lines(conn,po_id,lines)
        else:
            allowed={'submit':('draft','pending'),'approve':('pending','approved'),'reject':('pending','rejected'),'reopen':('rejected','draft'),'send':('approved','sent')}
            po_id=po['id']
            if action=='archive':
                if po['status'] not in ('draft','rejected'):raise HTTPException(409,'Only drafts or rejected orders can be archived')
                await conn.execute('UPDATE public.purchase_orders SET archived_at=now() WHERE id=$1',po_id)
                next_status='archived'
            else:
                source,next_status=allowed[action]
                if po['status']!=source:raise HTTPException(409,'Order state changed; this transition is no longer available')
                if action in ('submit','approve','send'):
                    current=await result(conn,po_id)
                    if not current['lines']:raise HTTPException(422,'An order needs at least one reviewed line')
                    await content(conn,store,Draft(vendor=po['vendor_name'],vendorId=po['vendor_id'],lines=[{k:l[k] for k in ('itemCode','controlNumber','name','vendorSku','qty','purchaseUnit','unitCost')} for l in current['lines']]))
                if action=='approve':
                    if not po['creator_actor']:raise HTTPException(409,'Legacy creator identity is unverified; reopen/rebuild a reviewed draft before approval')
                    if po['creator_actor']==actor:raise HTTPException(403,'A different authenticated reviewer must approve this order')
                if action=='reject' and not note:raise HTTPException(422,'Record the reason for rejecting this order')
                await conn.execute('''UPDATE public.purchase_orders SET status=$2,
                    submitted_at=CASE WHEN $3='submit' THEN now() ELSE submitted_at END,
                    approved_at=CASE WHEN $3='approve' THEN now() ELSE approved_at END,
                    approved_by=CASE WHEN $3='approve' THEN $4 ELSE approved_by END,
                    rejected_reason=CASE WHEN $3='reject' THEN $5 WHEN $3='reopen' THEN NULL ELSE rejected_reason END,
                    sent_at=CASE WHEN $3='send' THEN now() ELSE sent_at END WHERE id=$1''',po_id,next_status,action,actor,note)
            await conn.execute("UPDATE public.purchase_orders SET history=history||jsonb_build_array(jsonb_build_object('status',$2::text,'by',$3::text,'note',$4::text,'at',now())) WHERE id=$1",po_id,next_status,actor,note)
        saved=await result(conn,po_id)
        await conn.execute('''INSERT INTO purchasing.order_commands(request_key,store_id,po_id,action,actor,request_fingerprint,result_snapshot)
            VALUES($1,$2,$3,$4,$5,$6,$7)''',key,store,po_id,action,actor,digest,saved)
        return {'order':saved,'current_order':saved,'request_key':str(key),'replayed':False}


def install_routes(router,context):
    @router.post('/{store_id}/order-drafts')
    async def create(store_id:str,body:Draft,request:Request,idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True)
        return await execute(pool,store_id,actor,'create',body,idempotency_key)

    @router.put('/{store_id}/order-drafts/{ref}')
    async def edit(store_id:str,ref:str,body:Draft,request:Request,idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True)
        return await execute(pool,store_id,actor,'edit',body,idempotency_key,ref,version(request))

    @router.post('/{store_id}/orders/{ref}/commands')
    async def transition(store_id:str,ref:str,body:Transition,request:Request,idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True)
        return await execute(pool,store_id,actor,body.action,body,idempotency_key,ref,version(request))
