"""Pairing history (FR-9)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Member, PairingRound, Pairing, TeamLeadAssignment
from app.db.session import get_db
from app.services.round_service import COMBO_LABELS

router = APIRouter(prefix="/rounds", tags=["rounds"])


@router.get("/history")
def history(limit: int = 30, db: Session = Depends(get_db)) -> list[dict]:
    rounds = db.scalars(
        select(PairingRound).order_by(PairingRound.round_date.desc()).limit(limit)
    ).all()
    names = {m.id: m.name for m in db.scalars(select(Member)).all()}

    result: list[dict] = []
    for rnd in rounds:
        pairings = db.scalars(
            select(Pairing).where(Pairing.round_id == rnd.id)
        ).all()
        lead = db.scalar(
            select(TeamLeadAssignment).where(TeamLeadAssignment.round_id == rnd.id)
        )
        dev_pairs = []
        for p in pairings:
            if p.pair_type != "DEV":
                continue
            a = names.get(p.member_a_id, "?")
            b = names.get(p.member_b_id, "—")
            c = names.get(p.member_c_id) if p.member_c_id else None
            if c:
                dev_pairs.append(f"{a}·{b}·{c}")
            else:
                dev_pairs.append(f"{a}·{b}")
        result.append(
            {
                "date": rnd.round_date.isoformat(),
                "combo": COMBO_LABELS[rnd.combo_index]
                if rnd.combo_index < len(COMBO_LABELS)
                else str(rnd.combo_index),
                "dev_pairs": " / ".join(dev_pairs),
                "team_lead": names.get(lead.member_id) if lead else None,
                "status": rnd.status,
            }
        )
    return result
