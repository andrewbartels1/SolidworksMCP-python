"""VBA source run through execute_macro, when the server allows it (#96).

1. With ``allow_vba_source`` on: VBA source that sketches a point on the
   Front Plane runs, and one new sketch appears; the reply names the .swb
   it wrote and repeats the source;
2. with it off (the default): the same call is refused as
   ``vba_source_off`` and nothing is added.

Run it with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_macro_source.py

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import FastMCP

from solidworks_mcp.config import SolidWorksMCPConfig
from solidworks_mcp.tools.macro_recording import register_macro_recording_tools
from tests.live.evidence import evidence, note
from tests.live.test_live_sw_beta_tools import _feature_names, _tools

pytestmark = pytest.mark.asyncio

SOURCE = """Dim swApp As Object
Dim Part As Object
Sub main()
    Set swApp = Application.SldWorks
    Set Part = swApp.ActiveDoc
    Part.ClearSelection2 True
    Part.Extension.SelectByID2 "Front Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0
    Part.SketchManager.InsertSketch True
    Part.SketchManager.CreatePoint 0, 0, 0
    Part.SketchManager.InsertSketch True
End Sub
"""


async def _execute_macro(adapter: Any, allow: bool) -> Any:
    """execute_macro registered with ``allow_vba_source`` set as given."""
    mcp = FastMCP("macro-source-live")
    config = SolidWorksMCPConfig(allow_vba_source=allow)
    await register_macro_recording_tools(mcp, adapter, config)
    return next(t.fn for t in await mcp.list_tools() if t.name == "execute_macro")


async def test_vba_source_runs_only_when_allowed(scratch: Any) -> None:
    """Allowed: the source adds a sketch. Not allowed: refused, nothing added."""
    tools = await _tools(scratch.adapter)
    assert (await tools["create_part"]({"name": "vba_source"}))["status"] == "success"
    note(
        "VBA source, run by execute_macro",
        "Allowed on this server: the source sketches a point. Then the same "
        "call on a server that doesn't allow it, refused on purpose.",
        seconds=4.0,
    )
    before = await _feature_names(scratch.adapter)
    allowed = await (await _execute_macro(scratch.adapter, True))(
        {"vba_source": SOURCE}
    )
    scratch.written_files.append(allowed.get("source_file", ""))
    added = [n for n in await _feature_names(scratch.adapter) if n not in before]
    evidence(
        "Allowed: the source ran and added a sketch",
        {
            "status": allowed.get("status"),
            "source_file": allowed.get("source_file"),
            "added": added,
        },
    )

    after = await _feature_names(scratch.adapter)
    refused = await (await _execute_macro(scratch.adapter, False))(
        {"vba_source": SOURCE}
    )
    unchanged = await _feature_names(scratch.adapter) == after
    evidence(
        "Not allowed: refused, and nothing changed",
        {
            "error_type": refused.get("error_type"),
            "message": refused.get("message"),
            "unchanged": unchanged,
        },
    )

    assert allowed["status"] == "success", allowed
    assert allowed["source_file"].endswith(".swb")
    assert len(added) == 1
    assert refused["error_type"] == "vba_source_off"
    assert unchanged
