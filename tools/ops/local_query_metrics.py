"""Optional in-process local rehearsal counters; never connect or retain SQL/data.

Inclusive function totals overlap. Exclusive groups attribute each driver method
call once, to its innermost instrumented function (or a fixed catalog category).
Neither metric includes cursor/transaction protocol traffic or separates network
wait, server work and client scheduling. No production tool imports this module.
"""
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
        (adapter.backup, 'relation_fingerprint', relation_group),
    ]


def empty_totals():
    return {'queryCalls': 0, 'querySeconds': 0.0}


def initialize(metrics):
    metrics.setdefault('queryCalls', 0)
    metrics.setdefault('querySeconds', 0.0)
    metrics.setdefault('functionsInclusive', {name: empty_totals() for name in GROUPS})
    metrics.setdefault('exclusiveGroups', {name: empty_totals() for name in GROUPS})


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
