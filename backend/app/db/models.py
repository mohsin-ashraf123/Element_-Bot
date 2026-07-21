"""SQLAlchemy ORM models — the single source of truth (MEMORY.md §4).

Schema mirrors the relational sketch in MEMORY.md: members, settings,
pairing rounds/pairings/leads, element events, performance records, lead
accountability, reports, jobs and the audit log.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    matrix_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # DEVELOPER | QA
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    lead_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Setting(Base):
    """Key/value config store (schedule, cutoff, QA pair, lead order, …)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(String(120), nullable=True)


class PairingRound(Base):
    __tablename__ = "pairing_rounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    round_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    combo_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    rendered_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pairings: Mapped[list["Pairing"]] = relationship(
        back_populates="round", cascade="all, delete-orphan"
    )
    lead: Mapped["TeamLeadAssignment"] = relationship(
        back_populates="round", cascade="all, delete-orphan", uselist=False
    )
    events: Mapped[list["ElementEvent"]] = relationship(
        back_populates="round", cascade="all, delete-orphan"
    )


class Pairing(Base):
    __tablename__ = "pairings"

    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("pairing_rounds.id", ondelete="CASCADE"))
    member_a_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    member_b_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    member_c_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    pair_type: Mapped[str] = mapped_column(String(10), nullable=False)  # DEV | QA | SOLO

    round: Mapped["PairingRound"] = relationship(back_populates="pairings")


class TeamLeadAssignment(Base):
    __tablename__ = "team_lead_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("pairing_rounds.id", ondelete="CASCADE"))
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))

    round: Mapped["PairingRound"] = relationship(back_populates="lead")


class ElementEvent(Base):
    __tablename__ = "element_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int | None] = mapped_column(
        ForeignKey("pairing_rounds.id", ondelete="CASCADE"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)  # daily_message | report_post
    matrix_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rendered_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    round: Mapped["PairingRound"] = relationship(back_populates="events")


class PerformanceRecord(Base):
    __tablename__ = "performance_records"
    __table_args__ = (
        UniqueConstraint("member_id", "record_date", name="uq_member_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    record_date: Mapped[date] = mapped_column(Date, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    on_time: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)  # clean|has_issues|undetermined|missed
    source_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    corrected_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LeadAccountability(Base):
    __tablename__ = "lead_accountability"

    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("pairing_rounds.id", ondelete="CASCADE"))
    lead_member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    team_completion: Mapped[float] = mapped_column(default=0.0)
    team_on_time: Mapped[float] = mapped_column(default=0.0)
    team_clean: Mapped[float] = mapped_column(default=0.0)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    period_type: Mapped[str] = mapped_column(String(10), nullable=False)  # weekly | monthly
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    metrics_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    narrative_source: Mapped[str | None] = mapped_column(String(20), nullable=True)  # llm | template
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    llm_meta_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    posted_image_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    posted_text_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="generated", nullable=False)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(40), nullable=False)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
