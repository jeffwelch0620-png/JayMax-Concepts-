"""Bounded numeric memory observations. No process names, inputs or paths."""
from copy import deepcopy
import math
import threading

import read_only_probe as probe

VERSION = 2
PHASES = ('input', 'pre_claim', 'post_claim_setup', 'quiet_wait', 'requests', 'recovery_wait', 'cleanup')
MAX_SAMPLES = 1000000
QUIET_HEADROOM_MIB = 1536


def enabled(profile):
    return profile['mode'] == 'hosted' or profile.get('rehearsalResources') == 'real'


def phase(stage):
    if stage == 'quiet_wait': return 'quiet_wait'
    if stage == 'recovery_wait': return 'recovery_wait'
    if stage == 'request': return 'requests'
    if stage in ('worker_cleanup', 'owned_cleanup', 'controller_finish'): return 'cleanup'
    if stage in ('worker_dispatch_check', 'worker_transport', 'worker_sequence'):
        return 'post_claim_setup'
    if stage in ('worker_dispatch_wait', 'controller_claim'):
        return 'pre_claim'
    return 'input'


def validate(value, previous=None):
    if type(value) is not dict or set(value) != set(PHASES):
        raise ValueError('resource_summary_invalid')
    for name, row in value.items():
        if type(row) is not dict or set(row) != {'samples', 'minFreeMiB', 'minFreePercent'}:
            raise ValueError('resource_summary_invalid')
        n = row['samples']
        if type(n) is not int or not 0 <= n <= MAX_SAMPLES:
            raise ValueError('resource_summary_invalid')
        for key, limit in (('minFreeMiB', 2**40), ('minFreePercent', 100)):
            v = row[key]
            if n == 0:
                if v is not None: raise ValueError('resource_summary_invalid')
            elif type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= limit:
                raise ValueError('resource_summary_invalid')
        if previous is not None:
            old = previous[name]
            if n < old['samples'] or old['samples'] and any(
                    row[k] > old[k] for k in ('minFreeMiB', 'minFreePercent')):
                raise ValueError('resource_summary_invalid')
    return deepcopy(value)


def validate_pair(value):
    if (type(value) is not dict or set(value) != {'version', 'supervisor', 'worker'}
            or type(value['version']) is not int or value['version'] != VERSION):
        raise ValueError('resource_summary_invalid')
    return {'version': VERSION, **{k: validate(value[k]) if value[k] is not None else None
                                 for k in ('supervisor', 'worker')}}


def quiet_gate(value):
    """A numeric pre-live evidence check, never execution authority."""
    pair=validate_pair(value)
    rows={k:pair[k]['quiet_wait'] if pair[k] is not None else
          {'samples':0,'minFreeMiB':None} for k in ('supervisor','worker')}
    return {'passed':all(r['samples']>0 and r['minFreeMiB']>=QUIET_HEADROOM_MIB for r in rows.values()),
            'requiredFreeMiB':QUIET_HEADROOM_MIB,
            **{k+'Samples':r['samples'] for k,r in rows.items()},
            **{k+'MinFreeMiB':r['minFreeMiB'] for k,r in rows.items()}}


class Monitor:
    def __init__(self, active):
        if type(active) is not bool: raise ValueError('resource_mode_invalid')
        self.active, self.current, self.failed = active, 'input', False
        self._lock = threading.Lock()
        self._rows = {p: {'samples': 0, 'minFreeMiB': None, 'minFreePercent': None} for p in PHASES}

    def set_phase(self, name):
        if name not in PHASES: raise ValueError('resource_phase_invalid')
        with self._lock: self.current = name

    def _record(self, value):
        if (type(value) is not dict or set(value) != {'freeBytes', 'totalBytes'}
                or any(type(value[k]) is not int for k in value)
                or not 0 <= value['freeBytes'] <= value['totalBytes'] or value['totalBytes'] <= 0):
            raise probe.Held('Memory observation unavailable')
        free, percent = value['freeBytes'] / 2**20, 100 * value['freeBytes'] / value['totalBytes']
        with self._lock:
            row = self._rows[self.current]
            if row['samples'] >= MAX_SAMPLES: raise probe.Held('Memory observation bound exceeded')
            row['samples'] += 1
            row['minFreeMiB'] = free if row['minFreeMiB'] is None else min(free, row['minFreeMiB'])
            row['minFreePercent'] = percent if row['minFreePercent'] is None else min(percent, row['minFreePercent'])

    def check(self, *, start=False):
        if self.active:
            try: return probe.resources(start=start, observe=self._record)
            except probe.Held:
                self.failed = True
                raise

    def observe_cleanup(self):
        # Cleanup is never refused or interrupted because memory is low.
        if self.active:
            self.set_phase('cleanup')
            try: self._record(probe.memory())
            except Exception: pass  # Optional measurement must not replace cleanup/primary failure.

    def snapshot(self):
        with self._lock: return validate(self._rows)


def select(profile, supplied=None):
    active=enabled(profile)
    if supplied is None:return Monitor(active)
    if type(supplied) is not Monitor or supplied.active is not active:
        raise ValueError('resource_mode_invalid')
    return supplied
