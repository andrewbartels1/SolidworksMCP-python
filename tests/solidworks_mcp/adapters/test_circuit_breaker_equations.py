"""The equation methods pass through the circuit breaker."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


@pytest.mark.asyncio
async def test_set_list_and_delete_pass_through() -> None:
    inner = MockSolidWorksAdapter({})
    await inner.connect()
    await inner.create_part()
    breaker = CircuitBreakerAdapter(adapter=inner)

    added = await breaker.set_equation("Width", "60mm", "this")
    listed = await breaker.list_equations()
    deleted = await breaker.delete_equation("Width")

    assert added.data["value"] == 60.0
    assert [row["name"] for row in listed.data] == ["Width"]
    assert deleted.data == {"deleted": "Width", "equations": []}
