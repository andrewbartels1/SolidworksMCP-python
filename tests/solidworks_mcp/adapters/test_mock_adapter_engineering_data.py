"""The mock adapter's engineering-data methods mirror the live contract."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


@pytest.fixture
async def part() -> MockSolidWorksAdapter:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    assert (await adapter.create_part()).is_success
    return adapter


@pytest.mark.asyncio
async def test_list_model_dimensions_filters_by_feature(part) -> None:
    part._dimensions = {"D1@Sketch1": 40.0, "D1@Boss-Extrude1": 10.0}

    result = await part.list_model_dimensions("boss-extrude1")

    assert [d["full_name"] for d in result.data] == ["D1@Boss-Extrude1"]


@pytest.mark.asyncio
async def test_list_model_dimensions_unknown_feature(part) -> None:
    result = await part.list_model_dimensions("Fillet9")
    assert result.error == "No dimensions found on feature 'Fillet9'"


@pytest.mark.asyncio
async def test_measure_entities_one_face_gives_area(part) -> None:
    result = await part.measure_entities(["face:0,0.01,0"])
    assert result.data == {
        "selected": ["face:0,0.01,0"],
        "area_m2": 0.0025,
        "perimeter_m": 0.2,
    }


@pytest.mark.asyncio
async def test_measure_entities_two_specs_give_distance(part) -> None:
    result = await part.measure_entities(["Edge<1>", "Edge<2>"])
    assert result.data["distance_m"] == 0.05
    assert result.data["is_parallel"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("entities", [[], ["a", "b", "c"]])
async def test_measure_entities_takes_one_or_two_specs(part, entities) -> None:
    result = await part.measure_entities(entities)
    assert result.error == "measure_entities takes one or two entity specs"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("measure_entities", (["Edge<1>"],)),
        ("get_material", ()),
        ("export_flat_pattern", ("flat.dxf",)),
    ],
)
async def test_part_tools_need_an_active_document(method, args) -> None:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await getattr(adapter, method)(*args)

    assert not result.is_success
    assert "needs an active" in result.error


@pytest.mark.asyncio
async def test_set_custom_property_needs_a_document_and_a_name(part) -> None:
    empty = MockSolidWorksAdapter({})
    await empty.connect()

    assert (await empty.set_custom_property("A", "b")).error == "No active model"
    assert (await part.set_custom_property(" ", "b")).error == "name is required"


@pytest.mark.asyncio
async def test_export_flat_pattern_validates_the_extension(part) -> None:
    bad = await part.export_flat_pattern("flat.pdf")
    good = await part.export_flat_pattern("flat.dxf")

    assert bad.error == "file_path must end in .dxf or .dwg"
    assert good.data == {"file_path": "flat.dxf", "size_bytes": 0, "mock": True}


@pytest.mark.asyncio
async def test_set_material_unknown_name_is_not_found(part) -> None:
    result = await part.set_material("Unobtainium")
    assert result.error == (
        "Material 'Unobtainium' not found in 'SOLIDWORKS Materials'; use "
        "list_available_materials for the exact name and library."
    )


@pytest.mark.asyncio
async def test_list_available_materials_reports_what_it_searched(part) -> None:
    result = await part.list_available_materials("abs")
    assert [m["name"] for m in result.data] == ["ABS"]
    assert result.metadata == {"folders": ["mock://sldmaterials"], "total": 4}
