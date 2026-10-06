"""Retained manual source records feed the existing immutable purchase review.

No OCR, guessed units, inferred zero totals, or automatic inventory posting.
"""
import json
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import File, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from purchase_parser import FIELD_MAP, fingerprint, typed

VERSION = 'manual-document-v1'
TYPES = {s['target']: s['type'] for s in FIELD_MAP}


class ExtraField(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label: str = Field(max_length=200)
    value: str = Field(max_length=10000)


class ManualLine(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fields: dict[str, str] = Field(default_factory=dict, max_length=100)
    extra_fields: list[ExtraField] = Field(default_factory=list, max_length=200)


class ManualRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')
    vendor_id: str = Field(min_length=1, max_length=100)
    document_type: Literal['invoice', 'credit']
    documents: dict[str, str] = Field(max_length=100)
    parties: dict[str, dict[str, str]] = Field(default_factory=dict, max_length=5)
    lines: list[ManualLine] = Field(min_length=1, max_length=1000)
    extra_fields: list[ExtraField] = Field(default_factory=list, max_length=500)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=20)
    verified_source: Literal[True]
    evidence_note: str = Field(min_length=1, max_length=2000)


def project_record(body, vendor_name):
    """String inputs remain in original JSON even when typing fails."""
    errors = []
    def project(fields, prefix):
        result = {}
        for name, value in fields.items():
            kind = TYPES.get(f'{prefix}.{name}')
            if kind is None:
                errors.append(f'Unrecognized mapped field {prefix}.{name}; use additional source fields')
                continue
            try:
                # Bound arithmetic without losing the original submitted string.
                parsed = typed(value, kind)
                if kind == 'numeric' and parsed is not None and (len(parsed.as_tuple().digits)>28 or parsed.as_tuple().exponent < -12):
                    raise ValueError('Decimal is outside supported precision')
                result[name] = parsed
            except (ValueError, ArithmeticError):
                result[name] = None
                errors.append(f'Invalid source field {prefix}.{name}')
        return result
    header = project(body.documents, 'documents')
    parties = {role: project(fields, f'parties.{role}') for role, fields in body.parties.items()
               if role in ('customer','bill_to','ship_to','remit_to','ship_from')}
    if len(parties)!=len(body.parties): errors.append('Unrecognized address role')
    number = (header.get('document_number') or '').strip()
    branch = (header.get('vendor_branch_reference') or '').strip()
    customer = (header.get('customer_number') or '').strip()
    account = (header.get('account_number') or '').strip()
    if not header.get('invoice_date'): errors.append('Missing supplier invoice / receipt date')
    if not body.evidence_note.strip(): errors.append('Explain the source and any unstated identity fields')
    if body.vendor_id in ('pfg','us_foods') and (not branch or not customer):
        errors.append('PFG / US Foods need their actual branch and customer identity to match CSV records')
    if header.get('document_type_raw') and header['document_type_raw'].strip().lower() not in (
            body.document_type, 'credit memo' if body.document_type=='credit' else 'invoice'):
        errors.append('Source document type disagrees with the selected type')
    header['document_type_raw'] = body.document_type
    lines = [{'ordinal': i, 'sourceOrdinal': i, 'fields': project(line.fields,'lines'), 'errors': []}
             for i,line in enumerate(body.lines,1)]
    raw = body.model_dump(mode='json')
    raw['attachment_ids'] = sorted(set(raw['attachment_ids']))
    result = {'headers':['Entered source line'], 'rows':[{'ordinal':i,'values':[json.dumps(line,ensure_ascii=False)],'errors':[]}
              for i,line in enumerate(raw['lines'],1)], 'errors':[], 'documents':[],
              'vendor':'Manual source record', 'encoding':'utf-8', 'parserVersion':VERSION}
    if not number:
        result['errors'] = ['Missing invoice / receipt number. Source retained; supply a traceable source reference.']
    else:
        result['documents'] = [{'identity':(body.vendor_id,branch,json.dumps([customer,account],separators=(',',':')),body.document_type,number),
            'header':header,'parties':parties,'lines':lines,'fingerprint':fingerprint(raw),
            'errors':sorted(set(errors)),'vendor':vendor_name}]
    return raw, result


def install_routes(router, context):
    import purchase_api as purchases

    async def ready(pool):
        async with pool.acquire() as conn:
            if not await conn.fetchval("SELECT to_regclass('purchasing.manual_attachments') IS NOT NULL"):
                raise HTTPException(503,'Manual purchase setup is awaiting enablement')

    @router.get('/{store_id}/vendors')
    async def vendors(store_id:str,request:Request):
        _,pool=await context(request,store_id)
        await ready(pool)
        async with pool.acquire() as conn:
            return [dict(r) for r in await conn.fetch('SELECT id,name FROM public.vendors WHERE active ORDER BY name,id')]

    @router.post('/{store_id}/sources')
    async def source(store_id:str,request:Request,file:UploadFile=File(...),idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True)
        await ready(pool)
        original=await file.read(purchases.MAX_SOURCE_BYTES+1)
        if not original or len(original)>purchases.MAX_SOURCE_BYTES:
            raise HTTPException(413,'Select a nonempty source document no larger than 12 MB')
        file_id=await purchases.capture_source(pool,store_id,actor,original,Path(file.filename or 'receipt').name,
            file.content_type or 'application/octet-stream',str(idempotency_key))
        return await purchases.file_preview(pool,store_id,file_id)

    @router.post('/{store_id}/manual-records')
    async def record(store_id:str,body:ManualRecord,request:Request,idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True)
        await ready(pool)
        async with pool.acquire() as conn:
            vendor_name=await conn.fetchval('SELECT name FROM public.vendors WHERE id=$1 AND active',body.vendor_id)
            if vendor_name is None: raise HTTPException(422,'Select a registered active supplier')
            for file_id in set(body.attachment_ids):
                if not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM purchasing.import_files WHERE id=$1 AND store_id=$2)',file_id,store_id):
                    raise HTTPException(422,'An attached source is not retained at this location')
        raw,projection=project_record(body,vendor_name)
        original=json.dumps(raw,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
        if len(original)>purchases.MAX_SOURCE_BYTES: raise HTTPException(413,'Source record exceeds 12 MB')
        file_id=await purchases.capture_file(pool,store_id,actor,original,'manual-source-'+fingerprint(raw).hex()[:16]+'.json',
            'application/json',str(idempotency_key),projection=projection)
        async with pool.acquire() as conn:
            async with conn.transaction():
                for attachment in set(body.attachment_ids):
                    await conn.execute('''INSERT INTO purchasing.manual_attachments(record_file_id,attachment_file_id,store_id)
                        VALUES($1,$2,$3) ON CONFLICT DO NOTHING''',file_id,attachment,store_id)
        result=await purchases.file_preview(pool,store_id,file_id)
        result['manualRecord']=raw
        return result
