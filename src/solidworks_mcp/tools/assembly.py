"""Assembly tools: exploded views, component patterns, mirrors, replace.

Queue item 33: what takes an assembly to the drawing a shop builds from (an
exploded view with numbered balloons beside the BOM), and the everyday edits
between (repeat a component, mirror it, swap it for another version).
Inserting, mating and listing components stay in ``modeling``.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from pydantic import Field, model_validator

from ..adapters.base import SolidWorksAdapter
from .input_compat import CompatInput
from .tool_boundary import (
    normalize_input,
    require_capability,
    require_success,
    with_tool_boundary,
)

#: A component's instance name, as ``list_components`` reports it.
ComponentName = Annotated[str, Field(min_length=1)]


class ExplodeStep(CompatInput):
    """One explode step: components moved a distance along an axis.

    Attributes:
        components (list[str]): Instance names.
        direction (str): ``x``, ``y`` or ``z``.
        distance (float): How far, mm.
        reverse (bool): The other way along the axis.
    """

    components: list[ComponentName] = Field(
        min_length=1, description="Instance names, e.g. ['pin-1', 'pin-2']"
    )
    direction: Literal["x", "y", "z"] = Field(
        description="The model axis to move along"
    )
    distance: float = Field(gt=0, description="How far to move them, mm")
    reverse: bool = Field(default=False, description="Move the other way")


class CreateExplodedViewInput(CompatInput):
    """Input schema for exploding an assembly.

    Attributes:
        steps (list[ExplodeStep]): Explode steps in order; none explodes it
            automatically.
    """

    steps: list[ExplodeStep] = Field(
        default_factory=list,
        description="Explode steps in order, each moving components along x, y "
        "or z; leave empty to let SolidWorks explode it automatically",
    )


class SetExplodedViewInput(CompatInput):
    """Input schema for showing or collapsing the exploded view.

    Attributes:
        exploded (bool): Explode (``True``) or collapse (``False``).
    """

    exploded: bool = Field(description="true shows it exploded, false collapsed")


class PatternComponentsInput(CompatInput):
    """Input schema for a component pattern.

    Attributes:
        components (list[str]): The seed components.
        axis (str): A reference axis's name.
        count (int): Instances, the seeds included.
        kind (str): ``linear`` or ``circular``.
        spacing (float | None): Linear spacing, mm.
        angle (float | None): Circular angle, degrees.
    """

    components: list[ComponentName] = Field(
        min_length=1, description="The seed components' instance names"
    )
    axis: str = Field(
        min_length=1,
        description="A reference axis's name (create_axis in the assembly), the "
        "pattern's direction or centre",
    )
    count: int = Field(ge=2, description="Instances, the seeds included")
    kind: Literal["linear", "circular"] = Field(
        default="linear", description="linear (along the axis) or circular (around it)"
    )
    spacing: float | None = Field(
        default=None, gt=0, description="Linear: the distance between instances, mm"
    )
    angle: float | None = Field(
        default=None,
        gt=0,
        le=360,
        description="Circular: the total angle in degrees; 360 spaces them equally",
    )

    @model_validator(mode="after")
    def _size_for_kind(self) -> PatternComponentsInput:
        """A linear pattern needs its spacing."""
        if self.kind == "linear" and self.spacing is None:
            raise ValueError("a linear pattern needs spacing")
        return self


class MirrorComponentsInput(CompatInput):
    """Input schema for mirroring components.

    Attributes:
        components (list[str]): Instance names.
        plane (str): The plane to mirror about.
    """

    components: list[ComponentName] = Field(
        min_length=1, description="Instance names to mirror"
    )
    plane: str = Field(
        min_length=1,
        description="The plane: 'Front Plane', 'Top Plane', 'Right Plane' or a "
        "plane's name",
    )


class ReplaceComponentInput(CompatInput):
    """Input schema for replacing a component.

    Attributes:
        component (str): The instance to replace.
        file_path (str): The part or assembly to put in its place.
        all_instances (bool): Every instance of the same file.
    """

    component: ComponentName = Field(description="The instance name, e.g. 'pin-1'")
    file_path: str = Field(
        min_length=1, description="The .sldprt or .sldasm to put in its place"
    )
    all_instances: bool = Field(
        default=False, description="Replace every instance of the same file"
    )


async def register_assembly_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: Any
) -> int:
    """Register the assembly tools with FastMCP.

    Args:
        mcp (FastMCP): The mcp value.
        adapter (SolidWorksAdapter): Adapter instance used for the operation.
        config (Any): Configuration values for the operation.

    Returns:
        int: How many tools were registered.
    """
    mcp = with_tool_boundary(mcp)

    @mcp.tool()
    async def create_exploded_view(
        input_data: CreateExplodedViewInput,
    ) -> dict[str, Any]:
        """Explode the active assembly, automatically or step by step, and show it.

        Use it to show how an assembly goes together, and before an exploded
        drawing view (`create_drawing_view` with `exploded`, drawing toolset). With no `steps` SolidWorks
        explodes it automatically; each step moves named components a distance
        along x, y or z. Needs: an open assembly. Changes: adds an exploded view
        to the active configuration and shows it. Returns: `exploded_view` with
        its `view` name, `steps`, and the bounding box `size_before_mm` and
        `size_after_mm`. A component it doesn't hold fails as `not_found`.

        Args:
            input_data: `steps` (each `components`, `direction`, `distance`,
                `reverse`); empty explodes it automatically.

        Returns:
            dict[str, Any]: The exploded view.
        """
        input_data = normalize_input(input_data, CreateExplodedViewInput)
        require_capability(
            adapter, "create_exploded_view", "Active adapter can't explode assemblies"
        )
        steps = [step.model_dump() for step in input_data.steps]
        result = await adapter.create_exploded_view(steps or None)
        require_success(result, context="Failed to explode the assembly")
        return {
            "status": "success",
            "message": f"Exploded the assembly in {len(steps) or 'automatic'} step(s)",
            "exploded_view": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def set_exploded_view(input_data: SetExplodedViewInput) -> dict[str, Any]:
        """Show the active assembly exploded, or collapse it.

        Use it to switch between the exploded view `create_exploded_view` made
        and the assembled one. Needs: an open assembly with an exploded view.
        Changes: what the view shows; nothing in the model. Returns:
        `exploded_view` with the `view`, `exploded` as read back and the bounding
        box `size_mm`. No exploded view fails as `not_found`.

        Args:
            input_data: `exploded` (true or false).

        Returns:
            dict[str, Any]: The view's state.
        """
        input_data = normalize_input(input_data, SetExplodedViewInput)
        require_capability(
            adapter, "set_exploded_view", "Active adapter can't explode assemblies"
        )
        result = await adapter.set_exploded_view(input_data.exploded)
        require_success(result, context="Failed to change the exploded view")
        state = "exploded" if input_data.exploded else "collapsed"
        return {
            "status": "success",
            "message": f"The assembly shows {state}",
            "exploded_view": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def pattern_components(input_data: PatternComponentsInput) -> dict[str, Any]:
        """Repeat assembly components in a row along an axis, or around one.

        Use it for a row of bolts or pins, or parts around a hub. `axis` names a
        reference axis (`create_axis` in the assembly); `count` includes the
        seeds. Linear takes `spacing` (mm); circular takes `angle` (degrees, 360
        spaces them equally). The row runs along the axis's own direction, which
        SolidWorks picks (an x axis from `create_axis` runs toward -x), so check
        the result with `verify_model`'s bounding box. Needs: an open assembly
        with the seeds and the axis.
        Changes: adds a component pattern feature. Returns: `pattern` with the
        `feature` name, the component counts before and after and the `added`
        instances.

        Args:
            input_data: `components`, `axis` and `count` are required; `kind`
                (`linear`) with `spacing`, or `circular` with `angle`.

        Returns:
            dict[str, Any]: The pattern.
        """
        input_data = normalize_input(input_data, PatternComponentsInput)
        require_capability(
            adapter, "pattern_components", "Active adapter can't pattern components"
        )
        result = await adapter.pattern_components(
            input_data.components,
            input_data.axis,
            input_data.count,
            input_data.kind,
            input_data.spacing,
            input_data.angle,
        )
        require_success(result, context="Failed to pattern the components")
        added = (result.data or {}).get("added", [])
        return {
            "status": "success",
            "message": f"Added {len(added)} component(s) in a {input_data.kind} pattern",
            "pattern": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def mirror_components(input_data: MirrorComponentsInput) -> dict[str, Any]:
        """Mirror assembly components about a plane, as instances of the same parts.

        Use it for a part that appears on both sides, such as a pair of feet or
        brackets. Needs: an open assembly with the components and the plane.
        Changes: adds mirrored instances (no new part files). Returns: `mirror`
        with the `plane` and the `added` instances' names. A plane it doesn't
        have fails as `not_found`.

        Args:
            input_data: `components` and `plane`, both required.

        Returns:
            dict[str, Any]: The mirrored instances.
        """
        input_data = normalize_input(input_data, MirrorComponentsInput)
        require_capability(
            adapter, "mirror_components", "Active adapter can't mirror components"
        )
        result = await adapter.mirror_components(
            input_data.components, input_data.plane
        )
        require_success(result, context="Failed to mirror the components")
        return {
            "status": "success",
            "message": f"Mirrored {len(input_data.components)} component(s) about "
            f"{input_data.plane}",
            "mirror": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def replace_component(input_data: ReplaceComponentInput) -> dict[str, Any]:
        """Swap an assembly component for another part or assembly file.

        Use it to try another version of a part (a longer pin, a different motor)
        without re-inserting and re-mating it. `all_instances` replaces every
        instance of the same file, patterned copies included. Mates are kept where
        they still fit. Needs: an open assembly and the new file. Changes: the
        component's file. Returns: `replace` with the `replaced` instances and
        their files read back, and the components before and after. A file that
        doesn't exist fails as `invalid_input`.

        Args:
            input_data: `component` and `file_path` are required; `all_instances`
                is off.

        Returns:
            dict[str, Any]: What was replaced.
        """
        input_data = normalize_input(input_data, ReplaceComponentInput)
        require_capability(
            adapter, "replace_component", "Active adapter can't replace components"
        )
        result = await adapter.replace_component(
            input_data.component, input_data.file_path, input_data.all_instances
        )
        require_success(result, context="Failed to replace the component")
        replaced = (result.data or {}).get("replaced", {})
        return {
            "status": "success",
            "message": f"Replaced {len(replaced)} instance(s) with "
            f"{input_data.file_path}",
            "replace": result.data,
            "execution_time": result.execution_time,
        }

    return 5
