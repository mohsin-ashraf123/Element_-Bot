"""Align today's DB round with the message already sent to Element (no re-send)."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select

from app.db.models import Member, Pairing, PairingRound, TeamLeadAssignment
from app.db.session import SessionLocal
from app.domain.constants import PairType
from app.domain.pairing import Pair, build_combos

# Matches the message already posted in the official Pair Reviews room.
SENT_TEXT = """Pairs Today

Saad + Hamza + Farhan
Uzair + Faz
Habiba + Aqeel

Saad will make sure all above today"""

TARGET_DATE = date(2026, 7, 20)


def _name_map(db) -> dict[str, int]:
    return {m.name: m.id for m in db.scalars(select(Member)).all()}


def main() -> None:
    db = SessionLocal()
    try:
        names = _name_map(db)
        rnd = db.scalar(select(PairingRound).where(PairingRound.round_date == TARGET_DATE))
        if not rnd:
            raise SystemExit(f"No round for {TARGET_DATE}")

        dev_ids = sorted(
            [names[n] for n in ("Uzair", "Saad", "Faz", "Hamza", "Farhan")],
            key=lambda i: i,
        )
        combos = build_combos(dev_ids)
        target_combo_index = None
        for combo in combos:
            rendered_dev = []
            for p in combo.pairs:
                if p.member_c is not None:
                    a = db.get(Member, p.member_a).name
                    b = db.get(Member, p.member_b).name
                    c = db.get(Member, p.member_c).name
                    rendered_dev.append(f"{a} + {b} + {c}")
                elif p.member_b is not None:
                    a = db.get(Member, p.member_a).name
                    b = db.get(Member, p.member_b).name
                    rendered_dev.append(f"{a} + {b}")
            if all(line in SENT_TEXT for line in rendered_dev):
                target_combo_index = combo.index
                target_pairs = combo.pairs
                break

        if target_combo_index is None:
            raise SystemExit("Could not match sent message to a combo")

        db.execute(delete(Pairing).where(Pairing.round_id == rnd.id))
        db.execute(delete(TeamLeadAssignment).where(TeamLeadAssignment.round_id == rnd.id))

        for p in target_pairs:
            db.add(
                Pairing(
                    round_id=rnd.id,
                    member_a_id=p.member_a,
                    member_b_id=p.member_b,
                    member_c_id=p.member_c,
                    pair_type=p.pair_type.value,
                )
            )
        db.add(
            Pairing(
                round_id=rnd.id,
                member_a_id=names["Habiba"],
                member_b_id=names["Aqeel"],
                pair_type=PairType.QA.value,
            )
        )
        db.add(
            TeamLeadAssignment(round_id=rnd.id, member_id=names["Saad"])
        )

        rnd.combo_index = target_combo_index
        rnd.rendered_text = SENT_TEXT
        rnd.status = "sent"
        db.commit()

        print(
            {
                "round_id": rnd.id,
                "combo_index": rnd.combo_index,
                "combo": f"C{rnd.combo_index + 1}",
                "team_lead": "Saad",
                "rendered_text": rnd.rendered_text,
            }
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
