"""get_model_geometry_summary passes through CircuitBreakerAdapter."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter


class _SummaryStub:
    def __init__(self) -> None:
        self.calls = 0

    async def get_model_geometry_summary(self) -> AdapterResult[dict]:
        self.calls += 1
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS, data={"document_type": "part"}
        )


def test_breaker_defines_its_own_passthrough() -> None:
    assert "get_model_geometry_summary" in vars(CircuitBreakerAdapter)


@pytest.mark.asyncio
async def test_summary_is_forwarded() -> None:
    stub = _SummaryStub()

    result = await CircuitBreakerAdapter(adapter=stub).get_model_geometry_summary()

    assert result.is_success
    assert result.data == {"document_type": "part"}
    assert stub.calls == 1
