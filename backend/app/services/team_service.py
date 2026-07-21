"""Team service — member roster CRUD and lead-order helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Member
from app.domain.constants import Role
from app.domain.team_lead import preview_next_leads


def list_members(db: Session, active_only: bool = False) -> list[Member]:
    stmt = select(Member).order_by(Member.lead_order, Member.id)
    if active_only:
        stmt = stmt.where(Member.active.is_(True))
    return list(db.scalars(stmt).all())


def developers(db: Session) -> list[Member]:
    return [m for m in list_members(db) if m.role == Role.DEVELOPER.value]


def qa_members(db: Session) -> list[Member]:
    return [m for m in list_members(db) if m.role == Role.QA.value]


def create_member(
    db: Session, name: str, role: str, matrix_user_id: str | None
) -> Member:
    max_order = db.scalar(select(Member.lead_order).order_by(Member.lead_order.desc()))
    member = Member(
        name=name,
        role=role,
        matrix_user_id=matrix_user_id,
        active=True,
        lead_order=(max_order or 0) + 1,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def update_member(db: Session, member_id: int, **fields) -> Member | None:
    member = db.get(Member, member_id)
    if member is None:
        return None
    for key, value in fields.items():
        if value is not None and hasattr(member, key):
            setattr(member, key, value)
    db.commit()
    db.refresh(member)
    return member


def deactivate_member(db: Session, member_id: int) -> bool:
    """Soft-remove: keep history, exclude from future rounds (RULES R6.2)."""
    member = db.get(Member, member_id)
    if member is None:
        return False
    from datetime import datetime, timezone

    member.active = False
    member.deactivated_at = datetime.now(timezone.utc)
    db.commit()
    return True


def lead_order_ids(db: Session) -> list[int]:
    return [m.id for m in list_members(db)]


def next_leads_preview(db: Session, count: int, last_lead_id: int | None) -> list[str]:
    members = list_members(db)
    by_id = {m.id: m.name for m in members}
    order = [m.id for m in members]
    active = {m.id for m in members if m.active}
    if not active:
        return []
    ids = preview_next_leads(order, active, last_lead_id, count)
    return [by_id[i] for i in ids]


def has_config_gap(member: Member) -> bool:
    """A member without a valid Matrix ID cannot be attributed (RULES R1.3)."""
    return not member.matrix_user_id
