"""How far to trust each registered tool, in one reviewable table.

Every tool has exactly one support level:

- **stable**: checked by a live test on real SolidWorks, every input used,
  no known fault (or it never calls SolidWorks and is unit-tested);
- **beta**: works on SolidWorks, but has a known fault or covers only part
  of its COM call;
- **experimental**: implemented, never checked on real SolidWorks;
- **planned**: registered, but no adapter implements it yet (its
  description says "Not available yet"); its reason names the queue item
  that builds it;
- **deprecated**: works, but another tool replaces it; it keeps working
  until the next major release after ``since``, when it is removed.

``ToolRegistrar`` adds the level to each tool's tags and, for a beta,
experimental or deprecated tool, a ``warning`` to its successful results and
the same sentence at the start of its description. Fixing a fault
in the queue's small-faults list moves its tool up a level here.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Set
from dataclasses import dataclass
from enum import StrEnum


class SupportLevel(StrEnum):
    """The five support levels: four by trust, then the replaced tools."""

    STABLE = "stable"
    BETA = "beta"
    EXPERIMENTAL = "experimental"
    PLANNED = "planned"
    DEPRECATED = "deprecated"


@dataclass(frozen=True)
class Support:
    """One tool's support level and why it isn't higher.

    Attributes:
        level: The tool's support level.
        reason: One line on the gap; empty only for a stable tool. A
            deprecated tool's reason is ``"use `<tool>`."`` or
            ``"no replacement."``.
        since: The version a deprecated tool was deprecated in; empty for
            every other level.
    """

    level: SupportLevel
    reason: str = ""
    since: str = ""

    def __post_init__(self) -> None:
        """Require a reason below stable, and a version for a deprecated tool.

        Raises:
            ValueError: If a level below stable has no reason, a stable tool
                has one, or ``since`` is given for any level but deprecated
                (or missing for a deprecated tool).
        """
        if (self.level is SupportLevel.STABLE) == bool(self.reason):
            raise ValueError(
                "a reason is required below stable, and only there: "
                f"{self.level.value!r} with reason {self.reason!r}"
            )
        if (self.level is SupportLevel.DEPRECATED) != bool(self.since):
            raise ValueError(
                "a deprecated tool needs `since`, and only it: "
                f"{self.level.value!r} with since {self.since!r}"
            )

    def warning(self) -> str | None:
        """The sentence a successful beta, experimental or deprecated result carries.

        Returns:
            str | None: ``"Beta: <reason>"``, ``"Experimental: <reason>"`` or
            ``"Deprecated: <reason>"``; None for stable and planned tools (a
            planned tool never succeeds).
        """
        if self.level in (
            SupportLevel.BETA,
            SupportLevel.EXPERIMENTAL,
            SupportLevel.DEPRECATED,
        ):
            return f"{self.level.value.capitalize()}: {self.reason}"
        return None

    def replacement(self) -> str | None:
        """The tool a deprecated tool's reason names.

        Returns:
            str | None: The name in backticks in ``"use `<tool>`."``; None for
            ``"no replacement."`` and for every other level.
        """
        if self.level is not SupportLevel.DEPRECATED:
            return None
        match = re.fullmatch(r"use `(\w+)`\.", self.reason)
        return match.group(1) if match else None


def _major(version: str) -> int:
    """The major number of a ``X.Y.Z`` version."""
    return int(version.split(".", 1)[0])


def deprecation_problems(
    levels: Mapping[str, Support], registered: Set[str], version: str
) -> list[str]:
    """What is wrong with the table's deprecated entries.

    A deprecated tool names a registered replacement (or says there is
    none), and is gone once the package's major version passes the one it
    was deprecated in.

    Args:
        levels: The support table.
        registered: The names of the registered tools.
        version: The package version, ``X.Y.Z``.

    Returns:
        list[str]: One line per problem; empty when there is none.
    """
    problems = []
    for name, support in sorted(levels.items()):
        if support.level is not SupportLevel.DEPRECATED:
            continue
        replacement = support.replacement()
        if replacement is None and support.reason != "no replacement.":
            problems.append(
                f"{name}: the reason must be 'use `<tool>`.' or 'no replacement.'"
            )
        elif replacement is not None and replacement not in registered:
            problems.append(f"{name}: its replacement {replacement!r} is not a tool")
        if name in registered and _major(version) > _major(support.since):
            problems.append(
                f"{name}: deprecated in {support.since}, so remove it before {version}"
            )
    return problems


def planned_problems(levels: Mapping[str, Support]) -> list[str]:
    """Planned tools whose reason does not name the queue item that builds them.

    Args:
        levels: The support table.

    Returns:
        list[str]: One line per problem; empty when there is none.
    """
    return [
        f"{name}: a planned tool's reason names its queue item"
        for name, support in sorted(levels.items())
        if support.level is SupportLevel.PLANNED
        and not re.search(r"\bqueue item \d+\b", support.reason)
    ]


#: Tool families that never call SolidWorks; their tools are stable on unit
#: tests alone.
OFFLINE_FAMILIES = frozenset({"docs_discovery", "server_admin", "vba_generation"})

#: The release the eight duplicates of issue #174 were deprecated in.
_DEPRECATED_IN = "2.1.0"

_STABLE = Support(SupportLevel.STABLE)
#: New in queue item 22 (hole-wizard-library); stable once its live check passes.
_BETA_HOLE_LIBRARY = Support(
    SupportLevel.BETA, "not yet checked on SolidWorks (queue item 22's live check)."
)
_PLANNED_DRAWING = Support(
    SupportLevel.PLANNED, "planned in queue item 12 (the drawing pack)."
)


def _deprecated(replacement: str | None) -> Support:
    """A tool deprecated in 2.1.0 in favour of ``replacement`` (or none).

    Args:
        replacement: The registered tool that replaces it, or None.

    Returns:
        Support: The deprecated entry.
    """
    reason = f"use `{replacement}`." if replacement else "no replacement."
    return Support(SupportLevel.DEPRECATED, reason, since=_DEPRECATED_IN)


SUPPORT_LEVELS: dict[str, Support] = {
    # analysis
    "calculate_mass_properties": _deprecated("get_mass_properties"),
    "check_interference": _STABLE,
    "get_mass_properties": _STABLE,
    "verify_model": _STABLE,
    # automation
    "generate_vba_code": _STABLE,
    # docs_discovery
    "discover_solidworks_docs": _STABLE,
    "find_related_api_members": _STABLE,
    "lookup_api_interface": _STABLE,
    "lookup_api_method": _STABLE,
    "search_solidworks_api_help": _STABLE,
    # drawing
    "add_dimension": _PLANNED_DRAWING,
    "add_drawing_view": _deprecated("create_drawing_view"),
    "add_note": _STABLE,
    "auto_center_marks": _STABLE,
    "auto_dimension_view": _PLANNED_DRAWING,
    "check_drawing_standards": _PLANNED_DRAWING,
    "create_detail_view": _PLANNED_DRAWING,
    "create_drawing_view": _STABLE,
    "create_section_view": _PLANNED_DRAWING,
    "create_technical_drawing": _STABLE,
    "list_drawing_views": _STABLE,
    "update_sheet_format": _PLANNED_DRAWING,
    "update_title_block": _PLANNED_DRAWING,
    # drawing_analysis
    "compare_drawing_versions": _STABLE,
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
    "export_dwg": _STABLE,
    "export_iges": _STABLE,
    "export_image": _STABLE,
    "export_pdf": _STABLE,
    "export_step": _STABLE,
    "export_stl": _STABLE,
    # file_management
    "activate_document": _STABLE,
    "classify_feature_tree": _STABLE,
    "get_file_properties": _deprecated("get_model_info"),
    "get_model_info": _STABLE,
    "get_selected_entities": _STABLE,
    "list_configurations": _STABLE,
    "create_configuration": _STABLE,
    "activate_configuration": _STABLE,
    "delete_configuration": _STABLE,
    "list_features": _STABLE,
    "list_open_documents": _STABLE,
    "load_assembly": _deprecated("open_model"),
    "load_part": _deprecated("open_model"),
    "pack_and_go_assembly": _STABLE,
    "save_as": _STABLE,
    "save_assembly": _deprecated("save_file"),
    "save_body_as_part": _STABLE,
    "save_file": _STABLE,
    "save_part": _deprecated("save_file"),
    # macro_recording
    "execute_macro": _STABLE,
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
    "pattern_linear": _STABLE,
    "create_shell": _STABLE,
    "add_draft": _STABLE,
    "create_rib": _STABLE,
    "create_hole": _STABLE,
    "list_hole_sizes": _BETA_HOLE_LIBRARY,
    "add_cosmetic_thread": _STABLE,
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
    "sketch_convert_entities": _STABLE,
    "sketch_tutorial_simple_hole": _deprecated(None),
    # template_management
    "compare_templates": _STABLE,
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
