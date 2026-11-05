"""EP-07 self-acceptance setting (Jeff 2026-11-05): staff work only, never orders."""
import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from workflow_integrity import require_independent, require_independent_staff_work


class SelfAcceptanceTests(unittest.TestCase):
    def test_staff_work_follows_the_setting(self):
        with patch.dict(os.environ, {'SELF_ACCEPTANCE_ENABLED': 'true'}):
            require_independent_staff_work('manager', ['manager'])
        for value in ('false', ''):
            with patch.dict(os.environ, {'SELF_ACCEPTANCE_ENABLED': value}), self.assertRaises(HTTPException) as refused:
                require_independent_staff_work('manager', ['manager'])
            self.assertEqual(refused.exception.status_code, 403)

    def test_off_when_not_set(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(HTTPException):
            require_independent_staff_work('manager', ['manager'])

    def test_orders_never_allow_it(self):
        with patch.dict(os.environ, {'SELF_ACCEPTANCE_ENABLED': 'true'}), self.assertRaises(HTTPException):
            require_independent('manager', ['manager'])

    def test_someone_else_always_may_accept(self):
        with patch.dict(os.environ, {'SELF_ACCEPTANCE_ENABLED': 'false'}):
            require_independent_staff_work('second-manager', ['manager'])


if __name__ == '__main__':
    unittest.main()
