"""The base adapter's drawing-package defaults report a missing capability."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.base import SolidWorksAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("insert_bom_table", ("Drawing View1",)),
        ("set_sheet_scale", (1, 2)),
        ("create_standard_drawing", ("C:/parts/block.SLDPRT",)),
    ],
)
async def test_base_default_says_the_adapter_lacks_it(method, args) -> None:
    # Call the base implementation directly: every concrete adapter overrides it.
    result = await getattr(SolidWorksAdapter, method)(MockSolidWorksAdapter({}), *args)

    assert not result.is_success
    assert result.error == f"{method} is not implemented by this adapter"
