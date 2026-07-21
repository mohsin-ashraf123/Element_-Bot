"""Round service — build, preview and persist daily pairing rounds."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Pairing, PairingRound, TeamLeadAssignment
from app.domain.constants import PairType
from app.domain.pairing import Pair, select_combo
from app.domain.team_lead import select_lead
from app.services import team_service

COMBO_LABELS = [f"C{i + 1}" for i in range(20)]


def combo_label(index: int) -> str:
    return COMBO_LABELS[index] if index < len(COMBO_LABELS) else f"C{index + 1}"


def _pair_to_preview(p: Pair | dict, by_id: dict) -> dict:
    if isinstance(p, Pair):
        row = {
            "member_a": by_id.get(p.member_a, "?"),
            "member_b": by_id.get(p.member_b) if p.member_b else None,
            "pair_type": p.pair_type.value,
        }
        if p.member_c is not None:
            row["member_c"] = by_id.get(p.member_c, "?")
        return row
    return dict(p)


def _format_pair_line(p: dict) -> str:
    if p.get("member_c"):
        return f"{p['member_a']} + {p['member_b']} + {p['member_c']}"
    if p.get("member_b"):
        return f"{p['member_a']} + {p['member_b']}"
    return f"{p['member_a']} (self-review)"


def _last_combo_index(db: Session) -> int | None:
    return db.scalar(
        select(PairingRound.combo_index).order_by(PairingRound.round_date.desc())
    )


def _last_lead_id(db: Session) -> int | None:
    stmt = (
        select(TeamLeadAssignment.member_id)
        .join(PairingRound, TeamLeadAssignment.round_id == PairingRound.id)
        .order_by(PairingRound.round_date.desc())
    )
    return db.scalar(stmt)


def _compute_round(db: Session, round_date: date) -> dict:
    """Internal round computation — pair IDs + preview names."""
    members = team_service.list_members(db, active_only=True)
    by_id = {m.id: m.name for m in members}

    dev_ids = [m.id for m in members if m.role == "DEVELOPER"]
    qa_ids = [m.id for m in members if m.role == "QA"]
    order = [m.id for m in team_service.list_members(db)]
    active = {m.id for m in members}

    combo = select_combo(dev_ids, _last_combo_index(db)) if dev_ids else None
    lead_id = select_lead(order, active, _last_lead_id(db)) if active else None

    pairings: list[Pair] = []
    preview_pairs: list[dict] = []
    if combo:
        for p in combo.pairs:
            pairings.append(p)
            preview_pairs.append(_pair_to_preview(p, by_id))
    if len(qa_ids) == 2:
        pairings.append(Pair(qa_ids[0], qa_ids[1], PairType.QA))
        preview_pairs.append(
            {
                "member_a": by_id[qa_ids[0]],
                "member_b": by_id[qa_ids[1]],
                "pair_type": PairType.QA.value,
            }
        )
    elif len(qa_ids) == 1:
        pairings.append(Pair(qa_ids[0], None, PairType.QA))
        preview_pairs.append(
            {"member_a": by_id[qa_ids[0]], "member_b": None, "pair_type": PairType.QA.value}
        )

    lead_name = by_id.get(lead_id) if lead_id else None
    rendered = render_message(preview_pairs, lead_name)
    return {
        "round_date": round_date,
        "combo_index": combo.index if combo else 0,
        "combo_label": combo_label(combo.index) if combo else "—",
        "pairs": preview_pairs,
        "pairings": pairings,
        "team_lead": lead_name,
        "lead_id": lead_id,
        "rendered_text": rendered,
    }


def preview_round(db: Session, round_date: date) -> dict:
    """Compute the round for a date without persisting it."""
    computed = _compute_round(db, round_date)
    return {
        "round_date": computed["round_date"].isoformat(),
        "combo_index": computed["combo_index"],
        "combo_label": computed["combo_label"],
        "pairs": computed["pairs"],
        "team_lead": computed["team_lead"],
        "rendered_text": computed["rendered_text"],
    }


def persist_round(
    db: Session,
    round_date: date,
    *,
    status: str = "sent",
    rendered_text: str | None = None,
) -> PairingRound:
    """Save or update today's round so History can list it."""
    computed = _compute_round(db, round_date)
    text = rendered_text or computed["rendered_text"]

    existing = db.scalar(
        select(PairingRound).where(PairingRound.round_date == round_date)
    )
    if existing:
        from sqlalchemy import delete

        db.execute(delete(Pairing).where(Pairing.round_id == existing.id))
        db.execute(delete(TeamLeadAssignment).where(TeamLeadAssignment.round_id == existing.id))
        existing.combo_index = computed["combo_index"]
        existing.status = status
        existing.rendered_text = text
        rnd = existing
    else:
        rnd = PairingRound(
            round_date=round_date,
            combo_index=computed["combo_index"],
            status=status,
            rendered_text=text,
        )
        db.add(rnd)
        db.flush()

    for p in computed["pairings"]:
        db.add(
            Pairing(
                round_id=rnd.id,
                member_a_id=p.member_a,
                member_b_id=p.member_b,
                member_c_id=p.member_c,
                pair_type=p.pair_type.value,
            )
        )

    if computed["lead_id"]:
        db.add(TeamLeadAssignment(round_id=rnd.id, member_id=computed["lead_id"]))

    db.commit()
    db.refresh(rnd)
    return rnd


def render_message(pairs: list[dict], lead_name: str | None) -> str:
    """Render the daily message text (RULES R10.2, matching the PRD example)."""
    lines = ["Pairs Today", ""]
    for p in pairs:
        lines.append(_format_pair_line(p))
    lines.append("")
    if lead_name:
        lines.append(f"{lead_name} will make sure all above today")
    return "\n".join(lines)
