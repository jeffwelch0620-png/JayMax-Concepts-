"""Fictional v2 evidence cannot satisfy a legacy scope or unrelated window."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import unittest
from unittest.mock import patch

from application_backup_profiles import Held,RECEIVING7,canonical,digest
import journal_backup_receipts as receipts

POLICY={'extensions':[],'authFunctions':[]}


def binding():
    now=datetime.now(timezone.utc)
    return dict(profile='receiving7',profileSha256=RECEIVING7.sha256,
        sourceBinding=digest(canonical(dict(projectRef='abcdefghijklmnopqrst',host='db.abcdefghijklmnopqrst.supabase.co',
                                         port=5432,database='postgres',user='postgres'))),
        window=dict(startsAt=(now-timedelta(seconds=20)).isoformat(),expiresAt=(now+timedelta(minutes=20)).isoformat()),
        sourceHashes=receipts.source_hashes(),dependencyPolicySha256=digest(canonical(POLICY)))


def packet(b=None,action='export',policy=None):
    b=b or binding()
    return canonical(dict(format=receipts.PACKET_FORMAT,action=action,projectRef='abcdefghijklmnopqrst',
        binding=b,dependencyPolicy=POLICY if policy is None else policy,executionWindow=b['window'],
        restoreTargetSha256=None if action=='export' else digest(b'TEST ONLY owned target record')))


class ReceiptTests(unittest.TestCase):
    def test_exact_packet_pins_source_scope_and_window(self):
        raw=packet()
        self.assertEqual(receipts.packet(raw,digest(raw),'export')['binding']['profile'],'receiving7')

    def test_changed_digest_source_profile_window_and_policy_refuse(self):
        for change in ('digest','source','profile','scope','window','dependency','action','nan','duplicate','size','project'):
            with self.subTest(change=change),self.assertRaises(Held):
                b=binding(); raw=packet(b); sha=digest(raw)
                if change=='digest': sha='0'*64
                elif change=='source': b['sourceHashes']['backend/hosted_journal_backup.py']='0'*64;raw=packet(b);sha=digest(raw)
                elif change=='profile': b['profile']='legacy6';raw=packet(b);sha=digest(raw)
                elif change=='scope': b['sourceHashes'].pop('backend/native_backup.py');raw=packet(b);sha=digest(raw)
                elif change=='window': b['window']['expiresAt']=b['window']['startsAt'];raw=packet(b);sha=digest(raw)
                elif change=='dependency': raw=packet(b,policy={'extensions':[{}],'authFunctions':[]});sha=digest(raw)
                elif change=='action': raw=packet(b,action='verify-restore');sha=digest(raw)
                elif change=='nan': raw=b'{"x":NaN}';sha=digest(raw)
                elif change=='duplicate': raw=b'{"format":1,"format":2}';sha=digest(raw)
                elif change=='size': raw=b'x'*(256*1024+1);sha=digest(raw)
                elif change=='project':
                    import json
                    p=json.loads(raw);p['projectRef']='zyxwvutsrqponmlkjihg';raw=canonical(p);sha=digest(raw)
                receipts.packet(raw,sha,'export')

    def test_restore_packet_has_a_new_execution_window_without_relabelling_capture(self):
        b=binding(); b['window']={k:(receipts.instant(v)-timedelta(days=2)).isoformat() for k,v in b['window'].items()}
        import json
        p=json.loads(packet(b,action='verify-restore'));p['executionWindow']=binding()['window']
        raw=canonical(p)
        got=receipts.packet(raw,digest(raw),'verify-restore')
        self.assertEqual(got['binding'],b)
        with self.assertRaises(Held): receipts.packet(raw,digest(raw),'export')

    def test_independent_artifact_and_restored_phase_required(self):
        b=binding(); manifest=dict(binding=b,archiveSha256=digest(b'archive'),facts={'tables':{k:{} for k in (
            'supabase_migrations.schema_migrations','operations.store_settings','operations.handoff_notes',
            'operations.handoff_note_revisions','operations.handoff_command_receipts')},'catalog':{'x':{}}})
        r=receipts.receipt(manifest,digest(b'encrypted'),restored=True,verification_window=b['window'],topology='same_cluster')
        args=dict(expected=b,encrypted_sha=digest(b'encrypted'),archive_sha=digest(b'archive'),
                  facts_sha=digest(canonical(manifest['facts'])),verification_window=b['window'],expected_receipt_sha=digest(canonical(r)))
        self.assertEqual(receipts.validate(r,**args),r)
        for change in ('profile','schemas','binding','encryptedSha256','archiveSha256','factsSha256',
                       'cleanupVerified','majorVersionMatched','managedRecoveryVerified','status','tables',
                       'verificationWindow','ownershipMode','migrationLedgerCovered','journalTablesCovered'):
            bad=deepcopy(r)
            bad[change]=('legacy6' if change=='profile' else [] if change=='schemas' else {} if change in ('binding','verificationWindow')
                else False if change in ('cleanupVerified','majorVersionMatched','migrationLedgerCovered','journalTablesCovered') else True if change=='managedRecoveryVerified'
                else 0 if change=='tables' else '0'*64)
            with self.subTest(field=change),self.assertRaises(Held): receipts.validate(bad,**args)
            with self.subTest(semantics=change),self.assertRaises(Held): receipts.validate(bad,**(args|{'expected_receipt_sha':digest(canonical(bad))}))

    def test_future_unknown_or_overlong_window_refuses(self):
        for w in ({},dict(startsAt='2026-10-25',expiresAt='2026-10-26'),
                  dict(startsAt='2099-01-01T00:00:00+00:00',expiresAt='2099-01-01T00:10:00+00:00'),
                  dict(startsAt='2026-10-25T00:00:00+00:00',expiresAt='2026-10-25T02:00:00+00:00')):
            with self.subTest(window=w),self.assertRaises(Held): receipts.check_window(w)

    def test_source_inventory_contains_no_live_configuration_or_credentials(self):
        got=receipts.source_hashes()
        self.assertEqual(set(got),set(receipts.SOURCE_FILES))
        self.assertTrue(all(len(v)==64 for v in got.values()))
        self.assertFalse(any('.env' in k or 'credentials/' in k for k in got))
