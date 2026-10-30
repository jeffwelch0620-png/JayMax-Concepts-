"""Pars: owners and the Ops Lead only. Prepping above or below par needs sign-off (Jeff 2026-10-29/30)."""
import unittest
from types import SimpleNamespace

from fastapi import HTTPException

import positions
import server


def request(role, locations=('berts',), position=None):
    token = server._token({'id': f'invented-{role}-{position}', 'email': f'{role}@example.invalid', 'role': role,
                           'locations': list(locations), 'position': position})
    return SimpleNamespace(headers={'authorization': 'Bearer ' + token})


def denied(req, require, store='berts'):
    with unittest.TestCase().assertRaises(HTTPException) as caught:
        server._purchase_actor(req, store, True, require)
    return caught.exception


class ParAuthorityTests(unittest.TestCase):
    def test_only_owners_and_the_ops_lead_set_or_change_pars(self):
        for req in (request('owner'), request('owner', position='OWN'), request('owner', position='OPS')):
            self.assertTrue(server._purchase_actor(req, 'berts', True, 'par'))
        for req in (request('manager'), request('manager', position='GM')):
            e = denied(req, 'par')
            self.assertEqual((e.status_code, e.detail), (403, server.PAR_OWNER_MESSAGE))

    def test_prepping_above_or_below_par_needs_a_gm_or_above(self):
        for req in (request('owner'), request('owner', position='OPS'), request('manager', position='GM')):
            self.assertTrue(server._purchase_actor(req, 'berts', True, 'par_exception'))
        for req in (request('manager'), request('manager', position='KM'), request('manager', position='SL-BOH')):
            e = denied(req, 'par_exception')
            self.assertEqual(e.status_code, 403); self.assertIn('sign-off', e.detail)

    def test_bulk_runs_above_or_below_par_need_the_ops_lead_or_an_owner(self):
        self.assertTrue(server._purchase_actor(request('owner', position='OPS'), 'rudds', True, 'bulk_par_exception'))
        e = denied(request('manager', ('rudds',), position='GM'), 'bulk_par_exception', 'rudds')
        self.assertIn('Operations & Integration Lead', e.detail)

    def test_ordinary_manager_work_is_unchanged(self):
        self.assertTrue(server._purchase_actor(request('manager'), 'berts', True))
        with self.assertRaises(HTTPException):
            server._purchase_actor(request('readonly'), 'berts', True)


class PositionTests(unittest.TestCase):
    def test_every_position_belongs_to_one_access_class_and_every_permission_names_known_positions(self):
        self.assertTrue(all(cls in ('owner', 'manager', 'staff') for cls, _, _ in positions.POSITIONS.values()))
        for codes in positions.PERMISSIONS.values():
            self.assertTrue(codes <= set(positions.POSITIONS))
        self.assertEqual(set(positions.DENIED), set(positions.PERMISSIONS))

    def test_bulk_separation_of_duties(self):
        bpm = {'role': 'manager', 'position': 'BPM'}
        km = {'role': 'manager', 'position': 'KM'}
        self.assertTrue(positions.can(bpm, 'bulk_fulfill')); self.assertFalse(positions.can(bpm, 'bulk_request'))
        self.assertTrue(positions.can(km, 'bulk_request')); self.assertFalse(positions.can(km, 'bulk_fulfill'))
        for sl in ('SL-BOH', 'SL-FOH'):
            self.assertFalse(positions.can({'role': 'manager', 'position': sl}, 'bulk_request'))

    def test_staff_work_wages_and_legacy_logins(self):
        self.assertTrue(positions.can({'role': 'manager', 'position': 'SL-BOH'}, 'accept_staff_work'))
        self.assertFalse(positions.can({'role': 'manager', 'position': 'SL-FOH'}, 'accept_staff_work'))
        self.assertFalse(positions.can({'role': 'manager', 'position': 'SL-BOH'}, 'edit_staff_work'))
        self.assertTrue(positions.can({'role': 'manager', 'position': 'GM'}, 'see_wages'))
        self.assertFalse(positions.can({'role': 'manager', 'position': 'KM'}, 'see_wages'))
        # No position: exactly what the access class allowed before positions.
        self.assertTrue(positions.can({'role': 'manager'}, 'bulk_fulfill'))
        self.assertFalse(positions.can({'role': 'manager'}, 'par_exception'))
        self.assertTrue(all(positions.can({'role': 'owner'}, p) for p in positions.PERMISSIONS))
        self.assertFalse(any(positions.can({'role': 'readonly'}, p) for p in positions.PERMISSIONS))
        # A position that doesn't match the access class grants nothing beyond the class.
        self.assertFalse(positions.can({'role': 'manager', 'position': 'OPS'}, 'set_pars'))

    def test_a_session_carries_its_position(self):
        token = server._token({'id': 'x', 'email': 'x@example.invalid', 'role': 'manager', 'locations': ['berts'], 'position': 'KM'})
        self.assertEqual(server._decode_token(token)['position'], 'KM')
