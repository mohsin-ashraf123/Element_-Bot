"""Deterministic developer pairing (RULES §2–§5).

With N developers the set of valid "combos" (ways to split everyone into
pairs for one day) is generated with the classic round-robin *circle method*,
which yields N-1 combos that together cover every possible pair exactly once.

- N = 4  → 3 combos (C1, C2, C3), matching the PRD exactly.
- Even N → N-1 combos, each a perfect matching (all two-person pairs).
- Odd N → one developer gets a SOLO "self-review" slot each combo
           (RULES R5.2 default), rotating fairly. Never a three-person pair.

Rotation across working days is a simple round-robin over the combo list,
advancing one position per working day (RULES R2.3). State is *derived* from
the last used combo index (read from history), never a mutable counter.
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import PairType


@dataclass(frozen=True)
class Pair:
    """One assignment within a combo. `member_b` is None for a SOLO slot."""

    member_a: int
    member_b: int | None
    pair_type: PairType = PairType.DEV
    member_c: int | None = None

    def as_tuple(self) -> tuple[int, int | None]:
        return (self.member_a, self.member_b)

    def members(self) -> frozenset[int]:
        ids = {self.member_a}
        if self.member_b is not None:
            ids.add(self.member_b)
        if self.member_c is not None:
            ids.add(self.member_c)
        return frozenset(ids)


@dataclass(frozen=True)
class Combo:
    index: int
    pairs: tuple[Pair, ...]


_BYE = None  # sentinel used by the circle method for an odd participant count


def build_combos(dev_ids: list[int]) -> list[Combo]:
    """Return every distinct daily combo for the given ordered developer ids.

    Always uses the circle method so every assignment is a two-person pair
    (odd counts get a rotating SOLO slot). No three-person pairs are ever
    produced (operator rule: "ab do bandon ka hi pair banega").
    """
    return _build_combos_circle(dev_ids)


def _build_combos_circle(dev_ids: list[int]) -> list[Combo]:
    """Circle method: fix the first element, rotate the rest."""
    ids: list[int | None] = list(dev_ids)
    if len(ids) < 2:
        # Nobody to pair, or a single dev → a lone self-review slot.
        if len(ids) == 1:
            return [Combo(0, (Pair(ids[0], None, PairType.SOLO),))]  # type: ignore[arg-type]
        return []

    if len(ids) % 2 == 1:
        ids.append(_BYE)  # odd → add a bye so pairs are well-defined

    n = len(ids)
    rounds = n - 1
    half = n // 2
    fixed = ids[0]
    rotating = ids[1:]

    combos: list[Combo] = []
    for r in range(rounds):
        arrangement = [fixed] + rotating
        pairs: list[Pair] = []
        for i in range(half):
            a = arrangement[i]
            b = arrangement[n - 1 - i]
            if a is _BYE or b is _BYE:
                present = a if a is not _BYE else b
                pairs.append(Pair(present, None, PairType.SOLO))  # type: ignore[arg-type]
            else:
                pairs.append(Pair(a, b, PairType.DEV))  # type: ignore[arg-type]
        combos.append(Combo(r, tuple(pairs)))
        # rotate clockwise, keeping the first element fixed
        rotating = [rotating[-1]] + rotating[:-1]
    return combos


def next_combo_index(last_index: int | None, combo_count: int) -> int:
    """Round-robin advance (RULES R2.3). None → start at combo 0."""
    if combo_count <= 0:
        raise ValueError("combo_count must be positive")
    if last_index is None:
        return 0
    return (last_index + 1) % combo_count


def select_combo(dev_ids: list[int], last_index: int | None) -> Combo:
    """Pick the next combo for a working day given the last-used combo index."""
    combos = build_combos(dev_ids)
    if not combos:
        raise ValueError("no developers available to pair")
    idx = next_combo_index(last_index, len(combos))
    return combos[idx]
