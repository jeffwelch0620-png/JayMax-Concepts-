"""Complete probe paths against an owned fictional disposable database only."""
import asyncio
from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import asyncpg
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/ops'))
import read_only_probe as probe
import test_batched_fingerprints as fixture
from readonly_snapshot import readonly_snapshot


@unittest.skipUnless(os.environ.get('NATIVE_PURCHASE_TEST_DSN'),'Dedicated disposable PostgreSQL required')
class ReadOnlyProbeDatabaseTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.BatchedFingerprintDatabaseTests.asyncSetUp
    cleanup = fixture.BatchedFingerprintDatabaseTests.cleanup
    fixtures = fixture.BatchedFingerprintDatabaseTests.fixtures
    relations = fixture.BatchedFingerprintDatabaseTests.relations

    def scope(self,sha=None):
        return {'inventorySha256':sha,'discoveryApproved':sha is None}

    async def test_complete_two_families_preserve_rows_catalog_sequence_and_independent_hash_formats(self):
        await self.fixtures()
        async with readonly_snapshot(self.conn):
            baseline=await fixture.original_columns(self.conn)
            original=await fixture._oracle_preservation(self.conn,baseline)
            backup=await fixture.backup.fingerprint(self.conn)
        captured={}
        orig=fixture.preservation.fingerprints_batched
        back=fixture.backup.fingerprint_batched
        async def original_call(*args,**kwargs):
            captured['original']=await orig(*args,**kwargs)
            return captured['original']
        async def backup_call(*args,**kwargs):
            captured['backup']=await back(*args,**kwargs)
            return captured['backup']
        with patch.object(fixture.preservation,'fingerprints_batched',side_effect=original_call), \
             patch.object(fixture.backup,'fingerprint_batched',side_effect=backup_call):
            result=await probe.calibration(self.conn,self.scope())
        self.assertTrue(result['coverageComplete'])
        self.assertEqual(captured,{'original':original,'backup':backup})
        self.assertEqual(result['originalCount'],len(baseline))
        self.assertEqual(result['backupCount'],len(backup['tables']))
        self.assertFalse(self.conn.is_in_transaction())
        async with readonly_snapshot(self.conn): self.assertEqual(await fixture.backup.fingerprint(self.conn),backup)
        self.assertTrue(all(result['metrics'][g]['queryCalls']>0 for g in probe.GROUPS))

    async def test_full_cursor_fallback_and_sequences_are_included_in_envelopes(self):
        await self.fixtures()
        observed=probe.Observed(self.conn)
        with patch.object(fixture.backup,'MAX_FINGERPRINT_AGGREGATE_BYTES',65):
            result=await probe.calibration(self.conn,self.scope(),observer=observed)
        self.assertTrue(result['coverageComplete'])
        self.assertGreater(result['metrics']['backup']['cursorEnvelopes'],1)
        self.assertTrue(all(r['outcome']=='completed' for r in observed.cursors))
        self.assertGreater(result['metrics']['backup']['cursorOperations'],250)
        self.assertFalse(self.conn.is_in_transaction())

    async def test_unknown_inventory_or_unapproved_discovery_refuses_before_hashing(self):
        await self.fixtures()
        for scope in (self.scope('a'*64),{'inventorySha256':None,'discoveryApproved':False}):
            with self.subTest(scope=scope),patch.object(fixture.preservation,'fingerprints_batched') as first:
                with self.assertRaises(probe.Held): await probe.calibration(self.conn,scope)
                first.assert_not_called()
            self.assertFalse(self.conn.is_in_transaction())
        result=await probe.calibration(self.conn,self.scope())
        repeat=await probe.calibration(self.conn,self.scope(result['scopeSha256']))
        self.assertEqual(result['inventory'],repeat['inventory'])

    async def test_missing_original_and_backup_catalog_or_relation_results_fail_closed(self):
        await self.fixtures()
        orig=fixture.preservation.fingerprints_batched; back=fixture.backup.fingerprint_batched
        for family in ('original','backup','catalog'):
            async def bad_original(*args,**kwargs):
                result=await orig(*args,**kwargs)
                if family=='original': result.pop(next(iter(result)))
                return result
            async def bad_backup(*args,**kwargs):
                result=await back(*args,**kwargs)
                result[{'backup':'tables','catalog':'catalog'}[family]].pop(next(iter(result[{'backup':'tables','catalog':'catalog'}[family]])))
                return result
            with self.subTest(family=family),patch.object(fixture.preservation,'fingerprints_batched',side_effect=bad_original), \
                 patch.object(fixture.backup,'fingerprint_batched',side_effect=bad_backup):
                with self.assertRaises(probe.Held): await probe.calibration(self.conn,self.scope())
            self.assertFalse(self.conn.is_in_transaction())

    async def test_snapshot_enforces_readonly_and_refuses_every_mutation_and_sequence_advance(self):
        await self.fixtures()
        before=await self.conn.fetchrow('SELECT last_value,is_called FROM public.test_only_sequence')
        for sql in ('INSERT INTO public.test_only_large VALUES(999)',
                    'CREATE TABLE public.test_only_forbidden(n int)',
                    "SELECT nextval('public.test_only_sequence')"):
            with self.subTest(sql=sql):
                with self.assertRaises(asyncpg.ReadOnlySQLTransactionError):
                    async with readonly_snapshot(self.conn): await self.conn.execute(sql)
                self.assertFalse(self.conn.is_in_transaction())
        self.assertEqual(await self.conn.fetchrow('SELECT last_value,is_called FROM public.test_only_sequence'),before)
        self.assertEqual(await self.conn.fetchval('SELECT count(*) FROM public.test_only_large'),250)

    async def test_timeout_cancel_and_resource_failure_rollback_without_retry(self):
        await self.fixtures()
        for failure in (TimeoutError('TEST ONLY private timeout'),asyncio.CancelledError(),probe.Held('resource')):
            with self.subTest(failure=type(failure).__name__), \
                 patch.object(fixture.preservation,'fingerprints_batched',side_effect=failure) as first, \
                 patch.object(fixture.backup,'fingerprint_batched') as second:
                with self.assertRaises(type(failure)): await probe.calibration(self.conn,self.scope())
                self.assertEqual(first.call_count,1); second.assert_not_called()
            self.assertFalse(self.conn.is_in_transaction())
            self.assertEqual(await self.conn.fetchval('SELECT 1'),1)

    async def test_observed_slow_query_holds_and_later_family_never_runs(self):
        await self.fixtures()
        with patch.dict(probe.LIMITS,observed=0),patch.object(fixture.backup,'fingerprint_batched') as second:
            with self.assertRaises(probe.Held): await probe.calibration(self.conn,self.scope())
            second.assert_not_called()
        # Outer start itself may have crossed the screen; closing the owned
        # connection is the execution boundary's responsibility in that case.
        if self.conn.is_in_transaction(): await self.conn.execute('ROLLBACK')
