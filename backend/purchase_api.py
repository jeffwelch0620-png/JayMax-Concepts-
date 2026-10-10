"""Native PostgreSQL purchase capture/review/posting; no Mongo or state writes."""
import asyncio
import hashlib
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from purchase_parser import (FIELD_MAP, PARSER_VERSION, document_totals, fingerprint,
                             json_value, parse_csv)

MAX_SOURCE_BYTES = 12 * 1024 * 1024
ALLOWED_UNITS = {'lb': 'mass', 'oz': 'mass', 'g': 'mass', 'kg': 'mass',
                 'fl_oz': 'volume', 'ml': 'volume', 'l': 'volume', 'gal': 'volume', 'each': 'count'}
FIELD_COLUMNS = {'document_versions': set(), 'document_lines': set(), 'document_parties': set()}
for _spec in FIELD_MAP:
    _parts = _spec['target'].split('.')
    FIELD_COLUMNS[{'documents': 'document_versions', 'lines': 'document_lines',
                   'parties': 'document_parties'}[_parts[0]]].add(_parts[-1])


def enabled():
    return (os.environ.get('PURCHASE_IMPORT_ENABLED', 'false').lower() == 'true'
            and os.environ.get('USE_PG', 'false').lower() == 'true')


def serial(value):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (date, Decimal)):
        return str(value)
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    return value


class ReviewLine(BaseModel):
    model_config = ConfigDict(extra='forbid')
    line_id: UUID
    classification: Literal['food', 'nonfood', 'fee', 'tax']
    movement_kind: Literal['receipt', 'physical_return', 'price_credit', 'no_inventory']
    item_code: str | None = None
    base_unit: Literal['lb', 'oz', 'g', 'kg', 'fl_oz', 'ml', 'l', 'gal', 'each'] | None = None
    received_quantity: Decimal | None = Field(None, max_digits=28, decimal_places=12)
    received_unit: str | None = Field(None, max_length=40)
    base_units_per_received_unit: Decimal | None = Field(None, max_digits=28, decimal_places=12)
    movement_date: date | None = None
    original_line_id: UUID | None = None
    verified: Literal[True]
    note: str = Field(min_length=1, max_length=2000)

    @field_validator('received_quantity', 'base_units_per_received_unit')
    @classmethod
    def finite(cls, value):
        if value is not None and not value.is_finite():
            raise ValueError('Use a finite decimal number')
        return value

    @field_validator('note', 'received_unit', 'item_code')
    @classmethod
    def nonblank(cls, value):
        if value is not None and not value.strip():raise ValueError('Enter a nonblank value')
        return value


class PostDocument(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirmed_currency: Literal['USD']
    received_date: date | None = None
    lines: list[ReviewLine] = Field(min_length=1, max_length=50000)


async def projected_insert(conn, table, fields, extra):
    # Identifiers come exclusively from the checked-in field contract.
    assert table in FIELD_COLUMNS and set(fields) <= FIELD_COLUMNS[table]
    values = {**extra, **fields}
    columns = list(values)
    assert all(name.replace('_', '').isalnum() for name in columns)
    placeholders = ','.join(f'${i+1}' for i in range(len(columns)))
    return await conn.fetchval(f"INSERT INTO purchasing.{table} ({','.join(columns)}) VALUES ({placeholders}) RETURNING id",
                               *(values[name] for name in columns))


async def require_schema(conn):
    if not await conn.fetchval("SELECT to_regclass('purchasing.import_files') IS NOT NULL"):
        raise HTTPException(503, 'Purchase import setup has not been applied yet')


async def load_version(conn, store_id, version_id, lock=False):
    if lock:
        # Capture and posting use the same identity-before-version lock order.
        await conn.fetchval('''SELECT i.id FROM purchasing.document_identities i
            JOIN purchasing.document_versions d ON d.document_id=i.id
            WHERE d.id=$1 AND i.store_id=$2 FOR UPDATE OF i''', version_id, store_id)
    record = await conn.fetchrow('''SELECT d.*,i.store_id,i.vendor_id,i.document_type,
        i.vendor_branch_key,i.customer_account_key,
        (SELECT b.id FROM purchasing.posting_batches b WHERE b.document_id=i.id) AS posted_batch_id,
        (SELECT b.document_version_id FROM purchasing.posting_batches b WHERE b.document_id=i.id) AS posted_version_id
        FROM purchasing.document_versions d JOIN purchasing.document_identities i ON i.id=d.document_id
        WHERE d.id=$1 AND i.store_id=$2''' + (' FOR UPDATE OF d' if lock else ''), version_id, store_id)
    if record is None:
        raise HTTPException(404, 'Purchase document not found for this location')
    result=dict(record)
    if await conn.fetchval("SELECT to_regclass('purchasing.corrections') IS NOT NULL"):
        current=await conn.fetchrow('''SELECT c.id,c.replacement_version_id FROM purchasing.corrections c
            WHERE c.initial_batch_id=$1 AND NOT EXISTS
            (SELECT 1 FROM purchasing.corrections n WHERE n.previous_correction_id=c.id)''',result['posted_batch_id'])
        result['initial_posted_version_id']=result['posted_version_id']
        result['current_correction_id']=current['id'] if current else None
        if current:result['posted_version_id']=current['replacement_version_id']
    return result


async def document_preview(conn, store_id, version_id):
    header = await load_version(conn, store_id, version_id)
    records = [dict(r) for r in await conn.fetch('''SELECT l.* FROM purchasing.document_lines l
        WHERE l.document_version_id=$1 ORDER BY l.line_ordinal''', version_id)]
    totals = document_totals(header, records)
    legacy = await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM public.invoices
        WHERE store_id=$1 AND vendor_id=$2 AND btrim(invoice_number)=$3)''',
        store_id, header['vendor_id'], header['document_number'])
    matches = await conn.fetch('''SELECT vi.id,vi.vendor_sku,vi.item_code,i.name,
        ib.base_unit FROM public.vendor_items vi
        JOIN public.store_items si ON si.item_code=vi.item_code AND si.store_id=$1
        JOIN public.items i ON i.code=vi.item_code
        LEFT JOIN purchasing.item_bases ib ON ib.store_id=si.store_id AND ib.item_code=si.item_code
        WHERE vi.vendor_id=$2''', store_id, header['vendor_id'])
    by_sku = {}
    for match in matches:
        by_sku.setdefault(match['vendor_sku'], []).append(dict(match))
    for record in records:
        record['suggestions'] = by_sku.get(record['vendor_sku_snapshot'], [])
    if await conn.fetchval("SELECT to_regclass('purchasing.unit_profiles') IS NOT NULL"):
        from native_units import profiles
        fresh=[p for p in await profiles(conn,store_id) if p['profile_kind']=='purchase' and not p['stale']]
        for record in records:
            candidates=[p for p in fresh if p['source_snapshot']['supplierProduct']['vendor_id']==header['vendor_id']
                and p['source_snapshot']['supplierProduct']['vendor_sku']==record['vendor_sku_snapshot']]
            if len(candidates)==1:record['unitProfileSuggestion']=serial(candidates[0])
    errors = list(header['projection_errors']) + totals['errors']
    latest = await conn.fetchval('SELECT max(revision) FROM purchasing.document_versions WHERE document_id=$1', header['document_id'])
    if header['revision'] != latest and header['posted_version_id'] != version_id:
        errors.append('A newer source version exists; review the latest version before posting')
    if legacy:
        errors.append('An earlier purchase record already uses this invoice number; reconcile it before posting')
    namespace_conflict = await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM purchasing.document_identities i
        JOIN purchasing.posting_batches b ON b.document_id=i.id WHERE i.store_id=$1 AND i.vendor_id=$2
        AND i.document_type=$3 AND i.document_number=$4 AND i.id<>$5)''',
        store_id,header['vendor_id'],header['document_type'],header['document_number'],header['document_id'])
    if namespace_conflict:
        errors.append('This invoice number was posted under a different account or branch; identity review is required')
    source_errors=list(errors)
    posted = header['posted_version_id'] == version_id
    if header['posted_batch_id'] and not posted:
        errors.append('A different version was already posted; correction review is required')
    status = 'posted' if posted else 'held' if errors else 'awaiting_review'
    correction_ready=await conn.fetchval("SELECT to_regclass('purchasing.corrections') IS NOT NULL")
    current_mappings=[]
    if correction_ready and posted:
        current_mappings=[dict(r) for r in await conn.fetch('''SELECT m.* FROM purchasing.current_posting_lines p
            JOIN purchasing.mapping_decisions m ON m.id=p.mapping_id WHERE p.document_version_id=$1''',version_id)]
    return serial({'correctionAvailable':bool(correction_ready and header['posted_batch_id'] and header['revision']==latest and not source_errors),
                   'sourceErrors':source_errors,'currentMappings':current_mappings,'id': version_id, 'header': header, 'lines': records,
                   'totals': totals, 'status': status, 'errors': sorted(set(errors))})


async def capture_source(pool, store_id, actor, source, filename, mime_type, attempt_key):
    digest = hashlib.sha256(source).digest()
    async with pool.acquire() as conn:
        await require_schema(conn)
        async with conn.transaction():
            file_id = await conn.fetchval('''INSERT INTO purchasing.import_files
                (store_id,source_sha256,source_bytes,original_filename,mime_type,captured_by)
                VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT(store_id,source_sha256) DO NOTHING RETURNING id''',
                store_id, digest, source, filename, mime_type, actor)
            if file_id is None:
                file_id = await conn.fetchval('SELECT id FROM purchasing.import_files WHERE store_id=$1 AND source_sha256=$2', store_id, digest)
            attempt = await conn.fetchval('''INSERT INTO purchasing.upload_attempts
                (file_id,attempt_key,supplied_filename,attempted_by) VALUES ($1,$2,$3,$4)
                ON CONFLICT(attempt_key) DO NOTHING RETURNING file_id''', file_id, attempt_key, filename, actor)
            if attempt is None:
                existing = await conn.fetchval('SELECT file_id FROM purchasing.upload_attempts WHERE attempt_key=$1', attempt_key)
                if existing != file_id:
                    raise HTTPException(409, 'Upload request key was already used for another file')
    return file_id


async def capture_file(pool, store_id, actor, source, filename, mime_type, attempt_key, *, projection=None):
    # Source bytes commit first, even if parsing/projection fails afterwards.
    file_id = await capture_source(pool,store_id,actor,source,filename,mime_type,attempt_key)
    parsed = projection if projection is not None else await asyncio.to_thread(parse_csv, source)
    parser_version = parsed['parserVersion']
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.fetchval('SELECT id FROM purchasing.import_files WHERE id=$1 FOR UPDATE', file_id)
            run_id = await conn.fetchval('SELECT id FROM purchasing.parse_runs WHERE file_id=$1 AND parser_version=$2', file_id, parser_version)
            if run_id is None:
                run_id = await conn.fetchval('''INSERT INTO purchasing.parse_runs
                    (file_id,parser_version,detected_vendor_format,encoding_used,header_cells,parse_errors)
                    VALUES($1,$2,$3,$4,$5,$6) RETURNING id''', file_id, parser_version,
                    parsed['vendor'], parsed['encoding'], parsed['headers'], parsed['errors'])
                await conn.executemany('''INSERT INTO purchasing.raw_rows
                    (parse_run_id,row_ordinal,raw_values,parse_errors) VALUES($1,$2,$3,$4)''',
                    [(run_id,r['ordinal'],r['values'],r['errors']) for r in parsed['rows']])
                for document in sorted(parsed['documents'], key=lambda d:d['identity']):
                    vendor, branch, account, dtype, number = document['identity']
                    await conn.execute('''INSERT INTO public.vendors(id,name) VALUES($1,$2)
                        ON CONFLICT(id) DO NOTHING''', vendor, document['vendor'])
                    identity_id = await conn.fetchval('''INSERT INTO purchasing.document_identities
                        (store_id,vendor_id,vendor_branch_key,customer_account_key,document_type,document_number)
                        VALUES($1,$2,$3,$4,$5,$6)
                        ON CONFLICT(store_id,vendor_id,vendor_branch_key,customer_account_key,document_type,document_number)
                        DO NOTHING RETURNING id''', store_id,vendor,branch,account,dtype,number)
                    if identity_id is None:
                        identity_id = await conn.fetchval('''SELECT id FROM purchasing.document_identities
                            WHERE store_id=$1 AND vendor_id=$2 AND vendor_branch_key=$3 AND customer_account_key=$4
                            AND document_type=$5 AND document_number=$6 FOR UPDATE''', store_id,vendor,branch,account,dtype,number)
                    else:
                        await conn.fetchval('SELECT id FROM purchasing.document_identities WHERE id=$1 FOR UPDATE', identity_id)
                    version_id = await conn.fetchval('''SELECT id FROM purchasing.document_versions
                        WHERE document_id=$1 AND canonical_fingerprint=$2''', identity_id, document['fingerprint'])
                    if version_id is None:
                        revision = await conn.fetchval('SELECT coalesce(max(revision),0)+1 FROM purchasing.document_versions WHERE document_id=$1', identity_id)
                        version_id = await projected_insert(conn, 'document_versions', document['header'], {
                            'document_id': identity_id, 'revision': revision,
                            'canonical_fingerprint': document['fingerprint'],
                            'expected_line_count': len(document['lines']), 'parser_version': parser_version,
                            'confirmed_currency': 'USD', 'header_consistency_confirmed': not document['errors'],
                            'projection_errors': document['errors']})
                        for role, fields in document['parties'].items():
                            await projected_insert(conn, 'document_parties', fields,
                                {'document_version_id': version_id, 'party_role': role})
                        line_ids = {}
                        for line in document['lines']:
                            line_ids[line['ordinal']] = await projected_insert(conn, 'document_lines', line['fields'],
                                {'document_version_id': version_id, 'line_ordinal': line['ordinal']})
                    else:
                        line_ids = {r['line_ordinal']:r['id'] for r in await conn.fetch('SELECT id,line_ordinal FROM purchasing.document_lines WHERE document_version_id=$1', version_id)}
                    await conn.executemany('''INSERT INTO purchasing.document_source_rows
                        (parse_run_id,row_ordinal,document_version_id,document_line_id) VALUES($1,$2,$3,$4)''',
                        [(run_id,line['sourceOrdinal'],version_id,line_ids[line['ordinal']]) for line in document['lines']])
    return file_id


async def file_preview(pool, store_id, file_id):
    async with pool.acquire() as conn:
        row = await conn.fetchrow('''SELECT f.id,f.original_filename,f.source_sha256,f.captured_at,
            octet_length(f.source_bytes) AS byte_count,p.id AS parse_run_id,p.parser_version,p.header_cells,p.parse_errors,
            (SELECT count(*) FROM purchasing.raw_rows r WHERE r.parse_run_id=p.id) AS source_record_count
            FROM purchasing.import_files f LEFT JOIN LATERAL (SELECT * FROM purchasing.parse_runs x
                WHERE x.file_id=f.id ORDER BY (x.parser_version='manual-document-v1') DESC,x.parsed_at DESC LIMIT 1) p ON true
            WHERE f.id=$1 AND f.store_id=$2''', file_id,store_id)
        if row is None:
            raise HTTPException(404,'Captured file not found for this location')
        result=dict(row)
        version_ids = await conn.fetch('''SELECT DISTINCT document_version_id FROM purchasing.document_source_rows
            WHERE parse_run_id=$1''',row['parse_run_id']) if row['parse_run_id'] else []
        result['documents'] = [await document_preview(conn,store_id,r['document_version_id']) for r in version_ids]
        result['captureStatus'] = 'captured'
        if row['parser_version']=='manual-document-v1':
            result['manualRecord']=json.loads(await conn.fetchval('SELECT convert_from(source_bytes,\'UTF8\') FROM purchasing.import_files WHERE id=$1',file_id))
        if row['parse_run_id'] is None:
            result['parse_errors'] = ['Original source retained. Enter its details for manual review, or retry a supported CSV upload.']
        if await conn.fetchval("SELECT to_regclass('purchasing.manual_attachments') IS NOT NULL"):
            result['attachments'] = serial([dict(r) for r in await conn.fetch('''SELECT f.id,f.original_filename
                FROM purchasing.manual_attachments a JOIN purchasing.import_files f ON f.id=a.attachment_file_id
                WHERE a.record_file_id=$1 AND a.store_id=$2 ORDER BY f.id''',file_id,store_id)])
        return serial(result)


async def append_review_mappings(conn, store_id, actor, header, body, source_lines):
    for review in body.lines:
        source_line=source_lines[review.line_id]
        food=review.classification=='food'
        movement=review.movement_kind
        amount=source_line['extended_amount_source']
        quantity=review.received_quantity
        conversion=review.base_units_per_received_unit
        if food and movement=='receipt':
            record_date=body.received_date
        elif food and movement in ('physical_return','price_credit'):
            record_date=review.movement_date
        else:
            record_date=None
        if food and movement!='no_inventory':
            if not review.item_code or not review.base_unit or record_date is None:
                raise HTTPException(422,'Food movements require a confirmed item, base unit and inventory date')
            closed=await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM public.reporting_periods
                WHERE store_id=$1 AND status='closed' AND period_start<=$2 AND period_end>=$2)''',store_id,record_date)
            if closed:
                raise HTTPException(409,'This inventory date falls in a closed period; correction review is required')
        if movement in ('receipt','physical_return'):
            if quantity is None or conversion is None or conversion<=0 or not review.received_unit:
                raise HTTPException(422,'Confirm actual received/returned quantity, its unit and a positive conversion')
            if movement=='receipt' and quantity<0 or movement=='physical_return' and quantity>=0:
                raise HTTPException(422,'Receipt quantities cannot be negative; returned quantities must be negative')
        if not food and movement!='no_inventory':
            raise HTTPException(422,'Non-food, fee and tax lines must have no food-inventory movement')
        if food and movement=='price_credit' and review.original_line_id is None:
            raise HTTPException(422,'Link a price-only credit to its original receipt')
        if food and movement=='no_inventory' and amount!=0:
            raise HTTPException(422,'A nonzero food amount needs a receipt, return or price-credit disposition')
        if food and review.item_code:
            if not review.base_unit:
                raise HTTPException(422,'Confirm the fixed inventory base unit')
            valid=await conn.fetchval('SELECT EXISTS(SELECT 1 FROM public.store_items WHERE store_id=$1 AND item_code=$2)',store_id,review.item_code)
            if not valid:
                raise HTTPException(422,'Item is not registered at this location')
            await conn.execute('''INSERT INTO purchasing.item_bases(store_id,item_code,base_unit)
                VALUES($1,$2,$3) ON CONFLICT(store_id,item_code) DO NOTHING''',store_id,review.item_code,review.base_unit)
            actual_base=await conn.fetchval('SELECT base_unit FROM purchasing.item_bases WHERE store_id=$1 AND item_code=$2',store_id,review.item_code)
            if actual_base!=review.base_unit:
                raise HTTPException(409,f'Item inventory unit is already {actual_base}; convert quantities to that unit')
        revision=await conn.fetchval('SELECT coalesce(max(revision),0)+1 FROM purchasing.mapping_decisions WHERE line_id=$1',review.line_id)
        await conn.execute('''INSERT INTO purchasing.mapping_decisions
            (line_id,revision,store_id,classification,movement_kind,item_code,base_unit,
            received_quantity,received_unit,base_units_per_received_unit,inventory_cost_amount,
            inventory_record_date,goods_received_date,returned_date,credit_original_line_id,
            pricing_basis,conversion_snapshot,cost_policy_version,mapping_method,confirmed_by,decision_note)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21)''',
            review.line_id,revision,store_id,review.classification,movement,
            review.item_code if food else None,review.base_unit if food else None,
            quantity if food else None,review.received_unit if food else None,
            conversion if food else None,amount if food else Decimal(0),record_date,
            record_date if movement=='receipt' else None,record_date if movement=='physical_return' else None,
            review.original_line_id,'supplier_line_extension',
            {'sourcePack':source_line['pack_description_raw'],'receivedUnit':review.received_unit,
             'baseUnit':review.base_unit,'factor':str(conversion) if conversion is not None else None},
            'food_line_extension_separate_tax_fees-v1','manual',actor,review.note)


async def post_review(pool, store_id, actor, version_id, body, request_key):
    payload = body.model_dump(mode='python')
    payload['lines'] = sorted(payload['lines'],key=lambda x:str(x['line_id']))
    request_fingerprint = fingerprint(serial(payload))
    async with pool.acquire() as conn:
        async with conn.transaction():
            header = await load_version(conn,store_id,version_id,lock=True)
            prior = await conn.fetchrow('SELECT * FROM purchasing.posting_batches WHERE document_id=$1',header['document_id'])
            if prior:
                if prior['document_version_id']==version_id and prior['idempotency_key']==request_key and prior['request_fingerprint']==request_fingerprint:
                    return str(prior['id'])
                raise HTTPException(409,'This invoice is already posted; correction review is required')
            preview=await document_preview(conn,store_id,version_id)
            if preview['status']=='held':
                raise HTTPException(409, {'message':'Invoice needs review before posting','reasons':preview['errors']})
            source_lines={r['id']:dict(r) for r in await conn.fetch('SELECT * FROM purchasing.document_lines WHERE document_version_id=$1',version_id)}
            if len(body.lines)!=len(source_lines) or {r.line_id for r in body.lines}!=set(source_lines):
                raise HTTPException(422,'Confirm every source line exactly once')
            # Same revision-row lock used by existing period/state writes.
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext('purchase-invoice'),hashtext(concat_ws('|',$1::text,$2::text,$3::text)))",
                               store_id,header['vendor_id'],header['document_number'])
            await conn.execute('''INSERT INTO public.store_state(store_id) VALUES($1) ON CONFLICT(store_id) DO NOTHING''',store_id)
            await conn.fetchval('SELECT revision FROM public.store_state WHERE store_id=$1 FOR UPDATE',store_id)
            await append_review_mappings(conn,store_id,actor,header,body,source_lines)
            totals=document_totals(header,list(source_lines.values()))
            revision=await conn.fetchval('SELECT coalesce(max(revision),0)+1 FROM purchasing.reconciliation_checks WHERE document_version_id=$1',version_id)
            await conn.execute('''INSERT INTO purchasing.reconciliation_checks
                (document_version_id,revision,line_total,expected_document_total,stated_document_total,status,component_explanation,confirmed_by)
                VALUES($1,$2,$3,$4,$5,'balanced',$6,$7)''',version_id,revision,
                totals['lineTotal'],totals['expectedTotal'],totals['statedTotal'],
                {'tax':'separate','fees':'separate','unexplainedDifference':str(totals['difference'])},actor)
            batch_id=await conn.fetchval('SELECT purchasing.post_document($1,$2,$3,$4)',version_id,request_key,actor,request_fingerprint)
            await conn.execute('UPDATE public.store_state SET revision=revision+1,updated_at=now() WHERE store_id=$1',store_id)
            if await conn.fetchval('SELECT count(*) FROM purchasing.posting_lines WHERE batch_id=$1',batch_id)!=len(source_lines):
                raise HTTPException(500,'Purchase read-back failed; the transaction was rolled back')
            return str(batch_id)


def create_router(pool_factory, store_check, authorize):
    router=APIRouter(prefix='/api/pg/purchases')

    async def context(request,store_id,write=False):
        store_check(store_id)
        actor=authorize(request,store_id,write)
        if not enabled():
            raise HTTPException(503,'Purchase import is awaiting enablement')
        pool=pool_factory()
        async with pool.acquire() as conn:
            await require_schema(conn)
        return actor,pool

    @router.get('/{store_id}/capabilities')
    async def capabilities(store_id:str,request:Request):
        store_check(store_id);authorize(request,store_id,False)
        if not enabled():
            return {'enabled':False,'reportingReady':False}
        async with pool_factory().acquire() as conn:
            ready=await conn.fetchval("SELECT to_regclass('purchasing.import_files') IS NOT NULL")
            report_ready=(os.getenv('ACTUAL_INVENTORY_ENABLED','false').lower()=='true'
                          and await conn.fetchval("SELECT to_regclass('actual_inventory.scope_bridges') IS NOT NULL"))
            correction_ready=await conn.fetchval("SELECT to_regclass('purchasing.corrections') IS NOT NULL")
            manual_ready=await conn.fetchval("SELECT to_regclass('purchasing.manual_attachments') IS NOT NULL")
            units_ready=await conn.fetchval("SELECT to_regclass('purchasing.po_receipts') IS NOT NULL")
        return {'enabled':bool(ready),'reportingReady':bool(report_ready),'correctionReady':bool(correction_ready),'manualReady':bool(manual_ready),'unitsReady':bool(units_ready),'baseUnits':list(ALLOWED_UNITS)}

    @router.get('/{store_id}/operating-summary')
    async def operating(store_id:str,request:Request):
        _,pool=await context(request,store_id)
        from native_inventory_views import read_operating_summary
        return await read_operating_summary(pool,store_id)

    @router.post('/{store_id}/files')
    async def capture(store_id:str,request:Request,file:UploadFile=File(...),
                      idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True)
        source=await file.read(MAX_SOURCE_BYTES+1)
        if not source or len(source)>MAX_SOURCE_BYTES:
            raise HTTPException(413,'Select a nonempty invoice file no larger than 12 MB')
        file_id=await capture_file(pool,store_id,actor,source,Path(file.filename or 'invoice.csv').name,
                                   file.content_type or 'application/octet-stream',str(idempotency_key))
        return await file_preview(pool,store_id,file_id)

    @router.get('/{store_id}/files')
    async def files(store_id:str,request:Request,offset:int=0):
        _,pool=await context(request,store_id)
        if offset<0:raise HTTPException(422,'Offset must be nonnegative')
        async with pool.acquire() as conn:
            return serial([dict(r) for r in await conn.fetch('''SELECT f.id,f.original_filename,f.captured_at,
                octet_length(f.source_bytes) AS byte_count FROM purchasing.import_files f
                WHERE store_id=$1 ORDER BY captured_at DESC,id OFFSET $2 LIMIT 200''',store_id,offset)])

    @router.get('/{store_id}/files/{file_id}')
    async def preview_file(store_id:str,file_id:UUID,request:Request):
        _,pool=await context(request,store_id)
        return await file_preview(pool,store_id,file_id)

    @router.get('/{store_id}/files/{file_id}/source')
    async def download_source(store_id:str,file_id:UUID,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn:
            row=await conn.fetchrow('SELECT source_bytes FROM purchasing.import_files WHERE id=$1 AND store_id=$2',file_id,store_id)
            if row is None:raise HTTPException(404,'Captured file not found for this location')
            return Response(bytes(row['source_bytes']),media_type='application/octet-stream',
                            headers={'Content-Disposition':f'attachment; filename="invoice-{file_id}.bin"'})

    @router.get('/{store_id}/files/{file_id}/rows')
    async def raw_rows(store_id:str,file_id:UUID,request:Request,offset:int=0):
        _,pool=await context(request,store_id)
        if offset<0:raise HTTPException(422,'Offset must be nonnegative')
        async with pool.acquire() as conn:
            run=await conn.fetchrow('''SELECT p.id,p.header_cells FROM purchasing.parse_runs p
                JOIN purchasing.import_files f ON f.id=p.file_id
                WHERE f.id=$1 AND f.store_id=$2 ORDER BY (p.parser_version='manual-document-v1') DESC,p.parsed_at DESC LIMIT 1''',file_id,store_id)
            if run is None:raise HTTPException(404,'Parsed source not found for this location')
            rows=await conn.fetch('SELECT row_ordinal,raw_values,parse_errors FROM purchasing.raw_rows WHERE parse_run_id=$1 ORDER BY row_ordinal OFFSET $2 LIMIT 500',run['id'],offset)
            return serial({'headers':run['header_cells'],'rows':[dict(r) for r in rows],
                           'nextOffset':offset+500 if len(rows)==500 else None})

    @router.get('/{store_id}/documents/{version_id}')
    async def preview_document(store_id:str,version_id:UUID,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn:return await document_preview(conn,store_id,version_id)

    @router.post('/{store_id}/documents/{version_id}/post')
    async def post(store_id:str,version_id:UUID,body:PostDocument,request:Request,
                   idempotency_key:UUID=Header(...)):
        actor,pool=await context(request,store_id,True)
        try:
            batch=await post_review(pool,store_id,actor,version_id,body,str(idempotency_key))
        except (asyncpg.CheckViolationError,asyncpg.ForeignKeyViolationError,asyncpg.UniqueViolationError,
                asyncpg.RaiseError) as exc:
            raise HTTPException(409,'Purchase validation failed; no partial posting was saved. Review quantities, units and credit links.') from exc
        async with pool.acquire() as conn:
            document=await document_preview(conn,store_id,version_id)
        return {'batchId':batch,'document':document}

    @router.get('/{store_id}/history')
    async def history(store_id:str,request:Request):
        _,pool=await context(request,store_id)
        async with pool.acquire() as conn:
            correction_ready=await conn.fetchval("SELECT to_regclass('purchasing.corrections') IS NOT NULL")
            extra=",EXISTS(SELECT 1 FROM purchasing.current_posting_lines cp WHERE cp.mapping_id=f.mapping_id AND (f.fact_kind='replacement' AND cp.correction_id=f.correction_id OR f.fact_kind='initial' AND cp.correction_id IS NULL)) AND m.movement_kind='receipt' AS current_receipt" if correction_ready else ",m.movement_kind='receipt' AS current_receipt"
            return serial([dict(r) for r in await conn.fetch('''SELECT f.*,i.document_number'''+extra+''',
                i.document_type,l.description_snapshot FROM purchasing.actual_purchase_facts f
                JOIN purchasing.document_identities i ON i.id=f.document_id
                JOIN purchasing.document_lines l ON l.id=f.line_id
                JOIN purchasing.mapping_decisions m ON m.id=f.mapping_id WHERE f.store_id=$1
                ORDER BY f.inventory_record_date DESC,f.line_id,f.mapping_id,to_jsonb(f)->>'fact_id' ''',store_id)])

    from purchase_corrections import install_routes
    install_routes(router,context)
    from manual_purchases import install_routes as install_manual_routes
    install_manual_routes(router,context)
    from native_units import install_routes as install_unit_routes
    install_unit_routes(router,context)
    from native_order_receiving import install_routes as install_receiving_routes
    install_receiving_routes(router,context)
    from prep_mapping import install_routes as install_prep_mapping_routes
    install_prep_mapping_routes(router,context)
    from prep_batches import install_routes as install_prep_batch_routes
    install_prep_batch_routes(router,context)
    from prep_observations import install_routes as install_prep_observation_routes
    install_prep_observation_routes(router,context)
    from prep_periods import install_routes as install_prep_period_routes
    install_prep_period_routes(router,context)
    from prep_period_journal import install_routes as install_prep_journal_routes
    install_prep_journal_routes(router,context)
    from prep_openings import install_routes as install_prep_opening_routes
    install_prep_opening_routes(router,context)
    from supplier_prices import install_routes as install_price_routes
    install_price_routes(router,context)
    from order_commands import install_routes as install_order_routes
    install_order_routes(router,context)
    from supplier_contacts import install_routes as install_contact_routes
    install_contact_routes(router,context)
    from prep_planning import install_routes as install_planning_routes
    install_planning_routes(router,context)
    from prep_day_tasks import install_routes as install_day_task_routes
    install_day_task_routes(router,context)
    from prep_execution import install_routes as install_execution_routes
    install_execution_routes(router,context)
    return router
