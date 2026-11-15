"""The honest tool list (issue #174), checked on real SolidWorks.

One bundle, run together, then failures are fixed one at a time:

1. ``save_file`` to a new path, then refused for a missing folder, the wrong
   extension and an existing file (and allowed with ``overwrite``);
2. ``get_model_info`` reports the file's size and dates for a saved part, and
   nulls for a new one;
3. a deprecated tool still works and its result names the replacement;
4. the design-table probe that decides ``manage_design_table``: insert a
   design table on a scratch part from a two-row spreadsheet and read it back.
   It starts Excel (hidden) to write the spreadsheet, and SolidWorks opens it
   to read the table. Run it last.

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


def _write_design_table_sheet(path: Path) -> None:
    """A two-row design table for the block, written by Excel (hidden)."""
    from win32com.client import dynamic

    excel = dynamic.Dispatch("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    try:
        book = excel.Workbooks.Add()
        sheet = book.Worksheets(1)
        sheet.Cells(1, 2).Value = "D1@Boss-Extrude1"
        sheet.Cells(2, 1).Value = "Default"
        sheet.Cells(2, 2).Value = 20
        sheet.Cells(3, 1).Value = "Tall"
        sheet.Cells(3, 2).Value = 30
        book.SaveAs(str(path), 51)  # 51 = xlOpenXMLWorkbook (.xlsx)
        book.Close(False)
    finally:
        excel.Quit()


async def test_design_table_probe(scratch: Any, tmp_path: Path) -> None:
    """Insert a design table from a spreadsheet, then read it back.

    Decides ``manage_design_table`` (honest-tool-list task 2.0): if this
    works, the tool stays planned for queue item 13; if not, it is removed.
    """
    from solidworks_mcp.adapters import sw_type_info

    adapter = scratch.adapter
    tools = await _tools(adapter)
    await _block(tools, "design_table_probe")
    sheet = tmp_path / "block_table.xlsx"
    _write_design_table_sheet(sheet)

    model = sw_type_info.flagged(adapter.currentModel, "IModelDoc2")
    inserted = adapter._attempt(lambda: model.InsertFamilyTableOpen(str(sheet)))
    table = adapter._attempt(lambda: model.GetDesignTable(), default=None)
    read: dict[str, Any] = {"found": table is not None}
    if table is not None:
        flagged = sw_type_info.flagged(table, "IDesignTable")
        read["attached"] = adapter._attempt(lambda: flagged.Attach(), default=None)
        read["rows"] = adapter._attempt(
            lambda: flagged.GetTotalRowCount(), default=None
        )
        read["columns"] = adapter._attempt(
            lambda: flagged.GetTotalColumnCount(), default=None
        )
        read["cells"] = [
            [
                adapter._attempt(
                    lambda r=r, c=c: flagged.GetEntryText(r, c), default=None
                )
                for c in range(0, 2)
            ]
            for r in range(0, 3)
        ]
        adapter._attempt(lambda: flagged.Detach(), default=None)
    configurations = adapter._attempt(
        lambda: model.GetConfigurationNames(), default=None
    )

    evidence(
        "design table probe (decides manage_design_table)",
        {
            "inserted": inserted,
            "read_back": read,
            "configurations": list(configurations or []),
        },
    )
    assert inserted, "InsertFamilyTableOpen refused the spreadsheet"
    assert read["found"], "no design table after the insert"
    assert "Tall" in list(configurations or [])
