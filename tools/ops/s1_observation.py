"""S1 diagnostic core. No CLI, credentials, default transport or import-time I/O.

The operator must separately bind approval, source, resources, target, claim and
an exclusively created private evidence stream before supplying a connector.
Tests supply only fictional in-process connections. This module authorizes no run.
"""
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
import inspect
import os
import re
import time

from readonly_snapshot import readonly_snapshot

PHASES = ('metadata', 'audit')
READS = ('identity', 'relations', 'policies', 'pin_configuration', 'toast_jobs',
         'sessions', 'ledger', 'summary', 'breakdown', 'records')
LABELS = {f'{phase}.{op}' for phase in PHASES
          for op in (*READS, 'connect', 'begin', 'settings', 'commit', 'rollback',
                     'close', 'terminate', 'confirm_closed')}
LABELS.add('evidence.checkpoint')
ERROR_TYPES = frozenset(('TimeoutError', 'CancelledError', 'ConnectionError',
    'OSError', 'RuntimeError', 'ValueError', 'TypeError', 'ObservationHeld',
    'InterfaceError', 'QueryCanceledError', 'ConnectionDoesNotExistError',
    'PostgresError', 'KeyboardInterrupt', 'SystemExit'))


class ObservationHeld(ValueError):
    pass


def checkpoint_bytes(label, value):
    def encode(value):
        if isinstance(value, datetime):
            return value.isoformat()
        raise TypeError('Unsupported private checkpoint type')
    return (json.dumps({'format': 'jaymax-s1-checkpoint-v1', 'operation': label,
                       'data': value}, default=encode, allow_nan=False) + '\n').encode()


def safe_error(error):
    name = type(error).__name__
    try:
        state = getattr(error, 'sqlstate', None)
    except BaseException:
        state = None  # Error formatting must not replace the original failure.
    return {'errorType': name if name in ERROR_TYPES else 'OtherError',
            'sqlState': state if isinstance(state, str) and re.fullmatch(r'[A-Z0-9]{5}', state) else None}


class JsonlCheckpoints:
    """Append to an already prepared private stream; never open/repair a path.

    Private ACL/ownership verification is the operator boundary's responsibility.
    Flush/fsync each completed observation, so later failure retains its prefix.
    A partial final line is not a completed checkpoint; earlier lines stay valid.
    """
    def __init__(self, stream):
        self.stream = stream
        self.bytes_written = 0
        self.failed = False

    def __call__(self, label, value):
        if self.failed:
            raise ObservationHeld('Failed private stream cannot be reused')
        if label not in LABELS or label.rsplit('.', 1)[-1] not in READS:
            raise ObservationHeld('Unsupported private checkpoint')
        raw = checkpoint_bytes(label, value)
        if len(raw) > 128 * 1024 or self.bytes_written + len(raw) > 512 * 1024:
            raise ObservationHeld('Private checkpoint size held')
        try:
            written = self.stream.write(raw)
            if written != len(raw):
                raise ObservationHeld('Incomplete private checkpoint write')
            self.stream.flush()
            os.fsync(self.stream.fileno())
        except BaseException:
            self.failed = True
            raise
        self.bytes_written += written


class Diagnostics:
    def __init__(self, checkpoint, *, clock=time.monotonic):
        if (not callable(checkpoint) or inspect.iscoroutinefunction(checkpoint)
                or inspect.iscoroutinefunction(getattr(checkpoint, '__call__', None))):
            raise ObservationHeld('Prepared private checkpoint sink required')
        self.checkpoint = checkpoint
        self.clock = clock
        self.events = []
        self.completed = []
        self.status = 'not_started'
        self.primary = None
        self.closed = {}
        self.truncated = False
        self.envelope_expired = False
        # None means not durably observed, never zero/complete by default.
        self.audit_coverage = {'auditTotal': None, 'recordsTruncated': None,
                               'breakdownTruncated': None}

    @asynccontextmanager
    async def step(self, label, *, target=None, cleanup=False):
        if label not in LABELS or (target is not None and target not in LABELS):
            raise ObservationHeld('Unsupported diagnostic operation')
        if len(self.events) >= 64:
            self.truncated = True
            if cleanup:
                # Diagnostic capacity must never prevent actual owned cleanup.
                yield
                return
            raise ObservationHeld('Diagnostic event budget held')
        event = {'operation': label, 'status': 'running'}
        if target is not None:
            event['checkpointFor'] = target
        self.events.append(event)
        began = self.clock()
        try:
            yield
        except BaseException as error:
            event.update(status='failed', **safe_error(error))
            raise
        else:
            event['status'] = 'completed'
        finally:
            event['elapsedSeconds'] = round(max(0, self.clock() - began), 6)

    async def run(self, label, action, *, cleanup=False):
        async with self.step(label, cleanup=cleanup):
            return await action()

    async def capture(self, label, value):
        # Completed observations are persisted immediately, not at whole-run end.
        coverage = {}
        if label == 'audit.summary':
            total = value.get('total') if isinstance(value, dict) else None
            if type(total) is not int or total < 0:
                raise ObservationHeld('Valid audit total required')
            coverage['auditTotal'] = total
        elif label in ('audit.breakdown', 'audit.records'):
            key = 'breakdownTruncated' if label == 'audit.breakdown' else 'recordsTruncated'
            flag = value.get(key) if isinstance(value, dict) else None
            if type(flag) is not bool:
                raise ObservationHeld('Explicit audit coverage required')
            coverage[key] = flag
        async with self.step('evidence.checkpoint', target=label):
            result = self.checkpoint(label, value)
            if inspect.iscoroutine(result):
                result.close()
                raise ObservationHeld('Synchronous completed checkpoint required')
            if result is not None:
                raise ObservationHeld('Synchronous completed checkpoint required')
        self.completed.append(label)
        self.audit_coverage.update(coverage)

    def receipt(self):
        failed = next((event for event in self.events if event['status'] == 'failed'), None)
        result = {'format': 'jaymax-s1-diagnostics-v1', 'status': self.status,
                  'operations': deepcopy(self.events), 'completedObservations': list(self.completed),
                  'failedOperation': failed['operation'] if failed else None,
                  'ownedClientsClosed': dict(self.closed), 'diagnosticsTruncated': self.truncated,
                  'envelopeExpired': self.envelope_expired, **self.audit_coverage}
        if self.primary is not None:
            result['error'] = safe_error(self.primary)
        return result


class _Transaction:
    def __init__(self, tx, diagnostics, phase):
        self.tx, self.diagnostics, self.phase = tx, diagnostics, phase

    async def start(self):
        return await self.diagnostics.run(self.phase + '.begin', self.tx.start)

    async def commit(self):
        return await self.diagnostics.run(self.phase + '.commit', self.tx.commit)

    async def rollback(self):
        return await self.diagnostics.run(self.phase + '.rollback', self.tx.rollback)


class _SnapshotConnection:
    def __init__(self, conn, diagnostics, phase):
        self.conn, self.diagnostics, self.phase = conn, diagnostics, phase

    def transaction(self, **options):
        return _Transaction(self.conn.transaction(**options), self.diagnostics, self.phase)


async def close_owned(conn, diagnostics, phase, primary):
    """A close/terminate error never replaces an earlier observation failure."""
    failure = None
    diagnostics.closed[phase] = False
    try:
        await diagnostics.run(phase + '.close',
            lambda: asyncio.wait_for(conn.close(timeout=4), 4), cleanup=True)
    except BaseException as error:
        failure = error
        try:
            async with diagnostics.step(phase + '.terminate', cleanup=True):
                conn.terminate()  # Only this returned owned client; no backend SQL.
        except BaseException as cleanup:
            target = primary if primary is not None else failure
            target.connectionTerminateErrorType = safe_error(cleanup)['errorType']
    try:
        async with diagnostics.step(phase + '.confirm_closed', cleanup=True):
            diagnostics.closed[phase] = conn.is_closed() is True
            if not diagnostics.closed[phase]:
                raise ObservationHeld('Owned client closure unconfirmed')
    except BaseException as error:
        failure = failure or error
    if failure is not None:
        if primary is None:
            raise failure
        primary.connectionCloseErrorType = safe_error(failure)['errorType']


async def observe(connect, plans, diagnostics, *, remaining_seconds, work_seconds=120):
    """Run at most two fixed read-only phases with an injected approved connector.

    ``plans`` is exactly metadata/audit: each holds fixed (label, reader) pairs.
    A reader receives its owned connection and returns minimized private data.
    No retry or credential/configuration lookup exists. This is not an approval
    boundary: the separately reviewed operator handoff must enforce the packet.
    """
    if (diagnostics.status != 'not_started' or not callable(connect)
            or type(work_seconds) not in (int, float) or not 7 < work_seconds <= 120
            or type(remaining_seconds) not in (int, float) or not 7 < remaining_seconds <= 780
            or list(plans) != list(PHASES)):
        raise ObservationHeld('Bounded fresh observation required')
    for phase, readers in plans.items():
        labels = [label for label, _ in readers]
        if (len(set(labels)) != len(labels) or not labels
                or any(label != phase + '.' + label.rsplit('.', 1)[-1]
                       or label.rsplit('.', 1)[-1] not in READS
                       or not callable(reader) for label, reader in readers)):
            raise ObservationHeld('Fixed read-only observation plan required')
    # Keep the validated sequence stable while individual readers are awaited.
    plans = {phase: tuple(readers) for phase, readers in plans.items()}
    diagnostics.status = 'running'
    envelope = asyncio.timeout(min(work_seconds, remaining_seconds) - 7)
    try:
        # Reserve the existing 3-second rollback + 4-second owned close inside
        # the total envelope, rather than tacking cleanup onto its deadline.
        async with envelope:
            for phase, readers in plans.items():
                conn = None
                primary = None
                try:
                    conn = await diagnostics.run(phase + '.connect',
                        lambda: connect(phase, readonly=True, timeout=10, command_timeout=10))
                    tracked = _SnapshotConnection(conn, diagnostics, phase)
                    async with readonly_snapshot(tracked, rollback_timeout=3):
                        await diagnostics.run(phase + '.settings', lambda: conn.execute(
                            "SET LOCAL statement_timeout='10s'; SET LOCAL lock_timeout='1s'"))
                        for label, reader in readers:
                            value = await diagnostics.run(label, lambda: reader(conn))
                            await diagnostics.capture(label, value)
                except BaseException as error:
                    primary = error
                    raise
                finally:
                    if conn is not None:
                        await close_owned(conn, diagnostics, phase, primary)
    except BaseException as error:
        diagnostics.envelope_expired = envelope.expired()
        diagnostics.status = 'held'
        diagnostics.primary = error
        raise
    else:
        diagnostics.status = 'complete'
    return diagnostics.receipt()


OBJECTS = ('public.activity_log', 'public.app_users', 'public.push_subscriptions',
    'public.store_state', 'public.staff_pins', 'purchasing.inventory_par_versions',
    'purchasing.unit_profiles', 'purchasing.item_bases', 'public.items',
    'public.store_items', 'public.dishes', 'public.dish_lines',
    'public.prep_items', 'public.staff_members')

AUDIT_GROUP_LIMIT = 500
AUDIT_BREAKDOWN_BYTES = 96 * 1024  # Leaves room under the 128 KiB checkpoint cap.


async def collect(connect, diagnostics, *, audit_from, as_of, remaining_seconds):
    """The existing S1 query scope, now using checkpointed diagnostic operations.

    This supplies no connection implementation or live approval. The separately
    reviewed operator handoff must check its exact packet/target, prepare the
    private sink and claim, and bind the same audit interval before calling it.
    """
    if (not isinstance(audit_from, datetime) or not isinstance(as_of, datetime)
            or audit_from.utcoffset() is None or as_of.utcoffset() is None
            or audit_from > as_of):
        raise ObservationHeld('Bounded timezone-aware audit interval required')

    async def identity(conn):
        row = dict(await conn.fetchrow("SELECT current_user AS actor,session_user AS login,"
            "current_database() AS db,current_setting('transaction_read_only') AS readonly"))
        if row != {'actor':'postgres','login':'postgres','db':'postgres','readonly':'on'}:
            raise ObservationHeld('Maintenance read-only identity held')
        return {'maintenanceIdentityAndReadOnlyVerified': True}

    def rows(sql, *args):
        async def read(conn):
            return [dict(row) for row in await conn.fetch(sql, *args)]
        return read

    audit_args = (audit_from, as_of, ['owner', 'manager'])
    audit_filter = 'created_at >= $1 AND created_at < $2 AND role=ANY($3::text[])'

    async def summary(conn):
        return dict(await conn.fetchrow('SELECT count(*) AS total, '
            'min(created_at) AS first_at, max(created_at) AS last_at '
            'FROM public.activity_log WHERE ' + audit_filter, *audit_args))

    async def breakdown(conn):
        groups = await conn.fetch('''SELECT date_trunc('day', created_at AT TIME ZONE 'UTC') AS day,
            role,user_id,method,(status/100)::int AS status_class,count(*) AS n
            FROM public.activity_log WHERE ''' + audit_filter + '''
            GROUP BY 1,2,3,4,5 ORDER BY 1,2,3,4,5 LIMIT 501''', *audit_args)
        result = {'groups': [], 'breakdownTruncated': len(groups) > AUDIT_GROUP_LIMIT}
        for row in groups[:AUDIT_GROUP_LIMIT]:
            result['groups'].append(dict(row))
            if len(checkpoint_bytes('audit.breakdown', result)) > AUDIT_BREAKDOWN_BYTES:
                result['groups'].pop()
                result['breakdownTruncated'] = True
                break
        return result

    async def records(conn):
        total = diagnostics.audit_coverage['auditTotal']
        if total is None:
            raise ObservationHeld('Durable audit summary required before sampling')
        fields = 'id,created_at,user_id,role,method,path,status,store_id'
        sample = await conn.fetch('WITH first_rows AS (SELECT ' + fields +
            ' FROM public.activity_log WHERE ' + audit_filter +
            ' ORDER BY created_at ASC,id ASC LIMIT 100), last_rows AS (SELECT ' + fields +
            ' FROM public.activity_log WHERE ' + audit_filter +
            ''' ORDER BY created_at DESC,id DESC LIMIT 100)
            SELECT sample,created_at,user_id,role,method,path,status,store_id FROM (
                SELECT 'earliest' AS sample,* FROM first_rows UNION ALL
                SELECT 'latest' AS sample,* FROM last_rows) samples
            ORDER BY sample,created_at,id''', *audit_args)
        result = {'earliest': [], 'latest': [], 'recordsTruncated': total > 200}
        for row in sample:
            row = dict(row)
            side = row.pop('sample')
            if side not in ('earliest', 'latest') or len(result[side]) >= 100:
                raise ObservationHeld('Bounded audit sample required')
            result[side].append(row)
        return result

    plans = {
        'metadata': [
            ('metadata.identity', identity),
            ('metadata.relations', rows('''SELECT n.nspname AS schema,c.relname AS name,
                c.relrowsecurity AS rls,c.relforcerowsecurity AS force_rls
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname||'.'||c.relname=ANY($1::text[]) ORDER BY 1,2''', list(OBJECTS))),
            ('metadata.policies', rows('''SELECT schemaname,tablename,policyname,permissive,roles,cmd
                FROM pg_policies WHERE schemaname||'.'||tablename=ANY($1::text[])
                ORDER BY schemaname,tablename,policyname LIMIT 100''', list(OBJECTS))),
            ('metadata.pin_configuration', rows("SELECT store_id,coalesce(pin ~ '^[0-9]{4,8}$',false) AS configured "
                "FROM public.staff_pins WHERE store_id=ANY($1::text[]) ORDER BY store_id", ['berts','rudds','papa'])),
            ('metadata.toast_jobs', rows('SELECT jobid,active,schedule FROM cron.job WHERE jobid=ANY($1::bigint[]) ORDER BY jobid', [3,4])),
            ('metadata.sessions', rows('''SELECT usename,application_name,state,backend_start,pid::text AS session_ref
                FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()
                ORDER BY backend_start,pid LIMIT 20''')),
            ('metadata.ledger', rows('SELECT version::text,name::text FROM supabase_migrations.schema_migrations ORDER BY version::text,name::text LIMIT 64'))],
        'audit': [('audit.identity', identity), ('audit.summary', summary),
                  ('audit.breakdown', breakdown), ('audit.records', records)]
    }
    return await observe(connect, plans, diagnostics, remaining_seconds=remaining_seconds)
