"""Part features (queue item 11), checked on real SolidWorks.

One bundle, run together, then failures are fixed one at a time:

1. the Hole Wizard diagnostic: each hole type for ISO and ANSI inch;
2. ``create_hole`` blind and through, and a point off the part refused;
3. ``pattern_linear``: a row of three and a 3 x 2 grid of holes;
4. ``create_shell``: an open box with 2 mm walls;
5. ``add_draft``: two side walls drafted 3 degrees;
6. ``create_rib``: a rib across the open box;
7. ``add_cosmetic_thread`` on a 10 mm shaft, volume unchanged;
8. ``sketch_convert_entities``: the top face's outline, cut 2 mm down;
9. ``create_hole`` with ``positions`` on a plate: counterbores (mirrored),
   countersinks and tapped holes from points, a ring of six, and a point off
   the face refused on purpose (the docs demo).

The block every test starts from is 40 x 40 x 20 mm on the Top Plane: x and
z from -20 to 20, y from 0 to 20, so its top face is at y = 20.

Run one with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_part_features.py::test_shell_an_open_box

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows (see
``tests/live/conftest.py``).
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.live.evidence import evidence, note, starting
from tests.live.test_live_sw_beta_tools import _sketch

pytestmark = pytest.mark.asyncio

_BLOCK = 40.0 * 40.0 * 20.0
_TOP = [0.0, 20.0, 0.0]


async def _tools(adapter: Any) -> dict[str, Any]:
    """The modeling and sketching tools on ``adapter``; name -> fn."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools.analysis import register_analysis_tools
    from solidworks_mcp.tools.modeling import register_modeling_tools
    from solidworks_mcp.tools.sketching import register_sketching_tools

    mcp = FastMCP("part-features-live")
    for register in (
        register_modeling_tools,
        register_sketching_tools,
        register_analysis_tools,
    ):
        await register(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


async def _block(tools: dict[str, Any], name: str) -> None:
    """A new part holding the 40 x 40 x 20 mm block."""
    assert (await tools["create_part"]({"name": name}))["status"] == "success"
    await _sketch(tools, "Top", {"x1": -20, "y1": -20, "x2": 20, "y2": 20})
    made = await tools["create_extrusion"]({"depth": 20})
    assert made["status"] == "success", made


async def _volume(tools: dict[str, Any]) -> float:
    """The part's volume in mm³."""
    mass = await tools["get_mass_properties"]()
    assert mass["status"] == "success", mass
    return float(mass["mass_properties"]["volume"]["value"])


_HOLE_GRID = [
    ("simple", "iso", "Ø6.0"),
    ("counterbore", "iso", "M6"),
    ("countersink", "iso", "M6"),
    ("tapped", "iso", "M6x1.0"),
    ("simple", "ansi_inch", "1/4"),
    ("counterbore", "ansi_inch", "#10"),
    ("countersink", "ansi_inch", "#10"),
    ("tapped", "ansi_inch", "#10-24"),
]


async def test_hole_wizard_diagnostic(scratch: Any) -> None:
    """Each hole type for ISO and ANSI inch, 20 mm apart on an 80 x 40 block.

    Holes up to a 12.4 mm countersink fit without overlapping. Any rebuild
    warning SolidWorks gives a hole is printed with it.
    """
    tools = await _tools(scratch.adapter)
    assert (await tools["create_part"]({"name": "hole_grid"}))["status"] == "success"
    await _sketch(tools, "Top", {"x1": -40, "y1": -20, "x2": 40, "y2": 20})
    made = await tools["create_extrusion"]({"depth": 20})
    assert made["status"] == "success", made
    spots = [(x, z) for z in (-10.0, 10.0) for x in (-30.0, -10.0, 10.0, 30.0)]

    results: dict[str, Any] = {}
    for (hole_type, standard, size), (x, z) in zip(_HOLE_GRID, spots, strict=True):
        made = await tools["create_hole"](
            {
                "face_point": [x, 20.0, z],
                "hole_type": hole_type,
                "standard": standard,
                "size": size,
                "end_condition": "blind",
                "depth": 8,
            }
        )
        if made["status"] != "success":
            results[f"{hole_type}/{standard}/{size}"] = made["message"]
            continue
        hole = made["hole"]
        results[f"{hole_type}/{standard}/{size}"] = {
            "volume_change": round(hole["volume_change"], 1),
            "warnings": [
                f"{w['code_name']}: {w['description']}"
                for w in hole.get("rebuild_warnings", [])
            ],
        }

    evidence("Hole Wizard: each type and standard", results)
    failed = {k: v for k, v in results.items() if isinstance(v, str)}
    assert not failed, failed


async def test_simple_hole_through_all_diagnostic(scratch: Any) -> None:
    """Why a simple ISO hole through all makes no hole (Ø6.0 blind builds).

    Six raw ``HoleWizard5`` calls on an 80 x 40 block, each changing one
    thing: the end condition, an explicit diameter or depth, and the ISO
    screw-clearance table (144, sized ``M6``) in place of drill sizes (143).
    Each row says whether a feature came back and the volume it removed.
    """
    from solidworks_mcp.adapters.solidworks import part_features as pf

    tools = await _tools(scratch.adapter)
    assert (await tools["create_part"]({"name": "simple_hole_probe"}))[
        "status"
    ] == "success"
    await _sketch(tools, "Top", {"x1": -40, "y1": -20, "x2": 40, "y2": 20})
    assert (await tools["create_extrusion"]({"depth": 20}))["status"] == "success"
    adapter = scratch.adapter
    blind, through = (
        pf.HOLE_END_CONDITIONS["blind"],
        pf.HOLE_END_CONDITIONS["through_all"],
    )
    drill, clearance = 143, 144
    probes = [
        ("drill Ø6.0 blind 8 (control)", drill, "Ø6.0", blind, -1.0, 0.008),
        ("drill Ø6.0 through, all -1", drill, "Ø6.0", through, -1.0, -1.0),
        ("drill Ø6.0 through, diameter 6", drill, "Ø6.0", through, 0.006, -1.0),
        ("drill Ø6.0 through, depth 20", drill, "Ø6.0", through, -1.0, 0.02),
        ("drill Ø6.0 through, both", drill, "Ø6.0", through, 0.006, 0.02),
        ("clearance M6 through, all -1", clearance, "M6", through, -1.0, -1.0),
    ]
    spots = [(x, z) for z in (-10.0, 10.0) for x in (-30.0, -10.0, 10.0)]

    async def volume() -> float:
        mass = await tools["get_mass_properties"]()
        return float(mass["mass_properties"]["volume"]["value"])

    results: dict[str, Any] = {}
    for (label, fastener, size, end, diameter, depth), (x, z) in zip(
        probes, spots, strict=True
    ):
        before = await volume()

        def call(
            fastener: int = fastener,
            size: str = size,
            end: int = end,
            diameter: float = diameter,
            depth: float = depth,
            x: float = x,
            z: float = z,
        ) -> bool:
            model = adapter.currentModel
            model.ClearSelection2(True)
            model.ForceRebuild3(True)
            if not model.Extension.SelectByID2(
                "", "FACE", x / 1000, 0.02, z / 1000, False, 0, pf._null_callout(), 0
            ):
                raise LookupError("face not selected")
            manager = pf.sw_type_info.flagged(model.FeatureManager, "IFeatureManager")
            feature = manager.HoleWizard5(
                pf.HOLE_TYPES["simple"],
                pf.HOLE_STANDARDS["iso"],
                fastener,
                size,
                end,
                diameter,
                depth,
                -1.0,
                *([-1.0] * 12),
                "",
                False,
                True,
                True,
                True,
                True,
                False,
            )
            return feature is not None

        made = adapter._handle_com_operation("hole_probe", call)
        after = await volume()
        results[label] = {
            "feature": made.data if made.is_success else f"error: {made.error}",
            "volume_change": round(after - before, 1),
        }

    evidence("simple hole through all: which call builds", results)


async def test_create_hole_blind_through_and_off_the_part(scratch: Any) -> None:
    """A blind M6 counterbore and a through M5 tapped hole; a point in the air fails."""
    tools = await _tools(scratch.adapter)
    await _block(tools, "holes")

    blind = await tools["create_hole"](
        {
            "face_point": [-10, 20, 0],
            "hole_type": "counterbore",
            "size": "M6",
            "end_condition": "blind",
            "depth": 12,
        }
    )
    through = await tools["create_hole"](
        {"face_point": [10, 20, 0], "hole_type": "tapped", "size": "M5x0.8"}
    )
    in_air = await tools["create_hole"](
        {"face_point": [0, 60, 0], "hole_type": "simple", "size": "M6"}
    )

    evidence(
        "create_hole",
        {
            "blind_counterbore": blind.get("hole", blind.get("message")),
            "through_tapped": through.get("hole", through.get("message")),
            "in_air": [in_air["status"], in_air["message"]],
        },
    )
    assert blind["status"] == "success", blind
    assert blind["hole"]["volume_change"] < 0
    assert through["status"] == "success", through
    assert in_air["status"] == "error"


_ISO_VIEW = 7  # swStandardViews_e.swIsometricView


def _iso(adapter: Any) -> None:
    """Turn the camera isometric, zoomed to fit.

    Staging for the recording, not a tool call: an agent does not need it.
    Editing a hole's position sketch turns the view normal to the face, so
    the demo turns it back after each hole.
    """
    model = adapter.currentModel
    adapter._attempt(lambda: model.ShowNamedView2("", _ISO_VIEW), default=None)
    adapter._zoom_to_fit(model)


def _brief(made: dict[str, Any], key: str) -> Any:
    """A short caption of a tool's reply: the feature, holes and volume."""
    if made["status"] != "success":
        return made["message"]
    data = made[key]
    brief = {"name": data.get("name"), "volume_change": round(data["volume_change"], 1)}
    if "hole_count" in data:
        brief["hole_count"] = data["hole_count"]
    return brief


async def test_holes_at_several_points(scratch: Any) -> None:
    """Hole Wizard holes on a 100 x 60 x 15 mm plate, placed the way you place
    them by hand: one hole, then a point in its position sketch per other hole.

    Three M6 counterbores in one feature, mirrored about the Right Plane;
    three M6 countersinks; three M6 tapped holes through; a Ø6 hole patterned
    six times round the y axis. Then, on purpose, a point 5 mm above the top
    face: the call is refused, the half-made hole is deleted again, and the
    volume doesn't change.
    """
    adapter = scratch.adapter
    tools = await _tools(adapter)
    assert (await tools["create_part"]({"name": "hole_plate"}))["status"] == "success"
    await _sketch(tools, "Top", {"x1": -50, "y1": -30, "x2": 50, "y2": 30})
    assert (await tools["create_extrusion"]({"depth": 15}))["status"] == "success"
    _iso(adapter)
    before = await _volume(tools)
    note(
        "Prompt",
        "Drill a 100 x 60 x 15 mm plate: M6 counterbores down both ends, "
        "countersinks and tapped holes inside them, a ring of six Ø6 holes in "
        "the middle.",
        seconds=4.0,
    )

    async def holes(label: str, call: dict[str, Any]) -> dict[str, Any]:
        text = f"create_hole({call})"
        starting(label, text)
        made = await tools["create_hole"](call)
        _iso(adapter)
        evidence(label, _brief(made, "hole"), call=text)
        assert made["status"] == "success", made
        return made

    column = [[0, 15, -18], [0, 15, 0], [0, 15, 18]]

    def at(x: float) -> list[list[float]]:
        return [[x, y, z] for _, y, z in column]

    cbore = await holes(
        "three M6 counterbores, one feature",
        {
            "face_point": at(-38)[0],
            "hole_type": "counterbore",
            "size": "M6",
            "end_condition": "blind",
            "depth": 8,
            "positions": at(-38)[1:],
        },
    )
    mirror_call = {
        "features": [cbore["hole"]["name"]],
        "mirror_plane": "Right Plane",
        "mirror_bodies": False,
    }
    starting("mirrored to the other end", f"mirror_feature({mirror_call})")
    mirrored = await tools["mirror_feature"](mirror_call)
    _iso(adapter)
    evidence(
        "mirrored to the other end",
        _brief(mirrored, "mirror"),
        call=f"mirror_feature({mirror_call})",
    )
    assert mirrored["status"] == "success", mirrored
    csk = await holes(
        "three M6 countersinks",
        {
            "face_point": at(-22)[0],
            "hole_type": "countersink",
            "size": "M6",
            "end_condition": "blind",
            "depth": 10,
            "positions": at(-22)[1:],
        },
    )
    tapped = await holes(
        "three M6 tapped holes, through",
        {
            "face_point": at(22)[0],
            "hole_type": "tapped",
            "size": "M6x1.0",
            "positions": at(22)[1:],
        },
    )
    seed = await holes(
        "a Ø6 hole for the ring",
        {
            "face_point": [10, 15, 0],
            "hole_type": "simple",
            "size": "Ø6.0",
            "end_condition": "blind",
            "depth": 10,
        },
    )
    axis = await tools["create_axis"]({"reference": "y"})
    assert axis["status"] == "success", axis
    ring_call = {
        "features": [seed["hole"]["name"]],
        "axis": axis["axis"]["name"],
        "count": 6,
    }
    starting("a ring of six round the y axis", f"pattern_circular({ring_call})")
    ring = await tools["pattern_circular"](ring_call)
    _iso(adapter)
    evidence(
        "a ring of six round the y axis",
        _brief(ring, "pattern"),
        call=f"pattern_circular({ring_call})",
    )
    assert ring["status"] == "success", ring
    middle = await _volume(tools)

    note(
        "Next, on purpose: a point the tool must refuse",
        "One position is 5 mm above the top face. The tool should refuse it, "
        "delete the hole it started, and leave the plate as it is. The error "
        "that follows is the check passing.",
        seconds=5.0,
    )
    off_call = {
        "face_point": [0, 15, 22],
        "hole_type": "counterbore",
        "size": "M6",
        "end_condition": "blind",
        "depth": 8,
        "positions": [[0, 20, -22]],
    }
    starting("expected refusal", f"create_hole({off_call})")
    off_face = await tools["create_hole"](off_call)
    after = await _volume(tools)
    _iso(adapter)
    evidence(
        "Refused, as intended: the half-made hole was deleted again",
        {
            "status": off_face["status"],
            "message": off_face["message"],
            "plate_unchanged": round(after - middle, 1) == 0,
        },
        call=f"create_hole({off_call})",
        hold=5.0,
    )
    evidence(
        "The plate: 18 holes from 4 Hole Wizard features, a mirror and a ring",
        {
            "holes_per_feature": {
                "counterbores": cbore["hole"]["hole_count"],
                "countersinks": csk["hole"]["hole_count"],
                "tapped": tapped["hole"]["hole_count"],
            },
            "volume_mm3": [round(before, 1), round(after, 1)],
        },
        hold=5.0,
    )
    for made in (cbore, csk, tapped):
        assert made["hole"]["hole_count"] == 3
    assert off_face["status"] == "error"
    assert "was removed again" in off_face["message"]
    assert after == pytest.approx(middle)


async def test_pattern_a_row_and_a_grid(scratch: Any) -> None:
    """An M6 simple hole (listed as Ø6.0) repeated 3 times, then 3 x 2.

    The seed sits 15 mm from three edges of the block's top and 5 mm off the
    middle in z, so the 10 mm steps stay on the block whichever way SolidWorks
    reads each edge. Should the grid fail anyway, it is retried with the
    second direction flipped and both answers are shown.
    """
    tools = await _tools(scratch.adapter)
    await _block(tools, "pattern")
    hole = await tools["create_hole"](
        {"face_point": [-10, 20, -5], "hole_type": "simple", "size": "M6"}
    )
    assert hole["status"] == "success", hole
    seed = hole["hole"]["volume_change"]

    row = await tools["pattern_linear"](
        {
            "features": [hole["hole"]["name"]],
            "direction": [0, 20, 20],
            "count": 3,
            "spacing": 10,
        }
    )
    grid_call = {
        "features": [hole["hole"]["name"]],
        "direction": [0, 20, 20],
        "count": 3,
        "spacing": 10,
        "direction2": [20, 20, 0],
        "count2": 2,
        "spacing2": 10,
    }
    grid = await tools["pattern_linear"](grid_call)
    flipped = None
    if grid["status"] != "success":
        flipped = await tools["pattern_linear"]({**grid_call, "reverse2": True})
    nothing = await tools["pattern_linear"](
        {
            "features": ["NoSuchFeature"],
            "direction": [0, 20, 20],
            "count": 3,
            "spacing": 10,
        }
    )

    evidence(
        "pattern_linear (seed hole volume change, then the patterns')",
        {
            "seed": round(seed, 1),
            "row": row.get("pattern", row.get("message")),
            "grid": grid.get("pattern", grid.get("message")),
            "grid_reverse2": (
                None if flipped is None else flipped.get("pattern", flipped["message"])
            ),
            "unknown_feature": [nothing["status"], nothing["message"]],
        },
    )
    assert row["status"] == "success", row
    assert row["pattern"]["volume_change"] == pytest.approx(2 * seed, rel=0.05)
    assert grid["status"] == "success", grid
    assert nothing["status"] == "error"


async def test_shell_an_open_box(scratch: Any) -> None:
    """2 mm walls, the top face removed: 32000 -> 8672 mm³."""
    tools = await _tools(scratch.adapter)
    await _block(tools, "shell")

    shell = await tools["create_shell"]({"thickness": 2, "faces": [_TOP]})

    evidence("create_shell", shell.get("shell", shell.get("message")))
    assert shell["status"] == "success", shell
    assert shell["shell"]["volume_after"] == pytest.approx(
        _BLOCK - 36 * 36 * 18, rel=0.01
    )


async def test_draft_two_side_walls(scratch: Any) -> None:
    """The x = +-20 walls drafted 3 degrees about the bottom face."""
    tools = await _tools(scratch.adapter)
    await _block(tools, "draft")

    draft = await tools["add_draft"](
        {
            "angle": 3,
            "faces": [[20, 10, 0], [-20, 10, 0]],
            "neutral_face": [0, 0, 5],
        }
    )

    evidence("add_draft", draft.get("draft", draft.get("message")))
    assert draft["status"] == "success", draft
    # Each wall loses (or gains) a wedge of 0.5 * 20 * 20 * tan(3 deg) * 40.
    wedge = 0.5 * 20 * 20 * 0.0524 * 40
    assert abs(draft["draft"]["volume_change"]) == pytest.approx(2 * wedge, rel=0.1)


async def test_rib_across_an_open_box(scratch: Any) -> None:
    """A 2 mm rib from a line across the shelled box, at half height."""
    tools = await _tools(scratch.adapter)
    await _block(tools, "rib")
    shell = await tools["create_shell"]({"thickness": 2, "faces": [_TOP]})
    assert shell["status"] == "success", shell

    made = await tools["create_sketch"]({"plane": "Front"})
    assert made["status"] == "success", made
    line = await tools["add_line"]({"x1": -18, "y1": 10, "x2": 18, "y2": 10})
    assert line["status"] == "success", line
    closed = await tools["exit_sketch"]()
    sketch = str(closed.get("sketch", made["sketch"])["name"])

    rib = await tools["create_rib"]({"sketch": sketch, "thickness": 2})
    missing = await tools["create_rib"]({"sketch": "NoSuchSketch", "thickness": 2})

    evidence(
        "create_rib",
        {
            "rib": rib.get("rib", rib.get("message")),
            "unknown_sketch": [missing["status"], missing["message"]],
        },
    )
    assert rib["status"] == "success", rib
    assert rib["rib"]["volume_change"] > 0
    assert missing["status"] == "error"


async def test_cosmetic_thread_on_a_shaft(scratch: Any) -> None:
    """An M10 thread on a 10 mm shaft: a feature, and the volume unchanged."""
    tools = await _tools(scratch.adapter)
    await _block(tools, "thread")
    sketch = await tools["create_sketch"]({"face_point": _TOP})
    assert sketch["status"] == "success", sketch
    circle = await tools["add_circle"]({"center_x": 0, "center_y": 0, "radius": 5})
    assert circle["status"] == "success", circle
    assert (await tools["exit_sketch"]())["status"] == "success"
    shaft = await tools["create_extrusion"]({"depth": 15})
    assert shaft["status"] == "success", shaft

    thread = await tools["add_cosmetic_thread"](
        {"edge_point": [5, 35, 0], "size": "M10x1.5", "depth": 10}
    )
    off_edge = await tools["add_cosmetic_thread"](
        {"edge_point": [0, 80, 0], "size": "M10x1.5", "depth": 10}
    )

    evidence(
        "add_cosmetic_thread",
        {
            "thread": thread.get("thread", thread.get("message")),
            "off_edge": [off_edge["status"], off_edge["message"]],
        },
    )
    assert thread["status"] == "success", thread
    assert thread["thread"]["volume_change"] == pytest.approx(0, abs=0.01)
    assert off_edge["status"] == "error"


async def test_convert_the_top_face_and_cut(scratch: Any) -> None:
    """The top face's outline copied into a sketch on it, cut 2 mm: -3200 mm³."""
    tools = await _tools(scratch.adapter)
    await _block(tools, "convert")
    made = await tools["create_sketch"]({"face_point": _TOP})
    assert made["status"] == "success", made

    converted = await tools["sketch_convert_entities"]({"face_point": _TOP})
    closed = await tools["exit_sketch"]()
    sketch = str(closed.get("sketch", made["sketch"])["name"])
    before = await _volume(tools)
    cut = await tools["create_cut_extrude"]({"sketch_name": sketch, "depth": 2})
    after = await _volume(tools)

    evidence(
        "sketch_convert_entities then a 2 mm cut",
        {
            "converted": converted.get("converted", converted.get("message")),
            "volume_change": round(after - before, 1),
        },
    )
    assert converted["status"] == "success", converted
    assert converted["converted"]["count"] == 4
    assert cut["status"] == "success", cut
    assert after - before == pytest.approx(-3200, rel=0.01)
