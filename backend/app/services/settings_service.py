"""Settings service — typed access to the key/value `settings` table."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings as env
from app.db.models import Setting

# Default configuration seeded on first run. Values here come from env so the
# operator's .env drives the initial state; everything is editable in the UI.
DEFAULTS: dict[str, dict[str, Any]] = {
    "schedule": {
        "send_time": env.daily_send_time,
        "working_days": [d.strip() for d in env.working_days.split(",")],
        "timeliness_cutoff": env.timeliness_cutoff,
        "timezone": env.timezone,
    },
    "reports": {"weekly_enabled": True, "monthly_enabled": True},
    "llm": {
        "provider": env.llm_provider,
        "enabled": True,
        "pseudonymise": False,
        "model": env.llm_model or None,
    },
    "bot": {"status": "running"},
}


def get_setting(db: Session, key: str) -> dict[str, Any]:
    return _mask_secrets(key, get_setting_raw(db, key))


def get_setting_raw(db: Session, key: str) -> dict[str, Any]:
    """Internal — includes secrets (API keys) for server-side use only."""
    row = db.get(Setting, key)
    if row is None:
        return dict(DEFAULTS.get(key, {}))
    return dict(row.value_json or {})


def _mask_secrets(key: str, value: dict[str, Any]) -> dict[str, Any]:
    if key != "llm":
        return value
    out = dict(value)
    if out.get("api_key"):
        out["api_key_set"] = True
        out.pop("api_key", None)
    else:
        out["api_key_set"] = False
    return out


def _reset_scheduler_slot(db: Session) -> None:
    """Allow a new scheduled send when send_time changes (testing / reschedule)."""
    row = db.get(Setting, "bot")
    if row is None:
        return
    value = dict(row.value_json or {})
    changed = False
    for key in ("last_scheduled_send_date", "last_scheduled_send_time"):
        if key in value:
            value.pop(key)
            changed = True
    if changed:
        row.value_json = value
        row.updated_by = "schedule-change"


def set_setting(db: Session, key: str, value: dict[str, Any], actor: str = "system") -> None:
    row = db.get(Setting, key)
    if key == "schedule" and row is not None:
        old_time = (row.value_json or {}).get("send_time")
        new_time = value.get("send_time")
        if new_time and new_time != old_time:
            _reset_scheduler_slot(db)
    elif key == "schedule" and row is None:
        pass

    if row is None:
        row = Setting(key=key, value_json=value, updated_by=actor)
        db.add(row)
    else:
        merged = dict(row.value_json or {})
        merged.update(value)
        if key == "llm" and "api_key" not in value and (row.value_json or {}).get("api_key"):
            merged["api_key"] = row.value_json["api_key"]
        row.value_json = merged
        row.updated_by = actor
    db.commit()


def get_all(db: Session) -> dict[str, dict[str, Any]]:
    stored = {s.key: s.value_json for s in db.scalars(select(Setting)).all()}
    return {
        key: _mask_secrets(key, stored.get(key, default))
        for key, default in DEFAULTS.items()
    }


def ensure_defaults(db: Session) -> None:
    """Seed any missing default settings rows (idempotent)."""
    existing = {s.key for s in db.scalars(select(Setting)).all()}
    for key, value in DEFAULTS.items():
        if key not in existing:
            db.add(Setting(key=key, value_json=value, updated_by="bootstrap"))
    db.commit()
