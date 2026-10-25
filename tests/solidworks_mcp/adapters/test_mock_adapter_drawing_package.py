"""The mock adapter's drawing-package methods mirror the live contract."""

from __future__ import annotations

import os

import pytest

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


@pytest.fixture
async def drawing(tmp_path) -> MockSolidWorksAdapter:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    model = tmp_path / "assembly.SLDASM"
    model.write_bytes(b"")
    assert (await adapter.create_drawing()).is_success
    assert (
        await adapter.create_technical_drawing({"model_path": str(model)})
    ).is_success
    return adapter


@pytest.mark.asyncio
async def test_bom_on_a_known_view(drawing) -> None:
    view = drawing._drawing_views[0]
    result = await drawing.insert_bom_table(view, None, "parts_only")

    assert result.data == {
        "view": view,
        "bom_type": "parts_only",
        "template": None,
        "row_count": 2,
        "table_box_mm": [0.0, 0.0, 60.0, 15.0],
    }


@pytest.mark.asyncio
async def test_bom_errors(drawing) -> None:
    views = ", ".join(drawing._drawing_views)
    unknown = await drawing.insert_bom_table("Side")
    bad_type = await drawing.insert_bom_table(drawing._drawing_views[0], None, "flat")

    assert unknown.error == f"No view named 'Side'. Views: {views}"
    assert bad_type.error.startswith("bom_type must be")


@pytest.mark.asyncio
async def test_bom_and_scale_need_a_drawing() -> None:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    assert not (await adapter.insert_bom_table("Drawing View1")).is_success
    assert not (await adapter.set_sheet_scale(1, 2)).is_success


@pytest.mark.asyncio
async def test_sheet_scale(drawing) -> None:
    ok = await drawing.set_sheet_scale(1, 2)
    bad = await drawing.set_sheet_scale(0, 2)

    assert ok.data == {"sheet": "Sheet1", "scale": "1:2", "requested": "1:2"}
    assert bad.error == "Scale values must be positive"


@pytest.mark.asyncio
async def test_standard_drawing(tmp_path) -> None:
    adapter = MockSolidWorksAdapter({})
    model = tmp_path / "Mounting Plate.SLDPRT"
    model.write_bytes(b"")

    full = await adapter.create_standard_drawing(
        str(model), title="Plate", author="saiq", notes=["deburr"]
    )
    bare = await adapter.create_standard_drawing(
        str(model),
        output_dir=str(tmp_path / "out"),
        drawing_number="MP-01",
        include_isometric=False,
        write_model_properties=False,
    )

    assert full.data["drawing_number"] == "MOUNTING-PLATE-RevA-01"
    assert full.data["drawing_path"] == os.path.join(
        str(tmp_path), "MOUNTING-PLATE-RevA-01.SLDDRW"
    )
    assert full.data["views"]["Drawing View4"]["role"] == "iso"
    assert full.data["properties_written"]["model"] == {"Description": "Plate"}
    assert full.data["notes"] == ["NOTES", "DEBURR"]
    assert bare.data["isometric_scale"] is None
    assert "Drawing View4" not in bare.data["views"]
    assert bare.data["properties_written"]["model"] == {}
    assert bare.data["pdf_path"] == os.path.join(str(tmp_path / "out"), "MP-01.pdf")


@pytest.mark.asyncio
async def test_standard_drawing_missing_model(tmp_path) -> None:
    missing = str(tmp_path / "nope.SLDPRT")
    result = await MockSolidWorksAdapter({}).create_standard_drawing(missing)

    assert result.error == f"Model file not found: {missing}"
