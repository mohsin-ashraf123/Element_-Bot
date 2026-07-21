"""FastAPI application factory and wiring."""

from __future__ import annotations

import asyncio
import sys

# Playwright launches its driver via asyncio subprocesses; on Windows the default
# Selector loop (used by uvicorn --reload) cannot do that — Proactor is required.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import get_current_user
from app.api.routes import analysis, auth, dashboard, feed_ws, health, reports, room, rounds, settings as settings_route, team
from app.core.config import settings
from app.services.bootstrap import init_db


def _cors_origins() -> list[str]:
    import os

    raw = os.getenv("FRONTEND_URL", "").strip()
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if settings.is_production:
        return origins or ["*"]
    return ["*"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging

    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger(__name__)

    try:
        init_db()
        log.info("Database bootstrap complete")
    except Exception as exc:
        # Do not crash the process — Railway healthcheck must reach /api/health/live
        # even when DATABASE_URL is missing or Postgres is still starting.
        log.error("Database bootstrap failed (API will start; DB endpoints may fail): %s", exc)

    import threading

    from app.services.feed_hub import get_hub
    from app.services.matrix_e2ee import warm_store
    from app.services.matrix_trust import run_trust_check
    from app.services.scheduler_service import start as start_scheduler

    def _startup_matrix() -> None:
        """Login, join rooms, and warm E2EE as early as possible on Railway."""
        import time

        time.sleep(3)
        try:
            from app.services import element_health, matrix_client

            if matrix_client.is_configured():
                matrix_client.get_session()
                matrix_client.ensure_joined_room()
                element_health.check(force=True)
                log.info("Matrix startup: joined rooms and refreshed health")
        except Exception as exc:
            log.warning("Matrix startup skipped: %s", exc)

    def _startup_warm() -> None:
        # Defer heavy Matrix E2EE work so login/API stay responsive on boot.
        import time

        time.sleep(8)
        warm_store()
        try:
            from app.db.session import SessionLocal
            from app.services import matrix_room_feed, settings_service, team_service

            db = SessionLocal()
            try:
                sched = settings_service.get_setting(db, "schedule")
                zone = sched.get("timezone", settings.timezone)
                mxid = {
                    m.matrix_user_id: m.name
                    for m in team_service.list_members(db)
                    if m.matrix_user_id
                }
                matrix_room_feed.prefetch_all(zone_name=zone, mxid_to_name=mxid)
            finally:
                db.close()
        except Exception as exc:
            logging.getLogger(__name__).warning("Feed prefetch skipped: %s", exc)

    def _deferred_trust() -> None:
        import time

        time.sleep(30)
        run_trust_check()

    def _warm_health() -> None:
        import time

        time.sleep(5)
        from app.services import element_health

        element_health.check(force=True)

    threading.Thread(target=_startup_matrix, daemon=True, name="matrix-startup").start()
    threading.Thread(target=_startup_warm, daemon=True, name="e2ee-warm").start()
    threading.Thread(target=_deferred_trust, daemon=True, name="matrix-trust").start()
    threading.Thread(target=_warm_health, daemon=True, name="matrix-health").start()
    # Listener disabled — isolated feed fetch avoids E2EE store lock clashes on Windows.
    # start_listener()
    start_scheduler()

    hub = get_hub()
    hub.bind_loop(asyncio.get_running_loop())
    hub.start_background_sync()

    yield

    hub.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="PairFlow API",
        description="Element Team Pairing & Review Automation Bot",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_prefix = "/api"
    protected = [Depends(get_current_user)]
    app.include_router(health.router, prefix=api_prefix)
    app.include_router(auth.router, prefix=api_prefix)
    app.include_router(dashboard.router, prefix=api_prefix, dependencies=protected)
    app.include_router(feed_ws.router, prefix=api_prefix)
    app.include_router(analysis.router, prefix=api_prefix, dependencies=protected)
    app.include_router(reports.router, prefix=api_prefix, dependencies=protected)
    app.include_router(room.router, prefix=api_prefix, dependencies=protected)
    app.include_router(team.router, prefix=api_prefix, dependencies=protected)
    app.include_router(rounds.router, prefix=api_prefix, dependencies=protected)
    app.include_router(settings_route.router, prefix=api_prefix)

    @app.get(api_prefix)
    def api_root() -> dict:
        return {
            "name": "PairFlow API",
            "version": "0.1.0",
            "docs": "/docs",
        }

    return app


app = create_app()
