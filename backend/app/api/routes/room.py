"""Element room status and test sends."""

from __future__ import annotations

from datetime import date

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services import dashboard_service, element_health, round_service, send_service, settings_service, team_service
from app.services.matrix_trust import diagnose

router = APIRouter(prefix="/room", tags=["room"])
logger = logging.getLogger(__name__)


@router.post("/accept-verification")
def accept_verification() -> dict:
    """Auto-accept Element 'Verify session' for the PairFlow bot device."""
    from app.services.matrix_e2ee import accept_pending_verifications

    return accept_pending_verifications()


@router.get("/trust")
def room_trust() -> dict:
    """Why Element may show 'unknown device' on bot messages."""
    return diagnose()


@router.get("/status")
def room_status(db: Session = Depends(get_db)) -> dict:
    """Fast room connection status — no blocking Matrix or analysis."""
    health = element_health.check()
    schedule = settings_service.get_setting(db, "schedule")
    zone = schedule.get("timezone", settings.timezone)
    today_messages = dashboard_service.today_room_messages(db, zone)
    from app.services import matrix_room_feed

    pairing_id = settings.matrix_room_id
    refreshing = pairing_id in matrix_room_feed.refreshing_rooms()
    if not refreshing and matrix_room_feed.cache_age(pairing_id) is None:
        mxid = {
            m.matrix_user_id: m.name
            for m in team_service.list_members(db)
            if m.matrix_user_id
        }
        refreshing = matrix_room_feed.schedule_refresh(
            room_id=pairing_id, zone_name=zone, mxid_to_name=mxid
        ) or refreshing

    return {
        "configured": health["configured"],
        "connected": health["connected"],
        "joined": health["joined"],
        "e2ee_store_ready": health["e2ee_store_ready"],
        "homeserver": health.get("homeserver"),
        "room_label": health.get("room_label"),
        "room_name": health.get("room_name"),
        "today_messages": today_messages,
        "feed_refreshing": refreshing,
        "error": health.get("error"),
    }


@router.get("/preview")
def preview_pairs(db: Session = Depends(get_db)) -> dict:
    """Today's pairing message — exactly what Send pairs will post."""
    return round_service.preview_round(db, date.today())


@router.post("/send-pairs")
def send_pairs(db: Session = Depends(get_db)) -> dict:
    return send_service.send_pairs(db)


@router.get("/report-preview")
def report_preview(db: Session = Depends(get_db)) -> dict:
    """PNG preview of the weekly report table (same output as send-report)."""
    try:
        return send_service.get_report_preview(db)
    except Exception as exc:
        logger.exception("report-preview failed")
        detail = str(exc).strip() or repr(exc)
        raise HTTPException(status_code=500, detail=detail) from exc


@router.post("/send-report")
def send_report(db: Session = Depends(get_db)) -> dict:
    return send_service.send_report(db)

