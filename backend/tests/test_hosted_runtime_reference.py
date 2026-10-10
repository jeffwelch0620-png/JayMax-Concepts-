"""Explicit archived-schema variant; never accept target metadata as reference."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import runtime_permissions as candidate

class HostedRuntimeReferenceTests(unittest.TestCase):
    def test_registered_variant_preserves_default_and_exact_reviewed_delta(self):
        profile=candidate.manifest()
        local=candidate.contract(profile);hosted=candidate.contract(profile,'hosted_build')
        self.assertEqual((len(local['functions']),len(local['relations'])),(94,123))
        self.assertEqual((len(hosted['functions']),len(hosted['relations'])),(96,127))
        self.assertEqual(hosted['localFrozenContractSha256'],candidate.digest(local))
        self.assertEqual(hosted['differencesFromLocalReference'],candidate.HOSTED_DELTA)
        with self.assertRaisesRegex(ValueError,'explicitly reviewed'):
            candidate.contract(profile,'auto')

    def test_hosted_variant_holds_changed_parent_anchor_and_unreviewed_objects(self):
        profile=candidate.manifest();original=candidate.contract(profile,'hosted_build')
        for kind in ('parent','schema','matrix','function','relation'):
            value=copy.deepcopy(original)
            if kind=='parent':value['localFrozenContractSha256']='0'*64
            elif kind=='schema':value['schemaExportSha256']='0'*64
            elif kind=='matrix':value['permissionMatrixSha256']='0'*64
            elif kind=='function':value['functions']['public.jmax_touch_updated_at()']['securityDefiner']=True
            else:value['relations']['public.unreviewed_relation']={'kind':'r','shapeSha256':'0'*64}
            # Changed approved functions must remain exactly pinned by the
            # reconstruction digest, not merely have an approved object name.
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'reference.json';path.write_text(json.dumps(value),encoding='utf-8')
                with patch.object(candidate,'HOSTED_CONTRACT',path):
                    with self.assertRaises(ValueError):candidate.contract(profile,'hosted_build')
