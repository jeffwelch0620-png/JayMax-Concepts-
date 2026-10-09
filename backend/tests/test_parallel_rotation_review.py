"""Policy drift must prevent creation of an overlapping-account plan."""
import copy
import unittest
import parallel_rotation_review as review

ROLES = {'inventory': 'jaymax_build_inventory_' + '1' * 12,
    'accounts': 'jaymax_build_accounts_' + '2' * 12}


def fixture():
    attributes = [{'rolname': role, 'oid': 101 + index, 'rolcanlogin': True,
        'rolconnlimit': 6, **{key: False for key in ('rolsuper', 'rolbypassrls', 'rolcreatedb',
            'rolcreaterole', 'rolreplication', 'rolinherit')}} for index, role in enumerate(ROLES.values())]
    policies = []
    for index, kind in enumerate(ROLES):
        tables = review.runtime.PUBLIC if kind == 'inventory' else {name: review.auxiliary.VERBS for name in review.auxiliary.TABLES}
        prefix = 'runtime_candidate_' if kind == 'inventory' else 'auxiliary_candidate_'
        for table, verbs in tables.items():
            for verb in verbs:
                policies.append({'schema': 'public', 'table': table, 'name': prefix + verb.lower(),
                    'role_oids': [101 + index], 'permissive': True,
                    'command': {'SELECT': 'r', 'INSERT': 'a', 'UPDATE': 'w', 'DELETE': 'd'}[verb],
                    'using_expr': None if verb == 'INSERT' else 'true',
                    'check_expr': 'true' if verb in ('INSERT', 'UPDATE') else None})
    return attributes, policies


class PlanningGuards(unittest.TestCase):
    def test_exact_current_contract_produces_review_only_plan(self):
        attributes, policies = fixture()
        plan = review.policy_contract(ROLES, attributes, policies, [])
        self.assertFalse(plan['sqlExecutable'])
        self.assertTrue(plan['cohortAwareVerifierRequiredBeforeProvisioning'])
        self.assertEqual(sum(plan['policyCounts'].values()), len(policies))
        self.assertFalse(plan['automaticOldRoleRetirementAllowed'])

    def test_public_cross_profile_or_extra_role_never_qualifies(self):
        attributes, policies = fixture()
        for oids in ([0], [102], [101, 999], [], [101, 101]):
            row = copy.deepcopy(policies)
            row[0]['role_oids'] = oids
            with self.subTest(oids=oids), self.assertRaises(review.RotationPlanError):
                review.policy_contract(ROLES, attributes, row, [])

    def test_expression_command_or_restrictive_drift_holds(self):
        attributes, policies = fixture()
        for key, value in (('using_expr', 'false'), ('check_expr', 'true'),
                ('command', '*'), ('permissive', False), ('schema', 'auth'), ('name', 'unknown')):
            row = copy.deepcopy(policies)
            row[0][key] = value
            with self.subTest(key=key), self.assertRaises(review.RotationPlanError):
                review.policy_contract(ROLES, attributes, row, [])

    def test_missing_duplicate_or_unreviewed_policy_holds(self):
        attributes, policies = fixture()
        for row in (policies[1:], policies + [policies[0]], policies + [policies[0] | {'name': 'extra'}]):
            with self.subTest(count=len(row)), self.assertRaises(review.RotationPlanError):
                review.policy_contract(ROLES, attributes, row, [])

    def test_membership_or_elevated_identity_cannot_be_copied(self):
        attributes, policies = fixture()
        with self.assertRaises(review.RotationPlanError):
            review.policy_contract(ROLES, attributes, policies, [{'member': 101, 'role': 999}])
        for key in ('rolinherit', 'rolsuper', 'rolbypassrls', 'rolcreatedb', 'rolcreaterole', 'rolreplication'):
            row = copy.deepcopy(attributes)
            row[0][key] = True
            with self.subTest(key=key), self.assertRaises(review.retirement.RetirementReviewError):
                review.policy_contract(ROLES, row, policies, [])
