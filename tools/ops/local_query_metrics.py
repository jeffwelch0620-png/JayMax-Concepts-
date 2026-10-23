"""Optional in-process local rehearsal counters; never connect or retain SQL/data.

Inclusive function totals overlap. Exclusive groups attribute each driver method
call once, to its innermost instrumented function (or a fixed catalog category).
Query totals retain their original driver-method boundary. Separate operation
totals observe public cursor/transaction calls, not batches or network round
trips. No metric separates network wait, server work and client scheduling.
No production tool imports this module.
"""
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import hashlib
import time
from unittest.mock import patch

GROUPS = ('readiness', 'fingerprints', 'capture_catalog', 'acl', 'index_state',
          'ledger', 'readiness_check', 'original_columns', 'backup_compare',
          'backup_catalog', 'backup_fingerprints', 'sequences', 'writer_guard',
          'locks', 'apply_ddl', 'session_settings', 'identity', 'object_guard',
          'backend_permissions', 'outcome_check', 'other')
OPERATION_GROUPS = (*GROUPS, 'transaction_control')
OPERATIONS = ('cursor_create', 'cursor_iter', 'cursor_next', 'cursor_await',
              'cursor_fetch', 'cursor_fetchrow', 'cursor_forward',
              'transaction_create', 'transaction_enter', 'transaction_exit',
              'transaction_start', 'transaction_commit', 'transaction_rollback')
OUTCOMES = ('completed', 'errors', 'cancelled', 'exhausted')
# Diagnostic recognition only; the installer independently validates these bytes.
PAR_DDL_SHA256 = '3a189a8b2a352cbd560cea88194dbde1940f160a54e7bcd4616d719c47b88c48'
_scopes = ContextVar('local_rehearsal_query_scopes', default=())


@contextmanager
def query_scope(name):
    if name not in GROUPS:
        raise ValueError('Unknown public timing category')
    token = _scopes.set((*_scopes.get(), name))
    try:
        yield
    finally:
        _scopes.reset(token)


@contextmanager
def instrument_functions(bindings):
    """Temporarily wrap async functions; restore originals even after failure."""
    from contextlib import ExitStack
    def wrapper(function, group):
        @wraps(function)
        async def measured(*args, **kwargs):
            selected = group(args, kwargs) if callable(group) else group
            with query_scope(selected):
                return await function(*args, **kwargs)
        return measured
    with ExitStack() as stack:
        for owner, attribute, group in bindings:
            if not callable(group) and group not in GROUPS:
                raise ValueError('Unknown public timing category')
            original = getattr(owner, attribute)
            stack.enter_context(patch.object(owner, attribute, wrapper(original, group)))
        yield


def relation_group(args, kwargs):
    """Choose fixed labels from the existing relation-kind argument, never names."""
    kind = args[2] if len(args) > 2 else kwargs.get('kind')
    return 'sequences' if kind == 'S' else 'backup_fingerprints'


def par_attribution_bindings(adapter):
    """Local harness bindings only; production modules never call this factory."""
    engine = adapter.engine
    return [
        (engine.readiness, 'inspect', 'readiness'),
        (engine.readiness, 'inspect_index_contracts', 'index_state'),
        (engine.preservation, 'fingerprints', 'fingerprints'),
        (engine.preservation, 'fingerprints_batched', 'fingerprints'),
        (engine.preservation, 'original_columns', 'original_columns'),
        (engine, 'capture_catalog', 'capture_catalog'),
        (engine.preservation, 'ledger_fingerprints', 'ledger'),
        (engine.preservation, 'ledger_contract', 'ledger'),
        (engine, 'verify_prior', 'ledger'),
        (adapter, 'ledger_clients', 'ledger'),
        (engine, 'readiness_check', 'readiness_check'),
        (engine, 'backend_permissions', 'backend_permissions'),
        (engine, 'absent', 'object_guard'),
        (engine, '_verify_outcome', 'outcome_check'),
        (adapter, 'server_version', 'identity'),
        (adapter, 'writer_sessions', 'writer_guard'),
        (engine.preservation, 'lock_original_tables', 'locks'),
        (adapter, 'backup_match', 'backup_compare'),
        (adapter.backup, 'fingerprint', 'backup_catalog'),
        (adapter.backup, 'fingerprint_batched', 'backup_catalog'),
        (adapter.backup, 'relation_fingerprints_batched', 'backup_fingerprints'),
        (adapter.backup, 'relation_fingerprint', relation_group),
    ]


def empty_totals():
    return {'queryCalls': 0, 'querySeconds': 0.0}


def initialize(metrics):
    metrics.setdefault('queryCalls', 0)
    metrics.setdefault('querySeconds', 0.0)
    metrics.setdefault('functionsInclusive', {name: empty_totals() for name in GROUPS})
    metrics.setdefault('exclusiveGroups', {name: empty_totals() for name in GROUPS})


def empty_operations():
    return {'calls': 0, 'seconds': 0.0, **dict.fromkeys(OUTCOMES, 0)}


def initialize_operations(metrics):
    # Lazy: historical query-only receipts retain their exact structure.
    metrics.setdefault('driverOperations', {name: empty_operations() for name in OPERATIONS})
    metrics.setdefault('driverOperationGroups', {
        name: {op: empty_operations() for op in OPERATIONS} for name in OPERATION_GROUPS})


class _OperationObserver:
    def __init__(self, metrics, clock):
        self.metrics, self.clock = metrics, clock

    @contextmanager
    def observe(self, operation, *, iterator_next=False):
        initialize_operations(self.metrics)
        scopes = _scopes.get()
        group = ('transaction_control' if operation.startswith('transaction_')
                 else scopes[-1] if scopes else 'other')
        outcome = 'completed'
        started = self.clock()
        try:
            yield
        except StopAsyncIteration:
            outcome = 'exhausted' if iterator_next else 'errors'
            raise
        except asyncio.CancelledError:
            outcome = 'cancelled'
            raise
        except BaseException:
            outcome = 'errors'
            raise
        finally:
            seconds = self.clock() - started
            for row in (self.metrics['driverOperations'][operation],
                        self.metrics['driverOperationGroups'][group][operation]):
                row['calls'] += 1
                row['seconds'] += seconds
                row[outcome] += 1

    async def call(self, operation, function, *args, **kwargs):
        with self.observe(operation):
            return await function(*args, **kwargs)


class _CursorIterator:
    def __init__(self, target, observer):
        self.target, self.observer = target, observer

    def __aiter__(self):
        return self

    async def __anext__(self):
        # One call per row request, including terminal exhaustion; buffered rows
        # can require no I/O. Never infer fetch batches from prefetch or row count.
        with self.observer.observe('cursor_next', iterator_next=True):
            return await self.target.__anext__()

    def __getattr__(self, name):
        return getattr(self.target, name)


class _Cursor:
    def __init__(self, target, observer):
        self.target, self.observer = target, observer

    def __getattr__(self, name):
        method = getattr(self.target, name)
        if name not in ('fetch', 'fetchrow', 'forward'):
            return method
        async def measured(*args, **kwargs):
            return await self.observer.call('cursor_' + name, method, *args, **kwargs)
        return measured


class _CursorFactory:
    def __init__(self, target, observer):
        self.target, self.observer = target, observer

    def __aiter__(self):
        with self.observer.observe('cursor_iter'):
            iterator = self.target.__aiter__()
        return _CursorIterator(iterator, self.observer)

    def __await__(self):
        async def open_cursor():
            with self.observer.observe('cursor_await'):
                cursor = await self.target
            return _Cursor(cursor, self.observer)
        return open_cursor().__await__()

    def __getattr__(self, name):
        return getattr(self.target, name)


class _Transaction:
    def __init__(self, target, observer):
        self.target, self.observer = target, observer

    async def __aenter__(self):
        return await self.observer.call('transaction_enter', self.target.__aenter__)

    async def __aexit__(self, *args):
        # Delegate the exact exception tuple and suppression result. The driver
        # decides commit/rollback/savepoint behavior; do not infer or double-count.
        return await self.observer.call('transaction_exit', self.target.__aexit__, *args)

    def __getattr__(self, name):
        method = getattr(self.target, name)
        if name not in ('start', 'commit', 'rollback'):
            return method
        async def measured(*args, **kwargs):
            return await self.observer.call('transaction_' + name, method, *args, **kwargs)
        return measured


def exclusive_group(scopes, query):
    # Fixed local classifiers only; never store the query or parameters. Leaf
    # fingerprint/catalog/ledger queries remain attributed to those functions.
    if scopes and scopes[-1] in ('fingerprints', 'capture_catalog', 'ledger',
            'original_columns', 'backup_catalog', 'backup_fingerprints', 'sequences',
            'writer_guard', 'locks', 'backend_permissions', 'object_guard'):
        return scopes[-1]
    text = ' '.join(query.lower().split()) if isinstance(query, str) else ''
    if text.startswith('set '):
        return 'session_settings'
    if text.startswith('lock table ') or (text.startswith('select ') and
            any(name in text for name in ('pg_try_advisory_lock(', 'pg_advisory_xact_lock(', 'pg_advisory_unlock('))):
        return 'locks'
    if isinstance(query, str) and hashlib.sha256(query.encode()).hexdigest() == PAR_DDL_SHA256:
        return 'apply_ddl'
    if text.startswith('insert into supabase_migrations.schema_migrations'):
        return 'ledger'
    if text.startswith('select current_database() as database,current_user as actor,'):
        return 'identity'
    if 'pg_default_acl' in text or 'a.attacl::text as acl' in text:
        return 'acl'
    if 'pg_index' in text and 'indisvalid' in text:
        return 'index_state'
    return scopes[-1] if scopes else 'other'


class MeasuredConnection:
    def __init__(self, connection, metrics, *, clock=time.monotonic):
        self.connection, self.metrics, self.clock = connection, metrics, clock
        initialize(metrics)
        self.observer = _OperationObserver(metrics, clock)

    def cursor(self, *args, **kwargs):
        with self.observer.observe('cursor_create'):
            factory = self.connection.cursor(*args, **kwargs)
        return _CursorFactory(factory, self.observer)

    def transaction(self, *args, **kwargs):
        with self.observer.observe('transaction_create'):
            transaction = self.connection.transaction(*args, **kwargs)
        return _Transaction(transaction, self.observer)

    def __getattr__(self, name):
        method = getattr(self.connection, name)
        if name not in ('execute', 'fetch', 'fetchval', 'fetchrow'):
            return method
        async def measured(*args, **kwargs):
            scopes = _scopes.get()
            group = exclusive_group(scopes, args[0] if args else kwargs.get('query'))
            started = self.clock()
            try:
                return await method(*args, **kwargs)
            finally:
                seconds = self.clock() - started
                self.metrics['queryCalls'] += 1
                self.metrics['querySeconds'] += seconds
                exclusive = self.metrics['exclusiveGroups'][group]
                exclusive['queryCalls'] += 1
                exclusive['querySeconds'] += seconds
                for label in set(scopes):
                    inclusive = self.metrics['functionsInclusive'][label]
                    inclusive['queryCalls'] += 1
                    inclusive['querySeconds'] += seconds
        return measured


def finish(metrics):
    initialize(metrics)
    if sum(row['queryCalls'] for row in metrics['exclusiveGroups'].values()) != metrics['queryCalls']:
        raise ValueError('Exclusive query counts do not reconcile')
    if abs(sum(row['querySeconds'] for row in metrics['exclusiveGroups'].values()) - metrics['querySeconds']) > 1e-6:
        raise ValueError('Exclusive query seconds do not reconcile')
    metrics['querySeconds'] = round(metrics['querySeconds'], 6)
    for key in ('functionsInclusive', 'exclusiveGroups'):
        for row in metrics[key].values():
            row['querySeconds'] = round(row['querySeconds'], 6)
    if 'driverOperations' in metrics:
        for operation, total in metrics['driverOperations'].items():
            rows = [group[operation] for group in metrics['driverOperationGroups'].values()]
            for key in ('calls', *OUTCOMES):
                if sum(row[key] for row in rows) != total[key]:
                    raise ValueError('Exclusive driver operations do not reconcile')
            if abs(sum(row['seconds'] for row in rows) - total['seconds']) > 1e-6:
                raise ValueError('Exclusive driver seconds do not reconcile')
            for row in (total, *rows):
                if sum(row[key] for key in OUTCOMES) != row['calls']:
                    raise ValueError('Driver operation outcomes do not reconcile')
                row['seconds'] = round(row['seconds'], 6)
