"""Dashboard aggregation — real status, no placeholders."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import ElementEvent, Member, PairingRound
from app.domain.calendar import is_working_day, month_bounds, next_working_day, parse_hhmm, parse_working_days, send_datetime_for, tz
from app.services import analysis_service, element_health, settings_service, team_service

logger = logging.getLogger(__name__)


def build_status(db: Session) -> dict:
    """Fast dashboard status — no Matrix E2EE timeline fetch."""
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    bot = settings_service.get_setting(db, "bot")
    element = element_health.check()
    members = team_service.list_members(db, active_only=True)
    config_gaps = sum(1 for m in members if team_service.has_config_gap(m))

    last_send = db.scalar(
        select(ElementEvent.sent_at)
        .where(ElementEvent.kind == "daily_message", ElementEvent.status == "sent")
        .order_by(ElementEvent.sent_at.desc())
    )
    if last_send is None:
        last_send = db.scalar(
            select(PairingRound.created_at)
            .where(PairingRound.status == "sent")
            .order_by(PairingRound.created_at.desc())
        )

    schedule = settings_service.get_setting(db, "schedule")
    zone_name = schedule.get("timezone", settings.timezone)
    next_send = _next_send_at(db, schedule)

    alerts: list[str] = []
    if not element["configured"]:
        alerts.append("Matrix credentials not fully configured")
    elif not element["connected"]:
        alerts.append(element.get("error") or "Matrix login failed")
    elif not element["joined"]:
        alerts.append("Bot is not joined to the pairing room")
    elif settings.matrix_task_room_id.strip() and not element.get("task_room_joined"):
        alerts.append("Bot is not joined to the task room — invite bot to read task assignments")
    if config_gaps:
        alerts.append(f"{config_gaps} member(s) missing Matrix ID")

    return {
        "state": bot.get("status", "running"),
        "element_configured": element["configured"],
        "element_connected": element["connected"],
        "element_joined": element["joined"],
        "e2ee_store_ready": element["e2ee_store_ready"],
        "database_connected": db_ok,
        "active_members": len(members),
        "config_gaps": config_gaps,
        "last_send_at": last_send.isoformat() if last_send else None,
        "next_send_at": next_send.isoformat() if next_send else None,
        "homeserver": element.get("homeserver"),
        "room_id": element.get("room_id"),
        "room_label": element.get("room_label"),
        "room_name": element.get("room_name"),
        "task_room_id": element.get("task_room_id"),
        "task_room_label": element.get("task_room_label"),
        "task_room_name": element.get("task_room_name"),
        "task_room_joined": element.get("task_room_joined"),
        "element_error": element.get("error"),
        "alerts": alerts,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def build_fast_feed(db: Session, *, zone_name: str | None = None) -> list[dict]:
    """Instant pairing-room feed: DB bot posts + persisted member messages."""
    from app.services import matrix_room_feed

    schedule = settings_service.get_setting(db, "schedule")
    zone = zone_name or schedule.get("timezone", settings.timezone)
    pairing_id = settings.matrix_room_id
    return matrix_room_feed.merge_member_cache(
        pairing_id,
        _bot_events_from_db(db, zone),
        zone_name=zone,
    )


def build_feed(db: Session, *, force: bool = False) -> dict:
    """Room timelines + analysis — Element-style room mirror, then analyze today."""
    from app.services import matrix_room_feed
    from datetime import timedelta

    schedule = settings_service.get_setting(db, "schedule")
    zone_name = schedule.get("timezone", settings.timezone)

    mxid_to_name = {
        m.matrix_user_id: m.name
        for m in team_service.list_members(db)
        if m.matrix_user_id
    }
    mxid_to_name.setdefault("@mohsinashraf:matrix.org", "Mohsin")

    pairing_id = settings.matrix_room_id
    task_id = settings.matrix_task_room_id.strip()
    today = datetime.now(tz(zone_name)).date()
    month_start, month_end = month_bounds(today)
    # Pull a few days of Matrix history so the phone preview matches Element
    # (no "today-only" cut on the room display).
    sync_start = today - timedelta(days=7)

    # --- Display: full recent room timeline (same order as Element), no day filter.
    db_bot = _bot_events_from_db(db, zone_name, days=7)
    room_messages = matrix_room_feed.combine_feed_sources(
        matrix_room_feed.recent_room_timeline(pairing_id, zone_name=zone_name, limit=50),
        db_bot,
    )

    task_messages: list[dict] = []
    if task_id:
        task_messages = matrix_room_feed.recent_room_timeline(
            task_id, zone_name=zone_name, limit=50
        )

    # --- Analysis / performance still use today's slice of the same mirror.
    today_for_analysis = matrix_room_feed.filter_messages_for_day(
        room_messages, day=today, zone_name=zone_name
    )
    task_for_analysis = matrix_room_feed.filter_messages_for_day(
        task_messages, day=today, zone_name=zone_name
    ) or task_messages

    # --- Keep the DB fresh in the background (last 7 days of both rooms).
    matrix_room_feed.schedule_refresh(
        room_id=pairing_id,
        zone_name=zone_name,
        mxid_to_name=mxid_to_name,
        force=force,
        range_start=sync_start,
        range_end=today,
    )
    if task_id:
        matrix_room_feed.schedule_refresh(
            room_id=task_id,
            zone_name=zone_name,
            mxid_to_name=mxid_to_name,
            force=force,
            range_start=month_start,
            range_end=month_end,
        )

    refreshing = matrix_room_feed.feed_incomplete(today_for_analysis)

    try:
        # Feed stays heuristic (instant). LLM enrichment belongs to /analysis/run
        # and report generation so the dashboard never blocks on OpenRouter.
        analysis = analysis_service.analyze_today(
            db,
            pairing_messages=today_for_analysis,
            task_messages=task_for_analysis,
            zone_name=zone_name,
            force=force,
            llm=False,
        )
    except Exception:
        logger.exception("Feed analysis failed — returning messages without analysis")
        analysis = {
            "date": datetime.now(tz(zone_name)).date().isoformat(),
            "analyzed_at": datetime.now(tz(zone_name)).isoformat(),
            "source": "error",
            "summary": "Analysis temporarily unavailable.",
            "attendance": [],
            "suggestion_ranking": [],
            "stats": {"total": 0, "completed": 0, "on_time": 0, "missed": 0, "with_suggestions": 0},
        }

    return {
        "today_messages": room_messages,
        "task_messages": task_messages,
        "task_month_start": month_start.isoformat(),
        "task_month_end": month_end.isoformat(),
        "task_week_start": month_start.isoformat(),
        "task_week_end": month_end.isoformat(),
        "analysis": analysis,
        "feed_cached": bool(room_messages),
        "feed_refreshing": refreshing,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _next_send_at(db: Session, schedule: dict) -> datetime | None:
    working = parse_working_days(schedule.get("working_days", settings.working_days))
    send_time = parse_hhmm(schedule.get("send_time", settings.daily_send_time))
    zone = schedule.get("timezone", settings.timezone)
    today = datetime.now(tz(zone)).date()
    now = datetime.now(tz(zone))

    bot = settings_service.get_setting(db, "bot")
    already_fired = (
        bot.get("last_scheduled_send_date") == today.isoformat()
        and bot.get("last_scheduled_send_time") == schedule.get("send_time")
    )

    target_day = today if is_working_day(today, working) else next_working_day(today, working)
    candidate = send_datetime_for(target_day, send_time, zone)
    if already_fired or candidate <= now:
        target_day = next_working_day(target_day, working)
        candidate = send_datetime_for(target_day, send_time, zone)
    return candidate


def today_room_messages(
    db: Session,
    zone_name: str,
    *,
    room_id: str | None = None,
) -> list[dict]:
    """Element-style room mirror (recent messages). Callers that need 'today'
    only should run filter_messages_for_day themselves."""
    from app.services import matrix_room_feed

    target = room_id or settings.matrix_room_id
    recent = matrix_room_feed.recent_room_timeline(
        target, zone_name=zone_name, limit=50
    )
    if target == settings.matrix_room_id:
        return matrix_room_feed.combine_feed_sources(
            recent, _bot_events_from_db(db, zone_name, days=7)
        )
    return recent


def month_task_messages(db: Session, zone_name: str) -> list[dict]:
    """Recent messages from the task-assignment room (Element-style mirror)."""
    from app.services import matrix_room_feed

    task_id = settings.matrix_task_room_id.strip()
    if not task_id:
        return []
    return matrix_room_feed.recent_room_timeline(
        task_id, zone_name=zone_name, limit=50
    )


def week_task_messages(db: Session, zone_name: str) -> list[dict]:
    """Backward-compatible alias — returns this month's task messages."""
    return month_task_messages(db, zone_name)


def today_task_messages(db: Session, zone_name: str) -> list[dict]:
    """Backward-compatible alias — returns this month's task messages."""
    return month_task_messages(db, zone_name)


def _bot_events_from_db(db: Session, zone_name: str, *, days: int = 1) -> list[dict]:
    """Bot posts from ElementEvent — last ``days`` days (default today)."""
    from datetime import timedelta

    zone = tz(zone_name)
    now = datetime.now(zone)
    start = datetime.combine(now.date() - timedelta(days=max(days - 1, 0)), time.min, tzinfo=zone)
    end = datetime.combine(now.date(), time.max, tzinfo=zone)

    rows = db.scalars(
        select(ElementEvent)
        .where(
            ElementEvent.status == "sent",
            ElementEvent.sent_at.is_not(None),
            ElementEvent.sent_at >= start,
            ElementEvent.sent_at <= end,
        )
        .order_by(ElementEvent.sent_at.asc())
    ).all()

    out: list[dict] = []
    for row in rows:
        text_body = (row.rendered_text or "").strip()
        if not text_body:
            continue
        kind = row.kind
        label = "Daily pairs" if kind == "daily_message" else "Weekly report" if kind == "report_post" else kind
        out.append(
            {
                "id": row.id,
                "kind": kind,
                "label": label,
                "sender": settings.matrix_bot_username,
                "text": text_body,
                "sent_at": row.sent_at.isoformat() if row.sent_at else None,
                "is_bot": True,
                "event_id": row.matrix_event_id,
            }
        )
    from app.services.matrix_room_feed import dedupe_bot_messages

    return dedupe_bot_messages(out)
