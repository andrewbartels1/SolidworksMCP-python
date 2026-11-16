"""The mock adapter's configurations mirror the real adapter's refusals."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


@pytest.mark.asyncio
async def test_create_activate_list_and_delete() -> None:
    mock = MockSolidWorksAdapter({})
    await mock.connect()
    await mock.create_part()

    made = await mock.create_configuration("Long", parent="Default")
    shown = await mock.activate_configuration("Long")
    listed = await mock.list_configurations()
    active = await mock.active_configuration()
    refused = await mock.delete_configuration("Long")
    await mock.activate_configuration("Default")
    deleted = await mock.delete_configuration("Long")
    only = await mock.delete_configuration("Default")

    assert made.data["configurations"] == ["Default", "Long"]
    assert made.data["active"] == "Default"
    assert shown.data == {"active": "Long", "previous": "Default"}
    assert listed.data == ["Default", "Long"]
    assert active.data == "Long"
    assert (
        refused.error == "'Long' is the active configuration; activate another first."
    )
    assert deleted.data == {"deleted": "Long", "configurations": ["Default"]}
    assert only.error == "'Default' is the model's only configuration."


@pytest.mark.asyncio
async def test_refusals() -> None:
    mock = MockSolidWorksAdapter({})
    no_model = [
        await mock.create_configuration("Long"),
        await mock.activate_configuration("Long"),
        await mock.active_configuration(),
    ]
    await mock.connect()
    await mock.create_part()

    duplicate = await mock.create_configuration("Default")
    orphan = await mock.create_configuration("Long", parent="Ghost")
    activated = await mock.create_configuration("Short", activate=True)
    unknown = await mock.activate_configuration("Ghost")
    gone = await mock.delete_configuration("Ghost")

    assert [r.error for r in no_model] == ["No active model"] * 3
    assert duplicate.error == "A configuration named 'Default' already exists."
    assert orphan.error.startswith("No configuration named 'Ghost' to derive from")
    assert activated.data["active"] == "Short"
    assert unknown.error == (
        "No configuration named 'Ghost'; the model has Default, Short."
    )
    assert gone.error == unknown.error
