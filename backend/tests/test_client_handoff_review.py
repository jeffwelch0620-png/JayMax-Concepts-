"""Missing/stale/mixed clients and unmeasured capacity cannot pass handoff review."""
import copy
from datetime import datetime, timedelta, timezone
import unittest
from uuid import uuid4
import client_handoff_review as handoff


def fixture():
    credentials = {'storeKind': 'windows_private_local', 'originalBundleRef': str(uuid4()), 'candidateBundleRef': str(uuid4())}
    clients = [{'clientId': 'local_backend', 'instanceId': str(uuid4()), 'sourceRevision': 'a'*40,
        'originalRevision': str(uuid4()), 'candidateRevision': str(uuid4()),
        'maxPoolSize': {'inventory': 2, 'accounts': 2},
        'credentialRefs': {'original': credentials['originalBundleRef'], 'candidate': credentials['candidateBundleRef']}}]
    pin = handoff.digest({'clients': clients, 'credentialContract': credentials})
    plan = handoff.plan(clients, credentials, independent_pin=pin)
    now = datetime.now(timezone.utc)
    client = clients[0]
    observations = [{'clientId': client['clientId'], 'instanceId': client['instanceId'],
        'sourceRevision': client['sourceRevision'], 'revisionId': client['candidateRevision'],
        'observedAt': now.isoformat(), 'inventoryOldPoolsClosed': True, 'accountsOldPoolsClosed': True}]
    capacity = {'observedAt': now.isoformat(), 'clientInstances': 1, 'databaseSlotsAvailable': 7,
                'poolerSlotsAvailable': 7, 'sessionPoolSize': 6}
    return clients, credentials, pin, plan, observations, capacity, now


class HandoffReviewTests(unittest.TestCase):
    def test_valid_declarations_remain_review_only_and_inputs_are_copied(self):
        clients, credentials, pin, plan, observations, capacity, now = fixture()
        report = handoff.assess_declarations(plan, observations, capacity, now=now)
        self.assertEqual(report['status'], 'reviewed_declarations_only')
        for key in ('liveClientRegistryVerified', 'credentialStoreVerified', 'promotionAuthorized',
                    'applicationConfigurationChanged', 'hostedChanges', 'operationalReleaseApproved'):
            self.assertFalse(report[key])
        self.assertFalse(plan['credentialStoreImplemented']); self.assertEqual(plan['additionalOverlapSlots'], 7)
        clients[0]['clientId'] = 'modified_after_review'
        credentials['candidateBundleRef'] = str(uuid4())
        self.assertEqual(plan['clients'][0]['clientId'], 'local_backend')
        self.assertEqual(plan['registrySha256'], pin)

    def test_registry_rejects_unknown_fields_duplicates_secret_values_and_bad_pairs(self):
        for change in ('missing_pin', 'changed_source', 'duplicate_instance', 'shared_revisions',
                       'shared_credentials', 'mixed_bundle', 'wrong_pool', 'boolean_pool', 'secret_field'):
            with self.subTest(change=change):
                clients, credentials, pin, *_ = fixture()
                if change == 'missing_pin': pin = ''
                if change == 'changed_source': clients[0]['sourceRevision'] = 'b'*40
                if change == 'duplicate_instance': clients.append(copy.deepcopy(clients[0]))
                if change == 'shared_revisions': clients[0]['candidateRevision'] = clients[0]['originalRevision']
                if change == 'shared_credentials': credentials['candidateBundleRef'] = credentials['originalBundleRef']
                if change == 'mixed_bundle': clients[0]['credentialRefs']['candidate'] = str(uuid4())
                if change == 'wrong_pool': clients[0]['maxPoolSize']['inventory'] = 3
                if change == 'boolean_pool': clients[0]['maxPoolSize']['accounts'] = True
                if change == 'secret_field': credentials['DATABASE_URL'] = 'postgresql://invented:secret@invalid'
                # Structural checks must hold even with a correctly pinned bad declaration.
                if change not in ('missing_pin', 'changed_source'):
                    pin = handoff.digest({'clients': clients, 'credentialContract': credentials})
                with self.assertRaises(handoff.HandoffHeld): handoff.plan(clients, credentials, independent_pin=pin)

    def test_missing_unknown_stale_future_mixed_or_incomplete_client_acknowledgements_hold(self):
        for change in ('missing', 'duplicate', 'unknown', 'source', 'revision', 'stale', 'future',
                       'naive', 'inventory_open', 'accounts_open', 'extra_field', 'plan_changed'):
            with self.subTest(change=change):
                _, _, _, plan, observations, capacity, now = fixture()
                if change == 'missing': observations = []
                if change == 'duplicate': observations *= 2
                if change == 'unknown': observations[0]['instanceId'] = str(uuid4())
                if change == 'source': observations[0]['sourceRevision'] = 'b'*40
                if change == 'revision': observations[0]['revisionId'] = plan['clients'][0]['originalRevision']
                if change == 'stale': observations[0]['observedAt'] = (now-timedelta(seconds=901)).isoformat()
                if change == 'future': observations[0]['observedAt'] = (now+timedelta(seconds=1)).isoformat()
                if change == 'naive': observations[0]['observedAt'] = now.replace(tzinfo=None).isoformat()
                if change == 'inventory_open': observations[0]['inventoryOldPoolsClosed'] = False
                if change == 'accounts_open': observations[0]['accountsOldPoolsClosed'] = False
                if change == 'extra_field': observations[0]['password'] = 'invented-secret'
                if change == 'plan_changed': plan['automaticPromotion'] = True
                with self.assertRaises(handoff.HandoffHeld): handoff.assess_declarations(plan, observations, capacity, now=now)

    def test_capacity_must_cover_exact_instance_count_and_pooler_database_budgets(self):
        for change in ('none', 'count', 'database', 'pooler', 'pool_size', 'stale'):
            with self.subTest(change=change):
                _, _, _, plan, observations, capacity, now = fixture()
                if change == 'none': capacity = None
                if change == 'count': capacity['clientInstances'] = 2
                if change == 'database': capacity['databaseSlotsAvailable'] = 6
                if change == 'pooler': capacity['poolerSlotsAvailable'] = 6
                if change == 'pool_size': capacity['sessionPoolSize'] = 2
                if change == 'stale': capacity['observedAt'] = (now-timedelta(seconds=901)).isoformat()
                with self.assertRaises(handoff.HandoffHeld): handoff.assess_declarations(plan, observations, capacity, now=now)
