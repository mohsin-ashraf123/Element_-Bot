"""Scoped weekly/monthly reports — metrics + AI narrative + DB persistence."""

from __future__ import annotations

import json
import logging
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Member, PerformanceRecord, Report
from app.domain.calendar import is_working_day, parse_hhmm, parse_working_days, tz
from app.domain.constants import Outcome
from app.domain.scoring import DailyRecord, aggregate
from app.integrations.llm import template_narrative
from app.services import llm_service, settings_service, team_service

logger = logging.getLogger(__name__)

PeriodType = Literal["weekly", "monthly"]

_REPORTS_DIR = Path("./data/reports")


def _fmt_range(start: date, end: date) -> str:
    if start.month == end.month:
        return f"{start.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"
    return f"{start.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"


def period_bounds(
    period_type: PeriodType,
    *,
    ref: date | None = None,
    working_days_raw: str | list[str] | None = None,
) -> tuple[date, date]:
    """Return inclusive period start/end for weekly (Mon–Fri) or monthly."""
    today = ref or date.today()
    working = parse_working_days(working_days_raw or "mon,tue,wed,thu,fri")

    if period_type == "weekly":
        end = today
        while end.weekday() > 4:
            end -= timedelta(days=1)
        start = end - timedelta(days=end.weekday())
        return start, end

    # monthly — calendar month clipped to working days in range
    start = today.replace(day=1)
    last_day = monthrange(today.year, today.month)[1]
    end = today.replace(day=last_day)
    return start, end


def _records_for_period(
    db: Session, start: date, end: date, working_days: set[str]
) -> list[PerformanceRecord]:
    rows = db.scalars(
        select(PerformanceRecord)
        .where(
            PerformanceRecord.record_date >= start,
            PerformanceRecord.record_date <= end,
        )
        .order_by(PerformanceRecord.record_date.asc())
    ).all()
    return [r for r in rows if is_working_day(r.record_date, working_days)]


def _drop_open_today_misses(
    rows: list[PerformanceRecord],
    *,
    zone_name: str,
    cutoff: str,
    ref: datetime | None = None,
) -> list[PerformanceRecord]:
    """Don't penalise week/month stats for today until the timeliness cutoff passes."""
    now = ref or datetime.now(tz(zone_name))
    today = now.date()
    try:
        cutoff_t = parse_hhmm(cutoff)
    except ValueError:
        from datetime import time as dt_time

        cutoff_t = dt_time(23, 59)
    if now.time() >= cutoff_t:
        return rows
    return [
        r
        for r in rows
        if not (r.record_date == today and not r.completed and r.outcome == Outcome.MISSED.value)
    ]


def _daily_records(rows: list[PerformanceRecord]) -> list[DailyRecord]:
    out: list[DailyRecord] = []
    for r in rows:
        try:
            outcome = Outcome(r.outcome)
        except ValueError:
            outcome = Outcome.UNDETERMINED
        out.append(
            DailyRecord(
                member_id=r.member_id,
                record_date=r.record_date,
                completed=r.completed,
                on_time=r.on_time,
                outcome=outcome,
            )
        )
    return out


def _member_suggestions(
    rows: list[PerformanceRecord], members_by_id: dict[int, Member]
) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for r in rows:
        if r.outcome != Outcome.HAS_ISSUES.value or not r.raw_text:
            continue
        name = members_by_id.get(r.member_id)
        if not name:
            continue
        out.setdefault(name.name, []).append(r.raw_text.strip())
    return out


def build_metrics_payload(
    db: Session,
    *,
    period_type: PeriodType,
    ref: date | None = None,
) -> dict[str, Any]:
    """Deterministic scoped metrics — LLM narrates these numbers only."""
    schedule = settings_service.get_setting(db, "schedule")
    working = parse_working_days(schedule.get("working_days", "mon,tue,wed,thu,fri"))
    zone_name = schedule.get("timezone", "Asia/Karachi")
    cutoff = schedule.get("timeliness_cutoff", "23:59")
    start, end = period_bounds(period_type, ref=ref, working_days_raw=list(working))

    members = team_service.list_members(db, active_only=True)
    members_by_id = {m.id: m for m in members}
    perf_rows = _records_for_period(db, start, end, working)
    perf_rows = _drop_open_today_misses(perf_rows, zone_name=zone_name, cutoff=cutoff)
    team = aggregate(_daily_records(perf_rows))
    suggestions = _member_suggestions(perf_rows, members_by_id)

    member_rows: list[dict[str, Any]] = []
    for m in members:
        metrics = team.members.get(m.id)
        member_rows.append(
            {
                "member_id": m.id,
                "name": m.name,
                "role": m.role,
                "eligible_days": metrics.eligible_days if metrics else 0,
                "completed_days": metrics.completed_days if metrics else 0,
                "on_time_days": metrics.on_time_days if metrics else 0,
                "clean_days": metrics.clean_days if metrics else 0,
                "completion_rate": metrics.completion_rate if metrics else 0.0,
                "on_time_rate": metrics.on_time_rate if metrics else 0.0,
                "clean_rate": metrics.clean_rate if metrics else 0.0,
                "current_streak": metrics.current_streak if metrics else 0,
                "suggestions": suggestions.get(m.name, []),
            }
        )

    return {
        "period_type": period_type,
        "period_label": _fmt_range(start, end),
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "ingestion_live": len(perf_rows) > 0,
        "record_count": len(perf_rows),
        "team": {
            "completion_rate": team.team_completion_rate,
            "on_time_rate": team.team_on_time_rate,
            "clean_rate": team.team_clean_rate,
        },
        "members": member_rows,
    }


def _llm_scoped_analysis(
    db: Session, metrics: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    reason = llm_service.unavailable_reason(db)
    if reason:
        return None, reason

    system = """You are PairFlow's report analyst. You receive PRE-COMPUTED metrics and member suggestion texts.
Return ONLY valid JSON with this exact structure:
{
  "executive_summary": "2-3 sentences",
  "team_highlights": ["bullet", "..."],
  "areas_to_improve": ["bullet", "..."],
  "member_notes": [{"name": "...", "assessment": "one sentence", "standout": false}],
  "top_suggestions": [{"rank": 1, "member": "...", "summary": "...", "why_powerful": "..."}],
  "recommendations": ["actionable team recommendation", "..."],
  "narrative_short": "Under 400 chars for Element room caption"
}
Rules:
- NEVER recalculate or change the numeric rates provided.
- Rank suggestions by depth, specificity, and actionability.
- If no suggestions exist, top_suggestions may be empty.
- Be concise and professional."""

    user = json.dumps(metrics, ensure_ascii=False, indent=2)
    return llm_service.complete_json_with_error(
        system=system, user=user, db=db, temperature=0.25
    )


def _template_scoped_analysis(metrics: dict[str, Any]) -> dict[str, Any]:
    team = metrics["team"]
    period = metrics["period_label"]
    narrative = template_narrative(
        {
            "team_completion_rate": team["completion_rate"],
            "team_on_time_rate": team["on_time_rate"],
            "team_clean_rate": team["clean_rate"],
        },
        period,
    )
    with_suggestions = [m for m in metrics["members"] if m.get("suggestions")]
    return {
        "executive_summary": narrative,
        "team_highlights": [],
        "areas_to_improve": [],
        "member_notes": [],
        "top_suggestions": [],
        "recommendations": [],
        "narrative_short": narrative[:400],
        "template": True,
        "members_with_suggestions": len(with_suggestions),
    }


def generate_scoped_report(
    db: Session,
    *,
    period_type: PeriodType,
    ref: date | None = None,
) -> dict[str, Any]:
    """Build metrics, run AI analysis, persist Report row."""
    metrics = build_metrics_payload(db, period_type=period_type, ref=ref)
    llm_cfg = settings_service.get_setting(db, "llm")

    ai, llm_call_error = _llm_scoped_analysis(db, metrics)
    source = "llm"
    llm_error: str | None = None
    if ai is None:
        llm_error = llm_call_error or llm_service.unavailable_reason(db)
        if not llm_error:
            llm_error = "AI request failed — check OpenRouter key, model, and credits"
        ai = _template_scoped_analysis(metrics)
        source = "template"

    metrics["ai_analysis"] = ai
    if llm_error:
        metrics["llm_error"] = llm_error

    start = date.fromisoformat(metrics["period_start"])
    end = date.fromisoformat(metrics["period_end"])

    existing = db.scalar(
        select(Report).where(
            Report.period_type == period_type,
            Report.period_start == start,
            Report.period_end == end,
        )
    )

    narrative = ai.get("narrative_short") or ai.get("executive_summary") or ""
    row = existing or Report(
        period_type=period_type,
        period_start=start,
        period_end=end,
        metrics_json={},
        status="generated",
    )
    row.metrics_json = metrics
    row.narrative = narrative
    row.narrative_source = source
    row.llm_provider = llm_cfg.get("provider")
    row.llm_model = llm_cfg.get("model")
    row.llm_meta_json = ai

    if existing:
        db.merge(row)
    else:
        db.add(row)
    db.commit()
    db.refresh(row)

    return report_to_dict(row)


def report_to_dict(row: Report) -> dict[str, Any]:
    metrics = row.metrics_json or {}
    ai = metrics.get("ai_analysis") or row.llm_meta_json or {}
    return {
        "id": row.id,
        "period_type": row.period_type,
        "period_start": row.period_start.isoformat(),
        "period_end": row.period_end.isoformat(),
        "period_label": metrics.get("period_label")
        or _fmt_range(row.period_start, row.period_end),
        "metrics": metrics,
        "narrative": row.narrative,
        "narrative_source": row.narrative_source,
        "llm_provider": row.llm_provider,
        "llm_model": row.llm_model,
        "ai_analysis": ai,
        "status": row.status,
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
        "ingestion_live": metrics.get("ingestion_live", False),
        "llm_error": metrics.get("llm_error"),
    }


def list_reports(db: Session, *, limit: int = 20) -> list[dict]:
    rows = db.scalars(
        select(Report).order_by(Report.generated_at.desc()).limit(limit)
    ).all()
    return [report_to_dict(r) for r in rows]


def get_report(db: Session, report_id: int) -> dict | None:
    row = db.get(Report, report_id)
    return report_to_dict(row) if row else None


def latest_report(db: Session, period_type: PeriodType) -> dict | None:
    row = db.scalar(
        select(Report)
        .where(Report.period_type == period_type)
        .order_by(Report.generated_at.desc())
    )
    return report_to_dict(row) if row else None
