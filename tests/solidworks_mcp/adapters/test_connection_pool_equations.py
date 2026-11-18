"""The equation methods pass through the connection pool."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


@pytest.mark.asyncio
async def test_set_list_and_delete_pass_through() -> None:
    pool = ConnectionPoolAdapter(
        adapter_factory=lambda: MockSolidWorksAdapter({}), max_size=1
    )
    await pool.connect()
    try:
        assert (await pool.create_part()).is_success
        added = await pool.set_equation("Width", "60mm")
        listed = await pool.list_equations()
        deleted = await pool.delete_equation("Width")
    finally:
        await pool.disconnect()

    assert added.data["action"] == "added"
    assert [row["name"] for row in listed.data] == ["Width"]
    assert deleted.data["equations"] == []
