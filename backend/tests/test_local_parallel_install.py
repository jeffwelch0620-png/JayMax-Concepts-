"""Loopback boundary and metadata journal fail-closed guards."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import local_parallel_install as installer


DATABASE = 'native_purchase_test_' + 'a' * 32
URL = 'postgresql://local_owner@127.0.0.1:55439/' + DATABASE


class LocalInstallerGuards(unittest.TestCase):
    def test_only_exact_disposable_loopback_target_is_allowed(self):
        self.assertEqual(installer.local_target(URL), DATABASE)
        for url in (URL.replace('127.0.0.1', 'db.real.supabase.co'),
                    URL.replace('127.0.0.1', 'localhost'), URL + '?sslmode=disable',
                    URL + '#override', URL.replace(DATABASE, 'postgres'),
                    URL.replace(DATABASE, 'native_purchase_test_control'),
                    URL.replace('local_owner@', 'local_owner:secret@'),
                    URL.replace(':55439', ''), URL.replace('postgresql:', 'https:')):
            with self.subTest(url=url), self.assertRaises(installer.RehearsalHeld):
                installer.local_target(url)

    def test_journal_fsynced_chain_is_exclusive_and_detects_corruption(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'journal.jsonl'
            with patch.object(installer.os, 'fsync', wraps=installer.os.fsync) as sync:
                journal = installer.Journal(path, DATABASE)
                journal.append('intent', {'step': 'create', 'before': 'b' * 64})
                journal.append('expected', {'step': 'create', 'before': 'b' * 64,
                    'after': 'c' * 64, 'oids': {'jaymax_build_inventory_' + 'a' * 12: 101}})
                self.assertEqual(sync.call_count, 4)
            self.assertEqual(len(journal.rows()), 3)
            original = path.read_bytes()
            with self.assertRaises(FileExistsError): installer.Journal(path, DATABASE)
            self.assertEqual(path.read_bytes(), original)
            lines = original.splitlines(); row = json.loads(lines[1]); row['data']['before'] = 'd' * 64
            path.write_bytes(lines[0] + b'\n' + json.dumps(row).encode() + b'\n' + lines[2] + b'\n')
            with self.assertRaises(installer.RehearsalHeld): journal.rows()
            with self.assertRaises(installer.RehearsalHeld): journal.append('commit_unknown', {'step': 'create'})

    def test_journal_excludes_arbitrary_sql_password_urls_and_unreviewed_events(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = installer.Journal(Path(folder) / 'journal.jsonl', DATABASE)
            for event, data in (('apply', {}), ('intent', {'url': URL}),
                                ('intent', {'step': 'ALTER ROLE postgres'}),
                                ('expected', {'after': 'password'}),
                                ('expected', {'oids': {'postgres': 10}}),
                                ('expected', {'oids': {'jaymax_build_accounts_' + 'b' * 12: True}})):
                with self.subTest(event=event, keys=list(data)), self.assertRaises(installer.RehearsalHeld):
                    journal.append(event, data)
            self.assertEqual(len(journal.rows()), 1)

    def test_only_exact_new_grantee_and_policy_to_entries_are_masked(self):
        value = {'roles': [{'rolname': 'original'}, {'rolname': 'replacement'}],
                 'access': [{'grantee': 10, 'grantor': 1}, {'grantee': 11, 'grantor': 1}],
                 'policies': [{'role_oids': [10, 11], 'using_expr': 'true'}],
                 'catalog': {'policies': [], 'relations': [{'acl': 'text', 'owner': 'original'}]},
                 'memberships': [], 'rows': {'actual_inventory.counts': 'a'}}
        result = installer.unchanged_projection(value, {'replacement'}, {11})
        self.assertEqual(result['access'], [{'grantee': 10, 'grantor': 1}])
        self.assertEqual(result['policies'], [{'role_oids': [10], 'using_expr': 'true'}])
        self.assertEqual(result['catalog']['relations'], [{'owner': 'original'}])
        self.assertEqual(len(value['roles']), 2)
        for field, changed in (('memberships', [{'member': 11}]),
                               ('rows', {'actual_inventory.counts': 'b'})):
            altered = value | {field: changed}
            self.assertNotEqual(installer.digest(result), installer.digest(
                installer.unchanged_projection(altered, {'replacement'}, {11})))
