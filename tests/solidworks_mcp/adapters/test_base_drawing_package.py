"""The base adapter's drawing-package defaults report a missing capability."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.base import SolidWorksAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter

CALLS = {
    "insert_bom_table": ("Drawing View1",),
    "set_sheet_scale": (1.0, 2.0),
    "create_standard_drawing": ("C:/parts/block.SLDPRT",),
    "add_gtol": ("position", 0.2, 60.0, 250.0),
    "add_datum_tag": ("A", (10.0, 20.0), 15.0, 25.0),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("method", list(CALLS))
async def test_base_default_says_the_adapter_lacks_it(method) -> None:
    # Call the base implementation directly: every concrete adapter overrides it.
    result = await getattr(SolidWorksAdapter, method)(
        MockSolidWorksAdapter({}), *CALLS[method]
    )

    assert not result.is_success
    assert result.error == f"{method} is not implemented by this adapter"
