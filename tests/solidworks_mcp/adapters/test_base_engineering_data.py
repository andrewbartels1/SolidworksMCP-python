"""The base adapter's engineering-data defaults report a missing capability."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter

_CALLS = {
    "list_model_dimensions": (),
    "measure_entities": (["Edge<1>"],),
    "get_material": (),
    "set_material": ("AISI 1020",),
    "list_available_materials": (),
    "get_custom_properties": (),
    "set_custom_property": ("PartNo", "P-1"),
    "export_flat_pattern": ("flat.dxf",),
}


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "args"), _CALLS.items())
async def test_base_default_says_the_adapter_lacks_it(method, args) -> None:
    from solidworks_mcp.adapters.base import SolidWorksAdapter

    # Call the base implementation directly: every concrete adapter overrides it.
    result = await getattr(SolidWorksAdapter, method)(MockSolidWorksAdapter({}), *args)

    assert not result.is_success
    assert result.error == f"{method} is not implemented by this adapter"
