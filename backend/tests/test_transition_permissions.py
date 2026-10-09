"""Independent record pins and exact cohorts; no hosted writes or credentials."""
import copy
import hashlib
import json
import unittest
from unittest.mock import AsyncMock, patch
import transition_permissions as transition
import runtime_permissions as runtime
import auxiliary_permissions as auxiliary

PROJECT = 'a' * 20
PAIRS = {kind: {phase: {'name': 'jaymax_build_' + kind + '_' + str(index + 1) * 12,
                      'oid': 101 + index}
               for phase, index in (('original', offset), ('replacement', offset + 1))}
         for kind, offset in (('inventory', 0), ('accounts', 2))}


def record(pairs=PAIRS, memberships=None):
    return {'format': 'jaymax-permission-overlap-v1', 'projectRef': PROJECT, 'phase': 'overlap',
            'rolePairs': pairs, 'baselinePolicySha256': 'b' * 64, 'membershipContract': memberships or []}


def verified(value=None, **overrides):
    raw = json.dumps(record() if value is None else value, sort_keys=True).encode()
    pins = dict(expected_sha256=hashlib.sha256(raw).hexdigest(), expected_project=PROJECT,
                expected_pairs=PAIRS, expected_baseline_policy_sha256='b' * 64, expected_memberships=[])
    return transition.verify_record(raw, **(pins | overrides))


class RecordGuards(unittest.TestCase):
    def test_verified_record_freezes_only_exact_same_profile_pairs(self):
        context = verified()
        for kind, pair in PAIRS.items():
            for value in pair.values():
                self.assertEqual(context.cohort(kind, value['name']), tuple(p['oid'] for p in pair.values()))
        identities = context.identities()
        identities['inventory']['replacement']['oid'] = 999
        self.assertEqual(context.identities(), PAIRS)
        with self.assertRaises(transition.TransitionError):
            context.cohort('accounts', PAIRS['inventory']['original']['name'])

    def test_independent_record_project_role_and_policy_pins_cannot_be_skipped(self):
        for pins in ({'expected_sha256': 'c' * 64}, {'expected_project': 'c' * 20},
                     {'expected_baseline_policy_sha256': 'c' * 64}, {'expected_pairs': {}},
                     {'expected_sha256': ''}, {'expected_project': ''}):
            with self.subTest(pins=pins), self.assertRaises(transition.TransitionError):
                verified(**pins)
        for key, value in (('phase', 'retired'), ('phase', 'staged'), ('format', 'unknown'), ('extra', True)):
            with self.subTest(field=key, value=value), self.assertRaises(transition.TransitionError):
                verified(record() | {key: value})

    def test_malformed_duplicate_public_reused_or_cross_profile_identities_hold(self):
        for key, value in (('oid', 0), ('oid', True), ('oid', 101), ('oid', 2**32),
                           ('name', PAIRS['accounts']['original']['name']),
                           ('name', PAIRS['inventory']['original']['name']), ('name', 'postgres')):
            pairs = copy.deepcopy(PAIRS)
            pairs['inventory']['replacement'][key] = value
            with self.subTest(field=key, value=value), self.assertRaises(transition.TransitionError):
                verified(record(pairs), expected_pairs=pairs)
        for raw in (b'[]', b'null', b'{', b'{"phase":"overlap","phase":"overlap"}'):
            with self.subTest(raw=raw), self.assertRaises(transition.TransitionError):
                transition.verify_record(raw, expected_sha256=hashlib.sha256(raw).hexdigest(),
                    expected_project=PROJECT, expected_pairs=PAIRS, expected_baseline_policy_sha256='b' * 64, expected_memberships=[])

    def test_endpoint_project_profile_and_routing_overrides_hold_before_connect(self):
        context = verified(); role = PAIRS['inventory']['replacement']['name']
        self.assertEqual(transition.endpoint_role(context, 'postgresql://' + role + '.' + PROJECT + '@aws-0-us-east-1.pooler.supabase.com/postgres', 'inventory'), role)
        direct = 'postgresql://' + role + '@db.' + PROJECT + '.supabase.co/postgres'
        self.assertEqual(transition.endpoint_role(context, direct, 'inventory'), role)
        for url, kind in ((direct, 'accounts'), (direct + '?host=elsewhere', 'inventory'),
                          (direct + '#elsewhere', 'inventory'), (direct.replace('/postgres', '/other'), 'inventory'),
                          (direct.replace(PROJECT, 'c' * 20), 'inventory'),
                          (direct.replace('.supabase.co', '.supabase.co.attacker.invalid'), 'inventory'),
                          (direct.replace('/postgres', ':6543/postgres'), 'inventory')):
            with self.subTest(kind=kind, url=url), self.assertRaises(transition.TransitionError):
                transition.endpoint_role(context, url, kind)

    def test_policies_preserve_default_singleton_and_accept_only_reviewed_overlap(self):
        for tables, prefix, oid in ((runtime.PUBLIC, 'runtime_candidate_', 101),
                                   ({name: auxiliary.VERBS for name in auxiliary.TABLES}, 'auxiliary_candidate_', 103)):
            for table, verbs in tables.items():
                for verb in verbs:
                    row = {'table_name': 'public.' + table, 'polname': prefix + verb.lower(),
                           'polcmd': {'SELECT': 'r', 'INSERT': 'a', 'UPDATE': 'w', 'DELETE': 'd'}[verb],
                           'polpermissive': True, 'polroles': [oid, oid + 1],
                           'using_expr': None if verb == 'INSERT' else 'true',
                           'check_expr': 'true' if verb in ('INSERT', 'UPDATE') else None}
                    self.assertTrue(transition.policy_valid(row, tables, prefix, (oid, oid + 1)))
                    self.assertTrue(transition.policy_valid(row | {'polroles': [oid + 1, oid]}, tables, prefix, (oid, oid + 1)))
                    self.assertFalse(transition.policy_valid(row, tables, prefix, (oid,)))
                    self.assertTrue(transition.policy_valid(row | {'polroles': [oid]}, tables, prefix, (oid,)))
        row = {'table_name': 'public.app_users', 'polname': 'auxiliary_candidate_select',
               'polcmd': 'r', 'polpermissive': True, 'polroles': [103, 104], 'using_expr': 'true', 'check_expr': None}
        for key, value in (('polroles', [0]), ('polroles', [103]), ('polroles', [103, 104, 101]),
                           ('polroles', [103, 103]), ('polroles', [True, 104]), ('polroles', [101, 104]),
                           ('polpermissive', False), ('polcmd', '*'), ('using_expr', 'false'),
                           ('check_expr', 'true'), ('polname', 'duplicate_permissive'),
                           ('table_name', 'public.staff_pins'), ('table_name', 'purchasing.app_users')):
            with self.subTest(field=key, value=value):
                self.assertFalse(transition.policy_valid(row | {key: value}, {'app_users': auxiliary.VERBS}, 'auxiliary_candidate_', (103, 104)))


class LiveIdentityGuards(unittest.IsolatedAsyncioTestCase):
    async def test_changed_oid_login_attributes_or_any_membership_hold(self):
        rows = [{'rolname': p['name'], 'oid': p['oid'], 'rolcanlogin': True, 'rolconnlimit': 6,
                 **{key: False for key in transition.FLAGS}} for pair in PAIRS.values() for p in pair.values()]
        conn = AsyncMock(); conn.fetch.side_effect = [rows, []]
        context = verified(); role = PAIRS['inventory']['original']['name']
        self.assertEqual(await transition.live_cohort(conn, context, 'inventory', role), (101, 102))
        for key, value in (('oid', 999), ('rolcanlogin', False), ('rolconnlimit', 7),
                           *((key, True) for key in transition.FLAGS)):
            changed = copy.deepcopy(rows); changed[-1][key] = value; conn.fetch.side_effect = [changed]
            with self.subTest(field=key), self.assertRaises(transition.TransitionError):
                await transition.live_cohort(conn, context, 'inventory', role)
        conn.fetch.side_effect = [rows, [{'roleid': 101, 'member': 102, 'grantor': 10,
            'member_name': PAIRS['inventory']['replacement']['name'], 'grantor_name': 'supabase_admin',
            'admin_option': False, 'inherit_option': False, 'set_option': True}]]
        with self.assertRaises(transition.TransitionError):
            await transition.live_cohort(conn, context, 'inventory', role)
        with self.assertRaises(transition.TransitionError):
            await transition.live_cohort(conn, record(), 'inventory', role)

    async def test_only_exact_independent_creator_membership_with_no_inherit_or_set_is_accepted(self):
        row = {'roleid': 101, 'member': 10, 'grantor': 11, 'member_name': 'postgres',
               'grantor_name': 'supabase_admin', 'admin_option': True, 'inherit_option': False, 'set_option': False}
        context = verified(record(memberships=[row]), expected_memberships=[row])
        roles = [{'rolname': p['name'], 'oid': p['oid'], 'rolcanlogin': True, 'rolconnlimit': 6,
                  **{key: False for key in transition.FLAGS}} for pair in PAIRS.values() for p in pair.values()]
        conn = AsyncMock(); conn.fetch.side_effect = [roles, [row]]
        role = PAIRS['inventory']['original']['name']
        self.assertEqual(await transition.live_cohort(conn, context, 'inventory', role), (101, 102))
        for key, value in (('member', 103), ('member_name', 'unreviewed'), ('grantor', 104),
                           ('inherit_option', True), ('set_option', True), ('admin_option', False)):
            changed = row | {key: value}
            with self.subTest(field=key), self.assertRaises(transition.TransitionError):
                verified(record(memberships=[changed]), expected_memberships=[changed])
        conn.fetch.side_effect = [roles, [row | {'member': 99}]]
        with self.assertRaises(transition.TransitionError):
            await transition.live_cohort(conn, context, 'inventory', role)
        with self.assertRaises(transition.TransitionError):
            verified(record(memberships=[row]), expected_memberships=[])

    async def test_wrong_endpoint_never_connects_and_failed_inspection_closes_own_client(self):
        context = verified(); role = PAIRS['inventory']['original']['name']
        with patch('asyncpg.connect', AsyncMock()) as connect:
            with self.assertRaises(transition.TransitionError):
                await transition.assess_url(context, 'postgresql://' + role + '@127.0.0.1/postgres', 'inventory')
            connect.assert_not_awaited()
        conn = AsyncMock(); conn.fetchrow.return_value = {'login': role, 'current': role}
        with patch('asyncpg.connect', AsyncMock(return_value=conn)), patch('db_tls.connection_tls', return_value=True), patch.object(
                runtime, 'inspect', AsyncMock(side_effect=transition.TransitionError('Invented held assessment'))):
            with self.assertRaises(transition.TransitionError):
                await transition.assess_url(context, 'postgresql://' + role + '@db.' + PROJECT + '.supabase.co/postgres', 'inventory')
            conn.close.assert_awaited_once()
