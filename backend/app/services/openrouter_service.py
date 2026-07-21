"""OpenRouter model catalog — proxied so keys stay server-side when configured."""

from __future__ import annotations

import httpx

from app.core.config import settings

_OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


def _is_free(model: dict) -> bool:
    model_id = str(model.get("id", ""))
    if model_id.endswith(":free"):
        return True
    pricing = model.get("pricing") or {}
    try:
        prompt = float(pricing.get("prompt") or 0)
        completion = float(pricing.get("completion") or 0)
        return prompt == 0 and completion == 0
    except (TypeError, ValueError):
        return False


def _normalize(model: dict) -> dict:
    return {
        "id": model.get("id", ""),
        "name": model.get("name") or model.get("id", ""),
        "description": (model.get("description") or "")[:200] or None,
        "context_length": model.get("context_length"),
        "free": _is_free(model),
    }


def list_models(
    *,
    api_key: str | None = None,
    free_only: bool = False,
    search: str = "",
) -> dict:
    """Fetch models from OpenRouter and optionally filter."""
    key = (api_key or settings.llm_api_key or "").strip()
    if not key:
        return {
            "models": [],
            "total": 0,
            "error": "OpenRouter API key required — paste in Settings or set LLM_API_KEY in .env",
        }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                _OPENROUTER_MODELS_URL,
                headers={"Authorization": f"Bearer {key}"},
            )
        if resp.status_code == 401:
            return {"models": [], "total": 0, "error": "Invalid OpenRouter API key"}
        if resp.status_code != 200:
            return {
                "models": [],
                "total": 0,
                "error": f"OpenRouter API error ({resp.status_code})",
            }

        raw = resp.json().get("data") or []
        models = [_normalize(m) for m in raw if m.get("id")]

        if free_only:
            models = [m for m in models if m["free"]]

        q = search.strip().lower()
        if q:
            models = [
                m
                for m in models
                if q in m["id"].lower() or q in m["name"].lower()
            ]

        models.sort(key=lambda m: (not m["free"], m["name"].lower()))

        return {"models": models, "total": len(models), "error": None}

    except httpx.RequestError as exc:
        return {"models": [], "total": 0, "error": f"Network error: {exc}"}
