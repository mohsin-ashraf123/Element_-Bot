"""Dashboard endpoints: bot status + today's round preview."""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import dashboard_service, round_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/status")
def status(db: Session = Depends(get_db)) -> dict:
    try:
        return dashboard_service.build_status(db)
    except Exception as exc:
        logger.exception("Dashboard status failed")
        raise HTTPException(status_code=503, detail="Dashboard status temporarily unavailable") from exc


@router.get("/feed")
def feed(db: Session = Depends(get_db), force: bool = False) -> dict:
    try:
        return dashboard_service.build_feed(db, force=force)
    except Exception as exc:
        logger.exception("Dashboard feed failed")
        raise HTTPException(status_code=503, detail="Dashboard feed temporarily unavailable") from exc


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
    try:
        return round_service.preview_round(db, date.today())
    except Exception as exc:
        logger.exception("Dashboard today preview failed")
        raise HTTPException(status_code=503, detail="Round preview temporarily unavailable") from exc
