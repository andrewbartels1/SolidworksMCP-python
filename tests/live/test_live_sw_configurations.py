"""Configurations (queue item 13), checked on real SolidWorks.

1. ``create_configuration`` adds ``Long``; the active one stays ``Default``;
2. ``activate_configuration`` shows ``Long`` and back; ``list_configurations``
   reports the active one;
3. ``delete_configuration`` refuses the active one and an unknown name, then
   deletes ``Long``.

Run one with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_configurations.py::test_create_activate_and_delete

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.live.evidence import evidence
from tests.live.test_live_sw_beta_tools import _sketch

pytestmark = pytest.mark.asyncio


async def _tools(adapter: Any) -> dict[str, Any]:
    """The modeling and file-management tools on ``adapter``; name -> fn."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools.file_management import register_file_management_tools
    from solidworks_mcp.tools.modeling import register_modeling_tools
    from solidworks_mcp.tools.sketching import register_sketching_tools

    mcp = FastMCP("configurations-live")
    for register in (
        register_modeling_tools,
        register_sketching_tools,
        register_file_management_tools,
    ):
        await register(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


async def test_create_activate_and_delete(scratch: Any) -> None:
    """Long is added, shown, shown away from, refused while active, then deleted."""
    tools = await _tools(scratch.adapter)
    assert (await tools["create_part"]({"name": "configs"}))["status"] == "success"
    await _sketch(tools, "Top", {"x1": -20, "y1": -20, "x2": 20, "y2": 20})
    assert (await tools["create_extrusion"]({"depth": 20}))["status"] == "success"

    made = await tools["create_configuration"]({"name": "Long", "parent": "Default"})
    duplicate = await tools["create_configuration"]({"name": "Long"})
    shown = await tools["activate_configuration"]({"name": "Long"})
    listed = await tools["list_configurations"]()
    active_delete = await tools["delete_configuration"]({"name": "Long"})
    back = await tools["activate_configuration"]({"name": "Default"})
    unknown = await tools["delete_configuration"]({"name": "Ghost"})
    deleted = await tools["delete_configuration"]({"name": "Long"})

    evidence(
        "configurations",
        {
            "created": made.get("configuration", made.get("message")),
            "duplicate": [duplicate["status"], duplicate["message"]],
            "shown": [shown.get("active"), shown.get("previous")],
            "listed": [listed.get("configurations"), listed.get("active")],
            "delete_active": [active_delete["status"], active_delete["message"]],
            "back": back.get("active"),
            "delete_unknown": [unknown["status"], unknown["message"]],
            "deleted": [deleted.get("deleted"), deleted.get("configurations")],
        },
    )
    assert made["status"] == "success", made
    assert made["configuration"]["active"] == "Default"
    assert duplicate["status"] == "error"
    assert shown["active"] == "Long"
    assert listed["active"] == "Long"
    assert active_delete["status"] == "error"
    assert back["active"] == "Default"
    assert unknown["status"] == "error"
    assert deleted["status"] == "success", deleted
    assert "Long" not in deleted["configurations"]
