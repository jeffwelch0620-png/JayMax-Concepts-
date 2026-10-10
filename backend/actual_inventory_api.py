"""Track 1 physical counts and explicit-value Food Cost; no prep/sales inputs."""
import os
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal, localcontext, Inexact
from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from purchase_api import ALLOWED_UNITS, serial, enabled as purchases_enabled
from purchase_parser import fingerprint


def enabled():
    return (os.getenv('ACTUAL_INVENTORY_ENABLED', 'false').lower() == 'true'
            and purchases_enabled())

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ScopeItem(StrictModel):
    item_code: str = Field(min_length=1, max_length=150)
    base_unit: Literal['lb','oz','g','kg','fl_oz','ml','l','gal','each']
    location_notes: str = Field(min_length=1, max_length=2000)

    @field_validator('location_notes')
    @classmethod
    def locations(cls, value):
        if not value.strip():raise ValueError('Describe all raw inventory locations to include')
        return value.strip()


class ScopeInput(StrictModel):
    scope_kind: Literal['purchased_items_only']
    valuation_method: Literal['explicit_count_values']
    note: str = Field(min_length=1, max_length=2000)
    items: list[ScopeItem] = Field(min_length=1, max_length=10000)

    @field_validator('note')
    @classmethod
    def required_note(cls, value):
        if not value.strip():raise ValueError('A confirmation note is required')
        return value.strip()


class CountLine(StrictModel):
    item_code: str
    counted_quantity: Decimal | None = Field(None, ge=0, max_digits=28, decimal_places=10)
    counted_unit: str = Field(min_length=1, max_length=40)
    base_units_per_counted_unit: Decimal | None = Field(None, gt=0, max_digits=28, decimal_places=12)
    inventory_value: Decimal | None = Field(None, ge=0, max_digits=20, decimal_places=2)
    confirmed: bool = False
    note: str = Field('', max_length=2000)

    @field_validator('counted_unit')
    @classmethod
    def unit(cls, value):
        if not value.strip():raise ValueError('Describe the unit physically counted')
        return value.strip()

    @field_validator('counted_quantity','base_units_per_counted_unit','inventory_value')
    @classmethod
    def finite(cls, value):
        if value is not None and not value.is_finite():raise ValueError('Use a finite decimal')
        return value


class CountInput(StrictModel):
    scope_id: UUID
    count_date: date
    timing: Literal['before_receipts','after_receipts']
    note: str = Field(min_length=1, max_length=2000)
    corrects_snapshot_id: UUID | None = None
    lines: list[CountLine] = Field(min_length=1, max_length=10000)

    @field_validator('note')
    @classmethod
    def required_note(cls, value):
        if not value.strip():raise ValueError('A physical count note is required')
        return value.strip()


class CloseInput(StrictModel):
    opening_snapshot_id: UUID
    closing_snapshot_id: UUID
    expected_report_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    purchases_reviewed: Literal[True]
    counts_reviewed: Literal[True]
    acknowledge_overages: bool = False
    supersedes_closure_id: UUID | None = None
    opening_bridge_id: UUID | None = None


class ScopeBridgeInput(StrictModel):
    anchor_closure_id: UUID
    target_opening_id: UUID
    expected_plan_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    items_reviewed: Literal[True]
    note: str = Field(min_length=1, max_length=2000)

    @field_validator('note')
    @classmethod
    def note_required(cls, value):
        if not value.strip():raise ValueError('A scope handoff note is required')
        return value.strip()


class ReopenInput(StrictModel):
    first_closure_id: UUID
    expected_plan_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    affected_periods_reviewed: Literal[True]
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator('reason')
    @classmethod
    def required_reason(cls, value):
        if not value.strip():raise ValueError('A correction reason is required')
        return value.strip()


async def lock_store(conn, store_id):
    await conn.execute('INSERT INTO public.store_state(store_id) VALUES($1) ON CONFLICT(store_id) DO NOTHING',store_id)
    await conn.fetchval('SELECT revision FROM public.store_state WHERE store_id=$1 FOR UPDATE',store_id)


def request_hash(body, sort_key=None):
    payload=serial(body.model_dump())
    if sort_key:payload[sort_key]=sorted(payload[sort_key],key=lambda r:r['item_code'])
    return fingerprint(payload)


async def prior_request(conn, table, store_id, key, digest):
    assert table in ('scopes','count_snapshots','period_closures','reopen_events','scope_bridges')
    prior=await conn.fetchrow(f'SELECT * FROM actual_inventory.{table} WHERE request_key=$1',key)
    if prior:
        if prior['store_id']!=store_id or prior['request_fingerprint']!=digest:
            raise HTTPException(409,'This request key was used for a different record. Check the saved outcome before retrying.')
        return prior['id']
    return None


async def get_scope(conn, store_id, scope_id=None):
    header=await conn.fetchrow('''SELECT * FROM actual_inventory.scopes WHERE store_id=$1
        AND ($2::uuid IS NULL OR id=$2) ORDER BY revision DESC LIMIT 1''',store_id,scope_id)
    if header is None:
        if scope_id:raise HTTPException(404,'Count scope not found at this location')
        return None
    items=await conn.fetch('SELECT * FROM actual_inventory.scope_items WHERE scope_id=$1 ORDER BY item_code',header['id'])
    return {'header':dict(header),'items':[dict(r) for r in items]}


async def configure_scope(pool, store_id, actor, body, key):
    digest=request_hash(body,'items')
    async with pool.acquire() as conn:
        async with conn.transaction():
            await lock_store(conn,store_id)
            prior=await prior_request(conn,'scopes',store_id,key,digest)
            if prior:return prior
            codes=[i.item_code for i in body.items]
            if len(set(codes))!=len(codes):raise HTTPException(422,'Include each purchased inventory item exactly once')
            records=await conn.fetch('''SELECT i.code,i.name,i.item_type FROM public.items i
                JOIN public.store_items si ON si.item_code=i.code WHERE si.store_id=$1 AND i.code=ANY($2::text[])''',store_id,codes)
            by_code={r['code']:r for r in records}
            if set(by_code)!=set(codes) or any(r['item_type']!='raw' for r in records):
                raise HTTPException(422,'Track 1 scope must use purchased raw inventory items registered at this location')
            revision=await conn.fetchval('SELECT coalesce(max(revision),0)+1 FROM actual_inventory.scopes WHERE store_id=$1',store_id)
            scope_id=await conn.fetchval('''INSERT INTO actual_inventory.scopes
                (store_id,revision,scope_kind,valuation_method,note,request_key,request_fingerprint,confirmed_by)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id''',store_id,revision,body.scope_kind,body.valuation_method,body.note,key,digest,actor)
            for item in sorted(body.items,key=lambda i:i.item_code):
                await conn.execute('''INSERT INTO purchasing.item_bases(store_id,item_code,base_unit) VALUES($1,$2,$3)
                    ON CONFLICT(store_id,item_code) DO NOTHING''',store_id,item.item_code,item.base_unit)
                base=await conn.fetchval('SELECT base_unit FROM purchasing.item_bases WHERE store_id=$1 AND item_code=$2',store_id,item.item_code)
                if base!=item.base_unit:raise HTTPException(409,f'{item.item_code} already uses {base}. Inventory units cannot be silently changed.')
                await conn.execute('''INSERT INTO actual_inventory.scope_items
                    (scope_id,store_id,item_code,base_unit,name_snapshot,location_notes) VALUES($1,$2,$3,$4,$5,$6)''',
                    scope_id,store_id,item.item_code,item.base_unit,by_code[item.item_code]['name'],item.location_notes)
            await conn.execute('UPDATE public.store_state SET revision=revision+1,updated_at=now() WHERE store_id=$1',store_id)
            return scope_id


async def get_count(conn, store_id, snapshot_id):
    header=await conn.fetchrow('SELECT * FROM actual_inventory.count_snapshots WHERE id=$1 AND store_id=$2',snapshot_id,store_id)
    if header is None:raise HTTPException(404,'Physical count not found at this location')
    lines=await conn.fetch('SELECT * FROM actual_inventory.count_lines WHERE snapshot_id=$1 ORDER BY item_code',snapshot_id)
    return {'header':dict(header),'lines':[dict(r) for r in lines],
            'scope':await get_scope(conn,store_id,header['scope_id'])}


@asynccontextmanager
async def count_connection(pool, conn):
    if conn is not None:
        yield conn
    else:
        async with pool.acquire() as acquired:
            yield acquired


async def save_count(pool, store_id, actor, body, key, *, conn=None):
    digest=request_hash(body,'lines')
    async with count_connection(pool, conn) as conn:
        async with conn.transaction():
            await lock_store(conn,store_id)
            prior=await prior_request(conn,'count_snapshots',store_id,key,digest)
            if prior:return prior
            scope=await get_scope(conn,store_id,body.scope_id)
            if body.corrects_snapshot_id:
                previous=await get_count(conn,store_id,body.corrects_snapshot_id)
                if previous['header']['scope_id']!=body.scope_id:raise HTTPException(422,'A recount must keep the same scope')
                if previous['header']['count_date']!=body.count_date or previous['header']['timing']!=body.timing:
                    raise HTTPException(422,'A recount must keep the original physical date and receipt timing')
                if await conn.fetchval('SELECT EXISTS(SELECT 1 FROM actual_inventory.count_snapshots WHERE corrects_snapshot_id=$1)',body.corrects_snapshot_id):
                    raise HTTPException(409,'This count already has a recount; correct the latest replacement')
                if await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM actual_inventory.active_period_closures
                    WHERE opening_snapshot_id=$1 OR closing_snapshot_id=$1)''',body.corrects_snapshot_id):
                    raise HTTPException(409,'Reopen every active closed period using this count before correcting it')
                if await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM actual_inventory.active_scope_bridges
                    WHERE old_closing_snapshot_id=$1 OR new_opening_snapshot_id=$1)''',body.corrects_snapshot_id):
                    raise HTTPException(409,'Reopen the scope handoff anchor and later periods before correcting this count')
            members={r['item_code']:r for r in scope['items']}
            if len(body.lines)!=len(members) or {r.item_code for r in body.lines}!=set(members):
                raise HTTPException(422,'Include every item in the physical count scope exactly once; leave uncounted values blank')
            complete=True
            for line in body.lines:
                if line.counted_quantity is not None and line.base_units_per_counted_unit is None:
                    raise HTTPException(422,'A measured count needs a verified conversion to inventory units')
                if line.inventory_value is not None and line.counted_quantity is None:
                    raise HTTPException(422,'Inventory value needs a measured quantity')
                if line.counted_quantity==0 and line.inventory_value not in (None,0):
                    raise HTTPException(422,'A zero physical count must have zero inventory value')
                if line.confirmed and (line.counted_quantity is None or line.inventory_value is None or not line.note.strip()):
                    raise HTTPException(422,'Confirm the measured quantity, explicit value and note for every completed line')
                complete=complete and line.confirmed
            snapshot_id=await conn.fetchval('''INSERT INTO actual_inventory.count_snapshots
                (store_id,scope_id,count_date,timing,status,note,corrects_snapshot_id,request_key,request_fingerprint,counted_by)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING id''',store_id,body.scope_id,body.count_date,body.timing,
                'complete' if complete else 'incomplete',body.note,body.corrects_snapshot_id,key,digest,actor)
            await conn.executemany('''INSERT INTO actual_inventory.count_lines
                (snapshot_id,scope_id,store_id,item_code,base_unit,counted_quantity,counted_unit,
                 base_units_per_counted_unit,inventory_value,confirmed,note) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)''',
                [(snapshot_id,body.scope_id,store_id,l.item_code,members[l.item_code]['base_unit'],l.counted_quantity,
                  l.counted_unit,l.base_units_per_counted_unit,l.inventory_value,l.confirmed,l.note) for l in body.lines])
            if await conn.fetchval('SELECT count(*) FROM actual_inventory.count_lines WHERE snapshot_id=$1',snapshot_id)!=len(members):
                raise HTTPException(500,'Count read-back failed; transaction rolled back')
            await conn.execute('UPDATE public.store_state SET revision=revision+1,updated_at=now() WHERE store_id=$1',store_id)
            return snapshot_id


async def period_report(conn, store_id, opening_id, closing_id):
    opening=await get_count(conn,store_id,opening_id);closing=await get_count(conn,store_id,closing_id)
    o,c=opening['header'],closing['header']
    if o['scope_id']!=c['scope_id']:raise HTTPException(409,'Opening and closing counts must use the same scope version')
    if c['boundary_date']<=o['boundary_date']:raise HTTPException(422,'Closing count must follow the opening count receipt boundary')
    if await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM actual_inventory.count_snapshots
         WHERE corrects_snapshot_id=ANY($1::uuid[]))''',[opening_id,closing_id]):
        raise HTTPException(409,'A selected count has a newer recount; use the replacement snapshot')
    scope=await get_scope(conn,store_id,o['scope_id'])
    replacement=await conn.fetchval('''SELECT id FROM actual_inventory.pending_reclosures
        WHERE store_id=$1 AND period_start=$2 AND period_end_exclusive=$3''',store_id,o['boundary_date'],c['boundary_date'])
    bridge=await conn.fetchrow('''SELECT id,plan_snapshot FROM actual_inventory.active_scope_bridges
        WHERE store_id=$1 AND new_opening_snapshot_id=$2''',store_id,opening_id)
    purchases=[dict(r) for r in await conn.fetch('''SELECT f.*,m.movement_kind FROM purchasing.actual_purchase_facts f
        JOIN purchasing.mapping_decisions m ON m.id=f.mapping_id
        WHERE f.store_id=$1 AND f.inventory_record_date>=$2 AND f.inventory_record_date<$3 ORDER BY f.line_id,f.mapping_id,to_jsonb(f)->>'fact_id' ''',
        store_id,o['boundary_date'],c['boundary_date'])]
    ob={r['item_code']:r for r in opening['lines']};cb={r['item_code']:r for r in closing['lines']}
    members={r['item_code'] for r in scope['items']};errors=[];warnings=[];rows=[]
    if o['status']!='complete' or c['status']!='complete':errors.append('Both physical counts require confirmed quantities and explicit values for every scope item')
    # Exact reversal pairs remain in the audit but no longer assert active item scope.
    mapping_balances={}
    for r in purchases:
        mapping_balances[r['mapping_id']]=mapping_balances.get(r['mapping_id'],0)+(-1 if r.get('fact_kind')=='reversal' else 1)
    outside=sorted({r['item_code'] for r in purchases if mapping_balances[r['mapping_id']]>0}-members)
    if outside:errors.append('Food purchases outside the selected count scope: '+', '.join(outside))
    with localcontext() as ctx:
        ctx.prec=80;ctx.traps[Inexact]=True
        net_cost=sum((p['inventory_cost_amount'] for p in purchases),Decimal(0))
        for item in scope['items']:
            code=item['item_code'];a=ob.get(code);b=cb.get(code);pp=[p for p in purchases if p['item_code']==code]
            if any(p['base_unit']!=item['base_unit'] for p in pp):errors.append(f'Inventory unit mismatch for {code}')
            quantity=sum((p['base_quantity'] for p in pp),Decimal(0));cost=sum((p['inventory_cost_amount'] for p in pp),Decimal(0))
            quantities=(a is not None and b is not None and a['confirmed'] and b['confirmed']
                        and a['base_quantity'] is not None and b['base_quantity'] is not None)
            values=quantities and a['confirmed'] and b['confirmed'] and a['inventory_value'] is not None and b['inventory_value'] is not None
            usage=a['base_quantity']+quantity-b['base_quantity'] if quantities else None
            food_cost=a['inventory_value']+cost-b['inventory_value'] if values else None
            if not values:errors.append(f'Missing confirmed count or explicit value: {code}')
            if usage is not None and usage<0:warnings.append(f'Physical overage for {code}: closing quantity exceeds opening plus purchases')
            if food_cost is not None and food_cost<0:warnings.append(f'Negative actual Food Cost for {code}: review count values and credits')
            rows.append({'itemCode':code,'name':item['name_snapshot'],'baseUnit':item['base_unit'],
                'openingQuantity':a['base_quantity'] if a else None,'netPurchaseQuantity':quantity,'closingQuantity':b['base_quantity'] if b else None,
                'actualUsage':usage,'openingValue':a['inventory_value'] if a else None,'netPurchaseCost':cost,
                'closingValue':b['inventory_value'] if b else None,'actualFoodCost':food_cost,'confirmed':bool(values)})
        complete=not errors
        result=serial({'storeId':store_id,'scopeId':o['scope_id'],'scopeKind':'purchased_items_only','valuationMethod':'explicit_count_values',
            'supersedesClosureId':replacement,
            'openingBridgeId':bridge['id'] if bridge else None,'openingScopeHandoff':bridge['plan_snapshot'] if bridge else None,
            'openingSnapshotId':opening_id,'closingSnapshotId':closing_id,'receivedFrom':o['boundary_date'],'receivedBefore':c['boundary_date'],
            'openingCountDate':o['count_date'],'closingCountDate':c['count_date'],'openingTiming':o['timing'],'closingTiming':c['timing'],
            'status':'complete' if complete else 'incomplete','errors':sorted(set(errors)),'warnings':sorted(set(warnings)),
            'netPurchaseCost':net_cost,'openingValue':sum((r['openingValue'] for r in rows),Decimal(0)) if complete else None,
            'closingValue':sum((r['closingValue'] for r in rows),Decimal(0)) if complete else None,
            'actualFoodCost':sum((r['actualFoodCost'] for r in rows),Decimal(0)) if complete else None,'rows':rows,'purchaseLines':purchases})
    result['reportHash']=fingerprint(result).hex()
    return result


async def close_period(pool, store_id, actor, body, key):
    digest=request_hash(body)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await lock_store(conn,store_id)
            prior=await prior_request(conn,'period_closures',store_id,key,digest)
            if prior:return prior
            report=await period_report(conn,store_id,body.opening_snapshot_id,body.closing_snapshot_id)
            if report['status']!='complete':raise HTTPException(409,{'message':'Physical counts or values are incomplete','reasons':report['errors']})
            if report['reportHash']!=body.expected_report_hash:raise HTTPException(409,'Purchases or counts changed after preview. Refresh and review the new report before closing.')
            if report['supersedesClosureId']!=(str(body.supersedes_closure_id) if body.supersedes_closure_id else None):
                raise HTTPException(409,'Confirm the linked replacement shown by the refreshed report')
            if report['openingBridgeId']!=(str(body.opening_bridge_id) if body.opening_bridge_id else None):
                raise HTTPException(409,'Confirm the scope handoff shown by the refreshed report')
            if report['warnings'] and not body.acknowledge_overages:raise HTTPException(409,'Review and explicitly acknowledge the quantity/value overages before closing')
            closure_id=await conn.fetchval('''INSERT INTO actual_inventory.period_closures
                (store_id,opening_snapshot_id,closing_snapshot_id,period_start,period_end_exclusive,
                 report_snapshot,request_key,request_fingerprint,closed_by,supersedes_closure_id,opening_bridge_id)
                 VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING id''',
                store_id,body.opening_snapshot_id,body.closing_snapshot_id,date.fromisoformat(report['receivedFrom']),
                date.fromisoformat(report['receivedBefore']),report,key,digest,actor,body.supersedes_closure_id,body.opening_bridge_id)
            saved=await conn.fetchval('SELECT report_snapshot FROM actual_inventory.period_closures WHERE id=$1',closure_id)
            if saved!=report:raise HTTPException(500,'Closed report read-back failed; transaction rolled back')
            await conn.execute('UPDATE public.store_state SET revision=revision+1,updated_at=now() WHERE store_id=$1',store_id)
            return closure_id


async def reopen_plan(conn, store_id, first_id):
    first=await conn.fetchrow('SELECT * FROM actual_inventory.active_period_closures WHERE store_id=$1 AND id=$2',store_id,first_id)
    if first is None:raise HTTPException(409,'That period is no longer active at this location; refresh closed history')
    rows=await conn.fetch('''SELECT * FROM actual_inventory.active_period_closures
        WHERE store_id=$1 AND period_start>=$2 ORDER BY period_start,id''',store_id,first['period_start'])
    plan=serial({'storeId':store_id,'firstClosureId':first_id,'affectedPeriods':[
        {'id':r['id'],'periodStart':r['period_start'],'receivedBefore':r['period_end_exclusive'],
         'openingSnapshotId':r['opening_snapshot_id'],'closingSnapshotId':r['closing_snapshot_id'],
         'actualFoodCost':r['report_snapshot']['actualFoodCost'],'originalReportHash':r['report_snapshot']['reportHash']} for r in rows]})
    plan['planHash']=fingerprint(plan).hex()
    return plan


async def reopen_periods(pool, store_id, actor, body, key):
    digest=request_hash(body)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await lock_store(conn,store_id)
            prior=await prior_request(conn,'reopen_events',store_id,key,digest)
            if prior:return prior
            plan=await reopen_plan(conn,store_id,body.first_closure_id)
            if plan['planHash']!=body.expected_plan_hash:
                raise HTTPException(409,'Closed periods changed after the correction preview. Refresh and review every affected period.')
            event_id=await conn.fetchval('''INSERT INTO actual_inventory.reopen_events
                (store_id,first_closure_id,closure_ids,reason,plan_snapshot,request_key,request_fingerprint,reopened_by)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id''',store_id,body.first_closure_id,
                [UUID(r['id']) for r in plan['affectedPeriods']],body.reason,plan,key,digest,actor)
            saved=await conn.fetchval('SELECT plan_snapshot FROM actual_inventory.reopen_events WHERE id=$1',event_id)
            if saved!=plan:raise HTTPException(500,'Correction read-back failed; transaction rolled back')
            await conn.execute('UPDATE public.store_state SET revision=revision+1,updated_at=now() WHERE store_id=$1',store_id)
            return event_id


async def scope_bridge_plan(conn, store_id, anchor_id, target_id):
    anchor=await conn.fetchrow('SELECT * FROM actual_inventory.active_period_closures WHERE id=$1 AND store_id=$2',anchor_id,store_id)
    if anchor is None:raise HTTPException(409,'The scope handoff anchor is no longer active here; refresh period history')
    old=await get_count(conn,store_id,anchor['closing_snapshot_id']);new=await get_count(conn,store_id,target_id)
    a,b=old['header'],new['header'];errors=[];rows=[]
    if await conn.fetchval('SELECT EXISTS(SELECT 1 FROM actual_inventory.active_period_closures WHERE store_id=$1 AND period_end_exclusive>$2)',store_id,anchor['period_end_exclusive']):
        errors.append('Use the latest active closed period; reopen a historical suffix before changing its handoff')
    if await conn.fetchval('SELECT EXISTS(SELECT 1 FROM actual_inventory.active_scope_bridges WHERE anchor_closure_id=$1)',anchor_id):
        errors.append('This anchor already has an accepted handoff; reopen it before replacing the handoff')
    if a['status']!='complete' or b['status']!='complete':errors.append('Both counts need confirmed quantities and explicit values for every item')
    if a['count_date']!=b['count_date'] or a['timing']!=b['timing']:errors.append('Both counts must describe the same physical date and receipt timing')
    if new['scope']['header']['revision']<=old['scope']['header']['revision']:errors.append('Choose a newer purchased-item scope version')
    if await conn.fetchval('SELECT EXISTS(SELECT 1 FROM actual_inventory.count_snapshots WHERE corrects_snapshot_id=ANY($1::uuid[]))',[a['id'],b['id']]):
        errors.append('Use the latest linked recounts')
    pending=await conn.fetchrow('SELECT * FROM actual_inventory.pending_reclosures WHERE store_id=$1 ORDER BY period_start,id LIMIT 1',store_id)
    if pending and (pending['period_start']!=anchor['period_end_exclusive'] or not await conn.fetchval(
        'SELECT actual_inventory.count_descends_from($1,$2)',target_id,pending['opening_snapshot_id'])):
        errors.append('Finish older reopened periods; only rebuild the handoff needed by the next replacement')
    ob={r['item_code']:r for r in old['lines']};nb={r['item_code']:r for r in new['lines']}
    old_members={r['item_code']:r for r in old['scope']['items']};new_members={r['item_code']:r for r in new['scope']['items']}
    if set(ob)!=set(old_members) or set(nb)!=set(new_members):errors.append('Both counts must include their complete scope')
    for code in sorted(set(old_members)|set(new_members)):
        before=ob.get(code);after=nb.get(code);kind='carried' if before and after else 'added' if after else 'removed'
        valid=lambda line:line is not None and line['confirmed'] and line['base_quantity'] is not None and line['inventory_value'] is not None
        if (code in old_members and not valid(before)) or (code in new_members and not valid(after)):
            errors.append(f'{code}: physical quantity and explicit value must be confirmed')
        elif kind=='carried' and (before['base_unit']!=after['base_unit'] or before['base_quantity']!=after['base_quantity'] or before['inventory_value']!=after['inventory_value']):
            errors.append(f'{code}: carry the exact measured quantity and confirmed value; use linked corrections for differences')
        elif kind=='added' and (after['base_quantity']!=0 or after['inventory_value']!=0):
            errors.append(f'{code}: an added item needs an explicitly confirmed zero opening balance; reconcile existing stock first')
        elif kind=='removed' and (before['base_quantity']!=0 or before['inventory_value']!=0):
            errors.append(f'{code}: keep this item in scope until both its measured quantity and value are zero')
        item=new_members.get(code) or old_members[code]
        rows.append({'itemCode':code,'name':item['name_snapshot'],'change':kind,'baseUnit':item['base_unit'],
            'oldQuantity':before['base_quantity'] if before else None,'newQuantity':after['base_quantity'] if after else None,
            'oldValue':before['inventory_value'] if before else None,'newValue':after['inventory_value'] if after else None,
            'oldLocations':old_members.get(code,{}).get('location_notes'),'newLocations':new_members.get(code,{}).get('location_notes')})
    with localcontext() as ctx:
        ctx.prec=80;ctx.traps[Inexact]=True
        old_value=sum((r['inventory_value'] for r in old['lines']),Decimal(0)) if all(valid(r) for r in old['lines']) else None
        new_value=sum((r['inventory_value'] for r in new['lines']),Decimal(0)) if all(valid(r) for r in new['lines']) else None
    result=serial({'storeId':store_id,'anchorClosureId':anchor_id,'oldClosingSnapshotId':a['id'],'newOpeningSnapshotId':target_id,
        'countDate':a['count_date'],'timing':a['timing'],'boundaryDate':a['boundary_date'],
        'oldScopeRevision':old['scope']['header']['revision'],'newScopeRevision':new['scope']['header']['revision'],
        'status':'ready' if not errors else 'held','errors':sorted(set(errors)),'rows':rows,
        'oldValue':old_value,'newValue':new_value,'oldCount':old,'newCount':new,
        'pendingReplacementId':pending['id'] if pending else None})
    result['planHash']=fingerprint(result).hex()
    return result


async def accept_scope_bridge(pool, store_id, actor, body, key):
    digest=request_hash(body)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await lock_store(conn,store_id)
            prior=await prior_request(conn,'scope_bridges',store_id,key,digest)
            if prior:return prior
            plan=await scope_bridge_plan(conn,store_id,body.anchor_closure_id,body.target_opening_id)
            if plan['status']!='ready':raise HTTPException(409,{'message':'Scope handoff needs reconciliation','reasons':plan['errors']})
            if plan['planHash']!=body.expected_plan_hash:raise HTTPException(409,'Scope handoff changed after preview. Refresh and review the quantities and values.')
            bridge_id=await conn.fetchval('''INSERT INTO actual_inventory.scope_bridges
                (store_id,anchor_closure_id,old_closing_snapshot_id,new_opening_snapshot_id,note,plan_snapshot,request_key,request_fingerprint,confirmed_by)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id''',store_id,body.anchor_closure_id,
                UUID(plan['oldClosingSnapshotId']),body.target_opening_id,body.note,plan,key,digest,actor)
            if await conn.fetchval('SELECT plan_snapshot FROM actual_inventory.scope_bridges WHERE id=$1',bridge_id)!=plan:
                raise HTTPException(500,'Scope handoff read-back failed; transaction rolled back')
            await conn.execute('UPDATE public.store_state SET revision=revision+1,updated_at=now() WHERE store_id=$1',store_id)
            return bridge_id


def create_router(pool_factory, store_check, authorize):
    router=APIRouter(prefix='/api/pg/actual-inventory')

    async def context(request,store_id,write=False):
        store_check(store_id);actor=authorize(request,store_id,write)
        if not enabled():raise HTTPException(503,'Actual inventory is awaiting enablement')
        pool=pool_factory()
        async with pool.acquire() as conn:
            if not await conn.fetchval("SELECT to_regclass('actual_inventory.scope_bridges') IS NOT NULL"):
                raise HTTPException(503,'Actual inventory setup has not been applied')
        return actor,pool

    @router.get('/{store_id}/setup')
    async def setup(store_id:str,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn:
            items=await conn.fetch('''SELECT i.code,i.name,ib.base_unit,si.storage_area FROM public.items i
                JOIN public.store_items si ON si.item_code=i.code AND si.store_id=$1
                LEFT JOIN purchasing.item_bases ib ON ib.item_code=i.code AND ib.store_id=si.store_id
                WHERE i.item_type='raw' ORDER BY i.name,i.code''',store_id)
            scopes=await conn.fetch('SELECT * FROM actual_inventory.scopes WHERE store_id=$1 ORDER BY revision DESC',store_id)
            unit_profiles=[]
            if await conn.fetchval("SELECT to_regclass('purchasing.unit_profiles') IS NOT NULL"):
                from native_units import profiles
                unit_profiles=[p for p in await profiles(conn,store_id) if p['profile_kind']=='count' and not p['stale']]
            return serial({'scope':await get_scope(conn,store_id),'scopes':[dict(r) for r in scopes],
                           'items':[dict(r) for r in items],'unitProfiles':unit_profiles,'baseUnits':list(ALLOWED_UNITS)})

    @router.get('/{store_id}/scopes/{scope_id}')
    async def scope_detail(store_id:str,scope_id:UUID,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn:return serial(await get_scope(conn,store_id,scope_id))

    @router.post('/{store_id}/scope')
    async def scope(store_id:str,request:Request,body:ScopeInput,idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True)
        scope_id=await configure_scope(pool,store_id,actor,body,idempotency_key)
        async with pool.acquire() as conn:return serial(await get_scope(conn,store_id,scope_id))

    @router.get('/{store_id}/counts')
    async def counts(store_id:str,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn:return serial([dict(r) for r in await conn.fetch('''SELECT c.*,s.revision AS scope_revision
            FROM actual_inventory.count_snapshots c JOIN actual_inventory.scopes s ON s.id=c.scope_id
            WHERE c.store_id=$1 ORDER BY c.boundary_date DESC,c.recorded_at DESC''',store_id)])

    @router.get('/{store_id}/counts/{snapshot_id}')
    async def count(store_id:str,snapshot_id:UUID,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn:return serial(await get_count(conn,store_id,snapshot_id))

    @router.post('/{store_id}/counts')
    async def capture_count(store_id:str,request:Request,body:CountInput,idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True)
        try:snapshot_id=await save_count(pool,store_id,actor,body,idempotency_key)
        except (asyncpg.UniqueViolationError,asyncpg.RaiseError) as exc:
            raise HTTPException(409,'Count correction conflicts with its history or an active closed period') from exc
        async with pool.acquire() as conn:return serial(await get_count(conn,store_id,snapshot_id))

    @router.get('/{store_id}/report')
    async def report(store_id:str,request:Request,opening:UUID,closing:UUID):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read',readonly=True):return await period_report(conn,store_id,opening,closing)

    @router.post('/{store_id}/close')
    async def close(store_id:str,request:Request,body:CloseInput,idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True)
        try:closure_id=await close_period(pool,store_id,actor,body,idempotency_key)
        except (asyncpg.UniqueViolationError,asyncpg.RaiseError) as exc:
            raise HTTPException(409,'Period cannot be closed: replace the oldest reopened period, preserve count lineage and check count continuity') from exc
        async with pool.acquire() as conn:
            row=await conn.fetchrow('''SELECT c.*,EXISTS(SELECT 1 FROM actual_inventory.active_period_closures active WHERE active.id=c.id) AS active
                FROM actual_inventory.period_closures c WHERE c.id=$1 AND c.store_id=$2''',closure_id,store_id)
            return serial({'status':'closed' if row['active'] else 'historical','closure':dict(row)})

    @router.get('/{store_id}/closed-periods')
    async def closed(store_id:str,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn:return serial([dict(r) for r in await conn.fetch('''SELECT c.*,
            CASE WHEN replacement.id IS NOT NULL THEN 'superseded'
                 WHEN e.id IS NOT NULL THEN 'reopened' ELSE 'closed' END AS period_status,
            replacement.id AS replacement_closure_id,e.id AS reopen_event_id,e.reason AS reopen_reason,e.reopened_by,e.reopened_at
            FROM actual_inventory.period_closures c
            LEFT JOIN actual_inventory.period_closures replacement ON replacement.supersedes_closure_id=c.id
            LEFT JOIN actual_inventory.reopen_events e ON e.store_id=c.store_id AND c.id=ANY(e.closure_ids)
            WHERE c.store_id=$1 ORDER BY c.period_end_exclusive DESC,c.closed_at DESC''',store_id)])

    @router.get('/{store_id}/reopen-preview/{closure_id}')
    async def preview_reopen(store_id:str,closure_id:UUID,request:Request):
        _,pool=await context(request,store_id,True)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read',readonly=True):return await reopen_plan(conn,store_id,closure_id)

    @router.post('/{store_id}/reopen')
    async def reopen(store_id:str,request:Request,body:ReopenInput,idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True)
        try:event_id=await reopen_periods(pool,store_id,actor,body,idempotency_key)
        except (asyncpg.UniqueViolationError,asyncpg.RaiseError,asyncpg.NoDataFoundError) as exc:
            raise HTTPException(409,'Correction conflicts with the current closed-period chain; refresh the preview') from exc
        async with pool.acquire() as conn:
            row=await conn.fetchrow('SELECT * FROM actual_inventory.reopen_events WHERE id=$1 AND store_id=$2',event_id,store_id)
            return serial({'status':'reopened','event':dict(row)})

    @router.get('/{store_id}/scope-handoff-preview/{closure_id}')
    async def preview_scope_handoff(store_id:str,closure_id:UUID,target_count:UUID,request:Request):
        _,pool=await context(request,store_id,True)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read',readonly=True):return await scope_bridge_plan(conn,store_id,closure_id,target_count)

    @router.post('/{store_id}/scope-handoffs')
    async def scope_handoff(store_id:str,request:Request,body:ScopeBridgeInput,idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True)
        try:bridge_id=await accept_scope_bridge(pool,store_id,actor,body,idempotency_key)
        except (asyncpg.UniqueViolationError,asyncpg.RaiseError,asyncpg.NoDataFoundError) as exc:
            raise HTTPException(409,'Scope handoff conflicts with count history or active periods; refresh the preview') from exc
        async with pool.acquire() as conn:
            row=await conn.fetchrow('''SELECT b.*,EXISTS(SELECT 1 FROM actual_inventory.active_scope_bridges active WHERE active.id=b.id) AS active
                FROM actual_inventory.scope_bridges b WHERE b.id=$1 AND b.store_id=$2''',bridge_id,store_id)
            return serial({'status':'accepted' if row['active'] else 'historical','bridge':dict(row)})

    @router.get('/{store_id}/scope-handoffs')
    async def scope_handoff_history(store_id:str,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn:return serial([dict(r) for r in await conn.fetch('''SELECT b.*,
            EXISTS(SELECT 1 FROM actual_inventory.active_scope_bridges active WHERE active.id=b.id) AS active
            FROM actual_inventory.scope_bridges b WHERE store_id=$1 ORDER BY confirmed_at DESC''',store_id)])

    return router
