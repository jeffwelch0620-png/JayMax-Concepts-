"""Read-only planning guard for replacing the two restricted database logins.

No role creation, SQL generation, password changes or permission installation.
Existing policies must match the reviewed profile before a transition is planned.
"""
import hashlib
import json
import auxiliary_permissions as auxiliary
import runtime_permissions as runtime
import credential_retirement_review as retirement


class RotationPlanError(RuntimeError):
    """Safe category only."""


def policy_contract(roles, attributes, policies, memberships):
    oids = retirement.validate_roles(roles, attributes)
    if memberships:
        raise RotationPlanError('Existing build role membership held')
    expected = {}
    for kind in ('inventory', 'accounts'):
        tables = runtime.PUBLIC if kind == 'inventory' else {name: auxiliary.VERBS for name in auxiliary.TABLES}
        prefix = 'runtime_candidate_' if kind == 'inventory' else 'auxiliary_candidate_'
        for table, verbs in tables.items():
            for verb in verbs:
                key = ('public', table, prefix + verb.lower())
                expected[key] = {'kind': kind, 'command': {'SELECT': 'r', 'INSERT': 'a', 'UPDATE': 'w', 'DELETE': 'd'}[verb],
                    'using_expr': None if verb == 'INSERT' else 'true',
                    'check_expr': 'true' if verb in ('INSERT', 'UPDATE') else None}
    seen = set()
    for row in policies:
        key = (row['schema'], row['table'], row['name'])
        specification = expected.get(key)
        if specification is None or key in seen:
            raise RotationPlanError('Unreviewed or duplicate applicable policy held')
        if (row['role_oids'] != [oids[roles[specification['kind']]]]
                or row['permissive'] is not True
                or any(row[name] != specification[name] for name in ('command', 'using_expr', 'check_expr'))):
            raise RotationPlanError('Existing role-addressed policy differs from reviewed profile')
        seen.add(key)
    if seen != set(expected):
        raise RotationPlanError('Incomplete existing policy coverage held')
    digest = hashlib.sha256(json.dumps(sorted(policies, key=lambda row: (row['schema'], row['table'], row['name'])),
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'format': 'jaymax-parallel-rotation-review-v1', 'status': 'reviewed_existing_policy_contract',
        'existingRoleOids': oids, 'existingPolicySha256': digest,
        'policyCounts': {kind: sum(value['kind'] == kind for value in expected.values()) for kind in roles},
        'transitionPolicyChanges': [{'schema': key[0], 'table': key[1], 'policy': key[2],
            'profile': value['kind'], 'change': 'add_exact_recorded_replacement_role_to_TO_only'}
            for key, value in sorted(expected.items())],
        'inventoryVerifierCurrentlyRequiresSingletonRole': True,
        'cohortAwareVerifierRequiredBeforeProvisioning': True,
        'automaticMembershipCopyAllowed': False, 'automaticDefaultPrivilegeChangesAllowed': False,
        'automaticObjectOwnershipTransferAllowed': False, 'automaticClientSwitchAllowed': False,
        'automaticOldRoleRetirementAllowed': False, 'sqlExecutable': False,
        'operationalReleaseApproved': False}
