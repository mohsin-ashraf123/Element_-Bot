"""Tests for the deterministic developer pairing (RULES §2–§5)."""

from app.domain.constants import PairType
from app.domain.pairing import build_combos, next_combo_index, select_combo

# Fixed roster of 4 developers (ids stand in for Uzair, Saad, Faz, Hamza).
UZAIR, SAAD, FAZ, HAMZA, FARHAN = 1, 2, 3, 4, 5
DEVS = [UZAIR, SAAD, FAZ, HAMZA]
DEVS_FIVE = [UZAIR, SAAD, FAZ, HAMZA, FARHAN]


def _pairset(combo):
    return {frozenset(p.as_tuple()) for p in combo.pairs}


def test_four_devs_yield_exactly_three_combos():
    combos = build_combos(DEVS)
    assert len(combos) == 3


def test_combos_cover_every_pair_exactly_once():
    combos = build_combos(DEVS)
    all_pairs = [frozenset(p.as_tuple()) for c in combos for p in c.pairs]
    # 3 combos * 2 pairs = 6 pair-slots, all distinct, covering all C(4,2)=6 pairs.
    assert len(all_pairs) == 6
    assert len(set(all_pairs)) == 6


def test_rotation_is_round_robin_and_wraps():
    assert next_combo_index(None, 3) == 0
    assert next_combo_index(0, 3) == 1
    assert next_combo_index(1, 3) == 2
    assert next_combo_index(2, 3) == 0


def test_same_combo_never_on_consecutive_days():
    last = None
    seen = []
    for _ in range(6):
        combo = select_combo(DEVS, last)
        seen.append(combo.index)
        last = combo.index
    for a, b in zip(seen, seen[1:]):
        assert a != b


def test_odd_dev_count_creates_solo_slot():
    combos = build_combos([UZAIR, SAAD, FAZ])  # 3 developers
    for combo in combos:
        solos = [p for p in combo.pairs if p.pair_type is PairType.SOLO]
        assert len(solos) == 1
        assert solos[0].member_b is None


def test_single_dev_is_solo():
    combos = build_combos([UZAIR])
    assert len(combos) == 1
    assert combos[0].pairs[0].pair_type is PairType.SOLO


def test_five_devs_yield_triple_plus_pair():
    combos = build_combos(DEVS_FIVE)
    assert len(combos) == 10
    for combo in combos:
        triples = [p for p in combo.pairs if p.member_c is not None]
        pairs = [p for p in combo.pairs if p.member_c is None and p.pair_type is PairType.DEV]
        assert len(triples) == 1
        assert len(pairs) == 1
        assert len(triples[0].members()) == 3
        assert len(pairs[0].members()) == 2
        covered = triples[0].members() | pairs[0].members()
        assert covered == frozenset(DEVS_FIVE)
