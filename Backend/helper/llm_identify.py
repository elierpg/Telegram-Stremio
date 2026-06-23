"""Identify movies/TV from filename or caption text using Groq LLM."""

import json
import re
from typing import Optional

from groq import Groq as GroqClient

from Backend.config import Telegram
from Backend.logger import LOGGER

_CLIENT: GroqClient | None = None
_MODEL = "groq/compound-mini"
_CACHE: dict[str, dict | None] = {}
_CACHE_MAX = 500


def _get_client() -> GroqClient | None:
    global _CLIENT
    if _CLIENT is None and Telegram.GROQ_API_KEY:
        _CLIENT = GroqClient(api_key=Telegram.GROQ_API_KEY)
    return _CLIENT


def _extract_json(text: str) -> dict | None:
    """Parse JSON from LLM response, handling markdown fences and stray text."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return None


def _build_prompt(text: str) -> str:
    return (
        "From this filename or text, identify the movie or TV show. "
        "Return ONLY valid JSON with no markdown, no extra text:\n"
        '{"title": "...", "year": 2024, "type": "movie"|"tv", '
        '"season": null|number, "episode": null|number, '
        '"confidence": 0.95}\n\n'
        f"Text: {text}"
    )


async def llm_identify(text: str) -> Optional[dict]:
    """Identify media from filename/caption text via Groq compound-mini.

    Returns dict with keys: title, year, type, season, episode, confidence.
    Returns None when the API is not configured, the call fails, or the
    response can not be parsed.
    """
    cache_key = text.strip().lower()
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    client = _get_client()
    if client is None:
        _CACHE[cache_key] = None
        return None

    loop = __import__("asyncio").get_running_loop()

    try:
        response = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model=_MODEL,
                messages=[{"role": "user", "content": _build_prompt(text)}],
                temperature=0.1,
                max_tokens=256,
            ),
        )
    except Exception as e:
        LOGGER.warning(f"[LLM] Groq API call failed for '{text[:60]}': {e}")
        _CACHE[cache_key] = None
        return None

    raw = getattr(response, "choices", [{}])[0]
    content = getattr(raw, "message", None)
    content_str = getattr(content, "content", "") if content else ""

    if not content_str:
        _CACHE[cache_key] = None
        return None

    parsed = _extract_json(content_str)
    if parsed is None:
        LOGGER.warning(f"[LLM] Could not parse response: {content_str[:200]}")
        _CACHE[cache_key] = None
        return None

    parsed.setdefault("title", "")
    parsed.setdefault("year", None)
    parsed.setdefault("type", None)
    parsed.setdefault("season", None)
    parsed.setdefault("episode", None)
    parsed.setdefault("confidence", 0.0)

    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[cache_key] = parsed

    LOGGER.info(
        f"[LLM] '{text[:60]}' → '{parsed['title']}' "
        f"(year={parsed['year']}, type={parsed['type']}, "
        f"conf={parsed['confidence']})"
    )
    return parsed
