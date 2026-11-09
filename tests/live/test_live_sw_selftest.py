"""The selftest on real SolidWorks: every area passes, the user's part is untouched.

Before the run, the test opens a "user" part: a block that was never saved
and has unsaved changes. After it, that part must still be open, unsaved,
with the same features, and every document the selftest made must be gone.

Run with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_selftest.py

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows (see
``tests/live/conftest.py``).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests.live.evidence import evidence


class _KeepConnected:
    """The live adapter, minus ``disconnect``: the fixture owns the connection."""

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter

    def __getattr__(self, name: str) -> Any:
        return getattr(self._adapter, name)

    async def disconnect(self) -> None:
        return None


async def _users_part(adapter: Any) -> Any:
    """A never-saved block with unsaved changes, left as the active document."""
    from solidworks_mcp.adapters.base import ExtrusionParameters

    assert (await adapter.create_part()).is_success
    assert (await adapter.create_sketch("Front")).is_success
    assert (await adapter.add_rectangle(0.0, 0.0, 30.0, 30.0)).is_success
    assert (await adapter.exit_sketch()).is_success
    assert (await adapter.create_extrusion(ExtrusionParameters(depth=5.0))).is_success
    return adapter.currentModel


def _state(adapter: Any, doc: Any) -> dict[str, Any]:
    """What must not change about the user's part."""
    read = adapter._get_attr_or_call
    return {
        "title": str(read(doc, "GetTitle")),
        "path": str(read(doc, "GetPathName") or ""),
        "unsaved_changes": bool(read(doc, "GetSaveFlag")),
        "features": int(read(doc, "GetFeatureCount")),
    }


@pytest.mark.asyncio
@pytest.mark.timeout(900)
async def test_selftest_passes_and_leaves_the_users_part_alone(
    scratch, tmp_path: Path, capsys
) -> None:
    """Run the selftest's whole flow on SolidWorks 2026 with a user part open."""
    from fastmcp import FastMCP

    from solidworks_mcp.config import SolidWorksMCPConfig
    from solidworks_mcp.selftest.cli import EXIT_PASS, run_selftest
    from solidworks_mcp.tools import register_tools

    adapter = scratch.adapter
    users = await _users_part(adapter)
    before = _state(adapter, users)
    evidence("the user's part, open and unsaved, before the selftest", before)

    config = SolidWorksMCPConfig()
    config.solidworks_year = 2026

    async def _server(cfg: SolidWorksMCPConfig) -> SimpleNamespace:
        mcp = FastMCP("selftest-live")
        await register_tools(mcp, adapter, cfg)
        return SimpleNamespace(mcp=mcp, adapter=_KeepConnected(adapter))

    report = tmp_path / "selftest.md"
    code = await run_selftest(config, report, _server)
    printed = capsys.readouterr().out
    lines = [
        line for line in printed.splitlines() if line[:4] in {"PASS", "FAIL", "SKIP"}
    ]
    evidence("selftest result per area", {"exit_code": code, "areas": lines})

    after = _state(adapter, users)
    open_titles = [
        d.get("title") for d in (await adapter.list_open_documents()).data or []
    ]
    evidence(
        "the user's part after the selftest, and every open document",
        {"after": after, "open": open_titles},
    )

    summary = report.read_text(encoding="utf-8")
    print(summary)
    assert code == EXIT_PASS, printed
    assert len(lines) == 4 and all(line.startswith("PASS") for line in lines)
    assert after == before
    assert open_titles == [before["title"]]
    assert "Cleanup:" not in printed
