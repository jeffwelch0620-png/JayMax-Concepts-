"""Store contact configuration keyed by supplier identity, independent of invoices."""
import os, re
from uuid import UUID, uuid4
from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import order_commands, catalog_mapping
from native_units import lock_store
from purchase_api import serial
from purchase_parser import fingerprint


def enabled():
    requested=os.getenv('SUPPLIER_CONTACTS_ENABLED','false').lower()=='true'
    if requested and not order_commands.enabled():raise HTTPException(503,'Supplier contacts require versioned order workflow')
    return requested


async def installed(conn):
    return await conn.fetchval("SELECT to_regclass('purchasing.store_supplier_contacts') IS NOT NULL")


async def ready(conn):
    if not enabled():raise HTTPException(503,'Supplier contact workflow is awaiting enablement')
    await order_commands.ready(conn)
    if not await installed(conn):raise HTTPException(503,'Supplier contact migration is awaiting enablement')


async def hold_legacy(conn):
    if enabled() or await installed(conn):raise HTTPException(409,'Use supplier contacts keyed by supplier ID; legacy name-based contacts and email lookups are held')


def version(request):
    raw=request.headers.get('if-match','').strip('"')
    if not raw:raise HTTPException(428,'Refresh the contact and supply its version; zero means no saved contact')
    if not raw.isdigit() or not 0<=int(raw)<2**63:raise HTTPException(422,'Supply a valid contact version')
    return int(raw)


class SaveContact(BaseModel):
    model_config=ConfigDict(extra='forbid')
    order_email:str=Field(max_length=320)
    expected_vendor_version:int=Field(ge=1,lt=2**63,strict=True)
    note:str=Field(min_length=1,max_length=2000)
    legacy_vendor:str|None=Field(default=None,min_length=1,max_length=200)
    verified:bool=Field(default=False,strict=True)

    @field_validator('order_email','note')
    @classmethod
    def clean(cls,value,info):
        value=value.strip()
        if info.field_name=='note' and not value:raise ValueError('Record the reason for this contact edit')
        if info.field_name=='order_email' and value:
            if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+",value):raise ValueError('Supply one conventional email address, or blank to clear')
            local,domain=value.split('@')
            if len(local)>64 or len(domain)>253 or any(len(label)>63 for label in domain.split('.')) or local.startswith('.') or local.endswith('.') or '..' in local:raise ValueError('Supply one conventional email address, or blank to clear')
        return value

    @model_validator(mode='after')
    def review(self):
        if self.legacy_vendor is not None and not self.verified:raise ValueError('Explicitly verify the legacy contact mapping')
        return self


async def contact(conn,store,vendor):
    row=await conn.fetchrow('SELECT * FROM purchasing.store_supplier_contacts WHERE store_id=$1 AND vendor_id=$2',store,vendor)
    return serial(dict(row)) if row else {'store_id':store,'vendor_id':vendor,'version':0,'order_email':'','event_id':None}


async def setup(conn,store):
    vendors=await conn.fetch('SELECT id,name,active,catalog_version FROM public.vendors ORDER BY name,id')
    contacts=await conn.fetch('SELECT * FROM purchasing.store_supplier_contacts WHERE store_id=$1',store)
    by_id={r['vendor_id']:serial(dict(r)) for r in contacts}
    legacy=await conn.fetch('''SELECT l.vendor,l.raw_record FROM purchasing.legacy_supplier_contacts l
        WHERE l.store_id=$1 AND NOT EXISTS(SELECT 1 FROM purchasing.legacy_contact_resolutions r WHERE r.store_id=l.store_id AND r.vendor=l.vendor) ORDER BY l.vendor''',store)
    return {'store_id':store,'contacts':[{**(by_id.get(v['id']) or {'store_id':store,'vendor_id':v['id'],'version':0,'order_email':'','event_id':None}),
        'vendor_name':v['name'],'vendor_active':v['active'],'vendor_version':v['catalog_version']} for v in vendors],
        'legacy_contacts':[dict(r) for r in legacy]}


async def save(pool,store,vendor,actor,body,key,expected):
    digest=fingerprint(serial({'store':store,'vendor':vendor,'actor':actor,'expected':expected,'body':body.model_dump()}))
    async with pool.acquire() as conn,conn.transaction():
        await ready(conn);await catalog_mapping.lock_catalog(conn);await lock_store(conn,store)
        prior=await conn.fetchrow('SELECT * FROM purchasing.supplier_contact_commands WHERE request_key=$1',key)
        if prior:
            if prior['request_fingerprint']!=digest:raise HTTPException(409,'Request key belongs to another contact edit')
            return {'request_key':str(key),'contact':prior['result_snapshot'],'current_contact':await contact(conn,store,vendor),'replayed':True}
        supplier=await conn.fetchrow('SELECT * FROM public.vendors WHERE id=$1',vendor)
        if not supplier:raise HTTPException(404,'Supplier identity was not found')
        if supplier['catalog_version']!=body.expected_vendor_version:raise HTTPException(409,'Supplier changed; refresh and review the contact identity')
        if not supplier['active']:raise HTTPException(409,'Supplier is inactive; review its status before editing contacts')
        current=await contact(conn,store,vendor)
        if current['version']!=expected:raise HTTPException(409,'Supplier contact changed; refresh its version and review your retained entry')
        if body.legacy_vendor is not None:
            legacy=await conn.fetchrow('SELECT * FROM purchasing.legacy_supplier_contacts WHERE store_id=$1 AND vendor=$2',store,body.legacy_vendor)
            if not legacy:raise HTTPException(404,'Preserved legacy contact was not found in this store')
            if await conn.fetchval('SELECT EXISTS(SELECT 1 FROM purchasing.legacy_contact_resolutions WHERE store_id=$1 AND vendor=$2)',store,body.legacy_vendor):
                raise HTTPException(409,'Legacy contact was already assigned; refresh the preserved records')
        event=uuid4();next_version=expected+1
        await conn.execute('''INSERT INTO purchasing.supplier_contact_events(id,store_id,vendor_id,version,order_email,actor,note,legacy_vendor)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8)''',event,store,vendor,next_version,body.order_email,actor,body.note,body.legacy_vendor)
        if expected:
            await conn.execute('UPDATE purchasing.store_supplier_contacts SET version=$3,order_email=$4,event_id=$5 WHERE store_id=$1 AND vendor_id=$2',store,vendor,next_version,body.order_email,event)
        else:
            await conn.execute('INSERT INTO purchasing.store_supplier_contacts(store_id,vendor_id,version,order_email,event_id) VALUES($1,$2,$3,$4,$5)',store,vendor,next_version,body.order_email,event)
        if body.legacy_vendor is not None:
            await conn.execute('INSERT INTO purchasing.legacy_contact_resolutions(store_id,vendor,event_id) VALUES($1,$2,$3)',store,body.legacy_vendor,event)
        saved=await contact(conn,store,vendor)
        await conn.execute('''INSERT INTO purchasing.supplier_contact_commands(request_key,store_id,vendor_id,actor,request_fingerprint,event_id,result_snapshot)
            VALUES($1,$2,$3,$4,$5,$6,$7)''',key,store,vendor,actor,digest,event,saved)
        return {'request_key':str(key),'contact':saved,'current_contact':saved,'replayed':False}


def install_routes(router,context):
    @router.get('/{store_id}/supplier-contacts')
    async def read_contacts(store_id:str,request:Request):
        actor,pool=await context(request,store_id)
        async with pool.acquire() as conn,conn.transaction(isolation='repeatable_read'):
            await ready(conn);return await setup(conn,store_id)

    @router.put('/{store_id}/supplier-contacts/{vendor_id}')
    async def save_contact(store_id:str,vendor_id:str,body:SaveContact,request:Request,idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True)
        return await save(pool,store_id,vendor_id,actor,body,idempotency_key,version(request))
