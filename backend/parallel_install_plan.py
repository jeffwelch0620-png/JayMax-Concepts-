"""Concrete review-only grant/rollback plan; no database or filesystem mutation.

No apply entrypoint, password SQL, active-config writer or old-role retirement.
Original preflight/row/access/ledger pins and measured capacity remain independent.
"""
from datetime import datetime, timezone
import re
import auxiliary_permissions as auxiliary
import runtime_permissions as runtime
import parallel_rotation_review as reviewed


class InstallPlanError(ValueError):
    """Safe category only."""


def quoted(name):
    if not re.fullmatch(r'[a-z_][a-z0-9_]*', name):
        raise InstallPlanError('Reviewed SQL identifier required')
    return '"' + name + '"'


def capacity_check(capacity, now):
    """Reviewed limit-six roles, max-two pools; unknown capacity always holds."""
    if capacity is None:
        return {'status': 'held_unmeasured_capacity', 'requiredAdditionalSlots': None}
    try:
        if set(capacity) != {'observedAt', 'clientInstances', 'databaseSlotsAvailable', 'poolerSlotsAvailable', 'sessionPoolSize'}:
            raise InstallPlanError('Exact capacity observation required')
        seen = datetime.fromisoformat(capacity['observedAt'])
        if (seen.tzinfo is None or now.tzinfo is None or not 0 <= (now - seen).total_seconds() <= 900
                or any(type(capacity[key]) is not int or capacity[key] < 0 for key in
                       ('clientInstances', 'databaseSlotsAvailable', 'poolerSlotsAvailable', 'sessionPoolSize'))
                or capacity['clientInstances'] < 1):
            raise InstallPlanError('Recent measured capacity required')
        # Extra replacement pools plus one diagnostic connection per profile and
        # one controlling owner. Existing application pools are already counted
        # in the measured free slots; they are not assumed to disappear.
        additional = capacity['clientInstances'] * 4 + 3
        per_role = capacity['clientInstances'] * 2 + 1
        if (per_role > min(6, capacity['sessionPoolSize']) or min(capacity['databaseSlotsAvailable'], capacity['poolerSlotsAvailable']) < additional):
            raise InstallPlanError('Overlap connection budget held')
        return {'status': 'reviewed_capacity_observation', 'requiredAdditionalSlots': additional,
                'perReplacementRolePeak': per_role, 'observedAt': capacity['observedAt'],
                'clientInstances': capacity['clientInstances'], 'sessionPoolSize': capacity['sessionPoolSize']}
    except (TypeError, KeyError, ValueError, AttributeError):
        raise InstallPlanError('Capacity observation held') from None


def prepare(roles, attributes, policies, memberships, replacements, *, preservation_pins,
            capacity=None, now=None, reference='hosted_build'):
    """Render exact candidate SQL for review, with an explicit non-executable gate.

    No PIN, user, inventory, purchase, prep, sales or migration rows are written.
    Supplied preservation pins must originate in the independently archived
    preflight; this function does not authenticate their origin.
    """
    baseline = reviewed.policy_contract(roles, attributes, policies, memberships)
    if (set(replacements) != set(roles) or len(set(replacements.values())) != 2
            or set(replacements.values()) & set(roles.values())):
        raise InstallPlanError('Two distinct proposed replacement identities required')
    for kind, name in replacements.items():
        if not re.fullmatch('jaymax_build_' + kind + '_[a-f0-9]{12}', name):
            raise InstallPlanError('Generated profile-specific replacement required')
    pin_names = {'applicationRows', 'track1', 'migrationLedger', 'unaffectedAccess', 'administrativeMemberships'}
    if (set(preservation_pins) != pin_names
            or any(not re.fullmatch(r'[a-f0-9]{64}', value) for value in preservation_pins.values())):
        raise InstallPlanError('Independent complete preservation pins required')
    budget = capacity_check(capacity, now or datetime.now(timezone.utc))
    profile = runtime.manifest()
    contract = runtime.contract(profile, reference)
    matrix = runtime.table_privileges(profile)
    functions = [signature for signature, value in contract['functions'].items()
                 if not value['securityDefiner'] and (value['name'].startswith('public.') or not value['trigger'])]
    create, grants, revoke, overlap, restore = [], [], [], [], []
    for kind, role in replacements.items():
        target = quoted(role)
        create.append('CREATE ROLE ' + target + ' NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION CONNECTION LIMIT 6;')
        schemas = ('public', *runtime.readiness.PRIVATE) if kind == 'inventory' else ('public',)
        for schema in schemas:
            grants.append('GRANT USAGE ON SCHEMA ' + quoted(schema) + ' TO ' + target + ';')
            revoke.append('REVOKE USAGE ON SCHEMA ' + quoted(schema) + ' FROM ' + target + ';')
        tables = matrix if kind == 'inventory' else {'public.' + table: auxiliary.VERBS for table in auxiliary.TABLES}
        for table, verbs in sorted(tables.items()):
            relation = '.'.join(map(quoted, table.split('.')))
            grants.append('GRANT ' + ','.join(verbs) + ' ON ' + relation + ' TO ' + target + ';')
            revoke.append('REVOKE ' + ','.join(verbs) + ' ON ' + relation + ' FROM ' + target + ';')
        if kind == 'inventory':
            for signature in sorted(functions):
                # Only signatures from the independently frozen catalog are used.
                grants.append('GRANT EXECUTE ON FUNCTION ' + signature + ' TO ' + target + ';')
                revoke.append('REVOKE EXECUTE ON FUNCTION ' + signature + ' FROM ' + target + ';')
    for change in baseline['transitionPolicyChanges']:
        table = quoted(change['schema']) + '.' + quoted(change['table'])
        prefix = 'ALTER POLICY ' + quoted(change['policy']) + ' ON ' + table + ' TO '
        old = quoted(roles[change['profile']]); new = quoted(replacements[change['profile']])
        overlap.append(prefix + old + ',' + new + ';')
        restore.append(prefix + old + ';')
    stages = [
        {'stage': 'independent_preflight', 'requires': ['original_actual_logins_and_profiles', 'complete_preservation_pins', 'measured_capacity', 'registered_clients_and_revisions']},
        {'stage': 'private_credentials_staged', 'requires': ['fresh_private_directory_and_file_acl', 'durable_credentials_before_LOGIN', 'no_active_configuration_overwrite']},
        {'stage': 'create_NOLOGIN_roles', 'requires': ['creation_intent_journal_fsynced', 'fresh_name_collision_check', 'atomic_commit_with_recorded_OIDs_and_attributes']},
        {'stage': 'apply_exact_grants_and_overlap', 'requires': ['independent_creation_and_membership_receipt', 'verified_startup_revision', 'original_policy_digest_rechecked', 'bounded_transaction']},
        {'stage': 'enable_and_verify_replacements', 'requires': ['secure_password_assignment_without_public_SQL', 'all_four_read_only_profiles', 'both_actual_pool_constructors', 'preservation_verification']},
        {'stage': 'prove_return_to_originals', 'requires': ['close_owned_replacement_pools', 'fresh_original_pair_under_overlap', 'restore_exact_original_TO_lists', 'original_singleton_startup', 'unchanged_original_credentials_and_preservation']},
        {'stage': 'review_handoff', 'requires': ['all_owned_probe_clients_closed', 'new_roles_NOLOGIN_if_trial_rolled_back', 'unchanged_client_registry', 'separate_retirement_and_release_gates']},
    ]
    return {'format': 'jaymax-parallel-install-review-plan-v1', 'status': 'review_only',
        'originalRoles': dict(roles), 'proposedReplacementRoles': dict(replacements),
        'replacementOids': None, 'originalPolicySha256': baseline['existingPolicySha256'],
        'permissionMatrixSha256': runtime.digest(matrix), 'catalogContractSha256': runtime.digest(contract),
        'preservationPins': dict(preservation_pins), 'capacity': budget,
        'reviewSql': {'createNOLOGIN': create, 'grantExactProfile': grants, 'addExactPolicyCohort': overlap,
                      'restoreOriginalPolicyCohort': restore, 'revokeExactReplacementProfile': list(reversed(revoke))},
        'stages': stages, 'commitAcknowledgementLost': 'hold_commit_unknown_and_reconcile_fresh_catalog_before_any_retry',
        'rollbackOrder': ['close_owned_replacement_pools', 'verify_original_pair_while_both_roles_LOGIN', 'close_owned_original_overlap_probe_pools',
                          'restore_original_TO_singletons', 'verify_original_default_account_startup_and_inventory_preflight',
                          'pin_new_role_OIDs_then_NOLOGIN', 'revoke_only_reviewed_new_grants_if_unchanged',
                          'verify_preservation_and_keep_new_NOLOGIN_roles_for_dependency_review'],
        'unknownSessions': 'hold_no_automatic_termination', 'automaticRoleDrop': False,
        'automaticMembershipCopy': False, 'defaultPrivilegesChanged': False, 'objectOwnershipChanged': False,
        'passwordSqlIncluded': False, 'oldCredentialsChanged': False, 'sqlExecutable': False,
        'applicationConfigurationChanged': False, 'operationalReleaseApproved': False}
