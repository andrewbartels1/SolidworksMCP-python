"""A combination wrench sized by one global variable (the equations demo).

The wrench follows the usual combination-wrench layout (ISO 3318 / DIN 3113):
an open end with its jaw at 15° to the handle, a 12-point box end, and a flat
handle with rounded edges. It is built at Size = 13 mm with fixed numbers,
then ``set_equation`` ties every size to ``Size``, so one edit makes a 19 mm
wrench and a configuration holds an 8 mm one.

Each size is a dimension that grows from the centre, so the wrench keeps its
shape at any size:

- the handle is a round bar along x (its diameter is the handle's width, its
  length the distance between the heads), flattened by two cuts from planes
  offset either side of the Top Plane (the offsets are its thickness);
- the box end is a disc with two hexagon cuts 30° apart (a 12-point opening,
  the hexagon sized across flats), built at the origin and moved to the far
  end by a linear pattern whose spacing is the length;
- the open end is a larger disc at the origin, which fills the pattern's seed,
  and a jaw cut both ways from a plane at 15°, so the cut's depth is the jaw.

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

#: Each global variable as a multiple of Size (a 13 mm wrench is 169 mm
#: between head centres, with a Ø31.2 open end and a Ø23.4 box end).
RATIOS = {
    "Length": 13.0,
    "OpenHead": 2.4,
    "BoxHead": 1.8,
    "HeadT": 0.45,
    "HandleW": 0.95,
    "HandleT": 0.32,
}
JAW_ANGLE_DEG = 15.0
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


def wrench_box(size: float) -> list[float]:
    """The wrench's overall size [x, y, z] in mm for a given Size.

    x: the box end reaches Length + BoxHead/2. The jaw takes the open end's
    tip off; what stays furthest out is the jaw corner nearer the axis,
    a = √(R² − (S/2)²) along the jaw and S/2 across it, turned by 15°.
    y: the heads' thickness. z: the open end's diameter.
    """
    r = _mm("OpenHead", size) / 2
    a = math.sqrt(r**2 - (size / 2) ** 2)
    turn = math.radians(JAW_ANGLE_DEG)
    open_reach = a * math.cos(turn) + size / 2 * math.sin(turn)
    x = open_reach + _mm("Length", size) + _mm("BoxHead", size) / 2
    return [round(x, 2), round(_mm("HeadT", size), 2), round(2 * r, 2)]


async def _one_body(tools: dict[str, Any]) -> bool:
    """Whether the part is still one solid body."""
    checked = await tools["verify_model"]({"solid_body_count": 1})
    return bool(checked["verdict"] == "pass")


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


async def _flatten(tools: dict[str, Any], adapter: Any, flip: bool) -> None:
    """Cut the bar away beyond a plane HandleT/2 above (or below) the Top Plane.

    Which way a cut goes from a reference plane isn't certain, so the volume
    decides: the right cut takes off one rounded cap and leaves more than half
    the bar (58-70 %); the wrong one leaves less (30-42 %), or SolidWorks
    refuses it because nothing would be left. Then the cut is undone and made
    the other way, from the same sketch.
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
            return
        await tools["undo"]({"count": 1})
    raise AssertionError(f"neither cut from {name} left the flattened handle")


async def _box_end(tools: dict[str, Any]) -> list[str]:
    """The box end at the origin: a disc and a 12-point opening; its features.

    The 12 points are two hexagons 30° apart, each its own cut and each sized
    across flats by a dimension. (SolidWorks wouldn't copy a circular pattern
    of one hexagon with the linear pattern that moves the box end, so the
    second hexagon is drawn turned instead.)
    """
    s = SIZE_MM
    disc = await _sized_sketch(
        tools,
        "Top",
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
            "Top",
            "add_polygon",
            {"center_x": 0, "center_y": 0, "radius": s / 2, "sides": 6, "angle": angle},
            s,
        )
        hole = await tools["create_cut_extrude"](
            {"sketch_name": hexagon, "depth": 1, "end_condition": "ThroughAllBoth"}
        )
        assert hole["status"] == "success", hole
        features.append(hole["cut_extrude"]["name"])
    return features


async def _jaw_plane(tools: dict[str, Any], adapter: Any, axis: str) -> str:
    """A plane through the y axis, 15° off the Front Plane: the jaw's centre plane.

    Its normal must be within 15° of z, so a sketch on it runs along the
    wrench (x). ``create_reference_plane`` at 15° from the Front Plane gave a
    plane whose normal ran along x on SolidWorks 2026 (measured 2026-11-18:
    both sides of it cut the same volume), so the normal is measured, and a
    plane that faces the wrong way is undone and made from the Right Plane.
    """
    made = []
    for reference in ("Front Plane", "Right Plane"):
        plane = await tools["create_reference_plane"](
            {"reference": reference, "angle": JAW_ANGLE_DEG, "axis": axis}
        )
        assert plane["status"] == "success", plane
        name = str(plane["plane"]["name"])
        _origin, normal = _plane(adapter, name)
        made.append({"reference": reference, "normal": [round(c, 3) for c in normal]})
        if abs(normal[2]) == pytest.approx(
            math.cos(math.radians(JAW_ANGLE_DEG)), abs=0.01
        ):
            return name
        await tools["undo"]({"count": 1})
    raise AssertionError(f"no plane through y faced z at 15°: {made}")


async def _jaw(tools: dict[str, Any], adapter: Any, axis: str) -> None:
    """The jaw: Size wide, cut both ways from the jaw's centre plane.

    On this plane SolidWorks 2026 puts sketch x along the model's y (up) and
    sketch y along the wrench (measured 2026-11-18: a rectangle spanning
    sketch x 0..120 cut a half-depth groove), so the rectangle spans sketch x
    across the whole thickness and sketch y along one side. Which side is
    away from the handle isn't known, and a jaw on the handle's side still
    leaves one body, so the overall size decides: a wrong jaw leaves the open
    end's full radius, 0.2 mm too long. Then the cut and its sketch are undone
    and drawn on the other side.
    """
    name = await _jaw_plane(tools, adapter, axis)
    tried = []
    for y1, y2 in ((-120.0, 0.0), (0.0, 120.0)):
        sketch = await _sketch(tools, name, {"x1": -60, "y1": y1, "x2": 60, "y2": y2})
        cut = await tools["create_cut_extrude"](
            {"sketch_name": sketch, "depth": SIZE_MM, "both_directions": True}
        )
        assert cut["status"] == "success", cut
        size = await _size(tools, SIZE_MM)
        tried.append(
            {"sketch_y": [y1, y2], "cut": cut.get("measured_change"), "size": size}
        )
        if size["verdict"] == "pass":
            return
        undone = await tools["undo"]({"count": 2})
        tried[-1]["undone"] = undone.get("data")
    raise AssertionError(f"neither side of the plane gave the jaw its size: {tried}")


async def build_wrench(tools: dict[str, Any], adapter: Any) -> None:
    """The 13 mm combination wrench, at fixed sizes."""
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

    box_features = await _box_end(tools)
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
        if await _one_body(tools):
            break
        await tools["undo"]({"count": 1})
    else:
        raise AssertionError(f"the box end didn't reach the handle's end: {tried}")

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
    await _jaw(tools, adapter, str(y_axis["axis"]["name"]))


def drivers(dimensions: list[dict[str, Any]]) -> dict[str, str]:
    """Each dimension's full name -> the expression that will drive it.

    Picked by the value it was built with, so the test doesn't depend on
    SolidWorks' feature numbering.
    """
    by_value = {
        _mm("Length"): '"Length"',
        _mm("OpenHead"): '"OpenHead"',
        _mm("BoxHead"): '"BoxHead"',
        _mm("HeadT"): '"HeadT"',
        _mm("HandleW"): '"HandleW"',
        _mm("HandleT") / 2: '"HandleT" / 2',
        SIZE_MM: '"Size"',
    }
    found: dict[str, str] = {}
    for row in dimensions:
        for value, expression in by_value.items():
            if abs(float(row["value"]) - value) < 1e-3:
                found[row["full_name"]] = expression
    return found


async def _size(tools: dict[str, Any], size: float) -> dict[str, Any]:
    """verify_model against the wrench's expected size: verdict and box."""
    want = wrench_box(size)
    checked = await tools["verify_model"](
        {"bounding_box_mm": want, "solid_body_count": 1}
    )
    box = checked["measured"]["bounding_box_mm"]
    return {
        "verdict": checked["verdict"],
        "expected_mm": want,
        "measured_mm": box.get("size") if isinstance(box, dict) else box,
    }


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
    await build_wrench(tools, scratch.adapter)
    listed = await tools["list_model_dimensions"]({})
    found = drivers(listed["data"])
    built = await _size(tools, SIZE_MM)
    _frame(scratch.adapter, room_for=wrench_box(19)[0] / wrench_box(SIZE_MM)[0])
    evidence(
        "A 13 mm combination wrench, built at fixed sizes",
        {"dimensions_to_drive": found, "size": built},
        call="create_part, 8 sketches, 3 extrusions, 5 cuts, a linear pattern",
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
            '"Size"',
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
    at_19 = await _size(tools, 19)
    _hide_references(scratch.adapter)
    evidence(
        "Size = 19mm: one edit, the whole wrench regrows",
        {"set": grown.get("equation"), "size": at_19},
        call='set_equation({"name": "Size", "expression": "19mm"})',
    )
    assert grown["status"] == "success", grown
    assert at_19["verdict"] == "pass", at_19

    made = await tools["create_configuration"]({"name": "8 mm"})
    assert made["status"] == "success", made
    small = await tools["set_equation"](
        {"name": "Size", "expression": "8mm", "configurations": ["8 mm"]}
    )
    default_size = await _size(tools, 19)
    await tools["activate_configuration"]({"name": "8 mm"})
    small_size = await _size(tools, 8)
    _hide_references(scratch.adapter)
    evidence(
        'Size = 8mm in configuration "8 mm" only',
        {"set": small.get("equation"), "8 mm": small_size, "Default": default_size},
        call='set_equation({"name": "Size", "expression": "8mm", '
        '"configurations": ["8 mm"]})',
    )
    assert small["status"] == "success", small
    assert small["equation"]["values"] == {"8 mm": pytest.approx(8.0)}, small
    assert small_size["verdict"] == "pass", small_size
    assert default_size["verdict"] == "pass", default_size

    await tools["activate_configuration"]({"name": "Default"})
    refused = await tools["set_equation"]({"name": "Size", "expression": '"Nut" * 2'})
    unchanged = await _size(tools, 19)
    _hide_references(scratch.adapter)
    evidence(
        "A variable that doesn't exist is refused; the wrench is unchanged",
        {
            "refused": [refused["status"], refused.get("error_type")],
            "size": unchanged,
        },
        call='set_equation({"name": "Size", "expression": "\\"Nut\\" * 2"})',
    )
    assert refused["error_type"] == "equation_refused", refused
    assert unchanged["verdict"] == "pass", unchanged
