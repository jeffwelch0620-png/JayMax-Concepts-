"""Read-only count-aligned prep depletion; no accounting or balance writeback."""
from decimal import Decimal, localcontext
from typing import Literal
from uuid import UUID

from fastapi import HTTPException, Request
from pydantic import model_validator
import prep_mapping as mapping
import prep_observations as observations
from purchase_api import serial
from purchase_parser import fingerprint


class PeriodIn(mapping.Strict):
    opening_count_id: UUID
    closing_count_id: UUID
    opening_cutoff: Literal['before_all', 'after_all']
    closing_cutoff: Literal['before_all', 'after_all']
    cutoffs_confirmed: Literal[True]

    @model_validator(mode='after')
    def distinct(self):
        if self.opening_count_id == self.closing_count_id:
            raise ValueError('Select two distinct physical prep counts')
        return self


def exact_sum(values):
    values = [Decimal(v) for v in values]
    if not values: return Decimal(0)
    if any(not v.is_finite() for v in values): raise ValueError('Finite quantities required')
    # Align both ends of every coefficient; preserve tiny amounts beside large
    # ones, and allow enough carry digits for all rows without fixed rounding.
    precision = max(max(v.adjusted()+1, 1) for v in values) + max(max(-v.as_tuple().exponent, 0) for v in values) + len(str(len(values))) + 2
    with localcontext() as ctx:
        ctx.prec = precision
        return sum(values, Decimal(0))


def number(value): return format(Decimal(value), 'f')


def source(row):
    return {k: row[k] for k in ('id', 'root_id', 'revision', 'kind', 'performed_at', 'review_hash')}


def in_period(instant, start, end, opening, closing):
    return (instant > start or (instant == start and opening == 'before_all')) and (instant < end or (instant == end and closing == 'after_all'))


def calculate(body, opening, closing, events):
    start, end = opening['performed_at'], closing['performed_at']
    if start >= end: raise HTTPException(422, 'Closing count must be later than opening count')
    if opening['timezone_name'] != closing['timezone_name']:
        raise HTTPException(409, 'Prep count timezone policies differ; reconcile their boundaries first')
    left, right = opening['review_snapshot'], closing['review_snapshot']
    if left['scope'] != right['scope']:
        raise HTTPException(409, 'Prep count scopes differ; a reviewed scope handoff is required before comparing them')
    left_lines = {l['product_id']: l for l in left['lines']}
    right_lines = {l['product_id']: l for l in right['lines']}
    names = {str(d['product']['product_id']): d['product']['name'] for d in right.get('definitions', [])}
    rows, raw, included, boundary = {}, {}, [], {'opening': [], 'closing': []}
    for pid in left['scope']:
        a, b = left_lines[pid], right_lines[pid]
        if a['base_unit'] != b['base_unit']:
            raise HTTPException(409, 'Canonical prep count units differ; reconcile them before comparison')
        rows[pid] = {'product_id': pid, 'name': names.get(pid, pid), 'base_unit': b['base_unit'],
                     'openingQuantity': a['base_quantity'], 'closingQuantity': b['base_quantity'],
                     'production': [], 'nestedMeasured': [], 'nestedEstimated': [], 'waste': []}
    for event in events:
        if event.get('source_kind') == 'opening': continue  # physical opening count already carries this quantity
        instant, p = event['performed_at'], event['review_snapshot']
        ref = source(event) | {'purpose': event.get('purpose', 'batch')}
        if instant == start: boundary['opening'].append(ref)
        if instant == end: boundary['closing'].append(ref)
        if not in_period(instant, start, end, body.opening_cutoff, body.closing_cutoff): continue
        included.append(ref)
        for m in p['movements']:
            if m['side'] != 'apply': continue  # latest effective generation only
            qty = Decimal(m['quantity'])
            pid, code = m['product_id'], m['raw_item_code']
            if pid:
                if pid not in rows or rows[pid]['base_unit'] != m['base_unit']:
                    raise HTTPException(409, 'Period activity falls outside the common counted scope or canonical unit; reconcile the counts')
                if event.get('purpose') == 'waste': bucket = 'waste'; qty = qty.copy_negate()
                elif m['kind'] == 'output': bucket = 'production'
                else:
                    inp = next(i for i in p['inputs'] if i['recipe_line_id'] == m['recipe_line_id'])
                    bucket = 'nestedMeasured' if inp['measurement_basis'] == 'measured' else 'nestedEstimated'
                    qty = qty.copy_negate()
                rows[pid][bucket].append(qty)
            elif code:
                if code in raw and raw[code]['base_unit'] != m['base_unit']:
                    raise HTTPException(409, 'Recorded raw item units differ; reconcile before comparing')
                r = raw.setdefault(code, {'raw_item_code': code, 'base_unit': m['base_unit'], 'measured': [], 'estimated': [], 'waste': [], 'trim': [], 'unannotatedInputs': 0})
                if event.get('purpose') == 'waste': r['waste'].append(qty.copy_negate())
                else:
                    inp = next(i for i in p['inputs'] if i['recipe_line_id'] == m['recipe_line_id'])
                    r['measured' if inp['measurement_basis'] == 'measured' else 'estimated'].append(qty.copy_negate())
                    if inp['includedLossBaseQuantity'] is None: r['unannotatedInputs'] += 1
                    else: r['trim'].append(Decimal(inp['includedLossBaseQuantity']))
    prepared = []
    for row in rows.values():
        produced, measured, estimated, waste = [exact_sum(row.pop(k)) for k in ('production', 'nestedMeasured', 'nestedEstimated', 'waste')]
        a, b = Decimal(row['openingQuantity']), Decimal(row['closingQuantity'])
        depletion = exact_sum([a, produced, b.copy_negate()])
        residual = exact_sum([depletion, measured.copy_negate(), estimated.copy_negate(), waste.copy_negate()])
        row.update(openingQuantity=number(a), closingQuantity=number(b), recordedProduction=number(produced),
                   recordedNestedUseMeasured=number(measured), recordedNestedUseEstimated=number(estimated), recordedWaste=number(waste),
                   observedDepletion=number(depletion), serviceUseOrUnrecordedLoss=number(residual),
                   stockBeforeUnrecordedServiceUse=number(exact_sum([a, produced, measured.copy_negate(), estimated.copy_negate(), waste.copy_negate()])),
                   expectedClosingQuantity=None, unexplainedVariance=None,
                   flags=([ 'closing_exceeds_opening_plus_recorded_production' ] if depletion < 0 else []) + ([ 'recorded_use_exceeds_observed_depletion' ] if residual < 0 else []))
        prepared.append(row)
    raw_rows = []
    for r in raw.values():
        measured, estimated, waste, trim = [exact_sum(r.pop(k)) for k in ('measured', 'estimated', 'waste', 'trim')]
        r.update(recordedGrossPrepUseMeasured=number(measured), recordedGrossPrepUseEstimated=number(estimated), recordedStandaloneRawWaste=number(waste),
                 recordedRawExplanation=number(exact_sum([measured, estimated, waste])), annotatedIncludedTrim=number(trim), trimIsAlreadyInGrossInput=True)
        raw_rows.append(r)
    result = serial({'store_id': opening['store_id'], 'policyVersion': 'prep-period-quantity-1', 'request': body.model_dump(mode='json'),
        'opening': source(opening), 'closing': source(closing), 'timezone_name': closing['timezone_name'],
        'prepared': sorted(prepared, key=lambda x: x['product_id']), 'rawExplanations': sorted(raw_rows, key=lambda x: x['raw_item_code']),
        'includedEvents': sorted(included, key=lambda x: str(x['id'])),
        'boundaryEvents': {k: sorted(v, key=lambda x: str(x['id'])) for k,v in boundary.items()},
        'coverage': {'status': 'partial', 'recordedProductionCompleteness': 'not_verified', 'serviceUse': 'not_captured', 'sales': 'not_connected',
                     'finalVarianceAvailable': False},
        'cost': {'status': 'not_calculated', 'amount': None}, 'track1Writeback': False,
        'basis': 'Current effective facts by performed time; historical corrections/backfill change a refreshed comparison; no saved period closure'})
    return {'report': result, 'reportHash': fingerprint(result).hex()}


async def count(conn, store, ident):
    row = await conn.fetchrow("SELECT * FROM prep_inventory.observations WHERE id=$1 AND store_id=$2 AND purpose='count'", ident, store)
    if not row: raise HTTPException(404, 'Physical prep count is not at this location')
    if row['kind'] == 'void' or await conn.fetchval('SELECT 1 FROM prep_inventory.observations WHERE predecessor_id=$1', ident):
        raise HTTPException(409, 'Physical prep count changed or was voided; select its current generation')
    return dict(row)


async def preview(conn, store, body):
    await observations.ready(conn)
    opening, closing = await count(conn, store, body.opening_count_id), await count(conn, store, body.closing_count_id)
    from prep_openings import activity_time
    await activity_time(conn, store, opening['performed_at'])
    # A single repeatable-read snapshot includes active replacements at their
    # original performed time, even when corrected or backfilled much later.
    events = []
    for table, extra in [('batch_events', ''), ('observations', "AND e.purpose='waste'")]:
        events.extend(dict(x) for x in await conn.fetch(f'''SELECT * FROM prep_inventory.{table} e WHERE store_id=$1 AND kind<>'void'
            AND performed_at >= $2 AND performed_at <= $3 {extra}
            AND NOT EXISTS(SELECT 1 FROM prep_inventory.{table} n WHERE n.predecessor_id=e.id)''', store, opening['performed_at'], closing['performed_at']))
    return calculate(body, opening, closing, events)


def install_routes(router, context):
    async def pool_for(request, store):
        _, pool = await context(request, store, True)  # existing manager authority
        if not observations.enabled(): raise HTTPException(503, 'Prep count-period comparisons are awaiting enablement')
        return pool

    @router.get('/{store_id}/prep-periods/counts')
    async def counts(store_id: str, request: Request):
        pool = await pool_for(request, store_id)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read', readonly=True):
                await observations.ready(conn)
                rows = await conn.fetch('''SELECT id,root_id,revision,performed_at,business_date,timezone_name,
                    review_snapshot->'scope' AS scope,review_snapshot->'definitions' AS definitions FROM prep_inventory.observations e
                    WHERE store_id=$1 AND purpose='count' AND kind<>'void'
                    AND NOT EXISTS(SELECT 1 FROM prep_inventory.observations n WHERE n.predecessor_id=e.id) ORDER BY performed_at,id''', store_id)
                return serial({'store_id': store_id, 'counts': [dict(x) for x in rows]})

    @router.post('/{store_id}/prep-periods/preview')
    async def report(store_id: str, body: PeriodIn, request: Request):
        pool = await pool_for(request, store_id)
        async with pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read', readonly=True): return await preview(conn, store_id, body)
