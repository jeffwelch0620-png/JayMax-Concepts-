"""Genuine worker exits, separate process recovery and populated Food Cost."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID
import local_parallel_install as local
import local_install_recovery as recovery
import hosted_committed_workflow as workflow
import actual_inventory_api as actual
import test_local_parallel_install_catalog as fixture


class RestartRecoveryCatalog(fixture.ParallelInstallerCatalog):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        try:
            self.workflow = await workflow.run(self.dsn)
            self.assertEqual(self.workflow['actualFoodCost'], '55.00')
            self.assertTrue(self.workflow['track1UnchangedAfterPrepWasteAndSalesContext'])
            self.controller = await local.LocalInstaller.prepare(self.dsn, self.journal, self.originals, self.replacements)
            await local.db_pg._init_connection(self.conn)
            self.report_before = await self.report()
            self.archive_path = Path(self.temp.name) / 'independent-baseline.json'
            self.archive_pin = await recovery.archive(self.controller, self.archive_path)
            target = Path(os.environ['LOCAL_PARALLEL_INSTALL_EVIDENCE_DIR'])
            target.mkdir(exist_ok=True)
            # Metadata and row digests only; retain the independently pinned
            # archive even if a worker holds and fixture teardown runs.
            (target / 'independent-baseline.json').write_bytes(self.archive_path.read_bytes())
            recovery.load_archive(self.archive_path, self.archive_pin, self.dsn)
            self.journal_pin = self.journal.rows()[0]['sha256']  # Independently created opening checkpoint.
            self.supervisor_checkpoint = Path(self.temp.name) / 'supervisor-checkpoints.jsonl'
            self.workers = []
        except BaseException:
            await self.asyncTearDown(); raise

    async def report(self):
        params = self.workflow['actualReportParams']
        async with self.conn.transaction(readonly=True):
            return await actual.period_report(self.conn, self.workflow['temporaryStore'],
                                              UUID(params['opening']), UUID(params['closing']))

    async def worker(self, command, expected_exit=0):
        args = [sys.executable, str(Path(__file__).with_name('local_install_recovery_worker.py')),
                command, self.dsn, str(self.archive_path), self.archive_pin, str(self.journal.path), self.journal_pin]
        result = await asyncio.to_thread(subprocess.run, args, capture_output=True, timeout=600,
                                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(result.returncode, expected_exit, result.stdout.decode(errors='replace'))
        messages = [json.loads(line) for line in result.stdout.splitlines()]
        checkpoints = [item for item in messages if item.get('event') == 'journal_checkpoint']
        for point in checkpoints:
            self.assertEqual(point['independentArchiveSha256'], self.archive_pin)
            self.assertNotEqual(point['processPid'], os.getpid())
            self.assertEqual(len(point['journalHeadSha256']), 64)
            with self.supervisor_checkpoint.open('ab') as stream:
                stream.write((json.dumps(point) + '\n').encode()); stream.flush(); os.fsync(stream.fileno())
            self.journal_pin = point['journalHeadSha256']  # Actor output, never learned from the journal/catalog.
        receipt = next((item for item in reversed(messages) if item.get('event') != 'journal_checkpoint'), None)
        self.workers.append({'action': command, 'exitCode': result.returncode, 'receipt': receipt})
        return receipt

    async def test_real_crashes_new_process_recovery_and_food_cost(self):
        baseline = self.controller.baseline
        self.assertGreater(sum(value['rows'] for key, value in baseline['rows'].items()
                               if key.startswith('actual_inventory.')), 0)
        self.assertEqual(self.report_before['actualFoodCost'], '55.00')
        self.assertEqual(self.report_before['netPurchaseCost'], '40.00')
        original_globals = (local.db_pg._pool, local.db_auxiliary._pool,
                            local.db_pg._retry_task, local.db_auxiliary._retry_task)
        archived_bytes = self.archive_path.read_bytes()
        await self.worker('crash_before_create_commit', 91)
        no_commit = await self.worker('recover')
        self.assertEqual(no_commit['state'], 'not_committed'); self.assertEqual(no_commit['completed'], [])
        self.assertEqual(await local.snapshot(self.conn), baseline)
        await self.worker('crash_after_create_commit', 92)
        # An independently introduced column privilege keeps the pending outcome
        # ambiguous. Recovery must not absorb it, revoke it or retry creation.
        account = self.originals['accounts']
        await self.conn.execute('GRANT SELECT(pin) ON public.staff_pins TO ' + account)
        held = await self.worker('recover')
        self.assertEqual(held['state'], 'ambiguous'); self.assertTrue(held['held'])
        self.assertTrue(await self.conn.fetchval("SELECT has_column_privilege($1,'public.staff_pins','pin','SELECT')", account))
        await self.conn.execute('REVOKE SELECT(pin) ON public.staff_pins FROM ' + account)
        committed = await self.worker('recover')
        self.assertEqual(committed['state'], 'committed'); self.assertEqual(committed['completed'], ['create'])
        pinned_oids = committed['replacementOids']
        await self.worker('crash_after_enable_commit', 92)
        enabled = await self.worker('recover')
        self.assertEqual(enabled['state'], 'committed')
        self.assertEqual(enabled['completed'], ['create', 'overlap', 'enable'])
        self.assertEqual(enabled['replacementOids'], pinned_oids)
        await self.worker('crash_after_restore_commit', 92)
        restored = await self.worker('recover')
        self.assertEqual(restored['state'], 'committed'); self.assertEqual(restored['completed'][-1], 'restore')
        journal_before = self.journal.path.read_bytes()
        unsafe = await self.worker('unsafe_disable', 3)
        self.assertEqual(unsafe['errorClass'], 'RehearsalHeld')
        self.assertEqual(self.journal.path.read_bytes(), journal_before)
        # A new process must actually verify original singleton pools again.
        await self.worker('finish')
        final = await self.worker('recover')
        self.assertEqual(final['state'], 'no_pending_verified')
        self.assertEqual(final['completed'], list(recovery.STEPS))
        self.assertEqual(final['replacementOids'], pinned_oids)
        live = await local.snapshot(self.conn)
        final_controller, _ = await recovery.recover(self.dsn, self.archive_path, self.archive_pin, self.journal.path, self.journal_pin)
        final_controller.preserve(live)
        self.assertEqual(await self.report(), self.report_before)
        self.assertEqual(live['rows'], baseline['rows']); self.assertEqual(live['ledger'], baseline['ledger'])
        self.assertEqual(live['sequences'], baseline['sequences'])
        self.assertEqual(self.archive_path.read_bytes(), archived_bytes)
        self.assertEqual((local.db_pg._pool, local.db_auxiliary._pool,
                          local.db_pg._retry_task, local.db_auxiliary._retry_task), original_globals)
        self.assertFalse(any(row['rolcanlogin'] for row in live['roles'] if row['oid'] in pinned_oids.values()))
        self.assertFalse(any(row['grantee'] in pinned_oids.values() for row in live['access']))
        child_pids = [entry['receipt']['processPid'] for entry in self.workers if entry['receipt']]
        self.assertTrue(all(pid != os.getpid() for pid in child_pids))
        self.assertEqual(len(child_pids), len(set(child_pids)))
        target = Path(os.environ['LOCAL_PARALLEL_INSTALL_EVIDENCE_DIR'])
        target.mkdir(exist_ok=True)
        receipt = {'format': 'jaymax-local-process-restart-trial-v1', 'status': 'passed',
                   'supervisorPid': os.getpid(), 'workers': self.workers,
                   'actualFoodCost': self.report_before['actualFoodCost'],
                   'foodPurchaseCost': self.report_before['netPurchaseCost'],
                   'nonemptyActualInventoryRows': sum(value['rows'] for key, value in baseline['rows'].items() if key.startswith('actual_inventory.')),
                   'actualReportHashPreserved': self.report_before['reportHash'],
                   'track1UnaffectedByPrepWasteSales': self.workflow['track1UnchangedAfterPrepWasteAndSalesContext'],
                   'taxAndFeeSourceAmountsRetainedSeparately': self.workflow['taxAndFeeSourceAmountsRetainedSeparately'],
                   'independentArchiveSha256': self.archive_pin, 'archiveBytesPreserved': True,
                   'rowsLedgerSequencesAndOriginalAccessPreserved': True,
                   'freshOriginalSingletonPoolsBeforeNOLOGIN': True,
                   'processRestartRecoveryProved': True, 'journal': self.journal.rows(),
                   'hostedChanges': False, 'hostedCapacityGatePassed': False,
                   'passwordAuthenticationProved': False, 'operationalReleaseApproved': False}
        (target / 'process-restart-trial.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
