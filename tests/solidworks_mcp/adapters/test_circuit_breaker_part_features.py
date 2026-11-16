"""The part-feature methods pass through the circuit breaker."""

from __future__ import annotations

from typing import Any

import pytest

from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter

from .part_feature_calls import CALLS, IDS


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "args", "kwargs"), CALLS, ids=IDS)
async def test_each_part_feature_passes_through(
    name: str, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    inner = MockSolidWorksAdapter({})
    inner._current_sketch = "Sketch1"

    result = await getattr(CircuitBreakerAdapter(adapter=inner), name)(*args, **kwargs)

    assert result.is_success, result.error
