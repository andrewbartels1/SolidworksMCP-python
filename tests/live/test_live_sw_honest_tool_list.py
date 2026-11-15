"""The honest tool list (issue #174), checked on real SolidWorks.

One bundle, run together, then failures are fixed one at a time:

1. ``save_file`` to a new path, then refused for a missing folder, the wrong
   extension and an existing file (and allowed with ``overwrite``);
2. ``get_model_info`` reports the file's size and dates for a saved part, and
   nulls for a new one;
3. a deprecated tool still works and its result names the replacement.

Run one with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_honest_tool_list.py::test_save_file_checks_a_new_path

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows (see
``tests/live/conftest.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.live.evidence import evidence
from tests.live.test_live_sw_beta_tools import _sketch

pytestmark = pytest.mark.asyncio


async def _tools(adapter: Any) -> dict[str, Any]:
    """The tool families these tests use, registered on ``adapter``; name -> fn."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools.file_management import register_file_management_tools
    from solidworks_mcp.tools.modeling import register_modeling_tools
    from solidworks_mcp.tools.sketching import register_sketching_tools

    mcp = FastMCP("honest-tool-list-live")
    for register in (
        register_modeling_tools,
        register_sketching_tools,
        register_file_management_tools,
    ):
        await register(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


async def _block(tools: dict[str, Any], name: str) -> None:
    """A new part holding a 40 x 40 x 20 mm block (``D1@Boss-Extrude1`` = 20)."""
    assert (await tools["create_part"]({"name": name}))["status"] == "success"
    await _sketch(tools, "Top", {"x1": -20, "y1": -20, "x2": 20, "y2": 20})
    made = await tools["create_extrusion"]({"depth": 20})
    assert made["status"] == "success", made


async def test_save_file_checks_a_new_path(scratch: Any, tmp_path: Path) -> None:
    """A new path saves; a missing folder, wrong extension or existing file don't."""
    tools = await _tools(scratch.adapter)
    await _block(tools, "save_checks")
    target = tmp_path / "block.SLDPRT"
    scratch.written_files.append(str(target))

    saved = await tools["save_file"]({"file_path": str(target)})
    missing = await tools["save_file"](
        {"file_path": str(tmp_path / "no_such_folder" / "block.SLDPRT")}
    )
    wrong = await tools["save_file"]({"file_path": str(tmp_path / "block.SLDASM")})
    kept = await tools["save_file"]({"file_path": str(target)})
    replaced = await tools["save_file"]({"file_path": str(target), "overwrite": True})

    evidence(
        "save_file: new path, missing folder, wrong extension, existing file",
        {
            "saved": [saved["status"], target.exists()],
            "missing_folder": [missing.get("error_type"), missing["message"]],
            "wrong_extension": [wrong.get("error_type"), wrong["message"]],
            "existing": [kept.get("error_type"), kept["message"]],
            "overwrite": replaced["status"],
        },
    )
    assert saved["status"] == "success", saved
    assert target.stat().st_size > 0
    assert missing["error_type"] == "invalid_input"
    assert not (tmp_path / "no_such_folder").exists()
    assert wrong["error_type"] == "invalid_input"
    assert ".sldprt" in wrong["message"]
    assert kept["error_type"] == "invalid_input"
    assert replaced["status"] == "success", replaced


async def test_get_model_info_reports_the_file(scratch: Any, tmp_path: Path) -> None:
    """A saved part has a size and dates; a new one has nulls."""
    tools = await _tools(scratch.adapter)
    await _block(tools, "info_saved")
    target = tmp_path / "info.SLDPRT"
    scratch.written_files.append(str(target))
    assert (await tools["save_file"]({"file_path": str(target)}))["status"] == (
        "success"
    )
    saved = (await tools["get_model_info"]())["model_info"]

    assert (await tools["create_part"]({"name": "info_new"}))["status"] == "success"
    new = (await tools["get_model_info"]())["model_info"]

    evidence(
        "get_model_info on a saved part and a new one",
        {
            "saved": {k: saved[k] for k in ("path", "size_bytes", "modified")},
            "new": {k: new[k] for k in ("path", "size_bytes", "modified")},
        },
    )
    assert saved["size_bytes"] == target.stat().st_size
    assert saved["created"] is not None and saved["modified"] is not None
    assert new["size_bytes"] is None and new["modified"] is None


async def test_a_deprecated_tool_names_its_replacement(
    scratch: Any, tmp_path: Path
) -> None:
    """``load_part`` still opens a part, and says to use ``open_model``."""
    tools = await _tools(scratch.adapter)
    await _block(tools, "deprecated")
    target = tmp_path / "deprecated.SLDPRT"
    scratch.written_files.append(str(target))
    assert (await tools["save_file"]({"file_path": str(target)}))["status"] == (
        "success"
    )
    assert (await tools["close_model"]({"save": False}))["status"] == "success"

    loaded = await tools["load_part"]({"file_path": str(target)})

    evidence(
        "load_part (deprecated)",
        {"status": loaded["status"], "warning": loaded.get("warning")},
        call=f'load_part({{"file_path": "{target.name}"}})',
    )
    assert loaded["status"] == "success", loaded
    assert loaded["warning"] == "Deprecated: use `open_model`."
