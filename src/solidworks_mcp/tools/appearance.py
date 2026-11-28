"""Appearance tools: colour the part, a feature, a body or a face, and read it back.

A colour shows from the nearest level that has one: a face over its feature,
a feature over its body, a body over the part (SolidWorks's appearance
hierarchy). ``set_appearance`` sets or removes a level's colour and reads it
back; ``get_appearance`` says what shows and where it comes from (queue
item 36).
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from ..adapters.base import AppearanceParameters, AppearanceTarget, SolidWorksAdapter
from .input_compat import CompatInput
from .tool_boundary import (
    normalize_input,
    require_capability,
    require_success,
    with_tool_boundary,
)


class AppearanceTargetInput(CompatInput):
    """Input schema naming what a colour is read from or set on.

    Attributes:
        feature (str | None): A feature by name.
        body (str | None): A body by name.
        face_point (list[float] | None): ``[x, y, z]`` mm on a face.
    """

    feature: str | None = Field(
        default=None,
        min_length=1,
        description="A feature by its name in the tree, e.g. 'Boss-Extrude1'",
    )
    body: str | None = Field(
        default=None, min_length=1, description="A solid body, as list_bodies names it"
    )
    face_point: list[float] | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="[x, y, z] in mm, a point on the face; give one target, or "
        "none for the whole part",
    )


class SetAppearanceInput(AppearanceTargetInput):
    """Input schema for setting or removing a colour.

    Attributes:
        color (list[int] | str | None): ``[r, g, b]`` 0-255 or ``#rrggbb``.
        transparency (float): 0 opaque to 1 clear.
        reset (bool): Remove the target's own colour.
    """

    color: list[int] | str | None = Field(
        default=None,
        description="[r, g, b], each 0-255, or '#rrggbb', e.g. [31, 119, 180] "
        "or '#1f77b4'",
    )
    transparency: float = Field(
        default=0.0, ge=0.0, le=1.0, description="0 opaque (default) to 1 clear"
    )
    reset: bool = Field(
        default=False,
        description="Remove the feature's, body's or face's own colour so the "
        "one above it shows; give no color",
    )


def _brief(data: dict[str, Any]) -> str:
    """'#1f77b4 on feature Boss-Extrude1'."""
    target = data.get("target", "part")
    named = data.get(target) or data.get("face_point")
    where = (
        f"{target} {named}" if named is not None and target != "part" else "the part"
    )
    return f"{data.get('hex')} on {where}"


async def register_appearance_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: Any
) -> int:
    """Register the appearance tools with FastMCP.

    Args:
        mcp (FastMCP): The server.
        adapter (SolidWorksAdapter): The adapter the tools call.
        config (Any): Configuration values (unused).

    Returns:
        int: How many tools were registered.
    """
    mcp = with_tool_boundary(mcp)

    @mcp.tool()
    async def set_appearance(input_data: SetAppearanceInput) -> dict[str, Any]:
        """Colour the active part, one feature, one body or the face at a point, or remove a colour.

        Give `color` ([r, g, b] 0-255 or '#rrggbb') and at most one target:
        `feature`, `body` (as `list_bodies` names it) or `face_point`; none
        colours the whole part. A face's colour shows over its feature's, a
        feature's over its body's, a body's over the part's. `reset: true`
        removes a feature's, body's or face's own colour. Fails, changing
        nothing, for two targets, an unknown feature or body, or a point on no
        face. Needs: an open part. Changes: the colour only, not the geometry.
        Returns: `appearance` with `target`, the colour read back (`color`,
        `hex`, `transparency`), or after a reset what now `showing`.

        Args:
            input_data: `color` and an optional target and `transparency`,
                or a target and `reset`.

        Returns:
            dict[str, Any]: The colour as SolidWorks now holds it.
        """
        input_data = normalize_input(input_data, SetAppearanceInput)
        require_capability(
            adapter, "set_appearance", "Active adapter can't set colours"
        )
        result = await adapter.set_appearance(
            AppearanceParameters(**input_data.model_dump())
        )
        require_success(result, "Failed to set the colour")
        data = result.data or {}
        if data.get("reset"):
            showing = data.get("showing") or {}
            message = (
                f"Removed the {data.get('target')}'s colour; "
                f"{showing.get('hex')} from the {showing.get('level')} shows"
            )
        else:
            message = f"Coloured: {_brief(data)}"
        return {
            "status": "success",
            "message": message,
            "appearance": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def get_appearance(
        input_data: AppearanceTargetInput | None = None,
    ) -> dict[str, Any]:
        """Read the colour the active part, a feature, a body or the face at a point shows, and where it comes from.

        Give at most one target (`feature`, `body` or `face_point`); none reads
        the part. Needs: an open part. Read-only. Returns: `appearance` with
        `target`, `color` ([r, g, b] 0-255), `hex`, `transparency` and
        `level`: the face, feature, body or part the colour comes from.

        Args:
            input_data: An optional target.

        Returns:
            dict[str, Any]: The colour showing and its level.
        """
        input_data = normalize_input(input_data or {}, AppearanceTargetInput)
        require_capability(
            adapter, "get_appearance", "Active adapter can't read colours"
        )
        result = await adapter.get_appearance(
            AppearanceTarget(**input_data.model_dump())
        )
        require_success(result, "Failed to read the colour")
        data = result.data or {}
        return {
            "status": "success",
            "message": f"{_brief(data)}, from the {data.get('level')}",
            "appearance": data,
            "execution_time": result.execution_time,
        }

    return 2
