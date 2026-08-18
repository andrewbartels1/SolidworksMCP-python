"""Skill-routing tool for CAD-generation intent (issue #42).

Exposes the ``solidworks-native`` / ``text-to-cad`` / ``mesh-concept`` skill-
family contract directly as an MCP tool, with **no internal LLM call**. The
calling model (already an LLM, driving this MCP session) reasons about which
family fits a given request using this tool's own parameter description,
then calls ``get_skill_route`` with its decision to get back a validated,
bounded execution contract: allowed tools (checked against the real
``SolidWorksAdapter`` interface, never invented), required validation steps,
and expected outputs.

This intentionally does not call out to any LLM provider itself - the model
already in the loop (via MCP tool calls) does the classification. See
``openspec/changes/cad-skill-router/design.md`` for the earlier
dashboard-integrated, LLM-driven design this replaces, and its own revision
notes for why.
"""

from typing import Any, Literal

from fastmcp import FastMCP
from loguru import logger
from pydantic import Field

from ..adapters.base import SolidWorksAdapter
from .input_compat import CompatInput

_STUB_FALLBACK_MESSAGES: dict[str, str] = {
    "text-to-cad": (
        "The text-to-cad branch has no backing implementation yet "
        "(see issue #43). This route is a placeholder until that lands."
    ),
    "mesh-concept": (
        "The mesh-concept branch has no backing implementation yet. "
        "This route is a placeholder until one exists."
    ),
}

_SOLIDWORKS_NATIVE_VALIDATION_STEPS = [
    "Inspect before executing: read model/feature-tree state before proposing edits.",
    "Verify by artifact after execution: confirm via model info, feature-tree checks, "
    "mass properties, or exports - not by prose.",
]
_SOLIDWORKS_NATIVE_EXPECTED_OUTPUTS = [
    "Updated or created SolidWorks document reflecting the requested change.",
    "Post-execution model info / feature-tree / mass-properties readback.",
]


def _adapter_capability_names() -> frozenset[str]:
    """Public capability names declared on ``SolidWorksAdapter``.

    Plain class introspection - no running process, no network call, no MCP
    tool-catalog dependency. Validates that a name is a real adapter
    capability, not that a corresponding ``@mcp.tool()`` wrapper exists for
    it (the two track each other by convention, not by enforcement).

    Returns:
        frozenset[str]: Every public (non-underscore-prefixed) callable
        attribute declared on ``SolidWorksAdapter``.
    """
    return frozenset(
        name
        for name in dir(SolidWorksAdapter)
        if not name.startswith("_") and callable(getattr(SolidWorksAdapter, name, None))
    )


def filter_to_adapter_capabilities(proposed_tools: list[str]) -> list[str]:
    """Fail-closed allowlist filter against real ``SolidWorksAdapter`` capabilities.

    Args:
        proposed_tools: Candidate tool/capability names to validate.

    Returns:
        list[str]: The subset of *proposed_tools* that are real adapter
        capabilities, in their original order. Never raises on an unknown
        name - it is silently excluded.
    """
    valid_names = _adapter_capability_names()
    return [name for name in proposed_tools if name in valid_names]


class SkillRouteInput(CompatInput):
    """Input schema for ``get_skill_route``.

    Attributes:
        family: The skill family the caller has already selected.
    """

    family: Literal["solidworks-native", "text-to-cad", "mesh-concept"] = Field(
        description=(
            "Which CAD-generation skill family applies to the current request. "
            "Decide this yourself before calling this tool, based on what the "
            "user actually asked for:\n"
            "- solidworks-native: editable SolidWorks modeling - editing an "
            "existing feature tree, creating/editing an assembly, or any other "
            "operation on a document that stays live and editable in SolidWorks.\n"
            "- text-to-cad: generating a brand-new part from a natural-language "
            "description with no existing SolidWorks document open.\n"
            "- mesh-concept: quick concept geometry or a browser-preview-only "
            "result with no need for an editable SolidWorks feature tree."
        )
    )


async def register_skill_router_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: dict[str, Any]
) -> int:
    """Register the skill-routing tool with FastMCP.

    Args:
        mcp (FastMCP): The mcp value.
        adapter (SolidWorksAdapter): Adapter instance (unused directly - this
            tool only introspects the ``SolidWorksAdapter`` class, not a live
            instance - kept for registration-signature consistency with every
            other tool module).
        config (dict[str, Any]): Configuration values (unused).

    Returns:
        int: The number of tools registered.
    """
    _ = adapter, config

    @mcp.tool()
    async def get_skill_route(input_data: SkillRouteInput) -> dict[str, Any]:
        """Return the validated, bounded execution contract for a CAD-generation skill family.

        Call this after deciding (yourself, no separate model call) which of
        the three named skill families - ``solidworks-native``,
        ``text-to-cad``, ``mesh-concept`` - fits the current request. Returns
        the tools you're allowed to use, required validation steps, and
        expected outputs for that family. A non-null ``fallback`` in the
        response means the family has no backing implementation yet -
        `allowed_tools` will be empty and nothing should be executed for it.

        Args:
            input_data (SkillRouteInput): The selected skill family.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.
        """
        try:
            family = input_data.family

            if family == "solidworks-native":
                return {
                    "status": "success",
                    "message": "solidworks-native route: full adapter capability set allowed.",
                    "execution_time": 0.0,
                    "data": {
                        "family": family,
                        "allowed_tools": sorted(_adapter_capability_names()),
                        "validation_steps": list(_SOLIDWORKS_NATIVE_VALIDATION_STEPS),
                        "expected_outputs": list(_SOLIDWORKS_NATIVE_EXPECTED_OUTPUTS),
                        "fallback": None,
                    },
                }

            return {
                "status": "success",
                "message": f"{family} route: not yet executable.",
                "execution_time": 0.0,
                "data": {
                    "family": family,
                    "allowed_tools": [],
                    "validation_steps": [],
                    "expected_outputs": [],
                    "fallback": _STUB_FALLBACK_MESSAGES[family],
                },
            }
        except Exception as e:
            logger.error(f"Error in get_skill_route tool: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    return 1
