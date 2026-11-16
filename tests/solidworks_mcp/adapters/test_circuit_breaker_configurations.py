"""The configuration methods pass through the circuit breaker."""

from __future__ import annotations

from typing import Any

import pytest

from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter

from .configuration_calls import CALLS, IDS


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "args", "kwargs"), CALLS, ids=IDS)
async def test_each_configuration_method_passes_through(
    name: str, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    inner = MockSolidWorksAdapter({})
    await inner.connect()
    await inner.create_part()

    result = await getattr(CircuitBreakerAdapter(adapter=inner), name)(*args, **kwargs)

    assert result.is_success, result.error


@pytest.mark.asyncio
async def test_delete_passes_through() -> None:
    inner = MockSolidWorksAdapter({})
    await inner.connect()
    await inner.create_part()
    breaker = CircuitBreakerAdapter(adapter=inner)
    await breaker.create_configuration("Long")

    result = await breaker.delete_configuration("Long")

    assert result.data == {"deleted": "Long", "configurations": ["Default"]}
