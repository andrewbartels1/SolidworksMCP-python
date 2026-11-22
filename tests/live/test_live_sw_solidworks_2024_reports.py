"""The three SolidWorks 2024 reports (#255, #256, #257), checked on real SolidWorks.

Each follows the reporter's own steps. On SolidWorks 2026 these check that
the fixes changed nothing that worked; whether 2024 now works can only be
confirmed there.

1. #255: a 100 x 60 x 10 plate, a 5 mm fillet on a vertical corner edge.
2. #256: views of the plate at 0.5 (top) and 0.75 (isometric, given only as
   ``view_type``): each at its own scale, read back, and the isometric view
   really isometric.
3. #257: ``lookup_api_method`` from a working folder the server can't write
   to: the index is saved in ``~/.solidworks_mcp/docs-index``.

Run one with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_solidworks_2024_reports.py

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

import pytest

from tests.live.evidence import evidence

pytestmark = pytest.mark.asyncio


async def _tools(adapter: Any) -> dict[str, Any]:
    """Every tool, registered against ``adapter``: name -> function."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools import register_tools

    mcp = FastMCP("solidworks-2024-reports-live")
    await register_tools(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


async def _ok(reply: dict[str, Any]) -> dict[str, Any]:
    assert reply["status"] == "success", reply
    return reply


async def _plate(tools: dict[str, Any]) -> None:
    """The reporter's plate: a 100 x 60 rectangle on Top, extruded 10 mm."""
    await _ok(await tools["create_part"]({"name": "plate"}))
    made = await _ok(await tools["create_sketch"]({"plane": "Top"}))
    await _ok(await tools["add_rectangle"]({"x1": -50, "y1": -30, "x2": 50, "y2": 30}))
    await _ok(await tools["exit_sketch"]())
    await _ok(
        await tools["create_extrusion"](
            {"sketch_name": made["sketch"]["name"], "depth": 10}
        )
    )


async def test_a_fillet_on_the_reporters_plate(scratch: Any) -> None:
    """#255: one 5 mm fillet on a vertical corner edge removes its corner."""
    tools = await _tools(scratch.adapter)
    await _plate(tools)

    fillet = await tools["add_fillet"]({"radius": 5, "edge_names": ["0.05,0.005,0.03"]})
    expected = 100 * 60 * 10 - 5**2 * (1 - math.pi / 4) * 10
    checked = await tools["verify_model"]({"volume_mm3": round(expected, 3)})
    evidence(
        "#255: a 5 mm fillet on the plate's corner edge",
        {"fillet": fillet.get("message"), "verdict": checked["verdict"]},
        call='add_fillet({"radius": 5, "edge_names": ["0.05,0.005,0.03"]})',
    )
    assert fillet["status"] == "success", fillet
    assert checked["verdict"] == "pass", checked


async def test_views_at_their_own_scale(scratch: Any, tmp_path: Path) -> None:
    """#256: 0.5 and 0.75 views read back; view_type alone sets isometric."""
    tools = await _tools(scratch.adapter)
    await _plate(tools)
    part = str(tmp_path / "plate.SLDPRT")
    saved = await scratch.adapter.save_file(part)
    assert saved.is_success, saved.error
    scratch.written_files.append(part)
    await _ok(await tools["create_drawing"]({"name": "plate-views"}))

    top = await _ok(
        await tools["create_drawing_view"](
            {
                "model_path": part,
                "view_type": "top",
                "orientation": "top",
                "scale": 0.5,
                "position_x": 100,
                "position_y": 150,
            }
        )
    )
    iso = await _ok(
        await tools["create_drawing_view"](
            {
                "model_path": part,
                "view_type": "isometric",
                "scale": 0.75,
                "position_x": 280,
                "position_y": 150,
            }
        )
    )
    sheet = await _ok(
        await tools["create_drawing_view"](
            {
                "model_path": part,
                "view_type": "front",
                "position_x": 100,
                "position_y": 60,
            }
        )
    )
    evidence(
        "#256: each view at its own scale, read back; view_type sets isometric",
        {
            "top": {
                k: top["data"][k] for k in ("scale", "scale_applied", "scale_read")
            },
            "isometric": {
                k: iso["data"][k]
                for k in ("orientation", "scale", "scale_applied", "scale_read")
            },
            "no scale": {"scale_applied": sheet["data"]["scale_applied"]},
        },
        call="create_drawing_view(scale 0.5), (view_type isometric, scale 0.75), "
        "(no scale)",
    )
    assert top["data"]["scale_applied"] is True, top
    assert iso["data"]["orientation"] == "*Isometric", iso
    assert iso["data"]["scale_applied"] is True, iso
    assert sheet["data"]["scale_applied"] is None, sheet


async def test_a_lookup_from_a_folder_it_cant_write(
    scratch: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#257: started in an unwritable folder, the index goes to the user folder."""
    from solidworks_mcp.tools import docs_discovery

    tools = await _tools(scratch.adapter)
    locked = tmp_path / "locked"
    locked.mkdir()
    os.chmod(locked, 0o555)  # read-only: Windows honours the read-only flag
    monkeypatch.chdir(locked)

    result = await tools["lookup_api_method"](
        {"interface": "IDrawingDoc", "method": "AutoDimension"}
    )
    saved = sorted(docs_discovery.USER_INDEX_DIR.glob("solidworks_docs_index_*.json"))
    evidence(
        "#257: a lookup from a read-only working folder",
        {
            "status": result["status"],
            "found": result.get("result", {}).get("found"),
            "index_status": result.get("index_status"),
            "saved_in": str(docs_discovery.USER_INDEX_DIR),
            "files": [p.name for p in saved],
        },
        call='lookup_api_method({"interface": "IDrawingDoc", "method": "AutoDimension"})',
    )
    assert result["status"] == "success", result
    assert saved, "no index saved in the user folder"
    assert not (locked / ".generated").exists()
