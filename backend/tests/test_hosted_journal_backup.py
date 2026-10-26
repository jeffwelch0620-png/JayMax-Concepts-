"""Fictional scope/custody tests. Hosted-looking strings are mocked before DNS."""
import asyncio
import base64
from copy import deepcopy
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock,Mock,patch
from uuid import uuid4

from cryptography.fernet import Fernet
from application_backup_profiles import (Held,LEGACY6,RECEIVING7,canonical,digest,profile,scope,strict_json)
import hosted_backup as legacy
import hosted_journal_backup as journal
import hosted_journal_backup_cli as cli
import journal_backup_receipts as receipts
import native_backup
from test_journal_backup_receipts import POLICY,binding,packet

PROJECT='abcdefghijklmnopqrst'
URL='postgresql://postgres:TEST_ONLY@db.'+PROJECT+'.supabase.co:5432/postgres'


def manifest(b=None):
    raw=b'PGDMP TEST ONLY binary\x00\r\n'
    facts=dict(tables={'operations.fixture':dict(rows=1,sha256=digest(b'fictional rows'),kind='r')},
               catalog={k:dict(objects=0,sha256=digest(b'')) for k in journal.CATALOG_GROUPS})
    return dict(format=RECEIVING7.format,profile='receiving7',profileSha256=RECEIVING7.sha256,
        schemas=list(RECEIVING7.schemas),binding=b or binding(),createdAt=datetime.now(timezone.utc).isoformat(),
        serverVersionNum='170006',archiveBytes=len(raw),archiveSha256=digest(raw),rowFingerprintAlgorithm=journal.ROW_ALGORITHM,
        facts=facts,authority=dict(databaseOwner='local_owner',schemaOwners={s:'local_owner' for s in RECEIVING7.schemas},
             requiredRoles=['local_owner'],rolesWithoutPasswords=[],roleMemberships=[]),dependencies=deepcopy(POLICY),
        migrationFileHashes={'migrations/20991025_test_only.sql':digest(b'TEST ONLY')},sourceSystemIdentifier='123456789',
        sourceDatabaseOid=12345,ownershipMode='preserve',sequenceStateIsMvcc=False,sequencesObservedStable=True,
        managedRecoveryVerified=False),raw


class ProfileTests(unittest.TestCase):
    def test_profile_explicit_immutable_and_exact(self):
        self.assertEqual(profile('legacy6').schemas,legacy.SCHEMAS)
        self.assertEqual(profile('receiving7').schemas,legacy.SCHEMAS+('operations',))
        self.assertNotEqual(LEGACY6.sha256,RECEIVING7.sha256)
        for value in (None,'auto','',{},True,'future8'):
            with self.subTest(profile=value),self.assertRaises(Held): profile(value)
        with self.assertRaises(Exception): RECEIVING7.schemas=('public',)

    def test_missing_empty_extra_and_legacy_operations_never_downgrade(self):
        scope(RECEIVING7.schemas,RECEIVING7,legacy.MANAGED)
        scope(RECEIVING7.schemas+('auth','extensions'),RECEIVING7,legacy.MANAGED)
        for found,selected in ((LEGACY6.schemas,RECEIVING7),(RECEIVING7.schemas,LEGACY6),
                (RECEIVING7.schemas+('scheduling',),RECEIVING7)):
            with self.subTest(found=found),self.assertRaises(Held): scope(found,selected,legacy.MANAGED)

    def test_new_envelope_exact_authentication_and_independent_digests(self):
        m,raw=manifest();key=Fernet.generate_key();blob=journal.seal(m,raw,key)
        kwargs=dict(expected=m['binding'],expected_encrypted_sha=digest(blob),policy=POLICY)
        self.assertEqual(journal.open_envelope(blob,key,**kwargs),(m,raw))
        self.assertNotIn(raw,blob)
        for mode in ('key','blob','digest','project_binding','policy'):
            args=deepcopy(kwargs);k=key;data=blob
            if mode=='key':k=Fernet.generate_key()
            elif mode=='blob':data=blob[:-8]+b'damaged!'
            elif mode=='digest':args['expected_encrypted_sha']='0'*64
            elif mode=='project_binding':args['expected']['sourceBinding']='0'*64
            else:args['policy']={'extensions':[],'authFunctions':[dict(proname='uid',definitionSha256='0'*64)]}
            with self.subTest(mode=mode),self.assertRaises(Held):journal.open_envelope(data,k,**args)

    def test_authenticated_wrong_scope_shape_precision_and_partial_facts_hold(self):
        for field,value in [('format',legacy.FORMAT),('schemas',list(LEGACY6.schemas)),('profile','legacy6'),
                            ('profileSha256','0'*64),('archiveBytes',True),('archiveSha256','0'*64),
                            ('ownershipMode','no-owner'),('sequenceStateIsMvcc',True),('facts',{}),
                            ('migrationFileHashes',{}),('sourceDatabaseOid',False),('serverVersionNum','17')]:
            m,raw=manifest();m[field]=value;k=Fernet.generate_key();blob=journal.seal(m,raw,k)
            with self.subTest(field=field),self.assertRaises(Held):
                journal.open_envelope(blob,k,expected=m['binding'],expected_encrypted_sha=digest(blob),policy=POLICY)

    def test_duplicate_json_and_nan_do_not_get_signed_into_a_success(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}',b'{"x":1e9999}'):
            with self.subTest(raw=raw),self.assertRaises(Held):strict_json(raw)
        m,raw=manifest();k=Fernet.generate_key()
        duplicate=b'{"manifest":'+canonical(m)+b',"manifest":'+canonical(m)+b',"archive":"'+base64.b64encode(raw)+b'"}'
        blob=Fernet(k).encrypt(duplicate)
        with self.assertRaises(Held):journal.open_envelope(blob,k,expected=m['binding'],expected_encrypted_sha=digest(blob),policy=POLICY)

    def test_legacy_reader_still_opens_v1_and_refuses_v2(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);k=Fernet.generate_key();(root/'key').write_bytes(k)
            m,raw=manifest();v2=journal.seal(m,raw,k);(root/'enc').write_bytes(v2)
            with self.assertRaises(legacy.BackupError):legacy.open_backup(root/'enc',root/'key',PROJECT)
            old=dict(format=legacy.FORMAT,schemas=list(legacy.SCHEMAS),projectRef=PROJECT,archiveBytes=len(raw),archiveSha256=digest(raw))
            (root/'enc').write_bytes(Fernet(k).encrypt(json.dumps(dict(manifest=old,archive=base64.b64encode(raw).decode())).encode()))
            self.assertEqual(journal.open_profile(LEGACY6,root/'enc',root/'key',expected_project=PROJECT),(old,raw))

    def test_restore_remote_control_bad_port_and_ownership_bindings_refuse(self):
        target=journal.RestoreTarget('postgresql://local_owner@127.0.0.1:5544/native_purchase_test_backup_'+uuid4().hex,
            'postgresql://local_owner@127.0.0.1:5544/native_purchase_test_control','123',42)
        self.assertEqual(journal.restore_settings(target)['port'],5544)
        for t in (replace(target,url=URL),replace(target,url=target.control_url),replace(target,system_identifier='bad'),
                  replace(target,database_oid=True),replace(target,control_url=target.control_url.replace(':5544',':5545')),
                  replace(target,url=target.url+'?sslmode=disable'),replace(target,url=target.url.replace(':5544',':543'))):
            with self.subTest(target=t),self.assertRaises((Held,native_backup.BackupError)):journal.restore_settings(t)

    def test_dependency_policy_never_treats_function_name_as_review(self):
        actual=dict(extensions=[],authFunctions=[dict(proname='uid',prosecdef=False,lanname='sql',args='',definition='TEST ONLY definition')])
        policy=dict(extensions=[],authFunctions=[dict(proname='uid',definitionSha256=digest(b'TEST ONLY definition'))])
        self.assertEqual(journal.check_dependencies(actual,policy),actual)
        for p in (POLICY,dict(extensions=[dict(extname='untrusted',extversion='1',schema='extensions')],authFunctions=[]),
                  dict(extensions=[dict(extname='pgcrypto',extversion="1';BAD",schema='extensions')],authFunctions=[]),
                  dict(extensions=[],authFunctions=[dict(proname='uid',definitionSha256='0'*64)])):
            with self.subTest(policy=p),self.assertRaises(Held):journal.check_dependencies(actual,p)

    def test_frozen_design_sources_remain_raw_byte_unchanged(self):
        root=Path(__file__).resolve().parents[2]
        pins=json.loads((root/'docs/HOSTED_JOURNAL_BACKUP_ADAPTER_SOURCE_PINS_20261025.json').read_text())
        for name,values in pins['sourceFiles'].items():
            allowed={values['worktreeSha256']}
            if values['checkoutLineEndingsOnly']:
                allowed.add(values['gitBlobSha256'])
            with self.subTest(source=name):self.assertIn(digest((root/name).read_bytes()),allowed)


class AdapterGuards(unittest.IsolatedAsyncioTestCase):
    async def test_source_binding_and_packet_refuse_before_dns_or_connect(self):
        b=binding();b['sourceBinding']='0'*64;raw=packet(b)
        with patch.object(journal.maintenance,'dump_settings',new_callable=AsyncMock) as dns,patch.object(journal.maintenance,'connect',new_callable=AsyncMock) as connect:
            for sha,url in (('0'*64,URL),(digest(raw),URL),(digest(raw),URL.replace(':5432',':6543'))):
                with self.subTest(url=url),self.assertRaises((Held,journal.maintenance.MaintenanceConnectionError)):
                    await journal.export_backup(url,PROJECT,'dump','restore','backup','key',{},execution_packet=raw,packet_sha=sha)
            dns.assert_not_awaited();connect.assert_not_awaited()

    async def test_context_token_resets_on_error_cancellation_and_success(self):
        sentinel=object();token=legacy.EXPORT_CONTROL.set(sentinel)
        try:
            async with journal.bounded_run(2):self.assertIsNot(legacy.EXPORT_CONTROL.get(),sentinel)
            self.assertIs(legacy.EXPORT_CONTROL.get(),sentinel)
            for error in (Held('TEST_ONLY'),asyncio.CancelledError()):
                with self.assertRaises(type(error)):
                    async with journal.bounded_run(2):raise error
                self.assertIs(legacy.EXPORT_CONTROL.get(),sentinel)
        finally:legacy.EXPORT_CONTROL.reset(token)

    async def test_close_cleanup_preserves_primary_failure(self):
        c=Mock();c.close=AsyncMock(side_effect=OSError('TEST ONLY secret'))
        with self.assertRaises(OSError):await journal.close_owned(c)
        c.terminate.assert_called_once()

    async def test_cli_inactive_without_execute_and_prints_no_driver_messages(self):
        with patch.object(cli,'private_bytes') as read:
            with self.assertRaises(Held):await cli.main(['export','--packet','fictional','--expected-packet-sha256','0'*64,'--profile','receiving7','--pg-bin','fictional'])
            read.assert_not_called()
        def failed(awaitable):
            awaitable.close()
            raise RuntimeError('postgresql://TEST_ONLY_SECRET')
        with patch.object(cli.asyncio,'run',side_effect=failed),patch('builtins.print') as out:
            self.assertEqual(cli.run(),2)
            self.assertNotIn('TEST_ONLY_SECRET',str(out.call_args))

    async def test_restore_authentication_and_remote_target_hold_before_connect(self):
        target=journal.RestoreTarget(URL,URL,'123',42);m,raw=manifest();k=Fernet.generate_key();blob=journal.seal(m,raw,k)
        with patch.object(journal.asyncpg,'connect',new_callable=AsyncMock) as connect:
            with self.assertRaises((Held,native_backup.BackupError)):
                await journal.verify_restore(target,blob,k,'restore','folder',expected=m['binding'],expected_encrypted_sha=digest(blob),policy=POLICY,execution_window=m['binding']['window'])
            connect.assert_not_awaited()

    async def test_valid_loopback_restore_target_with_wrong_key_opens_no_connection(self):
        target=journal.RestoreTarget('postgresql://local_owner@127.0.0.1:5544/native_purchase_test_backup_'+uuid4().hex,
            'postgresql://local_owner@127.0.0.1:5544/native_purchase_test_control','123',42)
        m,raw=manifest();key=Fernet.generate_key();blob=journal.seal(m,raw,key)
        with patch.object(journal.asyncpg,'connect',new_callable=AsyncMock) as connect:
            with self.assertRaises(Held):
                await journal.verify_restore(target,blob,Fernet.generate_key(),'restore','folder',expected=m['binding'],
                    expected_encrypted_sha=digest(blob),policy=POLICY,execution_window=m['binding']['window'])
            connect.assert_not_awaited()

    async def test_valid_source_packet_does_not_fallback_when_ipv6_or_tls_holds(self):
        b=binding();b['sourceBinding']=journal.source_binding(journal.maintenance.direct_settings(URL,PROJECT),PROJECT)
        raw=packet(b)
        with patch.object(journal.maintenance,'dump_settings',AsyncMock(side_effect=journal.maintenance.MaintenanceConnectionError('TEST_ONLY_IPV6_HOLD'))) as dns,\
             patch.object(journal.asyncpg,'connect',new_callable=AsyncMock) as connect:
            with self.assertRaises(journal.maintenance.MaintenanceConnectionError):
                await journal.export_backup(URL,PROJECT,'dump','restore','backup','key',{},execution_packet=raw,packet_sha=digest(raw))
            dns.assert_awaited_once();connect.assert_not_awaited()

    async def test_cli_export_uses_only_private_maintenance_config_and_withholds_custody_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);pg=root/'pg';pg.mkdir();suffix='.exe' if os.name=='nt' else ''
            for name in ('pg_dump','pg_restore'):(pg/(name+suffix)).write_bytes(b'TEST ONLY executable placeholder')
            b=binding();raw=packet(b);packet_path=root/'packet.json';packet_path.write_bytes(raw)
            config=root/'private.env';config.write_text('MAINTENANCE_DATABASE_URL='+URL+'\nDATABASE_URL=SHOULD_NOT_BE_READ\n',encoding='utf-8')
            async def exported(*args,**kwargs):
                self.assertEqual(args[0],URL);self.assertEqual(args[1],PROJECT)
                self.assertEqual(kwargs['packet_sha'],digest(raw))
                directory=Path(args[4]);directory.mkdir(parents=True)
                m,_=manifest(b)
                return receipts.receipt(m,digest(b'TEST ONLY encrypted'))|{'encryptedBackup':str(directory/'backup.jmax.enc'),
                    'privateKey':str(Path(args[5])/'backup.key')}
            with patch.dict(os.environ,{'LOCALAPPDATA':str(root)}),patch.object(cli,'private_file',side_effect=Path),\
                 patch.object(journal,'export_backup',exported),patch.object(journal.asyncpg,'connect',new_callable=AsyncMock) as connect,\
                 patch('builtins.print') as out:
                public=await cli.main(['export','--execute','--packet',str(packet_path),'--expected-packet-sha256',digest(raw),
                    '--profile','receiving7','--pg-bin',str(pg),'--owner-config',str(config)])
                connect.assert_not_awaited()
                self.assertEqual(public['status'],'exported_not_restore_verified')
                self.assertNotIn('privateKey',public);self.assertNotIn('encryptedBackup',public)
                self.assertNotIn(str(root),str(out.call_args));self.assertNotIn('TEST_ONLY',str(out.call_args))
                record=list((root/'JayMaxBuild'/'backups').rglob('adapter.private.json'))
                self.assertEqual(len(record),1)
                self.assertIn('privateKey',json.loads(record[0].read_bytes()))

    async def test_restore_cli_packet_binds_exact_owned_target_file_before_connection(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);suffix='.exe' if os.name=='nt' else ''
            for name in ('pg_dump','pg_restore'):(root/(name+suffix)).write_bytes(b'TEST ONLY tool')
            raw=packet(action='verify-restore');p=root/'packet';p.write_bytes(raw)
            target=root/'target';target.write_bytes(b'{"different":"TEST ONLY target"}')
            with patch.object(cli,'private_file',side_effect=Path),patch.object(journal.asyncpg,'connect',new_callable=AsyncMock) as connect:
                with self.assertRaisesRegex(Held,'restore_target_record_digest_differs'):
                    await cli.main(['verify-restore','--execute','--packet',str(p),'--expected-packet-sha256',digest(raw),
                        '--profile','receiving7','--pg-bin',str(root),'--backup',str(root/'unused'),
                        '--key-file',str(root/'unused-key'),'--expected-encrypted-sha256','0'*64,'--target-record',str(target)])
                connect.assert_not_awaited()

    async def test_close_only_failure_and_cleanup_failure_never_publish_success(self):
        # Fault injection at resource boundaries; real archive fidelity is tested
        # separately against PostgreSQL and the frozen same-snapshot oracle.
        for failure in ('close','readback','cleanup'):
            with self.subTest(stage=failure),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);out=root/'archive';keys=root/'key'
                b=binding();b['sourceBinding']=journal.source_binding(journal.maintenance.direct_settings(URL,PROJECT),PROJECT)
                raw_packet=packet(b);m,data=manifest(b)
                conn=Mock();conn.close=AsyncMock(side_effect=OSError('TEST_ONLY') if failure=='close' else None)
                async def capture(c,settings,dump,path,*rest,**kw):path.write_bytes(data);return m,data
                def private(path,area):path=Path(path);path.mkdir();return path
                cleanup=legacy.remove_partial_files
                async def clean(paths):
                    if failure=='cleanup':raise OSError('TEST_ONLY')
                    await cleanup(paths)
                open_original=journal.open_envelope
                def read(*a,**kw):
                    if failure=='readback':raise Held('test_only_readback')
                    return open_original(*a,**kw)
                with patch.object(journal.maintenance,'dump_settings',AsyncMock(return_value={})),\
                     patch.object(journal.maintenance,'connect',AsyncMock(return_value=conn)),\
                     patch.object(journal,'capture',capture),patch.object(legacy,'private_directory',private),\
                     patch.object(legacy,'tool',AsyncMock(return_value=b'TEST ONLY listing')),\
                     patch.object(legacy,'remove_partial_files',clean),patch.object(journal,'open_envelope',read):
                    with self.assertRaises((OSError,Held)) as held:
                        await journal.export_backup(URL,PROJECT,'dump','restore',out,keys,{},
                            execution_packet=raw_packet,packet_sha=digest(raw_packet))
                self.assertFalse((out/'backup.jmax.enc').exists())
                self.assertTrue(held.exception.backupArtifacts['privateKeyRetained'])
                self.assertFalse(held.exception.backupArtifacts['finalBackupPresent'])
                self.assertIsNone(legacy.EXPORT_CONTROL.get())
