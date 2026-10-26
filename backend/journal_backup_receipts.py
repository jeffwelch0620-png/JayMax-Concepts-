"""New v2 evidence contract. Frozen six-schema consumers are never reinterpreted."""
from datetime import datetime, timezone
from pathlib import Path
import hmac
import re

from application_backup_profiles import (Held, RECEIVING7, canonical, digest, sha256,
                                         strict_json)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    'backend/application_backup_profiles.py', 'backend/hosted_journal_backup.py',
    'backend/hosted_journal_backup_cli.py', 'backend/journal_backup_receipts.py',
    'backend/hosted_backup.py', 'backend/hosted_backup_cli.py', 'backend/native_backup.py',
    'backend/readonly_snapshot.py', 'backend/maintenance_connection.py', 'backend/db_tls.py',
    'tools/ops/hosted_additive_index.py','tools/ops/apply_additive_migration.py',
    'backend/managed_development.py','backend/requirements.txt',
)
FORMAT = 'jaymax-journal-recovery-receipt-v2'
PACKET_FORMAT = 'jaymax-journal-recovery-execution-v1'


def source_hashes():
    return {name: digest((ROOT / name).read_bytes()) for name in SOURCE_FILES}


def instant(value):
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None:
            raise ValueError
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError):
        raise Held('invalid_timestamp') from None


def check_window(window, now=None, *, active=True):
    if not isinstance(window, dict) or set(window) != {'startsAt', 'expiresAt'}:
        raise Held('exact_window_required')
    start, end = instant(window['startsAt']), instant(window['expiresAt'])
    if (not 0 < (end - start).total_seconds() <= 2700
            or (active and not start <= (now or datetime.now(timezone.utc)) < end)):
        raise Held('window_expired_or_invalid')
    return end


def expected_binding(value):
    keys = {'profile', 'profileSha256', 'sourceBinding', 'window', 'sourceHashes',
            'dependencyPolicySha256'}
    if not isinstance(value, dict) or set(value) != keys:
        raise Held('exact_expected_binding_required')
    if value['profile'] != RECEIVING7.name or value['profileSha256'] != RECEIVING7.sha256:
        raise Held('profile_binding_differs')
    sha256(value['sourceBinding']); sha256(value['dependencyPolicySha256'])
    if (not isinstance(value['sourceHashes'], dict)
            or set(value['sourceHashes']) != set(SOURCE_FILES)):
        raise Held('source_inventory_differs')
    for v in value['sourceHashes'].values():
        sha256(v)
    check_window(value['window'],active=False)
    return value


def packet(raw, expected_sha, action, now=None):
    """Caller must obtain the expected digest from the separately approved packet."""
    if not isinstance(raw, bytes) or len(raw) > 256 * 1024:
        raise Held('packet_size_invalid')
    if not hmac.compare_digest(digest(raw), sha256(expected_sha)):
        raise Held('packet_digest_differs')
    p = strict_json(raw)
    if not isinstance(p, dict) or set(p) != {'format', 'action', 'projectRef', 'binding', 'dependencyPolicy','executionWindow','restoreTargetSha256'}:
        raise Held('exact_packet_required')
    if (p['format'] != PACKET_FORMAT or p['action'] != action
            or action not in ('export', 'verify-restore')
            or not isinstance(p['projectRef'], str)
            or not re.fullmatch('[a-z0-9]{20}', p['projectRef'])):
        raise Held('packet_scope_differs')
    b = expected_binding(p['binding'])
    designated=digest(canonical(dict(projectRef=p['projectRef'],host='db.'+p['projectRef']+'.supabase.co',
        port=5432,database='postgres',user='postgres')))
    if b['sourceBinding'] != designated:
        raise Held('packet_project_source_binding_differs')
    check_window(p['executionWindow'], now)
    if action == 'export' and b['window'] != p['executionWindow']:
        raise Held('capture_window_differs')
    if action == 'export':
        if p['restoreTargetSha256'] is not None:
            raise Held('export_cannot_bind_restore_target')
    else:
        sha256(p['restoreTargetSha256'])
    if b['sourceHashes'] != source_hashes():
        raise Held('toolchain_source_changed')
    if b['dependencyPolicySha256'] != digest(canonical(p['dependencyPolicy'])):
        raise Held('dependency_policy_differs')
    return p


def receipt(manifest, encrypted_sha, *, restored=False, cleanup=True, patch_matched=False,
            verification_window=None,topology='not_verified'):
    b = manifest['binding']
    covered=set(manifest['facts']['tables'])
    return dict(format=FORMAT, profile=RECEIVING7.name, profileSha256=RECEIVING7.sha256,
                schemas=list(RECEIVING7.schemas), binding=b,
                encryptedSha256=sha256(encrypted_sha), archiveSha256=manifest['archiveSha256'],
                factsSha256=digest(canonical(manifest['facts'])),
                status='verified_application_restore' if restored else 'exported_not_restore_verified',
                tables=len(manifest['facts']['tables']), catalogGroups=len(manifest['facts']['catalog']),
                cleanupVerified=cleanup, majorVersionMatched=restored, patchVersionMatched=patch_matched,
                verificationWindow=verification_window,
                recoveryTopology=topology,
                migrationLedgerCovered='supabase_migrations.schema_migrations' in covered,
                journalTablesCovered={'operations.store_settings','operations.handoff_notes',
                    'operations.handoff_note_revisions','operations.handoff_command_receipts'} <= covered,
                ownershipMode='preserve', managedRecoveryVerified=False,
                credentialRecoveryVerified=False, operationalReleaseApproved=False)


def validate(value, *, expected, encrypted_sha, archive_sha, facts_sha, expected_receipt_sha,
             restore_required=True, verification_window=None):
    """No permissive legacy adapter or truncation to six schemas is provided."""
    expected_binding(expected)
    if not isinstance(value, dict):
        raise Held('receipt_required')
    required={'format','profile','profileSha256','schemas','binding','encryptedSha256','archiveSha256',
        'factsSha256','status','tables','catalogGroups','cleanupVerified','majorVersionMatched',
        'patchVersionMatched','verificationWindow','recoveryTopology','migrationLedgerCovered',
        'journalTablesCovered','ownershipMode','managedRecoveryVerified','credentialRecoveryVerified',
        'operationalReleaseApproved'}
    if set(value) != required:
        raise Held('receipt_shape_differs')
    if digest(canonical(value)) != sha256(expected_receipt_sha):
        raise Held('receipt_digest_differs')
    fields = {'format': FORMAT, 'profile': RECEIVING7.name, 'profileSha256': RECEIVING7.sha256,
              'schemas': list(RECEIVING7.schemas), 'binding': expected,
              'encryptedSha256': sha256(encrypted_sha), 'archiveSha256': sha256(archive_sha),
              'factsSha256': sha256(facts_sha), 'ownershipMode': 'preserve',
              'managedRecoveryVerified': False, 'credentialRecoveryVerified': False,
              'operationalReleaseApproved': False, 'cleanupVerified': True,
              'migrationLedgerCovered': True,'journalTablesCovered': True}
    for key, wanted in fields.items():
        if type(value.get(key)) is not type(wanted) or value[key] != wanted:
            raise Held('receipt_binding_differs')
    if value.get('status') != ('verified_application_restore' if restore_required else 'exported_not_restore_verified'):
        raise Held('receipt_phase_differs')
    if restore_required and value.get('majorVersionMatched') is not True:
        raise Held('major_version_unverified')
    if type(value['patchVersionMatched']) is not bool or (not restore_required and value['majorVersionMatched'] is not False):
        raise Held('version_evidence_invalid')
    if value.get('recoveryTopology') not in (('same_cluster','cross_cluster') if restore_required else ('not_verified',)):
        raise Held('recovery_topology_unverified')
    check_window(expected['window'])  # Installation consumers need a fresh capture.
    if restore_required:
        check_window(verification_window)
        if value.get('verificationWindow') != verification_window:
            raise Held('restore_window_differs')
    for key in ('tables', 'catalogGroups'):
        if type(value.get(key)) is not int or value[key] < 1:
            raise Held('receipt_coverage_missing')
    return value
