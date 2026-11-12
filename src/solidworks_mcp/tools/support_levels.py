"""How far to trust each registered tool, in one reviewable table.

Every tool has exactly one support level:

- **stable**: checked by a live test on real SolidWorks, every input used,
  no known fault (or it never calls SolidWorks and is unit-tested);
- **beta**: works on SolidWorks, but has a known fault or covers only part
  of its COM call;
- **experimental**: implemented, never checked on real SolidWorks;
- **planned**: registered, but no adapter implements it yet (its
  description says "Not available yet").

``ToolRegistrar`` adds the level to each tool's tags and, for a beta or
experimental tool, a ``warning`` to its successful results. Fixing a fault
in the queue's small-faults list moves its tool up a level here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SupportLevel(StrEnum):
    """The four support levels, most trusted first."""

    STABLE = "stable"
    BETA = "beta"
    EXPERIMENTAL = "experimental"
    PLANNED = "planned"


@dataclass(frozen=True)
class Support:
    """One tool's support level and why it isn't higher.

    Attributes:
        level: The tool's support level.
        reason: One line on the gap; empty only for a stable tool.
    """

    level: SupportLevel
    reason: str = ""

    def __post_init__(self) -> None:
        """Require a reason for every level below stable.

        Raises:
            ValueError: If a level below stable has no reason, or a stable
                tool has one.
        """
        if (self.level is SupportLevel.STABLE) == bool(self.reason):
            raise ValueError(
                "a reason is required below stable, and only there: "
                f"{self.level.value!r} with reason {self.reason!r}"
            )

    def warning(self) -> str | None:
        """The sentence a successful beta or experimental result carries.

        Returns:
            str | None: ``"Beta: <reason>"`` or ``"Experimental: <reason>"``;
            None for stable and planned tools (a planned tool never succeeds).
        """
        if self.level in (SupportLevel.BETA, SupportLevel.EXPERIMENTAL):
            return f"{self.level.value.capitalize()}: {self.reason}"
        return None


#: Tool families that never call SolidWorks; their tools are stable on unit
#: tests alone.
OFFLINE_FAMILIES = frozenset({"docs_discovery", "server_admin", "vba_generation"})

_STABLE = Support(SupportLevel.STABLE)
_UNCHECKED = Support(
    SupportLevel.EXPERIMENTAL, "not yet checked by a live test on real SolidWorks."
)
_PLANNED = Support(SupportLevel.PLANNED, "no adapter implements it yet.")


SUPPORT_LEVELS: dict[str, Support] = {
    # analysis
    "analyze_geometry": _PLANNED,
    "calculate_mass_properties": _STABLE,
    "check_interference": _STABLE,
    "get_mass_properties": _STABLE,
    "get_material_properties": _PLANNED,
    "verify_model": _STABLE,
    # automation
    "automation_start_macro_recording": _PLANNED,
    "automation_stop_macro_recording": _PLANNED,
    "batch_process_files": _PLANNED,
    "create_template": _PLANNED,
    "execute_workflow": _PLANNED,
    "generate_vba_code": _UNCHECKED,
    "manage_design_table": _PLANNED,
    "optimize_performance": _PLANNED,
    # docs_discovery
    "discover_solidworks_docs": _STABLE,
    "find_related_api_members": _STABLE,
    "lookup_api_interface": _STABLE,
    "lookup_api_method": _STABLE,
    "search_solidworks_api_help": _STABLE,
    # drawing
    "add_annotation": _PLANNED,
    "add_dimension": _PLANNED,
    "add_drawing_view": _STABLE,
    "add_note": _STABLE,
    "auto_center_marks": _STABLE,
    "auto_dimension_view": _PLANNED,
    "check_drawing_standards": _PLANNED,
    "create_detail_view": _PLANNED,
    "create_drawing_view": _STABLE,
    "create_section_view": _PLANNED,
    "create_technical_drawing": _STABLE,
    "list_drawing_views": _STABLE,
    "update_sheet_format": _PLANNED,
    "update_title_block": _PLANNED,
    # drawing_analysis
    "analyze_drawing_annotations": _PLANNED,
    "analyze_drawing_comprehensive": _PLANNED,
    "analyze_drawing_dimensions": _PLANNED,
    "analyze_drawing_views": _PLANNED,
    "check_drawing_compliance": _PLANNED,
    "compare_drawing_versions": _STABLE,
    "generate_drawing_report": _PLANNED,
    "validate_drawing_completeness": _PLANNED,
    # drawing_automation
    "add_datum_tag": _STABLE,
    "add_gtol": _STABLE,
    "arrange_dimensions": _STABLE,
    "generate_drawing_package": _STABLE,
    "insert_bom_table": _STABLE,
    "insert_model_dimensions": _STABLE,
    "set_sheet_scale": _STABLE,
    # engineering_data
    "export_flat_pattern": _STABLE,
    "get_custom_properties": _STABLE,
    "get_material": _STABLE,
    "list_available_materials": _STABLE,
    "list_model_dimensions": _STABLE,
    "measure_entities": _STABLE,
    "set_custom_property": _STABLE,
    "set_material": _STABLE,
    # export
    "batch_export": _PLANNED,
    "export_dwg": _STABLE,
    "export_iges": _STABLE,
    "export_image": _STABLE,
    "export_pdf": _STABLE,
    "export_step": _STABLE,
    "export_stl": _STABLE,
    # file_management
    "activate_document": _STABLE,
    "batch_file_operations": _PLANNED,
    "classify_feature_tree": _STABLE,
    "convert_file_format": _PLANNED,
    "get_file_properties": _STABLE,
    "get_model_info": _STABLE,
    "get_selected_entities": _STABLE,
    "list_configurations": _STABLE,
    "list_features": _STABLE,
    "list_open_documents": _STABLE,
    "load_assembly": _STABLE,
    "load_part": _STABLE,
    "manage_file_properties": _PLANNED,
    "pack_and_go_assembly": _STABLE,
    "save_as": _STABLE,
    "save_assembly": _STABLE,
    "save_body_as_part": _STABLE,
    "save_file": _STABLE,
    "save_part": _STABLE,
    # macro_recording
    "analyze_macro": _PLANNED,
    "batch_execute_macros": _PLANNED,
    "create_macro_library": _PLANNED,
    "execute_macro": _STABLE,
    "optimize_macro": _PLANNED,
    "start_macro_recording": _PLANNED,
    "stop_macro_recording": _PLANNED,
    # modeling
    "add_chamfer": _STABLE,
    "add_fillet": _STABLE,
    "add_mate": _STABLE,
    "close_model": _STABLE,
    "create_assembly": _STABLE,
    "create_axis": _STABLE,
    "create_cut_extrude": _STABLE,
    "create_drawing": _STABLE,
    "create_extrusion": _STABLE,
    "create_loft": _STABLE,
    "create_part": _STABLE,
    "create_reference_plane": _STABLE,
    "create_reference_point": _STABLE,
    "create_revolve": _STABLE,
    "create_sweep": _STABLE,
    "delete_feature": _STABLE,
    "get_dimension": _STABLE,
    "insert_component": _STABLE,
    "list_components": _STABLE,
    "mirror_feature": _STABLE,
    "open_model": _STABLE,
    "pattern_circular": _STABLE,
    "rebuild_model": _STABLE,
    "rename_feature": _STABLE,
    "select_face_edges": _STABLE,
    "select_feature": _STABLE,
    "set_component_state": _STABLE,
    "set_dimension": _STABLE,
    "set_units": _STABLE,
    "suppress_feature": _STABLE,
    "undo": _STABLE,
    # server_admin
    "reset_circuit_breaker": _STABLE,
    # sketching
    "add_arc": _STABLE,
    "add_centerline": _STABLE,
    "add_circle": _STABLE,
    "add_ellipse": _STABLE,
    "add_line": _STABLE,
    "add_polygon": _STABLE,
    "add_rectangle": _STABLE,
    "add_sketch_constraint": _STABLE,
    "add_sketch_dimension": _STABLE,
    "add_spline": _STABLE,
    "check_sketch_fully_defined": _STABLE,
    "create_sketch": _STABLE,
    "exit_sketch": _STABLE,
    "sketch_circular_pattern": _STABLE,
    "sketch_linear_pattern": _STABLE,
    "sketch_mirror": _STABLE,
    "sketch_offset": _STABLE,
    "sketch_tutorial_simple_hole": _STABLE,
    "tutorial_simple_hole": _PLANNED,  # its cut step fails on real SolidWorks
    # template_management
    "apply_template": _PLANNED,
    "batch_apply_template": _PLANNED,
    "compare_templates": _STABLE,
    "extract_template": _PLANNED,
    "list_template_library": _PLANNED,
    "save_to_template_library": _PLANNED,
    # vba_generation
    "generate_vba_assembly_insert": _STABLE,
    "generate_vba_assembly_mates": _STABLE,
    "generate_vba_batch_export": _STABLE,
    "generate_vba_drawing_dimensions": _STABLE,
    "generate_vba_drawing_views": _STABLE,
    "generate_vba_extrusion": _STABLE,
    "generate_vba_file_operations": _STABLE,
    "generate_vba_macro_recorder": _STABLE,
    "generate_vba_part_modeling": _STABLE,
    "generate_vba_revolve": _STABLE,
}
