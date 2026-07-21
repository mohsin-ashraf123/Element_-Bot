"""Element (Matrix) service interface — implemented in Phase 1 (matrix-nio).

Defined now as a Protocol so the service layer can depend on the boundary
without pulling in E2EE/matrix-nio until that phase begins (ARCHITECTURE §3.5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ElementHealth:
    connected: bool
    joined: bool
    e2ee_ok: bool
    last_sync_at: str | None = None


class ElementService(Protocol):
    async def ensure_joined(self, room_id: str) -> None: ...

    async def send_message(self, text: str) -> str:  # returns matrix event id
        ...

    async def send_image(self, png_bytes: bytes, caption: str) -> str: ...

    async def health(self) -> ElementHealth: ...


class NotConfiguredElementService:
    """Placeholder used until Matrix credentials are provided (Phase 1)."""

    async def ensure_joined(self, room_id: str) -> None:
        raise RuntimeError("Element service not configured yet")

    async def send_message(self, text: str) -> str:
        raise RuntimeError("Element service not configured yet")

    async def send_image(self, png_bytes: bytes, caption: str) -> str:
        raise RuntimeError("Element service not configured yet")

    async def health(self) -> ElementHealth:
        return ElementHealth(connected=False, joined=False, e2ee_ok=False)
