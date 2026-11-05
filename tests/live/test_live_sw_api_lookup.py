"""Live demo: the API lookups against this machine's SolidWorks type library (#195).

Every call goes through a real MCP client (``fastmcp.Client`` over the
in-memory transport), so inputs are validated and results serialised exactly
as for Claude or VS Code. Each test prints ``[evidence]`` lines for
``tests/scripts/live_demo.ps1``, one demo per test::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        tests/live/test_live_sw_api_lookup.py::test_the_agent_is_told_how_to_use_the_lookups

The lookups read the registered type library only; they never start or call
SolidWorks. Only the chamfer demo touches SolidWorks, on a scratch part. The
index is kept in a temporary folder, so every run starts from no index.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from fastmcp import Client, FastMCP

from solidworks_mcp.config import SolidWorksMCPConfig
from solidworks_mcp.tools.docs_discovery import register_docs_discovery_tools
from tests.live import coupon
from tests.live.evidence import evidence


class _Agent:
    """Calls tools the way an MCP client does, and prints each as evidence."""

    def __init__(self, client: Client) -> None:
        """Wrap a connected client.

        Args:
            client: An MCP client connected to the server under test.
        """
        self.client = client
        # How long the last tool call took, without the evidence hold.
        self.last_seconds = 0.0

    async def call(self, label: str, tool: str, **arguments: Any) -> dict[str, Any]:
        """Call ``tool`` with ``arguments`` and print the response as evidence.

        Args:
            label: What the response proves.
            tool: The tool name.
            **arguments: The tool's input fields.

        Returns:
            The tool's response.
        """
        started = time.perf_counter()
        result = await self.client.call_tool(
            tool, {"input_data": arguments}, raise_on_error=False
        )
        self.last_seconds = time.perf_counter() - started
        response: dict[str, Any] = result.structured_content or {}
        evidence(label, _brief(response), call=f"{tool}({arguments})")
        return response


def _brief(response: dict[str, Any]) -> dict[str, Any]:
    """A response without timing and long lists, so a caption stays readable."""
    shown = {key: value for key, value in response.items() if key != "execution_time"}
    result = shown.get("result")
    if isinstance(result, dict):
        result = dict(result)
        for key in ("methods", "properties", "related"):
            if isinstance(result.get(key), list) and len(result[key]) > 6:
                result[key] = [*result[key][:6], f"... {len(result[key]) - 6} more"]
        shown["result"] = result
    return shown


async def _server(adapter: object = None) -> FastMCP:
    """A server with the docs tools, plus the modelling tools for ``adapter``.

    Args:
        adapter: A connected adapter when a demo also models; None otherwise.

    Returns:
        The server.
    """
    mcp = FastMCP("api-lookup-demo")
    await register_docs_discovery_tools(mcp, adapter, SolidWorksMCPConfig())
    if adapter is not None:
        from solidworks_mcp.tools.modeling import register_modeling_tools

        await register_modeling_tools(mcp, adapter, {})
    return mcp


@pytest_asyncio.fixture
async def agent(tmp_path, monkeypatch) -> AsyncIterator[_Agent]:
    """An MCP client on the docs tools, with the index in an empty folder."""
    monkeypatch.chdir(tmp_path)
    async with Client(await _server()) as client:
        yield _Agent(client)


@pytest.mark.asyncio
async def test_the_agent_is_told_how_to_use_the_lookups(tmp_path, monkeypatch) -> None:
    """Demo 0: what an agent reads about lookup_api_method before calling it."""
    monkeypatch.chdir(tmp_path)
    async with Client(await _server()) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    lookup = tools["lookup_api_method"]
    fields = lookup.inputSchema["properties"]["input_data"]["anyOf"][0]["properties"]

    evidence(
        "The description an agent is given",
        lookup.description,
        call="list_tools() -> lookup_api_method",
    )
    evidence(
        "Each input field it can send",
        {name: schema["description"] for name, schema in fields.items()},
    )

    description = " ".join((lookup.description or "").split())
    assert "installed, not running" in description
    assert "builds the index" in description
    assert "Example input:" in description


@pytest.mark.asyncio
async def test_the_first_lookup_builds_the_index_and_later_ones_reuse_it(
    agent: _Agent,
) -> None:
    """Demo 1: no setup step. The first call builds the index, the next reuse it."""
    first = await agent.call(
        "First lookup, no index on disk: it builds one",
        "lookup_api_interface",
        interface="IModelDoc2",
    )
    first_seconds = agent.last_seconds
    second = await agent.call(
        "Second lookup: it reuses the saved index",
        "lookup_api_interface",
        interface="IModelDoc2",
    )
    second_seconds = agent.last_seconds
    evidence(
        "Time per call, without the demo's pause (seconds)",
        {"build": round(first_seconds, 3), "reuse": round(second_seconds, 3)},
    )

    assert first["index_status"] == "rebuilt"
    assert second["index_status"] == "ready"
    assert second_seconds < first_seconds
    assert first["source_index_file"] == second["source_index_file"]
    assert first["type_library_version"] == second["type_library_version"]
    assert first["result"]["method_count"] > 700


@pytest.mark.asyncio
async def test_real_signatures_come_from_the_type_library(agent: _Agent) -> None:
    """Demo 2: OpenDoc6's output parameters and SaveBMP's three inputs."""
    open_doc = await agent.call(
        "OpenDoc6: which parameters SolidWorks fills",
        "lookup_api_method",
        interface="ISldWorks",
        method="OpenDoc6",
    )
    save_bmp = await agent.call(
        "SaveBMP: the member the old list said didn't exist",
        "lookup_api_method",
        interface="IModelDoc2",
        method="SaveBMP",
    )

    directions = {p["name"]: p["direction"] for p in open_doc["result"]["parameters"]}
    assert directions == {
        "FileName": "in",
        "Type": "in",
        "Options": "in",
        "Configuration": "in",
        "Errors": "in_out",
        "Warnings": "in_out",
    }
    assert open_doc["result"]["return_type"] == "IModelDoc2"
    assert [p["name"] for p in save_bmp["result"]["parameters"]] == [
        "FileNameIn",
        "WidthIn",
        "HeightIn",
    ]


@pytest.mark.asyncio
async def test_a_made_up_name_and_a_wrong_casing_are_caught(agent: _Agent) -> None:
    """Demo 3: the two mistakes an agent makes, answered plainly."""
    made_up = await agent.call(
        "A made-up member: no match, and why",
        "lookup_api_method",
        interface="IModelDoc2",
        method="SaveBitmapWithVariableSize",
    )
    casing = await agent.call(
        "A wrong casing: found under SolidWorks' spelling",
        "lookup_api_method",
        interface="IModelDoc2",
        method="ViewZoomToFit2",
    )

    assert made_up["result"]["found"] is False
    assert "is not an indexed member of IModelDoc2" in made_up["result"]["note"]
    assert casing["result"]["member"] == "ViewZoomtofit2"
    assert "spells it 'ViewZoomtofit2'" in casing["result"]["note"]


@pytest.mark.asyncio
async def test_a_lookup_settles_where_a_call_lives_then_the_tool_runs(
    scratch, tmp_path, monkeypatch
) -> None:
    """Demo 4: InsertFeatureChamfer is on IFeatureManager (runbook #12), then a real chamfer."""
    monkeypatch.chdir(tmp_path)
    adapter = scratch.adapter
    async with Client(await _server(adapter)) as client:
        agent = _Agent(client)
        wrong = await agent.call(
            "Is InsertFeatureChamfer on IModelDocExtension?",
            "lookup_api_method",
            interface="IModelDocExtension",
            method="InsertFeatureChamfer",
        )
        right = await agent.call(
            "It's on IFeatureManager, with these parameters",
            "lookup_api_method",
            interface="IFeatureManager",
            method="InsertFeatureChamfer",
        )

        part = await coupon.build(adapter)
        evidence(
            "The block as built: the 15 mm axis is its height",
            {"bounding_box_mm": part.box, "face_with_the_hole": part.hole_face},
        )
        before = await coupon.volume(adapter)
        chamfer = await agent.call(
            "add_chamfer, which calls IFeatureManager.InsertFeatureChamfer",
            "add_chamfer",
            distance=0.5,
            edge_names=[part.hole_face],
        )
        removed = before - await coupon.volume(adapter)
        # The hole rim plus the face's four 30 mm edges, whose four mitred
        # corners are removed once each: 17.1241 mm^3.
        expected = (
            coupon.circular_chamfer_volume(coupon.HOLE_RADIUS_MM, 0.5)
            + 4 * coupon.straight_chamfer_volume(coupon.EDGE_MM, 0.5)
            - 4 * coupon.chamfer_corner_overlap(0.5)
        )
        evidence(
            "Material the chamfer removed (mm^3)",
            {"removed": round(removed, 4), "exact": round(expected, 4)},
        )

    assert wrong["result"]["found"] is False
    assert right["result"]["found"] is True
    assert len(right["result"]["parameters"]) == 8
    assert chamfer["status"] == "success", chamfer
    # A side face (two 30 mm and two 15 mm edges) gives 11.0833 mm^3.
    assert removed == pytest.approx(expected, abs=coupon.VOLUME_TOLERANCE_MM3)


@pytest.mark.asyncio
async def test_a_year_that_isnt_installed_is_explained(agent: _Agent) -> None:
    """Demo 5: the failure case. Asking for SolidWorks 2024 names what is installed."""
    lookup = await agent.call(
        "A lookup for SolidWorks 2024: no match, and why",
        "lookup_api_method",
        interface="ISldWorks",
        method="OpenDoc6",
        year=2024,
    )
    discover = await agent.call(
        "A rebuild for SolidWorks 2024: a clear error",
        "discover_solidworks_docs",
        year=2024,
    )

    assert lookup["index_status"] == "unavailable"
    assert (
        "SolidWorks 2024 isn't installed here; installed:" in lookup["result"]["note"]
    )
    # Only real releases are listed, not a stray pre-1995 registry key.
    assert "1993" not in lookup["result"]["note"]
    assert discover["status"] == "error"
    assert "SolidWorks 2024 isn't installed here" in discover["message"]


@pytest.mark.asyncio
async def test_every_interface_is_indexed_without_com_plumbing(agent: _Agent) -> None:
    """IModelDocExtension (never in the old list) is indexed; COM plumbing isn't."""
    extension = await agent.call(
        "IModelDocExtension", "lookup_api_interface", interface="IModelDocExtension"
    )
    app = await agent.call("ISldWorks", "lookup_api_interface", interface="ISldWorks")

    assert extension["result"]["found"] is True
    assert extension["result"]["method_count"] > 100
    members = app["result"]["methods"] + app["result"]["properties"]
    assert "QueryInterface" not in members
    assert "Invoke" not in members
