"""Working-day, cutoff and timezone logic (RULES §9, §14).

All scheduling is anchored to a configured timezone (default Asia/Karachi).
Time is always passed in by the caller — this module never reads the clock,
keeping it deterministic and testable.
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from .constants import DEFAULT_WORKING_DAYS, WEEKDAY_CODES


def parse_working_days(raw: str | list[str]) -> set[str]:
    """Normalise a working-days spec (e.g. 'mon,tue,wed') into a code set."""
    if isinstance(raw, str):
        parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    else:
        parts = [p.strip().lower() for p in raw]
    codes = {p for p in parts if p in WEEKDAY_CODES}
    return codes or set(DEFAULT_WORKING_DAYS)


def parse_hhmm(raw: str) -> time:
    """Parse a 'HH:MM' 24-hour string into a `time`."""
    hh, mm = raw.strip().split(":")
    return time(hour=int(hh), minute=int(mm))


def tz(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def is_working_day(day: date, working_days: set[str]) -> bool:
    """True if `day` falls on a configured working weekday."""
    return WEEKDAY_CODES[day.weekday()] in working_days


def next_working_day(day: date, working_days: set[str]) -> date:
    """The first working day strictly after `day`."""
    from datetime import timedelta

    cursor = day + timedelta(days=1)
    for _ in range(14):  # guard against an empty working-day set
        if is_working_day(cursor, working_days):
            return cursor
        cursor += timedelta(days=1)
    raise ValueError("no working day found within two weeks")


def week_bounds(ref: date) -> tuple[date, date]:
    """Mon–Fri week containing ``ref`` (end clipped to ``ref`` on weekends)."""
    from datetime import timedelta

    end = ref
    while end.weekday() > 4:
        end -= timedelta(days=1)
    start = end - timedelta(days=end.weekday())
    return start, end


def month_bounds(ref: date) -> tuple[date, date]:
    """Calendar month containing ``ref`` (1st through ``ref``, inclusive)."""
    return ref.replace(day=1), ref


def is_last_working_day_of_month(day: date, working_days: set[str]) -> bool:
    """True when no later working day remains in the same calendar month."""
    from calendar import monthrange
    from datetime import timedelta

    if not is_working_day(day, working_days):
        return False
    last_dom = monthrange(day.year, day.month)[1]
    cursor = day + timedelta(days=1)
    while cursor.month == day.month and cursor.day <= last_dom:
        if is_working_day(cursor, working_days):
            return False
        cursor += timedelta(days=1)
    return True


def send_datetime_for(day: date, send_time: time, timezone: str) -> datetime:
    """The timezone-aware datetime the daily message should send on `day`."""
    return datetime.combine(day, send_time, tzinfo=tz(timezone))


def is_on_time(
    posted_at: datetime,
    record_date: date,
    cutoff: time,
    timezone: str,
) -> bool:
    """Whether a report `posted_at` counts as on-time (RULES R14.2 / OD-2).

    On-time = at/before the cutoff on the report's working day, in `timezone`.
    """
    zone = tz(timezone)
    local = posted_at.astimezone(zone)
    cutoff_dt = datetime.combine(record_date, cutoff, tzinfo=zone)
    return local <= cutoff_dt
