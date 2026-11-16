"""The mock adapter's configurations mirror the real adapter's refusals."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.base import ExtrusionParameters
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


@pytest.mark.asyncio
async def test_a_value_set_in_one_configuration_only() -> None:
    """Spec: 'A length in one configuration'. Default keeps its value."""
    mock = MockSolidWorksAdapter({})
    await mock.connect()
    await mock.create_part()
    await mock.set_dimension("D1@Boss-Extrude1", 50.0)
    await mock.create_configuration("Long")

    in_long = await mock.set_dimension("D1@Boss-Extrude1", 80.0, ["Long"])
    default_value = mock._dimensions["D1@Boss-Extrude1"]
    await mock.activate_configuration("Long")
    long_value = mock._dimensions["D1@Boss-Extrude1"]
    everywhere = await mock.set_dimension("D2@Boss-Extrude1", 5.0, "all")
    unknown = await mock.set_dimension("D1@Boss-Extrude1", 1.0, ["Short"])

    assert in_long.data == {"configurations": ["Long"]}
    assert (default_value, long_value) == (50.0, 80.0)
    assert everywhere.data == {"configurations": ["Default", "Long"]}
    assert (
        unknown.error == "No configuration named 'Short'; the model has Default, Long."
    )


@pytest.mark.asyncio
async def test_suppression_per_configuration() -> None:
    mock = MockSolidWorksAdapter({})
    await mock.connect()
    await mock.create_part()
    await mock.create_sketch("Front")
    await mock.add_rectangle(0.0, 0.0, 10.0, 10.0)
    await mock.exit_sketch()
    feature = (await mock.create_extrusion(ExtrusionParameters(depth=5.0))).data.name
    await mock.create_configuration("Long")

    elsewhere = await mock.suppress_feature(feature, True, ["Long"])
    await mock.activate_configuration("Long")
    in_long = feature in mock._suppressed_features
    await mock.activate_configuration("Default")
    in_default = feature in mock._suppressed_features
    everywhere = await mock.suppress_feature(feature, False, "all")
    unknown = await mock.suppress_feature(feature, True, ["Short"])

    assert elsewhere.data["configurations"] == ["Long"]
    assert elsewhere.data["suppressed"] is False  # read in the active one
    assert (in_long, in_default) == (True, False)
    assert everywhere.data["configurations"] == ["Default", "Long"]
    assert "No configuration named 'Short'" in (unknown.error or "")


@pytest.mark.asyncio
async def test_this_with_no_model_open_is_default() -> None:
    mock = MockSolidWorksAdapter({})
    await mock.connect()

    result = await mock.set_dimension("D1@Sketch1", 10.0)
    listed = mock._mock_scope("all")

    assert result.data == {"configurations": ["Default"]}
    assert listed == ["Default"]


@pytest.mark.asyncio
async def test_the_other_configurations_keep_a_value_the_model_had() -> None:
    mock = MockSolidWorksAdapter({})
    await mock.connect()
    await mock.create_part()
    await mock.create_configuration("Long")
    mock._dimensions["D9@Sketch1"] = 7.0  # the model's own value

    await mock.set_dimension("D9@Sketch1", 9.0, ["Long"])
    await mock.activate_configuration("Long")
    await mock.activate_configuration("Default")

    assert mock._dimensions["D9@Sketch1"] == 7.0
