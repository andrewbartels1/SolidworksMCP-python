"""Modelled threads: the standard sizes, and external or internal threads (queue item 43).

``list_thread_sizes`` reads the sizes SolidWorks's own thread profiles hold,
with coarse or fine, the ISO 68-1 basic depth and the ISO 3508 runout;
``create_thread`` cuts a thread with SolidWorks's Thread feature, checked
before and measured after. ``add_cosmetic_thread`` remains for a thread
shown only in drawings.
"""

from __future__ import annotations

from typing import Any, Literal

from fastmcp import FastMCP
from pydantic import Field

from ..adapters.base import SolidWorksAdapter, ThreadParameters
from .input_compat import CompatInput
from .tool_boundary import (
    normalize_input,
    require_capability,
    require_success,
    with_tool_boundary,
)


class ThreadSizesInput(CompatInput):
    """Input schema for listing thread sizes.

    Attributes:
        standard (str): ``metric`` or ``inch``.
    """

    standard: Literal["metric", "inch"] = Field(
        default="metric", description="'metric' (ISO, e.g. M6x1.0) or 'inch' (UTS)"
    )


class CreateThreadInput(CompatInput):
    """Input schema for a modelled thread.

    Attributes:
        kind (str): ``external`` or ``internal``.
        standard (str): ``metric`` or ``inch``.
        size (str): A size from ``list_thread_sizes``.
        edge_point (list[float]): ``[x, y, z]`` mm on the circular edge.
        length (float): mm.
        hand (str): ``right`` or ``left``.
    """

    kind: Literal["external", "internal"] = Field(
        default="external",
        description="'external' (a bolt or rod, male) or 'internal' (a tapped "
        "hole, female)",
    )
    standard: Literal["metric", "inch"] = Field(
        default="metric", description="'metric' or 'inch'"
    )
    size: str = Field(
        min_length=1,
        description="A size as list_thread_sizes names it, e.g. 'M6x1.0'; inch "
        "also takes '1/4-20'",
    )
    edge_point: list[float] = Field(
        min_length=3,
        max_length=3,
        description="[x, y, z] in mm on the circular edge where the thread "
        "starts: a rod's end edge, or a hole's edge at its opening",
    )
    length: float = Field(gt=0, description="Length of full thread in mm")
    hand: Literal["right", "left"] = Field(
        default="right", description="'right' (the usual) or 'left' hand"
    )


async def register_thread_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: Any
) -> int:
    """Register the thread tools with FastMCP.

    Args:
        mcp (FastMCP): The server.
        adapter (SolidWorksAdapter): The adapter the tools call.
        config (Any): Configuration values (unused).

    Returns:
        int: How many tools were registered.
    """
    mcp = with_tool_boundary(mcp)

    @mcp.tool()
    async def list_thread_sizes(
        input_data: ThreadSizesInput | None = None,
    ) -> dict[str, Any]:
        """List the standard thread sizes SolidWorks holds, metric or inch, with coarse or fine pitch, depth and runout.

        Read from SolidWorks's own thread profiles, so every size works in
        `create_thread`. Each size gives `diameter_mm`, `pitch_mm` (`tpi` for
        inch), `pitch_class` (coarse, fine, or only), `basic_depth_mm` (ISO
        68-1) and `runout_mm` (normal and short, ISO 3508; for inch the same
        rule on 1/TPI, as `runout_basis` says). M3 to M6 are the common bolt
        sizes. Needs: SolidWorks running. Read-only. Returns: `sizes`,
        `count`, `profile` and `runout_basis`.

        Args:
            input_data: Optional `standard`, metric by default.

        Returns:
            dict[str, Any]: The sizes.
        """
        input_data = normalize_input(input_data or {}, ThreadSizesInput)
        require_capability(
            adapter, "list_thread_sizes", "Active adapter can't read thread sizes"
        )
        result = await adapter.list_thread_sizes(input_data.standard)
        require_success(result, "Failed to read the thread sizes")
        data = result.data or {}
        return {
            "status": "success",
            "message": f"{data.get('count', 0)} {input_data.standard} thread sizes",
            **data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def create_thread(input_data: CreateThreadInput) -> dict[str, Any]:
        """Cut a modelled thread, external (a bolt) or internal (a tapped hole), at a standard size.

        Pick the circular edge where the thread starts with `edge_point`: a
        rod's end, or a hole's opening. The rod should be the nominal diameter
        (M6: 6 mm); the hole about the tap drill (nominal minus one pitch, M6:
        5 mm). Fails, changing nothing, for a size not in `list_thread_sizes`,
        a point on no circular edge, or a diameter that doesn't suit the size;
        a thread that cuts nothing is undone. The reply's `runout_mm` is the
        incomplete thread to leave before a shoulder. Needs: an open part with
        the cylinder or hole. Changes: adds a Thread feature. Returns: `thread`
        with `name`, `size`, `pitch_mm`, `basic_depth_mm`, `runout_mm`,
        `turns` and `volume_change`.

        Args:
            input_data: `size`, `edge_point` and `length`; `kind`, `standard`
                and `hand` optional.

        Returns:
            dict[str, Any]: The thread and its measured change.
        """
        input_data = normalize_input(input_data, CreateThreadInput)
        require_capability(
            adapter, "create_thread", "Active adapter can't model threads"
        )
        result = await adapter.create_thread(
            ThreadParameters(**input_data.model_dump())
        )
        require_success(result, "Failed to create the thread")
        data = result.data or {}
        return {
            "status": "success",
            "message": (
                f"{data.get('name')}: {data.get('size')} {input_data.kind}, "
                f"{input_data.length:g} mm, {float(data.get('volume_change') or 0):,.1f} mm³"
            ),
            "thread": data,
            "execution_time": result.execution_time,
        }

    return 2
