"""Week range helpers."""

from __future__ import annotations

from datetime import date

from app.domain.calendar import week_bounds


def test_week_bounds_monday_through_friday():
    start, end = week_bounds(date(2026, 7, 20))  # Monday
    assert start == date(2026, 7, 20)
    assert end == date(2026, 7, 20)


def test_week_bounds_wednesday_spans_mon_to_wed():
    start, end = week_bounds(date(2026, 7, 22))  # Wednesday
    assert start == date(2026, 7, 20)
    assert end == date(2026, 7, 22)


def test_week_bounds_saturday_clips_to_friday():
    start, end = week_bounds(date(2026, 7, 25))  # Saturday
    assert start == date(2026, 7, 20)
    assert end == date(2026, 7, 24)
