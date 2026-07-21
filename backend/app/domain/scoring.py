"""Deterministic performance scoring (RULES §15).

Turns raw per-member/per-day performance records into rates, counts and
streaks. Every number in a report comes from here — the LLM never computes
figures, it only narrates these (ARCHITECTURE §4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .constants import Outcome


@dataclass(frozen=True)
class DailyRecord:
    """A single member's outcome on a single eligible working day."""

    member_id: int
    record_date: date
    completed: bool
    on_time: bool
    outcome: Outcome


@dataclass
class MemberMetrics:
    member_id: int
    eligible_days: int = 0
    completed_days: int = 0
    on_time_days: int = 0
    clean_days: int = 0
    current_streak: int = 0

    @property
    def completion_rate(self) -> float:
        return _rate(self.completed_days, self.eligible_days)

    @property
    def on_time_rate(self) -> float:
        return _rate(self.on_time_days, self.completed_days)

    @property
    def clean_rate(self) -> float:
        return _rate(self.clean_days, self.completed_days)


@dataclass
class TeamMetrics:
    members: dict[int, MemberMetrics] = field(default_factory=dict)

    @property
    def team_completion_rate(self) -> float:
        elig = sum(m.eligible_days for m in self.members.values())
        done = sum(m.completed_days for m in self.members.values())
        return _rate(done, elig)

    @property
    def team_on_time_rate(self) -> float:
        done = sum(m.completed_days for m in self.members.values())
        ontime = sum(m.on_time_days for m in self.members.values())
        return _rate(ontime, done)

    @property
    def team_clean_rate(self) -> float:
        done = sum(m.completed_days for m in self.members.values())
        clean = sum(m.clean_days for m in self.members.values())
        return _rate(clean, done)


def _rate(numerator: int, denominator: int) -> float:
    """Safe percentage rounded to one decimal; 0.0 when denominator is 0."""
    if denominator <= 0:
        return 0.0
    return round(100.0 * numerator / denominator, 1)


def aggregate(records: list[DailyRecord]) -> TeamMetrics:
    """Aggregate raw daily records into per-member and team metrics.

    A report counts toward completion only if `completed` is True and its
    outcome is a genuine report (not `undetermined`, which is a system fault
    and must never be scored as a miss — RULES R17.2).
    """
    by_member: dict[int, list[DailyRecord]] = {}
    for rec in records:
        by_member.setdefault(rec.member_id, []).append(rec)

    team = TeamMetrics()
    for member_id, recs in by_member.items():
        recs_sorted = sorted(recs, key=lambda r: r.record_date)
        metrics = MemberMetrics(member_id=member_id)
        for rec in recs_sorted:
            if rec.outcome is Outcome.UNDETERMINED:
                # Excluded from eligible days — not the member's fault.
                continue
            metrics.eligible_days += 1
            if rec.completed:
                metrics.completed_days += 1
                if rec.on_time:
                    metrics.on_time_days += 1
                if rec.outcome is Outcome.CLEAN:
                    metrics.clean_days += 1
        metrics.current_streak = _current_streak(recs_sorted)
        team.members[member_id] = metrics
    return team


def _current_streak(records_sorted: list[DailyRecord]) -> int:
    """Consecutive on-time completions counting back from the latest day."""
    streak = 0
    for rec in reversed(records_sorted):
        if rec.outcome is Outcome.UNDETERMINED:
            continue  # neutral: does not break or extend the streak
        if rec.completed and rec.on_time:
            streak += 1
        else:
            break
    return streak
