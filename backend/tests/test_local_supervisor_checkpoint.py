"""Real process loss, independent restart, compare-and-swap and gap holds."""
import asyncio
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
import local_supervisor_checkpoint as witness
import local_install_recovery as recovery
import local_parallel_install as local
import test_local_install_recovery as archives


class WitnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'witness.sqlite'
        self.run = str(uuid4()); self.pin = 'a'*64; self.head = 'b'*64
        self.state = witness.create(self.path, run_id=self.run, database=archives.DATABASE,
                                    archive_pin=self.pin, opening_head=self.head)

    def read(self):
        return witness.read(self.path, run_id=self.run, archive_pin=self.pin)

    def worker(self, command, exit_code, head='c'*64):
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('local_supervisor_checkpoint_worker.py')),
            command, str(self.path), self.run, self.pin, self.state['receiptSha256'], head],
            capture_output=True, timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(result.returncode, exit_code, result.stdout.decode(errors='replace'))
        return json.loads(result.stdout) if result.stdout else None

    def test_real_process_exit_before_and_after_commit_survives_fresh_process_read(self):
        self.worker('crash_before_commit', 71)
        fresh = self.worker('read', 0)
        self.assertNotEqual(fresh['processPid'], os.getpid()); self.assertEqual(fresh['checkpoint'], self.state)
        self.worker('crash_after_commit', 72)
        second = self.worker('read', 0)
        self.assertNotEqual(second['processPid'], fresh['processPid'])
        self.assertEqual(second['checkpoint']['journalHeadSha256'], 'c'*64)
        self.assertEqual(second['checkpoint']['sequence'], 1)
        self.assertFalse(second['checkpoint']['credentialsStored'])
        target = os.environ.get('LOCAL_SUPERVISOR_EVIDENCE_DIR')
        if target:
            path = Path(target); path.mkdir(exist_ok=True)
            (path/'witness-process-trial.json').write_text(json.dumps({
                'format': 'jaymax-supervisor-process-trial-v1', 'status': 'passed',
                'beforeCommitExitCode': 71, 'afterCommitExitCode': 72,
                'separateReaders': [fresh['processPid'], second['processPid']],
                'oldCheckpointRecoveredAfterRollback': True, 'newCheckpointRecoveredAfterCommit': True,
                'applicationDataStored': False, 'credentialsStored': False, 'hostedChanges': False,
                'wholeMachineCrashRecoveryProved': False, 'operationalReleaseApproved': False}, indent=2)+'\n', encoding='utf-8')

    def test_concurrent_stale_writers_cannot_overwrite_a_new_checkpoint(self):
        barrier = threading.Barrier(2)
        def writer(head):
            barrier.wait()
            try:
                return witness.advance(self.path, run_id=self.run, archive_pin=self.pin,
                    expected_receipt=self.state['receiptSha256'], journal_head=head)
            except witness.CheckpointHeld: return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(writer, ['c'*64, 'd'*64]))
        winners = [result for result in results if result]
        self.assertEqual(len(winners), 1); self.assertEqual(self.read(), winners[0])
        with self.assertRaises(witness.CheckpointHeld):
            witness.advance(self.path, run_id=self.run, archive_pin=self.pin,
                expected_receipt=self.state['receiptSha256'], journal_head='e'*64)
        self.assertEqual(self.read(), winners[0])

    def test_wrong_identity_pin_missing_store_or_duplicate_creation_holds(self):
        before = self.path.read_bytes()
        for values in ({'run_id': str(uuid4()), 'archive_pin': self.pin},
                       {'run_id': self.run, 'archive_pin': 'f'*64}):
            with self.subTest(values=list(values)), self.assertRaises(witness.CheckpointHeld):
                witness.read(self.path, **values)
        with self.assertRaises(witness.CheckpointHeld):
            witness.create(self.path, run_id=self.run, database=archives.DATABASE, archive_pin=self.pin, opening_head=self.head)
        missing = self.path.with_name('missing.sqlite')
        with self.assertRaises(witness.CheckpointHeld): witness.read(missing, run_id=self.run, archive_pin=self.pin)
        self.assertFalse(missing.exists()); self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaises(witness.CheckpointHeld):
            witness.create(witness.ROOT/'must-not-create.sqlite', run_id=self.run, database=archives.DATABASE,
                           archive_pin=self.pin, opening_head=self.head)
        self.assertFalse((witness.ROOT/'must-not-create.sqlite').exists())

    def test_source_change_damaged_chain_or_wrong_mode_holds(self):
        original = self.path.read_bytes()
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("UPDATE checkpoints SET head=?", ('c'*64,))
            conn.commit()
        with self.assertRaises(witness.CheckpointHeld): self.read()
        self.path.write_bytes(original)
        with patch.object(witness.Path, 'read_bytes', return_value=b'changed engine'):
            with self.assertRaises(witness.CheckpointHeld): self.read()
        with closing(sqlite3.connect(self.path)) as conn: conn.execute('PRAGMA journal_mode=WAL')
        with self.assertRaises(witness.CheckpointHeld): self.read()

    def test_gap_after_journal_write_before_witness_commit_holds_before_network(self):
        journal_path = self.path.with_name('journal.jsonl'); journal = local.Journal(journal_path, archives.DATABASE)
        archive = archives.archive_value(journal); archive_path = self.path.with_name('archive.json')
        raw = json.dumps(archive, sort_keys=True).encode(); archive_path.write_bytes(raw)
        self.pin = recovery.sha(raw)
        # Separate independent witness bootstrapped from the known opening actor checkpoint.
        self.path = self.path.with_name('gap.sqlite')
        self.state = witness.create(self.path, run_id=self.run, database=archives.DATABASE,
                                    archive_pin=self.pin, opening_head=journal.rows()[0]['sha256'])
        self.worker('journal_gap', 73, str(journal_path))
        before = journal_path.read_bytes()
        self.assertEqual(self.read(), self.state)
        with patch.object(recovery.asyncpg, 'connect') as connect:
            with self.assertRaises(local.RehearsalHeld):
                asyncio.run(witness.recover_from_witness(archives.URL, archive_path, journal_path, self.path,
                            run_id=self.run, archive_pin=self.pin))
            connect.assert_not_called()
        self.assertEqual(journal_path.read_bytes(), before)

    def test_persisted_latest_checkpoint_rejects_valid_truncated_journal_prefix(self):
        journal_path = self.path.with_name('journal.jsonl'); original = local.Journal(journal_path, archives.DATABASE)
        opening = journal_path.read_bytes()
        self.path = self.path.with_name('paired.sqlite')
        state = witness.create(self.path, run_id=self.run, database=archives.DATABASE,
                               archive_pin=self.pin, opening_head=original.rows()[0]['sha256'])
        paired = witness.CheckpointedJournal(journal_path, self.path, run_id=self.run, archive_pin=self.pin)
        paired.append('intent', {'step': 'create', 'before': self.head})
        self.assertEqual(self.read()['journalHeadSha256'], original.rows()[-1]['sha256'])
        self.assertEqual(self.read()['sequence'], state['sequence']+1)
        journal_path.write_bytes(opening)
        with self.assertRaises(local.RehearsalHeld):
            witness.CheckpointedJournal(journal_path, self.path, run_id=self.run, archive_pin=self.pin)
        self.assertEqual(journal_path.read_bytes(), opening)

    def test_recovery_uses_surviving_witness_and_persists_new_reconciliation(self):
        journal_path = self.path.with_name('recover-journal.jsonl')
        original = local.Journal(journal_path, archives.DATABASE)
        value = archives.archive_value(original); archive_path = self.path.with_name('recover-archive.json')
        raw = json.dumps(value, sort_keys=True).encode(); archive_path.write_bytes(raw)
        self.pin = recovery.sha(raw); self.path = self.path.with_name('recover.sqlite')
        witness.create(self.path, run_id=self.run, database=archives.DATABASE,
            archive_pin=self.pin, opening_head=original.rows()[0]['sha256'])
        paired = witness.CheckpointedJournal(journal_path, self.path, run_id=self.run, archive_pin=self.pin)
        paired.append('intent', {'step': 'create', 'before': local.digest(value['baseline'])})
        before = self.read()
        conn = AsyncMock()
        with patch.object(recovery.asyncpg, 'connect', AsyncMock(return_value=conn)), \
             patch.object(local.LocalInstaller, 'identity', AsyncMock()), \
             patch.object(local, 'snapshot', AsyncMock(return_value=value['baseline'])):
            controller, result = asyncio.run(witness.recover_from_witness(archives.URL, archive_path,
                journal_path, self.path, run_id=self.run, archive_pin=self.pin))
        conn.close.assert_awaited_once()
        self.assertEqual(result['state'], 'not_committed'); self.assertFalse(controller.held)
        self.assertEqual(controller.completed, [])
        self.assertIsInstance(controller.journal, witness.CheckpointedJournal)
        self.assertEqual(self.read()['sequence'], before['sequence']+1)
        self.assertEqual(self.read()['journalHeadSha256'], original.rows()[-1]['sha256'])
        self.assertEqual(result['supervisorCheckpointReceiptSha256'], self.read()['receiptSha256'])
        self.assertFalse(result['databaseMutationsDuringRecovery'])
