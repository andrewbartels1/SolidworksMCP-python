"""Tests for base adapter defaults."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.base import AdapterResultStatus, SolidWorksAdapter


class _Adapter(SolidWorksAdapter):
    """Minimal concrete adapter for testing defaults."""

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None


def test_base_config_normalizes_unknown_object() -> None:
    """Non-mapping config objects should normalize to empty dict."""
    # Pass a plain object without model_dump to hit the fallback branch.
    adapter = _Adapter(object())
    assert adapter.config_dict == {}


@pytest.mark.asyncio
async def test_base_default_sketch_helpers_return_error() -> None:
    """Default sketch helper methods should return not-implemented errors."""
    # Exercise default error responses for unimplemented sketch helpers.
    adapter = _Adapter({})

    result = await adapter.add_polygon(0.0, 0.0, 1.0, 5)
    assert result.status == AdapterResultStatus.ERROR

    result = await adapter.add_ellipse(0.0, 0.0, 2.0, 1.0)
    assert result.status == AdapterResultStatus.ERROR

    result = await adapter.add_sketch_constraint("e1", None, "coincident")
    assert result.status == AdapterResultStatus.ERROR

    result = await adapter.sketch_linear_pattern(["e1"], 1.0, 2)
    assert result.status == AdapterResultStatus.ERROR

    result = await adapter.sketch_circular_pattern(["e1"], 90.0, 4)
    assert result.status == AdapterResultStatus.ERROR

    result = await adapter.sketch_mirror(["e1"], "line1")
    assert result.status == AdapterResultStatus.ERROR

    result = await adapter.sketch_offset(["e1"], 1.0, False)
    assert result.status == AdapterResultStatus.ERROR
