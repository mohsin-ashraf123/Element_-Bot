"""Streak after a full working week — one on-time day at end = streak 1."""

from datetime import date

from app.domain.constants import Outcome
from app.domain.scoring import DailyRecord, aggregate


def test_full_week_ends_with_streak_one_if_only_friday_on_time():
    """Mon–Thu missed, Fri completed on-time → streak = 1."""
    records = [
        DailyRecord(1, date(2026, 7, 13), False, False, Outcome.MISSED),  # Mon
        DailyRecord(1, date(2026, 7, 14), False, False, Outcome.MISSED),  # Tue
        DailyRecord(1, date(2026, 7, 15), False, False, Outcome.MISSED),  # Wed
        DailyRecord(1, date(2026, 7, 16), True, True, Outcome.CLEAN),   # Thu (today in tests)
    ]
    team = aggregate(records)
    assert team.members[1].current_streak == 1


def test_full_week_all_on_time_streak_is_five():
    records = [
        DailyRecord(1, date(2026, 7, 7 + i), True, True, Outcome.CLEAN)
        for i in range(5)
    ]
    team = aggregate(records)
    assert team.members[1].current_streak == 5
