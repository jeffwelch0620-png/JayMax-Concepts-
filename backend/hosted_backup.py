"""Encrypted application-scope export and disposable-only PostgreSQL restore.

No operational restore, managed-service recovery, scheduling or cloud sync.
Connection errors and dump stderr must never be printed or attached to receipts.
"""
import asyncio
import base64
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import asyncpg
from cryptography.fernet import Fernet
from db_tls import connection_tls, DEFAULT_CA
import native_backup as native
from readonly_snapshot import readonly_snapshot, preserve_cleanup_failure


async def remove_partial_files(paths):
    """Attempt every fixed temporary file even if an earlier unlink fails."""
    failure = None
    for path in paths:
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            if failure is None:
                failure = exc
    if failure is not None:
        raise failure

SCHEMAS = ('public', 'purchasing', 'actual_inventory', 'prep_inventory', 'integrations', 'supabase_migrations')
MANAGED = {'auth', 'cron', 'extensions', 'graphql', 'graphql_public', 'net', 'realtime', 'storage', 'vault'}
FORMAT = 'jaymax-encrypted-application-backup-v1'
ROW_ALGORITHM = 'sha256-sorted-sha256-canonical-jsonb-utf8-v1'
# Each modern row contributes 64 ASCII hex bytes plus one LF. Bound the
# aggregation input, including the sentinel row used to select cursor fallback.
# This is not a bound on all PostgreSQL sorting/JSON workspace memory.
MAX_FINGERPRINT_AGGREGATE_BYTES = 8 * 1024 * 1024
ROW_HASH_LINE_BYTES = 65
FINGERPRINT_PATHS = ('serverAggregateRelations', 'cursorFallbackRelations', 'cursorOnlyRelations')
MAX_ARCHIVE = 64 * 1024 * 1024  # Bounded build tool; larger backups need streaming encryption.
MAX_ENVELOPE = 3 * MAX_ARCHIVE
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
CONNECT_TIMEOUT_SECONDS = 20
COMMAND_TIMEOUT_SECONDS = 60
TOOL_TIMEOUT_SECONDS = 240
EXPORT_TIMEOUT_SECONDS = 600
CLEANUP_TIMEOUT_SECONDS = 5
PROGRESS_INTERVAL_SECONDS = 5
EXPORT_CONTROL = ContextVar('jaymax_backup_export_control', default=None)
LIMIT_NAMES = ('idle_in_transaction_session_timeout', 'statement_timeout',
    'idle_session_timeout', 'transaction_timeout', 'tcp_keepalives_idle',
    'tcp_keepalives_interval', 'tcp_keepalives_count', 'tcp_user_timeout')
EXPORT_PHASES = frozenset(('connect', 'effective_limits', 'snapshot_total', 'schema_check',
    'export_snapshot', 'fingerprint', 'dependencies', 'role_metadata', 'pg_dump',
    'sequence_recheck', 'manifest', 'encrypt', 'read_back', 'archive_list',
    'connection_close', 'partial_cleanup', 'publish'))


def safe_export_diagnostics(value):
    """Allow fixed labels/numbers and a hex run reference; never trust attached dictionaries."""
    if not isinstance(value, dict) or value.get('format') != 'jaymax-backup-diagnostics-v1':
        return None
    def duration(number):
        return (isinstance(number, (int, float)) and not isinstance(number, bool)
                and 0 <= number <= 10**9 and math.isfinite(number))
    phases = value.get('phases', [])
    safe = {'format': value['format'], 'phases': [], 'serverLimits': {}, 'clientLimits': {}}
    reference = value.get('exportReference')
    if isinstance(reference, str) and re.fullmatch(r'[a-f0-9]{32}', reference):
        safe['exportReference'] = reference
    if duration(value.get('totalElapsedSeconds')):
        safe['totalElapsedSeconds'] = value['totalElapsedSeconds']
    if isinstance(phases, list):
        for phase in phases[:32]:
            if (isinstance(phase, dict) and isinstance(phase.get('phase'), str) and phase['phase'] in EXPORT_PHASES
                    and duration(phase.get('elapsedSeconds')) and phase.get('outcome') in ('passed', 'held')):
                safe['phases'].append({key: phase[key] for key in ('phase', 'elapsedSeconds', 'outcome')})
    limits = value.get('serverLimits', {})
    if isinstance(limits, dict):
        for name in LIMIT_NAMES:
            item = limits.get(name)
            if (isinstance(item, dict) and isinstance(item.get('value'), int)
                    and not isinstance(item['value'], bool) and -10**18 <= item['value'] <= 10**18
                    and item.get('unit') in (None, 'ms', 's', 'min', 'h')):
                safe['serverLimits'][name] = {'value': item['value'], 'unit': item.get('unit')}
    clients = value.get('clientLimits', {})
    if isinstance(clients, dict):
        for name in ('connectSeconds', 'commandSeconds', 'subprocessSeconds', 'exportSeconds', 'cleanupSeconds'):
            if duration(clients.get(name)):
                safe['clientLimits'][name] = clients[name]
    safe['serverLimitsNotCaptured'] = [name for name in LIMIT_NAMES if name not in safe['serverLimits']]
    if isinstance(value.get('limitReadHeld'), bool):
        safe['limitReadHeld'] = value['limitReadHeld']
    paths = value.get('fingerprintPaths')
    if isinstance(paths, dict):
        safe['fingerprintPaths'] = {name: paths[name] for name in FINGERPRINT_PATHS
            if isinstance(paths.get(name), int) and not isinstance(paths[name], bool)
            and 0 <= paths[name] <= 10**9}
    for name in ('deadlineExceeded', 'ownedConnectionTerminated', 'ownedConnectionClosed', 'progressReportingHeld'):
        if isinstance(value.get(name), bool):
            safe[name] = value[name]
    return safe


def safe_export_artifacts(value):
    """Fixed presence flags only; never expose paths or key contents."""
    if not isinstance(value, dict):
        return None
    safe = {name: value[name] for name in ('privateKeyRetained', 'encryptedPartialRetained',
        'rawPartialRetained', 'finalBackupPresent', 'artifactInspectionHeld')
        if isinstance(value.get(name), bool)}
    return safe or None


class ExportDiagnostics:
    def __init__(self, timeout_seconds=EXPORT_TIMEOUT_SECONDS, progress=None):
        self.started = time.monotonic()
        self.phases = []
        self.server_limits = {}
        self.limit_read_held = False
        self.timeout_seconds = timeout_seconds
        self.progress = progress
        self.active = []
        self.deadline_exceeded = False
        self.connection_terminated = False
        self.connection_closed = False
        self.progress_held = False
        self.export_reference = uuid4().hex
        self.fingerprint_paths = dict.fromkeys(FINGERPRINT_PATHS, 0)

    def emit(self, phase, state):
        # Only fixed phase/state labels and monotonic elapsed time leave the tool.
        if self.progress is not None:
            try:
                self.progress({'format':'jaymax-backup-progress-v1', 'phase':phase, 'state':state,
                    'exportReference':self.export_reference,
                    'elapsedSeconds':round(time.monotonic()-self.started, 6)})
            except Exception:
                self.progress_held = True

    @contextmanager
    def phase(self, name):
        if name not in EXPORT_PHASES:
            raise ValueError('Unsupported export phase')
        started = time.monotonic()
        outcome = 'passed'
        self.active.append(name)
        self.emit(name, 'started')
        try:
            yield
        except BaseException:
            outcome = 'held'
            raise
        finally:
            self.active.pop()
            self.phases.append({'phase': name, 'elapsedSeconds': round(time.monotonic()-started, 6),
                                'outcome': outcome})
            self.emit(name, outcome)

    async def read_limits(self, conn):
        # Observe effective settings after the existing native.configure call.
        # No SET, ALTER ROLE or endpoint changes are introduced by diagnostics.
        rows = await conn.fetch('SELECT name,setting,unit FROM pg_settings WHERE name=ANY($1::text[])', list(LIMIT_NAMES))
        for row in rows:
            name, setting, unit = row['name'], row['setting'], row['unit']
            if name not in LIMIT_NAMES:
                continue
            # Socket getters on the Windows test server can report -1. Preserve
            # signed observations; do not reinterpret them as usable durations.
            if (not isinstance(setting, str) or not re.fullmatch(r'-?[0-9]{1,19}', setting)
                    or abs(int(setting)) > 10**18 or unit not in (None, 'ms', 's', 'min', 'h')):
                self.limit_read_held = True
                continue
            self.server_limits[name] = {'value': int(setting), 'unit': unit}

    def report(self):
        return safe_export_diagnostics({'format':'jaymax-backup-diagnostics-v1',
            'exportReference':self.export_reference,
            'fingerprintPaths':self.fingerprint_paths,
            'totalElapsedSeconds':round(time.monotonic()-self.started, 6),
            'phases':self.phases, 'serverLimits':self.server_limits, 'limitReadHeld':self.limit_read_held,
            'deadlineExceeded':self.deadline_exceeded, 'ownedConnectionTerminated':self.connection_terminated,
            'ownedConnectionClosed':self.connection_closed,
            'progressReportingHeld':self.progress_held,
            'clientLimits':{'connectSeconds':CONNECT_TIMEOUT_SECONDS, 'commandSeconds':COMMAND_TIMEOUT_SECONDS,
                            'subprocessSeconds':TOOL_TIMEOUT_SECONDS, 'exportSeconds':self.timeout_seconds,
                            'cleanupSeconds':CLEANUP_TIMEOUT_SECONDS}})


class ExportControl:
    """Own exactly one export connection; never select or terminate other sessions."""
    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
        self.application_name = 'jaymax-backup-' + diagnostics.export_reference
        self.connection = None
        self.termination_error = None
        self.tool_cleanup_held = False
        self.close_task = None
        self.stop_started = False

    async def close_owned(self):
        if self.connection is None:
            return
        if self.close_task is None:
            self.close_task = asyncio.create_task(self._close_owned())
        await asyncio.shield(self.close_task)

    async def _close_owned(self):
        try:
            # asyncpg's graceful close cancels an active server command before
            # sending Terminate. A transport abort alone leaves pg_sleep (and
            # real queries) alive until the backend next notices a dead socket.
            await asyncio.wait_for(self.connection.close(timeout=CLEANUP_TIMEOUT_SECONDS), CLEANUP_TIMEOUT_SECONDS)
            self.diagnostics.connection_closed = True
        except BaseException:
            self.abort()
            raise

    async def stop(self, worker):
        if not self.stop_started:
            self.stop_started = True
            # Keep the protocol alive for its cancellation request; graceful
            # close and bounded rollback share one owned close task.
            worker.cancel()
        try:
            await self.close_owned()
        except Exception:
            # The worker awaits the same close task in its protected cleanup,
            # preserving the original failure and recording the close category.
            pass

    def abort(self):
        if self.connection is not None:
            try:
                self.connection.terminate()
                self.diagnostics.connection_terminated = True
            except Exception as error:
                self.termination_error = type(error).__name__

    def check_deadline(self):
        if time.monotonic()-self.diagnostics.started >= self.diagnostics.timeout_seconds:
            self.diagnostics.deadline_exceeded = True
            self.abort()
            raise BackupError('Overall backup export deadline exceeded')

    async def watch(self, worker):
        while not worker.done():
            remaining = self.diagnostics.timeout_seconds - (time.monotonic()-self.diagnostics.started)
            if remaining <= 0:
                self.diagnostics.deadline_exceeded = True
                await self.stop(worker)
                return
            await asyncio.sleep(min(PROGRESS_INTERVAL_SECONDS, remaining))
            if self.diagnostics.active:
                self.diagnostics.emit(self.diagnostics.active[-1], 'running')


class BackupError(RuntimeError):
    """Safe category only: do not include source rows, URLs, SQL or driver text."""


def digest(value):
    return hashlib.sha256(value).hexdigest()


def hosted_connection(url, project):
    if not re.fullmatch(r'[a-z0-9]{20}', project):
        raise BackupError('Expected project reference required')
    u = urlsplit(url)
    if (u.scheme not in ('postgres', 'postgresql') or not u.username or not u.password
            or u.hostname is None or not u.hostname.endswith('.pooler.supabase.com')
            or u.port != 5432 or u.path != '/postgres' or u.query or u.fragment
            or unquote(u.username) != 'postgres.' + project):
        raise BackupError('Reviewed owner session-pooler connection required')
    return {'host': u.hostname, 'port': u.port, 'user': unquote(u.username),
            'password': unquote(u.password), 'database': 'postgres'}


def private_directory(path, area):
    """Fresh child directory with current-user and SYSTEM ACLs, outside synced paths."""
    if os.name != 'nt' or area not in ('backups', 'credentials'):
        raise BackupError('Windows private-directory verification required')
    root = Path(os.environ['LOCALAPPDATA']) / 'JayMaxBuild' / area
    path = Path(path)
    if (not path.is_absolute() or path.parent != root or path.exists()
            or not re.fullmatch(r'backup-[a-f0-9]{32}', path.name)):
        raise BackupError('Fresh private backup directory required')
    for parent in (root, root.parent):
        if parent.is_symlink() or parent.is_junction():
            raise BackupError('Redirected private directory refused')
    shell = shutil.which('pwsh')
    if not shell:
        raise BackupError('PowerShell 7 required')
    root.mkdir(parents=True, exist_ok=True)
    path.mkdir()
    script = '''$ErrorActionPreference='Stop'; $p=$env:JAYMAX_BACKUP_PRIVATE;
      $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User;
      $acl=[Security.AccessControl.DirectorySecurity]::new();
      $acl.SetOwner($sid); $acl.SetAccessRuleProtection($true,$false);
      foreach($id in @($sid.Value,'S-1-5-18')) {
        $identity=[Security.Principal.SecurityIdentifier]::new($id);
        $rule=[Security.AccessControl.FileSystemAccessRule]::new($identity,'FullControl','ContainerInherit,ObjectInherit','None','Allow');
        $acl.AddAccessRule($rule) };
      Set-Acl -LiteralPath $p -AclObject $acl;
      $actual=Get-Acl -LiteralPath $p;
      $ids=@($actual.Access | ForEach-Object {$_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value} | Sort-Object -Unique);
      $expected=@($sid.Value,'S-1-5-18') | Sort-Object -Unique;
      if (-not $actual.AreAccessRulesProtected -or $actual.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $sid.Value -or
        ($ids -join ',') -ne ($expected -join ',')) {exit 2}; Write-Output 'verified' '''
    checked = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-Command', script],
        env={**os.environ, 'JAYMAX_BACKUP_PRIVATE': str(path)}, capture_output=True, timeout=20, creationflags=FLAGS)
    if checked.returncode or checked.stdout.strip() != b'verified':
        raise BackupError('Private directory ACL held')
    return path


def process_env(settings, remote):
    env = {key: value for key, value in os.environ.items() if not key.startswith('PG')}
    env.update(PGHOST=settings['host'], PGPORT=str(settings['port']), PGUSER=settings['user'],
        PGPASSWORD=settings['password'], PGDATABASE=settings['database'], PGCONNECT_TIMEOUT='20',
        PGCLIENTENCODING='UTF8', PGSSLMODE='verify-full' if remote else 'disable')
    if remote:
        env.update(PGSSLROOTCERT=os.environ.get('DATABASE_SSL_ROOT_CERT', str(DEFAULT_CA)),
                   PGOPTIONS='-c default_transaction_read_only=on')
        if 'hostaddr' in settings:
            from maintenance_connection import ipv6_address
            env['PGHOSTADDR'] = ipv6_address(settings['hostaddr'])
    control = EXPORT_CONTROL.get()
    if control is not None:
        env['PGAPPNAME'] = control.application_name + '-tool'
    return env


async def tool(executable, args, settings=None, remote=False):
    # Popen gives this coroutine ownership before its first cancellation point.
    # A cancelled to_thread(subprocess.run) used to leave pg_dump writing after
    # partial-file cleanup. Kill and reap this exact child before unwinding.
    process = subprocess.Popen([str(executable), *args],
        env=process_env(settings, remote) if settings else os.environ.copy(),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=FLAGS)
    communication = asyncio.create_task(asyncio.to_thread(process.communicate))
    try:
        stdout, stderr = await asyncio.wait_for(asyncio.shield(communication), TOOL_TIMEOUT_SECONDS)
    except BaseException as original:
        try:
            if process.poll() is None:
                process.kill()
            await asyncio.wait_for(asyncio.shield(communication), CLEANUP_TIMEOUT_SECONDS)
        except BaseException as cleanup:
            original.subprocessCleanupErrorType = type(cleanup).__name__
            control = EXPORT_CONTROL.get()
            if control is not None:
                control.tool_cleanup_held = True
        raise
    if process.returncode:
        error = BackupError('PostgreSQL tool failed; private diagnostic text withheld')
        error.toolErrorCategories = [label for phrase, label in (
            (b'already exists', 'existing_object'), (b'does not exist', 'missing_dependency'),
            (b'permission denied', 'permission'), (b'must be owner', 'ownership'),
            (b'unrecognized configuration parameter', 'configuration'), (b'version mismatch', 'version'))
            if phrase in stderr]
        raise error
    return stdout


def record_fingerprint_path(path):
    # Export-owned counters only: no names, rows or changes to archived facts.
    control = EXPORT_CONTROL.get()
    if control is not None:
        control.diagnostics.fingerprint_paths[path] += 1


async def relation_fingerprint(conn, quoted, kind, row_hashes=True, *, server_aggregation=True):
    path = 'cursorOnlyRelations'
    if kind != 'S' and row_hashes and server_aggregation:
        probe_rows = MAX_FINGERPRINT_AGGREGATE_BYTES // ROW_HASH_LINE_BYTES
        if probe_rows < 1:
            raise BackupError('Fingerprint aggregate bound must allow a row')
        # LIMIT bounds the aggregate even when this table is far larger than the
        # limit. A full probe is inconclusive and must stream the entire relation
        # in the same caller-owned snapshot. No estimates or error fallback.
        fact = await conn.fetchrow(f"""SELECT count(*) AS rows,
            encode(sha256(convert_to(coalesce(string_agg(value || E'\\n', ''
                ORDER BY value COLLATE "C"), ''), 'UTF8')), 'hex') AS sha256
            FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS value
                FROM {quoted} t LIMIT $1::bigint) hashed""", probe_rows)
        if fact['rows'] < probe_rows:
            record_fingerprint_path('serverAggregateRelations')
            return {'rows': fact['rows'], 'sha256': fact['sha256']}
        path = 'cursorFallbackRelations'
    # Sequences and pre-row-hash archives retain their existing byte/order rules.
    sql = (f"SELECT jsonb_build_object('last_value',last_value,'is_called',is_called)::text AS value FROM {quoted}"
           if kind == 'S' else
           (f"SELECT value FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS value FROM {quoted} t) hashed ORDER BY value COLLATE \"C\"" if row_hashes
            else f'SELECT to_jsonb(t)::text AS value FROM {quoted} t ORDER BY to_jsonb(t)::text'))
    count = 0
    sha = hashlib.sha256()
    async for row in conn.cursor(sql, prefetch=100):
        sha.update(row['value'].encode()); sha.update(b'\n'); count += 1
    record_fingerprint_path(path)
    return {'rows': count, 'sha256': sha.hexdigest()}


async def relation_fingerprints_batched(conn, relations, row_hashes=True, *,
                                      server_aggregation=True, chunk_size=2):
    """Par-only batches; preserve each backup probe, fallback and path counter."""
    from hosted_install_preservation import checked_fingerprint_chunk, checked_fingerprint_chunk_size
    chunk_size = checked_fingerprint_chunk_size(chunk_size)
    if not conn.is_in_transaction():
        raise BackupError('Batched backup fingerprints require a caller snapshot')
    await conn.execute("SET LOCAL statement_timeout='20s'")
    probe_rows = MAX_FINGERPRINT_AGGREGATE_BYTES // ROW_HASH_LINE_BYTES
    if row_hashes and server_aggregation and probe_rows < 1:
        raise BackupError('Fingerprint aggregate bound must allow a row')
    tables = {}
    entries = list(relations)
    names = [r['nspname'] + '.' + r['relname'] for r in entries]
    if len(set(names)) != len(names) or any(r['kind'] not in ('r','p','m','S') for r in entries):
        raise BackupError('Ambiguous backup relation coverage')
    for start in range(0, len(entries), chunk_size):
        chunk = entries[start:start + chunk_size]
        queries, positions = [], []
        for offset, relation in enumerate(chunk):
            if relation['kind'] == 'S' or not row_hashes or not server_aggregation:
                continue
            position = start + offset
            quoted = native.quoted(relation['nspname']) + '.' + native.quoted(relation['relname'])
            queries.append(f'''(SELECT {position}::integer AS position, count(*) AS rows,
                encode(sha256(convert_to(coalesce(string_agg(value || E'\\n', ''
                    ORDER BY value COLLATE "C"), ''), 'UTF8')), 'hex') AS sha256
                FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS value
                    FROM {quoted} t LIMIT $1::bigint) hashed)''')
            positions.append(position)
        facts = (checked_fingerprint_chunk(await conn.fetch(' UNION ALL '.join(queries), probe_rows),
                                           positions, max_rows=probe_rows) if queries else {})
        # Validate all fast results before using any member of this chunk. A
        # timeout/malformed result never causes a retry or cursor error fallback.
        for offset, relation in enumerate(chunk):
            name = relation['nspname'] + '.' + relation['relname']
            quoted = native.quoted(relation['nspname']) + '.' + native.quoted(relation['relname'])
            if start + offset not in facts:
                fact = await relation_fingerprint(conn, quoted, relation['kind'], row_hashes,
                                                  server_aggregation=server_aggregation)
            else:
                fact = facts[start + offset]
                if fact['rows'] < probe_rows:
                    record_fingerprint_path('serverAggregateRelations')
                else:
                    # Full probe is inconclusive. Discard its digest and stream
                    # the entire relation with the original byte/order rules.
                    sql = f'''SELECT value FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS value FROM {quoted} t) hashed ORDER BY value COLLATE "C"'''
                    count = 0
                    sha = hashlib.sha256()
                    async for row in conn.cursor(sql, prefetch=100):
                        sha.update(row['value'].encode()); sha.update(b'\n'); count += 1
                    fact = {'rows': count, 'sha256': sha.hexdigest()}
                    record_fingerprint_path('cursorFallbackRelations')
            tables[name] = {**fact, 'kind': relation['kind']}
    return tables


async def fingerprint(conn, row_hashes=True, *, server_aggregation=True):
    # Deparser output is session-sensitive (pg_dump uses quote_all_identifiers).
    # Normalize within the caller's snapshot, without changing role/app defaults.
    await conn.execute("SET LOCAL quote_all_identifiers=off; SET LOCAL TIME ZONE 'UTC'; SET LOCAL search_path=pg_catalog; SET LOCAL DateStyle='ISO,YMD'; SET LOCAL IntervalStyle=postgres; SET LOCAL bytea_output=hex; SET LOCAL extra_float_digits=3; SET LOCAL standard_conforming_strings=on; SET LOCAL row_security=off")
    catalog = {}
    for key, sql in native.CATALOG.items():
        if key == 'extensions':
            continue  # Dependency bootstrap is verified separately, outside application scope.
        sql = sql.replace(native.NAMESPACES, 'n.nspname=ANY($1::text[])')
        if key == 'functions':
            sql = sql.replace('p.proacl::text AS acl', "ARRAY(SELECT a::text FROM unnest(coalesce(p.proacl,acldefault('f',p.proowner))) a ORDER BY a::text) AS acl")
        sql = sql.replace('ORDER BY a::text', 'ORDER BY a::text COLLATE "C"')
        rows = await conn.fetch('SELECT to_jsonb(r)::text AS value FROM (' + sql + ') r ORDER BY to_jsonb(r)::text', list(SCHEMAS))
        # Database collations differ between hosted Linux and local Windows.
        # Compare identical records in a portable client order, not locale order.
        catalog[key] = {'objects': len(rows), 'sha256': digest('\n'.join(sorted(r['value'] for r in rows)).encode())}
    acl = await conn.fetch('''SELECT n.nspname,pg_get_userbyid(d.defaclrole) AS role,d.defaclobjtype::text AS kind,
        ARRAY(SELECT a::text FROM unnest(d.defaclacl) a ORDER BY a::text COLLATE "C") AS acl
        FROM pg_default_acl d JOIN pg_namespace n ON n.oid=d.defaclnamespace WHERE n.nspname=ANY($1::text[])
        ORDER BY 1,2,3''', list(SCHEMAS))
    catalog['default_acl'] = {'objects': len(acl), 'sha256': digest('\n'.join(sorted(json.dumps(dict(r), sort_keys=True) for r in acl)).encode())}
    tables = {}
    relations = await conn.fetch('''SELECT n.nspname,c.relname,c.relkind::text AS kind FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[])
        AND c.relkind IN ('r','p','m','S') ORDER BY 1,2''', list(SCHEMAS))
    for relation in relations:
        name = relation['nspname'] + '.' + relation['relname']
        quoted = native.quoted(relation['nspname']) + '.' + native.quoted(relation['relname'])
        try:
            fact = await relation_fingerprint(conn, quoted, relation['kind'], row_hashes,
                                              server_aggregation=server_aggregation)
        except TimeoutError as exc:
            error = BackupError('Table fingerprint query timed out')
            error.failureObject = name
            raise error from exc
        tables[name] = {**fact, 'kind': relation['kind']}
    return {'tables': tables, 'catalog': catalog}


async def fingerprint_batched(conn, row_hashes=True, *, server_aggregation=True):
    if not conn.is_in_transaction():
        raise BackupError("Batched backup fingerprint requires a caller snapshot")
    await conn.execute("SET LOCAL statement_timeout='20s'")
    # Deparser output is session-sensitive (pg_dump uses quote_all_identifiers).
    # Normalize within the caller's snapshot, without changing role/app defaults.
    await conn.execute("SET LOCAL quote_all_identifiers=off; SET LOCAL TIME ZONE 'UTC'; SET LOCAL search_path=pg_catalog; SET LOCAL DateStyle='ISO,YMD'; SET LOCAL IntervalStyle=postgres; SET LOCAL bytea_output=hex; SET LOCAL extra_float_digits=3; SET LOCAL standard_conforming_strings=on; SET LOCAL row_security=off")
    catalog = {}
    for key, sql in native.CATALOG.items():
        if key == 'extensions':
            continue  # Dependency bootstrap is verified separately, outside application scope.
        sql = sql.replace(native.NAMESPACES, 'n.nspname=ANY($1::text[])')
        if key == 'functions':
            sql = sql.replace('p.proacl::text AS acl', "ARRAY(SELECT a::text FROM unnest(coalesce(p.proacl,acldefault('f',p.proowner))) a ORDER BY a::text) AS acl")
        sql = sql.replace('ORDER BY a::text', 'ORDER BY a::text COLLATE "C"')
        rows = await conn.fetch('SELECT to_jsonb(r)::text AS value FROM (' + sql + ') r ORDER BY to_jsonb(r)::text', list(SCHEMAS))
        # Database collations differ between hosted Linux and local Windows.
        # Compare identical records in a portable client order, not locale order.
        catalog[key] = {'objects': len(rows), 'sha256': digest('\n'.join(sorted(r['value'] for r in rows)).encode())}
    acl = await conn.fetch('''SELECT n.nspname,pg_get_userbyid(d.defaclrole) AS role,d.defaclobjtype::text AS kind,
        ARRAY(SELECT a::text FROM unnest(d.defaclacl) a ORDER BY a::text COLLATE "C") AS acl
        FROM pg_default_acl d JOIN pg_namespace n ON n.oid=d.defaclnamespace WHERE n.nspname=ANY($1::text[])
        ORDER BY 1,2,3''', list(SCHEMAS))
    catalog['default_acl'] = {'objects': len(acl), 'sha256': digest('\n'.join(sorted(json.dumps(dict(r), sort_keys=True) for r in acl)).encode())}
    relations = await conn.fetch('''SELECT n.nspname,c.relname,c.relkind::text AS kind FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[])
        AND c.relkind IN ('r','p','m','S') ORDER BY 1,2''', list(SCHEMAS))
    tables = await relation_fingerprints_batched(conn, relations, row_hashes,
                                                server_aggregation=server_aggregation)
    return {'tables': tables, 'catalog': catalog}

async def dependencies(conn):
    """Record referenced managed objects. Unsupported dependencies hold recovery."""
    rows = await conn.fetch('''WITH objects AS (
      SELECT 'pg_class'::regclass AS classid,c.oid AS objid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[])
      UNION SELECT 'pg_proc'::regclass,p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=ANY($1::text[])
      UNION SELECT 'pg_type'::regclass,t.oid FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname=ANY($1::text[])
      UNION SELECT 'pg_constraint'::regclass,k.oid FROM pg_constraint k JOIN pg_namespace n ON n.oid=k.connamespace WHERE n.nspname=ANY($1::text[])
      UNION SELECT 'pg_attrdef'::regclass,a.oid FROM pg_attrdef a JOIN pg_class c ON c.oid=a.adrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[])
      UNION SELECT 'pg_policy'::regclass,p.oid FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[])
      UNION SELECT 'pg_rewrite'::regclass,r.oid FROM pg_rewrite r JOIN pg_class c ON c.oid=r.ev_class JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[])
      UNION SELECT 'pg_trigger'::regclass,t.oid FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[]))
      SELECT DISTINCT i.type,i.schema,i.identity,e.extname AS extension,d.refclassid::regclass::text AS class,d.refobjid
      FROM pg_depend d JOIN objects o ON o.classid=d.classid AND o.objid=d.objid
      CROSS JOIN LATERAL pg_identify_object(d.refclassid,d.refobjid,d.refobjsubid) i
      LEFT JOIN pg_depend member ON member.classid=d.refclassid AND member.objid=d.refobjid AND member.deptype='e' AND member.refclassid='pg_extension'::regclass
      LEFT JOIN pg_extension e ON e.oid=member.refobjid
      WHERE i.schema IS NOT NULL AND NOT i.schema=ANY($1::text[]) AND i.schema NOT LIKE 'pg_%' ORDER BY 2,3''', list(SCHEMAS))
    facts = [dict(row) for row in rows]
    extensions = []
    functions = []
    for row in facts:
        if row['extension']:
            extension = dict(await conn.fetchrow('SELECT e.extname,e.extversion,n.nspname AS schema FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname=$1', row['extension']))
            if extension not in extensions:
                extensions.append(extension)
        elif row['schema'] == 'auth' and row['class'] == 'pg_proc':
            function = await conn.fetchrow('''SELECT p.proname,p.prosecdef,l.lanname,pg_get_function_identity_arguments(p.oid) AS args,pg_get_functiondef(p.oid) AS definition
              FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang WHERE p.oid=$1''', row['refobjid'])
            if function['proname'] not in ('uid','role','jwt') or function['prosecdef'] or function['lanname'] != 'sql' or function['args']:
                raise BackupError('Unsupported managed function dependency')
            functions.append(dict(function))
        else:
            raise BackupError('Unsupported out-of-scope dependency; no complete restore claim')
    return {'objects': facts, 'extensions': extensions, 'authFunctions': functions}


def open_backup(encrypted, key, expected_project):
    encrypted = Path(encrypted)
    if not encrypted.is_file() or encrypted.stat().st_size > MAX_ENVELOPE:
        raise BackupError('Missing or oversized encrypted backup')
    try:
        value = json.loads(Fernet(Path(key).read_bytes()).decrypt(encrypted.read_bytes()))
        manifest = value['manifest']
        archive = base64.b64decode(value['archive'], validate=True)
        if (manifest['format'] != FORMAT or manifest['projectRef'] != expected_project
            or manifest['schemas'] != list(SCHEMAS) or len(archive) > MAX_ARCHIVE
            or manifest.get('rowFingerprintAlgorithm') not in (None, ROW_ALGORITHM)
            or digest(archive) != manifest['archiveSha256'] or len(archive) != manifest['archiveBytes']):
            raise ValueError('Manifest validation failed')
    except Exception as exc:
        raise BackupError('Backup authentication or manifest validation failed') from exc
    return manifest, archive


def restore_list(toc):
    """Retain initdb's public schema and its initial privileges; keep its ACL entry."""
    lines = toc.decode('utf-8').splitlines(keepends=True)
    public = [i for i, line in enumerate(lines) if re.match(r'^\d+;\s+\d+\s+\d+\s+SCHEMA - public\s', line)]
    if len(public) != 1:
        raise BackupError('Expected public schema archive entry missing or ambiguous')
    lines[public[0]] = '; ' + lines[public[0]]
    return ''.join(lines).encode('utf-8')


async def export_backup(url, project, pg_dump, pg_restore, backup_directory, key_directory, migration_hashes,
                        *, timeout_seconds=EXPORT_TIMEOUT_SECONDS, progress=None, maintenance_direct_ipv6=False):
    if type(maintenance_direct_ipv6) is not bool:
        raise BackupError('Explicit boolean maintenance mode required')
    if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not 0 < timeout_seconds <= EXPORT_TIMEOUT_SECONDS or not math.isfinite(timeout_seconds)):
        raise BackupError('Export timeout must be positive and at most 600 seconds')
    diagnostics = ExportDiagnostics(timeout_seconds, progress)
    control = ExportControl(diagnostics)
    token = EXPORT_CONTROL.set(control)
    options = {'maintenance_direct_ipv6': True} if maintenance_direct_ipv6 else {}
    worker = asyncio.create_task(_export_backup(url, project, pg_dump, pg_restore, backup_directory,
                                               key_directory, migration_hashes, diagnostics, **options))
    watcher = asyncio.create_task(control.watch(worker))
    try:
        try:
            result = await asyncio.shield(worker)
        except asyncio.CancelledError as interrupted:
            # User cancellation reaches the supervisor while the worker remains
            # shielded. Cancel and gracefully close only its owned resources.
            await control.stop(worker)
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError as cancelled:
                if diagnostics.deadline_exceeded:
                    held = BackupError('Overall backup export deadline exceeded')
                    for name in ('snapshotCleanupErrorType', 'connectionCloseErrorType',
                                 'partialCleanupErrorType', 'subprocessCleanupErrorType'):
                        if hasattr(cancelled, name):
                            setattr(held, name, getattr(cancelled, name))
                    raise held from cancelled
                raise
            # A cancellation racing a completed export is still reported held;
            # artifact flags disclose any final file instead of inventing success.
            raise interrupted
    except BaseException as error:
        if control.termination_error is not None:
            error.connectionTerminateErrorType = control.termination_error
        error.backupDiagnostics = diagnostics.report()
        artifacts = {}
        for name, path in (
            ('privateKeyRetained', Path(key_directory) / 'backup.key'),
            ('encryptedPartialRetained', Path(backup_directory) / 'backup.partial.enc'),
            ('rawPartialRetained', Path(backup_directory) / 'archive.partial'),
            ('finalBackupPresent', Path(backup_directory) / 'backup.jmax.enc')):
            try:
                artifacts[name] = path.exists()
            except OSError:
                artifacts['artifactInspectionHeld'] = True
        error.backupArtifacts = artifacts
        raise
    finally:
        watcher.cancel()
        try:
            await watcher
        except asyncio.CancelledError:
            pass
        EXPORT_CONTROL.reset(token)
    return result | {'backupDiagnostics':diagnostics.report()}


async def _export_backup(url, project, pg_dump, pg_restore, backup_directory, key_directory,
                         migration_hashes, diagnostics, *, maintenance_direct_ipv6=False):
    if maintenance_direct_ipv6:
        import maintenance_connection
        settings = await maintenance_connection.dump_settings(url, project)
    else:
        settings = hosted_connection(url, project)
    context = connection_tls(url)
    directory = private_directory(backup_directory, 'backups')
    private_key = private_directory(key_directory, 'credentials') / 'backup.key'
    key = Fernet.generate_key()
    with private_key.open('xb') as stream:
        stream.write(key)
    raw = directory / 'archive.partial'
    candidate = directory / 'backup.partial.enc'
    conn = None
    body_completed = False
    async def close_connection():
        with diagnostics.phase('connection_close'):
            if conn is not None:
                await EXPORT_CONTROL.get().close_owned()
    async def clean_partials():
        with diagnostics.phase('partial_cleanup'):
            if EXPORT_CONTROL.get().tool_cleanup_held:
                raise BackupError('PostgreSQL tool cleanup held; partials retained')
            # Candidate survives only after the body AND connection close pass.
            await remove_partial_files((raw,) if body_completed else (raw, candidate))
    async with preserve_cleanup_failure(clean_partials, 'partialCleanupErrorType'):
        async with preserve_cleanup_failure(close_connection, 'connectionCloseErrorType'):
            with diagnostics.phase('connect'):
                if maintenance_direct_ipv6:
                    conn = await maintenance_connection.connect(url, project, readonly=True,
                        timeout=CONNECT_TIMEOUT_SECONDS, command_timeout=COMMAND_TIMEOUT_SECONDS,
                        label=EXPORT_CONTROL.get().application_name)
                else:
                    conn = await asyncpg.connect(url, ssl=context, timeout=CONNECT_TIMEOUT_SECONDS,
                        command_timeout=COMMAND_TIMEOUT_SECONDS, statement_cache_size=0,
                        server_settings={'application_name':EXPORT_CONTROL.get().application_name})
                EXPORT_CONTROL.get().connection = conn
                await native.configure(conn)
            # This aggregate overlaps its named subphases; do not sum all timings.
            with diagnostics.phase('snapshot_total'):
                async with readonly_snapshot(conn, rollback_timeout=CLEANUP_TIMEOUT_SECONDS):
                    with diagnostics.phase('effective_limits'):
                        await diagnostics.read_limits(conn)
                    with diagnostics.phase('schema_check'):
                        found = {r['nspname'] for r in await conn.fetch("SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname<>'information_schema'")}
                        if set(SCHEMAS) - found or found - set(SCHEMAS) - MANAGED:
                            raise BackupError('Missing or unclassified database schemas')
                    with diagnostics.phase('export_snapshot'):
                        snapshot = await conn.fetchval('SELECT pg_export_snapshot()')
                    with diagnostics.phase('fingerprint'):
                        facts = await fingerprint(conn)
                    with diagnostics.phase('dependencies'):
                        dependency = await dependencies(conn)
                    with diagnostics.phase('role_metadata'):
                        roles = [dict(r) for r in await conn.fetch("SELECT rolname,rolinherit,rolconnlimit,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication,rolcanlogin,rolvaliduntil::text,rolconfig FROM pg_roles WHERE rolname NOT LIKE 'pg_%' ORDER BY rolname")]
                        memberships = [dict(r) for r in await conn.fetch('SELECT pg_get_userbyid(roleid) AS role,pg_get_userbyid(member) AS member,admin_option,inherit_option,set_option FROM pg_auth_members ORDER BY 1,2')]
                    with diagnostics.phase('pg_dump'):
                        await tool(pg_dump, ['--format=custom', '--quote-all-identifiers', '--encoding=UTF8', '--lock-wait-timeout=5000',
                            '--snapshot=' + snapshot, '--file=' + str(raw), '--no-password', *['--schema=' + schema for schema in SCHEMAS]], settings, True)
                        if raw.stat().st_size > MAX_ARCHIVE:
                            raise BackupError('Archive exceeds build encryption bound; streaming export required')
                    with diagnostics.phase('sequence_recheck'):
                        # Sequence values are outside MVCC: hold on observed changes.
                        for name, fact in facts['tables'].items():
                            if fact['kind'] == 'S':
                                schema, table = name.split('.')
                                row = await conn.fetchval(f"SELECT jsonb_build_object('last_value',last_value,'is_called',is_called)::text FROM {native.quoted(schema)}.{native.quoted(table)}")
                                if digest((row + '\n').encode()) != fact['sha256']:
                                    raise BackupError('Sequence changed during export')
                    with diagnostics.phase('manifest'):
                        data = raw.read_bytes()
                        manifest = {'format': FORMAT, 'projectRef': project, 'schemas': list(SCHEMAS),
                            'rowFingerprintAlgorithm': ROW_ALGORITHM, 'databaseOwner': await conn.fetchval('SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()'),
                            'schemaOwners': {r['nspname']: r['owner'] for r in await conn.fetch('SELECT nspname,pg_get_userbyid(nspowner) AS owner FROM pg_namespace WHERE nspname=ANY($1::text[])', list(SCHEMAS))},
                            'createdAt': datetime.now(timezone.utc).isoformat(), 'serverVersionNum': await conn.fetchval('SHOW server_version_num'),
                            'archiveBytes': len(data), 'archiveSha256': digest(data), 'dependencies': dependency,
                            'rolesWithoutPasswords': roles, 'roleMemberships': memberships, 'migrationFileHashes': migration_hashes,
                            'sequenceStateIsMvcc': False, 'sequencesObservedStable': True, 'managedRecoveryVerified': False, **facts}
            with diagnostics.phase('encrypt'):
                with candidate.open('xb') as stream:
                    stream.write(Fernet(key).encrypt(json.dumps({'manifest': manifest, 'archive': base64.b64encode(data).decode()}).encode()))
            with diagnostics.phase('read_back'):
                verified, archive = open_backup(candidate, private_key, project)
                if verified != manifest or archive != data:
                    raise BackupError('Encrypted readback mismatch')
                encrypted_sha256 = digest(candidate.read_bytes())
            with diagnostics.phase('archive_list'):
                await tool(pg_restore, ['--list', str(raw)])
        # Reached only after the protected connection-close step succeeds.
        body_completed = True
    # No final filename or successful receipt exists while cleanup is held.
    # Synchronous bounded encryption/filesystem work cannot be interrupted by an
    # asyncio timer; check monotonic wall time again before publishing anything.
    EXPORT_CONTROL.get().check_deadline()
    with diagnostics.phase('publish'):
        final = directory / 'backup.jmax.enc'
        candidate.rename(final)
    return {'status': 'exported_not_restore_verified', 'encryptedBackup': str(final), 'privateKey': str(private_key),
        'encryptedSha256': encrypted_sha256, 'archiveSha256': manifest['archiveSha256'],
        'tablesCaptured': len(facts['tables']), 'catalogGroupsCaptured': len(facts['catalog']), 'sourceReadOnly': True,
        'sequencesObservedStable': True, 'managedRecoveryVerified': False}


async def verify_restore(dsn, encrypted, key, project, pg_restore, temporary_directory):
    settings = native.disposable_connection(dsn)
    if not re.fullmatch(r'native_purchase_test_backup_[a-f0-9]{32}', settings['database']):
        raise BackupError('Fresh UUID-named backup test database required')
    manifest, archive = open_backup(encrypted, key, project)  # Authenticate before connection or writes.
    directory = private_directory(temporary_directory, 'backups')
    raw = directory / 'restore.partial'
    listing = directory / 'restore.list.partial'
    conn = None
    async def close_connection():
        if conn is not None:
            await conn.close()
    async with preserve_cleanup_failure(lambda: remove_partial_files((raw, listing)), 'partialCleanupErrorType'), \
               preserve_cleanup_failure(close_connection, 'connectionCloseErrorType'):
        with raw.open('xb') as stream:
            stream.write(archive)
        with listing.open('xb') as stream:
            stream.write(restore_list(await tool(pg_restore, ['--list', str(raw)])))
        conn = await asyncpg.connect(**settings, ssl=False)
        occupied = await conn.fetchval(f"SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE {native.NAMESPACES}) OR EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE {native.NAMESPACES}) OR EXISTS(SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE {native.NAMESPACES}) OR EXISTS(SELECT 1 FROM pg_default_acl d JOIN pg_namespace n ON n.oid=d.defaclnamespace WHERE {native.NAMESPACES}) OR EXISTS(SELECT 1 FROM pg_namespace n WHERE {native.NAMESPACES} AND n.nspname<>'public')")
        if occupied:
            raise BackupError('Nonempty restore target refused')
        if int(await conn.fetchval('SHOW server_version_num')) // 10000 != int(manifest['serverVersionNum']) // 10000:
            raise BackupError('PostgreSQL major version mismatch')
        if manifest.get('databaseOwner') and await conn.fetchval('SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()') != manifest['databaseOwner']:
            raise BackupError('Disposable database owner must match recovery metadata')
        # Required NOLOGIN role stubs are prepared separately on the dedicated
        # test cluster. This utility never changes global roles or passwords.
        for role in manifest['rolesWithoutPasswords']:
            if not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=$1)', role['rolname']):
                raise BackupError('Required recovery role missing')
        async with conn.transaction():
            owner = manifest.get('schemaOwners', {}).get('public')
            if owner:
                await conn.execute('ALTER SCHEMA public OWNER TO ' + native.quoted(owner))
            for extension in manifest['dependencies']['extensions']:
                if extension['extname'] not in ('uuid-ossp', 'pgcrypto', 'pg_trgm', 'citext', 'btree_gist', 'btree_gin') or extension['schema'] != 'extensions':
                    raise BackupError('Unreviewed recovery extension')
                if not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM pg_available_extension_versions WHERE name=$1 AND version=$2)', extension['extname'], extension['extversion']):
                    raise BackupError('Required extension version unavailable')
                await conn.execute('CREATE SCHEMA IF NOT EXISTS extensions')
                await conn.execute('CREATE EXTENSION ' + native.quoted(extension['extname']) + ' WITH SCHEMA extensions VERSION ' + "'" + extension['extversion'].replace("'", "''") + "'")
            for function in manifest['dependencies']['authFunctions']:
                # Exact definitions came from the authenticated encrypted archive;
                # these SQL/non-definer helpers only support local policy creation.
                if function['proname'] not in ('uid', 'role', 'jwt') or function['prosecdef'] or function['lanname'] != 'sql' or function['args']:
                    raise BackupError('Unreviewed auth dependency')
                await conn.execute('CREATE SCHEMA IF NOT EXISTS auth')
                await conn.execute(function['definition'])
        await conn.close(); conn = None
        # Only after UUID/loopback/empty-object gates. The default public schema
        # remains; its archive ACL entry and all application objects are restored.
        await tool(pg_restore, ['--single-transaction', '--exit-on-error', '--clean', '--if-exists', '--use-list=' + str(listing), '--no-password', '--dbname=' + settings['database'], str(raw)], settings)
        conn = await asyncpg.connect(**settings, ssl=False)
        await native.configure(conn)
        async with readonly_snapshot(conn):
            algorithm = manifest.get('rowFingerprintAlgorithm')
            if algorithm not in (None, ROW_ALGORITHM):
                raise BackupError('Unsupported row fingerprint algorithm')
            actual = await fingerprint(conn, row_hashes=algorithm == ROW_ALGORITHM)
        expected = {key: manifest[key] for key in ('tables', 'catalog')}
        differences = {group: [name for name in sorted(set(actual[group]) | set(expected[group])) if actual[group].get(name) != expected[group].get(name)] for group in expected}
        if any(differences.values()):
            # Object identities only; no recovered rows/definitions in public evidence.
            error = BackupError('Restored application fingerprints differ')
            error.differences = differences
            raise error
        return {'status': 'verified_application_restore', 'tablesMatched': len(actual['tables']),
            'catalogGroupsMatched': len(actual['catalog']), 'archiveSha256': manifest['archiveSha256'],
            'rowsMatched': sum(t['rows'] for t in actual['tables'].values() if t['kind'] != 'S'),
            'majorVersionMatched': True, 'patchVersionMatched': await conn.fetchval('SHOW server_version_num') == manifest['serverVersionNum'],
            'managedRecoveryVerified': False, 'operationalReleaseApproved': False}
