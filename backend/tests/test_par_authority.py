"""Pars: owner/admin only. Prepping above or below par needs sign-off (Jeff 2026-10-29)."""
import unittest
from types import SimpleNamespace

from fastapi import HTTPException

import server


def request(role, locations=('berts',)):
    token = server._token({'id': f'invented-{role}', 'email': f'{role}@example.invalid', 'role': role, 'locations': list(locations)})
    return SimpleNamespace(headers={'authorization': 'Bearer ' + token})


class ParAuthorityTests(unittest.TestCase):
    def test_only_the_owner_sets_or_changes_pars(self):
        self.assertTrue(server._purchase_actor(request('owner'), 'berts', True, 'par'))
        with self.assertRaises(HTTPException) as denied:
            server._purchase_actor(request('manager'), 'berts', True, 'par')
        self.assertEqual((denied.exception.status_code, denied.exception.detail), (403, server.PAR_OWNER_MESSAGE))

    def test_prepping_above_or_below_par_needs_sign_off(self):
        self.assertTrue(server._purchase_actor(request('owner'), 'berts', True, 'par_exception'))
        with self.assertRaises(HTTPException) as denied:
            server._purchase_actor(request('manager'), 'berts', True, 'par_exception')
        self.assertEqual(denied.exception.status_code, 403)
        self.assertIn('sign-off', denied.exception.detail)

    def test_ordinary_manager_work_is_unchanged(self):
        self.assertTrue(server._purchase_actor(request('manager'), 'berts', True))
        with self.assertRaises(HTTPException):
            server._purchase_actor(request('readonly'), 'berts', True)
