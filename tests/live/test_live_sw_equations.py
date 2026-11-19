"""Equations and global variables (queue item 29), checked on real SolidWorks.

1. ``set_equation`` adds the global variable ``Depth`` = 30mm and makes the
   block's extrusion depth ``"Depth"``; the depth reads 30 mm, and 45 mm
   (volume 72,000 mm³) after ``Depth`` = 45mm. ``list_equations`` shows both
   with their values (confirming the units ``Value`` reports). An expression
   naming a variable that doesn't exist is refused as ``equation_refused``
   and the list is unchanged. Deleting the depth equation keeps 45 mm;
2. ``Depth`` = 50mm in ``Long`` only: ``Long`` is 50 mm deep, ``Default``
   stays 30 mm.

Run one with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_equations.py::test_a_global_variable_drives_the_depth

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.live.evidence import evidence
from tests.live.test_live_sw_beta_tools import _sketch

pytestmark = pytest.mark.asyncio

DEPTH = "D1@Boss-Extrude1"


async def _tools(adapter: Any) -> dict[str, Any]:
    """The modeling, equation and file-management tools on ``adapter``."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools.analysis import register_analysis_tools
    from solidworks_mcp.tools.engineering_data import register_engineering_data_tools
    from solidworks_mcp.tools.equations import register_equation_tools
    from solidworks_mcp.tools.file_management import register_file_management_tools
    from solidworks_mcp.tools.modeling import register_modeling_tools
    from solidworks_mcp.tools.sketching import register_sketching_tools

    mcp = FastMCP("equations-live")
    for register in (
        register_modeling_tools,
        register_sketching_tools,
        register_file_management_tools,
        register_analysis_tools,
        register_engineering_data_tools,
        register_equation_tools,
    ):
        await register(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


async def _block(tools: dict[str, Any], name: str) -> None:
    """A 40 x 40 mm block, 20 mm deep, on the Top plane."""
    assert (await tools["create_part"]({"name": name}))["status"] == "success"
    await _sketch(tools, "Top", {"x1": -20, "y1": -20, "x2": 20, "y2": 20})
    assert (await tools["create_extrusion"]({"depth": 20}))["status"] == "success"


async def _depth(tools: dict[str, Any]) -> Any:
    """The extrusion depth in mm, as get_dimension reads it."""
    read = await tools["get_dimension"]({"name": DEPTH})
    return read.get("dimension", {}).get("value")


async def test_a_global_variable_drives_the_depth(scratch: Any) -> None:
    """Depth drives the extrusion; a bad expression is refused; delete keeps it."""
    tools = await _tools(scratch.adapter)
    await _block(tools, "equations")

    variable = await tools["set_equation"]({"name": "Depth", "expression": "30mm"})
    driven = await tools["set_equation"]({"name": DEPTH, "expression": '"Depth"'})
    at_30 = await _depth(tools)
    changed = await tools["set_equation"]({"name": "Depth", "expression": "45mm"})
    at_45 = await _depth(tools)
    mass = await tools["get_mass_properties"]()
    volume = round(float(mass["mass_properties"]["volume"]["value"]), 1)
    listed = await tools["list_equations"]()
    refused = await tools["set_equation"](
        {"name": "Width", "expression": '"NoSuchVariable" * 2'}
    )
    after_refusal = await tools["list_equations"]()
    deleted = await tools["delete_equation"]({"name": DEPTH})
    kept = await _depth(tools)

    evidence(
        "Depth drives the extrusion depth",
        {
            "added": [variable.get("message"), driven.get("message")],
            "depth_at_30_then_45": [at_30, at_45],
            "changed": changed.get("equation"),
            "volume_mm3": volume,
            "listed": listed.get("equations"),
        },
    )
    evidence(
        "A bad expression is refused; deleting keeps the last depth",
        {
            "refused": [
                refused["status"],
                refused.get("error_type"),
                refused["message"],
            ],
            "unchanged": after_refusal.get("equations") == listed.get("equations"),
            "deleted": [deleted.get("deleted"), deleted.get("equations")],
            "depth_after_delete": kept,
        },
    )
    assert variable["status"] == "success", variable
    assert driven["status"] == "success", driven
    assert at_30 == pytest.approx(30.0, abs=1e-6)
    assert changed["equation"]["action"] == "changed"
    assert at_45 == pytest.approx(45.0, abs=1e-6)
    assert volume == pytest.approx(72000.0, rel=1e-3)
    kinds = {row["name"]: row["kind"] for row in listed["equations"]}
    assert kinds == {"Depth": "global_variable", DEPTH: "dimension"}
    assert refused["error_type"] == "equation_refused", refused
    assert after_refusal["equations"] == listed["equations"]
    assert deleted["equations"] == ["Depth"]
    assert kept == pytest.approx(45.0, abs=1e-6)


async def test_an_equation_in_one_configuration(scratch: Any) -> None:
    """Depth = 50mm in Long only; Default keeps 30 mm."""
    tools = await _tools(scratch.adapter)
    await _block(tools, "equation_configs")
    made = await tools["create_configuration"]({"name": "Long"})
    assert made["status"] == "success", made
    assert (await tools["set_equation"]({"name": "Depth", "expression": "30mm"}))[
        "status"
    ] == "success"
    assert (await tools["set_equation"]({"name": DEPTH, "expression": '"Depth"'}))[
        "status"
    ] == "success"

    long_only = await tools["set_equation"](
        {"name": "Depth", "expression": "50mm", "configurations": ["Long"]}
    )
    default_depth = await _depth(tools)
    await tools["activate_configuration"]({"name": "Long"})
    long_depth = await _depth(tools)
    await tools["activate_configuration"]({"name": "Default"})

    evidence(
        "Depth = 50mm in Long only",
        {
            "set": long_only.get("equation", long_only.get("message")),
            "depth_default_long": [default_depth, long_depth],
        },
    )
    assert long_only["status"] == "success", long_only
    assert default_depth == pytest.approx(30.0, abs=1e-6)
    assert long_depth == pytest.approx(50.0, abs=1e-6)
