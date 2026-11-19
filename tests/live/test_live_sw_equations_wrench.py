"""A combination wrench sized by one global variable (the equations demo).

Modelled from pictures of the user's reference wrench (a 16 mm combination
wrench; standard views exported read-only, its feature tree not read): an
open end whose jaw is a parallel-sided slot at 15°, its bottom a shallow
curve just past the head's centre (a nut Size across flats bears on both
walls, its corners clear in the curve), a 12-point box end tilted 15° and
raised, a flat handle with rounded edges, thinner than the heads, filleted
into both heads, and chrome-vanadium steel (51CrV4), the usual wrench
steel. It is built at Size = 13 mm with fixed numbers, then
``set_equation`` ties every size to ``Size``, so one edit makes a 19 mm
wrench and a configuration holds an 8 mm one.

Each size is a dimension that grows from the centre, so the wrench keeps its
shape at any size:

- the handle is a round bar along x (its diameter is the handle's width, its
  length the distance between the heads), flattened by two cuts from planes
  offset either side of the Top Plane (the offsets are its thickness);
- the box end is a disc with two hexagon cuts 30° apart (a 12-point opening,
  each hexagon sized across flats), all on a plane tilted 15° about the z
  axis and moved 0.13 x Size along the ring's axis, built near the origin
  and moved to the far end by a linear pattern whose spacing is the
  length; a clearance cut then removes the pattern's seed;
- the open end is a disc at the origin and a jaw Size wide, cut both ways
  from a plane at 15° from the head's centre outward; an ellipse at the
  centre, Size across the jaw and 0.2 x Size along it, curves the bottom
  (measured on the reference: 0.1 x Size past the centre);
- fillets where the handle meets each head, 0.2 x Size at its sides and
  0.16 x Size along its flat faces, where they meet the head and the side
  fillets (the user's pick, 2 mm on the 13 mm wrench).

The reference's handle bends up into the box end. Here the ring is lifted
just enough to cover the handle's end on both faces, so the handle meets
only its round wall and the neck fillets curve it in; a true bend would
need a swept or lofted handle.

Run it with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_equations_wrench.py

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from solidworks_mcp.adapters import sw_type_info
from tests.live.evidence import evidence
from tests.live.test_live_sw_beta_tools import _sketch
from tests.live.test_live_sw_equations import _tools
from tests.live.test_live_sw_ujoint_tool_gaps import _plane

pytestmark = pytest.mark.asyncio

SIZE_MM = 13.0

#: Each global variable as a multiple of Size, measured from the reference
#: (16 mm: heads 205 mm apart, open end Ø31.6, box end Ø24.4, heads 8.2 mm
#: thick, handle 14.6 x 4.7 mm).
RATIOS = {
    "Length": 12.8,
    "OpenHead": 2.0,
    "BoxHead": 1.55,
    "HeadT": 0.5,
    "HandleW": 0.9,
    "HandleT": 0.3,
}
#: The clearance cut that removes the box end's pattern seed: a little wider
#: than the raised, tilted ring reaches (0.89 x Size from the origin).
CLEARANCE = 1.2
JAW_ANGLE_DEG = 15.0
BOX_TILT_DEG = 15.0
#: How far the ring is moved along its own axis, as a multiple of Size. The
#: handle runs to the ring's centre, so the ring must cover it up to the
#: 12-point hole: lifted less than 0.12 x Size the handle shows above the
#: ring's top face, more than 0.14 x Size it shows below its underside as a
#: ledge (checked numerically 2026-11-18). In between, the handle meets only
#: the ring's round wall, and the neck fillets curve it in.
RING_RISE = 0.13
#: The jaw's curved bottom: an ellipse's axes as multiples of Size.
RELIEF = {"across": 1.0, "along": 0.2}
#: Neck fillet radii as multiples of Size: at the handle's sides and faces.
FILLET = {"sides": 0.2, "faces": 0.16}
#: Chrome-vanadium spring steel, the usual wrench steel (SAE 6150 / 51CrV4).
MATERIAL = "1.8159 (51CrV4)"
MATERIAL_LIBRARY = "SolidWorks DIN Materials"
#: Lettering debossed into both faces of the handle. ``$PRP:"WrenchSize"``
#: shows a custom property linked to a dimension the equations set to Size,
#: so the handle reads its own size after each change.
LETTERING = 'solidworksmcp-python  $PRP:"WrenchSize" mm'
LETTER_HEIGHT_MM = 3.5
DEBOSS_MM = 0.3
#: The handle's visible middle as a multiple of Size: between the open
#: end's rim (x = Size) and the ring's near edge (x = 11.95 x Size).
HANDLE_MIDDLE = 6.48
#: The spare block the lettering is first cut into, off the open end
#: (x from -260 to -120 mm, centred at -190), clear of the wrench at any
#: size; a linear pattern moves the lettering onto the handle's middle.
SPARE_X_MM = (-260.0, -120.0)
SPARE_CENTRE_MM = -190.0
_ISO_VIEW = 7  # swStandardViews_e.swIsometricView
#: ``swUserPreferenceToggle_e``: swDisplayAxes, swDisplayPlanes,
#: swDisplayOrigins, swDisplayTemporaryAxes.
_HIDDEN_REFERENCES = (4, 5, 6, 7)


def _hide_references(adapter: Any) -> None:
    """Hide the reference planes, axes and origin, so the wrench shows alone."""
    model = adapter.currentModel
    for toggle in _HIDDEN_REFERENCES:
        adapter._attempt(
            lambda t=toggle: model.Extension.SetUserPreferenceToggle(t, 0, False),
            default=None,
        )


def _frame(adapter: Any, room_for: float = 1.0) -> None:
    """Point the camera: isometric, zoomed to fit, then out to leave room.

    Staging for the recording, not a tool call. ``room_for`` is how many
    times larger the part will grow: the camera is set once and left alone
    after that, so a wrench that grows or shrinks visibly does (zooming to
    fit each time made every size look the same).
    """
    model = adapter.currentModel
    _hide_references(adapter)
    adapter._attempt(lambda: model.ShowNamedView2("", _ISO_VIEW), default=None)
    adapter._zoom_to_fit(model)
    view = sw_type_info.flagged(model.ActiveView, "IModelView")
    adapter._attempt(lambda: view.ZoomByFactor(0.92 / room_for), default=None)


def _mm(variable: str, size: float = SIZE_MM) -> float:
    """A variable's value in mm for a given Size."""
    return round(RATIOS[variable] * size, 4)


#: The box end as built at Size = 13 mm: its centre's offset from where the
#: pattern puts it (x = Length on the handle's line), and its axis.
Ring = tuple[tuple[float, ...], tuple[float, ...]]


def _ring_centre(size: float, ring: Ring) -> tuple[float, float, float]:
    """The box end's centre in mm for a given Size (everything scales)."""
    offset, _axis = ring
    k = size / SIZE_MM
    return (_mm("Length", size) + k * offset[0], k * offset[1], k * offset[2])


def _disc_reach(radius: float, half: float, axis_part: float) -> float:
    """How far a disc reaches along a model axis from its centre.

    ``axis_part`` is that model axis's component of the disc's own axis:
    the rim reaches radius x sin, the faces half the thickness x cos.
    """
    return radius * math.sqrt(1 - axis_part**2) + half * abs(axis_part)


def wrench_box(size: float, ring: Ring) -> list[float]:
    """The wrench's overall size [x, y, z] in mm for a given Size.

    x: the jaw takes the open end's tip off; what stays furthest out is the
    jaw corner nearer the axis, √(R² − (S/2)²) along the jaw and S/2 across
    it, turned 15°. Then the ring's centre and its reach along x.
    y: from the open end's underside (half its thickness below) to the
    ring's top, its centre plus its reach along y. z: the open end's
    diameter.
    """
    r = _mm("OpenHead", size) / 2
    rb = _mm("BoxHead", size) / 2
    t = _mm("HeadT", size) / 2
    jaw = math.radians(JAW_ANGLE_DEG)
    open_reach = math.sqrt(r**2 - (size / 2) ** 2) * math.cos(jaw)
    open_reach += size / 2 * math.sin(jaw)
    centre = _ring_centre(size, ring)
    axis = ring[1]
    x = open_reach + centre[0] + _disc_reach(rb, t, axis[0])
    top = centre[1] + _disc_reach(rb, t, axis[1])
    bottom = min(-t, centre[1] - _disc_reach(rb, t, axis[1]))
    return [round(x, 2), round(top - bottom, 2), round(2 * r, 2)]


async def _one_body(tools: dict[str, Any]) -> bool:
    """Whether the part is still one solid body."""
    checked = await tools["verify_model"]({"solid_body_count": 1})
    return bool(checked["verdict"] == "pass")


async def _length(tools: dict[str, Any]) -> float:
    """The part's overall size along x, in mm (its body count isn't judged)."""
    checked = await tools["verify_model"]({"solid_body_count": 1})
    box = checked["measured"]["bounding_box_mm"]
    size = box.get("size") if isinstance(box, dict) else box
    return float(size[0])


async def _sized_sketch(
    tools: dict[str, Any], plane: str, shape: str, args: dict[str, Any], value: float
) -> str:
    """A sketch of one circle or polygon at the origin, sized by a diameter."""
    made = await tools["create_sketch"]({"plane": plane})
    assert made["status"] == "success", made
    drawn = await tools[shape](args)
    assert drawn["status"] == "success", drawn
    key = "circle" if shape == "add_circle" else "polygon"
    sized = await tools["add_sketch_dimension"](
        {"entity1": drawn[key]["id"], "dimension_type": "diameter", "value": value}
    )
    assert sized["status"] == "success", sized
    closed = await tools["exit_sketch"]()
    assert closed["status"] == "success", closed
    return str(closed.get("sketch", made["sketch"])["name"])


async def _flatten(tools: dict[str, Any], adapter: Any, flip: bool) -> str:
    """Cut the bar away beyond a plane HandleT/2 above (or below) the Top Plane.

    Which way a cut goes from a reference plane isn't certain, so the volume
    decides: the right cut takes off one rounded cap and leaves more than half
    the bar (58-70 %); the wrong one leaves less (30-42 %), or SolidWorks
    refuses it because nothing would be left. Then the cut is undone and made
    the other way, from the same sketch.

    Returns:
        The plane, at the handle's flat face (the lettering goes on it).
    """
    half = _mm("HandleT") / 2
    plane = await tools["create_reference_plane"](
        {"reference": "Top Plane", "offset": half, "flip": flip}
    )
    assert plane["status"] == "success", plane
    name = str(plane["plane"]["name"])
    origin, _normal = _plane(adapter, name)
    assert origin[1] == pytest.approx(-half if flip else half, abs=1e-3), (
        f"{name} is at y = {origin[1]:.3f} mm, not {'-' if flip else ''}{half} mm"
    )
    sketch = await _sketch(tools, name, {"x1": -400, "y1": -400, "x2": 400, "y2": 400})
    for reverse in (False, True):
        cut = await tools["create_cut_extrude"](
            {
                "sketch_name": sketch,
                "depth": 1,
                "end_condition": "ThroughAll",
                "reverse_direction": reverse,
            }
        )
        if cut["status"] != "success":
            continue
        change = cut.get("measured_change", {})
        if change.get("volume_after_mm3", 0) > 0.5 * change.get("volume_before_mm3", 0):
            return name
        await tools["undo"]({"count": 1})
    raise AssertionError(f"neither cut from {name} left the flattened handle")


async def _box_end(tools: dict[str, Any], adapter: Any) -> tuple[list[str], Ring]:
    """The box end near the origin, tilted 15°: a disc and a 12-point opening.

    All three are sketched on a plane 0.13 x Size up along the ring's axis
    from a plane through the z axis, 15° off the Top Plane: the ring tilts
    and covers the handle's end on both faces. The 12 points are two hexagons 30° apart, each its own cut and
    each sized across flats by a dimension. (SolidWorks wouldn't copy a
    circular pattern of one hexagon with the linear pattern that moves the
    box end, so the second hexagon is drawn turned instead.)

    Returns:
        The features for the linear pattern to copy, and the ring: its
        centre (the raised plane's origin) and axis, pointing up.
    """
    s = SIZE_MM
    z_axis = await tools["create_axis"]({"reference": "z"})
    tilted = await _angled_plane(
        tools, adapter, "Top Plane", str(z_axis["axis"]["name"]), facing=1
    )
    tilted, centre, axis = await _raised(tools, adapter, tilted)
    disc = await _sized_sketch(
        tools,
        tilted,
        "add_circle",
        {"center_x": 0, "center_y": 0, "radius": _mm("BoxHead") / 2},
        _mm("BoxHead"),
    )
    boss = await tools["create_extrusion"](
        {"sketch_name": disc, "depth": _mm("HeadT"), "both_directions": True}
    )
    assert boss["status"] == "success", boss
    features = [boss["extrusion"]["name"]]
    for angle in (0.0, 30.0):
        hexagon = await _sized_sketch(
            tools,
            tilted,
            "add_polygon",
            {"center_x": 0, "center_y": 0, "radius": s / 2, "sides": 6, "angle": angle},
            s,
        )
        hole = await tools["create_cut_extrude"](
            {"sketch_name": hexagon, "depth": 1, "end_condition": "ThroughAllBoth"}
        )
        assert hole["status"] == "success", hole
        features.append(hole["cut_extrude"]["name"])
    return features, (centre, axis)


async def _raised(
    tools: dict[str, Any], adapter: Any, tilted: str
) -> tuple[str, tuple[float, ...], tuple[float, ...]]:
    """A plane RING_RISE x Size from ``tilted``, on the upper side.

    Which side an offset plane lands on isn't certain, so its origin is
    measured; one below the Top Plane is undone and made flipped.

    Returns:
        The plane, its origin in mm (the ring's centre) and its normal,
        turned to point up.
    """
    rise = round(SIZE_MM * RING_RISE, 4)
    tried = []
    for flip in (False, True):
        plane = await tools["create_reference_plane"](
            {"reference": tilted, "offset": rise, "flip": flip}
        )
        assert plane["status"] == "success", plane
        name = str(plane["plane"]["name"])
        origin, normal = _plane(adapter, name)
        tried.append([round(c, 3) for c in origin])
        if origin[1] > 0:
            assert math.dist(origin, (0, 0, 0)) == pytest.approx(rise, abs=1e-3), origin
            up = tuple(c if normal[1] > 0 else -c for c in normal)
            return name, tuple(origin), up
        await tools["undo"]({"count": 1})
    raise AssertionError(f"no plane {rise} mm above {tilted}: origins {tried}")


async def _through_circle(tools: dict[str, Any], diameter: float) -> None:
    """A round hole ``diameter`` across at the origin, through everything."""
    sketch = await _sized_sketch(
        tools,
        "Top",
        "add_circle",
        {"center_x": 0, "center_y": 0, "radius": diameter / 2},
        diameter,
    )
    cut = await tools["create_cut_extrude"](
        {"sketch_name": sketch, "depth": 1, "end_condition": "ThroughAllBoth"}
    )
    assert cut["status"] == "success", cut


async def _angled_plane(
    tools: dict[str, Any],
    adapter: Any,
    reference: str,
    axis: str,
    facing: int,
    flip: bool = False,
) -> str:
    """A plane through ``axis`` whose normal is 15° off model axis ``facing``.

    ``flip`` turns it the other way about ``axis``.

    ``create_reference_plane`` at 15° from the Front Plane about y once gave
    a plane whose normal ran along x (SolidWorks 2026, 2026-11-18), so the
    normal is measured: 15° and then 75° are tried, and a plane that faces
    the wrong way is undone.
    """
    made = []
    want = math.cos(math.radians(15.0))
    for angle in (15.0, 75.0):
        plane = await tools["create_reference_plane"](
            {"reference": reference, "angle": angle, "axis": axis, "flip": flip}
        )
        assert plane["status"] == "success", plane
        name = str(plane["plane"]["name"])
        _origin, normal = _plane(adapter, name)
        made.append({"angle": angle, "normal": [round(c, 3) for c in normal]})
        if abs(normal[facing]) == pytest.approx(want, abs=0.01):
            return name
        await tools["undo"]({"count": 1})
    raise AssertionError(f"no plane through {axis} came out at 15°: {made}")


async def _jaw(
    tools: dict[str, Any], adapter: Any, axis: str, ring: Ring
) -> tuple[float, ...]:
    """The jaw: Size wide, cut both ways from the jaw's centre plane.

    On this plane SolidWorks 2026 puts sketch x along the model's y (up) and
    sketch y along the wrench (measured 2026-11-18: a rectangle spanning
    sketch x 0..120 cut a half-depth groove), so the rectangle spans sketch x
    across the whole thickness and sketch y along one side. Which side is
    away from the handle isn't known, and a jaw on the handle's side still
    leaves one body, so the overall size decides: a wrong jaw leaves the open
    end's full radius, 0.2 mm too long. Then the cut and its sketch are undone
    and drawn on the other side.

    Returns:
        The jaw plane's normal: the direction across the jaw.
    """
    # Flipped so the jaw's walls rise towards the handle, as on the reference.
    name = await _angled_plane(tools, adapter, "Front Plane", axis, facing=2, flip=True)
    tried = []
    for y1, y2 in ((-120.0, 0.0), (0.0, 120.0)):
        sketch = await _sketch(tools, name, {"x1": -60, "y1": y1, "x2": 60, "y2": y2})
        cut = await tools["create_cut_extrude"](
            {"sketch_name": sketch, "depth": SIZE_MM, "both_directions": True}
        )
        assert cut["status"] == "success", cut
        size = await _size(tools, SIZE_MM, ring)
        tried.append(
            {"sketch_y": [y1, y2], "cut": cut.get("measured_change"), "size": size}
        )
        if size["verdict"] == "pass":
            _origin, normal = _plane(adapter, name)
            return tuple(normal)
        undone = await tools["undo"]({"count": 2})
        tried[-1]["undone"] = undone.get("data")
    raise AssertionError(f"neither side of the plane gave the jaw its size: {tried}")


async def _relief(tools: dict[str, Any], across: tuple[float, ...]) -> str:
    """Curve the jaw's bottom: an ellipse at the head's centre, cut through.

    Its major axis lies across the jaw (``across``, the jaw plane's normal),
    Size long, so it meets both walls where the flat bottom ended; its minor
    axis, 0.2 x Size, takes the bottom 0.1 x Size past the centre. The half
    towards the opening is inside the jaw already. On the Top Plane sketch x
    is model x and sketch y is model -z.

    Returns:
        The ellipse's sketch.
    """
    angle = math.degrees(math.atan2(-across[2], across[0]))
    made = await tools["create_sketch"]({"plane": "Top"})
    assert made["status"] == "success", made
    ellipse = await tools["add_ellipse"](
        {
            "major_axis": SIZE_MM * RELIEF["across"],
            "minor_axis": SIZE_MM * RELIEF["along"],
            "angle": angle,
        }
    )
    assert ellipse["status"] == "success", ellipse
    for axis, ratio in (("major_axis", "across"), ("minor_axis", "along")):
        sized = await tools["add_sketch_dimension"](
            {
                "entity1": ellipse["ellipse"]["id"],
                "dimension_type": axis,
                "value": SIZE_MM * RELIEF[ratio],
            }
        )
        assert sized["status"] == "success", sized
    closed = await tools["exit_sketch"]()
    assert closed["status"] == "success", closed
    sketch = str(closed.get("sketch", made["sketch"])["name"])
    cut = await tools["create_cut_extrude"](
        {"sketch_name": sketch, "depth": 1, "end_condition": "ThroughAllBoth"}
    )
    assert cut["status"] == "success", cut
    return sketch


def _entry(
    inside: Any, start: tuple[float, float, float], step: float, stop: float
) -> list[float] | None:
    """Where a line along x from ``start`` first enters a head, in metres.

    Marched ``step`` mm at a time up to x = ``stop``: the neck edges for the
    fillets are where the handle's faces and sides meet each head, found
    this way rather than by solving each surface. None if the line never
    enters before ``stop`` (no edge there to fillet).
    """
    point = list(start)
    while (point[0] - stop) * step < 0:
        if inside(point):
            return [round(c / 1000, 6) for c in point]
        point[0] += step
    return None


def _neck_edges(ring: Ring) -> dict[str, list[str]]:
    """Points on the edges where the handle meets each head, 'x,y,z' in metres.

    ``sides``: the handle's rounded sides (y = 0, z = ±half its width);
    ``faces``: its flat faces (z = 0, y = ±half its thickness). The open end
    is a disc about y at the origin; the box end the raised, tilted disc
    ``ring``.
    """
    r_open = _mm("OpenHead") / 2
    r_box = _mm("BoxHead") / 2
    half = _mm("HeadT") / 2
    length = _mm("Length")
    centre = _ring_centre(SIZE_MM, ring)
    ring_axis = ring[1]
    w = _mm("HandleW") / 2
    t = _mm("HandleT") / 2

    def in_open(p: list[float]) -> bool:
        return abs(p[1]) <= half and p[0] ** 2 + p[2] ** 2 <= r_open**2

    def in_box(p: list[float]) -> bool:
        d = (p[0] - centre[0], p[1] - centre[1], p[2] - centre[2])
        along = sum(a * b for a, b in zip(d, ring_axis, strict=False))
        radial = sum(c * c for c in d) - along**2
        return abs(along) <= half and radial <= r_box**2

    # Faces first: a side fillet at the box end ran on round the neck and
    # took the face edge with it (2026-11-18).
    starts = {"faces": [(t, 0.0), (-t, 0.0)], "sides": [(0.0, w), (0.0, -w)]}
    edges: dict[str, list[str]] = {}
    for kind, offsets in starts.items():
        points = []
        for y, z in offsets:
            mid = length / 2
            points.append(_entry(in_open, (mid, y, z), -0.01, 0.0))
            points.append(_entry(in_box, (mid, y, z), 0.01, length))
        edges[kind] = [",".join(str(c) for c in p) for p in points if p]
    return edges


async def _necks(tools: dict[str, Any], ring: Ring) -> list[str]:
    """Fillet the handle into both heads: its faces, then its sides.

    Returns:
        The two fillets.
    """
    names = []
    for kind, points in _neck_edges(ring).items():
        fillet = await tools["add_fillet"](
            {"radius": round(SIZE_MM * FILLET[kind], 4), "edge_names": points}
        )
        assert fillet["status"] == "success", (kind, points, fillet)
        names.append(str(fillet["fillet"]["name"]))
    return names


def _spacing_to_middle(size: float = SIZE_MM) -> float:
    """The lettering pattern's spacing: from the spare block to the handle's middle."""
    return round(HANDLE_MIDDLE * size - SPARE_CENTRE_MM, 4)


async def _lettering(
    tools: dict[str, Any], adapter: Any, x_axis: str, size_dimension: str
) -> list[Any]:
    """Deboss the lettering into the middle of both faces of the handle.

    A sketch text's position can't follow an equation, but a pattern's
    spacing can. So the lettering is cut, centred, into the top and bottom
    faces of a spare block off the open end, as thick as the handle (each
    sketch opened on its face, so the underside's text reads from below);
    a linear pattern moves both cuts to the handle's middle, x =
    HANDLE_MIDDLE x Size, by a spacing an equation drives; then the block is
    cut away, as the box end's pattern seed is. ``WrenchSize``, which the
    text shows, is linked to ``size_dimension`` (one the equations set to
    Size).

    Returns:
        The two lettering sketches, and what each read when written.
    """
    linked = await tools["set_custom_property"](
        {"name": "WrenchSize", "value": f'"{size_dimension}"'}
    )
    assert linked["status"] == "success", linked
    x0, x1 = SPARE_X_MM
    spare = await _sketch(tools, "Top", {"x1": x0, "y1": -15, "x2": x1, "y2": 15})
    block = await tools["create_extrusion"](
        {"sketch_name": spare, "depth": _mm("HandleT"), "both_directions": True}
    )
    assert block["status"] == "success", block
    sketches, reads, cuts = [], [], []
    for y in (_mm("HandleT") / 2, -_mm("HandleT") / 2):
        face = [SPARE_CENTRE_MM, y, 0.0]
        made = await tools["create_sketch"]({"face_point": face})
        assert made["status"] == "success", made
        text = await tools["add_sketch_text"](
            {"text": LETTERING, "height": LETTER_HEIGHT_MM, "center_at": face}
        )
        assert text["status"] == "success", text
        sketches.append(str(made["sketch"]["name"]))
        reads.append(str(text["sketch_text"]["text"]))
        closed = await tools["exit_sketch"]()
        assert closed["status"] == "success", closed
        cut = await tools["create_cut_extrude"](
            {"sketch_name": made["sketch"]["name"], "depth": DEBOSS_MM}
        )
        assert cut["status"] == "success", cut
        cuts.append(cut["cut_extrude"]["name"])
    tried = []
    for reverse in (False, True):
        moved = await tools["pattern_linear"](
            {
                "features": cuts,
                "direction": x_axis,
                "count": 2,
                "spacing": _spacing_to_middle(),
                "reverse": reverse,
            }
        )
        tried.append(moved)
        # The right way cuts the lettering into the handle: volume drops.
        if moved["status"] == "success" and moved["pattern"]["volume_change"] < 0:
            break
        if moved["status"] == "success":
            await tools["undo"]({"count": 1})
    else:
        raise AssertionError(f"the lettering didn't reach the handle: {tried}")
    clear = await _sketch(
        tools, "Top", {"x1": x0 - 20, "y1": -40, "x2": x1 + 20, "y2": 40}
    )
    gone = await tools["create_cut_extrude"](
        {"sketch_name": clear, "depth": 1, "end_condition": "ThroughAllBoth"}
    )
    assert gone["status"] == "success", gone
    assert await _one_body(tools), "the spare block is still there"
    return sketches, reads


async def _reletter(tools: dict[str, Any], sketches: list[str]) -> dict[str, Any]:
    """Re-letter the handle: each lettering sketch's text written again.

    SolidWorks doesn't redraw sketch text when an equation changes the
    model, so the lettering keeps the size it was written at until
    ``set_sketch_text`` writes the same ``$PRP:`` text again, which reads
    the linked Size dimension now (the user's choice: a visible re-letter
    step after each size change).

    Returns:
        The lettering ``before`` and ``after``, both faces.
    """
    before, after = [], []
    for sketch in sketches:
        rewritten = await tools["set_sketch_text"](
            {"sketch_name": sketch, "text": LETTERING}
        )
        assert rewritten["status"] == "success", rewritten
        before += rewritten["sketch_text"]["before"]
        after += rewritten["sketch_text"]["after"]
    return {"before": before, "after": after}


async def build_wrench(
    tools: dict[str, Any], adapter: Any
) -> tuple[str, Ring, tuple[list[str], list[str]]]:
    """The 13 mm combination wrench, at fixed sizes.

    Returns:
        The sketch of the jaw's curved bottom (its two dimensions are
        picked by that sketch, not by value), the box end's ring, and the
        lettering: its two sketches and what they read when written.
    """
    assert (await tools["create_part"]({"name": "wrench"}))["status"] == "success"
    bar = await _sized_sketch(
        tools,
        "Right",
        "add_circle",
        {"center_x": 0, "center_y": 0, "radius": _mm("HandleW") / 2},
        _mm("HandleW"),
    )
    handle = await tools["create_extrusion"](
        {"sketch_name": bar, "depth": _mm("Length")}
    )
    assert handle["status"] == "success", handle
    _frame(adapter, room_for=1.3)  # room for the heads still to come
    await _flatten(tools, adapter, flip=False)
    await _flatten(tools, adapter, flip=True)

    box_features, ring = await _box_end(tools, adapter)
    x_axis = await tools["create_axis"]({"reference": "x"})
    tried = []
    for reverse in (False, True):
        moved = await tools["pattern_linear"](
            {
                "features": box_features,
                "direction": x_axis["axis"]["name"],
                "count": 2,
                "spacing": _mm("Length"),
                "reverse": reverse,
            }
        )
        tried.append(moved)
        if moved["status"] != "success":
            continue  # the tool already removed a pattern that built nothing
        # A lifted seed can float clear of the handle, so the part may be two
        # bodies until the clearance cut; the overall length tells the way
        # instead: about Length plus the ring's reach along the handle,
        # nearly twice Length the wrong way.
        if await _length(tools) < 1.5 * _mm("Length"):
            break
        await tools["undo"]({"count": 1})
    else:
        raise AssertionError(f"the box end didn't reach the handle's end: {tried}")

    # The pattern's seed near the origin pokes out of the open end (it's
    # tilted and raised), so it is cut away; the open end then fills the gap.
    await _through_circle(tools, round(_mm("BoxHead") * CLEARANCE, 4))
    assert await _one_body(tools), "the box end isn't joined to the handle"
    head = await _sized_sketch(
        tools,
        "Top",
        "add_circle",
        {"center_x": 0, "center_y": 0, "radius": _mm("OpenHead") / 2},
        _mm("OpenHead"),
    )
    boss = await tools["create_extrusion"](
        {"sketch_name": head, "depth": _mm("HeadT"), "both_directions": True}
    )
    assert boss["status"] == "success", boss
    y_axis = await tools["create_axis"]({"reference": "y"})
    across = await _jaw(tools, adapter, str(y_axis["axis"]["name"]), ring)
    relief = await _relief(tools, across)
    await _necks(tools, ring)
    steel = await tools["set_material"](
        {"material_name": MATERIAL, "database": MATERIAL_LIBRARY}
    )
    assert steel["status"] == "success", steel
    listed = await tools["list_model_dimensions"]({})
    size_dimension = next(
        str(row["full_name"])
        for row in listed["data"]
        if abs(float(row["value"]) - SIZE_MM) < 1e-3
        and not str(row["full_name"]).endswith(f"@{relief}")
    )
    lettering = await _lettering(
        tools, adapter, str(x_axis["axis"]["name"]), size_dimension
    )
    return relief, ring, lettering


def drivers(dimensions: list[dict[str, Any]], relief: str) -> dict[str, str]:
    """Each dimension's full name -> the expression that will drive it.

    Picked by the value it was built with, so the test doesn't depend on
    SolidWorks' feature numbering. The jaw's ellipse (sketch ``relief``) is
    picked by its sketch: half its long axis is Size / 2, the same number as
    HeadT. Each of its dimensions holds half an axis.
    """
    by_value = {
        _mm("Length"): '"Length"',
        _mm("OpenHead"): '"OpenHead"',
        _mm("BoxHead"): '"BoxHead"',
        _mm("HeadT"): '"HeadT"',
        _mm("HandleW"): '"HandleW"',
        _mm("HandleT") / 2: '"HandleT" / 2',
        round(_mm("BoxHead") * CLEARANCE, 4): f'"BoxHead" * {CLEARANCE}',
        round(SIZE_MM * RING_RISE, 4): f'"Size" * {RING_RISE}',
        SIZE_MM: '"Size"',
        _mm("HandleT"): '"HandleT"',
        _spacing_to_middle(): f'"Size" * {HANDLE_MIDDLE} + {-SPARE_CENTRE_MM:g}mm',
        round(SIZE_MM * FILLET["sides"], 4): f'"Size" * {FILLET["sides"]}',
        round(SIZE_MM * FILLET["faces"], 4): f'"Size" * {FILLET["faces"]}',
    }
    halves = {SIZE_MM * RELIEF[k] / 2: f'"Size" * {RELIEF[k] / 2}' for k in RELIEF}
    found: dict[str, str] = {}
    for row in dimensions:
        if str(row["full_name"]).endswith(f"@{relief}"):
            for value, expression in halves.items():
                if abs(float(row["value"]) - value) < 1e-3:
                    found[row["full_name"]] = expression
            continue
        for value, expression in by_value.items():
            if abs(float(row["value"]) - value) < 1e-3:
                found[row["full_name"]] = expression
    return found


async def _size(tools: dict[str, Any], size: float, ring: Ring) -> dict[str, Any]:
    """verify_model against the wrench's expected size: verdict and box."""
    want = wrench_box(size, ring)
    checked = await tools["verify_model"](
        {"bounding_box_mm": want, "solid_body_count": 1}
    )
    box = checked["measured"]["bounding_box_mm"]
    return {
        "verdict": checked["verdict"],
        "expected_mm": want,
        "measured_mm": box.get("size") if isinstance(box, dict) else box,
    }


@pytest.mark.timeout(1200)  # 25 equations, each a rebuild with the lettering
async def test_a_combination_wrench_sized_by_one_variable(scratch: Any) -> None:
    """One variable, Size, drives a whole combination wrench.

    1. Build a 13 mm wrench at fixed sizes.
    2. Add Size = 13mm and six variables computed from it, and an equation
       on each dimension.
    3. Size = 19mm: one edit regrows the whole wrench.
    4. Size = 8mm in a configuration "8 mm" only; Default stays 19 mm.
    5. An expression naming a variable that doesn't exist is refused and the
       wrench is unchanged.
    """
    tools = await _tools(scratch.adapter)
    relief, ring, (lettering, letters) = await build_wrench(tools, scratch.adapter)
    listed = await tools["list_model_dimensions"]({})
    found = drivers(listed["data"], relief)
    built = await _size(tools, SIZE_MM, ring)
    _frame(
        scratch.adapter,
        room_for=wrench_box(19, ring)[0] / wrench_box(SIZE_MM, ring)[0],
    )
    evidence(
        "A 13 mm combination wrench, built at fixed sizes",
        {
            "dimensions_to_drive": found,
            "size": built,
            "handle_reads": letters,
        },
        call="create_part, 14 sketches, 4 extrusions, 10 cuts, 2 linear patterns, "
        "2 fillets, set_material, set_custom_property, add_sketch_text x 2",
    )
    assert built["verdict"] == "pass", built
    assert sorted(set(found.values())) == sorted(
        [
            '"Length"',
            '"OpenHead"',
            '"BoxHead"',
            '"HeadT"',
            '"HandleW"',
            '"HandleT" / 2',
            f'"BoxHead" * {CLEARANCE}',
            f'"Size" * {RING_RISE}',
            '"Size"',
            '"HandleT"',
            f'"Size" * {HANDLE_MIDDLE} + {-SPARE_CENTRE_MM:g}mm',
            f'"Size" * {FILLET["sides"]}',
            f'"Size" * {FILLET["faces"]}',
            f'"Size" * {RELIEF["across"] / 2}',
            f'"Size" * {RELIEF["along"] / 2}',
        ]
    ), listed

    added = [await tools["set_equation"]({"name": "Size", "expression": "13mm"})]
    for name, ratio in RATIOS.items():
        added.append(
            await tools["set_equation"](
                {"name": name, "expression": f'"Size" * {ratio}'}
            )
        )
    for name, expression in found.items():
        added.append(
            await tools["set_equation"]({"name": name, "expression": expression})
        )
    equations = await tools["list_equations"]()
    _hide_references(scratch.adapter)
    evidence(
        "Size, six variables from it, and an equation on every dimension",
        {
            "added": f"{sum(a['status'] == 'success' for a in added)} of {len(added)}",
            "equations": [
                f"{row['name']} = {row['expression']}"
                for row in equations.get("equations", [])
            ],
        },
        call=f"set_equation x {len(added)}, then list_equations",
    )
    assert all(a["status"] == "success" for a in added), added

    grown = await tools["set_equation"]({"name": "Size", "expression": "19mm"})
    at_19 = await _size(tools, 19, ring)
    relettered_19 = await _reletter(tools, lettering)
    _hide_references(scratch.adapter)
    evidence(
        "Size = 19mm: one edit, the whole wrench regrows",
        {
            "equation": '"Size" = 19mm',
            "change": {
                "Size_mm": [13, grown.get("equation", {}).get("value")],
                "box_mm": [built["measured_mm"], at_19["measured_mm"]],
                "handle_reads": relettered_19,
            },
            "size": at_19,
        },
        call='set_equation({"name": "Size", "expression": "19mm"}), then '
        "set_sketch_text on both lettering sketches (re-letter)",
    )
    assert grown["status"] == "success", grown
    assert at_19["verdict"] == "pass", at_19
    assert all("19.00" in t for t in relettered_19["after"]), relettered_19

    made = await tools["create_configuration"]({"name": "8 mm"})
    assert made["status"] == "success", made
    small = await tools["set_equation"](
        {"name": "Size", "expression": "8mm", "configurations": ["8 mm"]}
    )
    default_size = await _size(tools, 19, ring)
    await tools["activate_configuration"]({"name": "8 mm"})
    small_size = await _size(tools, 8, ring)
    relettered_8 = await _reletter(tools, lettering)
    _hide_references(scratch.adapter)
    evidence(
        'Size = 8mm in configuration "8 mm" only',
        {
            "equation": '"Size" = 8mm, in "8 mm"',
            "change": {
                "Size_mm": {
                    "Default": 19,
                    "8 mm": small.get("equation", {}).get("values"),
                },
                "box_mm": {
                    "Default": default_size["measured_mm"],
                    "8 mm": small_size["measured_mm"],
                },
                "handle_reads": relettered_8,
            },
            "8 mm": small_size,
            "Default": default_size,
        },
        call='set_equation({"name": "Size", "expression": "8mm", '
        '"configurations": ["8 mm"]}), activate_configuration, re-letter',
    )
    assert small["status"] == "success", small
    assert small["equation"]["values"] == {"8 mm": pytest.approx(8.0)}, small
    assert small_size["verdict"] == "pass", small_size
    assert default_size["verdict"] == "pass", default_size
    assert all("8.00" in t for t in relettered_8["after"]), relettered_8

    await tools["activate_configuration"]({"name": "Default"})
    back = await _reletter(tools, lettering)
    refused = await tools["set_equation"]({"name": "Size", "expression": '"Nut" * 2'})
    unchanged = await _size(tools, 19, ring)
    _hide_references(scratch.adapter)
    evidence(
        "A variable that doesn't exist is refused; the wrench is unchanged",
        {
            "equation": '"Size" = "Nut" * 2',
            "refused": [refused["status"], refused.get("error_type")],
            "change": {
                "box_mm": [at_19["measured_mm"], unchanged["measured_mm"]],
                "handle_reads": back["after"],
            },
            "size": unchanged,
        },
        call='set_equation({"name": "Size", "expression": "\\"Nut\\" * 2"})',
    )
    assert refused["error_type"] == "equation_refused", refused
    assert unchanged["verdict"] == "pass", unchanged
