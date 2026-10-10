"""Bound revisions, per-connection verification, all-or-none preparation and cleanup."""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import connection_transition as startup
import transition_permissions as permissions
import db_pg
import db_auxiliary
import runtime_permissions
import auxiliary_permissions
import test_transition_permissions as records


def urls(phase='replacement'):
    return {kind: 'postgresql://' + pair[phase]['name'] + '.' + records.PROJECT
            + ':invented-revision-secret@aws-0-us-east-1.pooler.supabase.com:5432/postgres'
            for kind, pair in records.PAIRS.items()}


def revision(values=None):
    return startup.bind_revision(records.verified(), urls() if values is None else values,
                                 client_id='registered_backend', revision_id=str(uuid4()))


def passed(kind, context):
    return {'status': 'passed_local_candidate' if kind == 'inventory' else 'passed',
            'readOnly': True, 'policyMode': 'reviewed_overlap', 'issues': [],
            'transitionRecordSha256': context.record_sha256, 'operationalReleaseApproved': False,
            'catalogReference': 'hosted_build'}


class RevisionGuards(unittest.TestCase):
    def test_exact_pair_is_frozen_and_secrets_are_not_in_repr(self):
        values = urls(); bound = revision(values)
        for kind in permissions.PROFILES:
            self.assertEqual(bound.validate(values[kind], kind), records.PAIRS[kind]['replacement']['name'])
        self.assertNotIn('invented-revision-secret', repr(bound))
        self.assertNotIn('postgresql://', repr(bound))
        values['inventory'] += '?host=elsewhere'
        with self.assertRaises(permissions.TransitionError):
            bound.validate(values['inventory'], 'inventory')

    def test_wrong_project_profile_mixed_revision_or_shared_endpoint_holds(self):
        for change in ('wrong_project', 'wrong_profile', 'mixed_revision', 'different_port', 'different_host', 'query_override'):
            values = urls()
            if change == 'wrong_project': values['accounts'] = values['accounts'].replace(records.PROJECT, 'c' * 20)
            if change == 'wrong_profile': values['accounts'] = values['inventory']
            if change == 'mixed_revision': values['accounts'] = urls('original')['accounts']
            if change == 'different_port': values['accounts'] = values['accounts'].replace(':5432/', ':6543/')
            if change == 'different_host': values['accounts'] = values['accounts'].replace('aws-0-us-east-1', 'aws-1-us-east-1')
            if change == 'query_override': values['accounts'] += '?user=postgres'
            with self.subTest(change=change), self.assertRaises(permissions.TransitionError):
                revision(values)
        with self.assertRaises(permissions.TransitionError):
            startup.bind_revision(records.verified(), urls(), client_id='registered_backend', revision_id='unreviewed')
        local = {kind: 'postgresql://' + pair['replacement']['name'] + '@127.0.0.1:55439/native_purchase_test_' + 'a' * 32
                 for kind, pair in records.PAIRS.items()}
        bound = startup.bind_revision(records.verified(), local, client_id='local_rehearsal', revision_id=str(uuid4()), reference='local')
        self.assertEqual(bound.reference, 'local')
        for value in (local['inventory'].replace('/native_purchase_test_', '/operational_'), local['inventory'].replace('127.0.0.1', 'localhost'), local['inventory'] + '?host=remote'):
            with self.subTest(local=value), self.assertRaises(permissions.TransitionError):
                startup.bind_revision(records.verified(), local | {'inventory': value}, client_id='local_rehearsal', revision_id=str(uuid4()), reference='local')


class PreparationGuards(unittest.IsolatedAsyncioTestCase):
    async def test_every_physical_connection_in_both_constructors_is_verified(self):
        values = urls(); bound = revision(values)
        for kind, module in (('inventory', db_pg), ('accounts', db_auxiliary)):
            clients = []
            candidate = MagicMock(); candidate.close = AsyncMock()
            async def create(*args, **kwargs):
                self.assertEqual(kwargs['max_size'], 2)
                self.assertTrue(kwargs['ssl'].check_hostname)
                for _ in range(2):
                    conn = AsyncMock(); role = dict(bound.roles)[kind]
                    conn.fetchrow.return_value = {'login': role, 'current': role}; clients.append(conn)
                    await kwargs['init'](conn)
                return candidate
            inspector = runtime_permissions if kind == 'inventory' else auxiliary_permissions
            with patch.object(module.asyncpg, 'create_pool', side_effect=create), patch.object(
                    inspector, 'inspect', AsyncMock(return_value=passed(kind, bound.context))) as inspect:
                self.assertIs(await module._try_connect(values[kind], transition=bound), candidate)
                self.assertEqual(inspect.await_count, 2)
                for conn in clients:
                    conn.set_type_codec.assert_awaited_once()
                    conn.fetchrow.assert_awaited_once()

    async def test_wrong_binding_holds_before_network_and_permission_failure_closes_initialization(self):
        values = urls(); bound = revision(values)
        for kind, module in (('inventory', db_pg), ('accounts', db_auxiliary)):
            with patch.object(module.asyncpg, 'create_pool', AsyncMock()) as create, self.assertLogs(module.__name__, level='WARNING') as logs:
                self.assertIsNone(await module._try_connect(values[kind].replace('invented-revision-secret', 'invented-changed-secret'), transition=bound))
                create.assert_not_called()
                self.assertNotIn('secret', '\n'.join(logs.output))
        conn = AsyncMock(); role = dict(bound.roles)['inventory']; conn.fetchrow.return_value = {'login': role, 'current': role}
        for delta in ({'status': 'held'}, {'readOnly': False}, {'policyMode': 'single_role'},
                      {'transitionRecordSha256': 'c' * 64}, {'issues': ['invented drift']}, {'operationalReleaseApproved': True},
                      {'catalogReference': 'unreviewed'}):
            with self.subTest(delta=delta), patch.object(runtime_permissions, 'inspect', AsyncMock(return_value=passed('inventory', bound.context) | delta)):
                with self.assertRaises(permissions.TransitionError):
                    await startup.inspect_connection(conn, values['inventory'], 'inventory', bound)

    async def test_failed_peer_or_cancellation_closes_only_owned_pool_and_never_promotes(self):
        values = urls(); bound = revision(values)
        for error in (None, asyncio.CancelledError()):
            own = MagicMock(); own.close = AsyncMock()
            old = object()
            with self.subTest(cancelled=error is not None), patch.object(db_pg, '_pool', old), patch.object(db_auxiliary, '_pool', old), patch.object(
                    db_pg, '_try_connect', AsyncMock(return_value=own)), patch.object(db_auxiliary, '_try_connect', AsyncMock(return_value=None, side_effect=error)):
                with self.assertRaises(permissions.TransitionError if error is None else asyncio.CancelledError):
                    await startup.prepare_pair(bound, values)
                own.close.assert_awaited_once()
                self.assertIs(db_pg._pool, old); self.assertIs(db_auxiliary._pool, old)

    async def test_success_is_owned_nonpublished_and_cleanup_terminates_only_failed_pool(self):
        values = urls(); bound = revision(values)
        pools = [MagicMock(), MagicMock()]
        for pool in pools: pool.close = AsyncMock()
        with patch.object(db_pg, '_try_connect', AsyncMock(return_value=pools[0])), patch.object(db_auxiliary, '_try_connect', AsyncMock(return_value=pools[1])):
            result = await startup.prepare_pair(bound, values)
            receipt = result.receipt()
            self.assertFalse(receipt['globalPoolsChanged']); self.assertFalse(receipt['operationalReleaseApproved'])
            self.assertNotIn('invented-revision-secret', str(receipt))
            pools[1].close.side_effect = ValueError('invented private driver text')
            with self.assertRaises(permissions.TransitionError):
                await result.close()
            pools[1].terminate.assert_called_once(); pools[0].terminate.assert_not_called()
            self.assertTrue(result.receipt()['ownedPoolsClosed'])
            pools[0].close.assert_awaited_once()
            await result.close()

    async def test_any_mutated_url_or_unbound_context_is_held_before_either_pool(self):
        values = urls(); bound = revision(values)
        for revision_value, candidate_urls in ((bound, values | {'accounts': urls('original')['accounts']}), (records.verified(), values)):
            with self.subTest(bound=isinstance(revision_value, startup.ClientRevision)), patch.object(db_pg, '_try_connect', AsyncMock()) as primary, patch.object(db_auxiliary, '_try_connect', AsyncMock()) as secondary:
                with self.assertRaises(permissions.TransitionError):
                    await startup.prepare_pair(revision_value, candidate_urls)
                primary.assert_not_awaited(); secondary.assert_not_awaited()

    async def test_shutdown_cancellation_is_preserved_after_both_owned_pools_are_closed(self):
        bound = revision()
        pools = [MagicMock(), MagicMock()]
        for pool in pools: pool.close = AsyncMock()
        pools[1].close.side_effect = asyncio.CancelledError()
        owned = startup.PreparedPools(bound, *pools)
        with self.assertRaises(asyncio.CancelledError):
            await owned.close()
        pools[1].terminate.assert_called_once()
        pools[0].close.assert_awaited_once()
        self.assertTrue(owned.receipt()['ownedPoolsClosed'])
