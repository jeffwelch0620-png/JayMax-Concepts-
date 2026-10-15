"""Read-only recovery of source capture attempts. Never posts inventory facts."""
import hashlib
import json
from uuid import UUID

from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

import purchase_api as purchases
from purchase_parser import PARSER_VERSION, fingerprint


class CaptureProbe(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['csv', 'source']
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    byteCount: int = Field(strict=True, gt=0, le=purchases.MAX_SOURCE_BYTES)
    filename: str = Field(min_length=1, max_length=255)


def manual_source(body):
    raw = body.model_dump(mode='json')
    raw['attachment_ids'] = sorted(set(raw['attachment_ids']))
    original = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return raw, original, 'manual-source-' + fingerprint(raw).hex()[:16] + '.json'


def multipart_filename(filename):
    # The probe carries File.name; the upload already passed through HTML's
    # multipart escaping. Do not URL-decode: literal "%22" must stay literal.
    return filename.replace('\n', '%0A').replace('\r', '%0D').replace('"', '%22')


async def capture_status(pool, store_id, actor, key, kind, digest, byte_count, filename, attachments=()):
    # A consistent read only; an absent attempt can still commit after this read.
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True, isolation='repeatable_read'):
            row = await conn.fetchrow('''SELECT a.attempted_by,a.supplied_filename,f.id,f.store_id,
                f.source_sha256,octet_length(f.source_bytes) AS byte_count
                FROM purchasing.upload_attempts a JOIN purchasing.import_files f ON f.id=a.file_id
                WHERE a.attempt_key=$1 AND f.store_id=$2''', key, store_id)
            result = dict(kind=kind, requestKey=key, actorId=actor, storeId=store_id,
                          sourceSha256=digest.hex(), outcome='retry_available', fileId=None)
            if row is None:
                return result
            if (row['attempted_by'] != actor or row['store_id'] != store_id
                    or row['source_sha256'] != digest or row['byte_count'] != byte_count
                    or row['supplied_filename'] != filename):
                raise HTTPException(409, {'code': 'capture_identity_mismatch',
                    'message': 'This capture request does not match the retained source and user'})
            complete = True
            if kind != 'source':
                version = 'manual-document-v1' if kind == 'manual' else PARSER_VERSION
                complete = bool(await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM purchasing.parse_runs
                    WHERE file_id=$1 AND parser_version=$2)''', row['id'], version))
            if kind == 'manual':
                linked = {str(r['attachment_file_id']) for r in await conn.fetch('''SELECT attachment_file_id
                    FROM purchasing.manual_attachments WHERE record_file_id=$1 AND store_id=$2''', row['id'], store_id)}
                complete = complete and linked == set(attachments)
            if complete:
                result.update(outcome='saved', fileId=str(row['id']))
            return result


def install_routes(router, context):
    from manual_purchases import ManualRecord, ready

    @router.post('/{store_id}/capture-status')
    async def file_status(store_id: str, body: CaptureProbe, request: Request,
                          idempotency_key: UUID = Header(...)):
        actor, pool = await context(request, store_id, True)
        return await capture_status(pool, store_id, actor, str(idempotency_key), body.kind,
                                    bytes.fromhex(body.sha256), body.byteCount, multipart_filename(body.filename))

    @router.post('/{store_id}/manual-records/status')
    async def manual_status(store_id: str, body: ManualRecord, request: Request,
                            idempotency_key: UUID = Header(...)):
        actor, pool = await context(request, store_id, True)
        await ready(pool)
        raw, original, filename = manual_source(body)
        if len(original) > purchases.MAX_SOURCE_BYTES:
            raise HTTPException(413, 'Source record exceeds 12 MB')
        result = await capture_status(pool, store_id, actor, str(idempotency_key), 'manual',
                                      hashlib.sha256(original).digest(), len(original), filename, raw['attachment_ids'])
        result['manualRecord'] = raw
        return result
