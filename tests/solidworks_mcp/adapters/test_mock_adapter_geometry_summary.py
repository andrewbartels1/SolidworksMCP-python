"""Tests for MockSolidWorksAdapter.get_model_geometry_summary."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


@pytest.mark.asyncio
async def test_part_reports_geometry_as_not_determinable(
    mock_adapter: MockSolidWorksAdapter,
) -> None:
    await mock_adapter.open_model("C:\\mock\\Bracket.sldprt")

    result = await mock_adapter.get_model_geometry_summary()

    assert result.is_success
    assert result.data == {
        "document_type": "part",
        "volume_mm3": None,
        "bounding_box_mm": None,
        "bounding_box_method": None,
        "solid_body_count": None,
    }


@pytest.mark.asyncio
async def test_assembly_counts_inserted_components_and_added_mates(
    mock_adapter: MockSolidWorksAdapter,
) -> None:
    await mock_adapter.open_model("C:\\mock\\Assem1.sldasm")
    await mock_adapter.insert_component("C:\\mock\\Base.sldprt")
    await mock_adapter.insert_component("C:\\mock\\Pin.sldprt")
    await mock_adapter.add_mate("component-1", "component-2", mate_type="concentric")

    result = await mock_adapter.get_model_geometry_summary()

    assert result.is_success
    assert result.data["document_type"] == "assembly"
    assert result.data["component_count"] == 2
    assert result.data["mate_count"] == 1
    assert result.data["volume_mm3"] is None


@pytest.mark.asyncio
async def test_rejected_mate_is_not_counted(
    mock_adapter: MockSolidWorksAdapter,
) -> None:
    await mock_adapter.open_model("C:\\mock\\Assem1.sldasm")
    rejected = await mock_adapter.add_mate("a", "b", mate_type="glue")
    assert not rejected.is_success

    result = await mock_adapter.get_model_geometry_summary()

    assert result.data["mate_count"] == 0


@pytest.mark.asyncio
async def test_no_active_model_is_an_error(
    mock_adapter: MockSolidWorksAdapter,
) -> None:
    result = await mock_adapter.get_model_geometry_summary()

    assert not result.is_success
    assert "get_model_geometry_summary" in (result.error or "")


@pytest.mark.asyncio
async def test_drawing_is_an_error(mock_adapter: MockSolidWorksAdapter) -> None:
    await mock_adapter.open_model("C:\\mock\\Sheet.slddrw")

    result = await mock_adapter.get_model_geometry_summary()

    assert not result.is_success
    assert "assembly or part" in (result.error or "")
