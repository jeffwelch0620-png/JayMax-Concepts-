"""Recovery alone cannot turn an interrupted or errored exercise into a pass."""
import unittest
import combined_rehearsal_result as result


class FinalQualification(unittest.TestCase):
    def receipt(self):
        return {key: True for key in result.REQUIRED} | {
            'format': 'jaymax-combined-rotation-rehearsal-v1', 'stage': 'complete',
            'status': 'passed_combined_rotation_recovery_rehearsal',
            'replacementPrivateConfigIsCurrent': False,
            'operationalReleaseApproved': False, 'businessRowsWritten': False,
            'applicationConfigurationChanged': False, 'existingApplicationSessionsTargeted': False,
            'objectPermissionsChanged': False,
            'originalCredentialsAvailable': {'accounts': True, 'inventory': True}}

    def test_recovered_journal_or_owner_error_keeps_otherwise_completed_work_held(self):
        receipt = self.receipt()
        self.assertTrue(result.passed(receipt))
        for field in ('errorType', 'exerciseErrorType', 'recoveryErrorType', 'safeReason', 'safeRecoveryReason'):
            with self.subTest(field=field):
                self.assertFalse(result.passed(receipt | {field: 'OSError'}))

    def test_missing_terminal_or_recovery_evidence_cannot_qualify(self):
        receipt = self.receipt()
        for key, value in (('stage', 'full_postflight_application_comparison'),
                ('ownerClosed', False), ('recoveryBaselinePreserved', None),
                ('originalCredentialsRestoredOnBothPaths', 1),
                ('replacementPrivateConfigIsCurrent', True),
                ('originalCredentialsAvailable', {'inventory': True, 'accounts': False})):
            with self.subTest(key=key):
                self.assertFalse(result.passed(receipt | {key: value}))
