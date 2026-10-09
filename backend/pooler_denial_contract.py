"""Versioned, independently corroborated pooler denial for owned test clients.

This never reclassifies an internal error as native PostgreSQL authentication
denial. It qualifies only the exact observed provider lookup category after the
native-only comparison restores LOGIN and original credentials reconnect.
"""
import re
from datetime import datetime
import pooler_drain_trial as trial

CONTRACT = 'jaymax-corroborated-pooler-denial-v1'
NATIVE_HOLD = 'Pooler response did not prove strict authentication denial'


def denial_mode(check, expected, role):
    """Fail closed on missing, inconsistent or non-boolean runtime witnesses."""
    def require(value):
        if not value:
            raise trial.DrainTrialError('Corroborated pooler denial witnesses held')

    require(check.get('denialContract') == CONTRACT)
    require(role in expected and re.fullmatch(r'jaymax_build_(inventory|accounts)_[a-f0-9]{12}', role))
    require(type(expected[role]) is int and expected[role] > 0)
    require(check.get('role') == role and check.get('kind') in ('inventory', 'accounts')
        and role.startswith('jaymax_build_' + check['kind'] + '_'))
    require(check.get('ownerRoleOidBefore') == expected[role]
        and check.get('ownerRoleOidAfter') == expected[role])
    for name in ('disableAttempted', 'ownerConfirmsNoLogin', 'poolerClientObservedClosed',
            'otherRoleAvailableOnBothPaths', 'ownerConfirmsLoginRestored',
            'originalCredentialReconnectedOnBothPaths'):
        require(check.get(name) is True)
    owned = check.get('ownedClient', {})
    signal = check.get('signal', {})
    require(owned.get('ownedReadOnlyPoolerClientVerified') is True
        and owned.get('existingApplicationSession') is False)
    require(signal.get('ownedReadOnlyProbeTerminated') is True
        and signal.get('backendAbsentConfirmed') is True
        and signal.get('existingApplicationSessionsTargeted') is False)
    require(type(owned.get('pid')) is int and owned['pid'] > 0)
    try:
        started = datetime.fromisoformat(owned.get('backendStart', ''))
        require(started.tzinfo is not None)
    except (TypeError, ValueError):
        raise trial.DrainTrialError('Corroborated pooler denial witnesses held') from None
    for name in ('role', 'pid', 'backendStart'):
        require(owned.get(name) == signal.get(name))
    require(owned.get('role') == role)
    signatures = {
        'login_not_permitted': ('InvalidAuthorizationSpecificationError', '28000'),
        'password_denied': ('InvalidPasswordError', '28P01'),
        'eauthquery_user_not_found': ('InternalServerError', 'XX000'),
    }
    def category(result):
        require(isinstance(result, dict) and result.get('accepted') is False)
        value = result.get('category')
        require(value in signatures and (result.get('errorType'), result.get('sqlstate')) == signatures[value])
        return value
    require(category(check.get('direct')) == 'login_not_permitted')
    attempts = check.get('poolerAttempts')
    require(isinstance(attempts, list) and len(attempts) in (1, 2))
    categories = [category(result) for result in attempts]
    if all(value == 'eauthquery_user_not_found' for value in categories):
        require(len(categories) == 2 and check.get('strictOwnedDrainComparisonPassed') is False
            and check.get('nativeOnlyComparisonHeld') is True)
        return 'provider_lookup_with_independent_witnesses'
    require(all(value in ('login_not_permitted', 'password_denied') for value in categories)
        and check.get('strictOwnedDrainComparisonPassed') is True)
    return 'native_authentication_denial'


async def compare_role(owner, client, expected, role, label, direct_url, pooler_url,
        other_role, other_urls, check, emit):
    """Keep the native-only gate unchanged; qualify a separate contract afterward."""
    if not re.fullmatch(r'jaymax_retirement_probe_[a-f0-9]{32}', label):
        raise trial.DrainTrialError('Owned probe identity required')
    if (role == other_role or set(expected) != {role, other_role}
            or not re.fullmatch(r'jaymax_build_(inventory|accounts)_[a-f0-9]{12}', other_role)
            or not isinstance(other_urls, (tuple, list)) or len(other_urls) != 2
            or len(set(other_urls)) != 2):
        raise trial.DrainTrialError('Independent peer role and both paths required')
    check['denialContract'] = CONTRACT
    check['ownerRoleOidBefore'] = await owner.fetchval('SELECT oid FROM pg_roles WHERE rolname=$1', role)
    try:
        await trial.compare_role(owner, client, expected, role, label, direct_url,
            pooler_url, other_role, other_urls, check, emit)
    except trial.DrainTrialError as exc:
        if str(exc) != NATIVE_HOLD:
            raise
        # This is a new qualification, never a rewrite of the native-only result.
        check['nativeOnlyComparisonHeld'] = True
    check['ownerRoleOidAfter'] = await owner.fetchval('SELECT oid FROM pg_roles WHERE rolname=$1', role)
    check['originalCredentialReconnectedOnBothPaths'] = False
    for url in (direct_url, pooler_url):
        conn = await trial.connect_role(url, role)
        await conn.close()
    check['originalCredentialReconnectedOnBothPaths'] = True
    mode = denial_mode(check, expected, role)
    check['denialMode'] = mode
    check['corroboratedLookupDenialQualified'] = mode == 'provider_lookup_with_independent_witnesses'
    check['corroboratedComparisonPassed'] = True
    emit('corroborated_denial_qualified_after_recovery')
