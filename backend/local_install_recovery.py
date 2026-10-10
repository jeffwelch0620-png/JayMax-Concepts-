"""Independently pinned local archives and fresh-process journal reconciliation.

No hosted targets, config writer, password staging, automatic retry or retirement.
Archive hashes must come from the owning supervisor before any mutation, never
from the archive/journal being recovered or the current database catalog.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
import asyncpg
import local_parallel_install as local

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('backend/local_install_recovery.py', 'backend/local_parallel_install.py',
    'backend/parallel_install_plan.py', 'backend/parallel_rotation_review.py',
    'backend/credential_retirement_review.py', 'backend/runtime_permissions.py',
    'backend/auxiliary_permissions.py', 'backend/transition_permissions.py',
    'backend/connection_transition.py', 'backend/db_pg.py', 'backend/db_auxiliary.py',
    'backend/db_tls.py', 'backend/deployment_readiness.py',
    'backend/schema_reconciliation.py', 'backend/hosted_install_preservation.py',
    'backend/native_backup.py', 'docs/RUNTIME_PERMISSION_CANDIDATE.json',
    'docs/RUNTIME_CATALOG_CONTRACT.json')
STEPS = ('create', 'overlap', 'enable', 'restore', 'disable_revoke')
FORMAT = 'jaymax-local-independent-install-archive-v1'
MAX_BYTES = 16 * 1024 * 1024


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def source_hashes():
    return {name: sha((ROOT / name).read_bytes()) for name in SOURCES}


def baseline_plan(baseline, originals, replacements):
    # JSON object order is not a plan input. Use the same profile order as the
    # local controller, including when a sorted archive is read in a new process.
    originals = {kind: originals[kind] for kind in ('inventory', 'accounts')}
    replacements = {kind: replacements[kind] for kind in ('inventory', 'accounts')}
    old = {row['oid'] for row in baseline['roles'] if row['rolname'] in originals.values()}
    policies = [row for row in baseline['policies'] if set(row['role_oids']) & (old | {0})]
    outgoing = [row for row in baseline['memberships'] if row['member'] in old]
    pins = {'applicationRows': local.digest(baseline['rows']),
            'track1': local.digest({name: value for name, value in baseline['rows'].items()
                                   if name.startswith('actual_inventory.')}),
            'migrationLedger': local.digest(baseline['ledger']),
            'unaffectedAccess': local.digest(baseline['access']),
            'administrativeMemberships': local.digest(baseline['memberships'])}
    return local.plans.prepare(originals, baseline['roles'], policies, outgoing,
                               replacements, preservation_pins=pins, reference='local')


async def initial_profiles(controller):
    """Actual original LOGINs/default constructors and separate inventory check."""
    pools = []
    try:
        for kind, module in (('inventory', local.db_pg), ('accounts', local.db_auxiliary)):
            pool = await module._try_connect(controller.profile_urls('original')[kind])
            if pool is None: raise local.RehearsalHeld('Original preflight pool held')
            pools.append(pool)
            async with pool.acquire() as conn:
                role = controller.plan['originalRoles'][kind]
                if await conn.fetchval('SELECT session_user') != role:
                    raise local.RehearsalHeld('Original preflight LOGIN identity held')
                result = (await local.runtime.inspect(conn, role) if kind == 'inventory'
                          else await local.auxiliary_permissions.inspect(conn))
                if (result['status'] != ('passed_local_candidate' if kind == 'inventory' else 'passed')
                        or result['policyMode'] != 'single_role' or not result['readOnly']
                        or result['issues'] or result['operationalReleaseApproved']):
                    raise local.RehearsalHeld('Original permission preflight held')
    finally:
        for pool in reversed(pools): await local.startup.close_owned(pool)


async def archive(controller, path):
    """Exclusive fsynced metadata archive BEFORE mutations; return independent pin."""
    if controller.completed or controller.held or len(controller.journal.rows()) != 1:
        raise local.RehearsalHeld('Archive requires untouched independently prepared baseline')
    if (any(row['rolconfig'] for row in controller.baseline['roles']) or controller.baseline['settings']):
        raise local.RehearsalHeld('Local archive requires no opaque role configuration values')
    expected = baseline_plan(controller.baseline, controller.plan['originalRoles'],
                             controller.plan['proposedReplacementRoles'])
    if local.digest(expected) != local.digest(controller.plan):
        raise local.RehearsalHeld('Independent rendered plan held')
    await initial_profiles(controller)
    conn = await asyncpg.connect(controller.url, timeout=10)
    try:
        await controller.identity(conn, controller.database)
        if local.digest(await local.snapshot(conn)) != local.digest(controller.baseline):
            raise local.RehearsalHeld('Baseline changed during original profile verification')
    finally: await conn.close()
    value = {'format': FORMAT, 'database': controller.database,
             'owner': urlsplit(controller.url).username,
             'baseline': copy.deepcopy(controller.baseline), 'plan': expected,
             'journalInitialSha256': controller.journal.rows()[0]['sha256'],
             'sourceHashes': source_hashes(), 'originalActualProfilesVerified': True}
    raw = (json.dumps(value, sort_keys=True, default=str) + '\n').encode()
    if len(raw) > MAX_BYTES: raise local.RehearsalHeld('Local archive size held')
    with Path(path).open('xb') as stream:
        stream.write(raw); stream.flush(); local.os.fsync(stream.fileno())
    if Path(path).read_bytes() != raw: raise local.RehearsalHeld('Archive readback held')
    return sha(raw)


def load_archive(path, expected_sha256, url):
    """Offline validation before networking; no live state supplies a baseline."""
    database = local.local_target(url)
    if not isinstance(expected_sha256, str) or not re.fullmatch('[a-f0-9]{64}', expected_sha256):
        raise local.RehearsalHeld('Independent archive hash required')
    try:
        path = Path(path)
        if not 0 < path.stat().st_size <= MAX_BYTES: raise ValueError()
        raw = path.read_bytes()
        if sha(raw) != expected_sha256: raise ValueError()
        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value: raise ValueError()
                value[key] = item
            return value
        value = json.loads(raw, object_pairs_hook=unique)
        if (set(value) != {'format', 'database', 'owner', 'baseline', 'plan',
                          'journalInitialSha256', 'sourceHashes', 'originalActualProfilesVerified'}
                or value['format'] != FORMAT or value['database'] != database
                or value['owner'] != urlsplit(url).username
                or value['originalActualProfilesVerified'] is not True
                or value['sourceHashes'] != source_hashes()
                or not re.fullmatch('[a-f0-9]{64}', value['journalInitialSha256'])):
            raise ValueError()
        plan = baseline_plan(value['baseline'], value['plan']['originalRoles'],
                             value['plan']['proposedReplacementRoles'])
        if local.digest(plan) != local.digest(value['plan']):
            raise local.RehearsalHeld('Independent rendered archive plan differs')
        return value
    except (ValueError, KeyError, TypeError, OSError, AttributeError):
        raise local.RehearsalHeld('Independent archive contract held') from None


class ExistingJournal(local.Journal):
    """Open without truncating, creating or repairing the existing journal."""
    def __init__(self, path, expected_head_sha256):
        self.path = Path(path)
        if not 0 < self.path.stat().st_size <= MAX_BYTES:
            raise local.RehearsalHeld('Existing journal size held')
        if (not isinstance(expected_head_sha256, str) or not re.fullmatch('[a-f0-9]{64}', expected_head_sha256)
                or self.rows()[-1]['sha256'] != expected_head_sha256):
            raise local.RehearsalHeld('Independent latest journal checkpoint differs')
        self.expected_head = expected_head_sha256

    def append(self, event, data):
        before = self.rows()
        if before[-1]['sha256'] != self.expected_head:
            raise local.RehearsalHeld('Journal changed outside the owning controller')
        expected = local.digest({'sequence': len(before), 'previous': self.expected_head,
                                 'event': event, 'data': data})
        super().append(event, data)
        if self.rows()[-1]['sha256'] != expected:
            raise local.RehearsalHeld('Journal append readback differs from actor checkpoint')
        self.expected_head = expected


def replay(rows, archived):
    """Require legal stage/event order in addition to the inherited hash chain."""
    if (not rows or rows[0]['event'] != 'opened'
            or rows[0]['data'] != {'database': archived['database']}
            or rows[0]['sha256'] != archived['journalInitialSha256']):
        raise local.RehearsalHeld('Journal origin differs from independent archive')
    completed = []; oids = {}; current = local.digest(archived['baseline']); pending = None
    new_names = set(archived['plan']['proposedReplacementRoles'].values())
    old_oids = {row['oid'] for row in archived['baseline']['roles']}
    try:
        for row in rows[1:]:
            event, data = row['event'], row['data']
            if event == 'intent':
                if (pending or len(completed) == len(STEPS) or set(data) != {'step', 'before'}
                        or data['step'] != STEPS[len(completed)] or data['before'] != current):
                    raise ValueError()
                pending = {'step': data['step'], 'before': current, 'expected': None, 'terminal': None}
                continue
            if not pending or data.get('step') != pending['step']: raise ValueError()
            if event == 'expected':
                if (pending['expected'] or pending['terminal'] or set(data) != {'step', 'before', 'after', 'oids'}
                        or data['before'] != pending['before'] or not re.fullmatch('[a-f0-9]{64}', data['after'])
                        or data['after'] == data['before'] or set(data['oids']) != new_names
                        or len(set(data['oids'].values())) != 2
                        or any(type(oid) is not int or not 0 < oid < 2**32 or oid in old_oids for oid in data['oids'].values())
                        or (pending['step'] != 'create' and data['oids'] != oids)):
                    raise ValueError()
                pending['expected'] = data
                continue
            if event == 'commit_unknown':
                if set(data) != {'step'} or not pending['expected'] or pending['terminal']: raise ValueError()
                pending['terminal'] = 'unknown'; continue
            if event == 'failed':
                if set(data) != {'step', 'state'} or data['state'] != 'rolled_back' or pending['terminal']: raise ValueError()
                pending['terminal'] = 'failed'; continue
            if event not in ('acknowledged', 'reconciled') or set(data) != {'step', 'state'}: raise ValueError()
            state = data['state']
            if event == 'acknowledged' and (state != 'committed' or pending['terminal']): raise ValueError()
            if state == 'ambiguous' and event == 'reconciled': continue
            if state == 'committed':
                if not pending['expected'] or pending['terminal'] == 'failed': raise ValueError()
                current = pending['expected']['after']; oids = dict(pending['expected']['oids'])
                completed.append(pending['step'])
            elif state != 'not_committed' or event != 'reconciled':
                raise ValueError()
            pending = None
        return {'completed': completed, 'oids': oids, 'current': current, 'pending': pending}
    except (ValueError, KeyError, TypeError, AttributeError):
        raise local.RehearsalHeld('Journal stage semantics held') from None


async def recover(url, archive_path, expected_archive_sha256, journal_path, expected_journal_head_sha256):
    """Reconstruct from pinned archive + legal journal, then freshly reconcile.

    No pool proof survives a process restart. The caller must explicitly verify
    the actual overlap/default original pools again before restore/NOLOGIN.
    """
    archived = load_archive(archive_path, expected_archive_sha256, url)
    journal = ExistingJournal(journal_path, expected_journal_head_sha256)
    state = replay(journal.rows(), archived)
    controller = local.LocalInstaller(url, journal, archived['baseline'], archived['plan'])
    controller.completed = list(state['completed']); controller.oids = dict(state['oids']); controller.held = True
    conn = await asyncpg.connect(url, timeout=10)
    try:
        await controller.identity(conn, archived['database'])
        fresh = await local.snapshot(conn); observed = local.digest(fresh)
    finally: await conn.close()
    pending = state['pending']; outcome = 'no_pending_verified'
    if pending:
        expected = pending['expected']
        outcome = ('committed' if expected and pending['terminal'] != 'failed' and observed == expected['after'] else
                   'not_committed' if observed == pending['before'] else 'ambiguous')
        if outcome == 'committed':
            controller.oids = dict(expected['oids']); controller.completed.append(pending['step'])
        if outcome != 'ambiguous': controller.preserve(fresh)
        journal.append('reconciled', {'step': pending['step'], 'state': outcome})
    elif observed != state['current']:
        groups = [name for name in fresh if local.digest(fresh[name]) != local.digest(archived['baseline'][name])]
        raise local.RehearsalHeld('Resolved journal differs from fresh catalog; groups=' + ','.join(groups))
    if outcome != 'ambiguous':
        controller.preserve(fresh); controller.current = fresh; controller.held = False
    receipt = {'format': 'jaymax-local-process-recovery-v1', 'state': outcome,
               'independentArchiveSha256': expected_archive_sha256,
               'baselineSha256': local.digest(archived['baseline']),
               'journalHeadSha256': journal.expected_head,
               'completed': list(controller.completed), 'replacementOids': dict(controller.oids),
               'held': controller.held, 'poolProofsReused': False,
               'databaseMutationsDuringRecovery': False, 'hostedChanges': False,
               'applicationConfigurationChanged': False, 'operationalReleaseApproved': False}
    return controller, receipt
