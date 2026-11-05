"""MCP behaviour hints for every registered tool, in one reviewable table.

An MCP client reads a tool's ``title`` and its ``readOnlyHint``,
``destructiveHint`` and ``idempotentHint`` annotations to decide, for
example, whether to ask the user before calling it. ``ToolRegistrar``
applies the entry for each tool at registration, and refuses a tool that has
no entry, so this table always matches the registered tools.

The hints describe what a tool is for, read from its adapter calls:

- **read-only**: changes neither the model, SolidWorks' state nor any file;
- **destructive**: may delete, overwrite or discard something the user
  can't get back from the feature tree (a file on disk, a deleted feature,
  unsaved work, a run macro);
- **idempotent**: calling it again with the same input changes nothing
  more.

A tool SolidWorks can't yet carry out (it reports ``unsupported``) still
gets the hints of what it is meant to do.
"""

from __future__ import annotations

from dataclasses import dataclass

from mcp.types import ToolAnnotations


@dataclass(frozen=True)
class ToolHints:
    """One tool's title and behaviour hints.

    Attributes:
        title: A short human-readable name for the tool.
        read_only: The tool changes nothing.
        destructive: The tool may delete, overwrite or discard work.
        idempotent: Repeating a call with the same input has no further effect.
    """

    title: str
    read_only: bool
    destructive: bool
    idempotent: bool

    def __post_init__(self) -> None:
        """Reject combinations that contradict each other.

        Raises:
            ValueError: If a read-only tool is marked destructive or not
                idempotent.
        """
        if self.read_only and (self.destructive or not self.idempotent):
            raise ValueError(
                f"{self.title!r}: a read-only tool is never destructive "
                "and always idempotent"
            )

    def annotations(self) -> ToolAnnotations:
        """The hints as MCP tool annotations.

        Returns:
            ToolAnnotations: ``title`` plus the three hints.
        """
        return ToolAnnotations(
            title=self.title,
            readOnlyHint=self.read_only,
            destructiveHint=self.destructive,
            idempotentHint=self.idempotent,
        )


def _reads(title: str) -> ToolHints:
    """A tool that only reads."""
    return ToolHints(title, read_only=True, destructive=False, idempotent=True)


def _adds(title: str) -> ToolHints:
    """A tool that adds something; each call adds another."""
    return ToolHints(title, read_only=False, destructive=False, idempotent=False)


def _sets(title: str) -> ToolHints:
    """A tool that sets a state; repeating the call changes nothing more."""
    return ToolHints(title, read_only=False, destructive=False, idempotent=True)


def _overwrites(title: str) -> ToolHints:
    """A tool that writes or replaces a file or value, the same each time."""
    return ToolHints(title, read_only=False, destructive=True, idempotent=True)


def _discards(title: str) -> ToolHints:
    """A tool that deletes, discards or runs something; each call acts again."""
    return ToolHints(title, read_only=False, destructive=True, idempotent=False)


#: Every registered tool's hints, grouped by the module that defines it.
TOOL_HINTS: dict[str, ToolHints] = {
    # analysis
    "calculate_mass_properties": _reads("Calculate Mass Properties"),
    "get_mass_properties": _reads("Get Mass Properties"),
    "check_interference": _reads("Check Assembly Interference"),
    "analyze_geometry": _reads("Analyze Geometry"),
    "get_material_properties": _reads("Get Material Properties"),
    "verify_model": _reads("Verify Model Against Expectations"),
    # automation
    "generate_vba_code": _reads("Generate VBA Code"),
    "automation_start_macro_recording": _adds("Start Macro Recording (Automation)"),
    "automation_stop_macro_recording": _discards("Stop Macro Recording (Automation)"),
    "batch_process_files": _discards("Batch Process Files"),
    "manage_design_table": _adds("Manage Design Table"),
    "execute_workflow": _discards("Execute Workflow"),
    "create_template": _overwrites("Create Template File"),
    "optimize_performance": _sets("Optimize SolidWorks Performance"),
    # docs_discovery
    "discover_solidworks_docs": _sets("Rebuild SolidWorks API Index"),
    "search_solidworks_api_help": _reads("Search SolidWorks API"),
    "lookup_api_method": _reads("Look Up API Method"),
    "lookup_api_interface": _reads("Look Up API Interface"),
    "find_related_api_members": _reads("Find Related API Members"),
    # drawing
    "create_drawing_view": _adds("Create Drawing View"),
    "add_dimension": _adds("Add Drawing Dimension"),
    "add_note": _adds("Add Drawing Note"),
    "create_section_view": _adds("Create Section View"),
    "create_detail_view": _adds("Create Detail View"),
    "update_sheet_format": _sets("Update Sheet Format"),
    "auto_dimension_view": _adds("Auto-Dimension Drawing View"),
    "check_drawing_standards": _reads("Check Drawing Standards"),
    "create_technical_drawing": _overwrites("Create Technical Drawing"),
    "add_drawing_view": _discards("Add, Update or Remove Drawing View"),
    "add_annotation": _adds("Add Drawing Annotation"),
    "update_title_block": _sets("Update Title Block"),
    "list_drawing_views": _reads("List Drawing Views"),
    "auto_center_marks": _adds("Add Centre Marks"),
    # drawing_analysis
    "analyze_drawing_comprehensive": _reads("Analyze Drawing (All Checks)"),
    "analyze_drawing_dimensions": _reads("Analyze Drawing Dimensions"),
    "analyze_drawing_annotations": _reads("Analyze Drawing Annotations"),
    "check_drawing_compliance": _reads("Check Drawing Compliance"),
    "analyze_drawing_views": _reads("Analyze Drawing Views"),
    "generate_drawing_report": _reads("Generate Drawing Report"),
    "compare_drawing_versions": _reads("Compare Drawing Files"),
    "validate_drawing_completeness": _reads("Validate Drawing Completeness"),
    # drawing_automation
    "insert_model_dimensions": _adds("Insert Model Dimensions"),
    "arrange_dimensions": _sets("Arrange Drawing Dimensions"),
    "insert_bom_table": _adds("Insert BOM Table"),
    "add_gtol": _adds("Add GD&T Frame"),
    "add_datum_tag": _adds("Add Datum Tag"),
    "set_sheet_scale": _sets("Set Sheet Scale"),
    "generate_drawing_package": _overwrites("Generate Drawing Package"),
    # engineering_data
    "list_model_dimensions": _reads("List Model Dimensions"),
    "measure_entities": _reads("Measure Entities"),
    "get_material": _reads("Get Material"),
    "set_material": _sets("Set Material"),
    "list_available_materials": _reads("List Available Materials"),
    "get_custom_properties": _reads("Get Custom Properties"),
    "set_custom_property": _overwrites("Set Custom Property"),
    "export_flat_pattern": _overwrites("Export Flat Pattern"),
    # export
    "export_step": _overwrites("Export STEP"),
    "export_iges": _overwrites("Export IGES"),
    "export_stl": _overwrites("Export STL"),
    "export_pdf": _overwrites("Export PDF"),
    "export_dwg": _overwrites("Export DWG"),
    "export_image": _overwrites("Export Image"),
    "batch_export": _overwrites("Batch Export"),
    # file_management
    "save_file": _overwrites("Save File"),
    "save_as": _overwrites("Save As"),
    "get_file_properties": _reads("Get File Properties"),
    "get_model_info": _reads("Get Model Info"),
    "list_features": _reads("List Features"),
    "get_selected_entities": _reads("Get Selected Entities"),
    "classify_feature_tree": _reads("Classify Feature Tree"),
    "list_configurations": _reads("List Configurations"),
    "manage_file_properties": _discards("Manage File Properties"),
    "convert_file_format": _overwrites("Convert File Format"),
    "batch_file_operations": _discards("Batch File Operations"),
    "load_part": _sets("Load Part"),
    "load_assembly": _sets("Load Assembly"),
    "save_part": _overwrites("Save Part"),
    "save_assembly": _overwrites("Save Assembly"),
    "pack_and_go_assembly": _overwrites("Pack and Go Assembly"),
    "list_open_documents": _reads("List Open Documents"),
    "activate_document": _sets("Activate Document"),
    "save_body_as_part": _overwrites("Save Body as Part"),
    # macro_recording
    "start_macro_recording": _adds("Start Macro Recording"),
    "stop_macro_recording": _discards("Stop Macro Recording"),
    "execute_macro": _discards("Run Macro"),
    "analyze_macro": _reads("Analyze Macro"),
    "batch_execute_macros": _discards("Run Macros in Batch"),
    "optimize_macro": _reads("Optimize Macro"),
    "create_macro_library": _overwrites("Create Macro Library"),
    # modeling
    "open_model": _sets("Open Model"),
    "create_part": _adds("Create Part"),
    "create_assembly": _adds("Create Assembly"),
    "create_drawing": _adds("Create Drawing"),
    "close_model": _discards("Close Model"),
    "create_extrusion": _adds("Create Extrusion"),
    "create_revolve": _adds("Create Revolve"),
    "get_dimension": _reads("Get Dimension"),
    "set_dimension": _sets("Set Dimension"),
    "set_units": _sets("Set Units"),
    "create_cut_extrude": _adds("Create Extruded Cut"),
    "add_fillet": _adds("Add Fillet"),
    "add_chamfer": _adds("Add Chamfer"),
    "create_sweep": _adds("Create Sweep"),
    "create_loft": _adds("Create Loft"),
    "insert_component": _adds("Insert Component"),
    "add_mate": _adds("Add Mate"),
    "list_components": _reads("List Components"),
    "delete_feature": _discards("Delete Feature"),
    "suppress_feature": _sets("Suppress or Unsuppress Feature"),
    "rename_feature": _sets("Rename Feature"),
    "select_feature": _sets("Select Feature"),
    "select_face_edges": _sets("Select Face Edges"),
    "rebuild_model": _sets("Rebuild Model"),
    "undo": _discards("Undo"),
    "create_reference_plane": _adds("Create Reference Plane"),
    "create_axis": _adds("Create Reference Axis"),
    "create_reference_point": _adds("Create Reference Point"),
    "mirror_feature": _adds("Mirror Feature"),
    "pattern_circular": _adds("Circular Pattern"),
    # sketching
    "create_sketch": _adds("Create Sketch"),
    "add_line": _adds("Add Sketch Line"),
    "add_circle": _adds("Add Sketch Circle"),
    "add_rectangle": _adds("Add Sketch Rectangle"),
    "exit_sketch": _sets("Exit Sketch"),
    "check_sketch_fully_defined": _reads("Check Sketch Fully Defined"),
    "add_arc": _adds("Add Sketch Arc"),
    "add_spline": _adds("Add Sketch Spline"),
    "add_centerline": _adds("Add Sketch Centerline"),
    "add_polygon": _adds("Add Sketch Polygon"),
    "add_ellipse": _adds("Add Sketch Ellipse"),
    "add_sketch_constraint": _adds("Add Sketch Relation"),
    "add_sketch_dimension": _adds("Add Sketch Dimension"),
    "sketch_linear_pattern": _adds("Sketch Linear Pattern"),
    "sketch_circular_pattern": _adds("Sketch Circular Pattern"),
    "sketch_mirror": _adds("Mirror Sketch Entities"),
    "sketch_offset": _adds("Offset Sketch Entities"),
    "sketch_tutorial_simple_hole": _adds("Tutorial: Hole Sketch"),
    "tutorial_simple_hole": _adds("Tutorial: Simple Hole"),
    # template_management
    "extract_template": _overwrites("Extract Template"),
    "apply_template": _overwrites("Apply Template"),
    "batch_apply_template": _overwrites("Apply Template in Batch"),
    "compare_templates": _reads("Compare Templates"),
    "save_to_template_library": _overwrites("Save to Template Library"),
    "list_template_library": _reads("List Template Library"),
    # vba_generation
    "generate_vba_extrusion": _reads("Generate VBA: Extrusion"),
    "generate_vba_revolve": _reads("Generate VBA: Revolve"),
    "generate_vba_assembly_insert": _reads("Generate VBA: Insert Component"),
    "generate_vba_drawing_views": _reads("Generate VBA: Drawing Views"),
    "generate_vba_batch_export": _reads("Generate VBA: Batch Export"),
    "generate_vba_part_modeling": _reads("Generate VBA: Part Modeling"),
    "generate_vba_assembly_mates": _reads("Generate VBA: Assembly Mates"),
    "generate_vba_drawing_dimensions": _reads("Generate VBA: Drawing Dimensions"),
    "generate_vba_file_operations": _reads("Generate VBA: File Operations"),
    "generate_vba_macro_recorder": _reads("Generate VBA: Macro Recorder"),
}
