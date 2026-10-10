"""Reviewed store planning prices. Never writes purchase or count facts."""
from decimal import Decimal, localcontext
from uuid import UUID
from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
import catalog_mapping
from native_units import profiles, lock_store
from purchase_api import serial
from purchase_parser import fingerprint


class AdoptPrice(BaseModel):
    model_config=ConfigDict(extra='forbid')
    line_id:UUID
    expected_plan_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    verified:bool
    note:str=Field(min_length=1,max_length=2000)

    @field_validator('note')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('Explain the planning price review')
        return value.strip()


async def ready(conn):
    if not catalog_mapping.enabled():raise HTTPException(404,'Shared catalog is not enabled')
    await catalog_mapping.ready(conn)
    if not await conn.fetchval("SELECT to_regclass('purchasing.supplier_price_events') IS NOT NULL"):
        raise HTTPException(503,'Supplier price history migration is awaiting enablement')


async def review(conn,store,sku,offset=0):
    await ready(conn)
    current=await conn.fetchrow('''SELECT s.*,vi.vendor_id,vi.vendor_sku,vi.purchase_unit,
        purchasing.supplier_pack(vi.id) AS pack_snapshot FROM purchasing.store_vendor_items s
        JOIN public.vendor_items vi ON vi.id=s.vendor_item_id WHERE s.store_id=$1 AND s.vendor_item_id=$2''',store,sku)
    if current is None:raise HTTPException(404,'Supplier product is not linked to this location')
    current=dict(current)
    event=await conn.fetchrow('SELECT * FROM purchasing.supplier_price_events WHERE id=$1',current['price_event_id'])
    current['effective_date']=event['effective_date'] if event else None
    current['source_stale']=bool(event and event['pack_snapshot']!=current['pack_snapshot'])
    if event and event['source']=='invoice':
        basis=event['basis_snapshot']
        current['source_stale'] |= not await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM purchasing.current_posting_lines
            WHERE line_id::text=$1 AND mapping_id::text=$2)''',basis['line_id'],basis['mapping_id'])
    history=[dict(r) for r in await conn.fetch('''SELECT * FROM purchasing.supplier_price_events
        WHERE store_id=$1 AND vendor_item_id=$2 ORDER BY event_sequence DESC OFFSET $3 LIMIT 101''',store,sku,offset)]
    profile=next((p for p in await profiles(conn,store) if p['profile_kind']=='purchase' and p['vendor_item_id']==sku),None)
    if event and event['source']=='invoice':
        used=event['basis_snapshot'].get('profile',{})
        current['source_stale'] |= not profile or profile['stale'] or str(profile['id'])!=used.get('id')
    lines=await conn.fetch('''SELECT pl.line_id,pl.mapping_id,pl.document_version_id,pl.correction_id,
        i.document_number,m.goods_received_date,m.base_quantity,m.base_unit,m.inventory_cost_amount,d.confirmed_currency
        FROM purchasing.current_posting_lines pl JOIN purchasing.document_identities i ON i.id=pl.document_id
        JOIN purchasing.document_versions d ON d.id=pl.document_version_id
        JOIN purchasing.document_lines l ON l.id=pl.line_id JOIN purchasing.mapping_decisions m ON m.id=pl.mapping_id
        WHERE i.store_id=$1 AND i.vendor_id=$2 AND l.vendor_sku_snapshot=$3 AND m.item_code=$4
        AND m.classification='food' AND m.movement_kind='receipt'
        ORDER BY m.goods_received_date DESC,pl.line_id LIMIT 100''',store,current['vendor_id'],current['vendor_sku'],current['item_code'])
    candidates=[]
    for row in lines:
        basis=dict(row);issues=[];price=None
        if not profile or profile['stale']:issues.append('Review the current physical purchase-unit conversion')
        elif profile['base_unit']!=row['base_unit']:issues.append('Receipt and purchase profile use different inventory units')
        if row['confirmed_currency']!='USD':issues.append('Only verified USD prices are supported')
        if row['base_quantity']<=0:issues.append('A positive received quantity is required')
        if row['goods_received_date'] is None:issues.append('Confirm the received date')
        elif current['price'] is not None and current['effective_date'] and row['goods_received_date']<current['effective_date']:
            issues.append('This receipt predates the current planning price')
        if event and event['source']=='invoice' and event['basis_snapshot'].get('line_id')==str(row['line_id']) and event['basis_snapshot'].get('mapping_id')==str(row['mapping_id']):
            if profile and event['basis_snapshot'].get('profile',{}).get('id')==str(profile['id']):issues.append('This receipt is already the current planning price')
        if not issues:
            with localcontext() as ctx:
                ctx.prec=50
                price=row['inventory_cost_amount']/row['base_quantity']*profile['base_units_per_source_unit']
        basis['profile']=serial(profile) if profile else None
        basis['current']=serial(current)
        basis['price']=price
        candidates.append({**dict(row),'price':price,'issues':issues,'basis':serial(basis),
            'plan_hash':fingerprint(serial(basis)).hex()})
    revision=await conn.fetchval('SELECT revision FROM public.store_state WHERE store_id=$1',store)
    return serial({'current':current,'history':history[:100],'has_more':len(history)>100,
                   'offset':offset,'candidates':candidates,'revision':revision or 0})


def install_routes(router,context):
    @router.get('/{store_id}/supplier-prices/{sku}')
    async def get_prices(store_id:str,sku:UUID,request:Request,offset:int=0):
        _,pool=await context(request,store_id)
        if offset<0:raise HTTPException(422,'Offset must be nonnegative')
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read',readonly=True):return await review(conn,store_id,sku,offset)

    @router.post('/{store_id}/supplier-prices/{sku}/adoptions')
    async def adopt(store_id:str,sku:UUID,body:AdoptPrice,request:Request,idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True)
        digest=fingerprint(body.model_dump(mode='json'))
        async with pool.acquire() as conn:
            async with conn.transaction():
                await ready(conn);await catalog_mapping.lock_catalog(conn);await lock_store(conn,store_id)
                prior=await conn.fetchrow('SELECT * FROM purchasing.supplier_price_events WHERE request_key=$1',str(idempotency_key))
                if prior:
                    if prior['store_id']!=store_id or prior['vendor_item_id']!=sku or prior['request_fingerprint']!=digest:
                        raise HTTPException(409,'Price review key belongs to a different request')
                    return serial({'event':dict(prior),'replayed':True,'revision':await conn.fetchval('SELECT revision FROM public.store_state WHERE store_id=$1',store_id)})
                if not body.verified:raise HTTPException(422,'Confirm the receipt, pack conversion and planning price')
                plan=await review(conn,store_id,sku)
                chosen=next((p for p in plan['candidates'] if p['line_id']==str(body.line_id)),None)
                if not chosen:raise HTTPException(409,'Receipt is no longer a current matching source; refresh the review')
                if chosen['issues']:raise HTTPException(409,chosen['issues'])
                if chosen['plan_hash']!=body.expected_plan_hash:raise HTTPException(409,'Price or receipt setup changed; refresh and review again')
                event=await conn.fetchrow('''INSERT INTO purchasing.supplier_price_events(store_id,vendor_item_id,item_code,price,
                    effective_date,source,actor,note,pack_snapshot,basis_snapshot,request_key,request_fingerprint)
                    VALUES($1,$2,$3,$4,$5::text::date,'invoice',$6,$7,$8,$9,$10,$11) RETURNING *''',
                    store_id,sku,plan['current']['item_code'],Decimal(chosen['price']),chosen['goods_received_date'],actor,body.note,
                    plan['current']['pack_snapshot'],chosen['basis'],str(idempotency_key),digest)
                await conn.execute("SELECT set_config('jmax.price_event',$1,true)",str(event['id']))
                await conn.execute('UPDATE purchasing.store_vendor_items SET price=$3 WHERE store_id=$1 AND vendor_item_id=$2',store_id,sku,event['price'])
                await conn.execute("SELECT set_config('jmax.price_event','',true)")
                revision=await conn.fetchval('UPDATE public.store_state SET revision=revision+1,updated_at=now() WHERE store_id=$1 RETURNING revision',store_id)
                return serial({'event':dict(event),'replayed':False,'revision':revision})
