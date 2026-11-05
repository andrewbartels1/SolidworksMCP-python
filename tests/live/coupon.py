"""The M4 heat-set-insert coupon that the live chamfer and fillet tests treat.

The coupon is a 30x30 mm square sketched on the Top Plane and extruded
15 mm, with a centred Ø5.5 mm hole sketched on the same plane and cut 6 mm
deep. Its height therefore runs along the model's Y axis, not Z: measured
live, its box is min ``[0, 0, -30]`` and max ``[30, 15, 0]`` mm, and the hole
opens onto the y = 0 face.

The tests once hard-coded points that assumed Z was the height, and treated
the wrong faces without noticing (#199). So every point here is worked out
from the measured bounding box, and each test checks the removed volume
against the formulas below, which tell one face from another.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from tests.live.evidence import evidence

#: The hole's radius (Ø5.5 mm).
HOLE_RADIUS_MM = 2.75
#: The length of the square's edges.
EDGE_MM = 30.0
#: The extrusion depth, which is the coupon's height.
HEIGHT_MM = 15.0
#: How far face points sit in from a corner: clear of the edges, and of the
#: hole at the face's centre.
_INSET_MM = 5.0


def circular_chamfer_volume(radius_mm: float, width_mm: float) -> float:
    """Volume removed by a 45° equal-distance chamfer on a hole's rim.

    Args:
        radius_mm: The hole's radius.
        width_mm: The chamfer distance.

    Returns:
        float: The removed volume in mm³.
    """
    r, w = radius_mm, width_mm
    return math.pi * (((r + w) ** 3 - r**3) / 3.0 - r * r * w)


def straight_chamfer_volume(length_mm: float, width_mm: float) -> float:
    """Volume removed by a 45° equal-distance chamfer along a straight edge.

    Args:
        length_mm: The edge's length.
        width_mm: The chamfer distance.

    Returns:
        float: The removed volume in mm³.
    """
    return 0.5 * width_mm * width_mm * length_mm


def straight_fillet_volume(length_mm: float, radius_mm: float) -> float:
    """Volume removed by a fillet along a straight 90° edge.

    Args:
        length_mm: The edge's length.
        radius_mm: The fillet radius.

    Returns:
        float: The removed volume in mm³.
    """
    return (1.0 - math.pi / 4.0) * radius_mm * radius_mm * length_mm


def chamfer_corner_overlap(width_mm: float) -> float:
    """Volume two edge chamfers share where they meet at a square corner.

    Two straight chamfers that meet at a corner mitre there, so the corner
    material is removed once, not twice. With distances ``a, b, c`` from the
    corner's three faces, the shared region is ``b + c < w`` and ``a + b < w``;
    integrating ``w - max(a, c)`` over the ``w × w`` square gives ``w³/3``.
    Confirmed live: the hole face measured 17.124 mm³ against 17.1241, and a
    side face 11.083 against 11.0833.

    Args:
        width_mm: The chamfer distance.

    Returns:
        float: The volume to subtract from the two edges' sum, in mm³.
    """
    return width_mm**3 / 3.0


#: How close a measured removal must be to the exact value, in mm³. The
#: faces are planes, cones and cylinders, so SolidWorks' volume is exact up
#: to rounding; this only absorbs that.
VOLUME_TOLERANCE_MM3 = 0.001


def _spec(point_mm: list[float], prefix: str = "") -> str:
    """An ``edge_names`` entry, in metres, for a point given in mm."""
    return prefix + ",".join(f"{value / 1000.0:g}" for value in point_mm)


@dataclass(frozen=True)
class Coupon:
    """The coupon's measured box and the face and edge points derived from it.

    Attributes:
        box: The bounding box in mm (``min``, ``max``, ``size``), as
            ``get_model_geometry_summary`` reports it.
    """

    box: dict[str, Any]

    @classmethod
    async def measure(cls, adapter: Any) -> Coupon:
        """Read the active coupon's bounding box from SolidWorks.

        Args:
            adapter: A connected SolidWorks adapter with the coupon open.

        Returns:
            Coupon: The measured coupon.
        """
        summary = await adapter.get_model_geometry_summary()
        assert summary.is_success, summary.error
        return cls(summary.data["bounding_box_mm"])

    @property
    def height_axis(self) -> int:
        """The axis (0, 1 or 2) whose extent is the 15 mm height."""
        return min(range(3), key=lambda axis: abs(self.box["size"][axis] - HEIGHT_MM))

    @property
    def _side_axes(self) -> list[int]:
        """The two axes across the 30x30 mm faces."""
        return [axis for axis in range(3) if axis != self.height_axis]

    @property
    def _hole_end(self) -> float:
        """The height-axis coordinate of the face the hole opens onto.

        The hole is sketched on the plane the block is extruded from, so it
        opens onto the end of the height axis at 0.
        """
        low = self.box["min"][self.height_axis]
        high = self.box["max"][self.height_axis]
        return float(low if abs(low) <= abs(high) else high)

    def _face_point(self, height_mm: float) -> list[float]:
        """A point at ``height_mm``, inset from a corner across the face."""
        point = [self.box["min"][axis] + _INSET_MM for axis in range(3)]
        point[self.height_axis] = height_mm
        return point

    @property
    def hole_face(self) -> str:
        """A ``face:`` point on the 30x30 mm face the hole opens onto."""
        return _spec(self._face_point(self._hole_end), "face:")

    @property
    def opposite_edge(self) -> str:
        """An edge point halfway along a 30 mm edge of the face opposite the hole.

        That edge shares no corner with the hole face, so treating both adds
        their volumes exactly.
        """
        low = self.box["min"][self.height_axis]
        high = self.box["max"][self.height_axis]
        point = [self.box["min"][axis] for axis in range(3)]
        point[self.height_axis] = high if self._hole_end == low else low
        along = self._side_axes[1]
        point[along] = (self.box["min"][along] + self.box["max"][along]) / 2.0
        return _spec(point)

    @property
    def side_face(self) -> str:
        """A ``face:`` point on a 30x15 mm side face."""
        point = self._face_point(self.box["min"][self.height_axis] + _INSET_MM)
        point[self._side_axes[0]] = self.box["min"][self._side_axes[0]]
        return _spec(point, "face:")

    @property
    def inside(self) -> str:
        """A ``face:`` point 5 mm inside the block, on no face."""
        point = self._face_point(self.box["min"][self.height_axis] + _INSET_MM)
        return _spec(point, "face:")

    def points(self) -> dict[str, str]:
        """Every derived point, for the evidence line."""
        return {
            "hole_face": self.hole_face,
            "side_face": self.side_face,
            "opposite_edge": self.opposite_edge,
            "inside": self.inside,
        }


async def add_chamfer_tool(adapter: Any) -> Any:
    """Register the modeling tools and return the ``add_chamfer`` tool function.

    Args:
        adapter: The connected SolidWorks adapter.

    Returns:
        Any: The tool function an MCP client's call reaches.
    """
    from fastmcp import FastMCP

    from solidworks_mcp.tools.modeling import register_modeling_tools

    mcp = FastMCP("add-chamfer-live-test")
    await register_modeling_tools(mcp, adapter, {})
    tools = {t.name: t.fn for t in await mcp.list_tools()}
    assert "add_chamfer" in tools, "add_chamfer tool did not register"
    return tools["add_chamfer"]


async def feature_names(adapter: Any) -> list[str]:
    """The names in the active part's feature tree.

    Args:
        adapter: A connected SolidWorks adapter.

    Returns:
        list[str]: The feature names, in tree order.
    """
    features = await adapter.list_features()
    assert features.is_success, features.error
    return [f["name"] for f in features.data]


async def volume(adapter: Any) -> float:
    """The active part's volume in mm³.

    Args:
        adapter: A connected SolidWorks adapter.

    Returns:
        float: The volume.
    """
    mass = await adapter.get_mass_properties()
    assert mass.is_success, mass.error
    return float(mass.data.volume)


async def build(adapter: Any) -> Coupon:
    """Build the coupon in a new part and measure it.

    Mirrors ``scripts/build_m4_heat_insert_coupon.py``: a 30x30x15 mm block
    with a centred Ø5.5 mm hole cut 6 mm deep.

    Args:
        adapter: A connected SolidWorks adapter.

    Returns:
        Coupon: The built coupon, with its measured box.
    """
    from solidworks_mcp.adapters.base import ExtrusionParameters

    assert (await adapter.create_part()).is_success

    assert (await adapter.create_sketch("Top")).is_success
    bottom = await adapter.add_line(0, 0, 30, 0)
    assert bottom.is_success
    left = await adapter.add_line(0, 30, 0, 0)
    assert left.is_success
    assert (await adapter.add_line(30, 0, 30, 30)).is_success
    assert (await adapter.add_line(30, 30, 0, 30)).is_success

    width_dim = await adapter.add_sketch_dimension(bottom.data, None, "linear", 30.0)
    assert width_dim.is_success, width_dim.error
    height_dim = await adapter.add_sketch_dimension(left.data, None, "linear", 30.0)
    assert height_dim.is_success, height_dim.error

    assert (await adapter.exit_sketch()).is_success
    boss = await adapter.create_extrusion(ExtrusionParameters(depth=HEIGHT_MM))
    assert boss.is_success, boss.error

    assert (await adapter.create_sketch("Top")).is_success
    circle = await adapter.add_circle(15.0, 15.0, HOLE_RADIUS_MM)
    assert circle.is_success, circle.error
    diameter_dim = await adapter.add_sketch_dimension(
        circle.data, None, "diameter", 2 * HOLE_RADIUS_MM
    )
    assert diameter_dim.is_success, diameter_dim.error
    assert (await adapter.exit_sketch()).is_success

    # The cut needs the hole sketch by name: the one sketch the boss didn't use.
    features = await adapter.list_features()
    assert features.is_success, features.error
    sketch_names = [
        f["name"] for f in features.data if f.get("type") == "ProfileFeature"
    ]
    unconsumed = [n for n in sketch_names if n != "Sketch1"]
    assert len(unconsumed) == 1, f"expected one unconsumed sketch, got {sketch_names}"

    cut = await adapter.create_cut_extrude(
        ExtrusionParameters(depth=6.0, sketch_name=unconsumed[0])
    )
    assert cut.is_success, cut.error
    # Whether the first cut direction found no material and the adapter
    # retried the other way (#193). Shown because SolidWorks has sometimes
    # played its error sound during this cut; with ``-Trace`` the two can be
    # lined up.
    evidence(
        "The hole cut",
        {"direction_flipped": cut.data.parameters.get("direction_flipped")},
        quick=True,
    )
    return await Coupon.measure(adapter)
