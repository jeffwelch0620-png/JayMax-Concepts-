"""Strict denial classification and restoration after controlled NOLOGIN failure."""
from datetime import datetime,timezone
import unittest
from unittest.mock import AsyncMock,Mock,patch
import asyncpg
import pooler_drain_trial as trial

ROLE='jaymax_build_inventory_0123456789ab'
LABEL='jaymax_retirement_probe_'+'a'*32


class SessionSetup(unittest.IsolatedAsyncioTestCase):
    def client(self):
        return Mock(fetchrow=AsyncMock(return_value={'login':ROLE,'current':ROLE}),
            execute=AsyncMock(),fetchval=AsyncMock(side_effect=[LABEL,'on']),close=AsyncMock())

    async def test_explicit_settings_are_acknowledged_even_when_startup_settings_ignored(self):
        conn=self.client()
        trust=object()
        with patch.object(trial.asyncpg,'connect',AsyncMock(return_value=conn)) as connect,patch.object(trial,'connection_tls',return_value=trust):
            result=await trial.connect_role('private-url',ROLE,LABEL)
        self.assertIs(result,conn)
        self.assertIs(connect.await_args.kwargs['ssl'],trust)
        conn.execute.assert_awaited_once_with('SET default_transaction_read_only=on')
        self.assertEqual(conn.fetchval.await_args_list[0].args,("SELECT set_config('application_name',$1,false)",LABEL))
        self.assertEqual(conn.fetchval.await_args_list[1].args,('SHOW transaction_read_only',))

    async def test_wrong_identity_is_closed_without_adjusting_session(self):
        conn=self.client()
        conn.fetchrow.return_value={'login':'postgres','current':'postgres'}
        with patch.object(trial.asyncpg,'connect',AsyncMock(return_value=conn)),patch.object(trial,'connection_tls',return_value=object()):
            with self.assertRaises(trial.DrainTrialError):await trial.connect_role('private-url',ROLE,LABEL)
        conn.execute.assert_not_called()
        conn.close.assert_awaited_once()

    async def test_unacknowledged_read_only_mode_is_closed_and_held(self):
        conn=self.client()
        conn.fetchval.side_effect=['off']
        with patch.object(trial.asyncpg,'connect',AsyncMock(return_value=conn)),patch.object(trial,'connection_tls',return_value=object()):
            with self.assertRaises(trial.DrainTrialError):await trial.connect_role('private-url',ROLE)
        conn.close.assert_awaited_once()

    async def test_session_setup_error_closes_connection(self):
        conn=self.client()
        conn.execute.side_effect=asyncpg.InsufficientPrivilegeError('private driver detail')
        with patch.object(trial.asyncpg,'connect',AsyncMock(return_value=conn)),patch.object(trial,'connection_tls',return_value=object()):
            with self.assertRaises(asyncpg.InsufficientPrivilegeError):await trial.connect_role('private-url',ROLE,LABEL)
        conn.close.assert_awaited_once()


class DenialClassification(unittest.IsolatedAsyncioTestCase):
    async def classify(self,error):
        with patch.object(trial,'connect_role',side_effect=error):
            return await trial.classify('private-url',ROLE)

    async def test_transport_and_unrelated_authorization_errors_never_qualify(self):
        for error in (TimeoutError('private token'),OSError('private URL'),
                asyncpg.InvalidAuthorizationSpecificationError('another authorization problem')):
            result=await self.classify(error)
            self.assertEqual(result['category'],'unclassified')
            self.assertNotIn('private',str(result))

    async def test_known_native_denials_are_classified(self):
        login=await self.classify(asyncpg.InvalidAuthorizationSpecificationError('role is not permitted to log in'))
        password=await self.classify(asyncpg.InvalidPasswordError('private password'))
        self.assertEqual(login['category'],'login_not_permitted')
        self.assertEqual(password['category'],'password_denied')
        self.assertNotIn('private password',str(password))

    async def test_lookup_error_is_evidence_not_native_denial(self):
        lookup=await self.classify(asyncpg.InternalServerError('(EAUTHQUERY) user not found in the database'))
        arbitrary=await self.classify(asyncpg.InternalServerError('unrelated private diagnostic'))
        self.assertEqual(lookup['category'],'eauthquery_user_not_found')
        self.assertEqual(arbitrary['category'],'unclassified')

    async def test_accepted_fresh_client_is_closed_and_never_denial(self):
        conn=Mock(close=AsyncMock())
        with patch.object(trial,'connect_role',AsyncMock(return_value=conn)):
            result=await trial.classify('private-url',ROLE)
        conn.close.assert_awaited_once()
        self.assertTrue(result['accepted'])


class Restoration(unittest.IsolatedAsyncioTestCase):
    async def test_owner_and_injected_identifiers_never_reach_disable(self):
        owner=Mock(execute=AsyncMock())
        for role in ('postgres','authenticator','jaymax_build_inventory_0123456789ab" LOGIN;'):
            with self.subTest(role=role),self.assertRaises(trial.DrainTrialError):
                await trial.compare_role(owner,Mock(),{role:101},role,LABEL,'direct','pooler','other',[],{},Mock())
        owner.execute.assert_not_called()

    def fixtures(self):
        owner=Mock(execute=AsyncMock(),fetchval=AsyncMock(side_effect=[101,False,True]))
        client=Mock(close=AsyncMock(),is_closed=Mock(return_value=True))
        prepare=AsyncMock(return_value={'role':ROLE,'pid':42,'backendStart':datetime.now(timezone.utc).isoformat()})
        return owner,client,prepare

    async def test_unverified_pooler_identity_cannot_disable_login(self):
        owner,client,_=self.fixtures()
        with patch.object(trial,'prepare_owned',AsyncMock(side_effect=trial.DrainTrialError('identity held'))):
            with self.assertRaises(trial.DrainTrialError):
                await trial.compare_role(owner,client,{ROLE:101},ROLE,LABEL,'direct','pooler','other',[],{},Mock())
        owner.execute.assert_not_called()

    async def test_signal_failure_still_restores_login(self):
        owner,client,prepare=self.fixtures()
        with patch.object(trial,'prepare_owned',prepare),patch.object(trial,'classify',AsyncMock(return_value={'accepted':False,'category':'login_not_permitted'})),patch.object(trial.review,'signal_owned_probe',AsyncMock(side_effect=RuntimeError('signal failed'))):
            with self.assertRaises(RuntimeError):
                await trial.compare_role(owner,client,{ROLE:101},ROLE,LABEL,'direct','pooler','other',[],{},Mock())
        self.assertEqual([call.args[0] for call in owner.execute.await_args_list],['ALTER ROLE "'+ROLE+'" NOLOGIN','ALTER ROLE "'+ROLE+'" LOGIN'])
        client.close.assert_awaited()

    async def test_fresh_acceptance_after_signal_is_held_and_restored(self):
        owner,client,prepare=self.fixtures()
        results=[{'accepted':False,'category':'login_not_permitted'},{'accepted':True,'category':'fresh_client_accepted'}]
        check={}
        with patch.object(trial,'prepare_owned',prepare),patch.object(trial,'classify',AsyncMock(side_effect=results)),patch.object(trial.review,'signal_owned_probe',AsyncMock(return_value={'backendAbsentConfirmed':True})),patch.object(trial.asyncio,'sleep',AsyncMock()):
            with self.assertRaises(trial.DrainTrialError):
                await trial.compare_role(owner,client,{ROLE:101},ROLE,LABEL,'direct','pooler','other',[],check,Mock())
        self.assertNotIn('strictOwnedDrainComparisonPassed',check)
        self.assertTrue(check['ownerConfirmsLoginRestored'])

    async def test_journal_failure_before_mutation_never_disables_login(self):
        owner,client,prepare=self.fixtures()
        with patch.object(trial,'prepare_owned',prepare):
            with self.assertRaises(OSError):
                await trial.compare_role(owner,client,{ROLE:101},ROLE,LABEL,'direct','pooler','other',[],{},Mock(side_effect=OSError('journal unavailable')))
        owner.execute.assert_not_called()
