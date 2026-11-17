"""VBA source run through execute_macro, when the server allows it (#96).

1. ``restricted``: VBA source that sketches a point on the Front Plane
   passes the SolidWorks-only check and runs; one new sketch appears, and
   the reply names the .swb it wrote;
2. ``restricted``: the same source with a ``Shell`` line is refused as
   ``vba_source_refused``, naming the line; nothing is added;
3. ``off`` (the default): refused as ``vba_source_off``; nothing is added.

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


async def _execute_macro(adapter: Any, allow: str) -> Any:
    """execute_macro registered with ``allow_vba_source`` set as given."""
    mcp = FastMCP("macro-source-live")
    config = SolidWorksMCPConfig(allow_vba_source=allow)
    await register_macro_recording_tools(mcp, adapter, config)
    return next(t.fn for t in await mcp.list_tools() if t.name == "execute_macro")


async def test_vba_source_runs_only_when_allowed(scratch: Any) -> None:
    """Restricted: the source runs; with Shell, refused. Off: refused."""
    tools = await _tools(scratch.adapter)
    assert (await tools["create_part"]({"name": "vba_source"}))["status"] == "success"
    note(
        "VBA source, run by execute_macro",
        "Restricted mode: the SolidWorks-only source sketches a point. Then, "
        "on purpose, the same source with a Shell line, and a server with "
        "VBA source off: both refused, nothing added.",
        seconds=4.0,
    )
    before = await _feature_names(scratch.adapter)
    allowed = await (await _execute_macro(scratch.adapter, "restricted"))(
        {"vba_source": SOURCE}
    )
    scratch.written_files.append(allowed.get("source_file", ""))
    added = [n for n in await _feature_names(scratch.adapter) if n not in before]
    evidence(
        "Restricted: the SolidWorks-only source ran and added a sketch",
        {
            "status": allowed.get("status"),
            "source_file": allowed.get("source_file"),
            "added": added,
        },
    )

    after = await _feature_names(scratch.adapter)
    shell = SOURCE.replace("End Sub", '    Shell "notepad.exe"\nEnd Sub')
    checked = await (await _execute_macro(scratch.adapter, "restricted"))(
        {"vba_source": shell}
    )
    evidence(
        "Restricted: a Shell line is refused before anything runs",
        {k: checked.get(k) for k in ("error_type", "message")},
    )
    refused = await (await _execute_macro(scratch.adapter, "off"))(
        {"vba_source": SOURCE}
    )
    unchanged = await _feature_names(scratch.adapter) == after
    evidence(
        "Off (the default): refused, and nothing changed",
        {
            "error_type": refused.get("error_type"),
            "message": refused.get("message"),
            "unchanged": unchanged,
        },
    )

    assert allowed["status"] == "success", allowed
    assert allowed["source_file"].endswith(".swb")
    assert len(added) == 1
    assert checked["error_type"] == "vba_source_refused"
    assert "Shell: reaches outside SolidWorks" in checked["message"]
    assert refused["error_type"] == "vba_source_off"
    assert unchanged
