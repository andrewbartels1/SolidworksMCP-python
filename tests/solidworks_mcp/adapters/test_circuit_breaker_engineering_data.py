"""The engineering-data methods pass through CircuitBreakerAdapter."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter, CircuitState

from .engineering_data_stub import EngineeringDataStub, exercise_engineering_data


@pytest.mark.asyncio
async def test_every_engineering_data_method_is_forwarded() -> None:
    stub = EngineeringDataStub()
    await exercise_engineering_data(CircuitBreakerAdapter(adapter=stub))
    assert stub.calls == EngineeringDataStub.EXPECTED_CALLS


class _MissingFeature(EngineeringDataStub):
    async def list_model_dimensions(self, feature_name=None):
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error=f"No dimensions found on feature {feature_name!r}",
        )


@pytest.mark.asyncio
async def test_expected_lookup_errors_do_not_trip_the_breaker() -> None:
    breaker = CircuitBreakerAdapter(adapter=_MissingFeature(), failure_threshold=2)

    for _ in range(3):
        result = await breaker.list_model_dimensions("Fillet9")
        assert "No dimensions found" in result.error

    assert breaker._get_bucket("list_model_dimensions").state == CircuitState.CLOSED
