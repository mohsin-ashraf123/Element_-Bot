"""Scoped AI reports — generate, list, view."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import report_builder_service

router = APIRouter(prefix="/reports", tags=["reports"])


class GenerateRequest(BaseModel):
    period_type: Literal["weekly", "monthly"] = "weekly"


@router.get("")
def list_reports(limit: int = 20, db: Session = Depends(get_db)) -> list[dict]:
    return report_builder_service.list_reports(db, limit=limit)


@router.get("/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db)) -> dict:
    row = report_builder_service.get_report(db, report_id)
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    return row


@router.post("/generate")
def generate_report(payload: GenerateRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return report_builder_service.generate_scoped_report(
            db, period_type=payload.period_type
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
