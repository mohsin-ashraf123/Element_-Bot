"""Tests for working-day / cutoff / timezone logic (RULES §9, §14)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.domain.calendar import (
    is_on_time,
    is_working_day,
    next_working_day,
    parse_hhmm,
    parse_working_days,
)

PKT = "Asia/Karachi"
WORKING = {"mon", "tue", "wed", "thu", "fri"}


def test_parse_working_days_defaults_when_empty():
    assert parse_working_days("") == WORKING
    assert parse_working_days("mon,wed,fri") == {"mon", "wed", "fri"}


def test_is_working_day():
    # 2026-07-15 is a Wednesday, 2026-07-18 is a Saturday.
    assert is_working_day(date(2026, 7, 15), WORKING) is True
    assert is_working_day(date(2026, 7, 18), WORKING) is False


def test_next_working_day_skips_weekend():
    friday = date(2026, 7, 17)
    assert next_working_day(friday, WORKING) == date(2026, 7, 20)  # Monday


def test_on_time_before_and_after_cutoff():
    cutoff = parse_hhmm("23:59")
    rec_date = date(2026, 7, 15)
    early = datetime(2026, 7, 15, 10, 30, tzinfo=ZoneInfo(PKT))
    late = datetime(2026, 7, 16, 0, 30, tzinfo=ZoneInfo(PKT))
    assert is_on_time(early, rec_date, cutoff, PKT) is True
    assert is_on_time(late, rec_date, cutoff, PKT) is False
