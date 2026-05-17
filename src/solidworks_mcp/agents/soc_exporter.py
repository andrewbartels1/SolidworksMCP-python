"""SolidWorks-as-Code exporter.

Reads ToolCallRecord rows from SQLite for a session and emits a clean,
runnable Python script that mirrors the structure of build_u_bracket_artifact.py.

Usage::

    from solidworks_mcp.agents.soc_exporter import export_session

    export_session("my-session-id", output_path="my_part.py")

CLI::

    python -m solidworks_mcp.agents.soc_exporter <session_id> <output_path>
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path
from typing import Any

from solidworks_mcp.agents.history_db import list_tool_call_records

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCRIPT_HEADER = """\
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from solidworks_mcp.adapters import create_adapter
from solidworks_mcp.adapters.base import ExtrusionParameters
from solidworks_mcp.config import load_config


def require(result: Any, label: str) -> Any:
    if not result.is_success:
        raise RuntimeError(f"{label} failed: {result.error}")
    return result


async def build_part() -> None:
    config = load_config()
    adapter = await create_adapter(config)
    await adapter.connect()
    try:
"""

_SCRIPT_FOOTER = """\
    finally:
        await adapter.disconnect()


if __name__ == "__main__":
    asyncio.run(build_part())
"""


def _r(v: Any) -> str:
    """Compact repr: omit None values, prefer bare strings for short strs."""
    return repr(v)


def _fmt_num(v: float) -> str:
    """Format a float without trailing zeros."""
    s = f"{v:.6g}"
    return s


def _parse_input(input_json: str | None) -> dict[str, Any]:
    if not input_json:
        return {}
    try:
        result = json.loads(input_json)
        return result if isinstance(result, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _parse_output(output_json: str | None) -> dict[str, Any]:
    if not output_json:
        return {}
    try:
        result = json.loads(output_json)
        return result if isinstance(result, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _coord(inp: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    """Return the first non-None value from inp for the given keys as a float."""
    for k in keys:
        v = inp.get(k)
        if v is not None:
            return float(v)
    return default


def _entity_id_from_output(output: dict[str, Any]) -> str | None:
    """Extract entity_id from an AdapterResult output dict."""
    data = output.get("data")
    if isinstance(data, dict):
        return data.get("entity_id") or data.get("id")
    if isinstance(data, str):
        return data
    return None


# ---------------------------------------------------------------------------
# Per-tool code emitters
# ---------------------------------------------------------------------------


class _CodeGen:
    """Stateful generator that tracks entity variables across one sketch."""

    def __init__(self) -> None:
        self._lines: list[str] = []
        # entity_id (str like "Line_1") → python variable name (str like "line_1")
        self._entity_vars: dict[str, str] = {}
        self._counters: dict[str, int] = {}
        self._in_sketch = False

    def _indent(self, code: str) -> str:
        return textwrap.indent(code, "        ")

    def _emit(self, line: str) -> None:
        self._lines.append(self._indent(line))

    def _blank(self) -> None:
        self._lines.append("")

    def _fresh_var(self, prefix: str) -> str:
        n = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = n
        return f"{prefix}_{n}"

    def _reset_sketch_state(self) -> None:
        self._entity_vars = {}
        self._counters = {}
        self._in_sketch = False

    def _var_for(self, entity_id: str | None, prefix: str) -> str:
        """Return (and register) a variable name for entity_id."""
        if entity_id and entity_id in self._entity_vars:
            return self._entity_vars[entity_id]
        var = self._fresh_var(prefix)
        if entity_id:
            self._entity_vars[entity_id] = var
        return var

    def _entity_ref(self, entity_id: str | None) -> str:
        """Return the python variable for a previously captured entity, or quoted id."""
        if entity_id and entity_id in self._entity_vars:
            return self._entity_vars[entity_id]
        return _r(entity_id)

    # ------------------------------------------------------------------
    # Emitters per tool
    # ------------------------------------------------------------------

    def emit_create_part(self, inp: dict[str, Any], _out: dict[str, Any]) -> None:
        name = inp.get("name", "part")
        self._blank()
        self._emit(
            f'require(await adapter.create_part(name={_r(name)}), "create_part")'
        )

    def emit_open_model(self, inp: dict[str, Any], _out: dict[str, Any]) -> None:
        path = inp.get("file_path") or inp.get("path", "")
        self._blank()
        self._emit(f'require(await adapter.open_model({_r(path)}), "open_model")')

    def emit_create_sketch(self, inp: dict[str, Any], _out: dict[str, Any]) -> None:
        self._reset_sketch_state()
        self._in_sketch = True
        plane = inp.get("plane", "Front")
        self._blank()
        self._emit(
            f'require(await adapter.create_sketch({_r(plane)}), "create_sketch")'
        )

    def emit_exit_sketch(self, _inp: dict[str, Any], _out: dict[str, Any]) -> None:
        self._in_sketch = False
        self._blank()
        self._emit('require(await adapter.exit_sketch(), "exit_sketch")')

    def emit_add_line(self, inp: dict[str, Any], out: dict[str, Any]) -> None:
        x1 = _coord(inp, "x1", "start_x")
        y1 = _coord(inp, "y1", "start_y")
        x2 = _coord(inp, "x2", "end_x")
        y2 = _coord(inp, "y2", "end_y")
        eid = _entity_id_from_output(out)
        var = self._var_for(eid, "line")
        args = f"{_fmt_num(x1)}, {_fmt_num(y1)}, {_fmt_num(x2)}, {_fmt_num(y2)}"
        self._emit(f'{var} = require(await adapter.add_line({args}), "add_line")')

    def emit_add_centerline(self, inp: dict[str, Any], out: dict[str, Any]) -> None:
        x1 = _coord(inp, "x1", "start_x")
        y1 = _coord(inp, "y1", "start_y")
        x2 = _coord(inp, "x2", "end_x")
        y2 = _coord(inp, "y2", "end_y")
        eid = _entity_id_from_output(out)
        var = self._var_for(eid, "cl")
        args = f"{_fmt_num(x1)}, {_fmt_num(y1)}, {_fmt_num(x2)}, {_fmt_num(y2)}"
        self._emit(
            f'{var} = require(await adapter.add_centerline({args}), "add_centerline")'
        )

    def emit_add_circle(self, inp: dict[str, Any], out: dict[str, Any]) -> None:
        cx = inp.get("center_x", 0.0)
        cy = inp.get("center_y", 0.0)
        r = inp.get("radius", 1.0)
        eid = _entity_id_from_output(out)
        var = self._var_for(eid, "circle")
        args = f"{_fmt_num(cx)}, {_fmt_num(cy)}, {_fmt_num(r)}"
        self._emit(f'{var} = require(await adapter.add_circle({args}), "add_circle")')

    def emit_add_arc(self, inp: dict[str, Any], out: dict[str, Any]) -> None:
        cx = inp.get("center_x", 0.0)
        cy = inp.get("center_y", 0.0)
        r = inp.get("radius", 1.0)
        start_angle = inp.get("start_angle", 0.0)
        end_angle = inp.get("end_angle", 90.0)
        eid = _entity_id_from_output(out)
        var = self._var_for(eid, "arc")
        args = (
            f"{_fmt_num(cx)}, {_fmt_num(cy)}, {_fmt_num(r)}, "
            f"{_fmt_num(start_angle)}, {_fmt_num(end_angle)}"
        )
        self._emit(f'{var} = require(await adapter.add_arc({args}), "add_arc")')

    def emit_add_rectangle(self, inp: dict[str, Any], out: dict[str, Any]) -> None:
        x1 = inp.get("x1", 0.0)
        y1 = inp.get("y1", 0.0)
        x2 = inp.get("x2", 1.0)
        y2 = inp.get("y2", 1.0)
        eid = _entity_id_from_output(out)
        var = self._var_for(eid, "rect")
        args = f"{_fmt_num(x1)}, {_fmt_num(y1)}, {_fmt_num(x2)}, {_fmt_num(y2)}"
        self._emit(
            f'{var} = require(await adapter.add_rectangle({args}), "add_rectangle")'
        )

    def emit_add_spline(self, inp: dict[str, Any], out: dict[str, Any]) -> None:
        points = inp.get("points", [])
        eid = _entity_id_from_output(out)
        var = self._var_for(eid, "spline")
        self._emit(
            f"{var} = require(await adapter.add_spline({_r(points)}), \"add_spline\")"
        )

    def emit_add_polygon(self, inp: dict[str, Any], out: dict[str, Any]) -> None:
        cx = inp.get("center_x", 0.0)
        cy = inp.get("center_y", 0.0)
        r = inp.get("radius", 1.0)
        sides = inp.get("sides", 6)
        eid = _entity_id_from_output(out)
        var = self._var_for(eid, "polygon")
        args = f"{_fmt_num(cx)}, {_fmt_num(cy)}, {_fmt_num(r)}, {sides}"
        self._emit(
            f'{var} = require(await adapter.add_polygon({args}), "add_polygon")'
        )

    def emit_add_ellipse(self, inp: dict[str, Any], out: dict[str, Any]) -> None:
        cx = inp.get("center_x", 0.0)
        cy = inp.get("center_y", 0.0)
        major = inp.get("major_axis", 1.0)
        minor = inp.get("minor_axis", 0.5)
        eid = _entity_id_from_output(out)
        var = self._var_for(eid, "ellipse")
        args = f"{_fmt_num(cx)}, {_fmt_num(cy)}, {_fmt_num(major)}, {_fmt_num(minor)}"
        self._emit(
            f'{var} = require(await adapter.add_ellipse({args}), "add_ellipse")'
        )

    def emit_add_sketch_constraint(
        self, inp: dict[str, Any], _out: dict[str, Any]
    ) -> None:
        e1 = inp.get("entity1", "")
        e2 = inp.get("entity2")
        rel = inp.get("relation_type", "")
        e3 = inp.get("entity3")
        ref1 = self._entity_ref(e1)
        ref2 = self._entity_ref(e2) if e2 else "None"
        parts = [ref1, ref2, _r(rel)]
        if e3:
            parts.append(self._entity_ref(e3))
        self._emit(
            f'require(await adapter.add_sketch_constraint({", ".join(parts)}), "constraint {rel}")'
        )

    def emit_add_sketch_dimension(
        self, inp: dict[str, Any], _out: dict[str, Any]
    ) -> None:
        e1 = inp.get("entity1", "")
        e2 = inp.get("entity2")
        dim_type = inp.get("dimension_type", "linear")
        value = inp.get("value", 0.0)
        ref1 = self._entity_ref(e1)
        ref2 = self._entity_ref(e2) if e2 else "None"
        self._emit(
            f"require(await adapter.add_sketch_dimension("
            f"{ref1}, {ref2}, {_r(dim_type)}, {_fmt_num(value)}), "
            f'"dimension {_fmt_num(value)}")'
        )

    def emit_create_extrusion(self, inp: dict[str, Any], _out: dict[str, Any]) -> None:
        depth = inp.get("depth", 10.0)
        thin = inp.get("thin_feature", False)
        thin_t = inp.get("thin_thickness")
        both = inp.get("both_directions", False)
        draft = inp.get("draft_angle", 0.0)
        reverse = inp.get("reverse_direction", False)
        end_cond = inp.get("end_condition", "Blind")

        params: list[str] = [f"depth={_fmt_num(depth)}"]
        if thin:
            params.append("thin_feature=True")
        if thin_t is not None:
            params.append(f"thin_thickness={_fmt_num(thin_t)}")
        if both:
            params.append("both_directions=True")
        if draft:
            params.append(f"draft_angle={_fmt_num(draft)}")
        if reverse:
            params.append("reverse_direction=True")
        if end_cond != "Blind":
            params.append(f"end_condition={_r(end_cond)}")

        param_lines = "".join(f"                    {p},\n" for p in params)
        self._blank()
        self._lines.append(
            "        require(\n"
            "            await adapter.create_extrusion(\n"
            "                ExtrusionParameters(\n"
            + param_lines
            + "                )\n"
            "            ),\n"
            '            "create_extrusion",\n'
            "        )"
        )

    def emit_create_cut_extrude(
        self, inp: dict[str, Any], _out: dict[str, Any]
    ) -> None:
        depth = inp.get("depth", 10.0)
        through_all = inp.get("through_all", False)
        reverse = inp.get("reverse_direction", False)

        params: list[str] = []
        if through_all:
            params.append("through_all=True")
        else:
            params.append(f"depth={_fmt_num(depth)}")
        if reverse:
            params.append("reverse_direction=True")

        self._blank()
        self._emit(
            f'require(await adapter.create_cut_extrude({", ".join(params)}), "create_cut_extrude")'
        )

    def emit_save_file(self, inp: dict[str, Any], _out: dict[str, Any]) -> None:
        path = inp.get("file_path") or inp.get("path", "")
        self._blank()
        self._emit(f'require(await adapter.save_file({_r(path)}), "save_file")')

    def emit_save_as(self, inp: dict[str, Any], _out: dict[str, Any]) -> None:
        path = inp.get("file_path") or inp.get("path", "")
        self._blank()
        self._emit(f'require(await adapter.save_as({_r(path)}), "save_as")')

    def emit_export_image(self, inp: dict[str, Any], _out: dict[str, Any]) -> None:
        path = inp.get("file_path", "")
        fmt = inp.get("format_type", "png")
        width = inp.get("width", 1600)
        height = inp.get("height", 1000)
        view = inp.get("view_orientation", "isometric")
        self._blank()
        self._lines.append(
            "        require(\n"
            "            await adapter.export_image({\n"
            f'                "file_path": {_r(path)},\n'
            f'                "format_type": {_r(fmt)},\n'
            f'                "width": {width},\n'
            f'                "height": {height},\n'
            f'                "view_orientation": {_r(view)},\n'
            "            }),\n"
            '            "export_image",\n'
            "        )"
        )

    def emit_generic(self, bare_name: str, inp: dict[str, Any]) -> None:
        """Emit adapter.<bare_name>(**inp) for any tool not in _DISPATCH.

        This gives every logged tool call valid, runnable Python code even if
        the exporter has no specialized emitter for it.  The adapter method
        name and its keyword-argument names come directly from the logged
        input_json, so they match the actual adapter API.
        """
        if not inp:
            self._blank()
            self._emit(f'require(await adapter.{bare_name}(), "{bare_name}")')
        else:
            kwargs = ", ".join(
                f"{k}={_r(v)}" for k, v in inp.items() if v is not None
            )
            self._blank()
            self._emit(f'require(await adapter.{bare_name}({kwargs}), "{bare_name}")')

    def emit_unknown(self, tool_name: str, inp: dict[str, Any]) -> None:
        self._blank()
        self._emit(f"# TODO: {tool_name}({inp!r})")

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    # These are pure reads — querying state without mutating the model.
    # They're logged for audit purposes but omitted from the replay script.
    _READ_ONLY_OPS: frozenset[str] = frozenset(
        {
            "get_model_info",
            "list_features",
            "list_configurations",
            "get_mass_properties",
            "get_dimension",
            "check_sketch_fully_defined",
            "analyze_geometry",
            "check_interference",
            "calculate_mass_properties",
        }
    )

    _DISPATCH: dict[str, str] = {
        "create_part": "emit_create_part",
        "open_model": "emit_open_model",
        "create_sketch": "emit_create_sketch",
        "exit_sketch": "emit_exit_sketch",
        "add_line": "emit_add_line",
        "add_centerline": "emit_add_centerline",
        "add_circle": "emit_add_circle",
        "add_arc": "emit_add_arc",
        "add_rectangle": "emit_add_rectangle",
        "add_spline": "emit_add_spline",
        "add_polygon": "emit_add_polygon",
        "add_ellipse": "emit_add_ellipse",
        "add_sketch_constraint": "emit_add_sketch_constraint",
        "add_sketch_dimension": "emit_add_sketch_dimension",
        "create_extrusion": "emit_create_extrusion",
        "create_cut_extrude": "emit_create_cut_extrude",
        "save_file": "emit_save_file",
        "save_part": "emit_save_file",
        "save_as": "emit_save_as",
        "export_image": "emit_export_image",
        "export_png": "emit_export_image",
    }

    def process(self, tool_name: str, inp: dict[str, Any], out: dict[str, Any]) -> None:
        # Strip any MCP namespace prefix (e.g. "mcp__solidworks-mcp__create_part")
        bare = tool_name.split("__")[-1] if "__" in tool_name else tool_name
        # Skip internal bookkeeping and UI service calls
        if bare in ("soc_create_checkpoint",) or bare.startswith("ui."):
            return
        # Skip read-only queries — they don't affect model state
        if bare in self._READ_ONLY_OPS:
            return
        method = self._DISPATCH.get(bare)
        if method:
            getattr(self, method)(inp, out)
        else:
            # Agnostic fallback: emit adapter.<bare_name>(**kwargs) for any
            # logged tool not in _DISPATCH (covers add_fillet, create_revolve,
            # set_dimension, export_stl, close_model, create_assembly, etc.)
            self.emit_generic(bare, inp)

    def body_lines(self) -> list[str]:
        return self._lines


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_CHECKPOINT_RULE = "-" * 52


def _checkpoint_comment(cp: dict[str, Any]) -> str:
    """Render a SoCCheckpoint as a parseable comment block."""
    label = cp.get("label", "")
    file_path = cp.get("file_path", "")
    first_id = cp.get("first_record_id")
    last_id = cp.get("last_record_id")
    records_range = f"{first_id}-{last_id}" if first_id and last_id else str(last_id or "")
    lines = [
        f"        # -- checkpoint {_CHECKPOINT_RULE}",
        f"        # label:    {label}",
        f"        # file:     {file_path}",
    ]
    if records_range:
        lines.append(f"        # records:  {records_range}")
    lines.append(f"        # {_CHECKPOINT_RULE}")
    return "\n".join(lines)


def generate_script(
    records: list[dict[str, Any]],
    *,
    session_id: str | None = None,
    checkpoints: list[dict[str, Any]] | None = None,
    skip_failed: bool = True,
) -> str:
    """Generate a Python script from a list of ToolCallRecord dicts.

    Args:
        records: Ordered list of ToolCallRecord dicts (from list_tool_call_records).
        session_id: Optional session ID to embed in header comment.
        checkpoints: Optional list of SoCCheckpoint dicts (from list_soc_checkpoints).
            When provided, checkpoint comment blocks are inserted between the
            corresponding record boundaries.
        skip_failed: Skip records where success=False (default True).

    Returns:
        Complete Python script as a string.
    """
    # Build a mapping from last_record_id → checkpoint for fast lookup
    cp_after: dict[int, dict[str, Any]] = {}
    if checkpoints:
        for cp in checkpoints:
            lid = cp.get("last_record_id")
            if lid is not None:
                cp_after[int(lid)] = cp

    gen = _CodeGen()

    for rec in records:
        if skip_failed and not rec.get("success", True):
            continue
        tool_name: str = rec.get("tool_name", "")
        inp = _parse_input(rec.get("input_json"))
        out = _parse_output(rec.get("output_json"))
        gen.process(tool_name, inp, out)

        # Emit checkpoint block if this record is the last in a checkpoint
        rec_id = rec.get("id")
        if rec_id is not None and int(rec_id) in cp_after:
            gen._lines.append("")
            gen._lines.append(_checkpoint_comment(cp_after[int(rec_id)]))
            gen._lines.append("")

    header_comment = ""
    if session_id:
        header_comment = f"# session_id: {session_id}\n"

    body = "\n".join(gen.body_lines())
    if not body.strip():
        body = "        pass  # no recorded tool calls"

    return f"{header_comment}{_SCRIPT_HEADER}{body}\n{_SCRIPT_FOOTER}"


def export_session(
    session_id: str,
    output_path: str | Path,
    *,
    checkpoint_id: int | None = None,
    db_path: Path | None = None,
    skip_failed: bool = True,
) -> Path:
    """Export a session's ToolCallRecords as a runnable Python script.

    Args:
        session_id: The session ID to export.
        output_path: Destination .py file path.
        checkpoint_id: If set, export only records from this checkpoint.
        db_path: Override default SQLite DB path.
        skip_failed: Skip failed tool call records (default True).

    Returns:
        Path to the written file.
    """
    from solidworks_mcp.agents.history_db import list_soc_checkpoints

    records = list_tool_call_records(
        session_id, checkpoint_id=checkpoint_id, db_path=db_path
    )
    checkpoints = list_soc_checkpoints(session_id, db_path=db_path)
    script = generate_script(
        records,
        session_id=session_id,
        checkpoints=checkpoints,
        skip_failed=skip_failed,
    )
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(script, encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    if len(sys.argv) < 3:
        print(
            "Usage: python -m solidworks_mcp.agents.soc_exporter <session_id> <output.py>"
        )
        sys.exit(1)
    session_id = sys.argv[1]
    output_path = Path(sys.argv[2])
    written = export_session(session_id, output_path)
    print(f"Exported {session_id!r} → {written}")


if __name__ == "__main__":
    _cli()
