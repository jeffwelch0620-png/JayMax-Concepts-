"""Incomplete synthetic task snapshots must be held, never guessed or written."""
import unittest
from datetime import date
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
import prep_execution as execution
import staff_prep_tasks as staff


class ReviewGuardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.task, self.draft, self.member = uuid4(), uuid4(), uuid4()
        self.day = date(2026, 10, 1)
        self.conn = AsyncMock()
        self.task_row = dict(id=str(self.task), included=True, planned_quantity='1', product_id=str(uuid4()), recipe_version_id=str(uuid4()))
        self.progress = dict(task_id=str(self.task), closed=False, needs_review=False, reviewed_base_quantity='1')
        self.execution = dict(revision=1, status='released', draft_version_id=str(self.draft),
            draft=dict(id=str(self.draft), review_hash='a'*64), tasks=[self.task_row], task_progress=[self.progress],
            progress_supported=True, release=dict(id=str(uuid4())), completions=[], history=[])

    async def rejected_execution(self, action, expected=409):
        body = execution.Command(action=action, draft_version_id=self.draft, task_id=self.task,
            batch_event_id=uuid4() if action in ('link','reconcile') else None,
            link_event_id=uuid4() if action == 'reconcile' else None,
            task_complete=False if action == 'reconcile' else None, reason='Invented review')
        with patch.object(execution, 'ready', AsyncMock()), patch.object(execution, 'state', AsyncMock(return_value=self.execution)):
            with self.assertRaises(HTTPException) as error:
                await execution.preview(self.conn, 'berts', self.day, 'daily', body, 1)
        self.assertEqual(error.exception.status_code, expected)
        self.conn.execute.assert_not_called()

    async def test_missing_progress_holds_all_extended_commands(self):
        self.execution['task_progress'] = []
        for action in ('link','finish','reconcile'):
            with self.subTest(action=action): await self.rejected_execution(action)

    async def test_unknown_invalid_and_nonpositive_output_cannot_finish(self):
        for quantity in (None, 'bad', 'NaN', 'Infinity', '-Infinity', '0', '-1'):
            with self.subTest(quantity=quantity):
                self.progress['reviewed_base_quantity'] = quantity
                await self.rejected_execution('finish')

    async def test_missing_assignment_is_held_but_a_valid_first_assignment_is_allowed(self):
        body = staff.Assignment(task_id=self.task, staff_member_id=self.member, expected_revision=0, note='Invented assignment')
        state = dict(execution=self.execution, members=[dict(id=str(self.member), active=True)], assignments=[])
        with patch.object(staff, 'state', AsyncMock(return_value=state)):
            with self.assertRaises(HTTPException) as error:
                await staff.preview(self.conn, 'berts', self.day, 'daily', body)
            self.assertEqual(error.exception.status_code, 409)
            state['assignments'] = [dict(task_id=str(self.task), current=None)]
            result = await staff.preview(self.conn, 'berts', self.day, 'daily', body)
            self.assertIsNone(result['review']['predecessor_id'])
            self.assertEqual(result['review']['accountingEffect'], 'none')
        self.conn.execute.assert_not_called()

    async def test_missing_completion_record_holds_reconciliation(self):
        root, link, batch = uuid4(), uuid4(), uuid4()
        self.execution['history'] = [dict(id=str(link), action='link', task_id=str(self.task), batch_root_id=str(root))]
        self.conn.fetchrow.return_value = dict(id=batch,root_id=root,product_id=self.task_row['product_id'],business_date=self.day)
        body = execution.Command(action='reconcile',draft_version_id=self.draft,task_id=self.task,
            batch_event_id=batch,link_event_id=link,task_complete=False,reason='Invented review')
        with patch.object(execution,'ready',AsyncMock()),patch.object(execution,'state',AsyncMock(return_value=self.execution)):
            with self.assertRaises(HTTPException) as error:
                await execution.preview(self.conn,'berts',self.day,'daily',body,1)
        self.assertEqual(error.exception.status_code,409)
        self.conn.execute.assert_not_called()
