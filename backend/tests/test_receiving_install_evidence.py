"""Fictional authenticated archives; no database/network or existing credentials."""
import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from cryptography.fernet import Fernet
import receiving_install_evidence as evidence
import hosted_backup as legacy
import hosted_journal_backup as journal
import journal_backup_receipts as receipts
from application_backup_profiles import Held, canonical, digest
from test_hosted_journal_backup import manifest as journal_manifest, PROJECT


def window():
    now = datetime.now(timezone.utc)
    return dict(startsAt=(now-timedelta(seconds=30)).isoformat(),
                expiresAt=(now+timedelta(minutes=40)).isoformat())


def matrix():
    return [dict(name=n, disposition='supported' if n in ('legacy_backup','journal_backup') else 'held',
                 required=n in ('legacy_backup','journal_backup'), ownerAccepted=True)
            for n in sorted(evidence.CONSUMERS)]


def attested():
    return dict(cleanup={k:True for k in ('sourceClosed','toolsClosed','plaintextRemoved','restoreTargetInspected')},
                custody={k:True for k in ('keyMoved','separateKeyAccessVerified','workingKeyPrivate','retentionConfirmed')})


def closed_key():
    return {k:True for k in ('keyMoved','separateKeyAccessVerified','restoreVerified','localKeyCopyDeleted','retentionConfirmed')}


def migration_hashes():
    return {k:v for k,v in evidence.source_hashes().items() if k.startswith('migrations/')}


def identity():
    return dict(host='127.0.0.1',port=5544,user='local_owner',
                database='native_purchase_test_'+'a'*32,systemIdentifier='123456789',databaseOid=12345)


def expectation(m, encrypted, restored, phase, source=None, capture=None):
    return dict(format=evidence.FORMAT,phase=phase,profile='legacy6' if phase=='pre_install' else 'receiving7',
        projectRef=PROJECT, source=source or identity(), sourceHashes=evidence.source_hashes(),
        captureWindow=capture or window(), verificationWindow=capture or window(),
        artifacts=dict(encryptedSha256=digest(encrypted),archiveSha256=m['archiveSha256'],
            manifestSha256=digest(canonical(m)),factsSha256=digest(canonical(
                {k:m[k] for k in ('tables','catalog')} if phase=='pre_install' else m['facts'])),
            restoreReceiptSha256=digest(canonical(restored))),
        dependencyPolicy={'extensions':[],'authFunctions':[]},attestations=attested(),
        journalBinding=None if phase=='pre_install' else m['binding'])


def legacy_files(root):
    raw=b'PGDMP TEST ONLY raw\x00\xff\r\n'
    m=dict(format=legacy.FORMAT,projectRef=PROJECT,schemas=list(legacy.SCHEMAS),
        rowFingerprintAlgorithm=legacy.ROW_ALGORITHM,serverVersionNum='170006',
        createdAt=datetime.now(timezone.utc).isoformat(),archiveSha256=digest(raw),archiveBytes=len(raw),
        tables={'supabase_migrations.schema_migrations':dict(rows=1,sha256=digest(b'ledger'),kind='r')},
        catalog={'fixtures':dict(objects=0,sha256=digest(b''))},
        dependencies={'objects':[],'extensions':[],'authFunctions':[]},
        sequenceStateIsMvcc=False,sequencesObservedStable=True,managedRecoveryVerified=False,
        migrationFileHashes=migration_hashes())
    key=Fernet.generate_key(); encrypted=Fernet(key).encrypt(canonical(dict(manifest=m,archive=base64.b64encode(raw).decode())))
    a=root/'before.enc';k=root/'before.key';a.write_bytes(encrypted);k.write_bytes(key)
    r=dict(status='verified_application_restore',archiveSha256=m['archiveSha256'],majorVersionMatched=True,
        patchVersionMatched=True,tablesMatched=1,catalogGroupsMatched=1,rowsMatched=1,
        managedRecoveryVerified=False,operationalReleaseApproved=False)
    w=window();e=expectation(m,encrypted,r,'pre_install',capture=w)
    return a,k,r,e


def post_files(root, source=None):
    m,raw=journal_manifest(); w=window();m['binding']['window']=w;m['migrationFileHashes']=migration_hashes()
    m['facts']['tables']={name:dict(rows=0,sha256=digest(b''),kind='r') for name in (
        'supabase_migrations.schema_migrations','operations.store_settings','operations.handoff_notes',
        'operations.handoff_note_revisions','operations.handoff_command_receipts')}
    if source:
        m['sourceSystemIdentifier']=source['systemIdentifier'];m['sourceDatabaseOid']=source['databaseOid']
    key=Fernet.generate_key(); encrypted=journal.seal(m,raw,key)
    r=receipts.receipt(m,digest(encrypted),restored=True,verification_window=w,topology='cross_cluster')
    a=root/'after.enc';k=root/'after.key';a.write_bytes(encrypted);k.write_bytes(key)
    e=expectation(m,encrypted,r,'post_install',source,capture=w)
    return a,k,r,e


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name);self.a,self.k,self.r,self.e=legacy_files(self.root)

    def test_authenticates_legacy_and_post_profiles_without_coercion(self):
        m,f=evidence.authenticate(self.a,self.k,self.r,self.e,digest(canonical(self.e)),'pre_install')
        self.assertEqual(m['schemas'],list(legacy.SCHEMAS))
        a,k,r,e=post_files(self.root)
        self.assertEqual(evidence.authenticate(a,k,r,e,digest(canonical(e)),'post_install')[0]['profile'],'receiving7')
        with self.assertRaises(Held):evidence.authenticate(a,k,r,e,digest(canonical(e)),'pre_install')
        with self.assertRaises(Held):evidence.authenticate(self.a,self.k,self.r,self.e,digest(canonical(self.e)),'post_install')

    def test_wrong_keys_swapped_receipts_and_independent_digests_refuse(self):
        for case in ('key','archive','receipt','expected'):
            with self.subTest(case=case):
                a,k,r,e=legacy_files(self.root);sha=digest(canonical(e))
                if case=='key':k.write_bytes(Fernet.generate_key())
                if case=='archive':a.write_bytes(a.read_bytes()[:-2]+b'xx')
                if case=='receipt':r['tablesMatched']=2
                if case=='expected':e['artifacts']['archiveSha256']='0'*64
                with self.assertRaises(Held):evidence.authenticate(a,k,r,e,sha,'pre_install')

    def test_missing_custody_cleanup_source_profile_window_and_dependencies_hold(self):
        for field in ('custody','cleanup','source','profile','window','policy','journal','size'):
            with self.subTest(field=field):
                e=deepcopy(self.e)
                if field in ('custody','cleanup'):e['attestations'][field][next(iter(e['attestations'][field]))]=False
                elif field=='source':e['source']['host']='db.example.invalid'
                elif field=='profile':e['profile']='receiving7'
                elif field=='window':e['captureWindow']['expiresAt']=e['captureWindow']['startsAt']
                elif field=='policy':e['dependencyPolicy']['extensions']=[dict(extname='unreviewed',schema='extensions',extversion='1')]
                elif field=='journal':e['journalBinding']={}
                elif field=='size':e['source']['databaseOid']=True
                with self.assertRaises(Held):evidence.authenticate(self.a,self.k,self.r,e,digest(canonical(e)),'pre_install')

    def test_manifest_and_restore_semantics_still_checked_when_caller_rehashes(self):
        for field in ('tablesMatched','catalogGroupsMatched','majorVersionMatched','status','managedRecoveryVerified','operationalReleaseApproved'):
            with self.subTest(field=field):
                r=deepcopy(self.r);r[field]=False if field=='majorVersionMatched' else True if field in ('managedRecoveryVerified','operationalReleaseApproved') else 999
                e=deepcopy(self.e);e['artifacts']['restoreReceiptSha256']=digest(canonical(r))
                with self.assertRaises(Held):evidence.authenticate(self.a,self.k,r,e,digest(canonical(e)),'pre_install')

    def test_matrix_cannot_hold_required_or_unaccepted_consumer(self):
        evidence.consumers(matrix())
        for case in ('required','accepted','duplicate','missing'):
            with self.subTest(case=case):
                v=matrix()
                if case=='required':v[0].update(required=True,disposition='held')
                elif case=='accepted':v[0]['ownerAccepted']=False
                elif case=='duplicate':v[0]=v[1]
                else:v.pop()
                with self.assertRaises(Held):evidence.consumers(v)

    def test_reserve_uses_real_remaining_time_and_does_not_extend_window(self):
        w=window();self.assertLessEqual(evidence.window_budget(w),600)
        for reserve in (0,599,True,2700):
            with self.subTest(reserve=reserve),self.assertRaises(Held):evidence.window_budget(w,reserve)
        now=datetime.now(timezone.utc);w['expiresAt']=(now+timedelta(seconds=599)).isoformat()
        with self.assertRaises(Held):evidence.window_budget(w,now=now)
        w['expiresAt']=(now+timedelta(minutes=46)).isoformat()
        with self.assertRaises(Held):evidence.window_budget(w,now=now)

    def test_duplicate_json_in_legacy_envelope_is_refused(self):
        key=self.k.read_bytes();self.a.write_bytes(Fernet(key).encrypt(b'{"manifest":{},"manifest":{},"archive":""}'))
        e=deepcopy(self.e);e['artifacts']['encryptedSha256']=digest(self.a.read_bytes())
        with self.assertRaises(Held):evidence.authenticate(self.a,self.k,self.r,e,digest(canonical(e)),'pre_install')

    def test_authenticated_archive_still_requires_reviewed_receiving_migration_hash(self):
        import json
        key=self.k.read_bytes()
        original=json.loads(Fernet(key).decrypt(self.a.read_bytes()))
        for value in ({}, {name:'0'*64 for name in migration_hashes()}):
            with self.subTest(migrationInventory=value):
                payload=deepcopy(original);payload['manifest']['migrationFileHashes']=value
                blob=Fernet(key).encrypt(canonical(payload));self.a.write_bytes(blob)
                e=deepcopy(self.e);e['artifacts']['encryptedSha256']=digest(blob)
                e['artifacts']['manifestSha256']=digest(canonical(payload['manifest']))
                with self.assertRaisesRegex(Held,'receiving_migration_source_binding_differs'):
                    evidence.authenticate(self.a,self.k,self.r,e,digest(canonical(e)),'pre_install')

    def test_source_inventory_excludes_configuration_and_legacy_files_stay_explicit(self):
        self.assertEqual(set(evidence.source_hashes()),set(evidence.SOURCE_FILES))
        self.assertTrue(all(not x.endswith('.env') for x in evidence.SOURCE_FILES))
        self.assertEqual(legacy.SCHEMAS,journal.LEGACY6.schemas)
