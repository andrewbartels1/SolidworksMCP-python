"""Reference and analysis extras: coordinate system, centre of mass, bounding box, section.

Each reply is read back from SolidWorks, not echoed: the coordinate system's
transform, the centre of mass, the bodies' box and a face's section
properties (queue item 39).
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from ..adapters.base import (
    BoundingBoxParameters,
    CoordinateSystemParameters,
    SectionPropertiesParameters,
    SolidWorksAdapter,
)
from .input_compat import CompatInput
from .tool_boundary import (
    normalize_input,
    require_capability,
    require_success,
    with_tool_boundary,
)


class CoordinateSystemInput(CompatInput):
    """Input schema for a coordinate system at a point.

    Attributes:
        origin (list[float]): ``[x, y, z]`` mm.
    """

    origin: list[float] = Field(
        min_length=3, max_length=3, description="The origin [x, y, z] in mm"
    )


class BoundingBoxInput(CompatInput):
    """Input schema for the bounding box.

    Attributes:
        include_hidden (bool): Include hidden bodies.
    """

    include_hidden: bool = Field(
        default=False, description="Include hidden bodies in the box"
    )


class SectionPropertiesInput(CompatInput):
    """Input schema for a face's section properties.

    Attributes:
        face_point (list[float]): ``[x, y, z]`` mm on the face.
    """

    face_point: list[float] = Field(
        min_length=3,
        max_length=3,
        description="[x, y, z] in mm, a point on a planar face",
    )


def _mm(values: Any) -> str:
    """'(20, 10, 20)' from a list of mm."""
    return "(" + ", ".join(f"{float(v):g}" for v in values or []) + ")"


async def register_reference_extras_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: Any
) -> int:
    """Register the reference and analysis extras with FastMCP.

    Args:
        mcp (FastMCP): The server.
        adapter (SolidWorksAdapter): The adapter the tools call.
        config (Any): Configuration values (unused).

    Returns:
        int: How many tools were registered.
    """
    mcp = with_tool_boundary(mcp)

    @mcp.tool()
    async def create_coordinate_system(
        input_data: CoordinateSystemInput,
    ) -> dict[str, Any]:
        """Add a coordinate system with its origin at a point, axes along the model's.

        Use it as a frame for measurements, mass properties or exports. The
        origin is a point in a 3D sketch the tool draws for it; the axes
        can't yet be turned. Needs: an open part.
        Changes: adds a 3D sketch and a Coordinate System feature. Returns:
        `coordinate_system` with `name`, `sketch`, and the transform read
        back: `origin_mm`, `x_axis`, `y_axis`, `z_axis`.

        Args:
            input_data: `origin` in mm.

        Returns:
            dict[str, Any]: The coordinate system as SolidWorks holds it.
        """
        input_data = normalize_input(input_data, CoordinateSystemInput)
        require_capability(
            adapter,
            "create_coordinate_system",
            "Active adapter can't add coordinate systems",
        )
        result = await adapter.create_coordinate_system(
            CoordinateSystemParameters(**input_data.model_dump())
        )
        require_success(result, "Failed to add the coordinate system")
        data = result.data or {}
        return {
            "status": "success",
            "message": f"{data.get('name')} at {_mm(data.get('origin_mm'))} mm",
            "coordinate_system": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def create_center_of_mass_point() -> dict[str, Any]:
        """Add SolidWorks's Center of Mass point to the active part, at its centre of mass.

        The point moves with the geometry; dimension to it or read it in
        drawings. A part has one at most. Fails when the part has one already
        or has no solid body. For the numbers alone, `get_mass_properties`
        changes nothing. Needs: an open part with a body. Changes: adds a
        Center of Mass feature. Returns: `center_of_mass` with `name` and
        `center_of_mass_mm`.
        """
        require_capability(
            adapter,
            "create_center_of_mass_point",
            "Active adapter can't add a centre-of-mass point",
        )
        result = await adapter.create_center_of_mass_point()
        require_success(result, "Failed to add the centre-of-mass point")
        data = result.data or {}
        return {
            "status": "success",
            "message": (
                f"{data.get('name')} at {_mm(data.get('center_of_mass_mm'))} mm"
            ),
            "center_of_mass": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def create_bounding_box(
        input_data: BoundingBoxInput | None = None,
    ) -> dict[str, Any]:
        """Add SolidWorks's Bounding Box feature around the active part's bodies and give the stock size.

        The box is SolidWorks's best fit and updates with the part. A part has
        one at most. For the size alone, `verify_model` changes nothing.
        Needs: an open part with a body. Changes: adds a Bounding Box feature.
        Returns: `bounding_box` with `name`, `size_mm` [x, y, z] and the
        `min_mm` and `max_mm` corners, in model axes.

        Args:
            input_data: Optional `include_hidden`.

        Returns:
            dict[str, Any]: The box and its size.
        """
        input_data = normalize_input(input_data or {}, BoundingBoxInput)
        require_capability(
            adapter, "create_bounding_box", "Active adapter can't add a bounding box"
        )
        result = await adapter.create_bounding_box(
            BoundingBoxParameters(**input_data.model_dump())
        )
        require_success(result, "Failed to add the bounding box")
        data = result.data or {}
        size = " x ".join(f"{float(v):g}" for v in data.get("size_mm") or [])
        return {
            "status": "success",
            "message": f"{data.get('name')}: {size} mm",
            "bounding_box": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def get_section_properties(
        input_data: SectionPropertiesInput,
    ) -> dict[str, Any]:
        """Read the area, centroid and second moments of area of a planar face, picked by a point on it.

        E.g. a beam's cross-section or a bracket's mounting face. Moments are
        about the face's centroid, in model axes. Fails when the point is on
        no face or the face isn't planar. Needs: an open part. Read-only.
        Returns: `section` with `area_mm2`, `centroid_mm`, `ixx`, `iyy`,
        `izz`, `ixy`, `izx`, `iyz` (mm⁴), `polar_moment_mm4` and
        `principal_moments_mm4`.

        Args:
            input_data: `face_point` in mm.

        Returns:
            dict[str, Any]: The face's section properties.
        """
        input_data = normalize_input(input_data, SectionPropertiesInput)
        require_capability(
            adapter,
            "get_section_properties",
            "Active adapter can't read section properties",
        )
        result = await adapter.get_section_properties(
            SectionPropertiesParameters(**input_data.model_dump())
        )
        require_success(result, "Failed to read the section properties")
        data = result.data or {}
        return {
            "status": "success",
            "message": (
                f"Area {float(data.get('area_mm2') or 0):,.2f} mm², centroid "
                f"{_mm(data.get('centroid_mm'))} mm"
            ),
            "section": data,
            "execution_time": result.execution_time,
        }

    return 4
