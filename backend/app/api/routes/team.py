"""Team & roles management (FR-1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import MemberCreate, MemberOut, MemberUpdate
from app.services import team_service

router = APIRouter(prefix="/team", tags=["team"])


def _to_out(member) -> MemberOut:
    out = MemberOut.model_validate(member)
    out.config_gap = team_service.has_config_gap(member)
    return out


@router.get("/members", response_model=list[MemberOut])
def list_members(db: Session = Depends(get_db)) -> list[MemberOut]:
    return [_to_out(m) for m in team_service.list_members(db)]


@router.post("/members", response_model=MemberOut, status_code=201)
def add_member(payload: MemberCreate, db: Session = Depends(get_db)) -> MemberOut:
    member = team_service.create_member(
        db, name=payload.name, role=payload.role, matrix_user_id=payload.matrix_user_id
    )
    return _to_out(member)


@router.patch("/members/{member_id}", response_model=MemberOut)
def update_member(
    member_id: int, payload: MemberUpdate, db: Session = Depends(get_db)
) -> MemberOut:
    member = team_service.update_member(
        db, member_id, **payload.model_dump(exclude_unset=True)
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    return _to_out(member)


@router.delete("/members/{member_id}")
def remove_member(member_id: int, db: Session = Depends(get_db)) -> dict:
    if not team_service.deactivate_member(db, member_id):
        raise HTTPException(status_code=404, detail="Member not found")
    return {"ok": True, "message": "Member deactivated; history retained."}


@router.get("/lead-preview")
def lead_preview(count: int = 5, db: Session = Depends(get_db)) -> dict:
    return {"next_leads": team_service.next_leads_preview(db, count, last_lead_id=None)}
