from datetime import date
from unittest import TestCase

from app.core.schedule_dates import inclusive_duration_days


class InclusiveDurationTests(TestCase):
    def test_required_calendar_date_examples(self):
        self.assertEqual(inclusive_duration_days(date(2026, 7, 14), date(2026, 7, 16)), 3)
        self.assertEqual(inclusive_duration_days(date(2026, 7, 17), date(2026, 7, 20)), 4)
        self.assertEqual(inclusive_duration_days(date(2026, 7, 14), date(2026, 7, 14)), 1)

    def test_end_before_start_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "on or after"):
            inclusive_duration_days(date(2026, 7, 16), date(2026, 7, 14))
