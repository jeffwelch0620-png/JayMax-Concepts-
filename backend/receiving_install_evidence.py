"""Explicit phase evidence for fictional receiving installation, not a live permit.

The legacy reader and v2 validator remain unchanged. Caller-held expected digests
are mandatory; archive metadata and a success string cannot approve themselves.
No configuration, database connection, key movement or cleanup runs on import.
"""
from datetime import datetime, timezone
from pathlib import Path
import base64
import re
import os

from cryptography.fernet import Fernet
import hosted_backup as legacy
import hosted_journal_backup as journal
import journal_backup_receipts as receipts
import manager_handoff_recovery as recovery
from application_backup_profiles import (Held, LEGACY6, RECEIVING7, canonical,
                                         digest, sha256, strict_json, MAX_ENVELOPE)

ROOT = Path(__file__).resolve().parents[1]
FORMAT = 'jaymax-local-receiving-proof-expectation-v1'
SOURCE_FILES = tuple(dict.fromkeys((*receipts.SOURCE_FILES,
    'backend/receiving_install_evidence.py', 'backend/receiving_install_coordinator.py',
    'backend/manager_handoff_install.py', 'backend/manager_handoff_recovery.py',
    'backend/manager_handoff.py', 'backend/manager_actor.py', 'backend/runtime_permissions.py',
    'backend/hosted_test_trial.py', 'backend/hosted_native_install.py',
    'backend/hosted_install_preservation.py', 'backend/schema_reconciliation.py',
    'migrations/20261025_manager_handoff_notes.sql', 'supabase/manager_handoff.schema.sql',
    'supabase/manager_handoff.manifest.json')))
CONSUMERS = frozenset(('legacy_backup', 'journal_backup', 'par', 'source_index',
                       'calibration', 'security_recovery', 'routine'))
ATTESTATIONS = ('cleanup', 'custody')


def source_hashes():
    return {name: digest((ROOT / name).read_bytes()) for name in SOURCE_FILES}


def exact(value, keys, reason):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise Held(reason)
    return value


def local_identity(value):
    exact(value, ('host', 'port', 'user', 'database', 'systemIdentifier', 'databaseOid'),
          'exact_local_identity_required')
    if (value['host'] not in ('127.0.0.1', '::1') or type(value['port']) is not int
            or not 1024 <= value['port'] <= 65535
            or not isinstance(value['user'], str) or not re.fullmatch('[a-z][a-z0-9_]{0,62}', value['user'])
            or not isinstance(value['database'], str)
            or not re.fullmatch('native_purchase_test_[a-f0-9]{32}', value['database'])
            or not isinstance(value['systemIdentifier'], str) or not value['systemIdentifier'].isdigit()
            or type(value['databaseOid']) is not int or value['databaseOid'] <= 0):
        raise Held('fictional_local_identity_required')
    return value


def attestations(value):
    exact(value, ATTESTATIONS, 'operator_attestations_required')
    expected = {'cleanup': ('sourceClosed', 'toolsClosed', 'plaintextRemoved', 'restoreTargetInspected'),
                'custody': ('keyMoved', 'separateKeyAccessVerified', 'workingKeyPrivate', 'retentionConfirmed')}
    for group, keys in expected.items():
        exact(value[group], keys, 'operator_attestation_shape_differs')
        if any(value[group][k] is not True for k in keys):
            raise Held('operator_closeout_prerequisite_held')
    # These are separately supplied operator attestations, not engine assertions.
    # Working-key deletion is a later custody closeout; never delete keys here.
    return value


def consumers(value):
    if not isinstance(value, list) or len(value) != len(CONSUMERS):
        raise Held('complete_consumer_matrix_required')
    seen = set()
    for row in value:
        exact(row, ('name', 'disposition', 'required', 'ownerAccepted'), 'consumer_row_invalid')
        if (not isinstance(row['name'], str) or row['name'] not in CONSUMERS or row['name'] in seen
                or row['disposition'] not in ('supported', 'completed', 'held')
                or type(row['required']) is not bool or row['ownerAccepted'] is not True
                or (row['required'] and row['disposition'] == 'held')):
            raise Held('required_consumer_unresolved')
        seen.add(row['name'])
    return value


def window_budget(window, reserve=600, *, active=True, now=None):
    if type(reserve) is not int or reserve < 600 or reserve >= 2700:
        raise Held('writer_restoration_reserve_required')
    end = receipts.check_window(window, now=now, active=active)
    if active:
        remaining = (end - (now or datetime.now(timezone.utc))).total_seconds() - reserve
        if remaining <= 0:
            raise Held('writer_restoration_reserve_reached')
        return min(600, remaining)
    return end


def expected(value, expected_sha, phase, *, active=True):
    sha256(expected_sha)
    if digest(canonical(value)) != expected_sha:
        raise Held('independent_expected_proof_digest_differs')
    exact(value, ('format', 'phase', 'profile', 'projectRef', 'source', 'sourceHashes',
                  'captureWindow', 'verificationWindow', 'artifacts', 'dependencyPolicy',
                  'attestations', 'journalBinding'), 'exact_expected_proof_required')
    selected = LEGACY6 if phase == 'pre_install' else RECEIVING7
    if (phase not in ('pre_install', 'post_install') or value['format'] != FORMAT
            or value['phase'] != phase or value['profile'] != selected.name
            or not isinstance(value['projectRef'], str)
            or not re.fullmatch('[a-z0-9]{20}', value['projectRef'])):
        raise Held('proof_phase_or_profile_differs')
    local_identity(value['source'])
    if value['sourceHashes'] != source_hashes():
        raise Held('receiving_source_changed')
    receipts.check_window(value['captureWindow'], active=active)
    receipts.check_window(value['verificationWindow'], active=active)
    if not (receipts.instant(value['captureWindow']['startsAt'])
            <= receipts.instant(value['verificationWindow']['startsAt'])
            < receipts.instant(value['verificationWindow']['expiresAt'])
            <= receipts.instant(value['captureWindow']['expiresAt'])):
        raise Held('verification_outside_capture_window')
    exact(value['artifacts'], ('encryptedSha256', 'archiveSha256', 'manifestSha256',
                               'factsSha256', 'restoreReceiptSha256'), 'artifact_inventory_differs')
    for item in value['artifacts'].values():
        sha256(item)
    journal.dependency_policy(value['dependencyPolicy'])
    attestations(value['attestations'])
    if phase == 'pre_install':
        if value['journalBinding'] is not None:
            raise Held('legacy_proof_cannot_claim_journal_binding')
    else:
        b = receipts.expected_binding(value['journalBinding'])
        if (b['window'] != value['captureWindow'] or b['sourceHashes'] != receipts.source_hashes()
                or b['dependencyPolicySha256'] != digest(canonical(value['dependencyPolicy']))):
            raise Held('post_install_binding_differs')
        project = value['projectRef']
        if b['sourceBinding'] != digest(canonical(dict(projectRef=project,
                host='db.' + project + '.supabase.co', port=5432, database='postgres', user='postgres'))):
            raise Held('post_install_project_binding_differs')
    return selected


def bounded_bytes(path, limit):
    # Local rehearsal caller owns private artifact storage; no URL is accepted.
    path = Path(path)
    with path.open('rb') as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise Held('proof_artifact_oversized')
    return value


def key_closeout(path, path_sha, value):
    exact(value, ('keyMoved', 'separateKeyAccessVerified', 'restoreVerified',
                  'localKeyCopyDeleted', 'retentionConfirmed'), 'key_closeout_required')
    if any(v is not True for v in value.values()):
        raise Held('key_closeout_incomplete')
    if (digest(str(Path(path).resolve()).encode()) != sha256(path_sha)
            or os.path.lexists(path)):
        raise Held('working_key_not_removed')
    # Physical absence at this exact working path plus operator attestations;
    # no claim about physical media, snapshots, other copies or forensic erasure.


def prepared_archive(archive, restored, value, expected_sha, manifest):
    """Recheck an approved prepared proof without recreating its deleted key."""
    expected(value, expected_sha, 'pre_install')
    a = value['artifacts']
    facts = {k:manifest[k] for k in ('tables', 'catalog')}
    if (digest(bounded_bytes(archive, MAX_ENVELOPE)) != a['encryptedSha256']
            or digest(canonical(restored)) != a['restoreReceiptSha256']
            or digest(canonical(manifest)) != a['manifestSha256']
            or digest(canonical(facts)) != a['factsSha256']):
        raise Held('prepared_recovery_evidence_changed')
    return manifest, facts


def authenticate(archive, key, restored, value, expected_sha, phase):
    selected = expected(value, expected_sha, phase)
    a = value['artifacts']
    encrypted = bounded_bytes(archive, MAX_ENVELOPE)
    secret = bounded_bytes(key, 128)
    if digest(encrypted) != a['encryptedSha256'] or digest(canonical(restored)) != a['restoreReceiptSha256']:
        raise Held('proof_artifact_or_receipt_changed')
    if phase == 'pre_install':
        try:
            clear = strict_json(Fernet(secret).decrypt(encrypted))
            exact(clear, ('manifest', 'archive'), 'legacy_envelope_shape_differs')
            manifest, raw = legacy.open_backup(archive, key, value['projectRef'])
            if (canonical(clear['manifest']) != canonical(manifest)
                    or base64.b64decode(clear['archive'], validate=True) != raw
                    or digest(bounded_bytes(archive, MAX_ENVELOPE)) != a['encryptedSha256']):
                raise Held('legacy_artifact_changed_during_read')
        except Exception:
            raise Held('legacy_archive_authentication_held') from None
        if (manifest.get('rowFingerprintAlgorithm') != legacy.ROW_ALGORITHM
                or manifest.get('schemas') != list(selected.schemas)
                or manifest.get('sequenceStateIsMvcc') is not False
                or manifest.get('sequencesObservedStable') is not True
                or manifest.get('managedRecoveryVerified') is not False):
            raise Held('legacy_capture_coverage_unverified')
        facts = {k: manifest[k] for k in ('tables', 'catalog')}
        deps = manifest['dependencies']
        exact(deps, ('objects', 'extensions', 'authFunctions'), 'legacy_dependencies_invalid')
        if not isinstance(deps['objects'], list):
            raise Held('legacy_dependencies_invalid')
        journal.check_dependencies({k: deps[k] for k in ('extensions', 'authFunctions')}, value['dependencyPolicy'])
        if (restored.get('status') != 'verified_application_restore'
                or restored.get('archiveSha256') != a['archiveSha256']
                or restored.get('majorVersionMatched') is not True
                or type(restored.get('tablesMatched')) is not int
                or restored['tablesMatched'] != len(facts['tables'])
                or type(restored.get('catalogGroupsMatched')) is not int
                or restored['catalogGroupsMatched'] != len(facts['catalog'])
                or restored.get('managedRecoveryVerified') is not False
                or restored.get('operationalReleaseApproved') is not False
                or 'supabase_migrations.schema_migrations' not in facts['tables']
                or any(k.startswith('operations.') for k in facts['tables'])):
            raise Held('legacy_restore_coverage_unverified')
    else:
        manifest, raw = journal.open_envelope(encrypted, secret, expected=value['journalBinding'],
            expected_encrypted_sha=a['encryptedSha256'], policy=value['dependencyPolicy'])
        facts = manifest['facts']
        receipts.validate(restored, expected=value['journalBinding'],
            encrypted_sha=a['encryptedSha256'], archive_sha=a['archiveSha256'],
            facts_sha=a['factsSha256'], expected_receipt_sha=a['restoreReceiptSha256'],
            verification_window=value['verificationWindow'])
        if (manifest['sourceSystemIdentifier'] != value['source']['systemIdentifier']
                or manifest['sourceDatabaseOid'] != value['source']['databaseOid']):
            raise Held('post_install_source_identity_differs')
    if (digest(canonical(manifest)) != a['manifestSha256']
            or digest(raw) != a['archiveSha256'] or digest(canonical(facts)) != a['factsSha256']
            or not receipts.instant(value['captureWindow']['startsAt'])
            <= receipts.instant(manifest['createdAt']) < receipts.instant(value['captureWindow']['expiresAt'])):
        raise Held('authenticated_manifest_binding_differs')
    migrations = manifest.get('migrationFileHashes')
    required_migrations = {k:v for k,v in value['sourceHashes'].items() if k.startswith('migrations/')}
    if (not isinstance(migrations, dict) or not required_migrations
            or any(migrations.get(k) != v for k,v in required_migrations.items())):
        raise Held('receiving_migration_source_binding_differs')
    return manifest, facts
