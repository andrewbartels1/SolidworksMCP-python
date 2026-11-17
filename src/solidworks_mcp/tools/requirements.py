"""What each registered tool needs from SolidWorks, in one reviewable table.

Every tool has exactly one requirement:

- **nothing**: works with no SolidWorks on the machine (it writes code,
  compares files on disk, or resets the server's own state);
- **installed**: reads SolidWorks' installed files (its type library or the
  Hole Wizard data); SolidWorks doesn't have to be running;
- **running**: calls the running SolidWorks. This is the default, so only
  the other two are listed.

No tool needs a licence above the one that runs SolidWorks: none calls an
add-in (Simulation, PDM, Routing, PhotoView) or a feature sold only with
Professional or Premium. ``ToolRegistrar`` adds ``needs:<requirement>`` to
each tool's tags, and ``docs/user-guide/tools-overview.md`` lists the tools
this table names (a test keeps the two the same).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum


class Requirement(StrEnum):
    """What a tool needs from SolidWorks, least first."""

    NOTHING = "nothing"
    INSTALLED = "installed"
    RUNNING = "running"


_VBA_WRITERS = (
    "generate_vba_code",
    "generate_vba_extrusion",
    "generate_vba_revolve",
    "generate_vba_assembly_insert",
    "generate_vba_drawing_views",
    "generate_vba_batch_export",
    "generate_vba_part_modeling",
    "generate_vba_assembly_mates",
    "generate_vba_drawing_dimensions",
    "generate_vba_file_operations",
    "generate_vba_macro_recorder",
)

#: The tools that don't need SolidWorks running; every other tool does.
REQUIREMENTS: Mapping[str, Requirement] = {
    **dict.fromkeys(_VBA_WRITERS, Requirement.NOTHING),
    "compare_templates": Requirement.NOTHING,
    "compare_drawing_versions": Requirement.NOTHING,
    "reset_circuit_breaker": Requirement.NOTHING,
    "discover_solidworks_docs": Requirement.INSTALLED,
    "search_solidworks_api_help": Requirement.INSTALLED,
    "lookup_api_method": Requirement.INSTALLED,
    "lookup_api_interface": Requirement.INSTALLED,
    "find_related_api_members": Requirement.INSTALLED,
    "list_hole_sizes": Requirement.INSTALLED,
}


def requirement_of(
    name: str, table: Mapping[str, Requirement] = REQUIREMENTS
) -> Requirement:
    """The requirement of the tool called ``name``.

    Args:
        name: The tool's registered name.
        table: The requirements table; the module's own by default.

    Returns:
        Requirement: The listed requirement, or ``running`` when the tool
        isn't listed.
    """
    return table.get(name, Requirement.RUNNING)
