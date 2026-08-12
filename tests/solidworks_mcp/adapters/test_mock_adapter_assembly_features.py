"""Tests for MockSolidWorksAdapter's assembly-aware ``list_features``.

Companion to ``test_list_features_assembly.py`` (which covers the real
pywin32 adapter with COM fakes) — exercises the same behavior against the
mock adapter's configurable ``_assembly_components`` fixture, per GitHub
issue #21 / OpenSpec change ``assembly-aware-list-features``.
"""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


@pytest.mark.asyncio
async def test_part_model_unaffected(mock_adapter: MockSolidWorksAdapter) -> None:
    """A Part model's seeded features are unchanged, tagged component=None."""
    await mock_adapter.open_model("C:\\mock\\Bracket.sldprt")

    result = await mock_adapter.list_features()

    assert result.is_success
    assert len(result.data) == 5  # the existing seeded fixture
    assert all(row["component"] is None for row in result.data)
    assert all(row["component_path"] is None for row in result.data)


@pytest.mark.asyncio
async def test_assembly_default_fixture_flattens_components(
    mock_adapter: MockSolidWorksAdapter,
) -> None:
    """An Assembly with no configured components uses the canned fixture."""
    await mock_adapter.open_model("C:\\mock\\Assem1.sldasm")

    result = await mock_adapter.list_features()

    assert result.is_success
    by_name = {row["name"]: row for row in result.data}
    # Own (assembly-level) seeded features are unattributed.
    assert by_name["Origin"]["component"] is None
    # Default fixture: two Part components plus one nested sub-assembly.
    assert by_name["Boss-Extrude1"]["component"] in {"PartA", "PartC"}
    assert by_name["Cut-Extrude1"]["component"] == "PartB"
    assert by_name["Mate1"]["component"] == "SubAssembly1"


@pytest.mark.asyncio
async def test_assembly_custom_components_and_suppression(
    mock_adapter: MockSolidWorksAdapter,
) -> None:
    """Custom _assembly_components are flattened, suppression applied per component."""
    await mock_adapter.open_model("C:\\mock\\Assem1.sldasm")
    mock_adapter._assembly_components = {
        "CompA": {
            "type": "Part",
            "path": "Mock://CompA.sldprt",
            "features": [
                {"name": "Boss1", "type": "Boss", "suppressed": False},
                {"name": "Hidden1", "type": "Fillet", "suppressed": True},
            ],
        },
        "CompB": {
            "type": "Part",
            "path": "Mock://CompB.sldprt",
            "features": [{"name": "Cut1", "type": "Cut", "suppressed": False}],
        },
    }

    hidden = await mock_adapter.list_features(include_suppressed=False)
    shown = await mock_adapter.list_features(include_suppressed=True)

    hidden_names = {row["name"] for row in hidden.data}
    shown_names = {row["name"] for row in shown.data}

    assert "Hidden1" not in hidden_names
    assert "Hidden1" in shown_names

    by_name = {row["name"]: row for row in shown.data}
    assert by_name["Boss1"]["component"] == "CompA"
    assert by_name["Boss1"]["component_path"] == "Mock://CompA.sldprt"
    assert by_name["Cut1"]["component"] == "CompB"


@pytest.mark.asyncio
async def test_assembly_depth_limit(mock_adapter: MockSolidWorksAdapter) -> None:
    """A sub-assembly beyond max_assembly_depth is a bare descriptor."""
    await mock_adapter.open_model("C:\\mock\\Assem1.sldasm")
    mock_adapter._assembly_components = {
        "SubA": {
            "type": "Assembly",
            "path": "Mock://SubA.sldasm",
            "features": [{"name": "Mate1", "type": "Mate", "suppressed": False}],
            "components": {
                "Nested": {
                    "type": "Part",
                    "path": "Mock://Nested.sldprt",
                    "features": [{"name": "Boss1", "type": "Boss", "suppressed": False}],
                },
            },
        },
    }

    result = await mock_adapter.list_features(max_assembly_depth=1)

    names = [row["name"] for row in result.data]
    assert "SubA" in names
    assert "Mate1" not in names
    assert "Boss1" not in names

    descriptor = next(row for row in result.data if row["name"] == "SubA")
    assert descriptor["type"] == "Component"
    assert descriptor["component"] == "SubA"


@pytest.mark.asyncio
async def test_assembly_unresolved_component(mock_adapter: MockSolidWorksAdapter) -> None:
    """An Unresolved-type component yields one UnresolvedComponent row."""
    await mock_adapter.open_model("C:\\mock\\Assem1.sldasm")
    mock_adapter._assembly_components = {
        "Missing": {"type": "Unresolved", "path": None, "features": []},
    }

    result = await mock_adapter.list_features()

    assert result.is_success
    assert len(result.data) >= 1
    row = next(r for r in result.data if r["name"] == "Missing")
    assert row["type"] == "UnresolvedComponent"
    assert row["component"] == "Missing"
