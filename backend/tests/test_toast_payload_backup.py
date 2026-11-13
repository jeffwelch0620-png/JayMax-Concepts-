"""Monthly payload backup rules that need no database: months, file checks, id lists."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4
from cryptography.fernet import Fernet
import hosted_backup as backup
import toast_payload_backup as payloads

PROJECT = 'abcdefghijklmnopqrst'


def month_file(root, key, rows, *, month='2026-03', manifest_change=None):
    lines = [json.dumps(row, separators=(',', ':')).encode() for row in rows]
    raw = root / ('raw-' + uuid4().hex)
    raw.write_bytes(b''.join(line + b'\n' for line in lines))
    size, sha = backup.file_digest(raw)
    manifest = {'format': payloads.FORMAT, 'projectRef': PROJECT, 'table': payloads.TABLE, 'month': month,
                'rowFingerprintAlgorithm': backup.ROW_ALGORITHM, 'rows': len(lines),
                'rowsSha256': payloads.rows_digest(backup.digest(line) for line in lines),
                'archiveBytes': size, 'archiveSha256': sha, **(manifest_change or {})}
    path = root / ('payloads-' + uuid4().hex + '.jmax.enc')
    backup.write_stream_envelope(path, key, manifest, raw)
    return path


class MonthlyBackupTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.key = Fernet.generate_key()
        self.key_path = self.root / 'payloads.key'
        self.key_path.write_bytes(self.key)

    def tearDown(self):
        self.folder.cleanup()

    def row(self, day='2026-03-05'):
        return {'id': str(uuid4()), 'business_date': day, 'payload': {'note': 'TEST ONLY\nsecond line'}}

    def test_month_ranges_and_spans(self):
        self.assertEqual([str(d) for d in payloads.month_range('2026-12')], ['2026-12-01', '2027-01-01'])
        self.assertEqual(payloads.month_span('2025-11', '2026-02'), ['2025-11', '2025-12', '2026-01', '2026-02'])
        for bad in ('2026-13', '26-01', '2026-1', None, '2026-01-01'):
            with self.subTest(bad=bad), self.assertRaises(backup.BackupError):
                payloads.month_range(bad)
        with self.assertRaisesRegex(backup.BackupError, 'before'):
            payloads.month_span('2026-02', '2026-01')

    def test_a_good_file_reads_back_with_every_row(self):
        rows = [self.row(), self.row('2026-03-31')]
        manifest, read = payloads.read_month(month_file(self.root, self.key, rows), self.key_path, PROJECT)
        self.assertEqual(manifest['rows'], 2)
        self.assertEqual(set(read), {r['id'] for r in rows})

    def test_rows_that_do_not_match_the_manifest_or_month_are_refused(self):
        for rows, change, reason in (
                ([self.row('2026-04-01')], None, 'outside its month'),
                ([self.row()], {'rows': 2}, 'differ from its manifest'),
                ([self.row()], {'rowsSha256': '0' * 64}, 'differ from its manifest')):
            with self.subTest(reason=reason), self.assertRaisesRegex(backup.BackupError, reason):
                payloads.read_month(month_file(self.root, self.key, rows, manifest_change=change), self.key_path, PROJECT)
        row = self.row()
        with self.assertRaisesRegex(backup.BackupError, 'repeated'):
            payloads.read_month(month_file(self.root, self.key, [row, row]), self.key_path, PROJECT)
        for change in ({'table': 'public.anything'}, {'projectRef': 'zyxwvutsrqponmlkjihg'}, {'month': '2026-13'}):
            with self.subTest(change=change), self.assertRaisesRegex(backup.BackupError, 'authentication or manifest'):
                payloads.read_month(month_file(self.root, self.key, [self.row()], manifest_change=change), self.key_path, PROJECT)

    def test_a_monthly_file_is_not_accepted_as_a_main_backup(self):
        path = month_file(self.root, self.key, [self.row()])
        with self.assertRaisesRegex(backup.BackupError, 'authentication or manifest'):
            backup.decrypt_backup(path, self.key_path, PROJECT)

    def test_two_files_for_one_month_are_refused(self):
        files = [month_file(self.root, self.key, [self.row()]) for _ in range(2)]
        with self.assertRaisesRegex(backup.BackupError, 'Two files'):
            payloads.verify_months(files, self.key_path, PROJECT)

    def test_main_backup_id_list_must_match_its_fingerprint(self):
        ids = sorted(str(uuid4()) for _ in range(3))
        fact = {'rows': 3, 'idsSha256': backup.digest(''.join(i + '\n' for i in ids).encode()), 'rowsInSeparateBackups': True}
        manifest = {'tables': {payloads.TABLE: fact}, 'separateTableRowIds': {payloads.TABLE: ids}}
        self.assertEqual(payloads.wanted_ids(manifest), set(ids))
        for change in ({'separateTableRowIds': {payloads.TABLE: ids[:2]}},
                       {'separateTableRowIds': {payloads.TABLE: ids + ids[:1]}},
                       {'separateTableRowIds': {payloads.TABLE: ids[:2] + ['not-an-id']}},
                       {'tables': {payloads.TABLE: {**fact, 'rowsInSeparateBackups': False}}}):
            with self.subTest(change=list(change)), self.assertRaisesRegex(backup.BackupError, 'does not match'):
                payloads.wanted_ids(manifest | change)
