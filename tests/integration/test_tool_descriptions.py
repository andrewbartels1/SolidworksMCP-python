"""Every registered tool's description follows the standard (spec: tools/tool-descriptions).

The standard is in ``docs/agents/tool-description-standard.md``. The checks
here are the mechanical part of it; usage guidance ("use it to ...", which
sibling to use instead) is reviewed in the PR.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from fastmcp import FastMCP

from solidworks_mcp.tools import register_tools
from solidworks_mcp.tools.tool_boundary import tool_family

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
    "server_admin",
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
@pytest.mark.parametrize("module", _MODULES)
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


#: Verbs a tool name starts with (the verb list, plus those of removed tools),
#: so a backticked ``analyze_geometry`` reads as a tool name and a backticked
#: ``volume_after`` (a reply field) does not. ``mirror`` and ``rebuild`` are
#: left out: ``mirror_line`` and ``rebuild_status`` are reply fields.
_TOOL_VERBS = (
    "add|analyze|apply|batch|check|close|compare|convert|create|delete|execute|"
    "export|extract|generate|get|insert|list|load|manage|measure|open|optimize|"
    "pattern|rename|save|select|set|sketch|suppress|validate|verify"
)
_TOOL_LIKE = re.compile(rf"`((?:{_TOOL_VERBS})_[a-z0-9_]+)`")


def unknown_tool_names(text: str, tools: set[str], fields: set[str]) -> list[str]:
    """Backticked tool-like names in ``text`` that are neither tools nor fields.

    Args:
        text: A tool description.
        tools: Registered tool names.
        fields: Every input field name of every tool.

    Returns:
        list[str]: The unknown names, in order of appearance.
    """
    return [n for n in _TOOL_LIKE.findall(text) if n not in tools | fields]


def _field_names(schema: Any) -> set[str]:
    """Every property name at any depth of a JSON schema."""
    names: set[str] = set()
    if isinstance(schema, dict):
        names.update(schema.get("properties", {}))
        for value in schema.values():
            names |= _field_names(value)
    elif isinstance(schema, list):
        for value in schema:
            names |= _field_names(value)
    return names


@pytest.mark.asyncio
async def test_no_description_names_a_tool_that_does_not_exist(mock_adapter) -> None:
    tools = await _tools(mock_adapter)
    names = {t.name for t in tools}
    fields = set().union(*(_field_names(t.parameters) for t in tools))

    unknown = {
        t.name: found
        for t in tools
        if (found := unknown_tool_names(t.description or "", names, fields))
    }

    assert unknown == {}, "descriptions name tools that are not registered"


def test_the_unknown_name_check_ignores_tools_and_fields() -> None:
    text = "Use `analyze_geometry`, then `get_model_info`; reads `set_value`."

    assert unknown_tool_names(text, {"get_model_info"}, {"set_value"}) == [
        "analyze_geometry"
    ]


_STANDARD = Path(__file__).resolve().parents[2] / (
    "docs/agents/tool-description-standard.md"
)


def _verbs_and_exceptions(text: str) -> tuple[tuple[str, ...], set[str]]:
    """The verb list and the named exceptions, read from the standard.

    Args:
        text: The standard's Markdown.

    Returns:
        tuple[tuple[str, ...], set[str]]: The verb prefixes (``create_``, ...)
        and the exception names.
    """
    section = text.split("## Tool names", 1)[1].split("\n## ", 1)[0]
    table, rest = section.split("<!-- tool-name-exceptions:start -->", 1)
    verbs = tuple(re.findall(r"`([a-z]+_)`", table))
    block = rest.split("<!-- tool-name-exceptions:end -->", 1)[0]
    return verbs, set(re.findall(r"`([a-z0-9_]+)`", block))


def naming_faults(
    names: set[str], verbs: tuple[str, ...], exceptions: set[str]
) -> list[str]:
    """Tool names that break the verb list, and exceptions that are no tool.

    Args:
        names: The registered tool names.
        verbs: The verb prefixes.
        exceptions: The names allowed to break the list.

    Returns:
        list[str]: One line per fault.
    """
    faults = [
        f"{name}: starts with none of {', '.join(verbs)}"
        for name in sorted(names - exceptions)
        if not name.startswith(verbs)
    ]
    faults += [
        f"{name}: listed as an exception but not registered"
        for name in sorted(exceptions - names)
    ]
    return faults


@pytest.mark.asyncio
async def test_every_tool_name_starts_with_a_listed_verb(mock_adapter) -> None:
    verbs, exceptions = _verbs_and_exceptions(_STANDARD.read_text(encoding="utf-8"))
    names = {t.name for t in await _tools(mock_adapter)}

    assert "create_" in verbs and "insert_component" in exceptions
    assert naming_faults(names, verbs, exceptions) == []


def test_an_unlisted_verb_fails_and_an_exception_passes() -> None:
    verbs = ("create_", "get_")

    assert naming_faults({"make_hole"}, verbs, set()) == [
        "make_hole: starts with none of create_, get_"
    ]
    assert naming_faults({"insert_component"}, verbs, {"insert_component"}) == []


def test_a_stale_exception_fails() -> None:
    assert naming_faults(set(), ("get_",), {"load_part"}) == [
        "load_part: listed as an exception but not registered"
    ]
