"""Fictional local handoffs; no credentials, service controls or database calls."""
import ast
from contextlib import redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('par_packet', ROOT/'tools/ops/par_qualification_packet.py')
packet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packet)


class ParQualificationPacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory(prefix='test_only_par_packet_')
        cls.root = Path(cls.temp.name)
        proposal = json.loads((ROOT/packet.PROPOSAL).read_bytes())
        names = {packet.PROPOSAL, *proposal['installerSourceHashes'], *packet.EXTRA_SOURCES}
        for name in names:
            target = cls.root/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/name, target)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def artifact(self, root, value=None, raw=None):
        path = Path(root)/'TEST_ONLY_PACKET.json'
        raw = raw if raw is not None else packet.json_bytes(value or packet.build(self.root))
        path.write_bytes(raw)
        return path, packet.digest(raw)

    def test_prepare_and_verify_bind_all_public_sources_without_authority(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'TEST_ONLY_PACKET.json'
            sha = packet.prepare(path, self.root)
            report = packet.verify(path, sha, self.root)
            data = json.loads(path.read_bytes())
            self.assertEqual(report['status'], 'verified_local_operator_handoff')
            self.assertEqual(report['coreSourcesVerified'], 49)
            self.assertEqual(report['sourceFilesVerified'], 56)
            self.assertEqual(report['orderedMigrations'], 31)
            self.assertTrue(all(value is False for value in data['executionApprovals'].values()))
            self.assertFalse(report['readyForHostedExecution'])
            self.assertFalse(report['schemaApplyApproved'])
            self.assertIsNone(data['window']['startsAt'])
            self.assertIsNone(data['deliveryVersion'])
            self.assertIsNone(data['executableInstallationPlanSha256'])
            self.assertEqual(data['toolingReviewStatus'],'candidate_requires_independent_review')
            self.assertEqual(set(data['toolingAmendments']),{
                'backend/deployment_readiness.py','tools/ops/apply_reviewed_par_migration.py'})

    def test_generation_is_deterministic(self):
        self.assertEqual(packet.json_bytes(packet.build(self.root)), packet.json_bytes(packet.build(self.root)))

    def test_unsupported_python_is_held_before_arguments_or_file_io(self):
        for version in ((3, 10), (3, 11)):
            with self.subTest(version=version), patch.object(packet.sys, 'version_info', version), \
                    patch.object(packet.Path, 'read_bytes') as reads, \
                    patch.object(packet.Path, 'open') as opens, \
                    patch.object(packet.argparse.ArgumentParser, 'parse_args') as arguments, \
                    redirect_stdout(io.StringIO()) as output:
                code = packet.main(['prepare', '--output', 'TEST_ONLY_NEVER_CREATED.json'])
                self.assertEqual(code, 2)
                result = json.loads(output.getvalue())
                self.assertEqual(result['status'], 'held')
                self.assertEqual(result['reason'], 'Python 3.12 or newer required')
                self.assertFalse(result['hostedActionsPerformed'])
                self.assertFalse(result['readyForHostedExecution'])
                reads.assert_not_called(); opens.assert_not_called(); arguments.assert_not_called()

    def test_existing_output_and_evidence_are_never_overwritten(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'TEST_ONLY_PACKET.json'
            path.write_bytes(b'TEST ONLY retained earlier evidence')
            with self.assertRaises(FileExistsError):
                packet.prepare(path, self.root)
            self.assertEqual(path.read_bytes(), b'TEST ONLY retained earlier evidence')

    def test_changed_approved_proposal_is_refused_even_if_json_remains_valid(self):
        path = self.root/packet.PROPOSAL
        original = path.read_bytes()
        try:
            value = json.loads(original)
            value['executionApprovals']['apiPause'] = True
            path.write_bytes(packet.json_bytes(value))
            with self.assertRaises(packet.PacketHeld): packet.build(self.root)
        finally: path.write_bytes(original)

    def test_changed_core_sql_catalog_or_runtime_source_prevents_generation(self):
        for name in ('backend/deployment_readiness.py','tools/ops/apply_reviewed_par_migration.py',
                     'migrations/20261018_reviewed_inventory_pars.sql',
                     'docs/REVIEWED_PAR_INSTALL_CATALOG.json', 'backend/maintenance_connection.py'):
            with self.subTest(source=name):
                path = self.root/name
                original = path.read_bytes()
                try:
                    path.write_bytes(original+b'\nTEST ONLY changed source\n')
                    with self.assertRaises(packet.PacketHeld): packet.build(self.root)
                finally: path.write_bytes(original)

    def test_source_change_after_packet_is_refused_for_every_added_source(self):
        with TemporaryDirectory() as tmp:
            artifact, sha = self.artifact(tmp)
            for name in packet.EXTRA_SOURCES:
                with self.subTest(source=name):
                    path = self.root/name
                    original = path.read_bytes()
                    try:
                        path.write_bytes(original+b'\nTEST ONLY drift\n')
                        with self.assertRaises(packet.PacketHeld): packet.verify(artifact, sha, self.root)
                    finally: path.write_bytes(original)

    def test_missing_source_holds_generation(self):
        path = self.root/'backend/hosted_backup_cli.py'
        raw = path.read_bytes()
        try:
            path.unlink()
            with self.assertRaises(OSError): packet.build(self.root)
        finally: path.write_bytes(raw)

    def test_text_checkout_newlines_are_portable_but_packet_remains_byte_bound(self):
        name = 'backend/maintenance_connection.py'
        path = self.root/name
        original = path.read_bytes()
        try:
            with TemporaryDirectory() as tmp:
                artifact, sha = self.artifact(tmp)
                lf = original.replace(b'\r\n', b'\n')
                changed = lf if b'\r\n' in original else lf.replace(b'\n', b'\r\n')
                self.assertNotEqual(original, changed)
                path.write_bytes(changed)
                packet.build(self.root)
                with self.assertRaises(packet.PacketHeld): packet.verify(artifact, sha, self.root)
        finally: path.write_bytes(original)

    def test_proposal_checkout_newlines_are_portable_and_packet_bytes_remain_bound(self):
        path = self.root/packet.PROPOSAL
        original = path.read_bytes()
        try:
            with TemporaryDirectory() as tmp:
                artifact, sha = self.artifact(tmp)
                lf = original.replace(b'\r\n', b'\n')
                path.write_bytes(lf if b'\r\n' in original else lf.replace(b'\n', b'\r\n'))
                packet.build(self.root)
                with self.assertRaises(packet.PacketHeld): packet.verify(artifact, sha, self.root)
        finally: path.write_bytes(original)

    def test_sql_newline_change_is_not_normalized(self):
        path = self.root/'migrations/20261018_reviewed_inventory_pars.sql'
        original = path.read_bytes()
        try:
            path.write_bytes(original.replace(b'\n', b'\r\n'))
            with self.assertRaises(packet.PacketHeld): packet.build(self.root)
        finally: path.write_bytes(original)

    def test_core_pin_manifest_change_is_refused(self):
        path = self.root/packet.CORE_PINS
        original = path.read_bytes()
        try:
            value = json.loads(original)
            value['coreSources']['backend/maintenance_connection.py']['contentSha256'] = '0'*64
            path.write_bytes(packet.json_bytes(value))
            with self.assertRaises(packet.PacketHeld): packet.build(self.root)
        finally: path.write_bytes(original)

    def test_legacy_packet_and_changed_amendment_are_refused(self):
        with TemporaryDirectory() as tmp:
            value=packet.build(self.root)
            value['format']='jaymax-par-qualification-operator-packet-v1'
            path,sha=self.artifact(tmp,value=value)
            with self.assertRaises(packet.PacketHeld):packet.verify(path,sha,self.root)
        changed=deepcopy(packet.TOOLING_AMENDMENTS)
        changed['backend/deployment_readiness.py']['priorContentSha256']='0'*64
        with patch.object(packet,'TOOLING_AMENDMENTS',changed),self.assertRaises(packet.PacketHeld):packet.build(self.root)
        changed=deepcopy(packet.TOOLING_AMENDMENTS)
        changed['backend/deployment_readiness.py']['contentSha256']='0'*64
        with patch.object(packet,'TOOLING_AMENDMENTS',changed),self.assertRaises(packet.PacketHeld):packet.build(self.root)

    def test_unsafe_source_paths_are_refused(self):
        for name in ('../TEST_ONLY.env', '/TEST_ONLY.env', 'C:/TEST_ONLY.env',
                     'backend\\TEST_ONLY.env', 'backend//x.py', 'backend/./x.py',
                     '//server/share', '', None):
            with self.subTest(path=name), self.assertRaises(packet.PacketHeld):
                packet.source_file(self.root, name)

    def test_source_link_and_junction_metadata_are_refused(self):
        for method in ('is_symlink', 'is_junction'):
            with self.subTest(kind=method), patch.object(Path, method, return_value=True):
                with self.assertRaises(packet.PacketHeld): packet.source_file(self.root, packet.PROPOSAL)

    def test_wrong_or_missing_external_packet_hash_holds(self):
        with TemporaryDirectory() as tmp:
            artifact, _ = self.artifact(tmp)
            for sha in ('0'*64, '', 'A'*64, None, True):
                with self.subTest(hash=sha), self.assertRaises(packet.PacketHeld):
                    packet.verify(artifact, sha, self.root)

    def test_tamper_is_refused_even_when_attacker_rehashes_the_new_artifact(self):
        original = packet.build(self.root)
        changes = [
            lambda v: v.update(schemaApplyApproved=True),
            lambda v: v.update(readyForHostedExecution=True),
            lambda v: v.update(automaticExecute=True),
            lambda v: v.update(automaticRetry=True),
            lambda v: v.update(deliveryVersion='20990101000000'),
            lambda v: v.update(executableInstallationPlanSha256='0'*64),
            lambda v: v['window'].update(startsAt='2099-01-01T00:00:00+00:00'),
            lambda v: v['window'].update(maximumMinutes=60),
            lambda v: v['window'].update(qualifyByMinute=44),
            lambda v: v['executionApprovals'].update(apiPause=True),
            lambda v: v['argvTemplates']['qualify'].__setitem__(2, 'apply'),
            lambda v: v['argvTemplates']['export'].remove('--maintenance-direct-ipv6'),
            lambda v: v['argvTemplates']['export'].__setitem__(-1, '999'),
            lambda v: v['stageEvidenceRequired'].update(export=[]),
            lambda v: v['requiredBeforeAnyHostedStep'].clear(),
            lambda v: v.update(TEST_ONLY_extra_instruction='run unreviewed code'),
            lambda v: v['sourceHashes'].clear(),
        ]
        for index, change in enumerate(changes):
            with self.subTest(change=index), TemporaryDirectory() as tmp:
                value = deepcopy(original); change(value)
                path, sha = self.artifact(tmp, value)
                with self.assertRaises(packet.PacketHeld): packet.verify(path, sha, self.root)

    def test_json_numeric_booleans_cannot_masquerade_as_false_gates(self):
        for key in ('schemaApplyApproved', 'readyForHostedExecution', 'automaticExecute', 'automaticRetry'):
            with self.subTest(gate=key), TemporaryDirectory() as tmp:
                value = packet.build(self.root); value[key] = 0
                path, sha = self.artifact(tmp, value)
                with self.assertRaises(packet.PacketHeld): packet.verify(path, sha, self.root)

    def test_duplicate_keys_nonfinite_and_nonobject_json_are_refused(self):
        for raw in (b'{"gate":false,"gate":true}', b'{"value":NaN}',
                    b'{"value":Infinity}', b'[]', b'null', b'{broken', b'\xff'):
            with self.subTest(raw=raw), TemporaryDirectory() as tmp:
                path, sha = self.artifact(tmp, raw=raw)
                with self.assertRaises(packet.PacketHeld): packet.verify(path, sha, self.root)

    def test_oversized_json_is_refused(self):
        with TemporaryDirectory() as tmp:
            path, sha = self.artifact(tmp, raw=b' '*packet.MAX_BYTES+b'{}')
            with self.assertRaises(packet.PacketHeld): packet.verify(path, sha, self.root)

    def test_templates_are_argv_arrays_with_only_the_three_reviewed_modes(self):
        commands = packet.build(self.root)['argvTemplates']
        self.assertEqual(set(commands), {'export', 'restore', 'qualify'})
        self.assertEqual([v[2] for v in commands.values()], ['export', 'verify-restore', 'dry-run'])
        self.assertTrue(all(isinstance(arg, str) for args in commands.values() for arg in args))
        self.assertNotIn('apply', json.dumps(commands))
        self.assertNotIn('--approve-plan-sha256', json.dumps(commands))
        self.assertNotIn('postgresql://', json.dumps(commands))

    def test_stage_timing_reserves_qualification_and_recovery_budgets(self):
        value = packet.build(self.root)
        w = value['window']
        self.assertEqual([w[k] for k in ('drainByMinute','exportByMinute','restoreByMinute',
            'qualifyByMinute','recoverByMinute')], [8,18,24,34,45])
        self.assertGreaterEqual((w['recoverByMinute']-w['restoreByMinute'])*60, 600+600)
        self.assertIn('full 600-second operation plus 600-second restoration reserve',
            value['stageEvidenceRequired']['qualify'])

    def test_module_cannot_open_connections_spawn_commands_or_load_credentials(self):
        tree = ast.parse((ROOT/'tools/ops/par_qualification_packet.py').read_text())
        allowed = {'argparse','hashlib','json','pathlib','re','sys'}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertTrue(all(n.name in allowed for n in node.names))
            if isinstance(node, ast.ImportFrom): self.assertIn(node.module, allowed)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, ('exec','eval','__import__'))

    def test_cli_prepare_verify_and_sanitized_error_receipts(self):
        with TemporaryDirectory() as tmp:
            # Exercise the actual repository CLI entry, including accepted source bindings.
            output = Path(tmp)/'TEST_ONLY_PACKET.json'
            stream = io.StringIO()
            with redirect_stdout(stream):
                code = packet.main(['prepare','--output',str(output)])
            self.assertEqual(code, 0)
            sha = json.loads(stream.getvalue())['packetSha256']
            stream = io.StringIO()
            with redirect_stdout(stream):
                code = packet.main(['verify','--packet',str(output),'--packet-sha256',sha])
            self.assertEqual(code, 0)
            self.assertFalse(json.loads(stream.getvalue())['readyForHostedExecution'])
            stream = io.StringIO()
            with redirect_stdout(stream):
                code = packet.main(['verify','--packet',str(output),'--packet-sha256','TEST ONLY PRIVATE TEXT'])
            self.assertEqual(code, 2)
            self.assertNotIn('PRIVATE TEXT', stream.getvalue())
            self.assertEqual(json.loads(stream.getvalue())['status'], 'held')

    def test_cli_has_no_activate_apply_or_execute_mode(self):
        for mode in ('activate','apply','execute'):
            with self.subTest(mode=mode), redirect_stdout(io.StringIO()), patch('sys.stderr', io.StringIO()):
                with self.assertRaises(SystemExit) as error: packet.main([mode])
                self.assertEqual(error.exception.code, 2)

    def test_new_suite_is_selected_by_offline_ci(self):
        spec = importlib.util.spec_from_file_location('TEST_ONLY_review_runner', ROOT/'tools/run_review_tests.py')
        runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
        self.assertIn('par_qualification_packet', runner.OFFLINE_MODULES)


if __name__ == '__main__': unittest.main()
