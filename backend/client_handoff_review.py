"""Exact metadata-only registry/credential contract and handoff review.

Declarations are not independently verified live client or credential evidence.
No connection, secret reader/writer, configuration switch or release gate.
"""
import copy
from datetime import datetime, timezone
import hashlib
import json
import re
from uuid import UUID
import parallel_install_plan as installation


class HandoffHeld(RuntimeError):
    """Safe category without supplied metadata values."""


PROFILES = ('inventory', 'accounts')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value: raise ValueError()


def registry(clients, credential_contract, independent_pin):
    """Validate an independently approved registry hash; no environment discovery."""
    try:
        if (not isinstance(independent_pin, str) or not re.fullmatch('[a-f0-9]{64}', independent_pin)
                or independent_pin != digest({'clients': clients, 'credentialContract': credential_contract})
                or set(credential_contract) != {'storeKind', 'originalBundleRef', 'candidateBundleRef'}
                or credential_contract['storeKind'] != 'windows_private_local'):
            raise ValueError()
        for field in ('originalBundleRef', 'candidateBundleRef'): uuid(credential_contract[field])
        if credential_contract['originalBundleRef'] == credential_contract['candidateBundleRef']: raise ValueError()
        if not isinstance(clients, list) or not 1 <= len(clients) <= 64: raise ValueError()
        identities = set(); instance_ids = set(); revisions = set()
        for client in clients:
            if (set(client) != {'clientId', 'instanceId', 'sourceRevision', 'originalRevision', 'candidateRevision',
                               'maxPoolSize', 'credentialRefs'}
                    or not isinstance(client['clientId'], str)
                    or not re.fullmatch('[a-z][a-z0-9_-]{1,63}', client['clientId'])
                    or not isinstance(client['sourceRevision'], str)
                    or not re.fullmatch('[a-f0-9]{40}', client['sourceRevision'])
                    or set(client['maxPoolSize']) != set(PROFILES)
                    or any(type(client['maxPoolSize'][kind]) is not int or client['maxPoolSize'][kind] != 2 for kind in PROFILES)
                    or client['credentialRefs'] != {'original': credential_contract['originalBundleRef'],
                                                     'candidate': credential_contract['candidateBundleRef']}):
                raise ValueError()
            for field in ('instanceId', 'originalRevision', 'candidateRevision'): uuid(client[field])
            key = (client['clientId'], client['instanceId'])
            if key in identities or client['instanceId'] in instance_ids: raise ValueError()
            identities.add(key); instance_ids.add(client['instanceId'])
            pair = {client['originalRevision'], client['candidateRevision']}
            if len(pair) != 2 or pair & revisions: raise ValueError()
            revisions |= pair
        return {'clients': copy.deepcopy(clients), 'credentialContract': copy.deepcopy(credential_contract),
                'registrySha256': independent_pin}
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HandoffHeld('Exact independently pinned client registry held') from None


def plan(clients, credential_contract, *, independent_pin):
    reviewed = registry(clients, credential_contract, independent_pin)
    return {'format': 'jaymax-client-handoff-review-v1', 'status': 'review_only', **reviewed,
        'clientInstances': len(clients), 'additionalOverlapSlots': len(clients) * 4 + 3,
        'credentialRequirements': ['fresh_directory_outside_repo_and_sync_roots',
            'owner_only_private_acl_readback', 'encrypted_credentials_with_independent_recovery_key',
            'original_and_candidate_bundles_separate_immutable_references',
            'durable_candidate_credentials_before_LOGIN', 'actual_password_and_TLS_verification',
            'secret_redaction_and_exact_original_bundle_recovery'],
        'handoffOrder': ['pin_exact_clients_sources_revisions_and_registry',
            'measure_database_and_pooler_capacity_for_all_registered_instances',
            'verify_durable_credentials_and_independent_checkpoint_store',
            'run_journaled_parallel_installer_with_original_preservation_pins',
            'prepare_both_candidate_pools_for_each_bound_client_revision',
            'explicitly_review_promotion_and_all_client_acknowledgements',
            'close_only_owned_old_pools_and_review_exact_live_session_registry',
            'prove_return_to_original_pair_and_singleton_policies',
            'complete_combined_backup_and_credential_recovery_trial',
            'separately_review_retirement_merge_and_release'],
        'credentialStoreImplemented': False, 'liveClientRegistryVerified': False,
        'unknownClients': 'hold_without_termination_or_policy_changes',
        'automaticPromotion': False, 'automaticRetirement': False,
        'applicationConfigurationChanged': False, 'hostedChanges': False,
        'operationalReleaseApproved': False}


def assess_declarations(review, observations, capacity, *, now=None):
    """Check exact recent acknowledgements; self-reported, never promotion proof."""
    try:
        expected_plan = plan(review['clients'], review['credentialContract'], independent_pin=review['registrySha256'])
        if digest(review) != digest(expected_plan): raise ValueError()
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None or not isinstance(observations, list): raise ValueError()
        expected = {(client['clientId'], client['instanceId']): client for client in review['clients']}
        seen = set()
        for item in observations:
            if set(item) != {'clientId', 'instanceId', 'sourceRevision', 'revisionId', 'observedAt',
                             'inventoryOldPoolsClosed', 'accountsOldPoolsClosed'}:
                raise ValueError()
            key = (item['clientId'], item['instanceId']); client = expected.get(key)
            if (client is None or key in seen or item['sourceRevision'] != client['sourceRevision']
                    or item['revisionId'] != client['candidateRevision']
                    or item['inventoryOldPoolsClosed'] is not True or item['accountsOldPoolsClosed'] is not True):
                raise ValueError()
            seen_at = datetime.fromisoformat(item['observedAt'])
            if seen_at.tzinfo is None or not 0 <= (now - seen_at).total_seconds() <= 900: raise ValueError()
            seen.add(key)
        if seen != set(expected) or capacity['clientInstances'] != len(expected): raise ValueError()
        budget = installation.capacity_check(capacity, now)
        if budget['status'] != 'reviewed_capacity_observation': raise ValueError()
        return {'format': 'jaymax-client-handoff-declarations-v1', 'status': 'reviewed_declarations_only',
            'registrySha256': review['registrySha256'], 'clientInstances': len(expected), 'capacity': budget,
            'liveClientRegistryVerified': False, 'credentialStoreVerified': False,
            'promotionAuthorized': False, 'applicationConfigurationChanged': False,
            'hostedChanges': False, 'operationalReleaseApproved': False}
    except (ValueError, KeyError, TypeError, AttributeError, installation.InstallPlanError):
        raise HandoffHeld('Client declaration or capacity review held') from None
