"""The base adapter's drawing-dimension defaults report a missing capability."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.base import SolidWorksAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["insert_model_dimensions", "arrange_dimensions"])
async def test_base_default_says_the_adapter_lacks_it(method) -> None:
    # Call the base implementation directly: every concrete adapter overrides it.
    result = await getattr(SolidWorksAdapter, method)(MockSolidWorksAdapter({}))

    assert not result.is_success
    assert result.error == f"{method} is not implemented by this adapter"
