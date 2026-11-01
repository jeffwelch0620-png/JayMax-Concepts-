"""Order calendar date logic and schedule changes (M4, Jeff 2026-11-01), offline."""
import unittest
from datetime import date, datetime, time, timezone
from pydantic import ValidationError
import order_calendar as cal

ROWS = [{'order_weekday': d, 'count_due': time(12), 'order_due': time(15), 'delivery_weekday': dl, 'vendor_ids': v, 'timezone_name': 'America/New_York'}
        for d, dl, v in ((6, 0, ['pfg', 'us_foods']), (2, 3, ['pfg', 'us_foods']), (3, 4, ['us_foods']))]
SUN, WED, THU = date(2026, 11, 1), date(2026, 11, 4), date(2026, 11, 5)


class OrderCalendarTests(unittest.TestCase):
    def test_weekly_cycles_and_delivery_days(self):
        cycles = cal.effective(ROWS, {}, SUN, 7)
        self.assertEqual(sorted(cycles), [SUN, WED, THU])
        self.assertEqual(cycles[SUN]['delivery'], date(2026, 11, 2))      # Sunday order, Monday delivery
        self.assertEqual(cycles[THU]['delivery'], date(2026, 11, 6))      # Thursday order, Friday US Foods
        self.assertEqual(cycles[THU]['row']['vendor_ids'], ['us_foods'])

    def test_skipped_and_moved_cycles(self):
        exc = {THU: {'kind': 'skip'}, SUN: {'kind': 'move', 'moved_to': date(2026, 10, 31), 'delivery_date': date(2026, 11, 2)}}
        cycles = cal.effective(ROWS, exc, date(2026, 10, 31), 7)
        self.assertEqual(sorted(cycles), [date(2026, 10, 31), WED])       # Sunday's cycle held Saturday; Thursday skipped
        self.assertEqual(cycles[date(2026, 10, 31)]['moved_from'], SUN)
        self.assertEqual(cycles[date(2026, 10, 31)]['delivery'], date(2026, 11, 2))
        self.assertEqual(cycles[date(2026, 10, 31)]['row']['order_weekday'], 6)

    def test_due_overdue_done_late_upcoming(self):
        due = datetime(2026, 11, 4, 17, 0, tzinfo=timezone.utc)
        before, after = datetime(2026, 11, 4, 16, 0, tzinfo=timezone.utc), datetime(2026, 11, 4, 18, 0, tzinfo=timezone.utc)
        self.assertEqual(cal.status(None, due, before, WED, WED), 'due')
        self.assertEqual(cal.status(None, due, after, WED, WED), 'overdue')
        self.assertEqual(cal.status(before, due, after, WED, WED), 'done')
        self.assertEqual(cal.status(after, due, after, WED, WED), 'late')
        self.assertEqual(cal.status(None, due, before, WED, date(2026, 11, 3)), 'upcoming')
        self.assertEqual(cal.clock(time(15)), '3:00 PM')

    def test_a_late_count_needs_a_reason(self):
        self.assertEqual(cal.LateCount(cycle_date='2026-11-04', reason='  Walk-in repair ').reason, 'Walk-in repair')
        with self.assertRaises(ValueError): cal.LateCount(cycle_date='2026-11-04', reason='   ')

    def test_the_schedule_an_order_was_placed_under(self):
        at = datetime(2026, 11, 4, 18, tzinfo=timezone.utc)
        changes = [{'order_weekday': 2, 'day_before': {'order_weekday': 2, 'delivery_weekday': 3, 'vendor_ids': ['pfg']}, 'changed_at': datetime(2026, 11, 5, tzinfo=timezone.utc)},
                   {'order_weekday': 0, 'day_before': None, 'changed_at': datetime(2026, 11, 6, tzinfo=timezone.utc)}]
        now = [r for r in ROWS if r['order_weekday'] != 2] + [{**ROWS[0], 'order_weekday': 0, 'delivery_weekday': 1}]
        then = {r['order_weekday']: r for r in cal.rows_at(now, changes, at)}
        self.assertEqual(sorted(then), [2, 3, 6])                         # Wednesday back (removed later); Monday not added yet
        self.assertEqual(then[2]['vendor_ids'], ['pfg'])
        self.assertEqual(cal.effective(list(then.values()), {}, WED, 1)[WED]['delivery'], THU)
        self.assertEqual({r['order_weekday'] for r in cal.rows_at(now, changes, datetime(2026, 11, 7, tzinfo=timezone.utc))}, {0, 3, 6})

    def test_schedule_change_shapes(self):
        ok = [dict(kind='set_day', order_weekday=0, count_due='11:00', order_due='14:00', delivery_weekday=1, vendor_ids=['pfg'], reason='New Monday order'),
              dict(kind='remove_day', order_weekday=3, reason='US Foods now Wednesday only'),
              dict(kind='skip', cycle_date='2026-11-26', reason='Thanksgiving'),
              dict(kind='move', cycle_date='2026-11-26', moved_to='2026-11-25', delivery_date='2026-11-27', reason='Thanksgiving'),
              dict(kind='restore', cycle_date='2026-11-26', reason='Supplier delivering after all')]
        for body in ok: cal.ScheduleChange(**body)
        bad = [dict(kind='set_day', order_weekday=0, count_due='15:00', order_due='14:00', delivery_weekday=1, vendor_ids=['pfg'], reason='x'),
               dict(kind='set_day', order_weekday=0, count_due='11:00', order_due='14:00', delivery_weekday=1, vendor_ids=['pfg', 'pfg'], reason='x'),
               dict(kind='set_day', order_weekday=0, count_due='11:00', order_due='14:00', delivery_weekday=1, vendor_ids=[], reason='x'),
               dict(kind='remove_day', order_weekday=3, cycle_date='2026-11-26', reason='x'),
               dict(kind='skip', cycle_date='2026-11-26', moved_to='2026-11-25', reason='x'),
               dict(kind='move', cycle_date='2026-11-26', moved_to='2026-12-04', delivery_date='2026-12-05', reason='x'),
               dict(kind='move', cycle_date='2026-11-26', moved_to='2026-11-25', delivery_date='2026-11-24', reason='x'),
               dict(kind='skip', cycle_date='2026-11-26', reason='   '),
               dict(kind='skip', order_weekday=3, cycle_date='2026-11-26', reason='x')]
        for body in bad:
            with self.assertRaises(ValidationError, msg=body): cal.ScheduleChange(**body)
