"""The part-feature methods pass through the connection pool."""

from __future__ import annotations

from typing import Any

import pytest

from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter

from .part_feature_calls import CALLS, IDS


def _adapter() -> MockSolidWorksAdapter:
    adapter = MockSolidWorksAdapter({})
    adapter._current_sketch = "Sketch1"
    return adapter


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "args", "kwargs"), CALLS, ids=IDS)
async def test_each_part_feature_passes_through(
    name: str, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    pool = ConnectionPoolAdapter(adapter_factory=_adapter, max_size=1)
    await pool.connect()
    try:
        result = await getattr(pool, name)(*args, **kwargs)
    finally:
        await pool.disconnect()

    assert result.is_success, result.error
