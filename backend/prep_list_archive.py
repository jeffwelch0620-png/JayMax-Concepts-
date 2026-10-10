"""Manager-only reads of stored prep lists; no classification or fact writes."""
from datetime import date
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, Request
from legacy_prep_views import archive_basis
from purchase_api import serial

FILTERS = {
    'all': 'true', 'daily': "p.count_type='nightly_prep'",
    'bulk': "p.count_type='commissary'", 'unclassified': 'p.count_type IS NULL',
    'other': "p.count_type IS NOT NULL AND p.count_type NOT IN ('nightly_prep','commissary')",
}


def classify_count_type(value):
    return {'nightly_prep':'daily', 'commissary':'bulk'}.get(value, 'unclassified' if value is None else 'other')


def create_router(pool, check_store, manager, postgres_enabled):
    router = APIRouter(prefix='/api/pg')

    @router.get('/prep-list-archive/{store_id}')
    async def read(store_id: str, request: Request,
                   date_from: date | None = None, date_through: date | None = None,
                   classification: Literal['all','daily','bulk','unclassified','other'] = 'all',
                   after_date: date | None = None, after_id: UUID | None = None,
                   limit: int = Query(50, ge=1, le=200)):
        check_store(store_id)
        manager(request)
        if not postgres_enabled():
            raise HTTPException(503, 'Historical PostgreSQL lists require PostgreSQL mode')
        if date_from and date_through and date_from > date_through:
            raise HTTPException(422, 'Start date must not follow end date')
        if (after_date is None) != (after_id is None):
            raise HTTPException(422, 'Archive continuation requires both date and list reference')
        # Interpolate only an enumerated source constant; all values are bound.
        where = 'p.store_id=$1 AND ($2::date IS NULL OR p.prep_date >= $2) AND ($3::date IS NULL OR p.prep_date <= $3) AND ' + FILTERS[classification]
        async with pool().acquire() as conn:
            async with conn.transaction(isolation='repeatable_read', readonly=True):
                await conn.execute("SET LOCAL TIME ZONE 'UTC'")
                await conn.execute("SET LOCAL statement_timeout='20s'")
                if after_id and not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM public.prep_lists p WHERE ' + where + ' AND p.prep_date=$4 AND p.id=$5)', store_id,date_from,date_through,after_date,after_id):
                    raise HTTPException(422, 'Archive continuation was not confirmed for this location and selection')
                headers = await conn.fetch('SELECT p.* FROM public.prep_lists p WHERE ' + where + ' AND ($4::date IS NULL OR (p.prep_date,p.id)>($4::date,$5::uuid)) ORDER BY p.prep_date,p.id LIMIT $6',store_id,date_from,date_through,after_date,after_id,limit+1)
                more = len(headers)>limit
                headers = headers[:limit]
                lines = await conn.fetch('''SELECT l.* FROM public.prep_list_lines l
                    JOIN public.prep_lists p ON p.id=l.list_id
                    WHERE p.store_id=$1 AND l.list_id=ANY($2::uuid[]) ORDER BY l.list_id,l.id''',store_id,[r['id'] for r in headers]) if headers else []
                grouped = {r['id']:[] for r in headers}
                for line in lines: grouped[line['list_id']].append(dict(line))
                records = []
                for header in headers:
                    kind = classify_count_type(header['count_type'])
                    records.append({'id':header['id'],'storeId':store_id,'date':header['prep_date'],
                        'countType':header['count_type'],'track':kind if kind in ('daily','bulk') else None,
                        'classification':kind,'header':dict(header),'lines':grouped[header['id']],**archive_basis()})
                cursor = {'after_date':headers[-1]['prep_date'],'after_id':headers[-1]['id']} if more else None
                return serial({'storeId':store_id,'dateFrom':date_from,'dateThrough':date_through,
                    'classification':classification,'records':records,'nextCursor':cursor,**archive_basis()})
    return router
