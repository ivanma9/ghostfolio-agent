"""Tests for the tool-level TTL cache decorator."""

import asyncio
import time
from unittest.mock import patch

import pytest

from ghostfolio_agent.tools.cache import _caches, clear_all_caches, ttl_cache


@pytest.fixture(autouse=True)
def _clean_caches():
    """Clear all caches before and after each test."""
    clear_all_caches()
    yield
    clear_all_caches()


async def test_cache_hit():
    """Cached result is returned on second call with same args."""
    call_count = 0

    @ttl_cache(ttl=60)
    async def my_func(x: str) -> str:
        nonlocal call_count
        call_count += 1
        return f"result-{x}"

    result1 = await my_func("a")
    result2 = await my_func("a")

    assert result1 == "result-a"
    assert result2 == "result-a"
    assert call_count == 1  # Only called once


async def test_cache_miss_different_args():
    """Different arguments produce separate cache entries."""
    call_count = 0

    @ttl_cache(ttl=60)
    async def my_func(x: str) -> str:
        nonlocal call_count
        call_count += 1
        return f"result-{x}"

    result1 = await my_func("a")
    result2 = await my_func("b")

    assert result1 == "result-a"
    assert result2 == "result-b"
    assert call_count == 2


async def test_cache_expiry():
    """Cache entry expires after TTL."""
    call_count = 0

    @ttl_cache(ttl=1)
    async def my_func(x: str) -> str:
        nonlocal call_count
        call_count += 1
        return f"result-{call_count}"

    result1 = await my_func("a")
    assert result1 == "result-1"
    assert call_count == 1

    # Simulate time passing by patching the cached timestamp
    cache_name = my_func.__wrapped__.__qualname__
    key = (("a",), ())
    _caches[cache_name][key] = (_caches[cache_name][key][0], time.time() - 2)

    result2 = await my_func("a")
    assert result2 == "result-2"
    assert call_count == 2


async def test_no_args_caching():
    """Functions with no arguments are cached correctly."""
    call_count = 0

    @ttl_cache(ttl=60)
    async def my_func() -> str:
        nonlocal call_count
        call_count += 1
        return f"result-{call_count}"

    result1 = await my_func()
    result2 = await my_func()

    assert result1 == "result-1"
    assert result2 == "result-1"
    assert call_count == 1


async def test_kwargs_caching():
    """Keyword arguments are included in cache key."""
    call_count = 0

    @ttl_cache(ttl=60)
    async def my_func(x: str = "default") -> str:
        nonlocal call_count
        call_count += 1
        return f"result-{x}"

    result1 = await my_func(x="a")
    result2 = await my_func(x="b")
    result3 = await my_func(x="a")

    assert result1 == "result-a"
    assert result2 == "result-b"
    assert result3 == "result-a"
    assert call_count == 2


async def test_clear_all_caches():
    """clear_all_caches empties all registered caches."""

    @ttl_cache(ttl=60)
    async def func_a(x: str) -> str:
        return f"a-{x}"

    @ttl_cache(ttl=60)
    async def func_b(x: str) -> str:
        return f"b-{x}"

    await func_a("1")
    await func_b("2")

    # Caches should have entries
    assert any(len(c) > 0 for c in _caches.values())

    clear_all_caches()

    # All caches should be empty
    assert all(len(c) == 0 for c in _caches.values())


async def test_cache_preserves_function_metadata():
    """Decorator preserves original function name and docstring."""

    @ttl_cache(ttl=60)
    async def my_documented_func(x: str) -> str:
        """This is a docstring."""
        return x

    assert my_documented_func.__name__ == "my_documented_func"
    assert my_documented_func.__doc__ == "This is a docstring."
