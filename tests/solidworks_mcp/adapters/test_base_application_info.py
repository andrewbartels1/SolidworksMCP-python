"""The base adapter's application-info default reports a missing capability."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.base import SolidWorksAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


@pytest.mark.asyncio
async def test_base_default_says_the_adapter_lacks_it() -> None:
    # Call the base implementation directly: every concrete adapter overrides it.
    result = await SolidWorksAdapter.get_application_info(MockSolidWorksAdapter({}))

    assert not result.is_success
    assert result.error == "get_application_info is not implemented by this adapter"
