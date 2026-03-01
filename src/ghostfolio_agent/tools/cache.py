"""TTL cache decorator for agent tools."""

import time
import structlog
from functools import wraps

logger = structlog.get_logger()

_caches: dict[str, dict] = {}


def ttl_cache(ttl: int = 300):
    """Decorator that caches async function results by args with a TTL in seconds."""

    def decorator(func):
        cache_name = func.__qualname__
        _caches[cache_name] = {}

        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            cache = _caches[cache_name]
            if key in cache:
                result, cached_at = cache[key]
                if time.time() - cached_at < ttl:
                    logger.debug("tool_cache_hit", tool=cache_name, key=str(key))
                    return result
            result = await func(*args, **kwargs)
            cache[key] = (result, time.time())
            return result

        return wrapper

    return decorator


def clear_all_caches():
    """Clear all tool caches. Useful for testing."""
    for cache in _caches.values():
        cache.clear()
