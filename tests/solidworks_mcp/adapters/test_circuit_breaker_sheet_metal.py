"""The sheet-metal methods pass through the circuit breaker unchanged."""

from __future__ import annotations

from typing import Any

import pytest

from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter

from .sheet_metal_calls import CALLS, IDS, recorder


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "args", "kwargs"), CALLS, ids=IDS)
async def test_each_sheet_metal_method_passes_through(
    name: str, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    result = await getattr(CircuitBreakerAdapter(adapter=recorder()), name)(
        *args, **kwargs
    )

    received = result.data[name][0]
    assert received[: len(args)] == args
    assert all(value in received for value in kwargs.values())
