"""Exact profile SQL review, capacity holds, and deliberate rollback sequencing."""
from datetime import datetime, timedelta, timezone
import unittest
import parallel_install_plan as installer
import test_parallel_rotation_review as originals

NOW = datetime(2026, 10, 9, 23, 0, tzinfo=timezone.utc)
NEW = {'inventory': 'jaymax_build_inventory_' + '3' * 12, 'accounts': 'jaymax_build_accounts_' + '4' * 12}
PINS = {name: 'b' * 64 for name in ('applicationRows', 'track1', 'migrationLedger', 'unaffectedAccess', 'administrativeMemberships')}
CAPACITY = {'observedAt': NOW.isoformat(), 'clientInstances': 1, 'databaseSlotsAvailable': 7, 'poolerSlotsAvailable': 7, 'sessionPoolSize': 15}


def plan(**overrides):
    attrs, policies = originals.fixture()
    options = dict(preservation_pins=PINS, capacity=CAPACITY, now=NOW, reference='local')
    return installer.prepare(originals.ROLES, attrs, policies, [], NEW, **(options | overrides))


class InstallReviewGuards(unittest.TestCase):
    def test_exact_profile_and_policy_delta_has_no_password_or_apply_authority(self):
        result = plan(); sql = result['reviewSql']
        self.assertFalse(result['sqlExecutable']); self.assertFalse(result['passwordSqlIncluded'])
        self.assertFalse(result['oldCredentialsChanged']); self.assertFalse(result['automaticRoleDrop'])
        self.assertEqual(len(sql['createNOLOGIN']), 2)
        self.assertTrue(all('NOLOGIN' in command and 'PASSWORD' not in command for command in sql['createNOLOGIN']))
        self.assertEqual(len(sql['addExactPolicyCohort']), 66)
        self.assertEqual(len(sql['restoreOriginalPolicyCohort']), 66)
        for forward, rollback in zip(sql['addExactPolicyCohort'], sql['restoreOriginalPolicyCohort']):
            self.assertTrue(forward.startswith('ALTER POLICY ')); self.assertNotIn('USING', forward); self.assertNotIn('WITH CHECK', forward)
            self.assertEqual(forward.split(' TO ')[0], rollback.split(' TO ')[0])
        account_sql = [command for command in sql['grantExactProfile'] if NEW['accounts'] in command]
        self.assertEqual(len(account_sql), 3)
        self.assertTrue(all('staff_pins' not in command and 'purchasing' not in command for command in account_sql))
        self.assertEqual(result['capacity']['requiredAdditionalSlots'], 7)
        self.assertIn('commit_unknown', result['commitAcknowledgementLost'])
        self.assertLess(result['rollbackOrder'].index('verify_original_pair_while_both_roles_LOGIN'), result['rollbackOrder'].index('pin_new_role_OIDs_then_NOLOGIN'))

    def test_unmeasured_capacity_keeps_review_only_and_over_budget_or_stale_measurement_holds(self):
        self.assertEqual(plan(capacity=None)['capacity']['status'], 'held_unmeasured_capacity')
        for delta in ({'clientInstances': 0}, {'clientInstances': 3}, {'databaseSlotsAvailable': 6},
                      {'poolerSlotsAvailable': 6}, {'clientInstances': True}, {'sessionPoolSize': 2}, {'sessionPoolSize': True},
                      {'observedAt': (NOW - timedelta(minutes=16)).isoformat()},
                      {'observedAt': (NOW + timedelta(seconds=1)).isoformat()}, {'observedAt': 'not-a-time'}):
            with self.subTest(delta=delta), self.assertRaises(installer.InstallPlanError):
                plan(capacity=CAPACITY | delta)
        two = installer.capacity_check(CAPACITY | {'clientInstances': 2, 'databaseSlotsAvailable': 11, 'poolerSlotsAvailable': 11}, NOW)
        self.assertEqual(two['perReplacementRolePeak'], 5)

    def test_unreviewed_existing_policy_source_or_missing_preservation_pins_holds(self):
        for pins in ({}, PINS | {'track1': 'unreviewed'}, PINS | {'unexpected': 'b' * 64}):
            with self.subTest(pins=pins), self.assertRaises(installer.InstallPlanError):
                plan(preservation_pins=pins)
        attrs, policies = originals.fixture(); policies[0]['role_oids'] = [0]
        with self.assertRaises(installer.reviewed.RotationPlanError):
            installer.prepare(originals.ROLES, attrs, policies, [], NEW, preservation_pins=PINS, reference='local')

    def test_role_reuse_profile_swap_or_sql_identifier_injection_holds(self):
        attrs, policies = originals.fixture()
        for names in (originals.ROLES, NEW | {'accounts': NEW['inventory']}, NEW | {'inventory': 'bad; DROP ROLE postgres'}, {}):
            with self.subTest(names=names), self.assertRaises(installer.InstallPlanError):
                installer.prepare(originals.ROLES, attrs, policies, [], names, preservation_pins=PINS, reference='local')
