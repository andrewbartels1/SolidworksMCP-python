"""What each tool needs from SolidWorks (spec: tools/tool-requirements)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from solidworks_mcp.progress.tool_list_size import listed_tools
from solidworks_mcp.tools.requirements import (
    REQUIREMENTS,
    Requirement,
    requirement_of,
)

OVERVIEW = (
    Path(__file__).resolve().parents[3] / "docs" / "user-guide" / "tools-overview.md"
)

#: The overview's sub-heading for each requirement it lists.
_HEADINGS = {
    Requirement.NOTHING: "### Needs nothing",
    Requirement.INSTALLED: "### Needs SolidWorks installed, not running",
}


@pytest.fixture(scope="module")
def tools() -> dict[str, Any]:
    """Every registered tool, by name."""
    import asyncio

    return {t.name: t for t in asyncio.run(listed_tools(("all",), "list"))}


def test_an_unlisted_tool_needs_solidworks_running() -> None:
    assert requirement_of("create_extrusion") is Requirement.RUNNING


def test_a_listed_tool_has_its_requirement() -> None:
    assert requirement_of("lookup_api_method") is Requirement.INSTALLED
    assert requirement_of("x", {"x": Requirement.NOTHING}) is Requirement.NOTHING


def test_the_table_lists_only_tools_that_dont_need_solidworks_running() -> None:
    assert Requirement.RUNNING not in REQUIREMENTS.values()


def test_every_listed_tool_is_registered(tools: dict[str, Any]) -> None:
    assert sorted(set(REQUIREMENTS) - set(tools)) == []


def test_each_tool_has_one_needs_tag(tools: dict[str, Any]) -> None:
    for name, tool in tools.items():
        needs = [t for t in tool.meta["fastmcp"]["tags"] if t.startswith("needs:")]
        assert needs == [f"needs:{requirement_of(name).value}"], name


def test_an_installed_tool_says_solidworks_need_not_run(tools: dict[str, Any]) -> None:
    for name, requirement in REQUIREMENTS.items():
        if requirement is Requirement.INSTALLED:
            assert re.search(
                r"not running|without SolidWorks running", tools[name].description
            ), name


def _overview_lists() -> dict[Requirement, set[str]]:
    """The tool names the overview lists under each requirement's heading."""
    text = OVERVIEW.read_text(encoding="utf-8")
    section = text.split("## What each tool needs from SolidWorks", 1)[1]
    section = section.split("\n## ", 1)[0]
    found: dict[Requirement, set[str]] = {}
    for requirement, heading in _HEADINGS.items():
        body = section.split(heading, 1)[1].split("\n### ", 1)[0]
        found[requirement] = set(re.findall(r"`([a-z_]+)`", body))
    return found


def test_the_overview_lists_the_table() -> None:
    listed = _overview_lists()
    for requirement in _HEADINGS:
        expected = {n for n, r in REQUIREMENTS.items() if r is requirement}
        assert listed[requirement] == expected, requirement
