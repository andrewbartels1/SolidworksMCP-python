"""Drawing sheets (queue item 37), checked on real SolidWorks.

A saved 30 mm block and a drawing of it: a front view on Sheet1; on
purpose, a second sheet named "sheet1" is refused; a new A2 sheet "Details"
at 1:2 becomes active and takes an isometric view; back to Sheet1. Each
step lists the sheets: names, paper, scale, projection and which is active.

Run with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_drawing_sheets.py::test_a_drawing_on_two_sheets

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.live.evidence import evidence
from tests.live.test_live_sw_drawing_package_tools import _saved_block

pytestmark = pytest.mark.asyncio


async def _tools(adapter: Any) -> dict[str, Any]:
    """The drawing, file and sheet tools; name -> fn."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools.drawing import register_drawing_tools
    from solidworks_mcp.tools.drawing_sheets import register_drawing_sheet_tools
    from solidworks_mcp.tools.file_management import register_file_management_tools
    from solidworks_mcp.tools.modeling import register_modeling_tools

    mcp = FastMCP("sheets-live")
    for register in (
        register_modeling_tools,
        register_file_management_tools,
        register_drawing_tools,
        register_drawing_sheet_tools,
    ):
        await register(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


async def _ok(reply: dict[str, Any]) -> dict[str, Any]:
    assert reply["status"] == "success", reply
    return reply


async def test_a_drawing_on_two_sheets(scratch: Any, tmp_path: Path) -> None:
    """Sheet1 with a front view, a 1:2 A2 Details sheet with an isometric."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    part = await _saved_block(scratch, tmp_path / "sheets-block.SLDPRT")
    await _ok(await tools["create_drawing"]({"name": "two-sheets"}))
    await _ok(
        await tools["create_drawing_view"](
            {"model_path": part, "view_type": "front", "position_x": 150}
        )
    )
    first = await _ok(await tools["list_sheets"]())
    evidence("one sheet, a front view on it", first["sheets"], call="list_sheets()")
    assert first["count"] == 1

    # On purpose: a name in use, in another case.
    refused = await tools["add_sheet"]({"name": "sheet1"})
    evidence("a second 'sheet1' is refused", refused)
    assert refused["status"] == "error" and refused["error_type"] == "invalid_input"

    call = {"name": "Details", "sheet_format": "a2 - iso", "scale": "1:2"}
    added = await _ok(await tools["add_sheet"](call))
    evidence(
        "an A2 Details sheet at 1:2, now active",
        added["sheets"],
        call=f"add_sheet({call})",
    )
    details = next(s for s in added["sheets"] if s["name"] == "Details")
    assert details["active"] is True
    assert details["paper_mm"] == pytest.approx([594, 420])
    assert details["scale"] == "1:2"

    view = await _ok(
        await tools["create_drawing_view"](
            {"model_path": part, "view_type": "isometric", "position_x": 300}
        )
    )
    evidence("an isometric view on Details", view.get("data") or view)

    back = await _ok(await tools["activate_sheet"]({"name": "SHEET1"}))
    evidence(
        "back on Sheet1", back["sheets"], call="activate_sheet({'name': 'SHEET1'})"
    )
    assert back["active"] == "Sheet1"
