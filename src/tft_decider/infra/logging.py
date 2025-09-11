"""
Structured logging helpers using structlog.

Overview
--------
Provide a small, self-contained logging setup built on top of structlog, enforcing
presence of the core fields: ``component``, ``event``, and ``thread_id``.
This module is side-effect free until ``setup_logging()`` is called.

Design
------
- Keep configuration minimal and JSON-rendered for easy ingestion.
- Enforce core fields via a custom processor (adds fallbacks if missing).
- Expose helpers to create a properly bound logger and to generate thread IDs.
- Avoid importing project-internal modules to keep this file fully standalone.

Integration
-----------
Call ``setup_logging()`` once during application startup (e.g., in the Streamlit app).
Use ``logger_for(component, event)`` to obtain a bound logger for a specific action.

Usage
-----
>>> from tft_decider.infra.logging import setup_logging, logger_for
>>> setup_logging()
>>> log = logger_for(component="ui.app", event="start")
>>> log.info("App booted", version="0.1.0")
"""

from __future__ import annotations

import logging
import sys
import uuid
from typing import Any, Callable, Final

import structlog

# -----------------------------
# Public constants & exports
# -----------------------------
DEFAULT_COMPONENT: Final[str] = "unspecified.component"
DEFAULT_EVENT: Final[str] = "unspecified.event"
DEFAULT_THREAD_ID: Final[str] = "no-thread-id"

__all__: Final[list[str]] = [
    "setup_logging",
    "logger_for",
    "generate_thread_id",
]


# -----------------------------
# Internal helpers
# -----------------------------

def _ensure_core_fields(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Ensure required structured fields are present.

    The project requires every log entry to include: ``component``, ``event``,
    and ``thread_id``. This processor adds safe fallbacks if they are missing,
    so downstream tooling always sees these keys.

    Args:
        _: Unused ``logger`` placeholder (structlog signature).
        __: Unused ``method_name`` placeholder (structlog signature).
        event_dict: The current structured event fields.

    Returns:
        The possibly augmented ``event_dict`` with guaranteed core fields.
    """

    event_dict.setdefault("component", DEFAULT_COMPONENT)
    event_dict.setdefault("event", DEFAULT_EVENT)
    event_dict.setdefault("thread_id", DEFAULT_THREAD_ID)
    return event_dict


def _resolve_level(level: int | str) -> int:
    """Resolve a logging level from ``int`` or name (case-insensitive)."""

    if isinstance(level, int):
        return level
    name = str(level).upper()
    return logging._nameToLevel.get(name, logging.INFO)


# -----------------------------
# Public API
# -----------------------------

_CONFIGURED: bool = False


def setup_logging(level: int | str = "INFO") -> None:
    """Configure structlog and the stdlib logging bridge.

    This function is idempotent: calling it multiple times will be a no-op
    after the first successful configuration.

    Args:
        level: The minimum log level (e.g., ``"INFO"``, ``"DEBUG"``).
    """

    global _CONFIGURED
    if _CONFIGURED:
        return

    resolved_level = _resolve_level(level)

    # Route stdlib logging through structlog; keep the message as-is because
    # structlog's JSON renderer will produce the final serialization.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=resolved_level,
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _ensure_core_fields,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _CONFIGURED = True


def generate_thread_id() -> str:
    """Generate a stable thread identifier for request/interaction context.

    Returns:
        A hex string suitable for binding as ``thread_id``.
    """

    return uuid.uuid4().hex


def logger_for(component: str, event: str, thread_id: str | None = None) -> structlog.BoundLogger:
    """Return a structlog logger bound with required fields.

    Args:
        component: Logical component name (e.g., ``"ui.app"``, ``"core.scoring"``).
        event: Short event name describing the action (e.g., ``"score"``).
        thread_id: Optional correlation ID. If ``None``, one is generated.

    Returns:
        A ``BoundLogger`` with ``component``, ``event`` and ``thread_id`` already bound.
    """

    if thread_id is None:
        thread_id = generate_thread_id()
    return structlog.get_logger().bind(
        component=component,
        event=event,
        thread_id=thread_id,
    )