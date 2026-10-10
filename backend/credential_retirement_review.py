"""Observe exact build-role sessions and rehearse signals on owned probe clients only.

This is not an old-role retirement command. It cannot terminate an observed
application session: the caller must hold the newly created probe connection,
its UUID application label, PID and backend-start timestamp. No LOGIN, password,
grant, service setting or business row is changed.
"""
import re
from datetime import datetime


class RetirementReviewError(RuntimeError):
    """Safe category only; never include connection URLs, SQL or raw driver text."""


ACTIVITY = """SELECT a.pid,a.usesysid AS role_oid,a.usename AS role,
    a.datname AS database,a.backend_start,a.state,a.xact_start IS NOT NULL AS in_transaction,
    a.backend_type,a.application_name,
    (SELECT count(*) FROM pg_locks l WHERE l.pid=a.pid) AS lock_count
    FROM pg_stat_activity a WHERE a.usename=ANY($1::text[]) ORDER BY a.pid"""


def validate_roles(roles, attributes):
    if set(roles) != {'inventory', 'accounts'} or len(set(roles.values())) != 2:
        raise RetirementReviewError('Two exact recorded build roles required')
    expected = {}
    for kind, name in roles.items():
        if not re.fullmatch('jaymax_build_' + kind + '_[a-f0-9]{12}', name):
            raise RetirementReviewError('Generated build identity required')
        matches = [row for row in attributes if row['rolname'] == name]
        if len(matches) != 1:
            raise RetirementReviewError('Recorded role identity missing')
        row = matches[0]
        if (not row['rolcanlogin'] or row['rolconnlimit'] != 6 or
                any(row[key] for key in ('rolsuper','rolbypassrls','rolcreatedb',
                    'rolcreaterole','rolreplication','rolinherit'))):
            raise RetirementReviewError('Retained role attributes held')
        expected[name] = row['oid']
    if len(set(expected.values())) != 2:
        raise RetirementReviewError('Distinct recorded role OIDs required')
    return expected


def public_activity(rows, roles):
    """Exclude raw query text, addresses and arbitrary client labels from evidence."""
    allowed = set(roles.values())
    result = []
    for row in rows:
        if row['role'] not in allowed:
            raise RetirementReviewError('Unexpected observed role')
        result.append({key: row[key] for key in ('pid','role_oid','role','database',
            'state','in_transaction','backend_type','lock_count')} |
            {'backendStart': row['backend_start'].isoformat() if row['backend_start'] else None,
             'isOwnedProbeLabel': bool(re.fullmatch(r'jaymax_retirement_probe_[a-f0-9]{32}', row['application_name'] or ''))})
    return result


def validate_probe(row, expected, role, pid, started, label, owner_pid):
    if (role not in expected or not re.fullmatch(r'jaymax_retirement_probe_[a-f0-9]{32}', label)
            or type(pid) is not int or pid <= 0 or pid == owner_pid
            or not isinstance(started, datetime) or started.tzinfo is None):
        raise RetirementReviewError('Owned probe identity required')
    if (row is None or row['pid'] != pid or row['role'] != role or row['role_oid'] != expected[role]
            or row['database'] != 'postgres' or row['backend_start'] != started
            or row['application_name'] != label or row['backend_type'] != 'client backend'):
        raise RetirementReviewError('Owned probe identity changed')
    if row['state'] != 'idle' or row['in_transaction'] or row['lock_count']:
        raise RetirementReviewError('Only idle transaction-free unlocked probe may be signalled')


async def signal_owned_probe(owner, client, expected, role, label):
    """Rehearse only a live caller-owned read-only client, never inventory candidates."""
    if client.is_closed():
        raise RetirementReviewError('Owned probe already closed')
    identity = await client.fetchrow("""SELECT pg_backend_pid() AS pid,session_user AS login,
        current_user AS current,current_setting('application_name') AS label,
        current_setting('transaction_read_only') AS read_only,
        (SELECT backend_start FROM pg_stat_activity WHERE pid=pg_backend_pid()) AS started""")
    if (identity['login'] != role or identity['current'] != role or identity['label'] != label
            or identity['read_only'] != 'on'):
        raise RetirementReviewError('Owned probe read-only identity held')
    owner_pid = await owner.fetchval('SELECT pg_backend_pid()')
    rows = await owner.fetch(ACTIVITY, [role])
    row = next((value for value in rows if value['pid'] == identity['pid']), None)
    validate_probe(row, expected, role, identity['pid'], identity['started'], label, owner_pid)
    # Repeat every identity/busy guard in the signalling statement itself. PID
    # reuse, a transaction starting, or an application-label change yields no call.
    signalled = await owner.fetchval("""SELECT pg_terminate_backend(a.pid,5000)
        FROM pg_stat_activity a WHERE a.pid=$1 AND a.backend_start=$2
        AND a.usesysid=$3 AND a.usename=$4 AND a.datname='postgres'
        AND a.application_name=$5 AND a.backend_type='client backend'
        AND a.pid<>pg_backend_pid() AND a.state='idle' AND a.xact_start IS NULL
        AND NOT EXISTS(SELECT 1 FROM pg_locks l WHERE l.pid=a.pid)""",
        identity['pid'], identity['started'], expected[role], role, label)
    if signalled is not True:
        raise RetirementReviewError('Owned probe signal did not confirm termination')
    present = await owner.fetchval('SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE pid=$1 AND backend_start=$2)',
        identity['pid'], identity['started'])
    if present:
        raise RetirementReviewError('Owned probe backend still present')
    return {'role': role, 'pid': identity['pid'], 'backendStart': identity['started'].isoformat(),
        'ownedReadOnlyProbeTerminated': True, 'backendAbsentConfirmed': True,
        'existingApplicationSessionsTargeted': False}
