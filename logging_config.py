"""Structured application logging and request correlation."""

from __future__ import annotations

import json
import logging
import os
import sys
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

REQUEST_ID_HEADER = "X-Request-ID"
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_RESERVED_LOG_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__)
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "prompt",
    "reply",
    "secret",
    "token",
)


def get_request_id() -> str | None:
    """Return the request ID active in the current async context."""
    return _request_id.get()


def set_request_id(request_id: str | None) -> Token:
    """Set the request ID and return a token suitable for resetting it."""
    return _request_id.set(request_id)


def reset_request_id(token: Token) -> None:
    """Restore the request context represented by *token*."""
    _request_id.reset(token)


def normalize_request_id(value: str | None) -> str:
    """Accept a UUID request ID or generate a new UUID."""
    if value:
        try:
            return str(UUID(value))
        except (ValueError, AttributeError):
            pass
    return str(uuid4())


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    if normalized.endswith(("_count", "_keys", "_length")):
        return False
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _sanitize(value: Any, key: str = "") -> Any:
    if _is_sensitive_key(key):
        return "[REDACTED]"
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize(item) for item in value]
    return str(value)


class JsonFormatter(logging.Formatter):
    """Render each log record as one safe JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "service": os.environ.get("SERVICE_NAME", "apira-agent"),
            "environment": os.environ.get("ENVIRONMENT", "development"),
            "event": getattr(record, "event", "application.log"),
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_RECORD_FIELDS and key not in payload:
                payload[key] = _sanitize(value, key)
        if record.exc_info:
            payload["error_type"] = record.exc_info[0].__name__
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """Compact local-development formatter with correlation context."""

    def format(self, record: logging.LogRecord) -> str:
        request_id = get_request_id() or "-"
        event = getattr(record, "event", "application.log")
        return f"{record.levelname} [{request_id}] {event}: {record.getMessage()}"


def configure_logging() -> None:
    """Configure stdout logging from environment settings."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    formatter: logging.Formatter
    if os.environ.get("LOG_FORMAT", "json").lower() == "text":
        formatter = TextFormatter()
    else:
        formatter = JsonFormatter()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Uvicorn's access line duplicates the request.completed application event.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False
    access_logger.disabled = True


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    message: str,
    **fields: Any,
) -> None:
    """Emit a structured event with explicitly supplied metadata."""
    logger.log(level, message, extra={"event": event, **fields})
