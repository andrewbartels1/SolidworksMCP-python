"""Multi-body tools: see, combine, split, move, copy, delete and scale bodies.

A part made with ``create_extrusion`` and ``merge_result: false`` holds
several solid bodies. ``list_bodies`` names them; the other five tools act
on them by those names, and each reply gives the bodies, their count and the
volume before and after, so a step that did nothing (a subtract with no
overlap, a split that made no new body) fails instead of passing silently
(queue item 35).
"""

from __future__ import annotations

from typing import Any, Literal

from fastmcp import FastMCP
from pydantic import Field

from ..adapters.base import (
    CombineBodiesParameters,
    DeleteBodiesParameters,
    MoveCopyBodyParameters,
    ScaleBodyParameters,
    SolidWorksAdapter,
    SplitBodyParameters,
)
from .input_compat import CompatInput
from .tool_boundary import (
    normalize_input,
    require_capability,
    require_success,
    with_tool_boundary,
)

#: A vector in mm or degrees.
Vector = list[float]


def _vector(description: str) -> Any:
    """A ``[x, y, z]`` field defaulting to zeros."""
    return Field(
        default_factory=lambda: [0.0, 0.0, 0.0],
        min_length=3,
        max_length=3,
        description=description,
    )


class CombineBodiesInput(CompatInput):
    """Input schema for combining bodies.

    Attributes:
        operation (str): ``add``, ``subtract`` or ``common``.
        main_body (str): The body the result keeps.
        tool_bodies (list[str]): The bodies combined with it.
    """

    operation: Literal["add", "subtract", "common"] = Field(
        description="'add' joins the bodies, 'subtract' removes the tool bodies "
        "from the main body, 'common' keeps only the volume they share"
    )
    main_body: str = Field(
        min_length=1, description="The body to keep, as list_bodies names it"
    )
    tool_bodies: list[str] = Field(
        min_length=1,
        description="The bodies to add, subtract or intersect; they are consumed",
    )


class SplitBodyInput(CompatInput):
    """Input schema for splitting bodies.

    Attributes:
        tool (str): The plane or sketch that cuts.
    """

    tool: str = Field(
        min_length=1,
        description="A plane (e.g. 'Right Plane') or a sketch that crosses the "
        "bodies all the way; every body it crosses is split",
    )


class MoveCopyBodyInput(CompatInput):
    """Input schema for moving or copying bodies.

    Attributes:
        bodies (list[str]): The bodies.
        translate (list[float]): ``[x, y, z]`` mm.
        rotate (list[float]): ``[x, y, z]`` degrees about ``rotation_point``.
        rotation_point (list[float]): ``[x, y, z]`` mm.
        as_copy (bool): Copy instead of move.
        copies (int): How many copies.
    """

    bodies: list[str] = Field(
        min_length=1,
        description="The bodies to move or copy, as list_bodies names them",
    )
    translate: Vector = _vector("Translation [x, y, z] in mm")
    rotate: Vector = _vector(
        "Rotation [x, y, z] in degrees about the model axes through rotation_point"
    )
    rotation_point: Vector = _vector("Centre of the rotation [x, y, z] in mm")
    as_copy: bool = Field(
        default=False, description="Copy the bodies instead of moving them"
    )
    copies: int = Field(
        default=1,
        ge=1,
        le=50,
        description="With as_copy, how many copies; copy n is moved n times "
        "the translation",
    )


class DeleteBodiesInput(CompatInput):
    """Input schema for deleting or keeping bodies.

    Attributes:
        bodies (list[str]): The bodies.
        keep (bool): Keep these and delete the rest.
    """

    bodies: list[str] = Field(
        min_length=1, description="The bodies, as list_bodies names them"
    )
    keep: bool = Field(
        default=False,
        description="false deletes these bodies; true keeps only these and "
        "deletes the rest",
    )


class ScaleBodyInput(CompatInput):
    """Input schema for scaling bodies.

    Attributes:
        scale (float | None): One factor.
        scale_xyz (list[float] | None): ``[x, y, z]`` factors.
        about (str): ``centroid`` or ``origin``.
        bodies (list[str] | None): The bodies; all when omitted.
    """

    scale: float | None = Field(
        default=None, gt=0, description="One factor for all three axes, e.g. 2"
    )
    scale_xyz: list[float] | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="Factors [x, y, z], each above 0; instead of scale",
    )
    about: Literal["centroid", "origin"] = Field(
        default="centroid",
        description="Scale about each body's centroid or the part's origin",
    )
    bodies: list[str] | None = Field(
        default=None, description="The bodies to scale; all when omitted"
    )


def _summary(data: dict[str, Any]) -> str:
    """'2 bodies, 16,000.0 mm³ -> 1 body, 15,214.6 mm³'."""

    def part(count: Any, volume: Any) -> str:
        plural = "body" if count == 1 else "bodies"
        return f"{count} {plural}, {float(volume or 0):,.1f} mm³"

    return (
        f"{part(data.get('body_count_before'), data.get('volume_before_mm3'))} -> "
        f"{part(data.get('body_count_after'), data.get('volume_after_mm3'))}"
    )


async def register_body_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: Any
) -> int:
    """Register the multi-body tools with FastMCP.

    Args:
        mcp (FastMCP): The server.
        adapter (SolidWorksAdapter): The adapter the tools call.
        config (Any): Configuration values (unused).

    Returns:
        int: How many tools were registered.
    """
    mcp = with_tool_boundary(mcp)

    @mcp.tool()
    async def list_bodies() -> dict[str, Any]:
        """List the active part's solid bodies by name, with each one's volume and bounding box.

        Use it before any body tool (`combine_bodies`, `split_body`,
        `move_copy_body`, `delete_bodies`, `scale_body`, `save_body_as_part`):
        they take these names. A part gets several bodies from
        `create_extrusion` with `merge_result: false`, a split or a copy.
        Needs: an open part. Read-only. Returns: `bodies`, each with `name`,
        `volume_mm3` and `bounding_box_mm` (`min`, `max`, `size`), `count` and
        `total_volume_mm3`.
        """
        require_capability(adapter, "list_bodies", "Active adapter can't read bodies")
        result = await adapter.list_bodies()
        require_success(result, "Failed to list bodies")
        data = result.data or {}
        return {
            "status": "success",
            "message": f"{data.get('count', 0)} solid bodies",
            **data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def combine_bodies(input_data: CombineBodiesInput) -> dict[str, Any]:
        """Combine bodies of the active part: add them, subtract tool bodies from a main body, or keep their common volume.

        E.g. a mould core: subtract the part from a block. The tool bodies are
        consumed and the result is one body (SolidWorks renames it after the
        feature, e.g. `Combine1`). Fails, changing nothing, when a name is
        unknown, the main body is also a tool, an add's bodies don't touch, or
        a subtract or common removes no volume. Needs: a part with the bodies
        (`list_bodies`). Changes: adds a Combine feature. Returns: `combine`
        with `name`, `operation`, the body names, counts and volumes before
        and after, and `volume_change_mm3`.

        Args:
            input_data: `operation`, `main_body` and `tool_bodies`.

        Returns:
            dict[str, Any]: The combine and its measured change.
        """
        input_data = normalize_input(input_data, CombineBodiesInput)
        require_capability(
            adapter, "combine_bodies", "Active adapter can't combine bodies"
        )
        result = await adapter.combine_bodies(
            CombineBodiesParameters(**input_data.model_dump())
        )
        require_success(result, "Failed to combine bodies")
        data = result.data or {}
        return {
            "status": "success",
            "message": f"{input_data.operation.capitalize()}: {_summary(data)}",
            "combine": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def split_body(input_data: SplitBodyInput) -> dict[str, Any]:
        """Split the active part's bodies with a plane or a sketch, keeping every piece in the part.

        E.g. cut a part in two at the Right Plane to print it in halves. The
        plane or sketch must cross the bodies all the way. Fails, changing
        nothing, when the tool is unknown or the split makes no new body. To
        save a piece as its own part, use `save_body_as_part`. Needs: a part
        with a body. Changes: adds a Split feature. Returns: `split` with
        `name`, `made` (the new bodies' names), the body names, counts and
        volumes before and after.

        Args:
            input_data: `tool`, a plane or sketch name.

        Returns:
            dict[str, Any]: The split and its measured change.
        """
        input_data = normalize_input(input_data, SplitBodyInput)
        require_capability(adapter, "split_body", "Active adapter can't split bodies")
        result = await adapter.split_body(SplitBodyParameters(tool=input_data.tool))
        require_success(result, "Failed to split the body")
        data = result.data or {}
        return {
            "status": "success",
            "message": f"Split at {input_data.tool}: {_summary(data)}",
            "split": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def move_copy_body(input_data: MoveCopyBodyInput) -> dict[str, Any]:
        """Move bodies of the active part by a translation and a rotation, or copy them up to 50 times.

        Translation is in mm, rotation in degrees about the model's x, y and z
        axes through `rotation_point`. With `as_copy`, copy n sits n times the
        translation away. Fails, changing nothing, when a name is unknown, the
        move is by nothing, or the bodies didn't move or copy. Needs: a part
        with the bodies (`list_bodies`). Changes: adds a Body-Move/Copy
        feature. Returns: `move` with `name`, the body names, counts and
        volumes before and after.

        Args:
            input_data: `bodies`, and `translate` and/or `rotate`; `as_copy` and
                `copies` to copy.

        Returns:
            dict[str, Any]: The move or copy and its measured change.
        """
        input_data = normalize_input(input_data, MoveCopyBodyInput)
        require_capability(
            adapter, "move_copy_body", "Active adapter can't move bodies"
        )
        result = await adapter.move_copy_body(
            MoveCopyBodyParameters(**input_data.model_dump())
        )
        require_success(result, "Failed to move or copy the bodies")
        data = result.data or {}
        verb = f"Copied {input_data.copies}x" if input_data.as_copy else "Moved"
        return {
            "status": "success",
            "message": f"{verb}: {_summary(data)}",
            "move": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def delete_bodies(input_data: DeleteBodiesInput) -> dict[str, Any]:
        """Delete bodies from the active part, or with keep=true keep only the named ones.

        Fails, changing nothing, when a name is unknown or every body would go.
        Needs: a part with the bodies (`list_bodies`). Changes: adds a
        Body-Delete/Keep feature (undo with `delete_feature`). Returns: `delete`
        with `name`, `removed` (the bodies deleted), the body names, counts
        and volumes before and after.

        Args:
            input_data: `bodies`, and `keep`.

        Returns:
            dict[str, Any]: The deletion and its measured change.
        """
        input_data = normalize_input(input_data, DeleteBodiesInput)
        require_capability(
            adapter, "delete_bodies", "Active adapter can't delete bodies"
        )
        result = await adapter.delete_bodies(
            DeleteBodiesParameters(**input_data.model_dump())
        )
        require_success(result, "Failed to delete bodies")
        data = result.data or {}
        return {
            "status": "success",
            "message": f"{'Kept' if input_data.keep else 'Deleted'}: {_summary(data)}",
            "delete": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def scale_body(input_data: ScaleBodyInput) -> dict[str, Any]:
        """Scale bodies of the active part, uniformly or per axis, about their centroid or the origin.

        Give `scale` (one factor) or `scale_xyz` ([x, y, z]); a body's volume
        is multiplied by the factors' product. Fails, changing nothing, when a
        name is unknown or every factor is 1. Needs: a part with a body.
        Changes: adds a Scale feature. Returns: `scale` with `name`, `factors`,
        the body names, counts and volumes before and after.

        Args:
            input_data: `scale` or `scale_xyz`; `about` and `bodies` optional.

        Returns:
            dict[str, Any]: The scale and its measured change.
        """
        input_data = normalize_input(input_data, ScaleBodyInput)
        require_capability(adapter, "scale_body", "Active adapter can't scale bodies")
        result = await adapter.scale_body(
            ScaleBodyParameters(**input_data.model_dump())
        )
        require_success(result, "Failed to scale the bodies")
        data = result.data or {}
        return {
            "status": "success",
            "message": f"Scaled: {_summary(data)}",
            "scale": data,
            "execution_time": result.execution_time,
        }

    return 6
