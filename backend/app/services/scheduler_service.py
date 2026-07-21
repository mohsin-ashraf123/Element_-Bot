"""In-process daily send scheduler (replaces deferred Celery for MVP).

Wakes every 30s, checks schedule settings, and posts today's pairs once per
working day after `send_time` in the configured timezone.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

from app.core.config import settings
from app.db.session import SessionLocal
from app.domain.calendar import (
    is_last_working_day_of_month,
    is_working_day,
    parse_hhmm,
    parse_working_days,
    send_datetime_for,
    tz,
)
from app.services import send_service, settings_service

logger = logging.getLogger(__name__)

_POLL_SECONDS = 10
_stop = threading.Event()
_tick_lock = threading.Lock()


def _scheduler_sent_for_slot(db, schedule: dict, zone_name: str) -> bool:
    """Skip only if we already fired for today's configured send_time."""
    bot = settings_service.get_setting(db, "bot")
    last_date = bot.get("last_scheduled_send_date")
    last_time = bot.get("last_scheduled_send_time")
    if not last_date:
        return False
    today = datetime.now(tz(zone_name)).date().isoformat()
    return last_date == today and last_time == schedule.get("send_time")


def _mark_scheduler_sent(db, zone_name: str, send_time: str) -> None:
    bot = settings_service.get_setting(db, "bot")
    today = datetime.now(tz(zone_name)).date().isoformat()
    settings_service.set_setting(
        db,
        "bot",
        {
            **bot,
            "last_scheduled_send_date": today,
            "last_scheduled_send_time": send_time,
        },
        actor="scheduler",
    )


def _clear_scheduler_sent(db) -> None:
    bot = settings_service.get_setting(db, "bot")
    changed = False
    for key in ("last_scheduled_send_date", "last_scheduled_send_time"):
        if key in bot:
            bot = {k: v for k, v in bot.items() if k != key}
            changed = True
    if changed:
        settings_service.set_setting(db, "bot", bot, actor="scheduler")


def is_due(schedule: dict) -> bool:
    """True when today is a working day and local time is past send_time."""
    zone_name = schedule.get("timezone", settings.timezone)
    zone = tz(zone_name)
    now = datetime.now(zone)
    working = parse_working_days(schedule.get("working_days", settings.working_days))
    if not is_working_day(now.date(), working):
        return False
    send_time = parse_hhmm(schedule.get("send_time", settings.daily_send_time))
    due_at = send_datetime_for(now.date(), send_time, zone_name)
    return now >= due_at


def _monthly_report_sent(db, zone_name: str) -> bool:
    bot = settings_service.get_setting(db, "bot")
    month_key = datetime.now(tz(zone_name)).date().strftime("%Y-%m")
    return bot.get("last_monthly_report_month") == month_key


def _mark_monthly_report_sent(db, zone_name: str) -> None:
    bot = settings_service.get_setting(db, "bot")
    month_key = datetime.now(tz(zone_name)).date().strftime("%Y-%m")
    settings_service.set_setting(
        db,
        "bot",
        {**bot, "last_monthly_report_month": month_key},
        actor="scheduler",
    )


def tick() -> dict | None:
    """One scheduler pass. Returns send result when a message is posted."""
    with _tick_lock:
        db = SessionLocal()
        try:
            schedule = settings_service.get_setting(db, "schedule")
            zone_name = schedule.get("timezone", settings.timezone)

            if not is_due(schedule):
                return None
            if _scheduler_sent_for_slot(db, schedule, zone_name):
                logger.debug(
                    "Scheduler skip — already sent for %s today",
                    schedule.get("send_time"),
                )
                return None

            # Reserve this slot before send so a slow Matrix call can't double-fire.
            _mark_scheduler_sent(db, zone_name, schedule.get("send_time", ""))

            logger.info(
                "Scheduled daily pairs send firing (send_time=%s %s)",
                schedule.get("send_time"),
                zone_name,
            )
            pairs_result = send_service.send_pairs(db)
            if pairs_result.get("ok"):
                logger.info("Scheduled daily pairs sent — event %s", pairs_result.get("event_id"))
            else:
                _clear_scheduler_sent(db)
                logger.error("Scheduled daily pairs failed: %s", pairs_result.get("error"))
                return pairs_result

            reports_cfg = settings_service.get_setting(db, "reports")
            working = parse_working_days(schedule.get("working_days", settings.working_days))
            today = datetime.now(tz(zone_name)).date()
            if reports_cfg.get("weekly_enabled", True):
                logger.info("Scheduled weekly report send firing (send_time=%s %s)", schedule.get("send_time"), zone_name)
                report_result = send_service.send_report(db, period_type="weekly")
                if report_result.get("ok"):
                    logger.info(
                        "Scheduled weekly report sent — image %s",
                        report_result.get("event_id"),
                    )
                else:
                    logger.error("Scheduled weekly report failed: %s", report_result.get("error"))
                pairs_result["report"] = report_result

            if (
                reports_cfg.get("monthly_enabled", True)
                and is_last_working_day_of_month(today, working)
                and not _monthly_report_sent(db, zone_name)
            ):
                logger.info("Scheduled monthly report send (last working day of %s)", today.strftime("%Y-%m"))
                monthly_result = send_service.send_report(db, period_type="monthly")
                if monthly_result.get("ok"):
                    _mark_monthly_report_sent(db, zone_name)
                    from app.services import matrix_room_feed

                    matrix_room_feed.invalidate_cache(settings.matrix_task_room_id.strip())
                    logger.info(
                        "Scheduled monthly report sent — image %s",
                        monthly_result.get("event_id"),
                    )
                else:
                    logger.error("Scheduled monthly report failed: %s", monthly_result.get("error"))
                pairs_result["monthly_report"] = monthly_result
            return pairs_result
        except Exception:
            logger.exception("Scheduler tick failed")
            try:
                _clear_scheduler_sent(db)
            except Exception:
                pass
            return None
        finally:
            db.close()


def _loop() -> None:
    logger.info("Daily send scheduler started (poll every %ss)", _POLL_SECONDS)
    # First check soon after boot so we don't wait a full poll interval.
    _stop.wait(3)
    while not _stop.is_set():
        try:
            tick()
        except Exception:
            logger.exception("Scheduler loop error")
        _stop.wait(_POLL_SECONDS)


def start() -> None:
    if getattr(start, "_started", False):
        return
    start._started = True  # type: ignore[attr-defined]
    threading.Thread(target=_loop, daemon=True, name="daily-send-scheduler").start()


def stop() -> None:
    _stop.set()
