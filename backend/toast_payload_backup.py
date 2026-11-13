"""Monthly encrypted backups of the raw Toast report rows that a main backup leaves out.

A main backup made with split_tables=(SPLIT_TABLE,) keeps that table's definition, its links and
the ids of its rows, but not the rows: on 2026-11-12 the 746 MB of raw Toast reports made the
dump run past 20 minutes and the pooler cut it off. Those rows go here instead, one encrypted
file per business month, each read in its own short read-only snapshot.

Each file holds one line per row: the row as `to_jsonb(row)::text` (which never contains a
raw newline), with the session normalized as the backup fingerprint normalizes it. The manifest
records the row count and the row digest of hosted_backup.ROW_ALGORITHM over those lines.

Take the monthly files after the main backup: a restore check needs every row id the main
backup lists, and loads only those (a row saved after the main backup is skipped). Old months
do not change, so earlier monthly files can be reused while they still cover the ids.

Row data, connection errors and SQL text are never printed or attached to results.
"""
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import asyncpg
from cryptography.fernet import Fernet

import hosted_backup as backup
from hosted_backup import BackupError
import native_backup as native
from readonly_snapshot import readonly_snapshot

FORMAT = 'jaymax-encrypted-table-month-v1'
TABLE = backup.SPLIT_TABLE
QUOTED = '"integrations"."toast_report_payloads"'
MAX_MONTHS = 120
# One month's file is decrypted into memory for checking and loading (a busy month is ~100 MB).
MAX_MONTH_ARCHIVE = 1024 * 1024 * 1024
INSERT_BATCH = 50
EXPORT_BATCH = 10  # rows per export query; October 2026 rows are about 2 MB each as text
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
# The same session normalization as hosted_backup.fingerprint, so a row's text (dates and
# times above all) is the same when it is exported and when a restore check re-reads it.
NORMALIZE = ("SET LOCAL quote_all_identifiers=off; SET LOCAL TIME ZONE 'UTC'; SET LOCAL search_path=pg_catalog; "
             "SET LOCAL DateStyle='ISO,YMD'; SET LOCAL IntervalStyle=postgres; SET LOCAL bytea_output=hex; "
             "SET LOCAL extra_float_digits=3; SET LOCAL standard_conforming_strings=on; SET LOCAL row_security=off")


def month_range(month):
    """'YYYY-MM' -> (first day, first day of the next month)."""
    match = re.fullmatch(r'(20\d\d)-(\d\d)', month) if isinstance(month, str) else None
    if not match or not 1 <= int(match[2]) <= 12:
        raise BackupError('Month must be YYYY-MM')
    start = date(int(match[1]), int(match[2]), 1)
    return start, date(start.year + start.month // 12, start.month % 12 + 1, 1)


def month_span(first, last):
    """Every month from first to last, inclusive."""
    start, _ = month_range(first)
    stop, _ = month_range(last)
    if stop < start:
        raise BackupError('The last month comes before the first')
    months, current = [], start
    while current <= stop:
        months.append(current.strftime('%Y-%m'))
        current = month_range(months[-1])[1]
    if len(months) > MAX_MONTHS:
        raise BackupError(f'At most {MAX_MONTHS} months at a time')
    return months


def rows_digest(hashes):
    return backup.digest(''.join(h + '\n' for h in sorted(hashes)).encode())


def accepted(project, month=None):
    def check(manifest):
        return (manifest['format'] == FORMAT and manifest['projectRef'] == project and manifest['table'] == TABLE
                and manifest['rowFingerprintAlgorithm'] == backup.ROW_ALGORITHM
                and month_range(manifest['month']) is not None and (month is None or manifest['month'] == month)
                and type(manifest['rows']) is int and manifest['rows'] >= 0
                and isinstance(manifest['rowsSha256'], str) and re.fullmatch(r'[0-9a-f]{64}', manifest['rowsSha256']))
    return check


def read_month(path, key, project):
    """Authenticate one monthly file and check every row against its manifest.
    Returns (manifest, rows) where rows maps row id -> (row text, row hash)."""
    parts = []
    manifest = backup.decrypt_stream(path, key, accepted(project), parts.append, max_archive=MAX_MONTH_ARCHIVE)
    data = b''.join(parts)
    lines = data.split(b'\n')
    if lines[-1] != b'':
        raise BackupError('Monthly backup rows are not complete lines')
    start, end = month_range(manifest['month'])
    rows, hashes = {}, []
    for line in lines[:-1]:
        try:
            text = line.decode('utf-8')
            value = json.loads(text)
            row_id, business_date = value['id'], date.fromisoformat(value['business_date'])
        except (UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
            raise BackupError('Unreadable row in monthly backup') from exc
        if not isinstance(row_id, str) or not UUID.fullmatch(row_id) or row_id in rows:
            raise BackupError('Missing or repeated row id in monthly backup')
        if not start <= business_date < end:
            raise BackupError('Row outside its month in monthly backup')
        row_hash = backup.digest(line)
        rows[row_id] = (text, row_hash)
        hashes.append(row_hash)
    if len(rows) != manifest['rows'] or rows_digest(hashes) != manifest['rowsSha256']:
        raise BackupError('Monthly backup rows differ from its manifest')
    return manifest, rows


async def export_months(url, project, months, backup_directory, key_directory):
    """One encrypted file per month, all under one new key. Read-only on the source."""
    settings = backup.hosted_connection(url, project)  # Refuses anything but the reviewed pooler login.
    del settings
    if not isinstance(months, (list, tuple)) or not months or len(months) > MAX_MONTHS or len(set(months)) != len(months):
        raise BackupError('Months required, each once')
    for month in months:
        month_range(month)
    directory = backup.private_directory(backup_directory, 'backups')
    key_path = backup.private_directory(key_directory, 'credentials') / 'payloads.key'
    key = Fernet.generate_key()
    with key_path.open('xb') as stream:
        stream.write(key)
    results = []
    for month in months:
        results.append(await export_month(url, project, month, directory, key, key_path))
    return {'status': 'exported_not_restore_verified', 'table': TABLE, 'privateKey': str(key_path),
            'months': results, 'rows': sum(r['rows'] for r in results), 'sourceReadOnly': True}


async def connect(url):
    return await asyncpg.connect(url, ssl=backup.connection_tls(url), timeout=backup.CONNECT_TIMEOUT_SECONDS,
        command_timeout=backup.COMMAND_TIMEOUT_SECONDS, statement_cache_size=0,
        server_settings={'application_name': 'jaymax_payload_backup'})


async def export_month(url, project, month, directory, key, key_path):
    start, end = month_range(month)
    raw = directory / f'payloads-{month}.partial'
    candidate = directory / f'payloads-{month}.partial.enc'
    final = directory / f'payloads-{month}.jmax.enc'
    conn = None
    published = False
    try:
        conn = await connect(url)
        await native.configure(conn)
        hashes = []
        async with readonly_snapshot(conn, rollback_timeout=backup.CLEANUP_TIMEOUT_SECONDS):
            await conn.execute(NORMALIZE)
            # Ids first (cheap), then the rows a batch at a time in the same snapshot. One query over a
            # whole month built and sorted every report before returning any, which ran past the
            # per-query timeout for October 2026 in production (2026-11-13).
            ids = [row['id'] for row in await conn.fetch(
                f'SELECT t.id FROM {QUOTED} t WHERE t.business_date >= $1 AND t.business_date < $2 ORDER BY t.id',
                start, end)]
            with raw.open('xb') as out:
                for offset in range(0, len(ids), EXPORT_BATCH):
                    batch = ids[offset:offset + EXPORT_BATCH]
                    rows = await conn.fetch(f'SELECT to_jsonb(t)::text AS value FROM {QUOTED} t '
                                            'WHERE t.id = ANY($1::uuid[]) ORDER BY t.id', batch)
                    if len(rows) != len(batch):
                        raise BackupError('Rows changed inside the snapshot')
                    for row in rows:
                        value = row['value']
                        if not isinstance(value, str) or '\n' in value:
                            raise BackupError('Unexpected row text')
                        line = value.encode('utf-8')
                        out.write(line + b'\n')
                        hashes.append(backup.digest(line))
            server_version = await conn.fetchval('SHOW server_version_num')
        archive_bytes, archive_sha256 = backup.file_digest(raw)
        manifest = {'format': FORMAT, 'projectRef': project, 'table': TABLE, 'month': month,
                    'rowFingerprintAlgorithm': backup.ROW_ALGORITHM, 'rows': len(hashes), 'rowsSha256': rows_digest(hashes),
                    'serverVersionNum': server_version, 'createdAt': datetime.now(timezone.utc).isoformat(),
                    'archiveBytes': archive_bytes, 'archiveSha256': archive_sha256}
        backup.write_stream_envelope(candidate, key, manifest, raw)
        checked, _ = read_month(candidate, key_path, project)
        if checked != manifest:
            raise BackupError('Encrypted readback mismatch')
        encrypted_sha256 = backup.file_digest(candidate)[1]
        candidate.rename(final)
        published = True
        return {'month': month, 'rows': len(hashes), 'file': str(final), 'encryptedSha256': encrypted_sha256,
                'rowsSha256': manifest['rowsSha256']}
    finally:
        try:
            if conn is not None:
                await conn.close(timeout=backup.CLEANUP_TIMEOUT_SECONDS)
        finally:
            await backup.remove_partial_files((raw,) if published else (raw, candidate))


def verify_months(files, key, project):
    """Check monthly files without a database: authentic, complete, one file per month."""
    seen = {}
    for path in files:
        manifest, _ = read_month(path, key, project)
        if manifest['month'] in seen:
            raise BackupError('Two files for one month')
        seen[manifest['month']] = manifest['rows']
    return {'status': 'monthly_backups_verified', 'table': TABLE, 'months': dict(sorted(seen.items())),
            'rows': sum(seen.values())}


def wanted_ids(manifest):
    """The row ids a split main backup needs, checked against its own fingerprint."""
    ids = manifest.get('separateTableRowIds', {}).get(TABLE)
    fact = manifest['tables'].get(TABLE, {})
    if (not isinstance(ids, list) or not all(isinstance(i, str) and UUID.fullmatch(i) for i in ids)
            or len(set(ids)) != len(ids) or not fact.get('rowsInSeparateBackups') or fact.get('rows') != len(ids)
            or fact.get('idsSha256') != backup.digest(''.join(i + '\n' for i in sorted(ids)).encode())):
        raise BackupError('Main backup row id list does not match its fingerprint')
    return set(ids)


async def load_rows(conn, manifest, payload_backups, project):
    """Insert exactly the main backup's rows from the monthly files into a disposable restore,
    before its links are restored, then check every inserted row reads back unchanged."""
    wanted = wanted_ids(manifest)
    loaded = {}
    months = set()
    for path, key in payload_backups:
        month_manifest, rows = read_month(path, key, project)
        if month_manifest['month'] in months:
            raise BackupError('Two files for one month')
        months.add(month_manifest['month'])
        chosen = [(row_id, item) for row_id, item in rows.items() if row_id in wanted]
        for start in range(0, len(chosen), INSERT_BATCH):
            batch = chosen[start:start + INSERT_BATCH]
            await conn.execute(f'INSERT INTO {QUOTED} SELECT (jsonb_populate_record(NULL::{QUOTED}, value::jsonb)).* '
                               'FROM unnest($1::text[]) value', [text for _, (text, _) in batch])
        loaded.update((row_id, row_hash) for row_id, (_, row_hash) in chosen)
    missing = len(wanted - set(loaded))
    if missing:
        error = BackupError(f'The monthly backups are missing {missing} rows the main backup needs')
        error.missingRows = missing
        raise error
    async with conn.transaction():
        await conn.execute(NORMALIZE)
        restored = {}
        async for row in conn.cursor(f"SELECT t.id::text AS id, encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS value "
                                     f'FROM {QUOTED} t', prefetch=1000):
            restored[row['id']] = row['value']
    if restored != loaded:
        raise BackupError('Restored rows differ from the monthly backups')
    return {'rowsLoaded': len(loaded), 'monthsRead': len(months)}
