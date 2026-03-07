"""
Tests for schedule-based lock: hard lock at Q1, unfreeze after race (race + 2h).
Run from risk-engine: python -m pytest tests/test_schedule_lock.py -v
Or: python -m unittest tests.test_schedule_lock -v
"""
from datetime import datetime, timezone, timedelta
import unittest
from unittest.mock import patch

# Mock schedule: round 1 Q1 and race, round 2 Q1 and race
Q1_R1 = datetime(2026, 3, 7, 5, 0, 0, tzinfo=timezone.utc)
RACE_R1 = datetime(2026, 3, 8, 4, 0, 0, tzinfo=timezone.utc)
RACE_END_R1 = RACE_R1 + timedelta(hours=2)
Q1_R2 = datetime(2026, 3, 14, 7, 0, 0, tzinfo=timezone.utc)
RACE_R2 = datetime(2026, 3, 15, 7, 0, 0, tzinfo=timezone.utc)
RACE_END_R2 = RACE_R2 + timedelta(hours=2)

MOCK_SCHEDULE = [
    {
        "round": "1",
        "qualifying_utc": Q1_R1,
        "race_start_utc": RACE_R1,
        "race_end_utc": RACE_END_R1,
        "race_name": "Australian GP",
    },
    {
        "round": "2",
        "qualifying_utc": Q1_R2,
        "race_start_utc": RACE_R2,
        "race_end_utc": RACE_END_R2,
        "race_name": "Chinese GP",
    },
]


class TestScheduleLock(unittest.TestCase):
    @patch("schedule.fetch_schedule")
    def test_can_edit_round1_before_q1(self, fetch):
        fetch.return_value = MOCK_SCHEDULE
        from schedule import can_edit_round
        now = Q1_R1 - timedelta(minutes=1)
        allowed, msg = can_edit_round("1", now=now)
        self.assertTrue(allowed, msg)

    @patch("schedule.fetch_schedule")
    def test_cannot_edit_round1_after_q1(self, fetch):
        fetch.return_value = MOCK_SCHEDULE
        from schedule import can_edit_round
        now = Q1_R1 + timedelta(minutes=1)
        allowed, msg = can_edit_round("1", now=now)
        self.assertFalse(allowed)
        self.assertTrue(msg and ("Q1" in msg or "lock" in msg.lower()))

    @patch("schedule.fetch_schedule")
    def test_cannot_edit_round2_before_race1_ended(self, fetch):
        fetch.return_value = MOCK_SCHEDULE
        from schedule import can_edit_round
        now = RACE_R1 + timedelta(hours=1)
        allowed, msg = can_edit_round("2", now=now)
        self.assertFalse(allowed)
        self.assertTrue("previous" in (msg or "").lower() or "race" in (msg or "").lower())

    @patch("schedule.fetch_schedule")
    def test_can_edit_round2_after_race1_ended_before_q1_r2(self, fetch):
        fetch.return_value = MOCK_SCHEDULE
        from schedule import can_edit_round
        now = RACE_END_R1 + timedelta(minutes=1)
        self.assertLess(now, Q1_R2)
        allowed, msg = can_edit_round("2", now=now)
        self.assertTrue(allowed, msg)

    @patch("schedule.fetch_schedule")
    def test_cannot_edit_round2_after_q1_r2(self, fetch):
        fetch.return_value = MOCK_SCHEDULE
        from schedule import can_edit_round
        now = Q1_R2 + timedelta(minutes=1)
        allowed, msg = can_edit_round("2", now=now)
        self.assertFalse(allowed)
        self.assertTrue("Q1" in (msg or "") or "lock" in (msg or "").lower())

    @patch("schedule.fetch_schedule")
    def test_next_editable_round(self, fetch):
        fetch.return_value = MOCK_SCHEDULE
        from schedule import get_next_editable_round
        self.assertEqual(get_next_editable_round(now=Q1_R1 - timedelta(hours=1)), "1")
        self.assertIsNone(get_next_editable_round(now=RACE_R1 + timedelta(hours=1)))
        self.assertEqual(get_next_editable_round(now=RACE_END_R1 + timedelta(minutes=1)), "2")
        self.assertIsNone(get_next_editable_round(now=Q1_R2 + timedelta(hours=1)))

    @patch("schedule.fetch_schedule")
    def test_is_round_locked(self, fetch):
        fetch.return_value = MOCK_SCHEDULE
        from schedule import is_round_locked
        self.assertFalse(is_round_locked("1", now=Q1_R1 - timedelta(seconds=1)))
        self.assertTrue(is_round_locked("1", now=Q1_R1 + timedelta(seconds=1)))
        self.assertFalse(is_round_locked("2", now=Q1_R2 - timedelta(seconds=1)))
        self.assertTrue(is_round_locked("2", now=Q1_R2 + timedelta(seconds=1)))


if __name__ == "__main__":
    unittest.main()
