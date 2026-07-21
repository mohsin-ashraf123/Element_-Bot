"""Tests for deterministic scoring/aggregation (RULES §15, §17)."""

from datetime import date

from app.domain.constants import Outcome
from app.domain.scoring import DailyRecord, aggregate


def _rec(day, completed, on_time, outcome):
    return DailyRecord(
        member_id=1,
        record_date=date(2026, 7, day),
        completed=completed,
        on_time=on_time,
        outcome=outcome,
    )


def test_rates_computed_correctly():
    records = [
        _rec(13, True, True, Outcome.CLEAN),
        _rec(14, True, False, Outcome.HAS_ISSUES),
        _rec(15, False, False, Outcome.MISSED),
    ]
    team = aggregate(records)
    m = team.members[1]
    assert m.eligible_days == 3
    assert m.completed_days == 2
    assert m.completion_rate == round(100 * 2 / 3, 1)
    assert m.on_time_rate == 50.0  # 1 of 2 completed were on-time
    assert m.clean_rate == 50.0  # 1 of 2 completed were clean


def test_undetermined_excluded_from_eligible_days():
    records = [
        _rec(13, True, True, Outcome.CLEAN),
        _rec(14, False, False, Outcome.UNDETERMINED),
    ]
    team = aggregate(records)
    m = team.members[1]
    assert m.eligible_days == 1  # undetermined day not counted
    assert m.completion_rate == 100.0


def test_current_streak_counts_back_from_latest():
    records = [
        _rec(13, True, True, Outcome.CLEAN),
        _rec(14, False, False, Outcome.MISSED),
        _rec(15, True, True, Outcome.CLEAN),
        _rec(16, True, True, Outcome.HAS_ISSUES),
    ]
    team = aggregate(records)
    assert team.members[1].current_streak == 2


def test_team_metrics_aggregate_across_members():
    records = [
        DailyRecord(1, date(2026, 7, 13), True, True, Outcome.CLEAN),
        DailyRecord(2, date(2026, 7, 13), False, False, Outcome.MISSED),
    ]
    team = aggregate(records)
    assert team.team_completion_rate == 50.0
