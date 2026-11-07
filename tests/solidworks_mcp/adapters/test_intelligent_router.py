"""``IntelligentRouter`` unit behaviour (the runtime-feature tests cover the rest)."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.complexity_analyzer import ComplexityAnalyzer
from solidworks_mcp.adapters.intelligent_router import IntelligentRouter
from solidworks_mcp.cache.response_cache import CachePolicy, ResponseCache


@pytest.mark.asyncio
async def test_an_exception_becomes_an_error_result() -> None:
    router = IntelligentRouter(
        analyzer=ComplexityAnalyzer(), cache=ResponseCache(CachePolicy(enabled=False))
    )

    async def _raises(payload: object) -> None:
        raise RuntimeError("COM went away")

    result, route = await router.execute(
        operation="create_extrusion",
        payload={},
        call_args=({},),
        call_kwargs={},
        com_operation=_raises,
        vba_operation=None,
    )

    assert result.is_error and "COM went away" in str(result.error)
    assert route.route == "com-error"


def test_interference_is_not_cached() -> None:
    """Interference changes as parts are mated; a cached answer went stale (#209)."""
    router = IntelligentRouter(
        analyzer=ComplexityAnalyzer(), cache=ResponseCache(CachePolicy(enabled=True))
    )

    assert "check_interference" not in router._cacheable_operations
