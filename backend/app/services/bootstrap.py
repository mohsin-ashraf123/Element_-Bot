"""First-run bootstrap: create tables and seed the default roster + settings.

For MVP/dev this uses `create_all`. Alembic migrations own the schema once the
project moves toward production (ARCHITECTURE §3.2, Phase 0).
"""

from __future__ import annotations

from sqlalchemy import select

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
    ("Habiba", Role.QA, "@habiba:matrix.org"),
    ("Aqeel", Role.QA, "@aqeel:matrix.org"),
]


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
