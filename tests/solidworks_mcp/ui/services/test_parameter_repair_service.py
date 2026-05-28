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
    validation = prs.validate_checkpoint_parameters({"part_name": "demo"}, "create_part")
    text = prs.build_repair_instruction_text(validation)
    assert "All parameters valid" in text
