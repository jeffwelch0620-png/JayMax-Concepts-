"""Lossless vendor CSV parsing. Source capture happens before this module runs.

Original bytes and positional cells are authoritative. Typed fields are a versioned
projection, never a replacement for blank, duplicate or currently unknown fields.
"""
import csv
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, Inexact, localcontext
from pathlib import Path

PARSER_VERSION = 'vendor-csv-v1'
FIELD_MAP = json.loads(Path(__file__).with_name('purchase_fields.json').read_text(encoding='utf-8'))
VENDOR_IDS = {'PFG': 'pfg', 'US Foods': 'us_foods'}
NUMERIC = re.compile(r'^[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$')


def json_value(value):
    if isinstance(value, (Decimal, date)):
        return str(value)
    if isinstance(value, dict):
        return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    return value


def fingerprint(value):
    return hashlib.sha256(json.dumps(json_value(value), sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')).digest()


def typed(value, kind):
    if kind == 'text':
        return value
    if value is None or not value.strip():
        return None
    raw = value.strip()
    if kind == 'numeric':
        if not NUMERIC.fullmatch(raw):
            raise ValueError('Expected a decimal number')
        result = Decimal(raw.replace(',', ''))
        if not result.is_finite():
            raise ValueError('Number must be finite')
        return result
    for fmt in ('%m/%d/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    raise ValueError('Expected a calendar date')


def decode_source(source):
    try:
        return source.decode('utf-8-sig'), 'utf-8-sig'
    except UnicodeDecodeError:
        return source.decode('cp1252'), 'cp1252'


def parse_csv(source):
    result = {'headers': [], 'rows': [], 'errors': [], 'documents': [],
              'vendor': None, 'encoding': None, 'parserVersion': PARSER_VERSION}
    try:
        text, result['encoding'] = decode_source(source)
        reader = csv.reader(io.StringIO(text, newline=''), strict=True)
        result['headers'] = next(reader, [])
        for ordinal, values in enumerate(reader, 1):
            errors = [] if len(values) == len(result['headers']) else ['Column count differs from the header']
            result['rows'].append({'ordinal': ordinal, 'values': values, 'errors': errors})
    except (UnicodeError, csv.Error) as exc:
        result['errors'].append(f'Cannot finish parsing this file: {exc}')
    if not result['headers']:
        result['errors'].append('No CSV header found')
        return result
    names = [h.strip() for h in result['headers']]
    found = set(names)
    if {'Product #', 'Customer OpCo', 'Invoice Number'} <= found:
        result['vendor'] = 'PFG'
    elif {'ProductNumber', 'DocumentNumber', 'PricingUnit'} <= found:
        result['vendor'] = 'US Foods'
    else:
        result['errors'].append('Format is not yet supported; original data is retained')
        return result
    return normalize(result, names)


def normalize(result, names):
    vendor = result['vendor']
    occurrences = Counter()
    positions = {}
    raw_keys = []
    for index, name in enumerate(names):
        occurrences[name] += 1
        positions[name, occurrences[name]] = index
        raw_keys.append((name, occurrences[name]))
    specs = [s for s in FIELD_MAP if s['vendor'] == vendor]
    expected_occurrences = Counter(s['header'] for s in specs)
    duplicates = [name for name, n in occurrences.items()
                  if name in expected_occurrences and n > expected_occurrences[name]]
    if duplicates:
        result['errors'].append('Ambiguous repeated fields: ' + ', '.join(duplicates))
    grouped = defaultdict(list)
    for row in result['rows']:
        if not any(v.strip() for v in row['values']):
            continue  # Retained in raw_rows, but not an invoice line.
        projections = {'documents': {}, 'lines': {}, 'parties': {}}
        errors = list(row['errors'])
        for spec in specs:
            position = positions.get((spec['header'], spec['occurrence']))
            value = row['values'][position] if position is not None and position < len(row['values']) else None
            try:
                value = typed(value, spec['type'])
            except (ValueError, InvalidOperation):
                errors.append(f"Invalid {spec['header']} at source record {row['ordinal']}")
                value = None
            parts = spec['target'].split('.')
            if parts[0] == 'parties':
                projections['parties'].setdefault(parts[1], {})[parts[2]] = value
            else:
                projections[parts[0]][parts[1]] = value
        header = projections['documents']
        number = (header.get('document_number') or '').strip()
        dtype_raw = (header.get('document_type_raw') or '').strip().lower()
        dtype = {'invoice': 'invoice', 'credit': 'credit', 'credit memo': 'credit',
                 'creditmemo': 'credit', 'credit_memo': 'credit'}.get(dtype_raw)
        customer = (header.get('customer_number') or '').strip()
        branch = (header.get('vendor_branch_reference') or '').strip()
        account = (header.get('account_number') or '').strip()
        if not number or not customer or not branch or not dtype:
            row['errors'].append('Missing or unsupported document identity; source retained')
            result['errors'].append('One or more source records need document identity review')
            continue
        identity = (VENDOR_IDS[vendor], branch, json.dumps([customer, account], separators=(',', ':')), dtype, number)
        raw = sorted([[name, occurrence, row['values'][i] if i < len(row['values']) else None]
                      for i, (name, occurrence) in enumerate(raw_keys)], key=lambda x: (x[0], x[1]))
        grouped[identity].append({'sourceOrdinal': row['ordinal'], 'header': header,
                                 'line': projections['lines'], 'parties': projections['parties'],
                                 'raw': raw, 'errors': errors})
    for identity, records in grouped.items():
        header, parties = records[0]['header'], records[0]['parties']
        errors = list(result['errors'])
        for record in records:
            errors.extend(record['errors'])
            if record['header'] != header or record['parties'] != parties:
                errors.append('Repeated document headers or party details disagree')
        if header.get('invoice_date') is None:
            errors.append('Missing supplier invoice date')
        # Stable ordering and multiplicity: overlapping/reordered files map to the
        # same version, while two identical SKU rows remain two distinct records.
        ordered = sorted(records, key=lambda r: json.dumps(json_value(r['raw']), ensure_ascii=False))
        lines = []
        for ordinal, record in enumerate(ordered, 1):
            lines.append({'ordinal': ordinal, 'sourceOrdinal': record['sourceOrdinal'],
                          'fields': record['line'], 'errors': record['errors']})
        result['documents'].append({'identity': identity, 'header': header, 'parties': parties,
                                    'lines': lines, 'fingerprint': fingerprint([r['raw'] for r in ordered]),
                                    'errors': sorted(set(errors)), 'vendor': vendor})
    if not result['documents']:
        result['errors'].append('No complete document identities could be read')
    return result


def document_totals(header, lines):
    # Never round an imbalance into a balanced invoice.
    try:
        with localcontext() as ctx:
            ctx.prec=80
            ctx.traps[Inexact]=True
            return _document_totals(header,lines)
    except ArithmeticError:
        return {'status':'held','errors':['Invoice arithmetic exceeds supported exact precision'],
                'lineTotal':None,'expectedTotal':None,'statedTotal':None,'difference':None}


def _document_totals(header, lines):
    errors = []
    amounts = [line.get('extended_amount_source') for line in lines]
    if any(a is None for a in amounts):
        return {'status': 'held', 'errors': ['Missing line amounts'], 'lineTotal': None,
                'expectedTotal': None, 'statedTotal': None, 'difference': None}
    line_total = sum(amounts, Decimal(0))
    stated = header.get('total_source')
    if stated is not None:
        fee, tax, discount = [header.get(k) for k in ('fees_source', 'tax_source', 'discount_source')]
        expected = None if any(v is None for v in (fee, tax, discount)) else line_total + fee + tax - discount
        if expected is None:
            errors.append('Missing invoice total components')
        if discount not in (None, 0):
            errors.append('Invoice-level discount needs a verified allocation policy')
        subtotal = header.get('subtotal_source')
        if subtotal is not None and subtotal != line_total:
            errors.append('Invoice subtotal differs from merchandise lines')
    else:
        stated = header.get('net_after_adjustment_source')
        expected = line_total
        if header.get('delivery_adjustment_source') != 0:
            errors.append('Delivery adjustment needs a verified interpretation')
        if header.get('net_before_adjustment_source') != stated:
            errors.append('Before/after adjustment totals need review')
    if stated is None:
        errors.append('Missing supplier document total')
    difference = None if stated is None or expected is None else stated - expected
    if difference != 0:
        errors.append('Supplier total has an unexplained difference')
    return {'status': 'held' if errors else 'balanced', 'errors': errors,
            'lineTotal': line_total, 'expectedTotal': expected,
            'statedTotal': stated, 'difference': difference}
