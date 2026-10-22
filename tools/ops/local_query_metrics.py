"""Optional in-process local rehearsal counters; never connect or retain SQL/data.

Inclusive function totals overlap. Exclusive groups attribute each driver method
call once, to its innermost instrumented function (or a fixed catalog category).
Neither metric includes cursor/transaction protocol traffic or separates network
wait, server work and client scheduling. No production tool imports this module.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import time
from unittest.mock import patch

GROUPS = ('readiness', 'fingerprints', 'capture_catalog', 'acl', 'index_state',
          'ledger', 'readiness_check', 'other')
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
            with query_scope(group):
                return await function(*args, **kwargs)
        return measured
    with ExitStack() as stack:
        for owner, attribute, group in bindings:
            if group not in GROUPS:
                raise ValueError('Unknown public timing category')
            original = getattr(owner, attribute)
            stack.enter_context(patch.object(owner, attribute, wrapper(original, group)))
        yield


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
    if scopes and scopes[-1] in ('fingerprints', 'capture_catalog', 'ledger'):
        return scopes[-1]
    text = ' '.join(query.lower().split()) if isinstance(query, str) else ''
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
