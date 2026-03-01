"""Shared utilities for the Ghostfolio agent."""

from typing import Any, Coroutine

import structlog

logger = structlog.get_logger()


async def safe_fetch(coro: Coroutine[Any, Any, Any], label: str) -> Any | None:
    """Await a coroutine, returning None on any exception.

    Logs a warning with the label and error on failure.
    Used for optional enrichment data that shouldn't block the main response.
    """
    try:
        return await coro
    except Exception as exc:
        logger.warning("enrichment_fetch_failed", label=label, error=str(exc))
        return None
