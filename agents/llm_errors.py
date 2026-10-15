"""Map Gemini / A2A failures to a short message the UI can show."""

from __future__ import annotations


def _flatten(exc: BaseException) -> str:
    parts: list[str] = []
    current: BaseException | None = exc
    seen = 0
    while current is not None and seen < 6:
        parts.append(str(current))
        current = current.__cause__ or current.__context__
        seen += 1
    return "\n".join(parts)


def user_facing_llm_error(exc: BaseException) -> str:
    text = _flatten(exc)
    lower = text.lower()

    if (
        "api key" in lower
        or "invalid_api_key" in lower
        or "unauthenticated" in lower
        or "api_key_invalid" in lower
    ):
        return (
            "The Gemini API key is missing or invalid. Set GOOGLE_API_KEY in "
            "apira-agent/.env and apira-rag/.env, then recreate those containers."
        )
    if "resource_exhausted" in lower or "quota" in lower or " 429" in f" {text}":
        return (
            "The Gemini API quota is exhausted. Free tier is a small number of "
            "requests per minute; wait about a minute and try again, or use a "
            "key with higher quota."
        )
    if "json-rpc" in lower and ("-32603" in text or "internal error" in lower):
        return (
            "The research agent failed (usually Gemini quota or a bad API key). "
            "Wait a minute and retry. If it keeps happening, recreate the agent "
            "and rag containers after updating GOOGLE_API_KEY."
        )
    return f"The agent hit an error: {str(exc)[:300]}"
