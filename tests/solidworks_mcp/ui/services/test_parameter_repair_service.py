"""Tests for parameter validation and repair helpers."""

from __future__ import annotations

from solidworks_mcp.ui.services import parameter_repair_service as prs


def test_validate_unknown_tool_is_valid() -> None:
    """Unknown tools should be treated as valid without errors."""
    # Validate that unknown tools are skipped rather than blocked.
    result = prs.validate_checkpoint_parameters({"foo": "bar"}, "unknown_tool")
    assert result.is_valid is True
    assert "not recognized" in result.message


def test_validate_alias_group_satisfies_requirements() -> None:
    """Alias groups should satisfy required parameters."""
    # Provide the add_line aliases instead of line_mm.
    planned = {"line_start_mm": [0, 0], "line_end_mm": [1, 1]}
    result = prs.validate_checkpoint_parameters(planned, "add_line")
    assert result.is_valid is True


def test_validate_missing_required_returns_suggestions() -> None:
    """Missing required parameters should return suggestions."""
    # create_part requires part_name; ensure the missing key and suggestion appear.
    result = prs.validate_checkpoint_parameters({}, "create_part")
    assert result.is_valid is False
    assert "part_name" in result.missing_keys
    assert "part_name" in result.suggestions


def test_attempt_auto_repair_uses_context() -> None:
    """Auto-repair should fill from context when possible."""
    # create_sketch can auto-repair sketch_plane from context.
    planned: dict[str, object] = {}
    result = prs.attempt_auto_repair(
        planned,
        "create_sketch",
        context={"active_sketch_plane": "Front"},
    )
    assert result.is_valid is True
    assert result.repaired_plan is not None
    assert result.repaired_plan["sketch_plane"] == "Front"


def test_attempt_auto_repair_falls_back_when_unrepairable() -> None:
    """Auto-repair should return the original invalid result when needed."""
    # create_part has no context-based auto repair for part_name.
    result = prs.attempt_auto_repair({}, "create_part")
    assert result.is_valid is False
    assert result.repaired_plan is None


def test_build_repair_instruction_text_formats_missing() -> None:
    """Instruction text should include missing parameters and guidance."""
    # Build instruction text from an invalid validation result.
    validation = prs.validate_checkpoint_parameters({}, "create_part")
    text = prs.build_repair_instruction_text(validation)
    assert "Missing Parameters" in text
    assert "part_name" in text


def test_build_repair_instruction_text_for_valid() -> None:
    """Valid results should short-circuit to a success message."""
    # Valid inputs should return the success banner.
    validation = prs.validate_checkpoint_parameters(
        {"part_name": "demo"}, "create_part"
    )
    text = prs.build_repair_instruction_text(validation)
    assert "All parameters valid" in text


def test_validate_missing_assembly_name_uses_else_suggestion() -> None:
    """assembly_name has no explicit suggestion key → falls through to else branch."""
    # create_assembly requires assembly_name which has no dedicated suggestion.
    result = prs.validate_checkpoint_parameters({}, "create_assembly")
    assert result.is_valid is False
    assert "assembly_name" in result.missing_keys
    # Suggestions should contain the generic fallback for assembly_name.
    assert "assembly_name" in result.suggestions
    assert "create_assembly" in result.suggestions["assembly_name"]


def test_validate_sketch_plane_suggestion() -> None:
    """Missing sketch_plane should have a plane-choice suggestion."""
    result = prs.validate_checkpoint_parameters({}, "create_sketch")
    assert result.is_valid is False
    assert result.suggestions.get("sketch_plane") is not None
    assert "Front" in result.suggestions["sketch_plane"]


def test_validate_geometry_key_suggestions() -> None:
    """Geometry tools should produce numeric/vector suggestions for missing keys."""
    # add_line missing line_mm.
    r = prs.validate_checkpoint_parameters({}, "add_line")
    assert r.suggestions.get("line_mm") is not None
    # add_rectangle missing rectangle_mm.
    r2 = prs.validate_checkpoint_parameters({}, "add_rectangle")
    assert r2.suggestions.get("rectangle_mm") is not None
    # add_circle missing circle_center_mm and circle_radius_mm.
    r3 = prs.validate_checkpoint_parameters({}, "add_circle")
    assert r3.suggestions.get("circle_center_mm") is not None
    assert r3.suggestions.get("circle_radius_mm") is not None


def test_validate_depth_and_file_suggestions() -> None:
    """depth and file_path should have numeric/path suggestions."""
    # create_extrusion requires depth.
    r = prs.validate_checkpoint_parameters({}, "create_extrusion")
    assert "depth" in r.suggestions

    # save_file requires file_path.
    r2 = prs.validate_checkpoint_parameters({}, "save_file")
    assert "file_path" in r2.suggestions


def test_attempt_auto_repair_with_sketch_plane_context() -> None:
    """Auto-repair should fill sketch_plane from context when available."""
    # create_sketch requires sketch_plane; context provides active_sketch_plane.
    result = prs.attempt_auto_repair(
        {},
        "create_sketch",
        context={"active_sketch_plane": "Top"},
    )
    assert result.is_valid is True
    assert result.repaired_plan is not None
    assert result.repaired_plan["sketch_plane"] == "Top"


def test_attempt_auto_repair_partial_repair_still_invalid() -> None:
    """Auto-repair should return invalid if repaired plan still has missing keys."""
    # create_circle requires circle_center_mm and circle_radius_mm; only provide one via context.
    # No auto-repair strategy for those keys → still invalid.
    result = prs.attempt_auto_repair(
        {}, "add_circle", context={"active_sketch_plane": "Front"}
    )
    assert result.is_valid is False


def test_validate_arc_and_centerline_suggestions() -> None:
    """Arc and centerline tools should produce vector suggestions for missing keys."""
    # add_arc missing arc_center_mm, arc_start_mm, arc_end_mm.
    r = prs.validate_checkpoint_parameters({}, "add_arc")
    assert r.suggestions.get("arc_center_mm") is not None
    assert r.suggestions.get("arc_start_mm") is not None
    assert r.suggestions.get("arc_end_mm") is not None
    # add_centerline missing centerline_mm.
    r2 = prs.validate_checkpoint_parameters({}, "add_centerline")
    assert r2.suggestions.get("centerline_mm") is not None


def test_validate_model_path_suggestion() -> None:
    """open_model missing model_path should have a file-path suggestion."""
    r = prs.validate_checkpoint_parameters({}, "open_model")
    assert "model_path" in r.suggestions
    assert "SolidWorks" in r.suggestions["model_path"]


def test_attempt_auto_repair_already_valid_returns_early() -> None:
    """attempt_auto_repair should return immediately when parameters are already valid."""
    # create_part with part_name provided is valid — hits the early return at line 253.
    result = prs.attempt_auto_repair({"part_name": "my_part"}, "create_part")
    assert result.is_valid is True
    assert result.repaired_plan is None
