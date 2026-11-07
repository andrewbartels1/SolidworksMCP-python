"""The support-level table agrees with the code (spec: tools/support-levels).

"Stable" is checked by text: the tool's name, as a whole word, in a test
under ``tests/live/`` or in a ``scripts/demo_*.py`` file such a test loads.
Tools of the offline families never call SolidWorks and are exempt.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from fastmcp import FastMCP

from solidworks_mcp.tools import register_tools
from solidworks_mcp.tools.support_levels import (
    OFFLINE_FAMILIES,
    SUPPORT_LEVELS,
    SupportLevel,
)
from solidworks_mcp.tools.tool_boundary import tool_family

_ROOT = Path(__file__).resolve().parents[2]
_NOT_AVAILABLE = "Not available yet"


async def _tools(adapter: Any) -> list[Any]:
    mcp = FastMCP("levels")
    await register_tools(mcp, adapter, {})
    return list(await mcp.list_tools())


def _live_text() -> str:
    """Every live test, plus the demo scripts those tests load."""
    text = "\n".join(
        p.read_text(encoding="utf-8") for p in (_ROOT / "tests/live").glob("*.py")
    )
    demos = [
        p.read_text(encoding="utf-8")
        for p in (_ROOT / "scripts").glob("demo_*.py")
        if p.name in text
    ]
    return "\n".join([text, *demos])


@pytest.mark.asyncio
async def test_the_table_lists_exactly_the_registered_tools(mock_adapter) -> None:
    registered = {t.name for t in await _tools(mock_adapter)}

    assert sorted(set(SUPPORT_LEVELS) - registered) == [], "stale names in the table"
    assert sorted(registered - set(SUPPORT_LEVELS)) == [], "tools with no level"


@pytest.mark.asyncio
async def test_planned_means_not_available_yet(mock_adapter) -> None:
    wrong = sorted(
        t.name
        for t in await _tools(mock_adapter)
        if (_NOT_AVAILABLE in (t.description or ""))
        != (SUPPORT_LEVELS[t.name].level is SupportLevel.PLANNED)
    )

    assert wrong == [], f"level and '{_NOT_AVAILABLE}' disagree"


@pytest.mark.asyncio
async def test_a_stable_tool_has_a_live_test(mock_adapter) -> None:
    live = _live_text()
    unchecked = sorted(
        t.name
        for t in await _tools(mock_adapter)
        if SUPPORT_LEVELS[t.name].level is SupportLevel.STABLE
        and tool_family(t.fn) not in OFFLINE_FAMILIES
        and not re.search(rf"\b{t.name}\b", live)
    )

    assert unchecked == [], "stable, but no live test names it"


@pytest.mark.asyncio
async def test_a_description_opens_with_its_level(mock_adapter) -> None:
    wrong = []
    for tool in await _tools(mock_adapter):
        text = tool.description or ""
        warning = SUPPORT_LEVELS[tool.name].warning()
        if warning is not None and not text.startswith(warning):
            wrong.append(tool.name)
        if warning is None and text.startswith(("Beta:", "Experimental:")):
            wrong.append(tool.name)

    assert wrong == []


@pytest.mark.asyncio
async def test_every_tool_is_tagged_with_its_level(mock_adapter) -> None:
    wrong = sorted(
        t.name
        for t in await _tools(mock_adapter)
        if f"level:{SUPPORT_LEVELS[t.name].level.value}" not in t.tags
    )

    assert wrong == []
