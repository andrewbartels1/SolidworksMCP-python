"""The mock adapter's drawing-package methods mirror the live contract."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


@pytest.fixture
async def drawing(tmp_path) -> MockSolidWorksAdapter:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    model = tmp_path / "bracket.SLDASM"
    model.write_bytes(b"")
    assert (await adapter.create_drawing()).is_success
    assert (
        await adapter.create_technical_drawing({"model_path": str(model)})
    ).is_success
    return adapter


@pytest.mark.asyncio
async def test_bom_reports_the_live_fields(drawing) -> None:
    result = await drawing.insert_bom_table(drawing._drawing_views[0])

    assert set(result.data) == {
        "view",
        "bom_type",
        "template",
        "configuration",
        "row_count",
    }
    assert result.data["template"] == "bom-standard.sldbomtbt"


@pytest.mark.asyncio
async def test_bom_refuses_unknown_types_and_views(drawing) -> None:
    views = ", ".join(drawing._drawing_views)
    wrong_type = await drawing.insert_bom_table(drawing._drawing_views[0], None, "flat")
    unknown = await drawing.insert_bom_table("Side")

    assert "bom_type must be one of" in (wrong_type.error or "")
    assert unknown.error == f"No view named 'Side'. Views: {views}"


@pytest.mark.asyncio
async def test_sheet_scale_reads_back_and_refuses_zero(drawing) -> None:
    half = await drawing.set_sheet_scale(1, 2)
    zero = await drawing.set_sheet_scale(0, 2)

    assert half.data == {"sheet": "Sheet1", "scale": "1:2"}
    assert zero.error == "Scale values must be positive, not 0:2"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["insert_bom_table", "set_sheet_scale"])
async def test_both_need_a_drawing(method) -> None:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()

    args = ("Drawing View1",) if method == "insert_bom_table" else (1, 2)
    result = await getattr(adapter, method)(*args)

    assert "needs an active drawing document" in (result.error or "")


@pytest.mark.asyncio
async def test_standard_drawing_names_its_files(tmp_path) -> None:
    adapter = MockSolidWorksAdapter({})
    model = tmp_path / "Mounting Plate.SLDPRT"
    model.write_bytes(b"")

    result = await adapter.create_standard_drawing(
        str(model), include_isometric=False, write_model_properties=False
    )

    assert result.data["drawing_number"] == "MOUNTING-PLATE-RevA-01"
    assert result.data["drawing_path"].endswith("MOUNTING-PLATE-RevA-01.SLDDRW")
    assert "Drawing View4" not in result.data["views"]
    assert result.data["properties_written"]["model"] == {}


@pytest.mark.asyncio
async def test_standard_drawing_needs_the_model(tmp_path) -> None:
    result = await MockSolidWorksAdapter({}).create_standard_drawing(
        str(tmp_path / "missing.SLDPRT")
    )

    assert result.error == f"Model file not found: {tmp_path / 'missing.SLDPRT'}"
