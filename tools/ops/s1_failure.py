"""Closed-vocabulary S1 diagnostics. Never serialize exception text or inputs."""
import asyncio

STAGES = frozenset(('unknown', 'worker_profile', 'worker_approval', 'worker_input',
    'worker_dispatch_wait', 'worker_dispatch_check', 'worker_transport',
    'worker_sequence', 'quiet_wait', 'recovery_wait', 'request', 'worker_cleanup',
    'controller_guard', 'controller_message', 'controller_claim', 'controller_intent',
    'controller_result', 'controller_finish', 'controller_profile', 'controller_approval',
    'controller_evidence', 'controller_execute', 'supervisor_guard', 'worker_start',
    'worker_wait', 'worker_protocol', 'controller_callback', 'owned_cleanup'))
REQUESTS = frozenset(('P01', 'P02', 'L01', 'L02', 'L03',
    *(f'P{i:02}' for i in range(3, 13)), *(f'R{i:02}' for i in range(1, 7))))
WORKER_STAGES = frozenset(s for s in STAGES if s.startswith('worker_')) | frozenset(
    ('quiet_wait', 'recovery_wait', 'request'))
REASONS = frozenset(('unknown_error', 'held', 'value_error', 'type_error', 'io_error',
    'runtime_error', 'assertion_error', 'timeout', 'cancelled', 'interrupted',
    'end_of_input', 'permission_error', 'not_found', 'connection_error', 'import_error',
    'cleanup_unconfirmed', 'resource_guard_failed', 'worker_held', 'worker_deadline',
    'worker_exited_without_receipt', 'worker_message_invalid', 'worker_message_bound',
    'controller_callback_unconfirmed', 'owned_job_assignment_failed',
    'owned_job_termination_failed', 'owned_job_query_failed', 'owned_cleanup_unconfirmed',
    'window_closed', 'profile_or_sources_changed', 'exact_approval_required',
    'actor_bindings_invalid', 'window_insufficient_before_claim', 'resource_headroom_insufficient', 'private_binding_changed',
    'local_input_entries_exhausted', 'fictional_inputs_required', 'dispatch_not_granted',
    'result_not_acknowledged', 'supervised_production_transport_required',
    'target_binding_invalid', 'invalid_deadline', 'local_guard_failed',
    'initial_evidence_failed', 'evidence_write_failed', 'dispatch_order_invalid',
    'worker_result_invalid', 'pin_input', 'unexpected_status', 'request_failed',
    'response_type', 'response_size', 'response_shape', 'encoded_response',
    'approved_actor_mismatch', 'login_shape', 'login_identity', 'probe_shape'))
ERROR_TYPES = frozenset(('OtherError', 'Held', 'ProcessHeld', 'ValueError', 'TypeError',
    'OSError', 'RuntimeError', 'AssertionError', 'TimeoutError', 'CancelledError',
    'KeyboardInterrupt', 'SystemExit', 'EOFError', 'PermissionError', 'FileNotFoundError',
    'BrokenPipeError', 'ConnectionError', 'ImportError'))
_ORDERED = ((PermissionError, 'PermissionError', 'permission_error'),
    (FileNotFoundError, 'FileNotFoundError', 'not_found'),
    (BrokenPipeError, 'BrokenPipeError', 'connection_error'),
    (ConnectionError, 'ConnectionError', 'connection_error'),
    (ImportError, 'ImportError', 'import_error'),
    (TimeoutError, 'TimeoutError', 'timeout'), (EOFError, 'EOFError', 'end_of_input'),
    (OSError, 'OSError', 'io_error'), (asyncio.CancelledError, 'CancelledError', 'cancelled'),
    (KeyboardInterrupt, 'KeyboardInterrupt', 'interrupted'), (SystemExit, 'SystemExit', 'interrupted'),
    (AssertionError, 'AssertionError', 'assertion_error'), (TypeError, 'TypeError', 'type_error'),
    (ValueError, 'ValueError', 'value_error'), (RuntimeError, 'RuntimeError', 'runtime_error'))


def position(stage, request=None):
    if (type(stage) is not str or stage not in STAGES
            or (request is not None and (type(request) is not str or request not in REQUESTS))
            or (stage == 'request' and request is None)
            or (stage not in ('request', 'recovery_wait') and request is not None)):
        raise ValueError('invalid_failure_position')
    return {'stage': stage, 'request': request}


def describe(error, stage, request=None, *, trusted_types=()):
    result = position(stage, request)
    kind, reason = 'OtherError', 'unknown_error'
    # Exact caller-owned exception classes only. No str/repr, subclass properties,
    # arbitrary class names, traceback, paths or exception chains are inspected.
    if any(type(error) is trusted for trusted in trusted_types):
        kind, reason = ('ProcessHeld' if type(error).__name__ == 'ProcessHeld' else 'Held'), 'held'
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in REASONS:
            reason = args[0]
    else:
        # Inspect the actual class ancestry, not an instance's spoofable __class__.
        ancestry = type.__getattribute__(type(error), '__mro__')
        for base, name, category in _ORDERED:
            if any(base is member for member in ancestry):
                kind, reason = name, category
                break
    return {**result, 'reason': reason, 'errorType': kind}


def validate(value, *, requests=REQUESTS):
    if type(value) is not dict or set(value) != {'stage', 'request', 'reason', 'errorType'}:
        raise ValueError('invalid_failure_descriptor')
    pos = position(value['stage'], value['request'])
    if (value['request'] is not None and value['request'] not in requests
            or type(value['reason']) is not str or value['reason'] not in REASONS
            or type(value['errorType']) is not str or value['errorType'] not in ERROR_TYPES):
        raise ValueError('invalid_failure_descriptor')
    return {**pos, 'reason': value['reason'], 'errorType': value['errorType']}


def validate_summary(value, *, requests=REQUESTS):
    failures = ('primaryFailure', 'workerCleanupFailure', 'supervisorFailure',
                'supervisorCleanupFailure', 'closureFailure')
    if (type(value) is not dict or set(value) != {'version', 'workerPosition', 'controllerStage', *failures}
            or type(value['version']) is not int or value['version'] != 1
            or type(value['controllerStage']) is not str or value['controllerStage'] not in STAGES):
        raise ValueError('invalid_failure_summary')
    pos = value['workerPosition']
    if pos is not None:
        if type(pos) is not dict or set(pos) != {'stage', 'request'}:
            raise ValueError('invalid_failure_summary')
        pos = position(pos['stage'], pos['request'])
        if pos['stage'] not in WORKER_STAGES or pos['request'] is not None and pos['request'] not in requests:
            raise ValueError('invalid_failure_summary')
    return {'version': 1, 'workerPosition': pos, 'controllerStage': value['controllerStage'],
            **{k: validate(value[k], requests=requests) if value[k] is not None else None for k in failures}}
