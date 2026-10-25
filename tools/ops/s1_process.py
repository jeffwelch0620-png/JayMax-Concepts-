"""Owned-process containment for S1. No application, network or credential I/O."""
import ctypes
from ctypes import wintypes
import json
import multiprocessing
import os
import threading
import time
from s1_failure import describe


class ProcessHeld(RuntimeError):
    pass


class OwnedJob:
    """A non-inheritable Windows kill-on-close job; never enumerate processes."""
    def __init__(self):
        self.handle = None
        if os.name != 'nt':
            raise ProcessHeld('windows_containment_required')
        class Basic(ctypes.Structure):
            _fields_ = [('processTime', ctypes.c_int64), ('jobTime', ctypes.c_int64),
                        ('flags', wintypes.DWORD), ('minWorkingSet', ctypes.c_size_t),
                        ('maxWorkingSet', ctypes.c_size_t), ('processLimit', wintypes.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ('reads','writes','other','readBytes','writeBytes','otherBytes')]
        class Extended(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', IO), ('processMemory', ctypes.c_size_t),
                        ('jobMemory', ctypes.c_size_t), ('peakProcessMemory', ctypes.c_size_t),
                        ('peakJobMemory', ctypes.c_size_t)]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel = kernel
        self.handle = kernel.CreateJobObjectW(None, None)
        limits = Extended(); limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise ProcessHeld('job_preparation_failed')

    def assign(self, process):
        if not self.handle or not process.is_alive() or not self.kernel.AssignProcessToJobObject(self.handle, process.sentinel):
            raise ProcessHeld('owned_job_assignment_failed')

    def terminate(self):
        if self.handle and not self.kernel.TerminateJobObject(self.handle, 1):
            raise ProcessHeld('owned_job_termination_failed')

    def empty(self):
        class Accounting(ctypes.Structure):
            _fields_ = [(name, ctypes.c_int64) for name in ('user','kernel','periodUser','periodKernel')] + [
                (name, wintypes.DWORD) for name in ('faults','total','active','terminated')]
        value = Accounting()
        if not self.handle or not self.kernel.QueryInformationJobObject(self.handle, 1, ctypes.byref(value), ctypes.sizeof(value), None):
            raise ProcessHeld('owned_job_query_failed')
        return value.active == 0

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def send(channel, value):
    raw = json.dumps(value, separators=(',', ':'), allow_nan=False).encode()
    if len(raw) > 4096:
        raise ProcessHeld('worker_message_bound')
    channel.send_bytes(raw)


def receive(channel):
    def unique(pairs):
        result = {}
        for key,value in pairs:
            if key in result: raise ValueError
            result[key]=value
        return result
    try:
        raw = channel.recv_bytes(4096)
        value = json.loads(raw,object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (OSError, EOFError, ValueError):
        raise ProcessHeld('worker_message_invalid') from None
    if not isinstance(value, dict):
        raise ProcessHeld('worker_message_invalid')
    return value


def _contained_child(channel, target, args):
    # No prompt/network until the parent has assigned the owned job and grants start.
    try:
        if not channel.poll(10) or receive(channel) != {'start': True}:
            return
        target(channel, *args)
    except BaseException:
        try: send(channel, {'event': 'held'})
        except BaseException: pass
    finally:
        channel.close()


def supervise(target, args=(), *, on_event, guard, seconds, cleanup_seconds=3):
    """Supervise a spawned owned child; parent consumes only bounded JSON events.

    The guard and on_event must themselves be bounded. No OS-freeze guarantee.
    Worker can block in getpass/network without blocking the parent's clock.
    """
    if not 0 < seconds <= 900 or not 0 < cleanup_seconds <= 120:
        raise ProcessHeld('supervisor_budget_invalid')
    guard()
    ctx = multiprocessing.get_context('spawn')
    parent, child = ctx.Pipe(duplex=True)
    process = ctx.Process(target=_contained_child, args=(child, target, args))
    job = OwnedJob()
    started = time.monotonic()
    result, held, cleanup = None, None, False
    stage, held_stage, cleanup_error = 'worker_start', 'unknown', None
    try:
        process.start(); child.close()
        job.assign(process)
        send(parent, {'start': True})
        while True:
            stage = 'supervisor_guard'
            guard()
            if time.monotonic() - started >= seconds:
                raise ProcessHeld('worker_deadline')
            if parent.poll(.05):
                stage = 'worker_protocol'
                event = receive(parent)
                outcome = {}
                def callback():
                    try: outcome['reply'] = on_event(event)
                    except BaseException as error: outcome['error'] = error
                task = threading.Thread(target=callback, daemon=True)
                stage = 'controller_callback'
                task.start()
                while task.is_alive():
                    try:
                        guard()
                        if time.monotonic()-started >= seconds: raise ProcessHeld('worker_deadline')
                    except BaseException:
                        raise ProcessHeld('controller_callback_unconfirmed') from None
                    task.join(.02)
                if 'error' in outcome: raise outcome['error']
                reply = outcome.get('reply')
                if reply is not None: send(parent, reply)
                if event == {'event': 'done'}:
                    result = 'completed'
                    break
                if event == {'event': 'held'}:
                    raise ProcessHeld('worker_held')
            elif not process.is_alive():
                stage = 'worker_wait'
                raise ProcessHeld('worker_exited_without_receipt')
    except BaseException as error:
        held, held_stage = error, stage
    finally:
        parent.close(); child.close()
        try:
            if process.pid:
                process.join(timeout=min(.5, cleanup_seconds))
                job.terminate()  # Includes owned descendants even if the worker exited.
                until = time.monotonic() + cleanup_seconds
                while time.monotonic() < until:
                    if job.empty(): break
                    time.sleep(.02)
                process.join(timeout=max(0, until-time.monotonic()))
                cleanup = not process.is_alive() and job.empty()
        except BaseException as error:
            cleanup_error = error
            cleanup = False
        finally:
            try:
                job.close()
                if process.pid and not process.is_alive(): process.close()
            except BaseException as error:
                if cleanup_error is None: cleanup_error = error
                cleanup = False
    primary = describe(held, held_stage, trusted_types=(ProcessHeld,)) if held is not None else None
    cleanup_failure = (describe(cleanup_error, 'owned_cleanup', trusted_types=(ProcessHeld,))
                       if cleanup_error is not None else
                       {'stage':'owned_cleanup','request':None,'reason':'cleanup_unconfirmed','errorType':'ProcessHeld'}
                       if not cleanup else None)
    if not cleanup:
        error = ProcessHeld('owned_cleanup_unconfirmed')
        error.ownedCleanupConfirmed = False
        error.supervisorFailure, error.cleanupFailure = primary, cleanup_failure
        raise error from None
    if held:
        # Never surface a worker/guard exception string containing private inputs.
        if isinstance(held, (KeyboardInterrupt, SystemExit)):
            held.ownedCleanupConfirmed = cleanup
            held.supervisorFailure, held.cleanupFailure = primary, cleanup_failure
            raise held
        args = BaseException.args.__get__(held)
        category = args[0] if type(held) is ProcessHeld and len(args)==1 and type(args[0]) is str and args[0] in (
            'worker_deadline', 'worker_held', 'worker_exited_without_receipt', 'worker_message_invalid',
            'worker_message_bound', 'owned_job_assignment_failed', 'controller_callback_unconfirmed') else 'supervisor_held'
        error = ProcessHeld(category)
        error.ownedCleanupConfirmed = cleanup
        error.supervisorFailure, error.cleanupFailure = primary, cleanup_failure
        raise error from None
    return {'status': result, 'ownedCleanupConfirmed': cleanup}
