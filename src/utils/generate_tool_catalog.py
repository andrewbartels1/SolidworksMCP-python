"""Generate a structured tool catalog from all registered MCP tool source files.

Parses every @mcp.tool() decorated function across the tools/ package,
extracts Pydantic input schemas, docstrings, and example payloads, then
writes per-category Markdown docs pages and a machine-readable JSON index.

Usage:
    python src/utils/generate_tool_catalog.py
    python src/utils/generate_tool_catalog.py --output-dir docs/user-guide/tool-catalog
    python src/utils/generate_tool_catalog.py --json-only
"""

from __future__ import annotations

import ast
import json
import sys
import textwrap
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Tool registry — built from AST, not runtime import, so no SolidWorks needed
# ---------------------------------------------------------------------------

CATEGORY_META: dict[str, dict[str, str]] = {
    "modeling": {
        "title": "Modeling Tools",
        "icon": ":material-cube-outline:",
        "description": (
            "Create and manipulate SolidWorks parts, assemblies, and drawings. "
            "These are the foundational tools for any CAD workflow — opening files, "
            "creating features (extrude, revolve), and querying/setting driven dimensions."
        ),
        "prerequisite": "An active SolidWorks session. Most feature tools require an open Part document.",
    },
    "sketching": {
        "title": "Sketching Tools",
        "icon": ":material-pencil:",
        "description": (
            "Build 2-D sketch geometry (lines, circles, arcs, splines, polygons) and "
            "apply geometric constraints and driven dimensions. Sketches are the "
            "prerequisite for every extrusion, revolve, sweep, and loft feature."
        ),
        "prerequisite": "An active part document with an active sketch edit session.",
    },
    "drawing": {
        "title": "Drawing Tools",
        "icon": ":material-technical-draw:",
        "description": (
            "Create and edit 2-D technical drawings: add projected/section/detail views, "
            "place dimensions, notes, and annotations, update title blocks and sheet "
            "formats, and run drafting standards checks."
        ),
        "prerequisite": "An active SolidWorks Drawing (.slddrw) document.",
    },
    "drawing_analysis": {
        "title": "Drawing Analysis Tools",
        "icon": ":material-magnify:",
        "description": (
            "Quality-gate your drawings. Analyse dimensions, annotations, view coverage, "
            "and GD&T compliance. Generate formal drawing reports and compare drawing "
            "revisions. Suitable for automated QA pipelines."
        ),
        "prerequisite": "An active Drawing document open in SolidWorks.",
    },
    "analysis": {
        "title": "Analysis Tools",
        "icon": ":material-chart-line:",
        "description": (
            "Extract engineering properties from models: mass, volume, centre of mass, "
            "moments of inertia, interference between solids, geometry curvature and "
            "thickness, and material properties. Essential for design validation."
        ),
        "prerequisite": "An active model (part or assembly) with solid geometry.",
    },
    "export": {
        "title": "Export Tools",
        "icon": ":material-export:",
        "description": (
            "Convert SolidWorks models to industry-standard interchange and "
            "manufacturing formats: STEP, IGES, STL, PDF, DWG, and raster images. "
            "Includes a batch-export tool for processing whole directories."
        ),
        "prerequisite": "An active document or a valid file path to an existing model.",
    },
    "file_management": {
        "title": "File Management Tools",
        "icon": ":material-folder-open:",
        "description": (
            "Open, save, and manage SolidWorks documents. Load parts and assemblies, "
            "save-as with new names or paths, manage custom file properties, and "
            "convert between file formats."
        ),
        "prerequisite": "SolidWorks running. File-write operations need writable output paths.",
    },
    "automation": {
        "title": "Automation Tools",
        "icon": ":material-cog:",
        "description": (
            "Orchestrate multi-step workflows, run batch file processing, manage design "
            "tables, generate VBA code on the fly, and tune SolidWorks performance "
            "settings. The glue that connects individual tool calls into repeatable pipelines."
        ),
        "prerequisite": "Varies by operation. Batch processing requires writable source/output directories.",
    },
    "vba_generation": {
        "title": "VBA Generation Tools",
        "icon": ":material-code-braces:",
        "description": (
            "Generate and execute VBA macro code for operations that exceed the COM "
            "direct-call parameter limit (typically > 12 params). Covers extrusions, "
            "revolves, assembly inserts, mates, drawing views, batch exports, file "
            "operations, and macro recording scaffolding."
        ),
        "prerequisite": "SolidWorks running. Generated VBA macros are executed via the COM runtime.",
    },
    "template_management": {
        "title": "Template Management Tools",
        "icon": ":material-file-document:",
        "description": (
            "Create, extract, apply, compare, and library-manage SolidWorks document "
            "templates (.prtdot, .asmdot, .drwdot) and sheet formats. Enables "
            "standardized document creation across teams and projects."
        ),
        "prerequisite": "Valid template file paths. Library operations require a configured template library path.",
    },
    "macro_recording": {
        "title": "Macro Recording Tools",
        "icon": ":material-record:",
        "description": (
            "Record, replay, analyse, and optimize SolidWorks VBA macros. Create macro "
            "libraries for reuse, batch-execute recorded macros, and profile performance "
            "hot-spots. Ideal for capturing manual workflows and converting them to "
            "automated, repeatable sequences."
        ),
        "prerequisite": "SolidWorks running. Macro execution requires a valid .swp file path.",
    },
    "docs_discovery": {
        "title": "Docs Discovery Tools",
        "icon": ":material-book-search:",
        "description": (
            "Introspect the live SolidWorks COM object library to discover available "
            "interfaces, methods, and properties for the installed version. Produces a "
            "JSON index that the integration harness uses to detect API-change drift "
            "between SolidWorks versions and suggest correct alternative tool calls."
        ),
        "prerequisite": "SolidWorks running. win32com.client must be available (Windows only).",
    },
}


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _first_paragraph(docstring: str) -> str:
    """Return the first paragraph of a docstring, stripped of indentation."""
    if not docstring:
        return ""
    lines = textwrap.dedent(docstring).strip().splitlines()
    para: list[str] = []
    for line in lines:
        if line.strip() == "" and para:
            break
        para.append(line.strip())
    return " ".join(para)


def _parse_pydantic_model(tree: ast.Module, class_name: str) -> list[dict[str, Any]]:
    """Extract field definitions from a Pydantic BaseModel class node."""
    fields: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.AnnAssign):
                continue
            field_name = getattr(stmt.target, "id", None)
            if field_name is None or field_name.startswith("_"):
                continue
            # Type annotation as source text
            type_str = ast.unparse(stmt.annotation)
            # Default / Field description
            description = ""
            default_val: Any = "required"
            if isinstance(stmt.value, ast.Call):
                func = stmt.value.func
                if (isinstance(func, ast.Attribute) and func.attr == "Field") or (
                    isinstance(func, ast.Name) and func.id == "Field"
                ):
                    for kw in stmt.value.keywords:
                        if kw.arg == "description":
                            description = (
                                ast.literal_eval(kw.value)
                                if isinstance(kw.value, ast.Constant)
                                else ast.unparse(kw.value)
                            )
                        elif kw.arg == "default":
                            try:
                                default_val = ast.literal_eval(kw.value)
                            except Exception:
                                default_val = ast.unparse(kw.value)
                    # If first positional arg is a default value
                    if stmt.value.args:
                        try:
                            default_val = ast.literal_eval(stmt.value.args[0])
                        except Exception:
                            default_val = ast.unparse(stmt.value.args[0])
            elif stmt.value is not None:
                try:
                    default_val = ast.literal_eval(stmt.value)
                except Exception:
                    default_val = ast.unparse(stmt.value)

            fields.append(
                {
                    "name": field_name,
                    "type": _simplify_type(type_str),
                    "description": description,
                    "default": default_val,
                    "required": default_val == "required",
                }
            )
    return fields


def _simplify_type(t: str) -> str:
    return (
        t.replace("list[", "List[")
        .replace("dict[", "Dict[")
        .replace(" | None", "?")
        .replace("| None", "?")
    )


def _find_tool_input_class(tree: ast.Module, func_name: str) -> str | None:
    """Return the Pydantic model class name used as the first parameter of a tool function."""
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == func_name
        ):
            args = node.args.args
            if len(args) >= 1:
                arg = args[0]
                if arg.annotation and isinstance(arg.annotation, ast.Name):
                    return arg.annotation.id
    return None


def _get_tool_docstring(tree: ast.Module, func_name: str) -> str:
    """Extract docstring from an inner function (possibly nested in register_* fn)."""
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == func_name
        ):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
            ):
                return node.body[0].value.value
    return ""


def _is_tool_func(node: ast.AST) -> bool:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    for dec in node.decorator_list:
        if isinstance(dec, ast.Attribute) and dec.attr == "tool":
            return True
        if isinstance(dec, ast.Name) and dec.id == "tool":
            return True
        if isinstance(dec, ast.Call):
            func = dec.func
            if (isinstance(func, ast.Attribute) and func.attr == "tool") or (
                isinstance(func, ast.Name) and func.id == "tool"
            ):
                return True
    return False


def _extract_tool_name_from_decorator(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str:
    """Return explicit name= from @mcp.tool(name=...) or fall back to function name."""
    for dec in node.decorator_list:
        if isinstance(dec, ast.Call):
            for kw in dec.keywords:
                if kw.arg == "name":
                    try:
                        return ast.literal_eval(kw.value)
                    except Exception:
                        pass
    return node.name


# ---------------------------------------------------------------------------
# Catalog builder
# ---------------------------------------------------------------------------


def _make_sample_payload(fields: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate a plausible sample call payload from Pydantic field definitions."""
    sample: dict[str, Any] = {}
    synthetic: dict[str, Any] = {
        "file_path": "C:\\Temp\\mcp_demo\\part.sldprt",
        "output_path": "C:\\Temp\\mcp_demo\\export.step",
        "name": "MCP_Demo_Part",
        "plane": "Front",
        "sketch_name": "Sketch1",
        "depth": 25.0,
        "angle": 360.0,
        "axis_entity": "Line1",
        "x1": -30.0,
        "y1": -20.0,
        "x2": 30.0,
        "y2": 20.0,
        "center_x": 0.0,
        "center_y": 0.0,
        "radius": 15.0,
        "source_directory": "C:\\Temp\\mcp_demo",
        "output_directory": "C:\\Temp\\mcp_demo\\exports",
        "format_type": "step",
        "analysis_type": "curvature",
        "dimension_name": "D1@Sketch1",
        "value": 50.0,
        "dimension": "D1@Sketch1",
        "units": "mm",
        "components": [],
        "profiles": ["Sketch1", "Sketch2"],
        "points": [
            {"x": 0.0, "y": 0.0},
            {"x": 10.0, "y": 15.0},
            {"x": 20.0, "y": 10.0},
        ],
        "entity1": "Line1",
        "relation_type": "perpendicular",
        "dimension_type": "linear",
        "start_x": -30.0,
        "start_y": 0.0,
        "end_x": 30.0,
        "end_y": 0.0,
        "diameter": 10.0,
        "query": "",
        "output_dir": "C:\\Temp\\mcp_demo\\docs-index",
        "template": None,
        "model_path": None,
    }
    for f in fields:
        if f["required"]:
            name = f["name"]
            if name in synthetic:
                sample[name] = synthetic[name]
            elif "path" in name:
                sample[name] = "C:\\Temp\\mcp_demo\\file.sldprt"
            elif "name" in name:
                sample[name] = "MCP_Demo_Part"
            elif f["type"].startswith("float") or f["type"].startswith("int"):
                sample[name] = 10.0
            elif f["type"].startswith("bool"):
                sample[name] = False
            elif f["type"].startswith("str"):
                sample[name] = "example"
            elif f["type"].startswith("List"):
                sample[name] = []
            elif f["type"].startswith("Dict"):
                sample[name] = {}
            else:
                sample[name] = None
    return sample


PREREQUISITES: dict[str, str] = {
    "open_model": "SolidWorks running",
    "create_part": "SolidWorks running",
    "create_assembly": "SolidWorks running",
    "create_drawing": "SolidWorks running",
    "close_model": "An active open document",
    "create_extrusion": "Active part with an active sketch (exit sketch first with exit_sketch)",
    "create_revolve": "Active part with an active sketch containing the profile and axis",
    "get_dimension": "Active document with named dimensions",
    "set_dimension": "Active document with named dimensions",
    "create_sketch": "Active part document, no active sketch",
    "exit_sketch": "Active sketch edit mode",
    "add_line": "Active sketch edit mode",
    "add_circle": "Active sketch edit mode",
    "add_rectangle": "Active sketch edit mode",
    "add_arc": "Active sketch edit mode",
    "add_spline": "Active sketch edit mode",
    "add_centerline": "Active sketch edit mode",
    "add_polygon": "Active sketch edit mode",
    "add_ellipse": "Active sketch edit mode",
    "add_sketch_constraint": "Active sketch edit mode with named entities",
    "add_sketch_dimension": "Active sketch edit mode",
    "sketch_linear_pattern": "Active sketch edit mode",
    "sketch_circular_pattern": "Active sketch edit mode",
    "sketch_mirror": "Active sketch edit mode",
    "sketch_offset": "Active sketch edit mode",
    "calculate_mass_properties": "Active model with solid geometry",
    "get_mass_properties": "Active model with solid geometry",
    "check_interference": "Active assembly",
    "analyze_geometry": "Active model with geometry",
    "get_material_properties": "Active part with assigned material",
    "export_step": "Active or specified model document",
    "export_iges": "Active or specified model document",
    "export_stl": "Active or specified model document",
    "export_pdf": "Active or specified drawing document",
    "export_dwg": "Active or specified drawing document",
    "export_image": "Active document",
    "batch_export": "Writable source and output directories",
    "save_file": "Active open document",
    "save_as": "Active open document, writable output path",
    "get_file_properties": "Active document",
    "manage_file_properties": "Active document",
    "convert_file_format": "Valid source file path",
    "batch_file_operations": "Writable directories",
    "load_part": "SolidWorks running, valid .sldprt path",
    "load_assembly": "SolidWorks running, valid .sldasm path",
    "save_part": "Active Part document",
    "save_assembly": "Active Assembly document",
    "discover_solidworks_docs": "SolidWorks running, win32com available (Windows only)",
}


def build_catalog(tools_dir: Path) -> list[dict[str, Any]]:
    """Parse all tool source files and return a structured catalog."""
    catalog: list[dict[str, Any]] = []

    for py_file in sorted(tools_dir.glob("*.py")):
        if py_file.name in ("__init__.py", "input_compat.py"):
            continue

        category = py_file.stem
        try:
            with open(py_file, encoding="utf-8") as fh:
                source = fh.read()
            tree = ast.parse(source)
        except Exception as exc:
            print(f"  [WARN] Could not parse {py_file.name}: {exc}")
            continue

        # Walk the entire tree to find @mcp.tool() decorated functions
        # (they live inside register_*_tools nested scope)
        for node in ast.walk(tree):
            if not _is_tool_func(node):
                continue

            tool_name = _extract_tool_name_from_decorator(node)
            func_name = node.name
            docstring = _get_tool_docstring(tree, func_name)
            description = _first_paragraph(docstring)
            input_class = _find_tool_input_class(tree, func_name)
            fields: list[dict[str, Any]] = []
            if input_class:
                fields = _parse_pydantic_model(tree, input_class)
            sample = _make_sample_payload(fields)

            catalog.append(
                {
                    "tool_name": tool_name,
                    "func_name": func_name,
                    "category": category,
                    "input_class": input_class,
                    "description": description,
                    "fields": fields,
                    "sample_payload": sample,
                    "prerequisite": PREREQUISITES.get(
                        func_name, PREREQUISITES.get(tool_name, "SolidWorks running")
                    ),
                }
            )

    return catalog


# ---------------------------------------------------------------------------
# Markdown generators
# ---------------------------------------------------------------------------

_PARAM_TABLE_HEADER = "| Parameter | Type | Required | Default | Description |\n|-----------|------|----------|---------|-------------|"


def _render_param_row(f: dict[str, Any]) -> str:
    req = "✅" if f["required"] else "—"
    default = "" if f["required"] else str(f["default"])
    return (
        f"| `{f['name']}` | `{f['type']}` | {req} | `{default}` | {f['description']} |"
    )


def _render_tool_section(tool: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"### `{tool['tool_name']}`\n")
    if tool["description"]:
        lines.append(tool["description"])
        lines.append("")
    lines.append(f"**Prerequisite:** {tool['prerequisite']}\n")

    if tool["fields"]:
        lines.append("**Parameters:**\n")
        lines.append(_PARAM_TABLE_HEADER)
        for f in tool["fields"]:
            lines.append(_render_param_row(f))
        lines.append("")

    # Sample call
    if tool["sample_payload"] is not None:
        sample_json = json.dumps(tool["sample_payload"], indent=2)
        lines.append("**Sample call:**\n")
        lines.append("```json")
        lines.append(sample_json)
        lines.append("```\n")
    else:
        lines.append("**Sample call:** *(no required parameters — call with `{}`)*\n")

    return "\n".join(lines)


def generate_category_page(
    category: str,
    tools: list[dict[str, Any]],
    meta: dict[str, str],
) -> str:
    """Generate a full Markdown page for one tool category."""
    lines: list[str] = []
    lines.append(f"# {meta['title']}\n")
    lines.append(meta["description"])
    lines.append("")
    lines.append(f"> **Prerequisite:** {meta['prerequisite']}\n")
    lines.append(f"**Total tools in this category: {len(tools)}**\n")

    lines.append("---\n")

    for tool in tools:
        lines.append(_render_tool_section(tool))
        lines.append("---\n")

    return "\n".join(lines)


def generate_index_page(catalog: list[dict[str, Any]]) -> str:
    """Generate the top-level tool catalog index page."""
    from collections import Counter

    counts = Counter(t["category"] for t in catalog)
    total = len(catalog)

    lines: list[str] = [
        "# Tool Catalog — All 101 Tools\n",
        f"This reference documents all **{total} MCP tools** registered by the SolidWorks MCP server.",
        "Each section covers one functional category with parameter tables and copy-paste sample calls.\n",
        "## Quick Navigation\n",
        "| Category | Count | Description |",
        "|----------|-------|-------------|",
    ]

    for cat, meta in CATEGORY_META.items():
        count = counts.get(cat, 0)
        slug = cat.replace("_", "-")
        lines.append(
            f"| [{meta['title']}]({slug}.md) | {count} | {meta['description'][:80]}… |"
        )

    lines += [
        "",
        "## Standard Response Envelope\n",
        "Every tool returns a dictionary with at least:\n",
        "```json",
        "{",
        '  "status": "success" | "error",',
        '  "message": "Human-readable description",',
        '  "data": { ... },',
        '  "execution_time": 0.123',
        "}",
        "```\n",
        "On error, `data` is omitted and `message` contains the failure reason.\n",
        "## Calling Tools from an LLM\n",
        "Pass parameters as a JSON object.  Only **required** fields (marked ✅) must be included.",
        "All others default to sensible values.\n",
        "```text",
        "Goal: calculate mass of the open model",
        "",
        "Tool: calculate_mass_properties",
        "Payload: {}",
        "```\n",
        "```text",
        "Goal: export active part to STEP",
        "",
        "Tool: export_step",
        "Payload:",
        '{  "file_path": "C:\\\\Temp\\\\part.step" }',
        "```",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    args = argv or sys.argv[1:]
    output_dir = Path("docs/user-guide/tool-catalog")
    json_only = False
    json_path = Path("tests/.generated/tool_catalog.json")

    i = 0
    while i < len(args):
        if args[i] == "--output-dir" and i + 1 < len(args):
            output_dir = Path(args[i + 1])
            i += 2
        elif args[i] == "--json-only":
            json_only = True
            i += 1
        elif args[i] == "--json-path" and i + 1 < len(args):
            json_path = Path(args[i + 1])
            i += 2
        else:
            i += 1

    project_root = Path(__file__).resolve().parents[2]
    tools_dir = project_root / "src" / "solidworks_mcp" / "tools"

    print(f"Parsing tool source files in: {tools_dir}")
    catalog = build_catalog(tools_dir)
    print(f"Found {len(catalog)} tools\n")

    # Always write JSON
    json_out_path = project_root / json_path
    json_out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_out_path, "w", encoding="utf-8") as fh:
        json.dump(catalog, fh, indent=2)
    print(f"JSON catalog -> {json_out_path}")

    if json_only:
        return

    # Write Markdown pages
    abs_output = project_root / output_dir
    abs_output.mkdir(parents=True, exist_ok=True)

    # Group by category
    cat_tools: dict[str, list[dict[str, Any]]] = {}
    for tool in catalog:
        cat_tools.setdefault(tool["category"], []).append(tool)

    # Index page
    index_md = generate_index_page(catalog)
    (abs_output / "index.md").write_text(index_md, encoding="utf-8")
    print(f"  wrote index.md ({len(catalog)} tools)")

    # Per-category pages
    for category, tools in sorted(cat_tools.items()):
        meta = CATEGORY_META.get(
            category,
            {
                "title": category.replace("_", " ").title() + " Tools",
                "icon": ":material-tools:",
                "description": f"Tools in the {category} category.",
                "prerequisite": "SolidWorks running",
            },
        )
        slug = category.replace("_", "-")
        page_md = generate_category_page(category, tools, meta)
        out_file = abs_output / f"{slug}.md"
        out_file.write_text(page_md, encoding="utf-8")
        print(f"  wrote {slug}.md ({len(tools)} tools)")

    print(f"\nCatalog written to: {abs_output}")
    print("   Add 'tool-catalog/index.md' to mkdocs.yml nav to publish.")


if __name__ == "__main__":
    main()
