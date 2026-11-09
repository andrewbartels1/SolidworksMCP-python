"""get_application_info passes through CircuitBreakerAdapter."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter


class _InfoStub:
    def __init__(self) -> None:
        self.calls = 0

    async def get_application_info(self) -> AdapterResult[dict]:
        self.calls += 1
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS, data={"revision": "34.4.0"}
        )


def test_breaker_defines_its_own_passthrough() -> None:
    assert "get_application_info" in vars(CircuitBreakerAdapter)


@pytest.mark.asyncio
async def test_info_is_forwarded() -> None:
    stub = _InfoStub()

    result = await CircuitBreakerAdapter(adapter=stub).get_application_info()

    assert result.is_success
    assert result.data == {"revision": "34.4.0"}
    assert stub.calls == 1
