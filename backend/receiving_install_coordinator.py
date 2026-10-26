"""Loopback-only receiving transition. No hosted CLI, configuration or activation.

Backup/restore are separate explicit operations. This consumer authenticates their
evidence, binds a local install plan, and keeps activation held on every outcome.
It never provisions roles, moves keys, drops databases/schemas or retries SQL.
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import hosted_backup as legacy
import hosted_journal_backup as journal
import manager_handoff_install as install
import manager_handoff_recovery as recovery
import receiving_install_evidence as evidence
from application_backup_profiles import Held, LEGACY6, RECEIVING7, canonical, digest, sha256
from readonly_snapshot import readonly_snapshot, error_details, preserve_cleanup_failure

FORMAT = 'jaymax-local-receiving-transition-v1'
INSTALL_RECEIPT = 'jaymax-local-receiving-install-receipt-v1'
RECOVERY_RECEIPT = 'jaymax-local-receiving-recovery-receipt-v1'


def local_target(url, identity):
    evidence.local_identity(identity)
    settings = recovery.target(url)  # Literal loopback; no control DB, options or hostname fallback.
    if {k: settings[k] for k in ('host', 'port', 'user', 'database')} != {
            k: identity[k] for k in ('host', 'port', 'user', 'database')}:
        raise Held('local_source_target_differs')
    return settings


async def source_matches(url, expected, manifest, facts, *, core=None, post=False):
    local_target(url, expected['source'])
    conn = await recovery.connect(url)  # Retains PR73 managed-marker refusal.
    async with preserve_cleanup_failure(lambda: journal.close_owned(conn), 'connectionCloseErrorType'):
        async with readonly_snapshot(conn):
            # The frozen local installer hashes jsonb under its fresh connection's
            # own session settings. Compare that oracle before the backup reader
            # normalizes timezone/deparser settings; never compare unlike hashes.
            if core is not None and not post:
                if await install.baseline(conn, core['runtimeRole'], core['accountsRole']) != core['baseline']:
                    raise Held('prepared_local_baseline_changed')
            await conn.execute(journal.NORMALIZE)
            identity = expected['source']
            if (await conn.fetchval('SELECT system_identifier::text FROM pg_control_system()') != identity['systemIdentifier']
                    or await conn.fetchval('SELECT oid::bigint FROM pg_database WHERE datname=current_database()') != identity['databaseOid']
                    or await conn.fetchval('SELECT current_user') != identity['user']
                    or await conn.fetchval('SELECT session_user') != identity['user']
                    or await conn.fetchval('SHOW server_version_num') != manifest['serverVersionNum']):
                raise Held('local_cluster_or_version_changed')
            await journal.check_scope(conn, RECEIVING7 if post else LEGACY6)
            actual = await journal.fingerprint(conn, RECEIVING7) if post else await legacy.fingerprint(conn)
            if actual != facts:
                raise Held('live_local_facts_differ_from_verified_archive')
            deps = await journal.dependencies(conn, RECEIVING7) if post else await legacy.dependencies(conn)
            if deps != manifest['dependencies']:
                raise Held('live_local_dependencies_changed')
            authority = await journal.authority(conn, RECEIVING7 if post else LEGACY6)
            if post:
                if authority != manifest['authority']:
                    raise Held('live_local_authority_changed')
            elif any(authority[k] != manifest[k] for k in
                     ('rolesWithoutPasswords', 'roleMemberships', 'databaseOwner', 'schemaOwners')):
                raise Held('live_local_authority_changed')


def checked(plan, expected_sha, url, *, active):
    if digest(canonical(plan)) != sha256(expected_sha):
        raise Held('independent_transition_plan_digest_differs')
    evidence.exact(plan, ('format', 'localOnly', 'sourceHashes', 'source', 'core', 'preExpected',
        'preExpectedSha256', 'preManifest', 'preWorkingKeyPathSha256', 'consumers', 'window',
        'restorationReserveSeconds'), 'transition_plan_shape_differs')
    if (plan['format'] != FORMAT or plan['localOnly'] is not True
            or plan['sourceHashes'] != evidence.source_hashes()
            or plan['source'] != plan['preExpected']['source']
            or plan['window'] != plan['preExpected']['captureWindow']):
        raise Held('transition_source_or_scope_changed')
    local_target(url, plan['source'])
    evidence.consumers(plan['consumers'])
    evidence.expected(plan['preExpected'], plan['preExpectedSha256'], 'pre_install', active=active)
    if digest(canonical(plan['preManifest'])) != plan['preExpected']['artifacts']['manifestSha256']:
        raise Held('prepared_manifest_binding_differs')
    sha256(plan['preWorkingKeyPathSha256'])
    evidence.window_budget(plan['window'], plan['restorationReserveSeconds'], active=active)
    install.checked(plan['core'], install.sha(plan['core']), url)
    return plan


async def prepare(url, runtime, accounts, versions, archive, key, restored, *,
                  expected, expected_sha, consumers, reserve_seconds=600):
    # Authenticate and check every local-only input before the first connection.
    manifest, facts = evidence.authenticate(archive, key, restored, expected, expected_sha, 'pre_install')
    local_target(url, expected['source']); evidence.consumers(consumers)
    budget = evidence.window_budget(expected['captureWindow'], reserve_seconds)
    async with asyncio.timeout(budget):
        await source_matches(url, expected, manifest, facts)
        core = await install.prepare(url, runtime, accounts, versions)
        # Match the core plan and the independent archive in the same snapshot.
        await source_matches(url, expected, manifest, facts, core=core)
    plan = dict(format=FORMAT, localOnly=True, sourceHashes=evidence.source_hashes(),
        source=expected['source'], core=core, preExpected=expected, preExpectedSha256=expected_sha,
        preManifest=manifest, preWorkingKeyPathSha256=digest(str(Path(key).resolve()).encode()),
        consumers=consumers, window=expected['captureWindow'], restorationReserveSeconds=reserve_seconds)
    # Detach caller-owned nested dictionaries; approval binds this exact value.
    import json
    plan = json.loads(canonical(plan))
    checked(plan, digest(canonical(plan)), url, active=True)
    return plan


def held_result(error, status):
    # Do not expose exception text, SQL, paths, role names or driver details.
    return dict(status=status, **error_details(error), retryAuthorized=False,
                featureActivated=False, hostedExecutionApproved=False,
                credentialRecoveryVerified=False, operationalReleaseApproved=False)


async def apply(url, plan, expected_plan_sha, archive, key, restored, *, custody_closeout):
    checked(plan, expected_plan_sha, url, active=True)
    expected = plan['preExpected']
    evidence.key_closeout(key, plan['preWorkingKeyPathSha256'], custody_closeout)
    manifest, facts = evidence.prepared_archive(archive, restored, expected,
                                               plan['preExpectedSha256'], plan['preManifest'])
    budget = evidence.window_budget(plan['window'], plan['restorationReserveSeconds'])
    core_invoked = False
    try:
        async with asyncio.timeout(budget):
            await source_matches(url, expected, manifest, facts, core=plan['core'])
            checked(plan, expected_plan_sha, url, active=True)
            core_invoked = True
            await install.apply(url, plan['core'], install.sha(plan['core']))
    except install.Unknown as error:
        return held_result(error, 'commit_unknown_activation_held')
    except TimeoutError as error:
        # asyncio.timeout can replace a cancellation carrying acknowledged-commit
        # cleanup metadata. Once the engine starts, never infer non-installation.
        return held_result(error, 'commit_unknown_activation_held' if core_invoked
                           else 'installation_failed_activation_held')
    except Exception as error:
        # A cleanup failure after acknowledgement cannot be called a rollback.
        return held_result(error, 'installed_reconciliation_required_activation_held'
                           if getattr(error, 'commitAcknowledged', False)
                           else 'installation_failed_activation_held')
    return dict(format=INSTALL_RECEIPT, status='installed_activation_held',
        planSha256=expected_plan_sha, preExpectedSha256=plan['preExpectedSha256'],
        sourceHashes=plan['sourceHashes'], source=plan['source'], ledgerEntries=3,
        featureActivated=False, hostedExecutionApproved=False, retryAuthorized=False,
        operationalReleaseApproved=False)


async def reconcile(url, plan, expected_plan_sha):
    checked(plan, expected_plan_sha, url, active=False)
    # Reconciliation is read-only and never renews a plan or grants retry authority.
    async with asyncio.timeout(60):
        result = await install.reconcile(url, plan['core'], install.sha(plan['core']))
    return dict(outcome=result['outcome'], retryAuthorized=False, featureActivated=False,
                hostedExecutionApproved=False)


async def finish(url, plan, expected_plan_sha, installed, expected_install_sha,
                 archive, key, restored, *, expected, expected_sha):
    # All post-install failures leave the committed source and feature flags alone.
    try:
        checked(plan, expected_plan_sha, url, active=False)
        if digest(canonical(installed)) != sha256(expected_install_sha):
            raise Held('independent_install_receipt_digest_differs')
        required = dict(format=INSTALL_RECEIPT, status='installed_activation_held',
            planSha256=expected_plan_sha, preExpectedSha256=plan['preExpectedSha256'],
            sourceHashes=plan['sourceHashes'], source=plan['source'], ledgerEntries=3,
            featureActivated=False, hostedExecutionApproved=False, retryAuthorized=False,
            operationalReleaseApproved=False)
        if canonical(installed) != canonical(required):
            raise Held('installation_receipt_binding_differs')
        manifest, facts = evidence.authenticate(archive, key, restored, expected, expected_sha, 'post_install')
        if (expected['source'] != plan['source'] or expected['projectRef'] != plan['preExpected']['projectRef']
                or expected['sourceHashes'] != plan['sourceHashes']):
            raise Held('post_install_transition_source_differs')
        budget = evidence.window_budget(expected['captureWindow'], plan['restorationReserveSeconds'])
        async with asyncio.timeout(budget):
            result = await install.reconcile(url, plan['core'], install.sha(plan['core']))
            if result['outcome'] != 'installed':
                raise Held('installed_state_not_confirmed')
            await source_matches(url, expected, manifest, facts, core=plan['core'], post=True)
        # Validate freshness/source one last time; do not reuse the pre-install window.
        evidence.expected(expected, expected_sha, 'post_install')
        evidence.window_budget(expected['captureWindow'], plan['restorationReserveSeconds'])
        return dict(format=RECOVERY_RECEIPT, status='verified_local_recovery_custody_closeout_pending', planSha256=expected_plan_sha,
            preExpectedSha256=plan['preExpectedSha256'], postExpectedSha256=expected_sha,
            sourceHashes=plan['sourceHashes'], postWorkingKeyPathSha256=digest(str(Path(key).resolve()).encode()),
            localOnly=True, preProfile='legacy6', postProfile='receiving7',
            custodyAttestationsSupplied=True, workingKeyDeletionStillRequired=True,
            featureActivated=False, hostedExecutionApproved=False, retryAuthorized=False,
            credentialRecoveryVerified=False, operationalReleaseApproved=False)
    except Exception as error:
        return held_result(error, 'installed_recovery_held')


def closeout(verified, expected_verified_sha, key, custody):
    """No IO mutations. Caller removes its working key and supplies private attestations."""
    if digest(canonical(verified)) != sha256(expected_verified_sha):
        raise Held('independent_recovery_receipt_digest_differs')
    evidence.exact(verified, ('format','status','planSha256','preExpectedSha256','postExpectedSha256',
        'sourceHashes','postWorkingKeyPathSha256','localOnly','preProfile','postProfile',
        'custodyAttestationsSupplied','workingKeyDeletionStillRequired','featureActivated',
        'hostedExecutionApproved','retryAuthorized','credentialRecoveryVerified','operationalReleaseApproved'),
        'recovery_closeout_shape_differs')
    if (verified['format'] != RECOVERY_RECEIPT or verified['status'] != 'verified_local_recovery_custody_closeout_pending'
            or verified['sourceHashes'] != evidence.source_hashes()
            or verified['preProfile'] != 'legacy6' or verified['postProfile'] != 'receiving7'
            or any(verified[k] is not True for k in ('localOnly','custodyAttestationsSupplied','workingKeyDeletionStillRequired'))
            or any(verified[k] is not False for k in ('featureActivated','hostedExecutionApproved',
                'retryAuthorized','credentialRecoveryVerified','operationalReleaseApproved'))):
        raise Held('recovery_closeout_binding_differs')
    for k in ('planSha256','preExpectedSha256','postExpectedSha256'):
        sha256(verified[k])
    evidence.key_closeout(key, verified['postWorkingKeyPathSha256'], custody)
    return dict(verified, status='passed_local_transition_activation_held',
                workingKeyDeletionStillRequired=False, localKeyCopyDeleted=True, forensicErasureVerified=False)
