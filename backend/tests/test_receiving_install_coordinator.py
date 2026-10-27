"""Actual proof validation with mocked database boundaries; never hosted calls."""
from copy import deepcopy
import asyncio
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import receiving_install_coordinator as coordinator
import receiving_install_evidence as evidence
import manager_handoff_install as install
import journal_backup_receipts as receipts
from application_backup_profiles import Held, canonical, digest
from test_receiving_install_evidence import legacy_files,post_files,matrix,closed_key


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup);self.root=Path(self.folder.name)
        self.a,self.k,self.r,self.e=legacy_files(self.root)
        self.url='postgresql://local_owner@127.0.0.1:5544/'+self.e['source']['database']
        self.core=dict(format=install.FORMAT,localOnly=True,applyAutomatically=False,
            target={k:self.e['source'][k] for k in ('host','port','user','database')},
            runtimeRole='fictional_runtime',accountsRole='fictional_accounts',sourceHashes=install.sources(),
            baseline={'facts':{'rows':{}},'ledger':{}},entries=[dict(version=str(20991026000001+i),name=n,body=b,bodySha256=digest(b.encode())) for i,(n,b) in enumerate(install.payloads('fictional_runtime'))])

    async def prepared(self):
        with patch.object(coordinator,'source_matches',AsyncMock()),patch.object(install,'prepare',AsyncMock(return_value=self.core)):
            return await coordinator.prepare(self.url,'fictional_runtime','fictional_accounts',
                ['20991026000001','20991026000002','20991026000003'],self.a,self.k,self.r,
                expected=self.e,expected_sha=digest(canonical(self.e)),consumers=matrix())

    async def applied(self,plan):
        if self.k.exists():self.k.unlink()
        with patch.object(coordinator,'source_matches',AsyncMock()),patch.object(install,'apply',AsyncMock(return_value={'status':'installed_local_only'})):
            return await coordinator.apply(self.url,plan,digest(canonical(plan)),self.a,self.k,self.r,custody_closeout=closed_key())

    async def test_remote_or_changed_proof_is_refused_before_database(self):
        for mode in ('remote','receipt','expected'):
            with self.subTest(mode=mode),patch.object(coordinator,'source_matches',AsyncMock()) as source:
                r=deepcopy(self.r);e=deepcopy(self.e);url=self.url;sha=digest(canonical(e))
                if mode=='remote':url='postgresql://owner@db.example.invalid/postgres'
                elif mode=='receipt':r['tablesMatched']=999
                else:e['sourceHashes']['backend/receiving_install_coordinator.py']='0'*64
                with self.assertRaises((Held,ValueError)):
                    await coordinator.prepare(url,'r','a',[],self.a,self.k,r,expected=e,expected_sha=sha,consumers=matrix())
                source.assert_not_awaited()

    async def test_plan_binds_consumer_matrix_and_detaches_mutable_inputs(self):
        plan=await self.prepared();self.e['source']['databaseOid']=999
        self.assertNotEqual(plan['source']['databaseOid'],999)
        coordinator.checked(plan,digest(canonical(plan)),self.url,active=True)
        for field in ('consumers','window','sourceHashes'):
            bad=deepcopy(plan);bad[field]={}
            with self.subTest(field=field),self.assertRaises(Held):coordinator.checked(bad,digest(canonical(plan)),self.url,active=True)

    async def test_rechecks_archive_and_reserve_before_apply(self):
        p=await self.prepared();self.a.write_bytes(b'TEST ONLY changed')
        self.k.unlink()
        with patch.object(install,'apply',AsyncMock()) as apply,self.assertRaises(Held):
            await coordinator.apply(self.url,p,digest(canonical(p)),self.a,self.k,self.r,custody_closeout=closed_key())
        apply.assert_not_awaited()

    async def test_unknown_ack_and_acknowledged_cleanup_are_not_blind_retry(self):
        p=await self.prepared()
        self.k.unlink()
        for error,status in ((install.Unknown('TEST ONLY unknown'),'commit_unknown_activation_held'),
                             (OSError('TEST ONLY path must not print'),'installed_reconciliation_required_activation_held')):
            if isinstance(error,OSError):error.commitAcknowledged=True
            with self.subTest(status=status),patch.object(coordinator,'source_matches',AsyncMock()),patch.object(install,'apply',AsyncMock(side_effect=error)) as apply:
                result=await coordinator.apply(self.url,p,digest(canonical(p)),self.a,self.k,self.r,custody_closeout=closed_key())
            self.assertEqual(result['status'],status);self.assertFalse(result['retryAuthorized'])
            self.assertNotIn('TEST ONLY',str(result));self.assertEqual(apply.await_count,1)

    async def test_failed_post_proof_holds_activation_without_reapplying(self):
        p=await self.prepared();installed=await self.applied(p);a,k,r,e=post_files(self.root,p['source']);a.write_bytes(b'TEST ONLY dropped')
        with patch.object(install,'apply',AsyncMock()) as apply,patch.object(install,'reconcile',AsyncMock()) as reconcile:
            result=await coordinator.finish(self.url,p,digest(canonical(p)),installed,digest(canonical(installed)),a,k,r,expected=e,expected_sha=digest(canonical(e)))
        self.assertEqual(result['status'],'installed_recovery_held');self.assertFalse(result['featureActivated'])
        apply.assert_not_awaited();reconcile.assert_not_awaited()

    async def test_distinct_post_proof_completes_only_local_transition(self):
        p=await self.prepared();installed=await self.applied(p);a,k,r,e=post_files(self.root,p['source'])
        with patch.object(install,'reconcile',AsyncMock(return_value={'outcome':'installed'})),patch.object(coordinator,'source_matches',AsyncMock()):
            result=await coordinator.finish(self.url,p,digest(canonical(p)),installed,digest(canonical(installed)),a,k,r,expected=e,expected_sha=digest(canonical(e)))
        self.assertEqual(result['status'],'verified_local_recovery_custody_closeout_pending')
        self.assertTrue(result['workingKeyDeletionStillRequired']);self.assertFalse(result['hostedExecutionApproved'])
        self.assertNotEqual(result['preExpectedSha256'],result['postExpectedSha256'])
        with self.assertRaises(Held):coordinator.closeout(result,digest(canonical(result)),k,closed_key())
        k.unlink();complete=coordinator.closeout(result,digest(canonical(result)),k,closed_key())
        self.assertEqual(complete['status'],'passed_local_transition_activation_held')
        self.assertFalse(complete['workingKeyDeletionStillRequired']);self.assertFalse(complete['forensicErasureVerified'])

    async def test_swapped_install_receipt_and_post_target_are_held_before_database(self):
        p=await self.prepared();installed=await self.applied(p);a,k,r,e=post_files(self.root,p['source'])
        for mode in ('installed','target'):
            v=deepcopy(installed);expected=deepcopy(e)
            if mode=='installed':v['ledgerEntries']=4
            else:expected['source']['databaseOid']+=1
            with self.subTest(mode=mode),patch.object(install,'reconcile',AsyncMock()) as reconcile:
                result=await coordinator.finish(self.url,p,digest(canonical(p)),v,digest(canonical(v)),a,k,r,expected=expected,expected_sha=digest(canonical(expected)))
            self.assertEqual(result['status'],'installed_recovery_held');reconcile.assert_not_awaited()

    async def test_fresh_post_window_does_not_reactivate_expired_pre_install_plan(self):
        p=await self.prepared()
        for name in ('captureWindow','verificationWindow'):
            p['preExpected'][name]={k:(receipts.instant(v)-timedelta(days=2)).isoformat() for k,v in p['preExpected'][name].items()}
        p['window']=p['preExpected']['captureWindow'];p['preExpectedSha256']=digest(canonical(p['preExpected']))
        sha=digest(canonical(p))
        with self.assertRaises(Held):coordinator.checked(p,sha,self.url,active=True)
        coordinator.checked(p,sha,self.url,active=False)
        installed=dict(format=coordinator.INSTALL_RECEIPT,status='installed_activation_held',planSha256=sha,
            preExpectedSha256=p['preExpectedSha256'],sourceHashes=p['sourceHashes'],source=p['source'],ledgerEntries=3,
            featureActivated=False,hostedExecutionApproved=False,retryAuthorized=False,operationalReleaseApproved=False)
        a,k,r,e=post_files(self.root,p['source'])
        with patch.object(install,'reconcile',AsyncMock(return_value={'outcome':'installed'})),patch.object(coordinator,'source_matches',AsyncMock()):
            result=await coordinator.finish(self.url,p,sha,installed,digest(canonical(installed)),a,k,r,expected=e,expected_sha=digest(canonical(e)))
        self.assertEqual(result['status'],'verified_local_recovery_custody_closeout_pending')

    async def test_pre_install_key_closeout_is_required_before_any_application(self):
        p=await self.prepared()
        with patch.object(coordinator,'source_matches',AsyncMock()) as source,patch.object(install,'apply',AsyncMock()) as apply:
            with self.assertRaises(Held):
                await coordinator.apply(self.url,p,digest(canonical(p)),self.a,self.k,self.r,custody_closeout=closed_key())
            self.k.unlink();bad=closed_key();bad['separateKeyAccessVerified']=False
            with self.assertRaises(Held):
                await coordinator.apply(self.url,p,digest(canonical(p)),self.a,self.k,self.r,custody_closeout=bad)
        source.assert_not_awaited();apply.assert_not_awaited()

    async def test_outer_timeout_after_engine_entry_is_unknown_before_entry_has_no_writes(self):
        p=await self.prepared();self.k.unlink()
        async def delay(*args,**kwargs):await asyncio.sleep(1)
        for stage in ('source','installer'):
            with self.subTest(stage=stage),patch.object(evidence,'window_budget',return_value=.05),\
                 patch.object(coordinator,'source_matches',AsyncMock(side_effect=delay if stage=='source' else None)),\
                 patch.object(install,'apply',AsyncMock(side_effect=delay)) as apply:
                result=await coordinator.apply(self.url,p,digest(canonical(p)),self.a,self.k,self.r,custody_closeout=closed_key())
            self.assertEqual(result['status'],'commit_unknown_activation_held' if stage=='installer' else 'installation_failed_activation_held')
            self.assertFalse(result['retryAuthorized'])
            self.assertEqual(apply.await_count,1 if stage=='installer' else 0)
