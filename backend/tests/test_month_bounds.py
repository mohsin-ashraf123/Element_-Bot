"""Month range helpers."""

from __future__ import annotations

from datetime import date

from app.domain.calendar import month_bounds


def test_month_bounds_from_first_to_today():
    start, end = month_bounds(date(2026, 7, 20))
    assert start == date(2026, 7, 1)
    assert end == date(2026, 7, 20)


def test_month_bounds_early_in_month():
    start, end = month_bounds(date(2026, 7, 3))
    assert start == date(2026, 7, 1)
    assert end == date(2026, 7, 3)


def test_last_working_day_of_month():
    from app.domain.calendar import is_last_working_day_of_month, parse_working_days

    working = parse_working_days("mon,tue,wed,thu,fri")
    assert is_last_working_day_of_month(date(2026, 7, 31), working)  # Fri
    assert not is_last_working_day_of_month(date(2026, 7, 30), working)  # Thu
    assert not is_last_working_day_of_month(date(2026, 7, 20), working)  # Mon
