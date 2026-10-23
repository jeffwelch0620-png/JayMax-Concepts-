"""Public source-only Git fixtures; no network, private config or hosted probe."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/ops'))
import read_only_probe as probe


class ProbeReproducibilityTests(unittest.TestCase):
    def test_same_commit_packet_matches_git_bytes_with_both_autocrlf_settings(self):
        root=probe.ROOT
        files=probe.sources()
        with TemporaryDirectory() as temporary:
            work=Path(temporary).resolve(); origin=work/'origin'; origin.mkdir()
            empty=work/'empty'; empty.mkdir()
            env={**os.environ,'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':os.devnull,
                 'GIT_CONFIG_COUNT':'0','GIT_TERMINAL_PROMPT':'0'}
            for name in tuple(env):
                if name.startswith(('GIT_CONFIG_KEY_','GIT_CONFIG_VALUE_')) or name in (
                        'GIT_DIR','GIT_WORK_TREE','GIT_INDEX_FILE','GIT_COMMON_DIR',
                        'GIT_OBJECT_DIRECTORY','GIT_ALTERNATE_OBJECT_DIRECTORIES'):
                    env.pop(name)
            def git(*args,cwd=origin):
                return subprocess.check_output(['git','-c','core.hooksPath='+str(empty),*args],
                    cwd=cwd,env=env,stderr=subprocess.PIPE,timeout=30)
            git('init','--quiet','--template='+str(empty))
            for name in files:
                destination=origin/name; destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes((root/name).read_bytes())
            (origin/'.gitattributes').write_bytes((root/'.gitattributes').read_bytes())
            git('-c','core.autocrlf=false','add','.')
            git('-c','user.name=TEST ONLY','-c','user.email=fictional@example.invalid',
                'commit','--quiet','-m','Fictional public source snapshot')
            commit=git('rev-parse','HEAD').strip()
            expected={name:hashlib.sha256(git('show','HEAD:'+name)).hexdigest() for name in files}
            packets=[]
            for setting in ('true','false'):
                clone=work/setting
                git('-c','core.autocrlf='+setting,'clone','--quiet','--no-local',
                    '--template='+str(empty),str(origin),str(clone),cwd=work)
                self.assertEqual(git('rev-parse','HEAD',cwd=clone).strip(),commit)
                self.assertEqual(git('status','--porcelain',cwd=clone),b'')
                with patch.object(probe,'ROOT',clone): packets.append(probe.packet('health'))
                self.assertEqual(packets[-1]['sources'],expected)
                self.assertTrue(all(b'\r' not in (clone/name).read_bytes() for name in files))
            self.assertEqual(packets[0],packets[1])
            self.assertEqual(probe.digest(packets[0]),probe.digest(packets[1]))

    def test_unrefreshed_crlf_source_refuses_without_changing_input_bytes(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'backend').mkdir(); (root/'tools/ops').mkdir(parents=True)
            (root/'docs').mkdir()
            requirement=root/'backend/requirements.txt'; requirement.write_bytes(b'TEST_ONLY\r\n')
            (root/'docs/READ_ONLY_HEALTH_CALIBRATION_PROPOSAL_20261023.md').write_bytes(b'TEST ONLY\n')
            with patch.object(probe,'ROOT',root),self.assertRaises(probe.Held): probe.packet('health')
            self.assertEqual(requirement.read_bytes(),b'TEST_ONLY\r\n')
