"""Explicit, read-only overlap assessment; never enables the application cutover.

The record's digest, original/replacement identities and original policy digest
must come from independently reviewed receipts, not from the target catalog.
No environment switch enables overlap. Normal startup uses singleton policies.
"""
from dataclasses import dataclass, field
import hashlib
import json
import re
from urllib.parse import unquote, urlsplit

PROFILES = ('inventory', 'accounts')
FLAGS = ('rolsuper', 'rolbypassrls', 'rolcreatedb', 'rolcreaterole', 'rolreplication', 'rolinherit')
_VERIFIED = object()


class TransitionError(ValueError):
    """Safe category only; do not include credential or driver material."""


@dataclass(frozen=True)
class VerifiedOverlap:
    project: str
    pairs: tuple
    record_sha256: str
    baseline_policy_sha256: str
    memberships: tuple
    _proof: object = field(repr=False, compare=False)

    def identities(self):
        if self._proof is not _VERIFIED:
            raise TransitionError('Independently verified overlap record required')
        return {kind: {'original': {'name': old, 'oid': old_oid},
                       'replacement': {'name': new, 'oid': new_oid}}
                for kind, old, old_oid, new, new_oid in self.pairs}

    def cohort(self, profile, role):
        pair = self.identities().get(profile)
        if pair is None or role not in {value['name'] for value in pair.values()}:
            raise TransitionError('Assessed role outside recorded profile')
        return tuple(value['oid'] for value in pair.values())


MEMBERSHIP_FIELDS = ('roleid', 'member', 'grantor', 'member_name', 'grantor_name',
                     'admin_option', 'inherit_option', 'set_option')


def verify_record(raw, *, expected_sha256, expected_project, expected_pairs,
                  expected_baseline_policy_sha256, expected_memberships):
    """Compare a reviewed record to independent pins, then freeze its identities.

    This checks integrity, not provenance: callers must obtain the expected pins
    from the preserved preflight and controlled creation journal. Copying pins
    out of the input record is not independent verification.
    """
    if (not isinstance(raw, bytes) or not re.fullmatch(r'[a-f0-9]{64}', expected_sha256 or '')
            or hashlib.sha256(raw).hexdigest() != expected_sha256
            or not re.fullmatch(r'[a-z0-9]{20}', expected_project or '')
            or not re.fullmatch(r'[a-f0-9]{64}', expected_baseline_policy_sha256 or '')):
        raise TransitionError('Independent record, project and policy pins required')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise TransitionError('Duplicate record field held')
            result[key] = value
        return result
    try:
        record = json.loads(raw, object_pairs_hook=unique)
        if (set(record) != {'format', 'projectRef', 'phase', 'rolePairs', 'baselinePolicySha256', 'membershipContract'}
                or record['format'] != 'jaymax-permission-overlap-v1'
                or record['projectRef'] != expected_project or record['phase'] != 'overlap'
                or record['baselinePolicySha256'] != expected_baseline_policy_sha256
                or record['rolePairs'] != expected_pairs or set(record['rolePairs']) != set(PROFILES)
                or record['membershipContract'] != expected_memberships):
            raise TransitionError('Unreviewed transition record held')
        result, names, oids = [], set(), set()
        for kind in PROFILES:
            pair = record['rolePairs'][kind]
            if set(pair) != {'original', 'replacement'}:
                raise TransitionError('Exact original and replacement pair required')
            for value in pair.values():
                if (set(value) != {'name', 'oid'}
                        or not re.fullmatch('jaymax_build_' + kind + '_[a-f0-9]{12}', value['name'])
                        or type(value['oid']) is not int or not 0 < value['oid'] < 2**32
                        or value['name'] in names or value['oid'] in oids):
                    raise TransitionError('Distinct pinned profile identities required')
                names.add(value['name']); oids.add(value['oid'])
            old, new = pair['original'], pair['replacement']
            result.append((kind, old['name'], old['oid'], new['name'], new['oid']))
        memberships, covered = [], set()
        for row in record['membershipContract']:
            # Supabase's creator administration is not runtime inheritance. Only
            # exact independently recorded metadata with no SET/INHERIT qualifies.
            if (set(row) != set(MEMBERSHIP_FIELDS)
                    or any(type(row[key]) is not int or not 0 < row[key] < 2**32 for key in ('roleid', 'member', 'grantor'))
                    or row['roleid'] not in oids or row['roleid'] in covered
                    or row['member'] in oids or row['grantor'] in oids
                    or row['member_name'] != 'postgres' or row['grantor_name'] not in ('postgres', 'supabase_admin')
                    or row['admin_option'] is not True or row['inherit_option'] is not False or row['set_option'] is not False):
                raise TransitionError('Unreviewed administrative membership held')
            memberships.append(tuple(row[key] for key in MEMBERSHIP_FIELDS)); covered.add(row['roleid'])
        return VerifiedOverlap(expected_project, tuple(result), expected_sha256,
                               expected_baseline_policy_sha256, tuple(sorted(memberships)), _VERIFIED)
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError, UnicodeDecodeError):
        raise TransitionError('Malformed transition record held') from None


async def live_cohort(conn, context, profile, role):
    """Require all four exact restricted roles in the same read-only snapshot."""
    if not isinstance(context, VerifiedOverlap):
        raise TransitionError('Verified overlap object required')
    cohort = context.cohort(profile, role)
    expected = {value['name']: value['oid'] for pair in context.identities().values() for value in pair.values()}
    rows = await conn.fetch('''SELECT rolname,oid,rolcanlogin,rolconnlimit,
        rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication,rolinherit
        FROM pg_roles WHERE rolname=ANY($1::text[])''', list(expected))
    if (len(rows) != 4 or {row['rolname']: row['oid'] for row in rows} != expected
            or any(row['rolcanlogin'] is not True or row['rolconnlimit'] != 6
                   or any(row[key] for key in FLAGS) for row in rows)):
        raise TransitionError('Recorded role identity or restricted attributes changed')
    memberships = await conn.fetch('''SELECT a.roleid,a.member,a.grantor,
        m.rolname AS member_name,g.rolname AS grantor_name,
        a.admin_option,a.inherit_option,a.set_option FROM pg_auth_members a
        JOIN pg_roles m ON m.oid=a.member JOIN pg_roles g ON g.oid=a.grantor
        WHERE a.member=ANY($1::oid[]) OR a.roleid=ANY($1::oid[])''', list(expected.values()))
    if tuple(sorted(tuple(row[key] for key in MEMBERSHIP_FIELDS) for row in memberships)) != context.memberships:
        raise TransitionError('Transition role membership differs from independent pins')
    return cohort


def policy_valid(row, tables, prefix, cohort):
    """Exact per-verb policy; only TO's recorded cohort may vary in overlap."""
    verb = row['polname'].removeprefix(prefix).upper()
    oids = list(row['polroles'])
    return (row['table_name'].startswith('public.')
            and verb in tables.get(row['table_name'][7:], ())
            and row['polname'] == prefix + verb.lower()
            and len(oids) == len(cohort) and all(type(oid) is int for oid in oids)
            and len(set(oids)) == len(oids) and set(oids) == set(cohort)
            and row['polpermissive'] is True
            and row['polcmd'] == {'SELECT': 'r', 'INSERT': 'a', 'UPDATE': 'w', 'DELETE': 'd'}.get(verb)
            and row['using_expr'] == (None if verb == 'INSERT' else 'true')
            and row['check_expr'] == ('true' if verb in ('INSERT', 'UPDATE') else None))


def endpoint_role(context, url, profile):
    """Bind the standalone assessor's actual connection to project and role."""
    try:
        uri = urlsplit(url)
        if (not isinstance(context, VerifiedOverlap) or uri.scheme not in ('postgres', 'postgresql')
                or uri.path != '/postgres' or uri.fragment or uri.query or (uri.port or 5432) != 5432):
            raise TransitionError('Reviewed PostgreSQL endpoint required')
        user, host = unquote(uri.username or ''), (uri.hostname or '').lower()
        if host == 'db.' + context.project + '.supabase.co':
            role = user
        elif re.fullmatch(r'aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com', host):
            role, project = user.rsplit('.', 1)
            if project != context.project:
                raise TransitionError('Connection project differs from reviewed record')
        else:
            raise TransitionError('Reviewed Supabase endpoint required')
        context.cohort(profile, role)
        return role
    except (ValueError, TypeError, AttributeError):
        raise TransitionError('Connection outside reviewed project/profile') from None


async def assess_url(context, url, profile):
    """Explicit diagnostic only: fresh actual LOGIN, verified TLS, always close."""
    role = endpoint_role(context, url, profile)
    import asyncpg
    from db_tls import connection_tls
    import runtime_permissions
    import auxiliary_permissions
    conn = await asyncpg.connect(url, ssl=connection_tls(url), timeout=15,
                                 command_timeout=30, statement_cache_size=0)
    try:
        identity = await conn.fetchrow('SELECT session_user AS login,current_user AS current')
        if dict(identity) != {'login': role, 'current': role}:
            raise TransitionError('Actual transition LOGIN identity differs')
        report = (await runtime_permissions.inspect(conn, role, reference='hosted_build', transition=context)
                  if profile == 'inventory' else await auxiliary_permissions.inspect(conn, transition=context))
        return report | {'actualLoginVerified': True, 'projectRef': context.project,
                         'transitionRecordSha256': context.record_sha256,
                         'operationalReleaseApproved': False}
    finally:
        await conn.close()
