"""Saving a document as a template (queue item 21), checked on real SolidWorks.

1. A part set up once: inches (IPS), 6061-T6 (SS), a ``Company`` property;
2. ``save_as_template`` by path writes the ``.prtdot``, and SolidWorks has
   the template open in place of the part, as File > Save As does; the
   reply warns; a ``.asmdot`` path for a part is refused first;
3. ``create_part`` with that template starts a part with the same units,
   material and property;
4. that part, saved as a ``.sldprt`` and then as a second template: the
   template opens in its place too, and the ``.sldprt`` is left on disk.

The first run (2026-11-16) expected ``swSaveAsOptions_Copy`` to keep the
part open as itself; SolidWorks ignored it for both, through
``IModelDoc2.SaveAs3`` and ``IModelDocExtension.SaveAs``.

The template goes to the test's temporary folder, never to SolidWorks' own
template folders (``name`` would write there; the unit tests cover it).

Run it with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_templates.py

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from solidworks_mcp.adapters.solidworks.io import _SW_PREF_UNIT_SYSTEM, _pref_int
from tests.live.evidence import evidence

pytestmark = pytest.mark.asyncio

#: ``swUnitSystem_e``: IPS is 3, MMGS 5.
_IPS = 3


async def _tools(adapter: Any) -> dict[str, Any]:
    """Modeling, file-management and engineering-data tools; name -> fn."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools.engineering_data import register_engineering_data_tools
    from solidworks_mcp.tools.file_management import register_file_management_tools
    from solidworks_mcp.tools.modeling import register_modeling_tools

    mcp = FastMCP("templates-live")
    for register in (
        register_modeling_tools,
        register_file_management_tools,
        register_engineering_data_tools,
    ):
        await register(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


def _unit_system(adapter: Any) -> int | None:
    """The active document's ``swUnitSystem_e``, read from SolidWorks."""
    model = adapter.currentModel
    ext = adapter._attempt(lambda: model.Extension, default=None)
    return _pref_int(adapter, ext, _SW_PREF_UNIT_SYSTEM)


async def test_a_part_set_up_once_starts_the_next(scratch: Any, tmp_path: Path) -> None:
    """Units, material and a property carry from a template into a new part."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    first = str(tmp_path / "Plate IPS.prtdot")
    part_file = str(tmp_path / "from_template.SLDPRT")
    second = str(tmp_path / "Plate IPS 2.prtdot")
    scratch.written_files += [first, part_file, second]

    made = await tools["create_part"]({"name": "template_source", "units": "in"})
    assert made["status"] == "success", made
    assert (await tools["set_material"]({"material_name": "6061-T6 (SS)"}))[
        "status"
    ] == "success"
    company = await tools["set_custom_property"]({"name": "Company", "value": "Acme"})
    assert company["status"] == "success", company
    source_units = _unit_system(adapter)
    source_title = adapter.currentModel.GetTitle()

    wrong = await tools["save_as_template"]({"file_path": str(tmp_path / "x.asmdot")})
    saved = await tools["save_as_template"]({"file_path": first})
    evidence(
        "save_as_template on a part never saved: written, and now the open document",
        {
            "message": saved["message"],
            "warning": saved.get("warning"),
            "written": os.path.isfile(first),
            "open_document": [source_title, adapter.currentModel.GetTitle()],
            "solidworks_template_folders": saved["data"]["template_folders"],
        },
    )
    evidence(
        "A part's template saved as .asmdot, refused before SolidWorks is asked",
        {k: wrong[k] for k in ("status", "error_type", "message")},
    )

    fresh = await tools["create_part"]({"name": "from_template", "template": first})
    assert fresh["status"] == "success", fresh
    material = await tools["get_material"]({})
    properties = await tools["get_custom_properties"]({})
    fresh_units = _unit_system(adapter)
    evidence(
        "create_part from the template: the same units, material and property",
        {
            "unit_system": [source_units, fresh_units],
            "material": material["data"]["material"],
            "Company": properties["data"]["properties"].get("Company"),
        },
    )

    assert (await tools["save_file"]({"file_path": part_file}))["status"] == "success"
    saved_title = adapter.currentModel.GetTitle()
    copied = await tools["save_as_template"]({"file_path": second})
    evidence(
        "save_as_template on a saved part: the template opens in its place, the file kept",
        {
            "warning": copied.get("warning"),
            "open_document": [saved_title, adapter.currentModel.GetTitle()],
            "part_file_still_on_disk": os.path.isfile(part_file),
        },
    )

    assert saved["status"] == "success", saved
    assert os.path.isfile(first)
    assert saved["data"]["document_became_template"] is True
    assert "exists only as this template" in saved["warning"]
    assert wrong["error_type"] == "invalid_input"
    assert (source_units, fresh_units) == (_IPS, _IPS)
    assert material["data"]["material"] == "6061-T6 (SS)"
    assert properties["data"]["properties"]["Company"]["value"] == "Acme"
    assert copied["status"] == "success", copied
    assert os.path.isfile(second)
    assert copied["data"]["document_became_template"] is True
    assert "is unchanged on disk" in copied["warning"]
    assert os.path.isfile(part_file)
