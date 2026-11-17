"""Material properties (queue item 20), checked on real SolidWorks.

On a 40 x 40 x 20 mm block made of AISI 1020:

1. ``get_material`` reads the part's material with its elastic modulus,
   Poisson's ratio, yield and tensile strength, in SI units; the density it
   reports times the volume is the mass SolidWorks measures;
2. 6061-T6 (SS) and ABS are read by name without assigning them (ABS has no
   yield strength in the library), and the part is still AISI 1020;
3. an unknown name is refused as ``not_found``.

Run it with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_material_properties.py

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.live.evidence import evidence
from tests.live.test_live_sw_part_features import _block

pytestmark = pytest.mark.asyncio


async def _tools(adapter: Any) -> dict[str, Any]:
    """Modeling, sketching, analysis and engineering-data tools; name -> fn."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools.analysis import register_analysis_tools
    from solidworks_mcp.tools.engineering_data import register_engineering_data_tools
    from solidworks_mcp.tools.modeling import register_modeling_tools
    from solidworks_mcp.tools.sketching import register_sketching_tools

    mcp = FastMCP("material-live")
    for register in (
        register_modeling_tools,
        register_sketching_tools,
        register_analysis_tools,
        register_engineering_data_tools,
    ):
        await register(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


def _values(reply: dict[str, Any]) -> dict[str, float]:
    """The reply's properties as key -> SI value."""
    return {k: v["value"] for k, v in reply["data"]["properties"].items()}


async def test_material_properties_from_the_library(scratch: Any) -> None:
    """AISI 1020 on the part; 6061-T6 and ABS by name; an unknown name refused."""
    tools = await _tools(scratch.adapter)
    await _block(tools, "material_props")
    assigned = await tools["set_material"]({"material_name": "AISI 1020"})
    assert assigned["status"] == "success", assigned

    steel = await tools["get_material"]({})
    mass = await tools["get_mass_properties"]()
    aluminium = await tools["get_material"]({"material": "6061-T6 (SS)"})
    plastic = await tools["get_material"]({"material": "ABS"})
    still = await tools["get_material"]({})
    unknown = await tools["get_material"]({"material": "Unobtainium"})

    volume_m3 = mass["mass_properties"]["volume"]["value"] / 1e9
    measured_kg = mass["mass_properties"]["mass"]["value"]
    evidence(
        "get_material: AISI 1020 on the part, in SI units",
        {"message": steel["message"], "properties": _values(steel)},
    )
    evidence(
        "Density x volume = the mass SolidWorks measures",
        {
            "density_kg_m3": steel["data"]["density_kg_m3"],
            "volume_m3": volume_m3,
            "density_x_volume_kg": steel["data"]["density_kg_m3"] * volume_m3,
            "measured_kg": measured_kg,
        },
    )
    evidence(
        "Read by name, nothing assigned: 6061-T6 and ABS (no yield in the library)",
        {
            "6061": [aluminium["message"], _values(aluminium)],
            "ABS": [plastic["message"], _values(plastic)],
            "part_still": still["data"]["material"],
        },
    )
    evidence(
        "An unknown material, refused",
        {k: unknown[k] for k in ("status", "error_type", "message")},
    )

    props = _values(steel)
    assert steel["data"]["source"] == "part"
    assert props["elastic_modulus"] == pytest.approx(2.0e11)
    assert props["poissons_ratio"] == pytest.approx(0.29)
    assert props["yield_strength"] == pytest.approx(3.51571e8)
    assert props["tensile_strength"] == pytest.approx(4.20507e8)
    assert steel["data"]["density_kg_m3"] * volume_m3 == pytest.approx(
        measured_kg, rel=1e-3
    )
    assert _values(aluminium)["elastic_modulus"] == pytest.approx(6.9e10)
    assert aluminium["data"]["source"] == "library"
    assert "yield_strength" not in _values(plastic)
    assert still["data"]["material"] == "AISI 1020"
    assert unknown["error_type"] == "not_found"
