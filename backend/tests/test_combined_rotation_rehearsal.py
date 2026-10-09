"""Credential changes fail closed and always return to the pinned originals."""
import unittest
from unittest.mock import AsyncMock, Mock, patch
import asyncpg
import combined_rotation_rehearsal as rehearsal

ROLES = {'inventory': 'jaymax_build_inventory_' + '1' * 12,
    'accounts': 'jaymax_build_accounts_' + '2' * 12}
EXPECTED = {ROLES['inventory']: 101, ROLES['accounts']: 102}
PROJECT = 'a' * 20
OLD = {key: 'postgresql://' + ROLES[kind] + '.' + PROJECT + ':' + 'x' * 64
    + '@aws-0-us-east-1.pooler.supabase.com:5432/postgres' for kind, key in rehearsal.rotation.KEYS.items()}
NEW = rehearsal.rotation.replacement_overlay(OLD, {'inventory': 'y' * 64, 'accounts': 'z' * 64})


class Gates(unittest.IsolatedAsyncioTestCase):
    async def test_recovery_refresh_verifies_both_paths_and_never_retries_transport(self):
        conn = Mock(close=AsyncMock())
        with patch.object(rehearsal, 'connect', AsyncMock(side_effect=[asyncpg.InvalidPasswordError(), conn, conn])) as connect, patch.object(rehearsal.asyncio, 'sleep', AsyncMock()):
            self.assertTrue(await rehearsal.fresh_both(OLD, ROLES, 'inventory', PROJECT, verify_refresh=True))
            self.assertEqual(connect.await_count, 3)
            self.assertEqual(conn.close.await_count, 2)
        with patch.object(rehearsal, 'connect', AsyncMock(side_effect=TimeoutError())) as connect, patch.object(rehearsal.asyncio, 'sleep', AsyncMock()) as sleep:
            with self.assertRaises(TimeoutError):
                await rehearsal.fresh_both(OLD, ROLES, 'inventory', PROJECT, verify_refresh=True)
            connect.assert_awaited_once()
            sleep.assert_not_called()
    def test_held_wrong_version_or_missing_recovery_prerequisite_cannot_qualify(self):
        base = {'format': 'jaymax-corroborated-pooler-comparison-v1',
            'denialContract': rehearsal.contract.CONTRACT,
            'status': 'passed_corroborated_pooler_denial_comparison', 'stage': 'complete',
            'roles': ROLES, 'bothRoleCorroboratedComparisonsPassed': True,
            'recoveryBaselinePreserved': True, 'ownerClosed': True}
        for key, value in (('format', 'old'), ('status', 'held'), ('denialContract', 'unknown'),
                ('roles', {}), ('stage', 'preflight'), ('recoveryBaselinePreserved', False),
                ('ownerClosed', False)):
            with self.subTest(key=key), self.assertRaises(rehearsal.RehearsalError):
                rehearsal.prerequisite(base | {key: value}, ROLES)
    async def test_missing_baseline_or_private_gate_never_connects(self):
        for flag in ('fullPreflightBaselineDurablySaved', 'privateAclVerified'):
            report = {'fullPreflightBaselineDurablySaved': True, 'privateAclVerified': True}
            report[flag] = False
            with self.subTest(flag=flag), patch.object(rehearsal, 'connect', AsyncMock()) as connect:
                with self.assertRaises(rehearsal.RehearsalError):
                    await rehearsal.roundtrip(Mock(), ROLES, EXPECTED, OLD, NEW, PROJECT, report, Mock())
                connect.assert_not_called()

    async def test_invalid_role_or_any_password_literal_never_reaches_sql(self):
        for roles, config in ((ROLES | {'inventory': 'postgres'}, NEW),
                (ROLES, NEW | {'AUXILIARY_DATABASE_URL': NEW['AUXILIARY_DATABASE_URL'].replace('z' * 64, "z'unsafe")})):
            owner = Mock(transaction=Mock(), execute=AsyncMock())
            with self.subTest(roles=roles), self.assertRaises(rehearsal.RehearsalError):
                await rehearsal.set_passwords(owner, roles, EXPECTED, config)
            owner.transaction.assert_not_called()
            owner.execute.assert_not_called()

    async def test_oid_change_prevents_every_password_statement(self):
        transaction = AsyncMock()
        owner = Mock(transaction=Mock(return_value=transaction), execute=AsyncMock(), fetchval=AsyncMock(side_effect=[101, 999]))
        with self.assertRaises(rehearsal.RehearsalError):
            await rehearsal.set_passwords(owner, ROLES, EXPECTED, NEW)
        self.assertEqual(owner.execute.await_count, 1)  # Bounded settings only.
        self.assertFalse(any('PASSWORD' in call.args[0] for call in owner.execute.await_args_list))

    async def test_rejected_password_requires_exact_password_denial(self):
        allowed = {'accepted': False, 'category': 'password_denied', 'errorType': 'InvalidPasswordError', 'sqlstate': '28P01'}
        for row in (allowed | {'accepted': True}, allowed | {'category': 'eauthquery_user_not_found'},
                allowed | {'sqlstate': 'XX000'}, {'accepted': False, 'category': 'unclassified'}):
            with self.subTest(row=row), patch.object(rehearsal.drain, 'classify', AsyncMock(return_value=row)):
                with self.assertRaises(rehearsal.RehearsalError):
                    await rehearsal.password_rejected('private', ROLES['inventory'])
        with patch.object(rehearsal.drain, 'classify', AsyncMock(return_value=allowed)):
            self.assertEqual(await rehearsal.password_rejected('private', ROLES['inventory']), allowed)

    async def test_refresh_has_three_attempt_bound_and_retries_only_password_denial(self):
        conn = Mock(close=AsyncMock())
        with patch.object(rehearsal, 'connect', AsyncMock(side_effect=[asyncpg.InvalidPasswordError(), conn])) as connect, patch.object(rehearsal.asyncio, 'sleep', AsyncMock()):
            await rehearsal.replacement_refresh('private', ROLES['inventory'])
            self.assertEqual(connect.await_count, 2)
            conn.close.assert_awaited_once()
        for error in (TimeoutError(), asyncpg.InternalServerError()):
            with self.subTest(error=type(error).__name__), patch.object(rehearsal, 'connect', AsyncMock(side_effect=error)) as connect, patch.object(rehearsal.asyncio, 'sleep', AsyncMock()) as sleep:
                with self.assertRaises(type(error)):
                    await rehearsal.replacement_refresh('private', ROLES['inventory'])
                connect.assert_awaited_once()
                sleep.assert_not_called()
        with patch.object(rehearsal, 'connect', AsyncMock(side_effect=asyncpg.InvalidPasswordError)) as connect, patch.object(rehearsal.asyncio, 'sleep', AsyncMock()):
            with self.assertRaises(asyncpg.InvalidPasswordError):
                await rehearsal.replacement_refresh('private', ROLES['inventory'])
            self.assertEqual(connect.await_count, 3)

    async def test_codec_setup_failure_closes_authenticated_client(self):
        conn = Mock(close=AsyncMock())
        with patch.object(rehearsal.drain, 'connect_role', AsyncMock(return_value=conn)), patch.object(rehearsal.db_pg, '_init_connection', AsyncMock(side_effect=RuntimeError())):
            with self.assertRaises(RuntimeError):
                await rehearsal.connect('private', ROLES['inventory'])
        conn.close.assert_awaited_once()


class Recovery(unittest.IsolatedAsyncioTestCase):
    def report(self):
        return {'fullPreflightBaselineDurablySaved': True, 'privateAclVerified': True, 'checks': []}

    async def test_ambiguous_password_transaction_still_restores_originals(self):
        report = self.report()
        conn = Mock(close=AsyncMock())
        with patch.object(rehearsal, 'connect', AsyncMock(return_value=conn)), patch.object(rehearsal, 'set_passwords', AsyncMock(side_effect=TimeoutError())), patch.object(rehearsal, 'recover', AsyncMock()) as recover:
            with self.assertRaises(TimeoutError):
                await rehearsal.roundtrip(Mock(), ROLES, EXPECTED, OLD, NEW, PROJECT, report, Mock())
        recover.assert_awaited_once()
        self.assertIs(recover.await_args.args[3], OLD)
        self.assertTrue(report['passwordMutationAttempted'])
        self.assertTrue(report['ownedClientsClosed'])
        self.assertEqual(report['exerciseErrorType'], 'TimeoutError')

    async def test_journal_failure_before_password_transaction_still_runs_recovery(self):
        report = self.report()
        conn = Mock(close=AsyncMock())
        with patch.object(rehearsal, 'connect', AsyncMock(return_value=conn)), patch.object(rehearsal, 'set_passwords', AsyncMock()) as set_passwords, patch.object(rehearsal, 'recover', AsyncMock()) as recover:
            with self.assertRaises(OSError):
                await rehearsal.roundtrip(Mock(), ROLES, EXPECTED, OLD, NEW, PROJECT, report, Mock(side_effect=OSError()))
        set_passwords.assert_not_called()
        recover.assert_awaited_once()

    async def test_old_password_acceptance_stops_before_pool_and_disable_tests(self):
        report = self.report()
        conn = Mock(close=AsyncMock(), fetchval=AsyncMock(return_value=1))
        with patch.object(rehearsal, 'connect', AsyncMock(return_value=conn)), patch.object(rehearsal, 'set_passwords', AsyncMock()), patch.object(rehearsal, 'replacement_refresh', AsyncMock()), patch.object(rehearsal, 'fresh_both', AsyncMock()), patch.object(rehearsal, 'rejected_both', AsyncMock(side_effect=rehearsal.RehearsalError('Fresh replaced-password denial held'))), patch.object(rehearsal, 'pools_and_accessors', AsyncMock()) as pools, patch.object(rehearsal.contract, 'compare_role', AsyncMock()) as compare, patch.object(rehearsal, 'recover', AsyncMock()) as recover:
            with self.assertRaises(rehearsal.RehearsalError):
                await rehearsal.roundtrip(Mock(), ROLES, EXPECTED, OLD, NEW, PROJECT, report, Mock())
        pools.assert_not_called()
        compare.assert_not_called()
        recover.assert_awaited_once()

    async def test_owned_disable_failure_stops_second_role_and_restores_passwords(self):
        report = self.report()
        conn = Mock(close=AsyncMock(), fetchval=AsyncMock(return_value=1))
        with patch.object(rehearsal, 'connect', AsyncMock(return_value=conn)), patch.object(rehearsal, 'set_passwords', AsyncMock()), patch.object(rehearsal, 'replacement_refresh', AsyncMock()), patch.object(rehearsal, 'fresh_both', AsyncMock()), patch.object(rehearsal, 'rejected_both', AsyncMock()), patch.object(rehearsal, 'pools_and_accessors', AsyncMock()), patch.object(rehearsal.drain, 'connect_role', AsyncMock(return_value=conn)), patch.object(rehearsal.contract, 'compare_role', AsyncMock(side_effect=rehearsal.drain.DrainTrialError('Pooler client closure not observed'))) as compare, patch.object(rehearsal, 'recover', AsyncMock()) as recover:
            with self.assertRaises(rehearsal.drain.DrainTrialError):
                await rehearsal.roundtrip(Mock(), ROLES, EXPECTED, OLD, NEW, PROJECT, report, Mock())
        compare.assert_awaited_once()
        self.assertEqual(compare.await_args.args[3], ROLES['accounts'])
        recover.assert_awaited_once()
        self.assertNotIn('rotationExercisePassed', report)

    async def test_success_also_restores_originals_after_both_role_tests(self):
        report = self.report()
        conn = Mock(close=AsyncMock(), fetchval=AsyncMock(return_value=1))
        events = []
        async def compare(*args):
            events.append(args[3])
        async def recover(*args):
            events.append('restore-originals')
        with patch.object(rehearsal, 'connect', AsyncMock(return_value=conn)), patch.object(rehearsal, 'set_passwords', AsyncMock()), patch.object(rehearsal, 'replacement_refresh', AsyncMock()), patch.object(rehearsal, 'fresh_both', AsyncMock()), patch.object(rehearsal, 'rejected_both', AsyncMock()), patch.object(rehearsal, 'pools_and_accessors', AsyncMock()), patch.object(rehearsal.drain, 'connect_role', AsyncMock(return_value=conn)), patch.object(rehearsal.contract, 'compare_role', side_effect=compare), patch.object(rehearsal, 'permissions', AsyncMock(return_value={})), patch.object(rehearsal, 'recover', side_effect=recover):
            await rehearsal.roundtrip(Mock(), ROLES, EXPECTED, OLD, NEW, PROJECT, report, Mock())
        self.assertEqual(events, [ROLES['accounts'], ROLES['inventory'], 'restore-originals'])
        self.assertTrue(report['rotationExercisePassed'])

    async def test_recovery_cannot_claim_pass_when_temporary_credentials_still_accepted(self):
        report = {}
        with patch.object(rehearsal, 'set_passwords', AsyncMock()), patch.object(rehearsal, 'fresh_both', AsyncMock(return_value=True)), patch.object(rehearsal, 'rejected_both', AsyncMock(side_effect=rehearsal.RehearsalError('Fresh replaced-password denial held'))):
            with self.assertRaises(rehearsal.RehearsalError):
                await rehearsal.recover(Mock(), ROLES, EXPECTED, OLD, NEW, PROJECT, report, Mock())
        self.assertNotIn('originalCredentialsRestoredOnBothPaths', report)
        self.assertNotIn('temporaryCredentialsRejectedOnBothPaths', report)
