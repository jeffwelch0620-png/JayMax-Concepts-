"""Controlled credential round trip; originals are restored even after success.

Caller must durably pin the complete source baseline and private staged file
before invoking this module. No app cutover, grants, business writes or broad
session termination. Driver messages/SQL/passwords must never enter receipts.
"""
import asyncio
import re
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote, unquote, urlparse, urlunparse
from uuid import uuid4
from unittest.mock import patch
import db_pg
import db_auxiliary
import pooler_drain_trial as drain
import pooler_denial_contract as contract
import rotate_build_connections as rotation


class RehearsalError(RuntimeError):
    """Safe category only."""


def verify_private_file(path):
    path = Path(path)
    root = Path(os.environ['LOCALAPPDATA']) / 'JayMaxBuild' / 'credentials'
    if (os.name != 'nt' or not path.is_file() or path.is_symlink()
            or path.parent.is_symlink() or path.parent.is_junction()
            or not path.resolve().is_relative_to(root.resolve())):
        raise RehearsalError('Private credential file boundary held')
    shell = shutil.which('pwsh')
    if not shell:
        raise RehearsalError('Private credential ACL verifier unavailable')
    script = '''$ErrorActionPreference='Stop';
      $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;
      $allowed=@($sid,'S-1-5-18') | Sort-Object -Unique;
      $f=Get-Acl -LiteralPath $env:JAYMAX_REHEARSAL_FILE;
      $d=Get-Acl -LiteralPath (Split-Path -Parent $env:JAYMAX_REHEARSAL_FILE);
      foreach($a in @($f,$d)) {
        $actual=@($a.Access | ForEach-Object {$_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value} | Sort-Object -Unique);
        if ($a.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $sid -or
            ($actual -join ',') -ne ($allowed -join ',') -or
            @($a.Access | Where-Object {$_.AccessControlType -ne 'Allow'}).Count) {exit 2} };
      if (-not $d.AreAccessRulesProtected) {exit 2}; Write-Output 'verified' '''
    checked = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-Command', script],
        env={**os.environ, 'JAYMAX_REHEARSAL_FILE': str(path)}, capture_output=True,
        timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
    if checked.returncode or checked.stdout.strip() != b'verified':
        raise RehearsalError('Private credential file ACL held')


def direct(url, role, project):
    if not re.fullmatch(r'[a-z0-9]{20}', project):
        raise RehearsalError('Expected project reference required')
    u = urlparse(url)
    return urlunparse(u._replace(netloc=quote(role, safe='') + ':' + u.password
        + '@db.' + project + '.supabase.co:5432'))


def prerequisite(receipt, roles):
    if (receipt.get('format') != 'jaymax-corroborated-pooler-comparison-v1'
            or receipt.get('denialContract') != contract.CONTRACT
            or receipt.get('status') != 'passed_corroborated_pooler_denial_comparison'
            or receipt.get('stage') != 'complete' or receipt.get('roles') != roles
            or receipt.get('bothRoleCorroboratedComparisonsPassed') is not True
            or receipt.get('recoveryBaselinePreserved') is not True
            or receipt.get('ownerClosed') is not True):
        raise RehearsalError('Verified two-role corroborated-denial receipt required')
    expected = drain.review.validate_roles(roles, receipt['baselineRoleAttributes'])
    checks = receipt.get('checks', [])
    if len(checks) != 2 or {row.get('role') for row in checks} != set(roles.values()):
        raise RehearsalError('Two distinct verified role comparisons required')
    for check in checks:
        if check.get('corroboratedComparisonPassed') is not True:
            raise RehearsalError('Passing corroborated comparison required')
        contract.denial_mode(check, expected, check['role'])
    return expected


async def set_passwords(owner, roles, expected, config):
    # Validate every identifier and literal before any SQL can change a password.
    if set(roles) != set(rotation.KEYS) or set(expected) != set(roles.values()):
        raise RehearsalError('Two pinned build identities required')
    values = {}
    for kind, role in roles.items():
        if not re.fullmatch('jaymax_build_' + kind + '_[a-f0-9]{12}', role):
            raise RehearsalError('Exact generated role required')
        uri = urlparse(config.get(rotation.KEYS[kind], ''))
        password = unquote(uri.password or '')
        if (unquote(uri.username or '').rsplit('.', 1)[0] != role
                or not re.fullmatch(r'[A-Za-z0-9_-]{40,}', password)):
            raise RehearsalError('Pinned credential literal required')
        values[role] = password
    async with owner.transaction():
        await owner.execute("SET LOCAL statement_timeout='20s'; SET LOCAL lock_timeout='5s'")
        for role in values:
            if await owner.fetchval('SELECT oid FROM pg_roles WHERE rolname=$1', role) != expected[role]:
                raise RehearsalError('Recorded role OID changed')
        for role, password in values.items():
            await owner.execute('ALTER ROLE "' + role + '" LOGIN PASSWORD \'' + password + "' VALID UNTIL 'infinity'")


async def connect(url, role):
    conn = await drain.connect_role(url, role)
    try:
        await db_pg._init_connection(conn)
        return conn
    except BaseException:
        await conn.close()
        raise


async def fresh_both(config, roles, kind, project, verify_refresh=False):
    url = config[rotation.KEYS[kind]]
    for endpoint in (direct(url, roles[kind], project), url):
        if verify_refresh:
            await replacement_refresh(endpoint, roles[kind])
        else:
            conn = await connect(endpoint, roles[kind])
            await conn.close()
    return True


async def password_rejected(url, role):
    result = await drain.classify(url, role)
    if result != {'accepted': False, 'category': 'password_denied',
            'errorType': 'InvalidPasswordError', 'sqlstate': '28P01'}:
        raise RehearsalError('Fresh replaced-password denial held')
    return result


async def rejected_both(config, roles, project):
    result = {}
    for kind, key in rotation.KEYS.items():
        result[kind] = [await password_rejected(url, roles[kind])
            for url in (direct(config[key], roles[kind], project), config[key])]
    return result


async def replacement_refresh(url, role):
    for attempt in range(3):
        try:
            conn = await connect(url, role)
        except drain.asyncpg.InvalidPasswordError:
            if attempt == 2:
                raise
            await asyncio.sleep(15)
        else:
            await conn.close()
            return


async def pools_and_accessors(config, roles):
    pools = []
    close_error = None
    try:
        for kind, constructor in (('inventory', db_pg._try_connect), ('accounts', db_auxiliary._try_connect)):
            pool = await constructor(config[rotation.KEYS[kind]])
            if pool is None:
                raise RehearsalError('Replacement pool startup gate held')
            pools.append(pool)
            async with pool.acquire() as conn:
                await asyncio.wait_for(conn.execute('SET default_transaction_read_only=on'), 20)
                identity = await asyncio.wait_for(conn.fetchrow('SELECT session_user AS login,current_user AS current'), 20)
                if dict(identity) != {'login': roles[kind], 'current': roles[kind]}:
                    raise RehearsalError('Replacement pool actual LOGIN held')
                if await asyncio.wait_for(conn.fetchval("SELECT '{}'::jsonb"), 20) != {}:
                    raise RehearsalError('Replacement pool JSON codec held')
    finally:
        for pool in reversed(pools):
            try:
                await asyncio.wait_for(pool.close(), 20)
            except BaseException as exc:
                pool.terminate()
                close_error = close_error or exc
        if close_error:
            raise close_error
    from fastapi import HTTPException
    with patch.object(db_pg, '_pool', None), patch.object(db_auxiliary, '_pool', None), patch.object(db_auxiliary, '_configured', True):
        for accessor in (db_pg.pool, db_auxiliary.pool):
            try:
                accessor()
            except HTTPException as exc:
                if exc.status_code != 503:
                    raise RehearsalError('Unavailable configured accessor status held') from None
            else:
                raise RehearsalError('Unavailable configured accessor fallback held')


async def permissions(config, roles, emit=None):
    result = {}
    for kind, key in rotation.KEYS.items():
        if emit:
            emit(kind + '_permission_connection_prepared')
        conn = await connect(config[key], roles[kind])
        try:
            if kind == 'inventory':
                result[kind] = await asyncio.wait_for(rotation.candidate.inspect(conn, roles[kind], 'hosted_build'), 240)
                expected_status = 'passed_local_candidate'
            else:
                result[kind] = await asyncio.wait_for(rotation.auxiliary_permissions.inspect(conn), 60)
                expected_status = 'passed'
            if result[kind]['status'] != expected_status:
                raise RehearsalError('Read-only permission profile held')
        finally:
            await conn.close()
    return result


async def recover(owner, roles, expected, original, temporary, project, report, emit):
    await set_passwords(owner, roles, expected, original)
    emit('original_passwords_and_logins_restored')
    report['originalCredentialsAvailable'] = {kind: await fresh_both(original, roles, kind, project, verify_refresh=True) for kind in rotation.KEYS}
    # Refresh original pooled authentication before requiring temporary rejection.
    report['temporaryCredentialDenials'] = await rejected_both(temporary, roles, project)
    report['temporaryCredentialsRejectedOnBothPaths'] = True
    report['originalCredentialsRestoredOnBothPaths'] = True
    report['replacementPrivateConfigIsCurrent'] = False
    emit('original_credentials_reconnected_temporary_credentials_rejected')


async def roundtrip(owner, roles, expected, original, temporary, project, report, emit):
    if report.get('fullPreflightBaselineDurablySaved') is not True or report.get('privateAclVerified') is not True:
        raise RehearsalError('Durable full baseline and verified private staging required')
    clients = []
    try:
        for kind, key in rotation.KEYS.items():
            clients.append(await connect(original[key], roles[kind]))
        report['passwordMutationAttempted'] = True
        emit('password_rotation_prepared')  # Durable journal BEFORE transaction.
        await set_passwords(owner, roles, expected, temporary)
        report['passwordsChanged'] = True
        report['temporaryPasswordTransactionCommitted'] = True
        emit('temporary_password_rotation_committed')
        for conn in clients:
            if await conn.fetchval('SELECT 1') != 1:
                raise RehearsalError('Existing owned session continuity held')
        report['existingOwnedSessionsRemainAuthorized'] = True
        for conn in clients:
            await conn.close()
        clients.clear()
        for kind, key in rotation.KEYS.items():
            await replacement_refresh(temporary[key], roles[kind])
            await fresh_both(temporary, roles, kind, project)
        report['replacementCredentialsAuthenticatedOnBothPaths'] = True
        report['previousCredentialDenials'] = await rejected_both(original, roles, project)
        report['previousCredentialsRejectedOnBothPaths'] = True
        emit('temporary_credentials_authenticated_original_passwords_denied')
        await pools_and_accessors(temporary, roles)
        report['replacementPoolsReconnected'] = True
        report['unavailablePoolsReturn503WithoutFallback'] = True
        emit('actual_pools_reconnected_and_unavailable_accessors_hold')
        for kind in ('accounts', 'inventory'):
            other = 'inventory' if kind == 'accounts' else 'accounts'
            url = temporary[rotation.KEYS[kind]]
            peer = temporary[rotation.KEYS[other]]
            label = 'jaymax_retirement_probe_' + uuid4().hex
            client = await drain.connect_role(url, roles[kind], label)
            clients.append(client)
            check = {'kind': kind, 'role': roles[kind], 'strictOwnedDrainComparisonPassed': False,
                'comparisonCredentialScope': 'temporary_rehearsal_credential'}
            report['checks'].append(check)
            await contract.compare_role(owner, client, expected, roles[kind], label,
                direct(url, roles[kind], project), url, roles[other],
                (direct(peer, roles[other], project), peer), check, lambda stage: emit(kind + '_' + stage))
        report['bothRoleCorroboratedComparisonsPassed'] = True
        report['replacementPermissionProfiles'] = await permissions(temporary, roles, emit)
        report['replacementPermissionProfilesPassed'] = True
        report['rotationExercisePassed'] = True
        emit('temporary_rotation_and_recovery_exercise_passed')
    except Exception as exc:
        # Recovery may raise another error; retain the first safe type/stage too.
        report['exerciseErrorType'] = type(exc).__name__
        report['exerciseFailedStage'] = report.get('stage')
        raise
    finally:
        for conn in clients:
            try:
                await conn.close()
            except Exception:
                conn.terminate()
        report['ownedClientsClosed'] = True
        if report.get('passwordMutationAttempted'):
            # Includes an unacknowledged transaction or journal failure. Originals
            # always win; a passing exercise never activates temporary disk config.
            await recover(owner, roles, expected, original, temporary, project, report, emit)
