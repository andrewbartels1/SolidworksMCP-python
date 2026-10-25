"""Real-SolidWorks checks for the drawing-package tools (slice C of PR #117).

Each test calls the registered MCP tool and checks what SolidWorks reports
afterwards: the sheet's scale and the views' real size for ``set_sheet_scale``,
the BOM table's own cells for ``insert_bom_table``, and the files, title-block
properties and read-back overlap check for ``generate_drawing_package``.
Every test also proves one failure case. In a demo, the generator's test also
holds SolidWorks on each build step (sheet, views, layout, dimensions, notes,
check, title block), so the drawing can be seen filling in.

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows (see
``tests/live/conftest.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.live.evidence import evidence
from tests.live.test_live_sw_documentation_tools import _block


async def _drawing_tools(adapter: Any) -> dict[str, Any]:
    """Register the drawing-automation tools against ``adapter``; name -> fn."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools.drawing_automation import (
        register_drawing_automation_tools,
    )

    mcp = FastMCP("drawing-package-live")
    await register_drawing_automation_tools(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


async def _saved_block(scratch, path: Path, depth_mm: float = 15.0) -> str:  # noqa: ANN001
    """Build the 30x30 mm block and save it to ``path``."""
    await _block(scratch.adapter, depth_mm)
    saved = await scratch.adapter.save_file(str(path))
    assert saved.is_success, saved.error
    scratch.written_files.append(str(path))
    return str(path)


#: What each of the generator's COM steps adds to the sheet.
_BUILD_STEPS = {
    "standard_drawing_sheet": "build 1/7: the A3 ISO sheet format",
    "standard_drawing_views": "build 2/7: third-angle views and an isometric",
    "standard_drawing_layout": "build 3/7: scale chosen, views centred in cells",
    "standard_drawing_dimensions": "build 4/7: model dimensions, laid out",
    "standard_drawing_notes": "build 5/7: view captions and the NOTES block",
    "standard_drawing_check": "build 6/7: overlap check on the real geometry",
    "standard_drawing_title_block": "build 7/7: title block filled and fitted",
}


def _show_each_build_step(adapter: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hold SolidWorks on the drawing after each of the generator's COM steps.

    Wraps the adapter's ``_handle_com_operation``: each build step runs as
    before, then its result is shown as evidence (a pause, and a frame when
    capturing). Nothing about the call itself changes.
    """
    original = adapter._handle_com_operation

    def watched(name: str, operation: Any, *args: Any) -> Any:
        result = original(name, operation, *args)
        if name in _BUILD_STEPS:
            evidence(
                _BUILD_STEPS[name],
                result.data if result.is_success else {"error": result.error},
            )
        return result

    monkeypatch.setattr(adapter, "_handle_com_operation", watched)


def _view_widths(adapter: Any) -> dict[str, float]:
    """Each view's outline width on the sheet, in mm."""
    from solidworks_mcp.adapters.solidworks.io import (
        _resolve_drawing_view,
        _sw_type_info,
        _view_names,
    )

    drawing = _sw_type_info.flagged(adapter.currentModel, "IDrawingDoc")
    widths = {}
    for name in _view_names(adapter, drawing):
        outline = _resolve_drawing_view(adapter, drawing, name).GetOutline()
        widths[name] = round((outline[2] - outline[0]) * 1000.0, 2)
    return widths


@pytest.mark.asyncio
async def test_set_sheet_scale_halves_the_views(scratch, tmp_path):
    """1:2 on a 1:1 sheet halves every view, and the sheet reads back 1:2."""
    adapter = scratch.adapter
    part = await _saved_block(scratch, tmp_path / "scale_block.SLDPRT")
    assert (await adapter.create_drawing()).is_success
    views = await adapter.create_technical_drawing({"model_path": part})
    assert views.is_success, views.error
    tools = await _drawing_tools(adapter)

    assert (await tools["set_sheet_scale"]({"numerator": 1, "denominator": 1}))[
        "status"
    ] == "success"
    before = _view_widths(adapter)
    result = await tools["set_sheet_scale"]({"numerator": 1, "denominator": 2})
    after = _view_widths(adapter)
    evidence(
        "sheet scale 1:1 -> 1:2: view widths (mm) halve",
        {"result": result.get("data"), "before": before, "after": after},
        call='set_sheet_scale({"numerator": 1, "denominator": 2})',
    )
    assert result["status"] == "success", result
    assert result["data"]["scale"] == "1:2"
    # A view's outline carries a fixed margin, so compare the part inside it:
    # the 30 mm block shrinks from 30 to 15 mm on the sheet.
    for name, width in before.items():
        assert width - after[name] == pytest.approx(15.0, abs=0.2), name

    zero = await tools["set_sheet_scale"]({"numerator": 0, "denominator": 2})
    evidence("a zero scale is invalid_input", zero)
    assert zero["error_type"] == "invalid_input"


@pytest.mark.asyncio
async def test_set_sheet_scale_needs_a_drawing(scratch):
    """On a part the tool refuses with wrong_document_type."""
    await _block(scratch.adapter)
    tools = await _drawing_tools(scratch.adapter)

    result = await tools["set_sheet_scale"]({"numerator": 1, "denominator": 2})
    evidence("set_sheet_scale on a part", result)
    assert result["error_type"] == "wrong_document_type"


def _bom_cells(adapter: Any) -> list[list[str]]:
    """Every cell of the first BOM table on the active drawing."""
    from solidworks_mcp.adapters.solidworks.io import _sw_type_info

    model = _sw_type_info.flagged(adapter.currentModel, "IModelDoc2")
    feature = model.FirstFeature()
    while feature is not None:
        feature = _sw_type_info.flagged(feature, "IFeature")
        if feature.GetTypeName2() == "BomFeat":
            bom = _sw_type_info.flagged(feature.GetSpecificFeature2(), "IBomFeature")
            table = _sw_type_info.flagged(
                bom.GetTableAnnotations()[0], "ITableAnnotation"
            )
            return [
                [str(table.Text(r, c)) for c in range(table.ColumnCount)]
                for r in range(table.RowCount)
            ]
        feature = feature.GetNextFeature()
    return []


def _sheet_texts(adapter: Any) -> list[str]:
    """The text of every note on the sheet itself (title block included), as shown."""
    from solidworks_mcp.adapters.solidworks.io import _sw_type_info

    drawing = _sw_type_info.flagged(adapter.currentModel, "IDrawingDoc")
    sheet_view = _sw_type_info.flagged(drawing.GetFirstView(), "IView")
    texts = []
    note = sheet_view.GetFirstNote()
    while note is not None:
        note = _sw_type_info.flagged(note, "INote")
        texts.append(str(note.GetText()))
        note = note.GetNext()
    return texts


@pytest.mark.asyncio
async def test_insert_bom_table_lists_both_parts(scratch, tmp_path):
    """A BOM on a two-part assembly drawing lists both parts."""
    adapter = scratch.adapter
    plate = await _saved_block(scratch, tmp_path / "bom_plate.SLDPRT", 5.0)
    block = await _saved_block(scratch, tmp_path / "bom_block.SLDPRT", 20.0)
    assert (await adapter.create_assembly()).is_success
    assert (await adapter.insert_component(plate, 0.0, 0.0, 0.0)).is_success
    assert (await adapter.insert_component(block, 0.0, 0.0, 0.05)).is_success
    assembly = str(tmp_path / "bom_assembly.SLDASM")
    assert (await adapter.save_file(assembly)).is_success
    scratch.written_files.append(assembly)
    assert (await adapter.create_drawing()).is_success
    views = await adapter.create_technical_drawing({"model_path": assembly})
    assert views.is_success, views.error
    tools = await _drawing_tools(adapter)
    view = next(iter(_view_widths(adapter)))

    result = await tools["insert_bom_table"]({"view_name": view})
    cells = _bom_cells(adapter)
    evidence(
        "BOM of the two-part assembly",
        {"result": result.get("data"), "cells": cells},
        call=f'insert_bom_table({{"view_name": "{view}"}})',
    )
    assert result["status"] == "success", result
    box = result["data"]["table_box_mm"]  # on the 420 x 297 mm sheet
    assert box and box[0] >= 0 and box[1] >= 0, box
    text = " ".join(" ".join(row) for row in cells)
    assert "bom_plate" in text and "bom_block" in text

    missing = await tools["insert_bom_table"]({"view_name": "Side"})
    evidence("an unknown view is not_found and lists the views", missing)
    assert missing["error_type"] == "not_found"
    assert view in missing["message"]


@pytest.mark.asyncio
async def test_insert_bom_table_on_a_part_view(scratch, tmp_path):
    """A view of a part says a BOM needs an assembly; a part is the wrong document."""
    adapter = scratch.adapter
    part = await _saved_block(scratch, tmp_path / "bom_part.SLDPRT")
    tools = await _drawing_tools(adapter)
    wrong_doc = await tools["insert_bom_table"]({"view_name": "Drawing View1"})
    evidence("insert_bom_table on a part document", wrong_doc)
    assert wrong_doc["error_type"] == "wrong_document_type"

    assert (await adapter.create_drawing()).is_success
    assert (await adapter.create_technical_drawing({"model_path": part})).is_success
    view = next(iter(_view_widths(adapter)))
    result = await tools["insert_bom_table"]({"view_name": view})
    evidence("insert_bom_table on a view of a part", result)
    assert result["status"] == "error"
    assert "A BOM needs a view of an assembly" in result["message"]


@pytest.mark.asyncio
async def test_generate_drawing_package_on_a_block(scratch, tmp_path, monkeypatch):
    """30x30x15 mm block: drawing and PDF written, material and mass shown, no overlaps."""
    adapter = scratch.adapter
    await _block(adapter)
    assert (await adapter.set_material("AISI 1020")).is_success
    part = str(tmp_path / "Package Block.SLDPRT")
    assert (await adapter.save_file(part)).is_success
    scratch.written_files.append(part)
    out = tmp_path / "drawings"
    tools = await _drawing_tools(adapter)
    _show_each_build_step(adapter, monkeypatch)

    result = await tools["generate_drawing_package"](
        {
            "model_path": part,
            "output_dir": str(out),
            "title": "Package Block",
            "drawing_number": "PB-01",
            "author": "Live test",
        }
    )
    data = result.get("data") or {}
    drawing, pdf = out / "PB-01.SLDDRW", out / "PB-01.pdf"
    scratch.written_files += [str(drawing), str(pdf)]

    # What the title block shows: the sheet's notes as SolidWorks displays them.
    shown = _sheet_texts(adapter)
    title_block = [t for t in shown if len(t.strip()) > 1]  # not the zone letters
    evidence(
        "A3 drawing of the block: files, title block and overlap check",
        {
            "message": result.get("message"),
            "scale": data.get("scale"),
            "views": data.get("views"),
            "overlaps_after": (data.get("overlap_check") or {}).get("overlaps_after"),
            "files": [drawing.exists(), pdf.exists()],
            "title_block": title_block,
            "title_block_fit": data.get("title_block"),
        },
        call='generate_drawing_package({"model_path": "Package Block.SLDPRT", ...})',
    )
    assert result["status"] == "success", result
    assert drawing.exists() and pdf.stat().st_size > 0
    assert data["overlap_check"]["overlaps_after"] == 0
    assert data["title_block"]["drawing number"]["fits"] is True
    assert "AISI 1020" in shown
    assert "Package Block" in shown
    # 13.5 cm^3 of AISI 1020 (7.87 g/cm^3) is about 106 g; the format shows grams.
    weight = next(t for t in shown if t.startswith("WEIGHT:"))
    assert 100 < float(weight.split(":")[1]) < 112, weight

    missing = await tools["generate_drawing_package"](
        {"model_path": str(tmp_path / "no_such_part.SLDPRT")}
    )
    evidence("a missing model is not_found", missing)
    assert missing["error_type"] == "not_found"

    not_a_model = await tools["generate_drawing_package"]({"model_path": str(drawing)})
    evidence("a drawing as the model is invalid_input", not_a_model)
    assert not_a_model["error_type"] == "invalid_input"
