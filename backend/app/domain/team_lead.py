"""Deterministic Team Lead rotation (RULES §8).

The lead is chosen daily from all members via round-robin over a configurable
ordered list. The rotation advances one position per working day and skips
inactive members without consuming their turn (R8.4). Like pairing, the
"next" lead is derived from the last assigned lead, not a stored counter.
"""

from __future__ import annotations


def select_lead(
    lead_order: list[int],
    active_ids: set[int],
    last_lead_id: int | None,
) -> int:
    """Return the next active member id in the lead order.

    Args:
        lead_order: the configured ordered round-robin list of member ids.
        active_ids: ids currently eligible (active) to lead.
        last_lead_id: the member who led on the previous working day.

    Raises:
        ValueError: if no active member is available to lead.
    """
    eligible = [m for m in lead_order if m in active_ids]
    if not eligible:
        raise ValueError("no active member available to be Team Lead")

    if last_lead_id is None or last_lead_id not in eligible:
        # First-ever assignment, or the previous lead is no longer eligible:
        # start from the earliest eligible position after the last known slot.
        if last_lead_id is None:
            return eligible[0]
        # find where last_lead sits in the full order, take next eligible after it
        return _next_eligible_after(lead_order, active_ids, last_lead_id)

    pos = eligible.index(last_lead_id)
    return eligible[(pos + 1) % len(eligible)]


def _next_eligible_after(
    lead_order: list[int], active_ids: set[int], anchor_id: int
) -> int:
    """Next eligible member strictly after `anchor_id` in the full order."""
    if anchor_id in lead_order:
        start = lead_order.index(anchor_id) + 1
    else:
        start = 0
    order_len = len(lead_order)
    for offset in range(order_len):
        candidate = lead_order[(start + offset) % order_len]
        if candidate in active_ids:
            return candidate
    raise ValueError("no active member available to be Team Lead")


def preview_next_leads(
    lead_order: list[int],
    active_ids: set[int],
    last_lead_id: int | None,
    count: int,
) -> list[int]:
    """Return the next `count` leads (for the UI's 'next N leads' preview)."""
    result: list[int] = []
    prev = last_lead_id
    for _ in range(count):
        nxt = select_lead(lead_order, active_ids, prev)
        result.append(nxt)
        prev = nxt
    return result
