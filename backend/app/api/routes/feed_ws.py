"""WebSocket feed — separate router (no HTTP Bearer middleware)."""

from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.services import dashboard_service
from app.services.feed_hub import get_hub

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.websocket("/feed/ws")
async def feed_ws(websocket: WebSocket, token: str = Query(...)) -> None:
    """Real-time room feed — pushes when Matrix timeline changes."""
    if not decode_access_token(token):
        await websocket.close(code=1008, reason="Unauthorized")
        return

    hub = get_hub()
    await hub.connect(websocket)
    db = SessionLocal()
    try:
        initial = dashboard_service.build_feed(db)
        await websocket.send_json({"type": "feed", "data": initial})
    finally:
        db.close()

    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(websocket)
