"""Tests for the SolidWorksSelectionMixin."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.solidworks.selection import SolidWorksSelectionMixin


class _SelectionHarness(SolidWorksSelectionMixin):
    """Minimal harness to exercise the mixin methods."""

    def __init__(self, *, has_model: bool) -> None:
        self.currentModel = object() if has_model else None
        self._feature_selector = SimpleNamespace(
            list_features=lambda _include: [{"name": "Feat1"}],
            select_feature=lambda _name: {"selected": True},
        )

    def _handle_com_operation(self, _name, operation, *args):
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=operation(*args))


@pytest.mark.asyncio
async def test_list_features_requires_active_model() -> None:
    """list_features should error when no model is active."""
    # Validate the error branch when currentModel is missing.
    harness = _SelectionHarness(has_model=False)
    result = await harness.list_features()
    assert result.status == AdapterResultStatus.ERROR


@pytest.mark.asyncio
async def test_select_feature_requires_active_model() -> None:
    """select_feature should error when no model is active."""
    # Validate the error branch when currentModel is missing.
    harness = _SelectionHarness(has_model=False)
    result = await harness.select_feature("Feat1")
    assert result.status == AdapterResultStatus.ERROR


@pytest.mark.asyncio
async def test_list_and_select_feature_success() -> None:
    """list_features/select_feature should call the selector when model exists."""
    # Exercise the success path when currentModel is set.
    harness = _SelectionHarness(has_model=True)
    list_result = await harness.list_features()
    select_result = await harness.select_feature("Feat1")
    assert list_result.is_success
    assert list_result.data == [{"name": "Feat1"}]
    assert select_result.is_success
    assert select_result.data == {"selected": True}
