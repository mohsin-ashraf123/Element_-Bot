"""First-run bootstrap: create tables and seed the default roster + settings.

For MVP/dev this uses `create_all`. Alembic migrations own the schema once the
project moves toward production (ARCHITECTURE §3.2, Phase 0).
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select

from app.db.base import Base, SessionLocal, engine
from app.db.models import Member
from app.domain.constants import Role
from app.services import settings_service

# Initial roster from PRD §7. Matrix IDs are placeholders the operator edits.
_SEED_MEMBERS = [
    ("Uzair", Role.DEVELOPER, "@uzair:matrix.org"),
    ("Saad", Role.DEVELOPER, "@saad:matrix.org"),
    ("Faz", Role.DEVELOPER, "@faz:matrix.org"),
    ("Hamza", Role.DEVELOPER, "@hamza:matrix.org"),
    ("Farhan", Role.DEVELOPER, "@farhan12:matrix.org"),
    ("Mohsin", Role.DEVELOPER, "@mohsinashraf:matrix.org"),
    ("Habiba", Role.QA, "@habiba:matrix.org"),
    ("Aqeel", Role.QA, "@aqeel:matrix.org"),
]

# Members ensured on every boot (idempotent, keyed by Matrix ID) so existing
# databases — including Railway — pick up roster additions after a redeploy.
_ENSURE_MEMBERS = [
    ("Mohsin", Role.DEVELOPER, "@mohsinashraf:matrix.org"),
]


def _ensure_members(db) -> None:
    """Add roster members that are missing, matched on their Matrix ID."""
    changed = False
    for name, role, mxid in _ENSURE_MEMBERS:
        exists = db.scalar(select(Member).where(Member.matrix_user_id == mxid))
        if exists is not None:
            continue
        max_order = db.scalar(select(func.max(Member.lead_order))) or 0
        db.add(
            Member(
                name=name,
                role=role.value,
                matrix_user_id=mxid,
                active=True,
                lead_order=max_order + 1,
            )
        )
        changed = True
    if changed:
        db.commit()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        settings_service.ensure_defaults(db)
        if db.scalar(select(Member).limit(1)) is None:
            for order, (name, role, mxid) in enumerate(_SEED_MEMBERS):
                db.add(
                    Member(
                        name=name,
                        role=role.value,
                        matrix_user_id=mxid,
                        active=True,
                        lead_order=order,
                    )
                )
            db.commit()
        _ensure_members(db)

    from pathlib import Path

    from app.core.config import settings
    from app.services import room_feed_cache_db

    cache_file = Path(settings.matrix_e2ee_store_path).resolve().parent / "member_feed_cache.json"
    # Always merge the local Element mirror into Postgres so dashboard / performance
    # read the same room timeline on every boot (local + Railway after volume sync).
    try:
        imported = room_feed_cache_db.import_json_file(cache_file)
        if imported:
            logging.getLogger(__name__).info("Synced %d message(s) from member_feed_cache.json", imported)
    except Exception:
        logging.getLogger(__name__).debug("member_feed_cache sync skipped", exc_info=True)
    room_feed_cache_db.seed_from_file_if_empty(cache_file)
    count = room_feed_cache_db.seed_bundled_cache()
    if count:
        logging.getLogger(__name__).info("Bundled room message seed: %d message(s)", count)
