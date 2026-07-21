"""LLM completions — OpenRouter-first, used for message analysis narratives."""

from __future__ import annotations

import json
import logging
import re

import httpx

from app.core.config import settings
from app.services import settings_service

logger = logging.getLogger(__name__)

_OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


def _api_key(db=None) -> str:
    if db is not None:
        from app.services.settings_service import get_setting_raw

        llm = get_setting_raw(db, "llm")
        if llm.get("api_key"):
            return str(llm["api_key"]).strip()
    return (settings.llm_api_key or "").strip()


def _model(db=None) -> str:
    if db is not None:
        from app.services.settings_service import get_setting_raw

        llm = get_setting_raw(db, "llm")
        if llm.get("model"):
            return str(llm["model"]).strip()
    return (settings.llm_model or "").strip()


def unavailable_reason(db=None) -> str | None:
    """Why LLM is off — for UI error messages."""
    if db is None:
        if not settings.llm_api_key.strip():
            return "OpenRouter API key not set — paste key in Settings and tap Save key"
        if not settings.llm_model.strip():
            return "No LLM model selected in Settings"
        return None

    from app.services.settings_service import get_setting_raw

    llm = get_setting_raw(db, "llm")
    if not llm.get("enabled", True):
        return "AI summaries are disabled in Settings"
    if not _api_key(db):
        return "OpenRouter API key not saved — paste sk-or-… key and tap Save key"
    if not _model(db):
        return "No model selected — choose a model in Settings"
    return None


def is_available(db=None) -> bool:
    return unavailable_reason(db) is None


def complete_json(
    *,
    system: str,
    user: str,
    db=None,
    temperature: float = 0.2,
) -> dict | None:
    data, _ = complete_json_with_error(
        system=system, user=user, db=db, temperature=temperature
    )
    return data


def complete_json_with_error(
    *,
    system: str,
    user: str,
    db=None,
    temperature: float = 0.2,
) -> tuple[dict | None, str | None]:
    """Chat completion expecting JSON; returns (data, error_message)."""
    key = _api_key(db)
    model = _model(db)
    if not key or not model:
        return None, unavailable_reason(db) or "LLM not configured"

    try:
        with httpx.Client(timeout=90.0) as client:
            resp = client.post(
                _OPENROUTER_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://pairflow.local",
                    "X-Title": "PairFlow",
                },
                json={
                    "model": model,
                    "temperature": temperature,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
        if resp.status_code != 200:
            detail = resp.text[:200]
            logger.warning("LLM error %s: %s", resp.status_code, detail)
            return None, f"OpenRouter returned {resp.status_code} — check key and model"

        content = resp.json()["choices"][0]["message"]["content"]
        parsed = _parse_json_block(content)
        if parsed is None:
            return None, "AI response was not valid JSON — try again or pick another model"
        return parsed, None
    except Exception as exc:
        logger.exception("LLM completion failed")
        return None, f"AI request failed: {exc}"


def _parse_json_block(text: str) -> dict | None:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None
