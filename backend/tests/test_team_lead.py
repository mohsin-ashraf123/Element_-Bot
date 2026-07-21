"""Tests for the deterministic Team Lead rotation (RULES §8)."""

import pytest

from app.domain.team_lead import preview_next_leads, select_lead

# 6 members in lead order.
ORDER = [1, 2, 3, 4, 5, 6]
ALL_ACTIVE = set(ORDER)


def test_first_lead_is_first_in_order():
    assert select_lead(ORDER, ALL_ACTIVE, None) == 1


def test_rotation_advances_and_wraps():
    assert select_lead(ORDER, ALL_ACTIVE, 1) == 2
    assert select_lead(ORDER, ALL_ACTIVE, 5) == 6
    assert select_lead(ORDER, ALL_ACTIVE, 6) == 1


def test_inactive_member_is_skipped_without_consuming_turn():
    active = ALL_ACTIVE - {2}
    # after 1, member 2 is inactive → 3 leads next.
    assert select_lead(ORDER, active, 1) == 3


def test_previous_lead_now_inactive_still_advances():
    active = ALL_ACTIVE - {3}
    # last lead 3 became inactive; next eligible after position of 3 is 4.
    assert select_lead(ORDER, active, 3) == 4


def test_preview_next_leads():
    assert preview_next_leads(ORDER, ALL_ACTIVE, 2, 5) == [3, 4, 5, 6, 1]


def test_no_active_members_raises():
    with pytest.raises(ValueError):
        select_lead(ORDER, set(), None)
