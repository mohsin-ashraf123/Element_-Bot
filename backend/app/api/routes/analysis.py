"""Message analysis endpoints — attendance, suggestions, AI ranking."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import analysis_service, dashboard_service, performance_service, settings_service
from app.core.config import settings

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/today")
def today(db: Session = Depends(get_db)) -> dict:
    schedule = settings_service.get_setting(db, "schedule")
    zone_name = schedule.get("timezone", settings.timezone)
    pairing = dashboard_service.today_room_messages(
        db, zone_name, room_id=settings.matrix_room_id
    )
    task = dashboard_service.today_task_messages(db, zone_name)
    return analysis_service.analyze_today(
        db,
        pairing_messages=pairing,
        task_messages=task,
        zone_name=zone_name,
        force=True,
    )


@router.post("/run")
def run_analysis(db: Session = Depends(get_db)) -> dict:
    """Force a fresh analysis pass (re-fetch + optional LLM)."""
    schedule = settings_service.get_setting(db, "schedule")
    zone_name = schedule.get("timezone", settings.timezone)
    pairing = dashboard_service.today_room_messages(
        db, zone_name, room_id=settings.matrix_room_id
    )
    task = dashboard_service.today_task_messages(db, zone_name)
    return analysis_service.analyze_today(
        db,
        pairing_messages=pairing,
        task_messages=task,
        zone_name=zone_name,
        force=True,
    )


@router.get("/performance")
def performance(
    db: Session = Depends(get_db),
    scope: Literal["today", "week", "month"] = Query(default="today"),
) -> dict:
    """Per-member performance for today, this week (Mon–today), or this month."""
    return performance_service.get_performance(db, scope=scope)
