"""Search mode with the core toolset (queue item 14), on real SolidWorks.

The server lists four tools; an agent-style build finds each step with
``search_tools`` and runs it with ``call_tool``: a part, a 40 x 40 mm
sketch, a 20 mm extrusion, the top edges selected and filleted at 2 mm,
then the volume read back. A drawing tool, outside ``core``, is refused.

Run it with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_tool_search.py

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from solidworks_mcp.tools import register_tools
from solidworks_mcp.tools.toolsets import apply_tool_visibility
from tests.live.evidence import evidence, note

pytestmark = pytest.mark.asyncio


async def test_a_build_in_search_mode(scratch: Any) -> None:
    """Search, then call, for every step; the geometry checks out."""
    note(
        "Search mode, core toolset",
        "The client sees 4 tools, not 135 (about 900 tokens a turn, not 55,000). "
        "Each step is found with search_tools, then run with call_tool.",
        seconds=4.0,
    )
    mcp = FastMCP("search-live")
    await register_tools(mcp, scratch.adapter, {})
    apply_tool_visibility(mcp, ("core",), "search")
    found: dict[str, list[str]] = {}

    async with Client(mcp) as client:
        listed = sorted(t.name for t in await client.list_tools())

        async def search(query: str, wanted: str) -> None:
            reply = await client.call_tool("search_tools", {"query": query})
            names = [t["name"] for t in json.loads(reply.content[0].text)]
            found[query] = names
            assert wanted in names, (query, names)

        async def call(name: str, arguments: dict[str, Any] | None = None) -> Any:
            args = {"input_data": arguments} if arguments is not None else {}
            reply = await client.call_tool(
                "call_tool", {"name": name, "arguments": args}, raise_on_error=False
            )
            return reply

        await search("create a new part", "create_part")
        assert not (await call("create_part", {"name": "search_block"})).is_error
        await search("sketch on a plane", "create_sketch")
        assert not (await call("create_sketch", {"plane": "Top"})).is_error
        await search("draw a rectangle in the sketch", "add_rectangle")
        rect = {"x1": -20, "y1": -20, "x2": 20, "y2": 20}
        assert not (await call("add_rectangle", rect)).is_error
        await search("close the sketch", "exit_sketch")
        assert not (await call("exit_sketch")).is_error
        await search("extrude the sketch into a solid", "create_extrusion")
        assert not (await call("create_extrusion", {"depth": 20})).is_error
        await search("select the edges of a face", "select_face_edges")
        picked = await call("select_face_edges", {"side": "top", "edge_type": "linear"})
        assert not picked.is_error, picked
        await search("fillet edges", "add_fillet")
        fillet = await call("add_fillet", {"radius": 2, "edge_names": []})
        # A failed tool answers with status "error", not an MCP error.
        assert fillet.structured_content["status"] == "success", fillet
        await search("mass properties volume", "get_mass_properties")
        mass = (await call("get_mass_properties", {})).structured_content
        hidden = await call("create_drawing_view", {"view_type": "front"})

    volume = mass["mass_properties"]["volume"]["value"]
    evidence("Search mode with core: what the client lists", {"tools": listed})
    evidence("Each search's results (best first)", found)
    evidence(
        "The block: 40 x 40 x 20 mm with 2 mm fillets on its top edges",
        {"volume_mm3": volume, "block_mm3": 32000},
    )
    evidence(
        "A drawing tool, outside core, is refused",
        {"is_error": hidden.is_error, "message": str(hidden.content[0].text)[:200]},
    )

    assert listed == [
        "call_tool",
        "get_model_info",
        "reset_circuit_breaker",
        "search_tools",
    ]
    # Each top edge loses r^2 (1 - pi/4) per mm of length: about 137 mm^3.
    assert 31_800 < volume < 32_000
    assert hidden.is_error
