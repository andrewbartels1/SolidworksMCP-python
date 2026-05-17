"""Parameter validation and repair service for checkpoint tool parameters.

Validates checkpoint planned actions against known tool signatures and provides
repair suggestions or auto-completion strategies for missing parameters.
"""

from __future__ import annotations

from typing import Any

from loguru import logger


# Tool parameter schemas: required parameters per tool name
TOOL_PARAM_SCHEMAS: dict[str, dict[str, Any]] = {
    "create_part": {
        "required": ["part_name"],
        "optional": [],
        "description": "Create a new part document.",
    },
    "create_assembly": {
        "required": ["assembly_name"],
        "optional": [],
        "description": "Create a new assembly document.",
    },
    "open_model": {
        "required": ["model_path"],
        "optional": [],
        "description": "Open an existing SolidWorks model.",
    },
    "create_sketch": {
        "required": ["sketch_plane"],
        "optional": ["sketch_name"],
        "description": "Create a sketch on the specified plane.",
    },
    "exit_sketch": {
        "required": [],
        "optional": [],
        "description": "Exit the current sketch.",
    },
    "save_file": {
        "required": ["file_path"],
        "optional": [],
        "description": "Save the active document.",
    },
    "add_line": {
        "required": ["line_mm"],  # or ["line_start_mm", "line_end_mm"]
        "optional": [],
        "description": "Add a line to the current sketch.",
        "aliases": [["line_start_mm", "line_end_mm"]],  # Alternative param format
    },
    "add_rectangle": {
        "required": ["rectangle_mm"],
        "optional": [],
        "description": "Add a rectangle to the current sketch.",
    },
    "add_circle": {
        "required": ["circle_center_mm", "circle_radius_mm"],
        "optional": [],
        "description": "Add a circle to the current sketch.",
    },
    "add_arc": {
        "required": ["arc_center_mm", "arc_start_mm", "arc_end_mm"],
        "optional": [],
        "description": "Add an arc to the current sketch.",
    },
    "add_centerline": {
        "required": ["centerline_mm"],
        "optional": [],
        "description": "Add a centerline to the current sketch.",
    },
    "create_extrusion": {
        "required": ["depth"],
        "optional": [
            "sketch_name",
            "thin_feature",
            "thin_thickness",
            "thin_thickness_mm",
            "both_directions",
            "auto_fillet_corners",
            "fillet_corners_radius",
        ],
        "description": "Create an extrusion from the current sketch.",
        "aliases": [["depth_mm"]],
    },
    "create_cut": {
        "required": ["depth"],
        "optional": ["sketch_name", "blind_or_through"],
        "description": "Create a cut (subtractive feature) from the current sketch.",
        "aliases": [["depth_mm"]],
    },
    "create_cut_extrude": {
        "required": ["depth"],
        "optional": [],
        "description": "Create a cut extrusion from the current sketch.",
        "aliases": [["depth_mm"]],
    },
    "export_image": {
        "required": ["file_path", "format_type"],
        "optional": ["width", "height", "view_orientation"],
        "description": "Export the current model as an image.",
        "aliases": [["export_image"]],
    },
    "check_sketch_fully_defined": {
        "required": [],
        "optional": ["sketch_name"],
        "description": "Check if the current or named sketch is fully defined.",
    },
}


class ParameterRepairResult:
    """Result of parameter validation and repair."""

    def __init__(
        self,
        is_valid: bool,
        missing_keys: list[str] | None = None,
        suggestions: dict[str, Any] | None = None,
        repaired_plan: dict[str, Any] | None = None,
        message: str = "",
    ):
        self.is_valid = is_valid
        self.missing_keys = missing_keys or []
        self.suggestions = suggestions or {}
        self.repaired_plan = repaired_plan
        self.message = message


def validate_checkpoint_parameters(
    planned: dict[str, Any], tool_name: str
) -> ParameterRepairResult:
    """Validate that a planned action has all required parameters for a tool.

    Args:
        planned: Checkpoint planned-action dict.
        tool_name: Name of the tool being validated.

    Returns:
        ParameterRepairResult with validation status and repair suggestions.
    """
    if tool_name not in TOOL_PARAM_SCHEMAS:
        logger.warning(f"Unknown tool: {tool_name}")
        return ParameterRepairResult(
            is_valid=True,  # Assume unknown tools are valid (may be new tools)
            message=f"Tool {tool_name} not recognized; skipping validation.",
        )

    schema = TOOL_PARAM_SCHEMAS[tool_name]
    required_keys = schema["required"]
    missing_keys: list[str] = []

    # Check required keys
    for key in required_keys:
        if key not in planned:
            # Check if this key has aliases (alternative parameter formats)
            has_alias = False
            if "aliases" in schema:
                for alias_group in schema["aliases"]:
                    if isinstance(alias_group, list) and all(
                        k in planned for k in alias_group
                    ):
                        has_alias = True
                        break
            if not has_alias:
                missing_keys.append(key)

    if missing_keys:
        return ParameterRepairResult(
            is_valid=False,
            missing_keys=missing_keys,
            suggestions=_generate_repair_suggestions(tool_name, planned),
            message=f"Tool '{tool_name}' is missing required parameter(s): {', '.join(missing_keys)}",
        )

    return ParameterRepairResult(
        is_valid=True, message=f"Tool '{tool_name}' validation passed."
    )


def _generate_repair_suggestions(
    tool_name: str, planned: dict[str, Any]
) -> dict[str, Any]:
    """Generate repair suggestions for incomplete planned actions.

    Args:
        tool_name: Name of the tool.
        planned: Current planned-action dict.

    Returns:
        Dict with suggested parameter values or instructions.
    """
    schema = TOOL_PARAM_SCHEMAS.get(tool_name, {})
    required_keys = schema.get("required", [])
    suggestions: dict[str, Any] = {}

    for key in required_keys:
        if key not in planned:
            # Generate context-aware suggestions
            if key == "sketch_plane":
                suggestions[key] = (
                    "Choose one of: 'Front', 'Top', 'Right', or face reference name"
                )
            elif key == "line_mm":
                suggestions[key] = "[x1, y1, x2, y2] in millimeters"
            elif key == "rectangle_mm":
                suggestions[key] = "[x, y, width, height] in millimeters"
            elif key == "circle_center_mm":
                suggestions[key] = "[center_x, center_y] in millimeters"
            elif key == "circle_radius_mm":
                suggestions[key] = "Numeric value in millimeters"
            elif key == "arc_center_mm":
                suggestions[key] = "[center_x, center_y] in millimeters"
            elif key == "arc_start_mm":
                suggestions[key] = "[start_x, start_y] in millimeters"
            elif key == "arc_end_mm":
                suggestions[key] = "[end_x, end_y] in millimeters"
            elif key == "centerline_mm":
                suggestions[key] = "[x1, y1, x2, y2] reference line in millimeters"
            elif key == "depth":
                suggestions[key] = (
                    "Numeric value in millimeters (positive for extrude/cut)"
                )
            elif key == "file_path":
                suggestions[key] = "Full path to target file (relative or absolute)"
            elif key == "model_path":
                suggestions[key] = "Full path to SolidWorks part or assembly file"
            elif key == "part_name":
                suggestions[key] = (
                    "Valid filename for the new part (alphanumeric, underscore, dash)"
                )
            else:
                suggestions[key] = f"Required for tool '{tool_name}'"

    return suggestions


def attempt_auto_repair(
    planned: dict[str, Any], tool_name: str, context: dict[str, Any] | None = None
) -> ParameterRepairResult:
    """Attempt automatic repair of incomplete parameters based on context.

    Args:
        planned: Checkpoint planned-action dict.
        tool_name: Name of the tool.
        context: Optional context dict with hints (e.g., previous sketch plane).

    Returns:
        ParameterRepairResult with repaired plan or failure details.
    """
    validation = validate_checkpoint_parameters(planned, tool_name)
    if validation.is_valid:
        return validation

    # Try context-aware auto-repair
    context = context or {}
    repaired = dict(planned)  # Make a copy
    repaired_any = False

    # Repair strategy: use context clues from session state
    for missing_key in validation.missing_keys:
        if missing_key == "sketch_plane" and "active_sketch_plane" in context:
            repaired[missing_key] = context["active_sketch_plane"]
            repaired_any = True
        elif missing_key == "sketch_name" and "last_sketch_name" in context:
            repaired[missing_key] = context["last_sketch_name"]
            repaired_any = True
        # For geometry parameters, we cannot auto-repair without user input

    if repaired_any:
        # Re-validate after repair attempt
        second_validation = validate_checkpoint_parameters(repaired, tool_name)
        if second_validation.is_valid:
            return ParameterRepairResult(
                is_valid=True,
                repaired_plan=repaired,
                message=f"Successfully auto-repaired '{tool_name}' using context clues.",
            )

    # Return original validation (couldn't auto-repair fully)
    return validation


def build_repair_instruction_text(validation: ParameterRepairResult) -> str:
    """Build human-readable repair instruction text.

    Args:
        validation: ParameterRepairResult with missing keys and suggestions.

    Returns:
        Formatted instruction text for user display.
    """
    if validation.is_valid:
        return "✓ All parameters valid. No repairs needed."

    lines = [
        "⚠️ Parameter Validation Failed",
        f"   Message: {validation.message}",
        "",
        "Missing Parameters:",
    ]

    for key in validation.missing_keys:
        suggestion = validation.suggestions.get(key, "Required parameter")
        lines.append(f"   • {key}: {suggestion}")

    lines.extend(
        [
            "",
            "Instructions:",
            "   1. Open the generated checkpoint script",
            "   2. Edit the PLANNED dict to add missing parameters",
            "   3. Save the script",
            "   4. Run execute-next again",
        ]
    )

    return "\n".join(lines)
