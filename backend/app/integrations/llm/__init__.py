"""LLM adapter interface — provider-agnostic (implemented in Phase 4).

The adapter only ever *narrates* pre-computed numbers; it never recalculates
figures or touches deterministic logic (PRD §12, ARCHITECTURE §3.6).
"""

from __future__ import annotations

from typing import Protocol


class LLMAdapter(Protocol):
    async def generate_narrative(
        self, metrics: dict, report_texts: list[str], period: str
    ) -> str: ...


def template_narrative(metrics: dict, period: str) -> str:
    """Deterministic fallback narrative when the LLM is unavailable (R18.1)."""
    completion = metrics.get("team_completion_rate", 0)
    on_time = metrics.get("team_on_time_rate", 0)
    return (
        f"{period} summary — team completion {completion}%, on-time {on_time}%. "
        "AI summary unavailable; deterministic template used. "
        "The numbers above are always exact."
    )
