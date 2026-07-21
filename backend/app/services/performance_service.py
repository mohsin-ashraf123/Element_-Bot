"""Performance views — today (live analysis) and week/month (stored records)."""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services import analysis_service, dashboard_service, settings_service
from app.services.report_builder_service import build_metrics_payload

Scope = Literal["today", "week", "month"]


def _scoped_summary(
    *,
    scope: Scope,
    completed: int,
    eligible: int,
    on_time: int,
    suggestions: int,
) -> str:
    if scope == "today":
        missed = eligible - completed
        return (
            f"Today: {completed}/{eligible} reports submitted, {on_time} on-time. "
            f"{suggestions} member(s) shared suggestions or issues."
        )
    label = "This week" if scope == "week" else "This month"
    on_time_pct = round(100.0 * on_time / completed, 1) if completed else 0.0
    return (
        f"{label}: {completed}/{eligible} member-days completed, "
        f"{on_time_pct:g}% on-time. {suggestions} suggestion report(s)."
    )


def get_performance(db: Session, *, scope: Scope = "today") -> dict[str, Any]:
    schedule = settings_service.get_setting(db, "schedule")
    zone_name = schedule.get("timezone", settings.timezone)

    if scope == "today":
        pairing = dashboard_service.today_room_messages(
            db, zone_name, room_id=settings.matrix_room_id
        )
        task = dashboard_service.today_task_messages(db, zone_name)
        result = analysis_service.analyze_today(
            db,
            pairing_messages=pairing,
            task_messages=task,
            zone_name=zone_name,
            llm=False,
        )
        return {
            "scope": "today",
            "period_label": f"Today — {result['date']}",
            "period_start": result["date"],
            "period_end": result["date"],
            "summary": result["summary"],
            "stats": result["stats"],
            "attendance": result["attendance"],
        }

    period_type = "weekly" if scope == "week" else "monthly"
    metrics = build_metrics_payload(db, period_type=period_type)
    members = metrics.get("members") or []

    attendance: list[dict[str, Any]] = []
    total_eligible = 0
    total_completed = 0
    total_on_time = 0
    total_suggestions = 0

    for row in members:
        eligible = int(row.get("eligible_days") or 0)
        completed = int(row.get("completed_days") or 0)
        on_time = int(row.get("on_time_days") or 0)
        clean = int(row.get("clean_days") or 0)
        suggestions = row.get("suggestions") or []
        sugg_count = len(suggestions)

        total_eligible += eligible
        total_completed += completed
        total_on_time += on_time
        total_suggestions += sugg_count

        if eligible == 0 or completed == 0:
            outcome = "missed"
        elif sugg_count > 0:
            outcome = "has_issues"
        elif clean == completed:
            outcome = "clean"
        else:
            outcome = "has_issues"

        attendance.append(
            {
                "member_id": row["member_id"],
                "name": row["name"],
                "eligible_days": eligible,
                "completed_days": completed,
                "on_time_days": on_time,
                "clean_days": clean,
                "completion_rate": row.get("completion_rate", 0.0),
                "on_time_rate": row.get("on_time_rate", 0.0),
                "clean_rate": row.get("clean_rate", 0.0),
                "current_streak": row.get("current_streak", 0),
                "suggestions_count": sugg_count,
                "completed": completed > 0,
                "on_time": on_time == completed and completed > 0,
                "outcome": outcome,
                "suggestion_summary": suggestions[-1][:160] if suggestions else None,
            }
        )

    attendance.sort(key=lambda r: (-r["completion_rate"], r["name"]))

    stats = {
        "total": len(members),
        "completed": total_completed,
        "eligible": total_eligible,
        "on_time": total_on_time,
        "missed": total_eligible - total_completed,
        "with_suggestions": sum(1 for r in attendance if r["suggestions_count"] > 0),
        "team_completion_rate": metrics.get("team", {}).get("completion_rate", 0.0),
        "team_on_time_rate": metrics.get("team", {}).get("on_time_rate", 0.0),
    }

    title = "This week" if scope == "week" else "This month"
    return {
        "scope": scope,
        "period_label": f"{title} — {metrics.get('period_label', '')}",
        "period_start": metrics.get("period_start"),
        "period_end": metrics.get("period_end"),
        "summary": _scoped_summary(
            scope=scope,
            completed=total_completed,
            eligible=total_eligible,
            on_time=total_on_time,
            suggestions=total_suggestions,
        ),
        "stats": stats,
        "attendance": attendance,
    }
