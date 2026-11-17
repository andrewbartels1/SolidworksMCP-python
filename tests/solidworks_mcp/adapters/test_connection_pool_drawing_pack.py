"""The drawing-pack methods pass through the connection pool unchanged."""

from __future__ import annotations

from typing import Any

import pytest

from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter

from .drawing_pack_calls import CALLS, IDS, recorder


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "args", "kwargs"), CALLS, ids=IDS)
async def test_each_drawing_pack_method_passes_through(
    name: str, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    pool = ConnectionPoolAdapter(adapter_factory=recorder, max_size=1)
    await pool.connect()
    try:
        result = await getattr(pool, name)(*args, **kwargs)
    finally:
        await pool.disconnect()

    received = result.data[name][0]
    assert received[: len(args)] == args
    assert all(value in received for value in kwargs.values())
