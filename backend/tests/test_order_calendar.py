"""Order calendar date logic (M4, Jeff 2026-11-01), offline."""
import unittest
from datetime import date, datetime, time, timezone
import order_calendar as cal

ROWS = [{'order_weekday': d, 'count_due': time(12), 'order_due': time(15), 'delivery_weekday': dl, 'vendor_ids': v, 'timezone_name': 'America/New_York'}
        for d, dl, v in ((6, 0, ['pfg', 'us_foods']), (2, 3, ['pfg', 'us_foods']), (3, 4, ['us_foods']))]


class OrderCalendarTests(unittest.TestCase):
    def test_the_cycle_is_today_on_an_order_day_otherwise_the_next_one(self):
        wed = datetime(2026, 11, 4, 20, 0, tzinfo=timezone.utc)                      # 3 PM Eastern, Wednesday
        day, row, _, today = cal.cycle(ROWS, wed)
        self.assertEqual((day, today, row['order_weekday']), (date(2026, 11, 4), date(2026, 11, 4), 2))
        mon = datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)
        self.assertEqual(cal.cycle(ROWS, mon)[0], date(2026, 11, 4))
        late_sat = datetime(2026, 11, 8, 3, 0, tzinfo=timezone.utc)                  # still Saturday in Eastern time
        self.assertEqual(cal.cycle(ROWS, late_sat)[0], date(2026, 11, 8))

    def test_delivery_days(self):
        self.assertEqual(cal.delivery(date(2026, 11, 1), ROWS[0]), date(2026, 11, 2))   # Sunday order, Monday delivery
        self.assertEqual(cal.delivery(date(2026, 11, 5), ROWS[2]), date(2026, 11, 6))   # Thursday order, Friday US Foods

    def test_due_overdue_done_late_upcoming(self):
        due = datetime(2026, 11, 4, 17, 0, tzinfo=timezone.utc)
        before, after = datetime(2026, 11, 4, 16, 0, tzinfo=timezone.utc), datetime(2026, 11, 4, 18, 0, tzinfo=timezone.utc)
        d = date(2026, 11, 4)
        self.assertEqual(cal.status(None, due, before, d, d), 'due')
        self.assertEqual(cal.status(None, due, after, d, d), 'overdue')
        self.assertEqual(cal.status(before, due, after, d, d), 'done')
        self.assertEqual(cal.status(after, due, after, d, d), 'late')
        self.assertEqual(cal.status(None, due, before, d, date(2026, 11, 3)), 'upcoming')
        self.assertEqual(cal.clock(time(15)), '3:00 PM')

    def test_a_late_count_needs_a_reason(self):
        self.assertEqual(cal.LateCount(cycle_date='2026-11-04', reason='  Walk-in repair ').reason, 'Walk-in repair')
        with self.assertRaises(ValueError): cal.LateCount(cycle_date='2026-11-04', reason='   ')
