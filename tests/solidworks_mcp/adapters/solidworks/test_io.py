"""Tests for SolidWorks IO mixin behaviors."""

from __future__ import annotations

from types import SimpleNamespace

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.solidworks.io import SolidWorksIOMixin


class _IOHarness(SolidWorksIOMixin):
    """Minimal harness for IO mixin."""

    def __init__(self, current_model) -> None:
        self.currentModel = current_model

    def _attempt(self, callback, default=None):
        try:
            return callback()
        except Exception:
            return default

    def _handle_com_operation(self, _name, callback, *args):
        try:
            return AdapterResult(status=AdapterResultStatus.SUCCESS, data=callback())
        except Exception as exc:
            return AdapterResult(status=AdapterResultStatus.ERROR, error=str(exc))


import pytest


@pytest.mark.asyncio
async def test_get_mass_properties_uses_callable_gmp() -> None:
    """Callable GetMassProperties should be used when CreateMassProperty is missing."""
    # Provide a callable GetMassProperties to cover the callable branch.
    current_model = SimpleNamespace(
        ForceRebuild3=lambda _flag: None,
        Extension=SimpleNamespace(CreateMassProperty=lambda: None),
        GetMassProperties=lambda: [1.0, 2.0, 3.0, 0.1, 0.2, 0.3],
    )
    harness = _IOHarness(current_model)
    result = await harness.get_mass_properties()
    assert result.is_success
    assert result.data.mass == 0.3


@pytest.mark.asyncio
async def test_get_mass_properties_missing_gmp_fails() -> None:
    """Missing GetMassProperties should surface a failure."""
    # Use a non-callable/non-list attribute to hit raw=None.
    current_model = SimpleNamespace(
        ForceRebuild3=lambda _flag: None,
        Extension=SimpleNamespace(CreateMassProperty=lambda: None),
        GetMassProperties=123,
    )
    harness = _IOHarness(current_model)
    result = await harness.get_mass_properties()
    assert result.status == AdapterResultStatus.ERROR
    assert "Failed to get mass properties" in (result.error or "")
