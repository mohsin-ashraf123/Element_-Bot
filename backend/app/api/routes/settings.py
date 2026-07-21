"""Schedule & rules / settings endpoints (FR-17 subset)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.schemas import OpenRouterModelsRequest, OpenRouterModelsResponse
from app.services import openrouter_service, settings_service

router = APIRouter(
    prefix="/settings",
    tags=["settings"],
    dependencies=[Depends(get_current_user)],
)


@router.get("")
def get_settings(db: Session = Depends(get_db)) -> dict[str, Any]:
    return settings_service.get_all(db)


@router.put("/{key}")
def update_setting(
    key: str, value: dict[str, Any], db: Session = Depends(get_db)
) -> dict[str, Any]:
    settings_service.set_setting(db, key, value, actor="admin")
    return {"key": key, "value": value}


@router.post("/openrouter/models", response_model=OpenRouterModelsResponse)
def openrouter_models(payload: OpenRouterModelsRequest) -> OpenRouterModelsResponse:
    result = openrouter_service.list_models(
        api_key=payload.api_key,
        free_only=payload.free_only,
        search=payload.search,
    )
    return OpenRouterModelsResponse(**result)
