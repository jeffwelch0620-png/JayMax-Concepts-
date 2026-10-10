"""Independent local recovery witness; metadata only, never application data.

SQLite FULL-synchronous transactions survive a worker/supervisor process exit.
This does not prove whole-machine power-loss durability or secure credentials.
The owning controller supplies the run ID, archive pin and opening journal hash
before mutation. No recovered journal/catalog supplies a replacement baseline.
"""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from uuid import UUID


class CheckpointHeld(RuntimeError):
    """Safe category only, without paths, URLs or raw database errors."""


FORMAT = 'jaymax-local-supervisor-checkpoint-v1'
MAX_BYTES = 16 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[1]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def identifier(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError()
    return value


def hash_value(value):
    if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value):
        raise ValueError()
    return value


def target(value):
    if not isinstance(value, str) or not re.fullmatch('native_purchase_test_[a-f0-9]{32}', value):
        raise ValueError()
    return value


def location(path):
    """A pre-existing, separate directory, never inside this repository."""
    path = Path(path).absolute()
    if (path.is_symlink() or path.parent.resolve() != path.parent
            or path.resolve().is_relative_to(ROOT.resolve()) or not path.parent.is_dir()):
        raise CheckpointHeld('Separate local witness location required')
    return path


def connection(path):
    # mode=rw cannot silently create a missing recovery witness.
    conn = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=2, isolation_level=None)
    conn.execute('PRAGMA synchronous=FULL')
    if conn.execute('PRAGMA journal_mode').fetchone()[0] != 'delete':
        conn.close(); raise CheckpointHeld('Witness durability mode differs')
    return conn


def _read(conn, run_id, archive_pin):
    if conn.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
        raise ValueError()
    contract = conn.execute('SELECT body FROM contract WHERE singleton=1').fetchall()
    if len(contract) != 1: raise ValueError()
    contract = json.loads(contract[0][0])
    if (set(contract) != {'format', 'runId', 'database', 'archiveSha256', 'openingJournalSha256', 'sourceSha256'}
            or contract['format'] != FORMAT or contract['runId'] != identifier(run_id)
            or contract['archiveSha256'] != hash_value(archive_pin)
            or contract['sourceSha256'] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()):
        raise ValueError()
    target(contract['database']); hash_value(contract['openingJournalSha256'])
    rows = conn.execute('SELECT sequence,previous,head,receipt FROM checkpoints ORDER BY sequence').fetchall()
    if not rows: raise ValueError()
    previous = '0' * 64
    for index, (sequence, prior, head, receipt) in enumerate(rows):
        hash_value(head)
        if (sequence != index or prior != previous
                or receipt != digest({'sequence': sequence, 'previous': prior, 'head': head,
                                     'runId': run_id, 'archiveSha256': archive_pin})
                or (index == 0 and head != contract['openingJournalSha256'])):
            raise ValueError()
        previous = receipt
    return {'format': FORMAT, 'runId': run_id, 'database': contract['database'],
            'archiveSha256': archive_pin, 'journalHeadSha256': rows[-1][2],
            'sequence': rows[-1][0], 'receiptSha256': rows[-1][3],
            'applicationDataStored': False, 'credentialsStored': False,
            'hostedChanges': False, 'operationalReleaseApproved': False}


def create(path, *, run_id, database, archive_pin, opening_head):
    """Exclusive creation from independently supplied pre-mutation pins."""
    try:
        identifier(run_id); target(database); hash_value(archive_pin); hash_value(opening_head)
        path = location(path)
        with path.open('xb'):
            pass
        conn = connection(path)
        try:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('CREATE TABLE contract(singleton INTEGER PRIMARY KEY CHECK(singleton=1),body TEXT NOT NULL)')
            conn.execute('CREATE TABLE checkpoints(sequence INTEGER PRIMARY KEY,previous TEXT NOT NULL,head TEXT NOT NULL,receipt TEXT NOT NULL)')
            contract = {'format': FORMAT, 'runId': run_id, 'database': database,
                        'archiveSha256': archive_pin, 'openingJournalSha256': opening_head,
                        'sourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
            conn.execute('INSERT INTO contract VALUES(1,?)', (json.dumps(contract, sort_keys=True),))
            receipt = digest({'sequence': 0, 'previous': '0' * 64, 'head': opening_head,
                              'runId': run_id, 'archiveSha256': archive_pin})
            conn.execute('INSERT INTO checkpoints VALUES(0,?,?,?)', ('0' * 64, opening_head, receipt))
            result = _read(conn, run_id, archive_pin)
            conn.execute('COMMIT')
            return result
        finally: conn.close()
    except (OSError, sqlite3.Error, ValueError, TypeError, AttributeError):
        # A partial initialization is retained and held, never repaired/reused.
        raise CheckpointHeld('Independent witness creation held') from None


def read(path, *, run_id, archive_pin):
    try:
        path = location(path)
        if not 0 < path.stat().st_size <= MAX_BYTES: raise ValueError()
        conn = connection(path)
        try:
            conn.execute('BEGIN')
            result = _read(conn, run_id, archive_pin)
            conn.execute('COMMIT')
            return result
        finally: conn.close()
    except (OSError, sqlite3.Error, ValueError, TypeError, AttributeError):
        raise CheckpointHeld('Independent witness read held') from None


def advance(path, *, run_id, archive_pin, expected_receipt, journal_head, _fault=None):
    """Compare-and-swap the actor's checkpoint; never derive it from a journal.

    Caller must stop its database work if this update holds. A journal/witness
    mismatch remains held for independent review; no auto trim or retry exists.
    """
    try:
        hash_value(expected_receipt); hash_value(journal_head)
        path = location(path)
        if not 0 < path.stat().st_size <= MAX_BYTES: raise ValueError()
        conn = connection(path)
        try:
            conn.execute('BEGIN IMMEDIATE')
            before = _read(conn, run_id, archive_pin)
            if before['receiptSha256'] != expected_receipt: raise ValueError()
            if before['journalHeadSha256'] == journal_head:
                conn.execute('COMMIT'); return before
            sequence = before['sequence'] + 1
            receipt = digest({'sequence': sequence, 'previous': expected_receipt, 'head': journal_head,
                              'runId': run_id, 'archiveSha256': archive_pin})
            conn.execute('INSERT INTO checkpoints VALUES(?,?,?,?)', (sequence, expected_receipt, journal_head, receipt))
            result = _read(conn, run_id, archive_pin)
            if _fault: _fault('before_commit')
            conn.execute('COMMIT')
            if _fault: _fault('after_commit')
            return result
        finally: conn.close()
    except (OSError, sqlite3.Error, ValueError, TypeError, AttributeError):
        raise CheckpointHeld('Independent witness update held') from None


class CheckpointedJournal:
    """Persist each fsynced journal append in the separately created witness."""
    def __init__(self, journal_path, witness_path, *, run_id, archive_pin):
        import local_install_recovery as recovery
        self.witness_path = witness_path; self.run_id = run_id; self.archive_pin = archive_pin
        self.checkpoint = read(witness_path, run_id=run_id, archive_pin=archive_pin)
        self.journal = recovery.ExistingJournal(journal_path, self.checkpoint['journalHeadSha256'])
        if self.journal.rows()[0]['data'] != {'database': self.checkpoint['database']}:
            raise CheckpointHeld('Witness and journal targets differ')
        self.path = self.journal.path

    @property
    def expected_head(self):
        return self.journal.expected_head

    def rows(self):
        return self.journal.rows()

    def append(self, event, data):
        self.journal.append(event, data)
        self.checkpoint = advance(self.witness_path, run_id=self.run_id, archive_pin=self.archive_pin,
            expected_receipt=self.checkpoint['receiptSha256'], journal_head=self.journal.expected_head)


async def recover_from_witness(url, archive_path, journal_path, witness_path, *, run_id, archive_pin):
    """Use persisted independent pins; a gap between files always holds."""
    import local_install_recovery as recovery
    state = read(witness_path, run_id=run_id, archive_pin=archive_pin)
    if recovery.local.local_target(url) != state['database']:
        raise CheckpointHeld('Witness target differs from requested recovery')
    controller, receipt = await recovery.recover(url, archive_path, archive_pin, journal_path,
                                                state['journalHeadSha256'])
    state = advance(witness_path, run_id=run_id, archive_pin=archive_pin,
                    expected_receipt=state['receiptSha256'], journal_head=receipt['journalHeadSha256'])
    controller.journal = CheckpointedJournal(journal_path, witness_path, run_id=run_id, archive_pin=archive_pin)
    receipt['supervisorCheckpointReceiptSha256'] = state['receiptSha256']
    receipt['wholeMachineCrashRecoveryProved'] = False
    return controller, receipt
