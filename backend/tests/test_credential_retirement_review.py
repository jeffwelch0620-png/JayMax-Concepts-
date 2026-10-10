"""Prevent the signal rehearsal from reaching unrelated or busy database clients."""
from datetime import datetime, timezone
import unittest
from unittest.mock import AsyncMock, Mock
import credential_retirement_review as review

ROLE = 'jaymax_build_inventory_0123456789ab'
LABEL = 'jaymax_retirement_probe_' + 'a' * 32
START = datetime(2026, 10, 9, tzinfo=timezone.utc)


def activity(**changes):
    return {'pid': 42, 'role_oid': 101, 'role': ROLE, 'database': 'postgres',
        'backend_start': START, 'state': 'idle', 'in_transaction': False,
        'backend_type': 'client backend', 'application_name': LABEL, 'lock_count': 0} | changes


class IdentityGuards(unittest.TestCase):
    def test_recorded_roles_must_be_distinct_and_restricted(self):
        account = 'jaymax_build_accounts_0123456789ab'
        roles = {'inventory':ROLE,'accounts':account}
        attrs = [{'rolname':name,'oid':index,'rolcanlogin':True,'rolconnlimit':6,
            'rolsuper':False,'rolbypassrls':False,'rolcreatedb':False,'rolcreaterole':False,
            'rolreplication':False,'rolinherit':False} for index,name in enumerate(roles.values(),101)]
        self.assertEqual(review.validate_roles(roles,attrs),{ROLE:101,account:102})
        for field,value in (('rolsuper',True),('rolbypassrls',True),('rolinherit',True),
                ('rolcanlogin',False),('rolconnlimit',-1),('oid',102)):
            changed = [dict(row) for row in attrs]
            changed[0][field] = value
            with self.subTest(field=field), self.assertRaises(review.RetirementReviewError):
                review.validate_roles(roles,changed)

    def test_owner_and_unknown_roles_cannot_be_selected(self):
        with self.assertRaises(review.RetirementReviewError):
            review.validate_roles({'inventory':'postgres','accounts':'authenticator'},[])
        with self.assertRaises(review.RetirementReviewError):
            review.validate_roles({'inventory':ROLE,'accounts':ROLE},[])

    def test_refuses_arbitrary_application_sessions_and_pid_reuse(self):
        for changes in ({'application_name': 'inventory_app'}, {'backend_start': START.replace(second=1)},
                {'role_oid': 102}, {'role': 'postgres'}, {'database': 'another_database'},
                {'backend_type': 'autovacuum worker'}):
            with self.subTest(changes=changes), self.assertRaises(review.RetirementReviewError):
                review.validate_probe(activity(**changes), {ROLE: 101}, ROLE, 42, START, LABEL, 99)

    def test_refuses_busy_transaction_locked_and_owner_clients(self):
        for changes in ({'state': 'active'}, {'in_transaction': True}, {'lock_count': 1}):
            with self.subTest(changes=changes), self.assertRaises(review.RetirementReviewError):
                review.validate_probe(activity(**changes), {ROLE: 101}, ROLE, 42, START, LABEL, 99)
        with self.assertRaises(review.RetirementReviewError):
            review.validate_probe(activity(), {ROLE: 101}, ROLE, 42, START, LABEL, 42)

    def test_public_evidence_excludes_arbitrary_labels_addresses_and_sql(self):
        value = activity(application_name='postgresql://secret', query='private invoice', client_addr='private address')
        result = str(review.public_activity([value], {'inventory': ROLE}))
        self.assertNotIn('secret', result)
        self.assertNotIn('invoice', result)
        self.assertNotIn('address', result)


class AsyncGuards(unittest.IsolatedAsyncioTestCase):
    def clients(self):
        client = Mock(is_closed=Mock(return_value=False))
        client.fetchrow = AsyncMock(return_value={'pid':42,'login':ROLE,'current':ROLE,
            'label':LABEL,'read_only':'on','started':START})
        owner = Mock(fetch=AsyncMock(return_value=[activity()]), fetchval=AsyncMock(side_effect=[99, True, False]))
        return owner, client

    async def test_unowned_client_never_reaches_signal(self):
        owner, client = self.clients()
        client.fetchrow.return_value['label'] = 'inventory_app'
        with self.assertRaises(review.RetirementReviewError):
            await review.signal_owned_probe(owner, client, {ROLE:101}, ROLE, LABEL)
        owner.fetchval.assert_not_called()

    async def test_busy_client_never_reaches_signal(self):
        owner, client = self.clients()
        owner.fetch.return_value = [activity(in_transaction=True)]
        with self.assertRaises(review.RetirementReviewError):
            await review.signal_owned_probe(owner, client, {ROLE:101}, ROLE, LABEL)
        self.assertEqual(owner.fetchval.await_count, 1)

    async def test_race_that_removes_candidate_is_held(self):
        owner, client = self.clients()
        owner.fetchval.side_effect = [99, None]
        with self.assertRaises(review.RetirementReviewError):
            await review.signal_owned_probe(owner, client, {ROLE:101}, ROLE, LABEL)
        self.assertEqual(owner.fetchval.await_count, 2)

    async def test_signal_requires_confirmed_absence(self):
        owner, client = self.clients()
        owner.fetchval.side_effect = [99, True, True]
        with self.assertRaises(review.RetirementReviewError):
            await review.signal_owned_probe(owner, client, {ROLE:101}, ROLE, LABEL)

    async def test_only_exact_probe_identity_enters_guarded_signal(self):
        owner, client = self.clients()
        result = await review.signal_owned_probe(owner, client, {ROLE:101}, ROLE, LABEL)
        self.assertTrue(result['backendAbsentConfirmed'])
        self.assertFalse(result['existingApplicationSessionsTargeted'])
        call = owner.fetchval.await_args_list[1]
        self.assertEqual(call.args[1:], (42, START, 101, ROLE, LABEL))
