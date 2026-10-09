"""Independent witnesses, narrow provider errors and recovery gate regression tests."""
import copy
import unittest
from unittest.mock import AsyncMock, Mock, patch
import pooler_denial_contract as contract

ROLE = 'jaymax_build_accounts_0123456789ab'
OTHER = 'jaymax_build_inventory_abcdefabcdef'
EXPECTED = {ROLE: 101, OTHER: 102}
LABEL = 'jaymax_retirement_probe_' + 'a' * 32


def evidence():
    return {'denialContract': contract.CONTRACT, 'nativeOnlyComparisonHeld': True,
        'kind': 'accounts', 'role': ROLE, 'ownerRoleOidBefore': 101,
        'ownerRoleOidAfter': 101, 'disableAttempted': True, 'ownerConfirmsNoLogin': True,
        'poolerClientObservedClosed': True, 'otherRoleAvailableOnBothPaths': True,
        'ownerConfirmsLoginRestored': True, 'originalCredentialReconnectedOnBothPaths': True,
        'strictOwnedDrainComparisonPassed': False,
        'ownedClient': {'role': ROLE, 'pid': 42, 'backendStart': '2026-10-09T21:30:00+00:00',
            'ownedReadOnlyPoolerClientVerified': True, 'existingApplicationSession': False},
        'signal': {'role': ROLE, 'pid': 42, 'backendStart': '2026-10-09T21:30:00+00:00',
            'ownedReadOnlyProbeTerminated': True, 'backendAbsentConfirmed': True,
            'existingApplicationSessionsTargeted': False},
        'direct': {'accepted': False, 'category': 'login_not_permitted',
            'errorType': 'InvalidAuthorizationSpecificationError', 'sqlstate': '28000'},
        'poolerAttempts': [{'accepted': False, 'category': 'eauthquery_user_not_found',
            'errorType': 'InternalServerError', 'sqlstate': 'XX000'} for _ in range(2)]}


class Qualification(unittest.TestCase):
    def test_lookup_requires_two_attempts_and_keeps_native_result_held(self):
        row = evidence()
        self.assertEqual(contract.denial_mode(row, EXPECTED, ROLE), 'provider_lookup_with_independent_witnesses')
        self.assertIs(row['strictOwnedDrainComparisonPassed'], False)
        row['poolerAttempts'].pop()
        with self.assertRaises(contract.trial.DrainTrialError):
            contract.denial_mode(row, EXPECTED, ROLE)

    def test_missing_or_non_boolean_independent_witnesses_hold(self):
        keys = ('disableAttempted', 'ownerConfirmsNoLogin', 'poolerClientObservedClosed',
            'otherRoleAvailableOnBothPaths', 'ownerConfirmsLoginRestored',
            'originalCredentialReconnectedOnBothPaths')
        for key in keys:
            for value in (None, False, 1, 'true'):
                with self.subTest(key=key, value=value):
                    row = evidence()
                    row[key] = value
                    with self.assertRaises(contract.trial.DrainTrialError):
                        contract.denial_mode(row, EXPECTED, ROLE)

    def test_role_oid_and_owned_signal_identity_must_match(self):
        mutations = [('role', OTHER), ('kind', 'inventory'), ('ownerRoleOidBefore', 103),
            ('ownerRoleOidAfter', 103), ('signal.pid', 43), ('signal.role', OTHER),
            ('signal.backendStart', '2026-10-09T21:30:01+00:00'), ('ownedClient.pid', -1),
            ('ownedClient.backendStart', '2026-10-09T21:30:00'),
            ('ownedClient.ownedReadOnlyPoolerClientVerified', False),
            ('ownedClient.existingApplicationSession', True),
            ('signal.ownedReadOnlyProbeTerminated', False), ('signal.backendAbsentConfirmed', False),
            ('signal.existingApplicationSessionsTargeted', True)]
        for path, value in mutations:
            with self.subTest(path=path):
                row = evidence()
                parts = path.split('.')
                target = row if len(parts) == 1 else row[parts[0]]
                target[parts[-1]] = value
                with self.assertRaises(contract.trial.DrainTrialError):
                    contract.denial_mode(row, EXPECTED, ROLE)

    def test_any_accepted_unknown_or_transport_attempt_holds(self):
        for index in (0, 1):
            for key, value in (('accepted', True), ('accepted', None),
                    ('category', 'unclassified'), ('errorType', 'TimeoutError'),
                    ('sqlstate', '08006'), ('category', 'password_denied')):
                with self.subTest(index=index, key=key, value=value):
                    row = evidence()
                    row['poolerAttempts'][index][key] = value
                    with self.assertRaises(contract.trial.DrainTrialError):
                        contract.denial_mode(row, EXPECTED, ROLE)

    def test_direct_password_denial_is_not_owner_nologin_corroboration(self):
        row = evidence()
        row['direct'] = {'accepted': False, 'category': 'password_denied',
            'errorType': 'InvalidPasswordError', 'sqlstate': '28P01'}
        with self.assertRaises(contract.trial.DrainTrialError):
            contract.denial_mode(row, EXPECTED, ROLE)

    def test_native_denial_remains_a_distinct_mode(self):
        row = evidence()
        row['poolerAttempts'] = [copy.deepcopy(row['direct'])]
        row['strictOwnedDrainComparisonPassed'] = True
        self.assertEqual(contract.denial_mode(row, EXPECTED, ROLE), 'native_authentication_denial')


class Orchestration(unittest.IsolatedAsyncioTestCase):
    def args(self, row):
        owner = Mock(fetchval=AsyncMock(return_value=101))
        return (owner, Mock(), EXPECTED, ROLE, LABEL, 'direct-private', 'pooler-private',
            OTHER, ('other-direct', 'other-pooler'), row, Mock())

    async def test_only_exact_native_hold_can_be_corroborated_after_reconnect(self):
        row = evidence()
        conn = Mock(close=AsyncMock())
        with patch.object(contract.trial, 'compare_role', AsyncMock(side_effect=contract.trial.DrainTrialError(contract.NATIVE_HOLD))), patch.object(contract.trial, 'connect_role', AsyncMock(return_value=conn)) as connect:
            await contract.compare_role(*self.args(row))
        self.assertTrue(row['corroboratedComparisonPassed'])
        self.assertTrue(row['corroboratedLookupDenialQualified'])
        self.assertFalse(row['strictOwnedDrainComparisonPassed'])
        self.assertEqual([call.args[0] for call in connect.await_args_list], ['direct-private', 'pooler-private'])
        self.assertEqual(conn.close.await_count, 2)

    async def test_unrelated_hold_or_runtime_error_never_reaches_qualification(self):
        for error in (contract.trial.DrainTrialError('Fresh disabled pooler client accepted after owned drain'), RuntimeError('private diagnostic')):
            row = evidence()
            with self.subTest(error=type(error).__name__), patch.object(contract.trial, 'compare_role', AsyncMock(side_effect=error)), patch.object(contract.trial, 'connect_role', AsyncMock()) as connect:
                with self.assertRaises(type(error)):
                    await contract.compare_role(*self.args(row))
                connect.assert_not_called()
                self.assertNotIn('corroboratedComparisonPassed', row)

    async def test_reconnect_failure_cannot_pass_or_skip_the_second_path(self):
        row = evidence()
        conn = Mock(close=AsyncMock())
        with patch.object(contract.trial, 'compare_role', AsyncMock(side_effect=contract.trial.DrainTrialError(contract.NATIVE_HOLD))), patch.object(contract.trial, 'connect_role', AsyncMock(side_effect=[conn, TimeoutError()])):
            with self.assertRaises(TimeoutError):
                await contract.compare_role(*self.args(row))
        conn.close.assert_awaited_once()
        self.assertFalse(row['originalCredentialReconnectedOnBothPaths'])
        self.assertNotIn('corroboratedComparisonPassed', row)

    async def test_arbitrary_label_cannot_reach_native_mutation_probe(self):
        args = list(self.args(evidence()))
        args[4] = 'application-session'
        with patch.object(contract.trial, 'compare_role', AsyncMock()) as compare:
            with self.assertRaises(contract.trial.DrainTrialError):
                await contract.compare_role(*args)
        compare.assert_not_called()

    async def test_peer_must_be_distinct_and_checked_on_two_paths(self):
        for role, urls in ((ROLE, ('a', 'b')), (OTHER, ()), (OTHER, ('a', 'a'))):
            args = list(self.args(evidence()))
            args[7], args[8] = role, urls
            with self.subTest(role=role, urls=urls), patch.object(contract.trial, 'compare_role', AsyncMock()) as compare:
                with self.assertRaises(contract.trial.DrainTrialError):
                    await contract.compare_role(*args)
                compare.assert_not_called()
