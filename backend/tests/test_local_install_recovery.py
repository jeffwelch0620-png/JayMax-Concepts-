"""Independent archive pins and legal journal semantics before networking."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import local_install_recovery as recovery
import local_parallel_install as local
import test_parallel_rotation_review as originals

DATABASE = 'native_purchase_test_' + 'a' * 32
URL = 'postgresql://local_owner@127.0.0.1:55439/' + DATABASE
NEW = {'inventory': 'jaymax_build_inventory_' + '3' * 12,
       'accounts': 'jaymax_build_accounts_' + '4' * 12}
OIDS = {name: 201 + index for index, name in enumerate(NEW.values())}


def baseline():
    attrs, policies = originals.fixture()
    return {'roles': attrs, 'policies': policies, 'memberships': [], 'access': [],
            'rows': {'actual_inventory.count_snapshots': {'rows': 2, 'sha256': 'b' * 64}},
            'ledger': {}, 'settings': [], 'catalog': {'policies': []}, 'sequences': {},
            'columns': {}, 'ledgerColumns': []}


def archive_value(journal):
    before = baseline()
    return {'format': recovery.FORMAT, 'database': DATABASE, 'owner': 'local_owner',
            'baseline': before, 'plan': recovery.baseline_plan(before, originals.ROLES, NEW),
            'journalInitialSha256': journal.rows()[0]['sha256'],
            'sourceHashes': recovery.source_hashes(), 'originalActualProfilesVerified': True}


class RecoveryGuards(unittest.TestCase):
    def test_valid_record_prefix_cannot_replace_independent_latest_checkpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'journal.jsonl'; journal = local.Journal(path, DATABASE)
            opening = path.read_bytes()
            journal.append('intent', {'step': 'create', 'before': 'b' * 64})
            pin = journal.rows()[-1]['sha256']
            path.write_bytes(opening)  # Complete valid JSON/hash-chain prefix, not a torn record.
            with self.assertRaises(local.RehearsalHeld): recovery.ExistingJournal(path, pin)
            self.assertEqual(path.read_bytes(), opening)

    def test_archive_pin_owner_target_source_and_rendered_plan_are_independent(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = local.Journal(Path(folder) / 'journal.jsonl', DATABASE)
            value = archive_value(journal); path = Path(folder) / 'archive.json'
            raw = json.dumps(value, sort_keys=True).encode(); path.write_bytes(raw); pin = recovery.sha(raw)
            self.assertEqual(recovery.load_archive(path, pin, URL), value)
            for wrong in ('', 'f' * 64, None):
                with self.subTest(pin=wrong), self.assertRaises(local.RehearsalHeld):
                    recovery.load_archive(path, wrong, URL)
            for changes in ({'database': 'native_purchase_test_' + 'b' * 32}, {'owner': 'another_owner'},
                            {'sourceHashes': {}}, {'originalActualProfilesVerified': False}):
                altered = json.dumps(value | changes).encode(); path.write_bytes(altered)
                with self.subTest(keys=list(changes)), self.assertRaises(local.RehearsalHeld):
                    recovery.load_archive(path, recovery.sha(altered), URL)
            altered = copy.deepcopy(value); altered['plan']['reviewSql']['createNOLOGIN'] = ['DROP ROLE postgres;']
            raw = json.dumps(altered).encode(); path.write_bytes(raw)
            with self.assertRaises(local.RehearsalHeld): recovery.load_archive(path, recovery.sha(raw), URL)

    def test_reopening_preserves_bytes_and_torn_or_tampered_journal_holds(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'journal.jsonl'; journal = local.Journal(path, DATABASE)
            before = path.read_bytes(); pin = journal.rows()[-1]['sha256']; reopened = recovery.ExistingJournal(path, pin)
            self.assertEqual(path.read_bytes(), before); self.assertEqual(reopened.rows(), journal.rows())
            for raw in (before[:-1], before + b'{"incomplete":', before.replace(b'opened', b'intent')):
                path.write_bytes(raw)
                with self.subTest(raw_bytes=len(raw)), self.assertRaises(local.RehearsalHeld):
                    recovery.ExistingJournal(path, pin)
                self.assertEqual(path.read_bytes(), raw)

    def test_replay_tracks_committed_uncommitted_pending_and_ambiguous_states(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = local.Journal(Path(folder) / 'journal.jsonl', DATABASE); value = archive_value(journal)
            before = local.digest(value['baseline'])
            journal.append('intent', {'step': 'create', 'before': before})
            journal.append('expected', {'step': 'create', 'before': before, 'after': 'c' * 64, 'oids': OIDS})
            state = recovery.replay(journal.rows(), value)
            self.assertEqual(state['completed'], []); self.assertIsNotNone(state['pending'])
            journal.append('reconciled', {'step': 'create', 'state': 'ambiguous'})
            self.assertIsNotNone(recovery.replay(journal.rows(), value)['pending'])
            journal.append('reconciled', {'step': 'create', 'state': 'not_committed'})
            self.assertEqual(recovery.replay(journal.rows(), value)['oids'], {})
            journal.append('intent', {'step': 'create', 'before': before})
            journal.append('expected', {'step': 'create', 'before': before, 'after': 'd' * 64, 'oids': OIDS})
            journal.append('commit_unknown', {'step': 'create'})
            journal.append('reconciled', {'step': 'create', 'state': 'committed'})
            state = recovery.replay(journal.rows(), value)
            self.assertEqual(state['completed'], ['create']); self.assertEqual(state['oids'], OIDS)
            journal.append('intent', {'step': 'overlap', 'before': 'd' * 64})
            journal.append('expected', {'step': 'overlap', 'before': 'd' * 64, 'after': 'e' * 64, 'oids': OIDS})
            journal.append('acknowledged', {'step': 'overlap', 'state': 'committed'})
            self.assertEqual(recovery.replay(journal.rows(), value)['completed'], ['create', 'overlap'])

    def test_valid_hash_chain_cannot_authorize_illegal_stage_event_or_oid_adoption(self):
        bad_sequences = [
            [('intent', {'step': 'enable', 'before': 'BASE'})],
            [('intent', {'step': 'create', 'before': 'f' * 64})],
            [('acknowledged', {'step': 'create', 'state': 'committed'})],
            [('intent', {'step': 'create', 'before': 'BASE'}), ('acknowledged', {'step': 'create', 'state': 'committed'})],
            [('intent', {'step': 'create', 'before': 'BASE'}), ('expected', {'step': 'create', 'before': 'BASE', 'after': 'c' * 64, 'oids': {name: 101 for name in NEW.values()}})],
            [('intent', {'step': 'create', 'before': 'BASE'}), ('expected', {'step': 'create', 'before': 'BASE', 'after': 'c' * 64, 'oids': {NEW['inventory']: 101, NEW['accounts']: 202}})],
            [('intent', {'step': 'create', 'before': 'BASE'}), ('failed', {'step': 'create', 'state': 'rolled_back'}), ('reconciled', {'step': 'create', 'state': 'committed'})],
        ]
        for events in bad_sequences:
            with self.subTest(events=len(events)), tempfile.TemporaryDirectory() as folder:
                journal = local.Journal(Path(folder) / 'journal.jsonl', DATABASE); value = archive_value(journal)
                for event, data in events:
                    data = {key: local.digest(value['baseline']) if item == 'BASE' else item for key, item in data.items()}
                    journal.append(event, data)
                with self.assertRaises(local.RehearsalHeld): recovery.replay(journal.rows(), value)


class RecoveryBeforeNetworking(unittest.IsolatedAsyncioTestCase):
    async def test_bad_archive_pin_or_journal_semantics_hold_without_database_connection(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'journal.jsonl'; journal = local.Journal(path, DATABASE)
            value = archive_value(journal); archive = Path(folder) / 'archive.json'
            raw = json.dumps(value).encode(); archive.write_bytes(raw)
            with patch.object(recovery.asyncpg, 'connect') as connect:
                with self.assertRaises(local.RehearsalHeld):
                    await recovery.recover(URL, archive, 'f' * 64, path, journal.rows()[-1]['sha256'])
                journal.append('intent', {'step': 'enable', 'before': local.digest(value['baseline'])})
                with self.assertRaises(local.RehearsalHeld):
                    await recovery.recover(URL, archive, recovery.sha(raw), path, journal.rows()[-1]['sha256'])
                connect.assert_not_called()
