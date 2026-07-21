"""Single-admin authentication (FR-12)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import create_access_token
from app.schemas import LoginRequest, MeResponse, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    # MVP: validate against configured admin credentials. Post-MVP moves the
    # hashed password into the DB with a change-password flow.
    if (
        payload.username != settings.admin_username
        or payload.password != settings.admin_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    return TokenResponse(access_token=create_access_token(subject=payload.username))


@router.get("/me", response_model=MeResponse)
def me(user: str = Depends(get_current_user)) -> MeResponse:
    return MeResponse(username=user)
