"""TLS downgrade, endpoint bypass, pool budget and safe failure regressions."""
import asyncio
import os
import ssl
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import db_auxiliary
import db_pg
import db_tls

REMOTE = 'postgresql://role.project:synthetic-secret@aws-0.pooler.supabase.com:5432/postgres'


class TLSBoundaryTests(unittest.TestCase):
    def setUp(self):
        # Keep Windows runtime variables used to initialize OpenSSL.
        self.environment = patch.dict(os.environ, DATABASE_SSL_ROOT_CERT=str(db_tls.DEFAULT_CA))
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_remote_requires_certificate_and_hostname_even_with_disable_query(self):
        for url in (REMOTE, REMOTE + '?sslmode=disable'):
            context = db_tls.connection_tls(url)
            self.assertIsInstance(context, ssl.SSLContext)
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(context.check_hostname)
            self.assertTrue(context.get_ca_certs())

    def test_only_explicit_loopback_uses_plaintext(self):
        for host in ('127.0.0.1', '[::1]', 'localhost'):
            self.assertIs(db_tls.connection_tls('postgresql://test@' + host + '/test'), False)
        self.assertIsInstance(db_tls.connection_tls('postgresql://test@localhost.example/test'), ssl.SSLContext)

    def test_routing_overrides_cannot_bypass_tls_or_target_gate(self):
        for key in ('host', 'HOST', 'hostaddr', 'port', 'service', 'servicefile', 'user', 'dbname'):
            with self.assertRaises(ValueError):
                db_tls.connection_tls('postgresql://test@127.0.0.1/test?' + key + '=remote')

    def test_invalid_ca_configuration_never_falls_back(self):
        for value in ('', '/missing/synthetic-ca.pem'):
            with patch.dict(os.environ, DATABASE_SSL_ROOT_CERT=value):
                with self.assertRaises((ValueError, OSError)):
                    db_tls.connection_tls(REMOTE)


class PoolTLSBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_both_actual_constructors_use_verified_tls_and_bounded_pool(self):
        with patch.dict(os.environ, DATABASE_SSL_ROOT_CERT=str(db_tls.DEFAULT_CA)):
            for module in (db_pg, db_auxiliary):
                candidate = MagicMock()
                candidate.close = AsyncMock()
                candidate.acquire.return_value.__aenter__ = AsyncMock(return_value=object())
                candidate.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
                with patch.object(module.asyncpg, 'create_pool', AsyncMock(return_value=candidate)) as create, patch.object(
                        db_auxiliary.auxiliary_permissions, 'inspect', AsyncMock(return_value={'status': 'passed'})):
                    self.assertIs(await module._try_connect(REMOTE), candidate)
                    settings = create.call_args.kwargs
                    self.assertTrue(settings['ssl'].check_hostname)
                    self.assertEqual(settings['ssl'].verify_mode, ssl.CERT_REQUIRED)
                    self.assertEqual(settings['max_size'], 2)
                    self.assertEqual(settings['statement_cache_size'], 0)

    async def test_tls_verification_failure_has_no_plaintext_retry_or_secret_log(self):
        with patch.dict(os.environ, DATABASE_SSL_ROOT_CERT=str(db_tls.DEFAULT_CA)):
            for module in (db_pg, db_auxiliary):
                with patch.object(module.asyncpg, 'create_pool', AsyncMock(side_effect=ssl.SSLCertVerificationError(
                        'synthetic-secret'))) as create, self.assertLogs(module.__name__, level='WARNING') as logs:
                    self.assertIsNone(await module._try_connect(REMOTE))
                self.assertEqual(create.await_count, 1)
                self.assertNotIn('synthetic-secret', '\n'.join(logs.output))
                self.assertNotIn('Traceback', '\n'.join(logs.output))

    async def test_bad_ca_holds_both_pools_before_network_attempt(self):
        with patch.dict(os.environ, DATABASE_SSL_ROOT_CERT='/missing/synthetic-ca.pem'):
            for module in (db_pg, db_auxiliary):
                with patch.object(module.asyncpg, 'create_pool', AsyncMock()) as create:
                    self.assertIsNone(await module._try_connect(REMOTE))
                    create.assert_not_called()

    async def test_primary_shutdown_awaits_retry_cancellation(self):
        async def retry():
            await asyncio.Event().wait()
        task = asyncio.create_task(retry())
        await asyncio.sleep(0)
        with patch.multiple(db_pg, _pool=None, _retry_task=task):
            await db_pg.close_pool()
            self.assertTrue(task.cancelled())
            self.assertIsNone(db_pg._retry_task)
