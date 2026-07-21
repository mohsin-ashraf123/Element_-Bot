"""Daily message analysis — attendance, task context, suggestion ranking."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import date, datetime, time as dt_time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Member, PerformanceRecord
from app.domain.calendar import parse_hhmm, tz
from app.domain.constants import CLEAN_REPORT_MESSAGE, Outcome
from app.services import llm_service, round_service, settings_service, team_service

logger = logging.getLogger(__name__)

_CACHE_TTL = 60.0
_cache: dict[str, tuple[float, dict]] = {}


def invalidate_cache() -> None:
    """Clear analysis cache after Matrix feed refresh."""
    _cache.clear()

_POWER_KEYWORDS = (
    "should",
    "recommend",
    "improve",
    "fix",
    "issue",
    "concern",
    "because",
    "suggest",
    "refactor",
    "security",
    "performance",
    "bug",
    "risk",
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def is_clean_message(text: str) -> bool:
    normalized = _normalize(text)
    clean = _normalize(CLEAN_REPORT_MESSAGE)
    return normalized == clean or clean in normalized


def _member_by_sender(sender: str, members: list[Member]) -> Member | None:
    for m in members:
        if m.matrix_user_id and m.matrix_user_id == sender:
            return m
    if not sender.startswith("@"):
        return None
    local = sender[1:].split(":", 1)[0].lower()
    for m in members:
        if m.name.lower().replace(" ", "") == local.replace(" ", ""):
            return m
    return None


def _pair_header_names(text: str) -> list[str]:
    """Names from a group report header, e.g. ``Faz + Uzair:`` or ``Saad + Hamza + Farhan``."""
    stripped = text.strip()
    # Colon after names (Faz + Uzair:) or newline before body (Saad + Hamza + Farhan\nReview…)
    match = re.match(r"^([^:\n]+)(?::|\n)", stripped)
    if not match or "+" not in match.group(1):
        return []
    return [n.strip() for n in match.group(1).split("+") if n.strip()]


def _member_reports(member: Member, messages: list[dict]) -> list[dict]:
    mxid = member.matrix_user_id
    out: list[dict] = []
    for m in messages:
        if m.get("is_bot"):
            continue
        sender = m.get("sender") or ""
        if mxid and sender == mxid:
            out.append(m)
            continue
        text = m.get("text") or ""
        if member.name in _pair_header_names(text):
            out.append(m)
    return out


def _find_task(member: Member, task_messages: list[dict]) -> str | None:
    name = member.name.lower()
    matches = [
        msg
        for msg in task_messages
        if name in (msg.get("text") or "").lower()
    ]
    if not matches:
        return None
    latest = max(matches, key=lambda m: m.get("sent_at") or "")
    return (latest.get("text") or "").strip()


def _heuristic_power(text: str) -> int:
    if not text or is_clean_message(text):
        return 0
    score = 25
    score += min(len(text) // 25, 30)
    lower = text.lower()
    score += sum(6 for kw in _POWER_KEYWORDS if kw in lower)
    if re.search(r"\d+", text):
        score += 5
    return min(score, 100)


def _is_on_time(sent_at: datetime, cutoff: str) -> bool:
    try:
        cutoff_t = parse_hhmm(cutoff)
    except ValueError:
        cutoff_t = dt_time(23, 59)
    return sent_at.time() <= cutoff_t


def _cache_key(
    pairing_messages: list[dict],
    task_messages: list[dict],
    round_date: date,
) -> str:
    payload = json.dumps(
        {
            "date": round_date.isoformat(),
            "pairing": [(m.get("id"), m.get("sent_at")) for m in pairing_messages],
            "task": [(m.get("id"), m.get("sent_at")) for m in task_messages],
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _persist_record(
    db: Session,
    *,
    member: Member,
    record_date: date,
    completed: bool,
    on_time: bool,
    outcome: str,
    raw_text: str | None,
    source_event_id: str | None,
) -> None:
    row = db.scalar(
        select(PerformanceRecord).where(
            PerformanceRecord.member_id == member.id,
            PerformanceRecord.record_date == record_date,
        )
    )
    if row is None:
        row = PerformanceRecord(
            member_id=member.id,
            record_date=record_date,
            completed=completed,
            on_time=on_time,
            outcome=outcome,
            raw_text=raw_text,
            source_event_id=source_event_id,
        )
        db.add(row)
    else:
        row.completed = completed
        row.on_time = on_time
        row.outcome = outcome
        row.raw_text = raw_text
        row.source_event_id = source_event_id
    db.commit()


def _build_member_rows(
    db: Session,
    *,
    pairing_messages: list[dict],
    task_messages: list[dict],
    zone_name: str,
    round_date: date,
) -> list[dict]:
    schedule = settings_service.get_setting(db, "schedule")
    cutoff = schedule.get("timeliness_cutoff", "23:59")
    zone = tz(zone_name)
    round_preview = round_service.preview_round(db, round_date)
    members = team_service.list_members(db, active_only=True)

    rows: list[dict] = []
    for member in members:
        reports = _member_reports(member, pairing_messages)
        latest = max(reports, key=lambda m: m.get("sent_at") or "") if reports else None

        completed = latest is not None
        raw_text = (latest.get("text") or "").strip() if latest else None
        sent_at = latest.get("sent_at") if latest else None

        if not completed:
            outcome = Outcome.MISSED.value
            on_time = False
        elif raw_text and is_clean_message(raw_text):
            outcome = Outcome.CLEAN.value
            on_time = bool(
                sent_at
                and _is_on_time(datetime.fromisoformat(sent_at).astimezone(zone), cutoff)
            )
        else:
            outcome = Outcome.HAS_ISSUES.value
            on_time = bool(
                sent_at
                and _is_on_time(datetime.fromisoformat(sent_at).astimezone(zone), cutoff)
            )

        task_text = _find_task(member, task_messages)
        pair_context = _pair_context(member.name, round_preview.get("pairs", []))
        power = _heuristic_power(raw_text or "")

        _persist_record(
            db,
            member=member,
            record_date=round_date,
            completed=completed,
            on_time=on_time,
            outcome=outcome,
            raw_text=raw_text,
            source_event_id=latest.get("event_id") if latest else None,
        )

        rows.append(
            {
                "member_id": member.id,
                "name": member.name,
                "completed": completed,
                "on_time": on_time,
                "outcome": outcome,
                "task": task_text,
                "pair_context": pair_context,
                "suggestion_summary": _suggestion_summary(raw_text),
                "power_score": power,
                "sent_at": sent_at,
                "has_suggestion": outcome == Outcome.HAS_ISSUES.value,
            }
        )

    rows.sort(key=lambda r: (-r["power_score"], r["name"]))
    return rows


def _pair_context(name: str, pairs: list[dict]) -> str | None:
    for p in pairs:
        names = [p.get("member_a"), p.get("member_b"), p.get("member_c")]
        names = [n for n in names if n]
        if name in names:
            return " + ".join(names)
    return None


def _suggestion_summary(text: str | None) -> str | None:
    if not text or is_clean_message(text):
        return None
    first = text.strip().split("\n", 1)[0]
    return first[:160] + ("…" if len(first) > 160 else "")


def _llm_enhance(
    db: Session,
    *,
    member_rows: list[dict],
    pairing_messages: list[dict],
    task_messages: list[dict],
    round_preview: dict,
) -> dict | None:
    if not llm_service.is_available(db):
        return None

    system = (
        "You analyze a dev team's daily Matrix room messages. "
        "Task messages cover the full working month — use them for context. "
        "Return ONLY valid JSON with keys: summary (string), rankings (array). "
        "Each ranking item: name, power_score (0-100), reason (string), task (string|null). "
        "Rank suggestions by depth, specificity, and actionability given each developer's task. "
        "Clean reports (no issues) get power_score 0. Be concise."
    )
    user = json.dumps(
        {
            "pairs_today": round_preview.get("pairs"),
            "team_lead": round_preview.get("team_lead"),
            "member_status": member_rows,
            "pairing_messages": [
                {"from": m.get("label"), "text": m.get("text"), "at": m.get("sent_at")}
                for m in pairing_messages
                if not m.get("is_bot")
            ],
            "task_messages": [
                {"from": m.get("label"), "text": m.get("text"), "at": m.get("sent_at")}
                for m in task_messages
                if not m.get("is_bot")
            ],
        },
        ensure_ascii=False,
    )

    return llm_service.complete_json(system=system, user=user, db=db)


def _apply_llm_rankings(member_rows: list[dict], llm: dict) -> tuple[list[dict], str | None]:
    rankings = llm.get("rankings") or []
    if not rankings:
        return member_rows, llm.get("summary")

    by_name = {r["name"].lower(): r for r in member_rows}
    merged: list[dict] = []
    for item in rankings:
        name = str(item.get("name", "")).strip()
        row = by_name.get(name.lower())
        if not row:
            continue
        updated = dict(row)
        if item.get("power_score") is not None:
            updated["power_score"] = int(item["power_score"])
        if item.get("reason"):
            updated["ai_reason"] = str(item["reason"])
        if item.get("task"):
            updated["task"] = str(item["task"])
        merged.append(updated)

    seen = {r["member_id"] for r in merged}
    for row in member_rows:
        if row["member_id"] not in seen:
            merged.append(row)

    merged.sort(key=lambda r: (-r["power_score"], r["name"]))
    return merged, llm.get("summary")


def analyze_today(
    db: Session,
    *,
    pairing_messages: list[dict],
    task_messages: list[dict],
    zone_name: str,
    round_date: date | None = None,
    force: bool = False,
    llm: bool = True,
) -> dict:
    """Analyze today's room messages → attendance + suggestion ranking."""
    today = round_date or datetime.now(tz(zone_name)).date()
    key = _cache_key(pairing_messages, task_messages, today)
    now = time.monotonic()

    if not force:
        cached = _cache.get(key)
        if cached and (now - cached[0]) < _CACHE_TTL:
            return cached[1]

    round_preview = round_service.preview_round(db, today)
    member_rows = _build_member_rows(
        db,
        pairing_messages=pairing_messages,
        task_messages=task_messages,
        zone_name=zone_name,
        round_date=today,
    )

    llm_result = None
    if llm:
        llm_result = _llm_enhance(
            db,
            member_rows=member_rows,
            pairing_messages=pairing_messages,
            task_messages=task_messages,
            round_preview=round_preview,
        )

    summary = None
    source = "heuristic"
    if llm_result:
        member_rows, summary = _apply_llm_rankings(member_rows, llm_result)
        source = "llm"

    completed = sum(1 for r in member_rows if r["completed"])
    on_time = sum(1 for r in member_rows if r["on_time"])
    suggestions = [r for r in member_rows if r["has_suggestion"]]

    result = {
        "date": today.isoformat(),
        "analyzed_at": datetime.now(tz(zone_name)).isoformat(),
        "source": source,
        "summary": summary
        or _template_summary(completed, len(member_rows), on_time, len(suggestions)),
        "attendance": member_rows,
        "suggestion_ranking": [
            {
                "rank": i + 1,
                "name": r["name"],
                "power_score": r["power_score"],
                "reason": r.get("ai_reason") or r.get("suggestion_summary") or "Clean / no suggestion",
                "task": r.get("task"),
                "pair_context": r.get("pair_context"),
            }
            for i, r in enumerate(member_rows)
            if r["power_score"] > 0 or r["has_suggestion"]
        ],
        "stats": {
            "total": len(member_rows),
            "completed": completed,
            "on_time": on_time,
            "missed": len(member_rows) - completed,
            "with_suggestions": len(suggestions),
        },
    }

    _cache[key] = (now, result)
    return result


def _template_summary(completed: int, total: int, on_time: int, suggestions: int) -> str:
    return (
        f"Today: {completed}/{total} reports submitted, {on_time} on-time. "
        f"{suggestions} member(s) shared suggestions or issues."
    )
