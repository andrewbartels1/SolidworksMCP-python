"""The configuration methods pass through the connection pool."""

from __future__ import annotations

from typing import Any

import pytest

from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter

from .configuration_calls import CALLS, IDS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "args", "kwargs"),
    [*CALLS, ("delete_configuration", ("Default",), {})],
    ids=[*IDS, "delete"],
)
async def test_each_configuration_method_passes_through(
    name: str, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    pool = ConnectionPoolAdapter(
        adapter_factory=lambda: MockSolidWorksAdapter({}), max_size=1
    )
    await pool.connect()
    try:
        assert (await pool.create_part()).is_success
        result = await getattr(pool, name)(*args, **kwargs)
    finally:
        await pool.disconnect()

    # Deleting the only configuration is refused, which still proves the
    # call reached the adapter.
    assert result.is_success or "only configuration" in (result.error or "")
