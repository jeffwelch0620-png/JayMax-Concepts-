"""Response projection must not mutate the audit facts or change opaque hashes."""
import copy
import unittest
from staff_response import staff_view


class StaffResponseTests(unittest.TestCase):
    def test_history_review_nested_identity_projection_preserves_facts_and_hashes(self):
        source = {'sheet': {'issued_by': 'manager@example.invalid', 'id': 'sheet'},
                  'history': [{'submitted_by': 'staff@example.invalid',
                               'review_snapshot': {'sources': {'assignment': {'recorded_by': 'other@example.invalid'}},
                                                   'submitted_by': 'staff@example.invalid',
                                                   'batch': {'actor': 'manager@example.invalid'}}}],
                  'reviewHash': 'a'*64, 'request_fingerprint': 'b'*64,
                  'counter_name': 'Claimed cook', 'quantity': '0', 'email': 'hidden@example.invalid'}
        before = copy.deepcopy(source)
        projected = staff_view(source)
        self.assertEqual(source, before)
        self.assertNotIn('example.invalid', str(projected))
        self.assertEqual(projected['reviewHash'], source['reviewHash'])
        self.assertEqual(projected['request_fingerprint'], source['request_fingerprint'])
        self.assertEqual(projected['counter_name'], 'Claimed cook')
        self.assertEqual(projected['quantity'], '0')
