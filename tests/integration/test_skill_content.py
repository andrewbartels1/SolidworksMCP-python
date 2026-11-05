"""The agent skill and the server instructions name only real tools (spec: agents/usage-skill).

Every backticked snake_case name in the skill files and the instructions must
be a registered tool, an input field of one, an ``error_type``, or one of the
response keys listed below. A tool renamed or removed therefore fails here,
naming the file. A tool that can't run yet (its description starts "Not
available yet") may be named only in ``references/errors-and-limits.md``,
which lists them as such; nowhere else may the skill send an agent to one.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastmcp import FastMCP

from solidworks_mcp.skills import SERVER_INSTRUCTIONS, SKILL_DIR, SKILL_NAME
from solidworks_mcp.tools import register_tools
from solidworks_mcp.tools.error_classifier import (
    DEFAULT_RULES,
    INTERNAL,
    INVALID_INPUT,
    NOT_SUPPORTED,
    OPERATION_FAILED,
)

_LIMITS_FILE = "references/errors-and-limits.md"
_NAME = re.compile(r"`([a-z][a-z0-9]*(?:_[a-z0-9]+)+)`")
#: Response keys the skill quotes; they are not input fields or tools.
_RESPONSE_KEYS = {
    "area_m2",
    "center_mm",
    "direction_flipped",
    "distance_m",
    "error_type",
    "length_m",
    "length_mm",
    "measured_change",
    "system_value",
    "usage_instructions",
    "vba_code",
}

_SKILL_FILES = sorted(
    p.relative_to(SKILL_DIR).as_posix() for p in SKILL_DIR.rglob("*.md")
)


def _field_names(schema: dict[str, Any]) -> set[str]:
    names: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            names.update(node.get("properties", {}))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    return names


@pytest.fixture(scope="module")
def tools_by_name() -> dict[str, Any]:
    import asyncio

    from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter

    async def collect() -> dict[str, Any]:
        mcp = FastMCP("skill-content")
        await register_tools(mcp, MockSolidWorksAdapter({}), {})
        return {t.name: t for t in await mcp.list_tools()}

    return asyncio.run(collect())


@pytest.fixture(scope="module")
def known_names(tools_by_name: dict[str, Any]) -> set[str]:
    fields: set[str] = set()
    for tool in tools_by_name.values():
        fields |= _field_names(tool.parameters or {})
    error_types = {rule.error_type for rule in DEFAULT_RULES} | {
        INTERNAL,
        INVALID_INPUT,
        NOT_SUPPORTED,
        OPERATION_FAILED,
    }
    return set(tools_by_name) | fields | error_types | _RESPONSE_KEYS


def _unknown(text: str, known: set[str]) -> list[str]:
    return sorted({n for n in _NAME.findall(text) if n not in known})


def test_the_skill_files_are_found() -> None:
    assert "SKILL.md" in _SKILL_FILES
    assert _LIMITS_FILE in _SKILL_FILES


@pytest.mark.parametrize("name", _SKILL_FILES)
def test_every_name_in_the_skill_is_real(name: str, known_names: set[str]) -> None:
    text = (SKILL_DIR / name).read_text(encoding="utf-8")

    assert _unknown(text, known_names) == [], name


def test_every_name_in_the_instructions_is_real(known_names: set[str]) -> None:
    assert _unknown(SERVER_INSTRUCTIONS, known_names) == []


@pytest.mark.parametrize("name", [n for n in _SKILL_FILES if n != _LIMITS_FILE])
def test_the_skill_sends_agents_only_to_tools_that_run(
    name: str, tools_by_name: dict[str, Any]
) -> None:
    unavailable = {
        tool_name
        for tool_name, tool in tools_by_name.items()
        if "Not available yet" in (tool.description or "")
    }
    text = (SKILL_DIR / name).read_text(encoding="utf-8")

    assert sorted(set(_NAME.findall(text)) & unavailable) == [], name


def test_the_instructions_send_agents_only_to_tools_that_run(
    tools_by_name: dict[str, Any],
) -> None:
    named = set(_NAME.findall(SERVER_INSTRUCTIONS))

    assert all(
        "Not available yet" not in (tools_by_name[n].description or "")
        for n in named & set(tools_by_name)
    )


def test_skill_md_has_frontmatter_and_stays_short() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    front = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)

    assert front is not None
    assert f"name: {SKILL_NAME}" in front.group(1)
    assert re.search(r"^description: \S.{40,}", front.group(1), re.MULTILINE)
    assert len(text.splitlines()) < 500


def test_the_instructions_stay_short() -> None:
    assert len(SERVER_INSTRUCTIONS) <= 1500


def test_the_unknown_name_check_reports_a_missing_tool() -> None:
    assert _unknown("Call `create_widget` then `create_part`.", {"create_part"}) == [
        "create_widget"
    ]
