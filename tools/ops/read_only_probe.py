"""Opt-in operator observations; no installer, application pool or default network use.

The CLI prepares/checks public packets only. execute_approved is the separately
approved operator boundary, never called by packet preparation or the app.
"""
import argparse
import asyncio
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
FORMAT = 'jaymax-readonly-probe-v1'
HEALTH_URL = 'https://jaymax-api.onrender.com/api/health'
APP_SCHEMAS = ('public', 'integrations', 'purchasing', 'actual_inventory', 'prep_inventory')
BACKUP_SCHEMAS = ('public', 'purchasing', 'actual_inventory', 'prep_inventory', 'integrations', 'supabase_migrations')
LIMITS = dict(connect=20, health=90, responseBytes=4096, statement=20, lock=5,
              idle=120, work=600, cleanup=15, observed=10, chunkSize=2, events=100000)
GROUPS = ('setup', 'original_projection', 'backup')


class Held(ValueError):
    """Only fixed messages; public receipts never serialize exception strings."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def utc():
    return datetime.now(timezone.utc)


def timestamp(value):
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None:
            raise ValueError
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError):
        raise Held('Explicit timezone-aware timestamps required') from None


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise Held('Ambiguous JSON keys refused')
        value[key] = item
    return value


def sources():
    # Conservative complete local module sets, including function-local imports,
    # SQL and CA bytes. No import discovery executes application code.
    paths = {ROOT / 'backend/requirements.txt',
             ROOT / 'docs/READ_ONLY_HEALTH_CALIBRATION_PROPOSAL_20261023.md'}
    for area in ('backend', 'tools/ops'):
        paths.update(p for p in (ROOT / area).rglob('*')
                     if p.suffix in ('.py', '.sql', '.crt')
                     and 'tests' not in p.relative_to(ROOT).parts
                     and '__pycache__' not in p.parts)
    if any(p.is_symlink() or not p.resolve().is_relative_to(ROOT) for p in paths):
        raise Held('Redirected source refused')
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}


def packet(stage, *, project=None, health_sha=None, scope_sha=None):
    if stage not in ('health', 'calibration'):
        raise Held('One supported stage required')
    if stage == 'health':
        if any(v is not None for v in (project, health_sha, scope_sha)):
            raise Held('Mixed stages refused')
        target = {'url': HEALTH_URL}
        scope = None
    else:
        if not isinstance(project, str) or re.fullmatch('[a-z0-9]{20}', project) is None:
            raise Held('Designated project required')
        if not isinstance(health_sha, str) or re.fullmatch('[a-f0-9]{64}', health_sha) is None:
            raise Held('Prior health receipt binding required')
        if scope_sha is not None and (not isinstance(scope_sha, str)
                or re.fullmatch('[a-f0-9]{64}', scope_sha) is None):
            raise Held('Invalid scope binding')
        target = {'project': project, 'host': 'db.' + project + '.supabase.co',
                  'port': 5432, 'database': 'postgres', 'actor': 'postgres'}
        scope = {'applicationSchemas': list(APP_SCHEMAS), 'backupSchemas': list(BACKUP_SCHEMAS),
                 'originalKinds': ['r', 'p'], 'backupKinds': ['r', 'p', 'm', 'S'],
                 'inventorySha256': scope_sha, 'discoveryApproved': scope_sha is None,
                 'healthReceiptSha256': health_sha}
    return {'format': FORMAT, 'stage': stage, 'target': target, 'scope': scope,
            'limits': dict(LIMITS), 'sources': sources(), 'executionApproved': False}


def check_packet(value):
    if not isinstance(value, dict):
        raise Held('Probe packet required')
    try:
        scope = value['scope']
        expected = packet(value['stage'], project=value['target'].get('project'),
                          health_sha=scope['healthReceiptSha256'] if scope else None,
                          scope_sha=scope['inventorySha256'] if scope else None)
        if json.dumps(value, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True):
            raise Held('Source or packet binding differs')
    except (KeyError, TypeError, AttributeError, ValueError):
        raise Held('Source or packet binding differs') from None
    return digest(value)


def approve_check(value, approval, *, health=None, now=None):
    sha = check_packet(value)
    now = now or utc()
    if (not isinstance(approval, dict) or set(approval) !=
            {'packetSha256', 'stage', 'approved', 'startsAt', 'endsAt', 'reference', 'evidenceDirectory'}
            or approval['packetSha256'] != sha or approval['stage'] != value['stage']
            or approval['approved'] is not True
            or not isinstance(approval['evidenceDirectory'], str)
            or not Path(approval['evidenceDirectory']).is_absolute()
            or not isinstance(approval['reference'], str)
            or re.fullmatch('[a-zA-Z0-9_-]{1,80}', approval['reference']) is None):
        raise Held('Separate exact-stage owner approval required')
    start, end = timestamp(approval['startsAt']), timestamp(approval['endsAt'])
    required = LIMITS['health'] + LIMITS['cleanup'] if value['stage'] == 'health' else LIMITS['work'] + LIMITS['cleanup']
    if not (0 < (end-start).total_seconds() <= 3600 and start <= now
            and (end-now).total_seconds() >= required):
        raise Held('Fresh approval with complete operation and cleanup reserve required')
    if value['stage'] == 'calibration':
        if (not isinstance(health, dict) or digest(health) != value['scope']['healthReceiptSha256']
                or health.get('format') != FORMAT or health.get('stage') != 'health'
                or health.get('status') != 'preliminary_pass'
                or health.get('cleanupConfirmed') is not True
                or health.get('target') != {'url': HEALTH_URL}
                or health.get('sourcesSha256') != digest(value['sources'])
                or not 0 <= (now-timestamp(health.get('completedAt'))).total_seconds() <= 1800):
            raise Held('Fresh bound preliminary health observation required')
    return sha


def memory():
    """Windows local physical memory only; never enumerate/close applications."""
    if os.name != 'nt':
        raise Held('Windows resource verification required')
    class Memory(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in
            ('total', 'free', 'pageTotal', 'pageFree', 'virtualTotal', 'virtualFree', 'extended')]
    result = Memory(); result.length = ctypes.sizeof(result)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(result)):
        raise Held('Memory observation unavailable')
    return {'freeBytes': result.free, 'totalBytes': result.total}


def resources(*, start=False):
    value = memory()
    floor, ratio = (1024**3, .15) if start else (512*1024**2, .10)
    if value['totalBytes'] <= 0 or value['freeBytes'] < floor or value['freeBytes']/value['totalBytes'] < ratio:
        raise Held('Local memory floor not met')
    return value


class Observed:
    """Private per-await facts plus complete cursor envelopes; no SQL/args retained."""
    def __init__(self, connection, *, clock=time.monotonic, guard=lambda: None):
        self.raw, self.clock, self.guard = connection, clock, guard
        self.group = 'setup'
        self.reads = []
        self.cursors = []

    def record(self, started, kind, outcome, *, envelope=False):
        elapsed = self.clock()-started
        if not math.isfinite(elapsed) or elapsed < 0:
            raise Held('Invalid monotonic timing')
        if len(self.reads)+len(self.cursors) >= LIMITS['events']:
            if outcome == 'completed':
                raise Held('Observation evidence bound exceeded')
            return  # Preserve the original driver/cancellation failure.
        row = {'family': self.group, 'kind': kind, 'seconds': elapsed, 'outcome': outcome}
        (self.cursors if envelope else self.reads).append(row)
        if outcome == 'completed':
            self.guard()
            if elapsed > LIMITS['observed']:
                raise Held('Observed read exceeds conservative timing screen')

    async def measured(self, kind, method, *args, **kwargs):
        self.guard(); started = self.clock(); outcome = 'failed'
        try:
            result = await method(*args, **kwargs)
            outcome = 'completed'
            return result
        except asyncio.CancelledError:
            outcome = 'cancelled'
            raise
        finally:
            self.record(started, kind, outcome)

    def __getattr__(self, name):
        if name in ('execute', 'fetch', 'fetchval', 'fetchrow'):
            async def call(*args, **kwargs):
                return await self.measured(name, getattr(self.raw, name), *args, **kwargs)
            return call
        if name == 'transaction':
            def transaction(*args, **kwargs):
                raw = self.raw.transaction(*args, **kwargs)
                owner = self
                class Transaction:
                    async def start(self): return await owner.measured('transaction_start', raw.start)
                    async def commit(self): return await owner.measured('transaction_commit', raw.commit)
                    async def rollback(self):
                        # Cleanup must still run after resource/timing refusal.
                        return await raw.rollback()
                return Transaction()
            return transaction
        if name == 'is_in_transaction':
            return getattr(self.raw, name)
        raise Held('Unobserved connection API refused')

    def cursor(self, *args, **kwargs):
        async def iterate():
            self.guard(); started = self.clock(); outcome = 'failed'
            try:
                iterator = self.raw.cursor(*args, **kwargs).__aiter__()
                while True:
                    before = self.clock()
                    try:
                        row = await iterator.__anext__()
                    except StopAsyncIteration:
                        self.record(before, 'cursor_next', 'completed')
                        outcome = 'completed'
                        break
                    except BaseException as error:
                        self.record(before, 'cursor_next', 'cancelled' if isinstance(error, asyncio.CancelledError) else 'failed')
                        raise
                    self.record(before, 'cursor_next', 'completed')
                    yield row
            except asyncio.CancelledError:
                outcome = 'cancelled'
                raise
            finally:
                self.record(started, 'cursor_lifecycle', outcome, envelope=True)
        return iterate()

    def summary(self):
        return {group: {'queryCalls': sum(r['kind'] in ('execute','fetch','fetchval','fetchrow') for r in self.reads if r['family']==group),
                        'cursorOperations': sum(r['kind']=='cursor_next' for r in self.reads if r['family']==group),
                        'cursorEnvelopes': sum(r['family']==group for r in self.cursors),
                        'maxSeconds': max((r['seconds'] for r in self.reads+self.cursors
                                           if r['family']==group), default=0)} for group in GROUPS}


async def health_observation(*, transport=None):
    import httpx
    async with asyncio.timeout(LIMITS['health']):
        async with httpx.AsyncClient(verify=True, trust_env=False, follow_redirects=False,
                transport=transport, timeout=httpx.Timeout(LIMITS['health'], connect=LIMITS['connect'])) as client:
            async with client.stream('GET', HEALTH_URL, headers={'Accept': 'application/json', 'Accept-Encoding':'identity'}) as response:
                raw = bytearray()
                if response.status_code != 200:
                    raise Held('Health response status held')
                if response.headers.get('content-encoding', 'identity') != 'identity':
                    raise Held('Encoded health response refused')
                async for chunk in response.aiter_raw():
                    raw.extend(chunk)
                    if len(raw) > LIMITS['responseBytes']:
                        raise Held('Health response bound exceeded')
                try:
                    value = json.loads(raw, object_pairs_hook=unique_object)
                except (ValueError, UnicodeError):
                    raise Held('Health JSON shape held') from None
                if value != {'status': 'ok', 'database': 'connected'}:
                    raise Held('Preliminary database pool signal unavailable')
                return {'httpStatus': 200, **value}


async def calibration(conn, scope, *, observer=None):
    """Caller owns validated dedicated connection, deadline, resource monitor/close."""
    import hosted_backup as backup
    import hosted_install_preservation as preservation
    from readonly_snapshot import readonly_snapshot
    if conn.is_in_transaction() or tuple(preservation.reconciliation.SCHEMAS) != APP_SCHEMAS or backup.SCHEMAS != BACKUP_SCHEMAS:
        raise Held('Idle connection and reviewed schema scope required')
    observer = observer or Observed(conn)
    async with readonly_snapshot(observer, rollback_timeout=5):
        await observer.execute("SET LOCAL statement_timeout='20s'; SET LOCAL lock_timeout='5s'; "
            "SET LOCAL idle_in_transaction_session_timeout='120s'; SET LOCAL TIME ZONE 'UTC'")
        facts = dict(await observer.fetchrow("SELECT current_setting('transaction_read_only') AS readonly, "
            "current_setting('transaction_isolation') AS isolation, current_setting('statement_timeout') AS statement, "
            "current_setting('lock_timeout') AS lock, current_setting('idle_in_transaction_session_timeout') AS idle"))
        if facts != dict(readonly='on', isolation='repeatable read', statement='20s', lock='5s', idle='2min'):
            raise Held('Read-only snapshot settings differ')
        snapshot = dict(await observer.fetchrow("SELECT pg_current_snapshot()::text AS snapshot, "
            "current_user AS actor, session_user AS login, current_database() AS database, "
            "pg_backend_pid() AS pid, current_setting('server_version_num') AS server_version"))
        baseline = await preservation.original_columns(observer)
        relations = [dict(r) for r in await observer.fetch("SELECT n.nspname,c.relname,c.relkind::text AS kind "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY($1::text[]) "
            "AND c.relkind IN ('r','p','m','S') ORDER BY 1,2", list(BACKUP_SCHEMAS))]
        inventory = {'original': [{'schema': k[0], 'table': k[1], 'columns': v} for k,v in baseline.items()],
                     'backup': relations}
        inventory_sha = digest(inventory)
        if scope['inventorySha256'] is not None and scope['inventorySha256'] != inventory_sha:
            raise Held('Reviewed inventory differs')
        if scope['inventorySha256'] is None and scope['discoveryApproved'] is not True:
            raise Held('Complete discovery authority required')
        if not baseline or not relations:
            raise Held('Empty calibration scope refused')
        observer.group = 'original_projection'
        original = await preservation.fingerprints_batched(observer, baseline, chunk_size=2)
        if set(original) != {'.'.join(k) for k in baseline}:
            raise Held('Original result coverage differs')
        observer.group = 'backup'
        result = await backup.fingerprint_batched(observer, row_hashes=True, server_aggregation=True)
        expected = {r['nspname']+'.'+r['relname'] for r in relations}
        catalogs = (set(backup.native.CATALOG)-{'extensions'}) | {'default_acl'}
        if (len(expected) != len(relations) or set(result['tables']) != expected
                or set(result['catalog']) != catalogs
                or any(result['tables'][r['nspname']+'.'+r['relname']]['kind'] != r['kind'] for r in relations)
                or any(r['outcome'] != 'completed' for r in observer.reads+observer.cursors)):
            raise Held('Backup or observer coverage differs')
    return {'scopeSha256': inventory_sha, 'inventory': inventory, 'settings': facts,
            'snapshot': snapshot, 'originalFingerprints': original, 'backupFingerprints': result,
            'originalCount': len(original), 'backupCount': len(expected), 'catalogCount': len(catalogs),
            'coverageComplete': True, 'metrics': observer.summary()}


async def supervised(function, guard):
    async def monitor():
        while True:
            guard()
            await asyncio.sleep(1)
    work, monitor_task = asyncio.create_task(function), asyncio.create_task(monitor())
    try:
        done, _ = await asyncio.wait((work, monitor_task), return_when=asyncio.FIRST_COMPLETED)
        # Preserve a simultaneous driver/cancellation failure and its typed
        # timeout context rather than replacing it with a resource category.
        if work in done and (work.cancelled() or work.exception() is not None):
            return await work
        if monitor_task in done:
            await monitor_task
        return await work
    finally:
        for task in (work, monitor_task):
            if not task.done(): task.cancel()
        done, pending = await asyncio.wait((work, monitor_task), timeout=5)
        # Retrieve failures without replacing the original work/monitor failure.
        for task in done:
            if not task.cancelled(): task.exception()
        if pending:
            error = Held('Owned observation task cleanup held')
            error.snapshotCleanupErrorType = 'ObservationTaskCleanupHeld'
            raise error


def private_path(path, *, directory=False):
    """Verify existing private artifacts; never alter a supplied ACL/configuration."""
    if os.name != 'nt' or not shutil.which('pwsh'):
        raise Held('Windows and PowerShell private-artifact verification required')
    root = Path(os.environ['LOCALAPPDATA'])/'JayMaxBuild'
    path = Path(path)
    if (not path.is_absolute() or not path.resolve().is_relative_to(root.resolve())
            or not (path.is_dir() if directory else path.is_file())):
        raise Held('Existing private local artifact required')
    for parent in (path, *path.parents):
        if parent.is_symlink() or parent.is_junction():
            raise Held('Redirected private artifact refused')
        if parent == root: break
    script = """$ErrorActionPreference='Stop'; $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User;
    $acl=Get-Acl -LiteralPath $env:JAYMAX_PROBE_PRIVATE;
    if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $sid.Value) {exit 2};
    foreach($r in $acl.Access) { if ($r.AccessControlType -eq 'Allow' -and
    $r.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -notin @($sid.Value,'S-1-5-18')) {exit 2} };
    Write-Output 'verified'"""
    result = subprocess.run([shutil.which('pwsh'), '-NoProfile', '-NonInteractive', '-Command', script],
        env={**os.environ, 'JAYMAX_PROBE_PRIVATE': str(path)}, capture_output=True, timeout=20,
        creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode or result.stdout.strip() != b'verified':
        raise Held('Private artifact ACL held')
    return path


def public_summary(receipt):
    # Explicit allowlist; do not forward driver text, private members or identifiers.
    result = {'format': FORMAT, 'stage': receipt['stage'], 'status': receipt['status'],
              'coverageComplete': receipt.get('coverageComplete', False),
              'elapsedSeconds': receipt['elapsedSeconds'], 'hostedExecutionAuthorized': True,
              'automaticApply': False, 'operationalReleaseApproved': False,
              'cleanupConfirmed': receipt.get('cleanupConfirmed', False)}
    if 'metrics' in receipt:
        result['metrics'] = {g: {k: receipt['metrics'][g][k] for k in
            ('queryCalls', 'cursorOperations', 'cursorEnvelopes', 'maxSeconds')} for g in GROUPS}
    return result


async def execute_approved(value, approval, *, evidence_directory, config_path=None, health=None):
    """No CLI execution shortcut. Owner-approved operator calls this boundary once.

    A durable exclusive claim in the verified private directory consumes approval
    before any request/config read. All failures require a new reviewed approval.
    """
    if sys.version_info < (3,12):
        raise Held('Python 3.12 or newer required')
    sha = approve_check(value, approval, health=health)
    if (value['stage']=='health' and config_path is not None
            or value['stage']=='calibration' and config_path is None):
        raise Held('Stage-specific configuration required')
    resources(start=True)
    directory = private_path(evidence_directory, directory=True)
    if directory != Path(approval['evidenceDirectory']):
        raise Held('Approved evidence directory differs')
    if shutil.disk_usage(directory).free < 64*1024**2:
        raise Held('Private evidence disk reserve required')
    claim = directory/('probe-'+digest(approval))
    # The approval binds this directory, so its exclusive marker cannot be moved
    # to a new directory to repeat the same owner-approved attempt.
    with claim.open('xb') as stream:
        stream.write(sha.encode())
        stream.flush()
        os.fsync(stream.fileno())
    private_path(claim)
    # Establish and verify a fresh empty receipt before any network/config read.
    # Failed writes retain the consumed claim and never permit automatic replay.
    receipt_path = claim.with_suffix('.json')
    receipt_stream = receipt_path.open('xb')
    try:
        private_path(receipt_path)
    except BaseException:
        receipt_stream.close()
        raise
    started = time.monotonic(); conn = None; observer = None; cancelled = None
    receipt = {'format': FORMAT, 'stage': value['stage'], 'status': 'held',
               'packetSha256': sha, 'sourcesSha256': digest(value['sources']),
               'target': value['target'], 'startedAt': utc().isoformat()}
    try:
        # Recheck after local ACL/resource work, before configuration or network.
        approve_check(value, approval, health=health)
        resources(start=True)
        async with asyncio.timeout(LIMITS['health'] if value['stage']=='health' else LIMITS['work']):
            if value['stage']=='health':
                receipt['health'] = await supervised(health_observation(), resources)
                receipt['status'] = 'preliminary_pass'
            else:
                from dotenv import dotenv_values
                import maintenance_connection as maintenance
                config = dotenv_values(private_path(config_path), interpolate=False)
                url = maintenance.config_url(config)
                maintenance.direct_settings(url, value['target']['project'])
                # Bind trust bytes too; do not accept an environment CA override.
                if os.environ.get('DATABASE_SSL_ROOT_CERT'):
                    raise Held('Maintenance CA override refused')
                resources(start=True)
                async def database_work():
                    nonlocal conn, observer
                    conn = await maintenance.connect(url, value['target']['project'], readonly=True,
                        label='jaymax-readonly-calibration', timeout=20, command_timeout=20)
                    receipt['transport'] = {'peer':conn.maintenance_peer, 'tls':conn.maintenance_tls}
                    observer = Observed(conn, guard=resources)
                    return await calibration(conn, value['scope'], observer=observer)
                receipt.update(await supervised(database_work(), resources))
                receipt['status'] = 'calibration_pass'
    except BaseException as error:
        from readonly_snapshot import error_details
        receipt['error'] = error_details(error)
        if value['stage'] == 'calibration':
            import hosted_install_preservation as preservation
            receipt['error'].update(preservation.private_fingerprint_timeout_details(error))
        if isinstance(error, TimeoutError) and error.__cause__ is not None:
            details = error_details(error.__cause__)
            if details['snapshotCleanupErrorType'] is not None:
                receipt['error']['snapshotCleanupErrorType'] = details['snapshotCleanupErrorType']
        if isinstance(error, asyncio.CancelledError): cancelled = error
    finally:
        try:
            if conn is not None:
                await asyncio.wait_for(conn.close(timeout=5), 5)
            receipt['cleanupConfirmed'] = not any(v for k,v in receipt.get('error', {}).items()
                if 'Cleanup' in k or 'Close' in k or 'Terminate' in k)
        except BaseException as error:
            receipt['status'] = 'held'; receipt['cleanupConfirmed'] = False
            receipt['cleanupErrorType'] = type(error).__name__
            if isinstance(error, asyncio.CancelledError): cancelled = error
            try: conn.terminate()
            except BaseException: receipt['terminateFailed'] = True
        if observer is not None:
            receipt['reads'], receipt['cursorEnvelopes'] = observer.reads, observer.cursors
            receipt['metrics'] = observer.summary()
        receipt['completedAt'] = utc().isoformat()
        receipt['elapsedSeconds'] = round(time.monotonic()-started, 6)
        raw = json.dumps(receipt, sort_keys=True, allow_nan=False).encode()
        # Retain the exclusively created handle; never reopen/overwrite a path.
        try:
            receipt_stream.write(raw)
            receipt_stream.flush()
            os.fsync(receipt_stream.fileno())
        finally:
            receipt_stream.close()
    if cancelled is not None: raise cancelled
    return public_summary(receipt)


def main():
    parser = argparse.ArgumentParser(description='Local public probe packets only; no hosted CLI execution')
    parser.add_argument('action', choices=('packet', 'check'))
    parser.add_argument('--stage', choices=('health', 'calibration'))
    parser.add_argument('--project'); parser.add_argument('--health-sha'); parser.add_argument('--scope-sha')
    parser.add_argument('--file', required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.action == 'packet':
            value = packet(args.stage, project=args.project, health_sha=args.health_sha, scope_sha=args.scope_sha)
            with args.file.open('x', encoding='utf-8') as stream:
                stream.write(json.dumps(value, sort_keys=True, indent=2)+'\n')
            print(json.dumps({'format': FORMAT, 'packetSha256': digest(value), 'executionApproved': False}))
        else:
            if any(x is not None for x in (args.stage,args.project,args.health_sha,args.scope_sha)):
                raise Held('Mixed CLI inputs refused')
            if args.file.stat().st_size > 1024*1024: raise Held('Packet size bound exceeded')
            print(json.dumps({'packetSha256':check_packet(json.loads(args.file.read_bytes(), object_pairs_hook=unique_object)), 'executionApproved':False}))
    except Exception:
        print(json.dumps({'format': FORMAT, 'status':'held', 'executionApproved':False}))
        return 2
    return 0


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT/'backend'))
    raise SystemExit(main())
