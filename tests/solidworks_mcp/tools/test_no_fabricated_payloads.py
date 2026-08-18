"""Guard against tools inventing their answers.

Several tools used to return confident, plausible, entirely fabricated payloads:
a 92% drafting-standards compliance score for a drawing they never opened, a
similarity percentage for templates they never read, a catalogue of templates
nobody had registered. Nothing errored, so nothing looked wrong.

These tests pin the two properties that matter:

1. Tools that cannot do the job report an error rather than a success-shaped
   invention.
2. Every registered tool either reaches the adapter or is one of the handful
   that legitimately never needs it.
"""

import ast
import pathlib

import pytest
from fastmcp import FastMCP

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.tools.drawing import (
    CreateDetailViewInput,
    CreateSectionViewInput,
    register_drawing_tools,
)

TOOLS_DIR = pathlib.Path(__file__).resolve().parents[3] / "src" / "solidworks_mcp" / "tools"

#: Tools that legitimately never touch SolidWorks: they generate VBA text,
#: search local documentation, delegate to a sibling tool, or compare files on
#: disk. Anything NOT on this list that skips the adapter is fabricating.
ADAPTER_FREE_TOOLS = {
    "get_mass_properties",  # delegates to calculate_mass_properties
    "stop_macro_recording",
    "discover_solidworks_docs",
    "search_solidworks_api_help",
    "generate_vba_part_modeling",
    "generate_vba_assembly_mates",
    "generate_vba_drawing_dimensions",
    "generate_vba_file_operations",
    "generate_vba_macro_recorder",
    # Same deal: these build the macro text from their inputs. The VBA is real
    # output, not a stand-in for work SolidWorks was supposed to do.
    "generate_vba_assembly_insert",
    "generate_vba_batch_export",
    "generate_vba_drawing_views",
    "generate_vba_code",  # emits a labelled skeleton and says so
    # These refuse honestly instead of inventing a result.
    "create_section_view",
    "create_detail_view",
    "check_drawing_standards",
    "execute_workflow",
    "manage_design_table",
    "optimize_performance",
    "analyze_macro",
    "batch_execute_macros",
    "optimize_macro",
    "create_macro_library",
    "apply_template",
    "batch_apply_template",
    # File-level work that needs no SolidWorks session: comparisons read the
    # files, and the template tools copy a model to a template file.
    "compare_drawing_versions",
    "compare_templates",
    "create_template",
    "extract_template",
    # The template library is a JSON file on disk: these read and write it, and
    # stat the referenced template files. No SolidWorks session involved.
    "list_template_library",
    "save_to_template_library",
    # Returns the CAD-generation skill-route contract for a family the caller
    # already decided on. Pure introspection of the SolidWorksAdapter class
    # itself (its public method names) - never needs a live adapter instance,
    # and never claims to have done any SolidWorks work.
    "get_skill_route",
}


def _tools_without_adapter() -> set[str]:
    """Return the names of @mcp.tool functions that never reference `adapter`."""
    offenders: set[str] = set()
    for path in sorted(TOOLS_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            decorated = any(
                isinstance(d, ast.Call)
                and isinstance(d.func, ast.Attribute)
                and d.func.attr == "tool"
                for d in node.decorator_list
            )
            if not decorated:
                continue
            segment = ast.get_source_segment(source, node) or ""
            if "adapter." not in segment:
                offenders.add(node.name)
    return offenders


def test_no_new_tools_fabricate_their_answer() -> None:
    """Every tool either uses the adapter or is a known adapter-free tool."""
    offenders = _tools_without_adapter() - ADAPTER_FREE_TOOLS
    assert not offenders, (
        "These tools never reach the adapter, so they cannot be returning real "
        f"data: {sorted(offenders)}. Either wire them to the adapter or make "
        "them report an error."
    )


def _statement_lists(node: ast.AST) -> list[list[ast.stmt]]:
    """Every list-of-statements anywhere beneath `node`.

    The fabricating fallbacks live inside the tool's `try:` block, not directly
    in the function body, so scanning `fn.body` alone finds nothing.
    """
    lists: list[list[ast.stmt]] = []
    for child in ast.walk(node):
        for _field, value in ast.iter_fields(child):
            if (
                isinstance(value, list)
                and value
                and all(isinstance(item, ast.stmt) for item in value)
            ):
                lists.append(value)
    return lists


def _tools_with_fabricated_fallback() -> set[str]:
    """Return tools whose no-adapter-support branch invents a success payload.

    The shape this catches:

        if hasattr(adapter, "do_thing"):
            result = await adapter.do_thing(...)   # real path
            ...
        return {"status": "success", "data": {...literals...}}

    The tool mentions `adapter.` on the real path, so
    `_tools_without_adapter` is satisfied while the fallback still lies. A
    fallback that reaches `adapter` again (export_step falls back to
    `adapter.export_file`) or that reads `result` is doing real work and is
    not flagged.
    """
    offenders: set[str] = set()
    for path in sorted(TOOLS_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            decorated = any(
                isinstance(d, ast.Call)
                and isinstance(d.func, ast.Attribute)
                and d.func.attr == "tool"
                for d in node.decorator_list
            )
            if not decorated:
                continue
            for statements in _statement_lists(node):
                for index, statement in enumerate(statements):
                    if not isinstance(statement, ast.If):
                        continue
                    test = ast.get_source_segment(source, statement.test) or ""
                    if "hasattr(adapter" not in test:
                        continue
                    fallback = list(statement.orelse) + list(statements[index + 1 :])
                    text = " ".join(
                        (ast.get_source_segment(source, s) or "") for s in fallback
                    )
                    if '"status": "success"' not in text:
                        continue
                    if "adapter." in text or "result" in text:
                        continue
                    # Qualified by file: two modules define start_macro_recording
                    # and only one of them fabricates.
                    offenders.add(f"{path.name}::{node.name}")
    return offenders


def test_no_tool_invents_a_payload_when_the_adapter_cannot_help() -> None:
    """A tool with no adapter support must refuse, not improvise.

    `test_no_new_tools_fabricate_their_answer` only asks whether a tool
    mentions the adapter at all. That let 25 tools through which call the
    adapter on the happy path and then fabricate when the capability is
    missing — including `save_file` reporting "File saved successfully" with a
    fresh timestamp for a save that never happened.
    """
    offenders = {
        qualified
        for qualified in _tools_with_fabricated_fallback()
        if qualified.split("::", 1)[1] not in ADAPTER_FREE_TOOLS
    }
    assert not offenders, (
        "These tools invent a success payload when the adapter cannot do the "
        f"job: {sorted(offenders)}. Return an error naming the missing "
        "capability, or add the tool to ADAPTER_FREE_TOOLS if it genuinely "
        "needs no SolidWorks session."
    )


def _tools_returning_success_before_touching_the_adapter() -> set[str]:
    """Return tools whose first success payload precedes any adapter use.

    Both checks above reason about the *fallback* after a
    ``hasattr(adapter, ...)`` gate, so neither sees a success payload returned
    before the tool ever consults the adapter. That gap is real: injecting an
    unconditional ``{"status": "success", "compliance_score": 92}`` at the top
    of ``check_drawing_compliance`` left all of the other checks passing.
    """
    offenders: set[str] = set()
    for path in sorted(TOOLS_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for fn in ast.walk(ast.parse(source)):
            if not isinstance(fn, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            if not any(
                isinstance(d, ast.Call)
                and isinstance(d.func, ast.Attribute)
                and d.func.attr == "tool"
                for d in fn.decorator_list
            ):
                continue
            if fn.name in ADAPTER_FREE_TOOLS:
                continue

            # First line that reads something off the adapter.
            adapter_lines = [
                node.lineno
                for node in ast.walk(fn)
                if isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "adapter"
            ]
            if not adapter_lines:
                # Covered by test_no_new_tools_fabricate_their_answer.
                continue
            first_adapter_use = min(adapter_lines)

            for node in ast.walk(fn):
                if not isinstance(node, ast.Return) or node.value is None:
                    continue
                if node.lineno >= first_adapter_use:
                    continue
                segment = ast.get_source_segment(source, node) or ""
                if '"status": "success"' in segment:
                    offenders.add(f"{path.name}::{fn.name}")
    return offenders


def test_no_tool_reports_success_before_consulting_the_adapter() -> None:
    """An adapter-backed tool cannot know it succeeded before it has asked.

    Closes the blind spot the other two checks share: they analyse what happens
    after a ``hasattr(adapter, ...)`` gate, so an unconditional success return
    placed above that gate sails straight past them.
    """
    offenders = _tools_returning_success_before_touching_the_adapter()
    assert not offenders, (
        "These tools return a success payload before they ever read anything "
        f"from the adapter, so the payload cannot be real: {sorted(offenders)}."
    )


def test_no_simulation_markers_left_in_tools() -> None:
    """No tool still advertises that it is faking its result."""
    # "# Simulate " (imperative) slipped past an earlier version of this check
    # that only looked for "# For now, simulate" — five automation tools were
    # still inventing their entire answer behind it.
    markers = (
        "# For now, simulate",
        "# Simulate ",
        "# Simulated",
        "# Would be actual",
    )
    found: list[str] = []
    for path in sorted(TOOLS_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker in text:
                found.append(f"{path.name}: {marker}")
    assert not found, f"Simulation markers left behind: {found}"


@pytest.mark.asyncio
async def test_standards_check_refuses_instead_of_scoring() -> None:
    """check_drawing_standards must not invent a compliance score."""
    mcp = FastMCP("test")
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await register_drawing_tools(mcp, adapter, {})

    tools = {tool.name: tool.fn for tool in await mcp.list_tools()}
    result = await tools["check_drawing_standards"](input_data={})

    assert result["status"] == "error"
    assert "compliance_score" not in str(result)


@pytest.mark.asyncio
async def test_section_and_detail_views_refuse_clearly() -> None:
    """The view tools that cannot work explain why rather than pretending."""
    mcp = FastMCP("test")
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await register_drawing_tools(mcp, adapter, {})

    tools = {tool.name: tool.fn for tool in await mcp.list_tools()}

    section = await tools["create_section_view"](
        input_data=CreateSectionViewInput(
            section_line_start=[0.0, 0.0],
            section_line_end=[10.0, 0.0],
            view_position_x=100.0,
            view_position_y=100.0,
        )
    )
    assert section["status"] == "error"
    assert "section line" in section["message"].lower()

    detail = await tools["create_detail_view"](
        input_data=CreateDetailViewInput(
            center_x=0.0,
            center_y=0.0,
            radius=10.0,
            view_position_x=100.0,
            view_position_y=100.0,
        )
    )
    assert detail["status"] == "error"
    assert "detail circle" in detail["message"].lower()
