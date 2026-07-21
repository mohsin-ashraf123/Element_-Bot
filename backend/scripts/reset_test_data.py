"""Remove test/operational data — keep members, room config, and reset schedule."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# Allow `python scripts/reset_test_data.py` from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select

from app.core.config import settings
from app.db.models import (
    AuditLog,
    ElementEvent,
    Job,
    LeadAccountability,
    Member,
    PairingRound,
    PerformanceRecord,
    Report,
    Setting,
)
from app.db.session import SessionLocal
from app.domain.calendar import (
    is_working_day,
    parse_hhmm,
    parse_working_days,
    send_datetime_for,
    tz,
)
from app.services import settings_service


def _clear_runtime_caches() -> None:
    cache_file = Path("./data/member_feed_cache.json")
    if cache_file.is_file():
        cache_file.write_text("{}", encoding="utf-8")

    preview = Path("./tmp_preview.json")
    if preview.is_file():
        preview.unlink()

    try:
        from app.services import analysis_service, matrix_room_feed

        matrix_room_feed.invalidate_cache()
        analysis_service.invalidate_cache()
    except Exception:
        pass


def reset_test_data() -> dict:
    db = SessionLocal()
    try:
        before = {
            "members": db.scalar(select(func.count()).select_from(Member)) or 0,
            "events": db.scalar(select(func.count()).select_from(ElementEvent)) or 0,
            "rounds": db.scalar(select(func.count()).select_from(PairingRound)) or 0,
            "reports": db.scalar(select(func.count()).select_from(Report)) or 0,
        }

        db.execute(delete(ElementEvent))
        db.execute(delete(LeadAccountability))
        db.execute(delete(PerformanceRecord))
        db.execute(delete(Report))
        db.execute(delete(Job))
        db.execute(delete(AuditLog))
        db.execute(delete(PairingRound))
        db.commit()

        schedule = {
            "send_time": settings.daily_send_time,
            "working_days": ["mon", "tue", "wed", "thu", "fri"],
            "timeliness_cutoff": settings.timeliness_cutoff,
            "timezone": settings.timezone,
        }
        settings_service.set_setting(db, "schedule", schedule, actor="reset")

        zone_name = schedule["timezone"]
        now = datetime.now(tz(zone_name))
        working = parse_working_days(schedule["working_days"])
        send_time = schedule["send_time"]
        due_at = send_datetime_for(now.date(), parse_hhmm(send_time), zone_name)
        bot_value: dict[str, str] = {"status": "running"}
        if is_working_day(now.date(), working) and now >= due_at:
            bot_value["last_scheduled_send_date"] = now.date().isoformat()
            bot_value["last_scheduled_send_time"] = send_time

        bot_row = db.get(Setting, "bot")
        if bot_row is None:
            settings_service.set_setting(db, "bot", bot_value, actor="reset")
        else:
            bot_row.value_json = bot_value
            bot_row.updated_by = "reset"
            db.commit()

        _clear_runtime_caches()

        after = {
            "members": db.scalar(select(func.count()).select_from(Member)) or 0,
            "events": db.scalar(select(func.count()).select_from(ElementEvent)) or 0,
            "rounds": db.scalar(select(func.count()).select_from(PairingRound)) or 0,
            "reports": db.scalar(select(func.count()).select_from(Report)) or 0,
            "schedule": settings_service.get_setting(db, "schedule"),
            "rooms": {
                "pairing": settings.matrix_room_id,
                "task": settings.matrix_task_room_id or None,
            },
        }
        return {"before": before, "after": after}
    finally:
        db.close()


if __name__ == "__main__":
    result = reset_test_data()
    print(json.dumps(result, indent=2, default=str))
