"""The U-joint tool gaps (#209), each checked on real SolidWorks.

One test per changed tool, all called as an agent would (through the MCP
tool functions, with plain dicts):

- a thin wall from an open L-shaped sketch (a bent plate), mid-plane;
- a both-directions extrusion that is symmetric and says so;
- a 60° chamfer, and ``flip`` swapping its legs;
- a plane at 40° to the Top Plane about an axis;
- a plane offset from a sloped face;
- a pin mated concentric in a hole by two face points;
- fixing, floating and flexing components;
- interference before and after the mate, through dict calls.

Run one with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_ujoint_tool_gaps.py::test_a_pin_mates_concentric_in_its_hole_by_two_faces

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows (see
``tests/live/conftest.py``).
"""

from __future__ import annotations

import functools
import json
import math
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.live.evidence import evidence, starting

#: The bent plate: a 80 mm wall and a 40 mm foot, 6.35 mm thick, 38.1 mm wide.
_WALL, _FOOT, _THICK, _WIDE = 80.0, 40.0, 6.35, 38.1

#: Adapter steps the tests take directly; each is also an MCP tool of that name.
_CAPTIONED_STEPS = frozenset(
    {
        "create_part",
        "create_sketch",
        "add_rectangle",
        "add_circle",
        "add_line",
        "exit_sketch",
        "save_file",
        "create_assembly",
        "insert_component",
    }
)


def _shown(value: Any) -> str:
    """One argument as a caption shows it: a file path by its name only."""
    if isinstance(value, str) and ("\\" in value or "/" in value):
        return json.dumps(Path(value).name)
    return json.dumps(value, ensure_ascii=False)


class _Captioned:
    """An adapter whose test-level steps caption the recording as they start.

    A recorded demo then shows every call under the motion it causes, not
    only the final result. Everything else passes straight through.
    """

    def __init__(self, raw: Any) -> None:
        self.raw = raw

    def __getattr__(self, name: str) -> Any:
        member = getattr(self.raw, name)
        if name not in _CAPTIONED_STEPS:
            return member

        @functools.wraps(member)
        async def step(*args: Any) -> Any:
            starting(name, f"{name}({', '.join(_shown(a) for a in args)})")
            return await member(*args)

        return step


@pytest.fixture(autouse=True)
def _caption_steps(scratch: Any) -> Iterator[None]:
    """Caption each direct adapter step; restore the plain adapter for cleanup."""
    raw = scratch.adapter
    scratch.adapter = _Captioned(raw)
    yield
    scratch.adapter = raw


def _captioned_tool(name: str, fn: Any) -> Any:
    """``fn``, captioning the recording with its call as it starts."""

    @functools.wraps(fn)
    async def call(arguments: dict[str, Any]) -> Any:
        starting(name, f"{name}({json.dumps(arguments, ensure_ascii=False)})")
        return await fn(arguments)

    return call


async def _tools(adapter: Any) -> dict[str, Any]:
    """Register the modelling and analysis tools against ``adapter``; name -> fn.

    Each tool captions the recording as it is called. The tools drive the
    plain adapter, so a tool's own adapter call isn't captioned twice.
    """
    from fastmcp import FastMCP

    from solidworks_mcp.tools.analysis import register_analysis_tools
    from solidworks_mcp.tools.modeling import register_modeling_tools

    raw = getattr(adapter, "raw", adapter)
    mcp = FastMCP("ujoint-tool-gaps-live")
    await register_modeling_tools(mcp, raw, {})
    await register_analysis_tools(mcp, raw, {})
    return {t.name: _captioned_tool(t.name, t.fn) for t in await mcp.list_tools()}


async def _summary(adapter: Any) -> dict[str, Any]:
    result = await adapter.get_model_geometry_summary()
    assert result.is_success, result.error
    return result.data


async def _block(adapter: Any, tools: dict[str, Any]) -> None:
    """A 40 x 20 x 10 mm block: x -20..20, y 0..10, z -10..10."""
    assert (await adapter.create_part()).is_success
    sketch = await adapter.create_sketch("Top")
    assert (await adapter.add_rectangle(-20.0, -10.0, 20.0, 10.0)).is_success
    assert (await adapter.exit_sketch()).is_success
    boss = await tools["create_extrusion"]({"sketch_name": sketch.data, "depth": 10.0})
    assert boss["status"] == "success", boss


def _sloped_faces(adapter: Any) -> list[tuple[float, float, float]]:
    """Normals of the active part's flat faces that aren't square to an axis."""
    from solidworks_mcp.adapters.solidworks.face_selection import FaceEdgeSelector

    return [
        f.normal
        for f in FaceEdgeSelector(adapter).faces()
        if f.is_planar and sum(abs(c) > 1e-6 for c in f.normal) > 1
    ]


def _plane(adapter: Any, name: str) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """``(origin_mm, unit normal)`` of a reference plane."""
    from solidworks_mcp.adapters.solidworks.face_selection import FaceEdgeSelector

    origin, normal = FaceEdgeSelector(adapter).plane_geometry(name)
    return tuple(c * 1000 for c in origin), normal


async def _part(scratch: Any, tools: dict[str, Any], path: Path, build: Any) -> str:
    """Build a part with ``build(tools)`` and save it to ``path``."""
    assert (await scratch.adapter.create_part()).is_success
    await build(tools)
    saved = await scratch.adapter.save_file(str(path))
    assert saved.is_success, saved.error
    scratch.written_files.append(str(path))
    return str(path)


async def _plate_and_pin(
    scratch: Any, tools: dict[str, Any], folder: Path, tag: str
) -> tuple[str, str]:
    """A 60 x 40 x 10 plate with a Ø10 hole at x = 20, and a Ø9.5 x 30 pin.

    ``tag`` names the files, so two tests never open same-named parts.
    """
    adapter = scratch.adapter

    async def plate(t: dict[str, Any]) -> None:
        s = await adapter.create_sketch("Top")
        assert (await adapter.add_rectangle(-30.0, -20.0, 30.0, 20.0)).is_success
        assert (await adapter.exit_sketch()).is_success
        assert (await t["create_extrusion"]({"sketch_name": s.data, "depth": 10.0}))[
            "status"
        ] == "success"
        h = await adapter.create_sketch("Top")
        assert (await adapter.add_circle(20.0, 0.0, 5.0)).is_success
        assert (await adapter.exit_sketch()).is_success
        cut = await t["create_cut_extrude"](
            {"sketch_name": h.data, "depth": 10.0, "end_condition": "ThroughAllBoth"}
        )
        assert cut["status"] == "success", cut

    async def pin(t: dict[str, Any]) -> None:
        s = await adapter.create_sketch("Top")
        assert (await adapter.add_circle(0.0, 0.0, 4.75)).is_success
        assert (await adapter.exit_sketch()).is_success
        assert (await t["create_extrusion"]({"sketch_name": s.data, "depth": 30.0}))[
            "status"
        ] == "success"

    return (
        await _part(scratch, tools, folder / f"{tag}_plate.SLDPRT", plate),
        await _part(scratch, tools, folder / f"{tag}_pin.SLDPRT", pin),
    )


async def _plate_then_pin(adapter: Any) -> tuple[str, str]:
    """The plate's and the pin's instance names, by name, not list order."""
    names = (await adapter.list_components()).data
    plate = next(n for n in names if "_plate" in n)
    pin = next(n for n in names if "_pin" in n)
    return plate, pin


def _transforms(adapter: Any) -> dict[str, list[float]]:
    """Each top-level component's ``Transform2.ArrayData`` (rotation, then m)."""
    from solidworks_mcp.adapters import sw_type_info

    assembly = sw_type_info.flagged(adapter.currentModel, "IAssemblyDoc")
    out = {}
    for component in assembly.GetComponents(True):
        c = sw_type_info.flagged(component, "IComponent2")
        out[str(c.Name2)] = list(c.Transform2.ArrayData)
    return out


def _axis_point_mm(data: list[float], y: float) -> tuple[float, float, float]:
    """Where the part point (0, y, 0) mm lands in the assembly, in mm.

    Only the rotation's y column matters for a point on the y axis.
    """
    return (
        data[3] * y + data[9] * 1000,
        data[4] * y + data[10] * 1000,
        data[5] * y + data[11] * 1000,
    )


async def _seat_pin(
    tools: dict[str, Any], plate: str, pin: str
) -> list[dict[str, Any]]:
    """Two face mates: the pin concentric in the hole, its bottom on the plate's."""
    concentric = {
        "component_a": plate,
        "component_b": pin,
        "face_a": [25.0, 5.0, 0.0],  # the hole's wall, 5 mm from its axis at x = 20
        "face_b": [4.75, 15.0, 0.0],  # the pin's round face
        "mate_type": "concentric",
    }
    flush = {
        "component_a": plate,
        "component_b": pin,
        "face_a": [-20.0, 0.0, 0.0],  # the plate's bottom, clear of the hole
        "face_b": [0.0, 0.0, 0.0],  # the pin's bottom
        "mate_type": "coincident",
        "alignment": "aligned",
    }
    return [await tools["add_mate"](concentric), await tools["add_mate"](flush)]


@pytest.mark.asyncio
async def test_a_thin_wall_from_an_open_sketch_makes_a_bent_plate(scratch) -> None:
    """An open L, 6.35 mm thin wall, mid-plane both ways: one body, exact volume."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    assert (await adapter.create_part()).is_success
    sketch = await adapter.create_sketch("Right")
    assert (await adapter.add_line(0.0, 0.0, 0.0, _WALL)).is_success
    assert (await adapter.add_line(0.0, 0.0, _FOOT, 0.0)).is_success
    assert (await adapter.exit_sketch()).is_success

    call = {
        "sketch_name": sketch.data,
        "depth": _WIDE,
        "both_directions": True,
        "thin_feature": True,
        "thin_thickness": _THICK,
        "thin_side": "mid_plane",
    }
    result = await tools["create_extrusion"](call)
    summary = await _summary(adapter)
    expected = (_WALL + _FOOT) * _THICK * _WIDE  # mid-plane: corners cancel
    evidence(
        f"open L, thin 6.35 mm mid-plane, 38.1 mm both ways (expect {expected:.0f} mm³)",
        {
            "extrusion": result.get("extrusion"),
            "volume_mm3": summary["volume_mm3"],
            "solid_bodies": summary.get("solid_body_count"),
            "x_mm": [
                summary["bounding_box_mm"]["min"][0],
                summary["bounding_box_mm"]["max"][0],
            ],
        },
        call=f"create_extrusion({call})",
    )
    assert result["status"] == "success", result
    assert result["extrusion"]["end_condition"] == "MidPlane"
    assert result["extrusion"]["thin"] == {"thickness": _THICK, "side": "mid_plane"}
    assert summary["solid_body_count"] == 1
    assert summary["volume_mm3"] == pytest.approx(expected, rel=0.01)
    assert summary["bounding_box_mm"]["min"][0] == pytest.approx(-_WIDE / 2, abs=0.01)
    assert summary["bounding_box_mm"]["max"][0] == pytest.approx(_WIDE / 2, abs=0.01)


@pytest.mark.asyncio
async def test_both_directions_is_symmetric_and_says_mid_plane(scratch) -> None:
    """A 20 mm both-ways extrusion spans -10..10 and reports MidPlane."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    assert (await adapter.create_part()).is_success
    sketch = await adapter.create_sketch("Front")
    assert (await adapter.add_rectangle(-15.0, -10.0, 15.0, 10.0)).is_success
    assert (await adapter.exit_sketch()).is_success

    call = {"sketch_name": sketch.data, "depth": 20.0, "both_directions": True}
    result = await tools["create_extrusion"](call)
    box = (await _summary(adapter))["bounding_box_mm"]
    evidence(
        "both_directions: 20 mm about the Front Plane (expect z -10..10)",
        {"extrusion": result.get("extrusion"), "z_mm": [box["min"][2], box["max"][2]]},
        call=f"create_extrusion({call})",
    )
    assert result["extrusion"]["end_condition"] == "MidPlane"
    assert box["min"][2] == pytest.approx(-10.0, abs=0.01)
    assert box["max"][2] == pytest.approx(10.0, abs=0.01)


@pytest.mark.asyncio
async def test_a_60_degree_chamfer_and_flip_swaps_its_legs(scratch) -> None:
    """2 mm at 60°: the right volume, and flip turns a 60° face into a 30° one."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    await _block(adapter, tools)
    before = (await _summary(adapter))["volume_mm3"]
    removed = 0.5 * 2.0 * 2.0 * math.tan(math.radians(60)) * 40.0

    first = {"distance": 2.0, "angle": 60, "edge_names": ["0,0.01,0.01"]}
    chamfer = await tools["add_chamfer"](first)
    after_first = (await _summary(adapter))["volume_mm3"]
    slopes = _sloped_faces(adapter)
    tilt_1 = math.degrees(math.acos(abs(slopes[0][1])))
    evidence(
        f"chamfer 2 mm at 60° along a 40 mm edge (expect -{removed:.1f} mm³)",
        {
            "chamfer": chamfer.get("chamfer"),
            "volume_change_mm3": round(after_first - before, 2),
            "face_tilt_from_top_deg": round(tilt_1, 2),
        },
        call=f"add_chamfer({first})",
    )
    assert chamfer["status"] == "success", chamfer
    assert before - after_first == pytest.approx(removed, rel=0.01)

    second = {
        "distance": 2.0,
        "angle": 60,
        "flip": True,
        "edge_names": ["0,0.01,-0.01"],
    }
    flipped = await tools["add_chamfer"](second)
    after_second = (await _summary(adapter))["volume_mm3"]
    tilts = sorted(
        round(math.degrees(math.acos(abs(n[1]))), 2) for n in _sloped_faces(adapter)
    )
    evidence(
        "the same chamfer with flip on the opposite edge (expect the other leg)",
        {
            "chamfer": flipped.get("chamfer"),
            "volume_change_mm3": round(after_second - after_first, 2),
            "face_tilts_from_top_deg": tilts,
        },
        call=f"add_chamfer({second})",
    )
    assert after_first - after_second == pytest.approx(removed, rel=0.01)
    assert tilts == pytest.approx([30.0, 60.0], abs=0.1)


@pytest.mark.asyncio
async def test_a_plane_at_40_degrees_about_an_axis(scratch) -> None:
    """create_axis names the axis; the plane is 40° from the Top Plane about it."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    await _block(adapter, tools)

    axis = await tools["create_axis"]({"reference": "x"})
    call = {"reference": "Top Plane", "angle": 40, "axis": axis["axis"]["name"]}
    plane = await tools["create_reference_plane"](call)
    _origin, normal = _plane(adapter, plane["plane"]["name"])
    tilt = math.degrees(math.acos(abs(normal[1])))
    evidence(
        "a plane at 40° to the Top Plane about the x axis",
        {
            "axis": axis["axis"]["name"],
            "plane": plane.get("plane"),
            "tilt_deg": round(tilt, 3),
        },
        call=f"create_reference_plane({call})",
    )
    assert axis["axis"]["name"], axis
    assert plane["status"] == "success", plane
    assert tilt == pytest.approx(40.0, abs=0.01)
    assert abs(normal[0]) < 1e-6  # rotated about x


@pytest.mark.asyncio
async def test_a_plane_offset_from_a_sloped_face(scratch) -> None:
    """A 3-4-5 wedge: a plane 5 mm off its slope, parallel to it."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    assert (await adapter.create_part()).is_success
    sketch = await adapter.create_sketch("Front")
    for line in ((0, 0, 40, 0), (40, 0, 0, 30), (0, 30, 0, 0)):
        assert (await adapter.add_line(*map(float, line))).is_success
    assert (await adapter.exit_sketch()).is_success
    assert (
        await tools["create_extrusion"]({"sketch_name": sketch.data, "depth": 10.0})
    )["status"] == "success"

    call = {"face_point": [20.0, 15.0, 5.0], "offset": 5.0}
    plane = await tools["create_reference_plane"](call)
    origin, normal = _plane(adapter, plane["plane"]["name"])
    # The slope is 0.6 x + 0.8 y = 24 mm; the new plane is 5 mm from it.
    unit = (0.6, 0.8, 0.0)
    gap = abs(abs(sum(a * b for a, b in zip(origin, unit, strict=True))) - 24.0)
    evidence(
        "a plane 5 mm off the wedge's 3-4-5 slope",
        {
            "plane": plane.get("plane"),
            "normal": [round(c, 4) for c in normal],
            "gap_from_slope_mm": round(gap, 4),
        },
        call=f"create_reference_plane({call})",
    )
    assert plane["status"] == "success", plane
    assert [abs(c) for c in normal] == pytest.approx([0.6, 0.8, 0.0], abs=1e-4)
    assert gap == pytest.approx(5.0, abs=0.01)


@pytest.mark.asyncio
async def test_a_pin_mates_concentric_in_its_hole_by_two_faces(
    scratch, tmp_path
) -> None:
    """Two face mates by points in each part's own coordinates seat the pin in its hole."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    plate, pin = await _plate_and_pin(scratch, tools, tmp_path, "mate")
    assert (await adapter.create_assembly()).is_success
    assert (await adapter.insert_component(plate, 0.0, 0.0, 0.0)).is_success
    assert (await adapter.insert_component(pin, 100.0, 0.0, 0.0)).is_success
    scratch.written_files.append(str(tmp_path / "gap_assembly.SLDASM"))
    plate_name, pin_name = await _plate_then_pin(adapter)

    concentric, flush = await _seat_pin(tools, plate_name, pin_name)
    placed = _transforms(adapter)
    hole = _axis_point_mm(placed[plate_name], 0.0)  # the plate's bottom, on its origin
    ends = sorted(
        _axis_point_mm(placed[pin_name], y) for y in (0.0, 30.0)
    )  # the pin's axis, bottom to top
    axis = [round(ends[0][0] - hole[0], 3), round(ends[0][2] - hole[2], 3)]
    span = [round(ends[0][1] - hole[1], 3), round(ends[1][1] - hole[1], 3)]
    evidence(
        "pin seated in the plate's hole by two face mates (expect axis 20, 0; y 0..30)",
        {
            "mates": [m.get("mate", m).get("entities") for m in (concentric, flush)],
            "pin_axis_from_plate_mm": axis,
            "pin_height_above_plate_bottom_mm": span,
        },
        call="add_mate(concentric, faces), add_mate(coincident, bottoms)",
    )
    assert concentric["status"] == "success", concentric
    assert flush["status"] == "success", flush
    assert axis == pytest.approx([20.0, 0.0], abs=0.01)
    assert span == pytest.approx([0.0, 30.0], abs=0.01)


@pytest.mark.asyncio
async def test_components_fix_float_and_a_sub_assembly_turns_flexible(
    scratch, tmp_path
) -> None:
    """Float and fix a part; flex a sub-assembly, keeping its other settings."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    plate, pin = await _plate_and_pin(scratch, tools, tmp_path, "state")
    assert (await adapter.create_assembly()).is_success
    assert (await adapter.insert_component(plate, 0.0, 0.0, 0.0)).is_success
    assert (await adapter.insert_component(pin, 100.0, 0.0, 0.0)).is_success
    sub = tmp_path / "gap_pin_plate.SLDASM"
    assert (await adapter.save_file(str(sub))).is_success
    scratch.written_files.append(str(sub))
    plate_name, _pin_name = await _plate_then_pin(adapter)

    floated = await tools["set_component_state"](
        {"component": plate_name, "fixed": False}
    )
    fixed = await tools["set_component_state"]({"component": plate_name, "fixed": True})
    evidence(
        "the first part in, which SolidWorks fixes: floated, then fixed again",
        {"floated": floated.get("message"), "fixed": fixed.get("message")},
        call=f'set_component_state({{"component": "{plate_name}", "fixed": false}})',
    )
    assert floated["state"]["before"]["fixed"] is True
    assert floated["state"]["after"]["fixed"] is False
    assert fixed["state"]["after"]["fixed"] is True

    assert (await adapter.create_assembly()).is_success
    assert (await adapter.insert_component(str(sub), 0.0, 0.0, 0.0)).is_success
    scratch.written_files.append(str(tmp_path / "gap_main.SLDASM"))
    sub_name = (await adapter.list_components()).data[0]
    flexed = await tools["set_component_state"](
        {"component": sub_name, "flexible": True}
    )
    kept = ("suppression", "visible", "referenced_configuration", "exclude_from_bom")
    evidence(
        "the pin-and-plate sub-assembly made flexible; everything else kept",
        {
            "message": flexed.get("message"),
            "before": {
                k: flexed["state"]["before"].get(k) for k in ("flexible", *kept)
            },
            "after": {k: flexed["state"]["after"].get(k) for k in ("flexible", *kept)},
        },
        call=f'set_component_state({{"component": "{sub_name}", "flexible": true}})',
    )
    assert flexed["status"] == "success", flexed
    assert flexed["state"]["after"]["flexible"] is True
    for key in kept:
        assert flexed["state"]["after"][key] == flexed["state"]["before"][key], key
    rigid = await tools["set_component_state"](
        {"component": sub_name, "flexible": False}
    )
    evidence(
        "the sub-assembly back to rigid",
        {
            "message": rigid.get("message"),
            "flexible": [
                rigid["state"]["before"].get("flexible"),
                rigid["state"]["after"].get("flexible"),
            ],
        },
        call=f'set_component_state({{"component": "{sub_name}", "flexible": false}})',
    )
    assert rigid["state"]["after"]["flexible"] is False


@pytest.mark.asyncio
async def test_interference_is_fresh_after_a_mate(scratch, tmp_path) -> None:
    """Called with dicts: the pin overlaps the plate, then sits in the Ø10 hole clear."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    plate, pin = await _plate_and_pin(scratch, tools, tmp_path, "clash")
    assert (await adapter.create_assembly()).is_success
    assert (await adapter.insert_component(plate, 0.0, 0.0, 0.0)).is_success
    assert (await adapter.insert_component(pin, 0.0, 0.0, 0.0)).is_success
    scratch.written_files.append(str(tmp_path / "gap_clash.SLDASM"))
    plate_name, pin_name = await _plate_then_pin(adapter)
    check = {"components": [plate_name, pin_name]}

    clash = await tools["check_interference"](check)
    seated = await _seat_pin(tools, plate_name, pin_name)
    assert all(m["status"] == "success" for m in seated), seated
    clear = await tools["check_interference"](check)
    before = clash["data"]["interference_count"]
    after = clear["data"]["interference_count"]
    evidence(
        "interference: the pin through solid plate, then seated in the Ø10 hole",
        {"before_mate": before, "after_mate": after},
        call=f"check_interference({check})",
    )
    assert clash["status"] == "success", clash
    assert clear["status"] == "success", clear
    assert before >= 1
    assert after == 0
