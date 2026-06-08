"""Tests for soc_exporter.py — all pure Python, no SolidWorks required."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from solidworks_mcp.agents.soc_exporter import (
    _CodeGen,
    _checkpoint_comment,
    _entity_id_from_output,
    _fmt_num,
    _parse_input,
    _parse_output,
    generate_script,
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _rec(
    tool_name: str,
    inp: dict | None = None,
    out: dict | None = None,
    success: bool = True,
    rec_id: int = 1,
) -> dict:
    return {
        "id": rec_id,
        "tool_name": tool_name,
        "input_json": json.dumps(inp or {}),
        "output_json": json.dumps(out or {}),
        "success": success,
        "session_id": "test-session",
        "checkpoint_id": None,
        "run_id": None,
        "latency_ms": None,
        "status": None,
        "created_at": "2026-01-01T00:00:00",
    }


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def test_fmt_num_integer():
    assert _fmt_num(10.0) == "10"


def test_fmt_num_decimal():
    assert _fmt_num(9.525) == "9.525"


def test_fmt_num_small():
    assert _fmt_num(0.001) == "0.001"


def test_parse_input_valid():
    assert _parse_input('{"plane": "Front"}') == {"plane": "Front"}


def test_parse_input_empty():
    assert _parse_input(None) == {}
    assert _parse_input("") == {}


def test_parse_input_non_dict():
    assert _parse_input("[1,2,3]") == {}


def test_parse_input_invalid_json():
    assert _parse_input("{bad json}") == {}


def test_parse_output_valid():
    assert _parse_output('{"data": {"entity_id": "Line_1"}}') == {
        "data": {"entity_id": "Line_1"}
    }


def test_entity_id_from_output_dict_data():
    out = {"data": {"entity_id": "Arc_2"}}
    assert _entity_id_from_output(out) == "Arc_2"


def test_entity_id_from_output_string_data():
    out = {"data": "Circle_1"}
    assert _entity_id_from_output(out) == "Circle_1"


def test_entity_id_from_output_missing():
    assert _entity_id_from_output({}) is None
    assert _entity_id_from_output({"data": None}) is None


# ---------------------------------------------------------------------------
# _CodeGen unit tests
# ---------------------------------------------------------------------------


def test_codegen_fresh_var_increments():
    cg = _CodeGen()
    assert cg._fresh_var("line") == "line_1"
    assert cg._fresh_var("line") == "line_2"
    assert cg._fresh_var("arc") == "arc_1"


def test_codegen_var_for_registers_entity():
    cg = _CodeGen()
    var = cg._var_for("Line_1", "line")
    assert var == "line_1"
    # Same entity → same variable
    assert cg._var_for("Line_1", "line") == "line_1"


def test_codegen_entity_ref_fallback():
    cg = _CodeGen()
    # Unknown entity_id → quoted id
    assert cg._entity_ref("Unknown_99") == "'Unknown_99'"


def test_codegen_entity_ref_known():
    cg = _CodeGen()
    cg._var_for("Line_1", "line")
    assert cg._entity_ref("Line_1") == "line_1"


def test_codegen_reset_sketch_state_clears_vars():
    cg = _CodeGen()
    cg._var_for("Line_1", "line")
    cg._reset_sketch_state()
    # After reset, entity ref returns the quoted fallback
    assert cg._entity_ref("Line_1") == "'Line_1'"


# ---------------------------------------------------------------------------
# generate_script — structural checks
# ---------------------------------------------------------------------------


def test_generate_script_empty_records():
    script = generate_script([])
    assert "async def build_part()" in script
    assert "await adapter.disconnect()" in script
    assert "pass  # no recorded tool calls" in script


def test_generate_script_session_id_in_header():
    script = generate_script([], session_id="my-session-abc")
    assert "# session_id: my-session-abc" in script


def test_generate_script_create_part():
    records = [_rec("create_part", {"name": "my_bracket"})]
    script = generate_script(records)
    assert "adapter.create_part(name='my_bracket')" in script
    assert "require(" in script


def test_generate_script_create_sketch():
    records = [_rec("create_sketch", {"plane": "Top"})]
    script = generate_script(records)
    assert "adapter.create_sketch('Top')" in script


def test_generate_script_exit_sketch():
    records = [_rec("exit_sketch")]
    script = generate_script(records)
    assert "adapter.exit_sketch()" in script


def test_generate_script_add_line():
    inp = {"x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 0.0}
    out = {"data": {"entity_id": "Line_1"}}
    records = [_rec("add_line", inp, out)]
    script = generate_script(records)
    assert "adapter.add_line(0, 0, 10, 0)" in script
    assert "line_1 = require(" in script


def test_generate_script_add_circle():
    inp = {"center_x": 0.0, "center_y": 9.525, "radius": 4.7625}
    out = {"data": {"entity_id": "Circle_1"}}
    records = [_rec("add_circle", inp, out)]
    script = generate_script(records)
    assert "adapter.add_circle(0, 9.525, 4.7625)" in script


def test_generate_script_add_arc():
    inp = {
        "center_x": 0.0,
        "center_y": 0.0,
        "radius": 5.0,
        "start_angle": 0.0,
        "end_angle": 90.0,
    }
    out = {"data": {"entity_id": "Arc_1"}}
    records = [_rec("add_arc", inp, out)]
    script = generate_script(records)
    assert "adapter.add_arc(0, 0, 5, 0, 90)" in script


def test_generate_script_add_centerline():
    inp = {"x1": -10.0, "y1": 0.0, "x2": 10.0, "y2": 0.0}
    out = {"data": {"entity_id": "CL_1"}}
    records = [_rec("add_centerline", inp, out)]
    script = generate_script(records)
    assert "adapter.add_centerline(-10, 0, 10, 0)" in script
    assert "cl_1 = require(" in script


def test_generate_script_add_rectangle():
    inp = {"x1": 0.0, "y1": 0.0, "x2": 50.0, "y2": 25.0}
    out = {"data": {"entity_id": "Rect_1"}}
    records = [_rec("add_rectangle", inp, out)]
    script = generate_script(records)
    assert "adapter.add_rectangle(0, 0, 50, 25)" in script


def test_generate_script_add_spline():
    inp = {"points": [[0, 0], [5, 10], [10, 0]]}
    out = {"data": {"entity_id": "Spline_1"}}
    records = [_rec("add_spline", inp, out)]
    script = generate_script(records)
    assert "adapter.add_spline(" in script


def test_generate_script_add_polygon():
    inp = {"center_x": 0.0, "center_y": 0.0, "radius": 10.0, "sides": 6}
    out = {"data": {"entity_id": "Poly_1"}}
    records = [_rec("add_polygon", inp, out)]
    script = generate_script(records)
    assert "adapter.add_polygon(0, 0, 10, 6)" in script


def test_generate_script_add_ellipse():
    inp = {"center_x": 0.0, "center_y": 0.0, "major_axis": 20.0, "minor_axis": 10.0}
    out = {"data": {"entity_id": "Ell_1"}}
    records = [_rec("add_ellipse", inp, out)]
    script = generate_script(records)
    assert "adapter.add_ellipse(0, 0, 20, 10)" in script


def test_generate_script_add_sketch_dimension():
    # Line_1 entity → references line_1 variable
    line_out = {"data": {"entity_id": "Line_1"}}
    line_rec = _rec(
        "add_line", {"x1": 0, "y1": 0, "x2": 10, "y2": 0}, line_out, rec_id=1
    )
    dim_inp = {
        "entity1": "Line_1",
        "entity2": None,
        "dimension_type": "linear",
        "value": 10.0,
    }
    dim_rec = _rec("add_sketch_dimension", dim_inp, {}, rec_id=2)
    script = generate_script([line_rec, dim_rec])
    assert "line_1" in script
    assert "adapter.add_sketch_dimension(line_1" in script
    assert "'linear'" in script
    assert "10" in script


def test_generate_script_add_sketch_constraint():
    line_out = {"data": {"entity_id": "Line_1"}}
    line_rec = _rec(
        "add_line", {"x1": 0, "y1": 0, "x2": 10, "y2": 0}, line_out, rec_id=1
    )
    con_inp = {"entity1": "Line_1", "entity2": None, "relation_type": "fix"}
    con_rec = _rec("add_sketch_constraint", con_inp, {}, rec_id=2)
    script = generate_script([line_rec, con_rec])
    assert "adapter.add_sketch_constraint(line_1, None, 'fix')" in script


def test_generate_script_create_extrusion_defaults():
    records = [_rec("create_extrusion", {"depth": 25.4})]
    script = generate_script(records)
    assert "ExtrusionParameters" in script
    assert "depth=25.4" in script


def test_generate_script_create_extrusion_non_defaults():
    inp = {
        "depth": 10.0,
        "both_directions": True,
        "reverse_direction": True,
        "end_condition": "ThroughAll",
        "thin_feature": True,
        "thin_thickness": 2.0,
        "draft_angle": 5.0,
    }
    records = [_rec("create_extrusion", inp)]
    script = generate_script(records)
    assert "both_directions=True" in script
    assert "reverse_direction=True" in script
    assert "end_condition='ThroughAll'" in script
    assert "thin_feature=True" in script
    assert "thin_thickness=2" in script
    assert "draft_angle=5" in script


def test_generate_script_create_cut_extrude_through_all():
    inp = {"depth": 0.0, "through_all": True, "reverse_direction": False}
    records = [_rec("create_cut_extrude", inp)]
    script = generate_script(records)
    assert "through_all=True" in script
    assert "adapter.create_cut_extrude" in script


def test_generate_script_create_cut_extrude_blind():
    inp = {"depth": 15.0, "through_all": False}
    records = [_rec("create_cut_extrude", inp)]
    script = generate_script(records)
    assert "depth=15" in script


def test_generate_script_save_file():
    records = [_rec("save_file", {"file_path": "C:/tmp/part.sldprt"})]
    script = generate_script(records)
    assert "adapter.save_file('C:/tmp/part.sldprt')" in script


def test_generate_script_save_part_alias():
    # save_part maps to emit_save_file
    records = [_rec("save_part", {"file_path": "C:/tmp/part.sldprt"})]
    script = generate_script(records)
    assert "adapter.save_file('C:/tmp/part.sldprt')" in script


def test_generate_script_save_as():
    records = [_rec("save_as", {"file_path": "C:/tmp/part_v2.sldprt"})]
    script = generate_script(records)
    assert "adapter.save_as('C:/tmp/part_v2.sldprt')" in script


def test_generate_script_export_image():
    inp = {
        "file_path": "C:/tmp/part.png",
        "format_type": "png",
        "width": 800,
        "height": 600,
        "view_orientation": "isometric",
    }
    records = [_rec("export_image", inp)]
    script = generate_script(records)
    assert "adapter.export_image" in script
    assert '"file_path"' in script
    assert "800" in script


def test_generate_script_skips_failed_records():
    good = _rec("create_part", {"name": "p"}, rec_id=1, success=True)
    bad = _rec("create_sketch", {"plane": "Front"}, rec_id=2, success=False)
    script = generate_script([good, bad], skip_failed=True)
    assert "create_part" in script
    assert "create_sketch" not in script


def test_generate_script_includes_failed_when_disabled():
    bad = _rec("create_sketch", {"plane": "Front"}, success=False)
    script = generate_script([bad], skip_failed=False)
    assert "create_sketch" in script


def test_generate_script_skips_read_only_ops():
    records = [
        _rec("get_model_info"),
        _rec("list_features"),
        _rec("check_sketch_fully_defined"),
        _rec("analyze_geometry"),
        _rec("get_dimension"),
        _rec("check_interference"),
        _rec("calculate_mass_properties"),
    ]
    script = generate_script(records)
    assert "get_model_info" not in script
    assert "list_features" not in script
    assert "pass  # no recorded tool calls" in script


def test_generate_script_mcp_namespace_prefix_stripped():
    records = [_rec("mcp__solidworks-mcp__create_part", {"name": "bracket"})]
    script = generate_script(records)
    assert "adapter.create_part" in script


def test_generate_script_generic_fallback_for_unknown_tool():
    records = [_rec("some_custom_tool", {"foo": "bar", "n": 42})]
    script = generate_script(records)
    assert "adapter.some_custom_tool(foo='bar', n=42)" in script


def test_generate_script_generic_fallback_no_args():
    records = [_rec("close_model", {})]
    script = generate_script(records)
    assert "adapter.close_model()" in script


def test_generate_script_open_model():
    records = [_rec("open_model", {"file_path": "C:/tmp/part.sldprt"})]
    script = generate_script(records)
    assert "adapter.open_model('C:/tmp/part.sldprt')" in script


def test_generate_script_with_checkpoint_comment():
    records = [
        _rec("create_part", {"name": "p"}, rec_id=1),
        _rec("create_extrusion", {"depth": 10.0}, rec_id=2),
    ]
    checkpoints = [
        {
            "label": "base-body",
            "file_path": "C:/tmp/cp1.sldprt",
            "first_record_id": 1,
            "last_record_id": 2,
        }
    ]
    script = generate_script(records, checkpoints=checkpoints)
    assert "# -- checkpoint" in script
    assert "label:    base-body" in script
    assert "file:     C:/tmp/cp1.sldprt" in script
    assert "records:  1-2" in script


def test_generate_script_checkpoint_inserted_after_correct_record():
    records = [
        _rec("create_part", {"name": "p"}, rec_id=1),
        _rec("create_extrusion", {"depth": 5.0}, rec_id=2),
        _rec("create_sketch", {"plane": "Front"}, rec_id=3),
    ]
    checkpoints = [
        {
            "label": "after-extrude",
            "file_path": "C:/cp.sldprt",
            "first_record_id": 1,
            "last_record_id": 2,
        }
    ]
    script = generate_script(records, checkpoints=checkpoints)
    lines = script.splitlines()
    cp_idx = next(i for i, l in enumerate(lines) if "# -- checkpoint" in l)
    sketch_idx = next(i for i, l in enumerate(lines) if "create_sketch" in l)
    assert cp_idx < sketch_idx, (
        "checkpoint comment should appear before the next sketch call"
    )


def test_checkpoint_comment_no_records():
    cp = {
        "label": "init",
        "file_path": "C:/tmp/init.sldprt",
        "first_record_id": None,
        "last_record_id": None,
    }
    comment = _checkpoint_comment(cp)
    assert "label:    init" in comment
    assert "records:" not in comment


# ---------------------------------------------------------------------------
# export_session — file writing
# ---------------------------------------------------------------------------


def test_export_session_writes_file(tmp_path):
    from solidworks_mcp.agents.soc_exporter import export_session

    db = tmp_path / "test.sqlite3"
    out = tmp_path / "session_out.py"

    from solidworks_mcp.agents.history_db import init_db, insert_tool_call_record

    init_db(db)
    insert_tool_call_record(
        session_id="sess-export",
        tool_name="create_part",
        input_json='{"name":"my_part"}',
        output_json="{}",
        success=True,
        db_path=db,
    )
    insert_tool_call_record(
        session_id="sess-export",
        tool_name="create_sketch",
        input_json='{"plane":"Front"}',
        output_json="{}",
        success=True,
        db_path=db,
    )

    written = export_session("sess-export", out, db_path=db)
    assert written == out
    content = out.read_text()
    assert "create_part" in content
    assert "create_sketch" in content
    assert "async def build_part()" in content


# ---------------------------------------------------------------------------
# Additional coverage for uncovered lines
# ---------------------------------------------------------------------------


def test_parse_output_empty_and_invalid() -> None:
    """_parse_output should return {} for empty/None and invalid JSON. Covers lines 89, 93-94."""
    # Empty string → line 89
    assert _parse_output(None) == {}
    assert _parse_output("") == {}
    # Invalid JSON → lines 93-94
    assert _parse_output("{bad json}") == {}
    # Non-dict JSON → line 92
    assert _parse_output("[1, 2, 3]") == {}


def test_coord_returns_default_when_no_key_matches() -> None:
    """_coord should return default when none of the keys are found. Covers line 103."""
    from solidworks_mcp.agents.soc_exporter import _coord

    result = _coord({}, "x", "y", default=99.0)
    assert result == 99.0


def test_codegen_emit_add_sketch_constraint_with_entity3() -> None:
    """emit_add_sketch_constraint should include entity3 ref when e3 is set. Covers line 291."""
    cg = _CodeGen()
    inp = {
        "entity1": "line1",
        "entity2": "line2",
        "entity3": "origin",
        "relation_type": "coincident",
    }
    cg.emit_add_sketch_constraint(inp, {})
    script = "\n".join(cg._lines)
    assert "add_sketch_constraint" in script
    # entity3 was included (3 entity refs + relation = 4 args)
    assert script.count(",") >= 3


def test_codegen_emit_create_cut_extrude_with_reverse() -> None:
    """emit_create_cut_extrude should include reverse_direction when reverse_direction=True. Covers line 360."""
    cg = _CodeGen()
    inp = {"depth": 5.0, "reverse_direction": True, "through_all": False}
    cg.emit_create_cut_extrude(inp, {})
    script = "\n".join(cg._lines)
    assert "reverse_direction=True" in script


def test_codegen_emit_unknown_writes_todo() -> None:
    """emit_unknown should write a TODO comment. Covers lines 414-415."""
    cg = _CodeGen()
    cg.emit_unknown("some_unknown_tool", {"param": "value"})
    script = "\n".join(cg._lines)
    assert "# TODO: some_unknown_tool" in script


def test_codegen_process_skips_soc_and_ui_tools() -> None:
    """process() should return early for soc_create_checkpoint and ui.* tools. Covers line 466."""
    cg = _CodeGen()
    initial_lines = len(cg._lines)
    cg.process("soc_create_checkpoint", {}, {})
    cg.process("ui.some_action", {}, {})
    # No new lines added
    assert len(cg._lines) == initial_lines


def test_soc_exporter_cli_usage(monkeypatch) -> None:
    """CLI with <3 args should print usage and exit. Covers lines 611-615."""
    import sys
    from solidworks_mcp.agents import soc_exporter

    monkeypatch.setattr(sys, "argv", ["prog", "only_one_arg"])
    with pytest.raises(SystemExit):
        soc_exporter._cli()
