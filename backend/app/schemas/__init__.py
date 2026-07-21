"""Pydantic request/response models (the API contract)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Auth ─────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    username: str


class OpenRouterModelsRequest(BaseModel):
    api_key: str | None = None
    free_only: bool = False
    search: str = ""


class OpenRouterModelOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    context_length: int | None = None
    free: bool


class OpenRouterModelsResponse(BaseModel):
    models: list[OpenRouterModelOut]
    total: int
    error: str | None = None


# ── Members ──────────────────────────────────────────────
class MemberBase(BaseModel):
    name: str
    matrix_user_id: str | None = None
    role: str = Field(pattern="^(DEVELOPER|QA)$")


class MemberCreate(MemberBase):
    pass


class MemberUpdate(BaseModel):
    name: str | None = None
    matrix_user_id: str | None = None
    role: str | None = Field(default=None, pattern="^(DEVELOPER|QA)$")
    active: bool | None = None


class MemberOut(ORMModel):
    id: int
    name: str
    matrix_user_id: str | None
    role: str
    active: bool
    lead_order: int
    config_gap: bool = False


# ── Rounds / dashboard ───────────────────────────────────
class PairOut(BaseModel):
    member_a: str
    member_b: str | None
    member_c: str | None = None
    pair_type: str


class RoundPreview(BaseModel):
    round_date: date
    combo_index: int
    combo_label: str
    pairs: list[PairOut]
    team_lead: str | None
    rendered_text: str


class BotStatus(BaseModel):
    state: str
    element_connected: bool
    database_connected: bool
    last_send_at: datetime | None
    next_send_at: datetime | None


# ── Settings ─────────────────────────────────────────────
class ScheduleSettings(BaseModel):
    send_time: str
    working_days: list[str]
    timeliness_cutoff: str
    timezone: str


class SettingsOut(BaseModel):
    schedule: ScheduleSettings
    reports: dict
    llm: dict
    bot: dict
