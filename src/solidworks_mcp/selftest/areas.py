"""The selftest's four areas: part, assembly, drawing and export.

Each area calls tools through ``Context.call`` exactly as an MCP client
would, and appends a ``Check`` per value it reads back. The values it
expects are in ``expected.py``. An area saves what later areas need into
``Context.files``; an area whose ``needs`` aren't there is skipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from . import expected as ex
from .results import Check, ToolCaller, ToolFailed


@dataclass
class Context:
    """What the areas share: the tool caller, the folder, and saved files."""

    call: ToolCaller
    folder: Path
    files: dict[str, str] = field(default_factory=dict)


async def verify(
    ctx: Context, label: str, checks: list[Check], **expectations: Any
) -> None:
    """Run ``verify_model`` on the active document; append one check per value.

    Args:
        ctx: The selftest context.
        label: Prefix for the check names, e.g. ``"after the hole"``.
        checks: The area's checks, appended to.
        **expectations: ``verify_model`` input, e.g. ``volume_mm3=8000``.
    """
    reply = await ctx.call(
        "verify_model",
        {
            **expectations,
            "relative_tolerance": ex.VOLUME_TOLERANCE,
            "length_tolerance_mm": ex.LENGTH_TOLERANCE_MM,
        },
    )
    for item in reply.get("checks") or []:
        checks.append(
            Check(
                name=f"{label}: {item.get('name')}",
                expected=item.get("expected"),
                measured=item.get("actual"),
                tolerance=item.get("tolerance"),
                unit=str(item.get("unit") or ""),
                passed=item.get("passed"),
            )
        )


async def _sketch_and_extrude(
    ctx: Context, shape: tuple[str, dict[str, Any]], depth: float
) -> None:
    """Sketch one shape on the Top Plane and extrude it ``depth`` mm."""
    sketch = await ctx.call("create_sketch", {"plane": "Top"})
    await ctx.call(*shape)
    await ctx.call("exit_sketch")
    await ctx.call(
        "create_extrusion",
        {"sketch_name": sketch["sketch"]["name"], "depth": depth},
    )


class PartArea:
    """A block with a hole and a fillet, and a pin; both saved for later areas."""

    name: ClassVar[str] = "part"
    needs: ClassVar[tuple[str, ...]] = ()

    async def run(self, ctx: Context, checks: list[Check]) -> None:
        """Build, check and save the block, then the pin.

        Args:
            ctx: The selftest context.
            checks: The area's checks, appended to.
        """
        await ctx.call("create_part", {"name": "selftest_block"})
        rectangle = {"x1": -20.0, "y1": -10.0, "x2": 20.0, "y2": 10.0}
        await _sketch_and_extrude(ctx, ("add_rectangle", rectangle), ex.BLOCK_HEIGHT_MM)
        await verify(
            ctx,
            "block",
            checks,
            volume_mm3=ex.BLOCK_VOLUME_MM3,
            bounding_box_mm=ex.BLOCK_BOX_MM,
        )

        hole = await ctx.call("create_sketch", {"plane": "Top"})
        await ctx.call(
            "add_circle",
            {"center_x": 0.0, "center_y": 0.0, "radius": ex.HOLE_RADIUS_MM},
        )
        await ctx.call("exit_sketch")
        await ctx.call(
            "create_cut_extrude",
            {
                "sketch_name": hole["sketch"]["name"],
                "depth": ex.BLOCK_HEIGHT_MM,
                "end_condition": "ThroughAllBoth",
            },
        )
        await verify(
            ctx,
            "after the hole",
            checks,
            volume_mm3=ex.HOLE_VOLUME_MM3,
            bounding_box_mm=ex.BLOCK_BOX_MM,
        )

        await ctx.call(
            "add_fillet",
            {"radius": ex.FILLET_RADIUS_MM, "edge_names": [ex.FILLET_EDGE]},
        )
        await verify(
            ctx,
            "after the fillet",
            checks,
            volume_mm3=ex.FILLET_VOLUME_MM3,
            bounding_box_mm=ex.BLOCK_BOX_MM,
        )
        ctx.files["block"] = await _save(ctx, "selftest_block.SLDPRT")

        await ctx.call("create_part", {"name": "selftest_pin"})
        circle = {"center_x": 0.0, "center_y": 0.0, "radius": ex.PIN_RADIUS_MM}
        await _sketch_and_extrude(ctx, ("add_circle", circle), ex.PIN_LENGTH_MM)
        await verify(
            ctx,
            "pin",
            checks,
            volume_mm3=ex.PIN_VOLUME_MM3,
            bounding_box_mm=ex.PIN_BOX_MM,
        )
        ctx.files["pin"] = await _save(ctx, "selftest_pin.SLDPRT")


async def _save(ctx: Context, file_name: str) -> str:
    """Save the active document into the selftest's folder; return its path."""
    path = str(ctx.folder / file_name)
    await ctx.call("save_as", {"file_path": path})
    return path


class AssemblyArea:
    """The pin seated in the block's hole by two face mates."""

    name: ClassVar[str] = "assembly"
    needs: ClassVar[tuple[str, ...]] = ("block", "pin")

    async def run(self, ctx: Context, checks: list[Check]) -> None:
        """Insert both parts, mate them, and check counts and clearance.

        Args:
            ctx: The selftest context.
            checks: The area's checks, appended to.
        """
        await ctx.call("create_assembly", {"name": "selftest_assembly"})
        await ctx.call("insert_component", {"file_path": ctx.files["block"]})
        await ctx.call("insert_component", {"file_path": ctx.files["pin"], "x": 100.0})
        names = (await ctx.call("list_components")).get("components") or []
        block, pin = (
            _component(names, "selftest_block"),
            _component(names, "selftest_pin"),
        )
        for face_a, face_b, mate_type in (
            (ex.HOLE_WALL_POINT, ex.PIN_SIDE_POINT, "concentric"),
            (ex.BLOCK_BOTTOM_POINT, ex.PIN_BOTTOM_POINT, "coincident"),
        ):
            await ctx.call(
                "add_mate",
                {
                    "component_a": block,
                    "component_b": pin,
                    "face_a": face_a,
                    "face_b": face_b,
                    "mate_type": mate_type,
                    "alignment": "aligned",
                },
            )
        await verify(
            ctx,
            "assembly",
            checks,
            component_count=ex.COMPONENT_COUNT,
            mate_count=ex.MATE_COUNT,
            no_interference=True,
        )


def _component(names: list[str], part: str) -> str:
    """The component made from ``part``.

    Raises:
        ToolFailed: ``list_components`` didn't list it.
    """
    for name in names:
        if part in name:
            return name
    raise ToolFailed("list_components", f"no component from {part} in {names}")


class DrawingArea:
    """A new drawing with one isometric view of the block."""

    name: ClassVar[str] = "drawing"
    needs: ClassVar[tuple[str, ...]] = ("block",)

    async def run(self, ctx: Context, checks: list[Check]) -> None:
        """Make the drawing and count its views.

        Args:
            ctx: The selftest context.
            checks: The area's checks, appended to.
        """
        await ctx.call("create_drawing", {"name": "selftest_drawing"})
        await ctx.call(
            "add_drawing_view",
            {"model_file": ctx.files["block"], "view_type": "isometric"},
        )
        views = (await ctx.call("list_drawing_views")).get("count")
        checks.append(
            Check(
                name="drawing: view_count",
                expected=ex.DRAWING_VIEW_COUNT,
                measured=views,
                unit="view",
                passed=views == ex.DRAWING_VIEW_COUNT,
            )
        )


class ExportArea:
    """The block exported as STEP."""

    name: ClassVar[str] = "export"
    needs: ClassVar[tuple[str, ...]] = ("block",)

    async def run(self, ctx: Context, checks: list[Check]) -> None:
        """Export the block and check the file.

        Args:
            ctx: The selftest context.
            checks: The area's checks, appended to.
        """
        await ctx.call("activate_document", {"title_or_path": ctx.files["block"]})
        target = ctx.folder / "selftest_block.step"
        await ctx.call("export_step", {"file_path": str(target)})
        size = target.stat().st_size if target.is_file() else None
        checks.append(
            Check(
                name="export: step_file_bytes",
                expected="> 0",
                measured=size,
                unit="bytes",
                passed=bool(size),
            )
        )


#: The areas in the order they run.
AREAS = (PartArea(), AssemblyArea(), DrawingArea(), ExportArea())
