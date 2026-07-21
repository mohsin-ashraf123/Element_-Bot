"""Tests for open-today exclusion in scoped metrics."""

from __future__ import annotations

from datetime import date, datetime

from app.db.models import PerformanceRecord
from app.domain.constants import Outcome
from app.services.report_builder_service import _drop_open_today_misses


def _row(member_id: int, day: date, *, completed: bool) -> PerformanceRecord:
    return PerformanceRecord(
        member_id=member_id,
        record_date=day,
        completed=completed,
        on_time=completed,
        outcome=Outcome.CLEAN.value if completed else Outcome.MISSED.value,
    )


def test_open_today_misses_excluded_before_cutoff():
    today = date(2026, 7, 21)
    rows = [
        _row(1, date(2026, 7, 20), completed=True),
        _row(1, today, completed=False),
    ]
    ref = datetime(2026, 7, 21, 11, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Karachi"))
    out = _drop_open_today_misses(rows, zone_name="Asia/Karachi", cutoff="23:59", ref=ref)
    assert len(out) == 1
    assert out[0].record_date == date(2026, 7, 20)


def test_open_today_misses_count_after_cutoff():
    today = date(2026, 7, 21)
    rows = [
        _row(1, date(2026, 7, 20), completed=True),
        _row(1, today, completed=False),
    ]
    ref = datetime(2026, 7, 21, 23, 59, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Karachi"))
    out = _drop_open_today_misses(rows, zone_name="Asia/Karachi", cutoff="23:59", ref=ref)
    assert len(out) == 2
