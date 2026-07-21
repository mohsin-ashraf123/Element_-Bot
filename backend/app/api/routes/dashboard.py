"""Dashboard endpoints: bot status + today's round preview."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import dashboard_service, round_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/status")
def status(db: Session = Depends(get_db)) -> dict:
    return dashboard_service.build_status(db)


@router.get("/feed")
def feed(db: Session = Depends(get_db), force: bool = False) -> dict:
    return dashboard_service.build_feed(db, force=force)


@router.get("/feed/status")
def feed_status(db: Session = Depends(get_db)) -> dict:
    """Lightweight poll — is Matrix refresh done yet?"""
    from app.services import matrix_room_feed
    from app.core.config import settings as cfg

    pairing_id = cfg.matrix_room_id
    task_id = cfg.matrix_task_room_id.strip()
    return {
        "pairing_cached": matrix_room_feed.peek_cached(pairing_id) is not None,
        "task_cached": matrix_room_feed.peek_cached(task_id) is not None if task_id else None,
        "pairing_age_s": matrix_room_feed.cache_age(pairing_id),
        "refreshing": matrix_room_feed.refreshing_rooms(),
    }


@router.get("/today")
def today(db: Session = Depends(get_db)) -> dict:
    return round_service.preview_round(db, date.today())
