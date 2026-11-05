"""Every registered tool's description follows the standard (spec: tools/tool-descriptions).

The standard is in ``docs/agents/tool-description-standard.md``. The checks
here are the mechanical part of it; usage guidance ("use it to ...", which
sibling to use instead) is reviewed in the PR.

Description checks are switched on module by module, as each module's tools
are rewritten: a module not yet in ``_REWRITTEN`` is expected to fail, and
strictly so, so finishing a module without switching it on fails too. The
input-field check is on for every module.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastmcp import FastMCP

from solidworks_mcp.tools import register_tools
from solidworks_mcp.tools.tool_boundary import tool_family

#: The modules whose descriptions have been rewritten to the standard.
_REWRITTEN: set[str] = {
    "automation",
    "docs_discovery",
    "drawing",
    "drawing_analysis",
    "drawing_automation",
    "export",
    "file_management",
    "macro_recording",
    "template_management",
    "vba_generation",
}

_MODULES = [
    "analysis",
    "automation",
    "docs_discovery",
    "drawing",
    "drawing_analysis",
    "drawing_automation",
    "engineering_data",
    "export",
    "file_management",
    "macro_recording",
    "modeling",
    "sketching",
    "template_management",
    "vba_generation",
]

_MIN_CHARS, _MAX_CHARS = 120, 1200
_GENERIC_INPUT = re.compile(r"^\s*$|input data value", re.IGNORECASE)
# A Google-style section header alone on its line ("Returns:"), as a leftover
# docstring section shows; a "Returns: ..." sentence is part of the standard.
_LEAKED_SECTION = re.compile(r"^\s*(Args|Returns|Raises|Examples?):\s*$", re.MULTILINE)


async def _tools(adapter: Any) -> list[Any]:
    mcp = FastMCP("descriptions")
    await register_tools(mcp, adapter, {})
    return list(await mcp.list_tools())


def description_faults(tool: Any) -> list[str]:
    """What breaks the standard in one tool's description and input text.

    Args:
        tool: A registered FastMCP tool.

    Returns:
        list[str]: One line per fault; empty when the tool is compliant.
    """
    faults = []
    text = tool.description or ""
    if text.startswith("Handle "):
        faults.append("restates its name ('Handle ...')")
    if not _MIN_CHARS <= len(text) <= _MAX_CHARS:
        faults.append(f"{len(text)} characters, not {_MIN_CHARS}-{_MAX_CHARS}")
    if "Read-only." not in text and "Changes:" not in text:
        faults.append("says neither 'Read-only.' nor 'Changes: ...'")
    if _LEAKED_SECTION.search(text):
        faults.append("docstring Args/Returns/Example text in the description")
    input_data = (tool.parameters or {}).get("properties", {}).get("input_data")
    if input_data is not None and _GENERIC_INPUT.search(
        input_data.get("description", "")
    ):
        faults.append("input_data has a generic description")
    return faults


def undescribed_fields(tool: Any) -> list[str]:
    """Input fields, at any depth, that have no description.

    Args:
        tool: A registered FastMCP tool.

    Returns:
        list[str]: Dotted paths of the undescribed fields.
    """
    schema = tool.parameters or {}
    defs = schema.get("$defs", {})
    missing: list[str] = []

    def resolve(node: dict[str, Any]) -> dict[str, Any]:
        ref = node.get("$ref")
        return defs.get(ref.rsplit("/", 1)[-1], {}) if ref else node

    def walk(node: dict[str, Any], path: str, seen: frozenset[str]) -> None:
        ref = node.get("$ref", "")
        if ref in seen:
            return
        body = resolve(node)
        for key, prop in body.get("properties", {}).items():
            field = f"{path}.{key}" if path else key
            if not (prop.get("description") or resolve(prop).get("description")):
                missing.append(field)
            walk(prop, field, seen | {ref})

    for name, prop in schema.get("properties", {}).items():
        if name == "input_data":
            walk(prop, "input_data", frozenset())
    return missing


def _report(faults: dict[str, list[str]]) -> str:
    return "\n".join(
        f"{name}: {'; '.join(found)}" for name, found in sorted(faults.items())
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "module",
    [
        module
        if module in _REWRITTEN
        else pytest.param(
            module,
            marks=pytest.mark.xfail(strict=True, reason="not yet rewritten"),
        )
        for module in _MODULES
    ],
)
async def test_descriptions_follow_the_standard(module: str, mock_adapter) -> None:
    tools = [t for t in await _tools(mock_adapter) if tool_family(t.fn) == module]
    assert tools, f"no tools registered from {module}"

    faults = {t.name: f for t in tools if (f := description_faults(t))}

    assert not faults, f"\n{_report(faults)}"


@pytest.mark.asyncio
async def test_every_input_field_is_described(mock_adapter) -> None:
    faults = {
        t.name: m for t in await _tools(mock_adapter) if (m := undescribed_fields(t))
    }

    assert not faults, f"\n{_report(faults)}"


@pytest.mark.asyncio
async def test_every_module_is_listed(mock_adapter) -> None:
    families = {tool_family(t.fn) for t in await _tools(mock_adapter)}

    assert families == set(_MODULES)


class _Tool:
    """A stand-in tool for checking the checks themselves."""

    def __init__(self, description: str, parameters: dict[str, Any]) -> None:
        self.name = "fake"
        self.description = description
        self.parameters = parameters


def test_the_check_names_each_fault() -> None:
    tool = _Tool(
        "Handle new thing.\n\nArgs:\n    x: y",
        {"properties": {"input_data": {"description": "The input data value."}}},
    )

    faults = description_faults(tool)

    assert faults == [
        "restates its name ('Handle ...')",
        f"{len(tool.description)} characters, not 120-1200",
        "says neither 'Read-only.' nor 'Changes: ...'",
        "docstring Args/Returns/Example text in the description",
        "input_data has a generic description",
    ]


def test_a_compliant_description_has_no_faults() -> None:
    text = (
        "List the features in the active part's tree, in order. Use it to "
        "find a feature's name before editing it. Needs: an open part. "
        "Read-only. Returns: name and type of each feature."
    )
    tool = _Tool(
        text, {"properties": {"input_data": {"description": "Which document to read."}}}
    )

    assert description_faults(tool) == []


def test_the_field_check_follows_refs_and_nesting() -> None:
    tool = _Tool(
        "",
        {
            "properties": {
                "input_data": {"$ref": "#/$defs/Outer", "description": "Outer."}
            },
            "$defs": {
                "Outer": {
                    "properties": {
                        "inner": {"$ref": "#/$defs/Inner"},
                        "ok": {"description": "Fine."},
                    }
                },
                "Inner": {
                    "description": "Inner model.",
                    "properties": {
                        "bare": {"type": "string"},
                        "loop": {"$ref": "#/$defs/Inner"},
                    },
                },
            },
        },
    )

    assert undescribed_fields(tool) == ["input_data.inner.bare"]
