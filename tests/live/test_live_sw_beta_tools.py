"""The beta tools' fixes (``beta-tool-faults``), each checked on real SolidWorks.

Every test calls the tools as an agent would, through the MCP tool functions
with plain dicts, and prints its proof as ``[evidence]`` lines. They run in
five batches, one test per process, each with the maintainer's permission:

1. sketch and feature inputs: ``create_extrusion`` and ``create_revolve``
   with ``sketch_name`` and ``axis_entity``, ``create_sketch`` naming its
   sketch, ``create_part`` with a material;
2. ``pattern_circular`` and ``mirror_feature`` on cuts, ``delete_feature``
   naming the dependents it removed;
3. ``calculate_mass_properties`` in kg·mm², ``check_interference`` and
   hidden components, ``get_material``'s density;
4. ``save_as`` and ``overwrite``, ``save_file``, the five ``export_*`` tools,
   ``execute_macro`` repeating;
5. ``create_assembly``, ``create_drawing``, ``create_technical_drawing``,
   ``add_drawing_view`` and ``sketch_tutorial_simple_hole``.

Run one with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_beta_tools.py::test_extrude_an_earlier_sketch_by_name

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows (see
``tests/live/conftest.py``).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from tests.live.evidence import evidence
from tests.live.test_live_sw_ujoint_tool_gaps import _plate_and_pin, _plate_then_pin

pytestmark = pytest.mark.asyncio


async def _tools(adapter: Any) -> dict[str, Any]:
    """Every tool family these tests need, registered on ``adapter``; name -> fn."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools.analysis import register_analysis_tools
    from solidworks_mcp.tools.drawing import register_drawing_tools
    from solidworks_mcp.tools.engineering_data import register_engineering_data_tools
    from solidworks_mcp.tools.export import register_export_tools
    from solidworks_mcp.tools.file_management import register_file_management_tools
    from solidworks_mcp.tools.macro_recording import register_macro_recording_tools
    from solidworks_mcp.tools.modeling import register_modeling_tools
    from solidworks_mcp.tools.sketching import register_sketching_tools

    mcp = FastMCP("beta-tools-live")
    for register in (
        register_modeling_tools,
        register_sketching_tools,
        register_analysis_tools,
        register_drawing_tools,
        register_engineering_data_tools,
        register_export_tools,
        register_file_management_tools,
        register_macro_recording_tools,
    ):
        await register(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


async def _volume(adapter: Any) -> float:
    result = await adapter.get_mass_properties()
    assert result.is_success, result.error
    return float(result.data.volume)


async def _feature_names(adapter: Any) -> list[str]:
    result = await adapter.list_features(include_suppressed=True)
    assert result.is_success, result.error
    return [str(f.get("name")) for f in result.data]


async def _sketch(
    tools: dict[str, Any], plane: str, draw: dict[str, Any], name: str | None = None
) -> str:
    """A closed sketch with one rectangle or circle; its tree name.

    A ``name`` is given when ``exit_sketch`` closes the sketch, so that reply
    holds the final name.
    """
    args: dict[str, Any] = {"plane": plane}
    if name:
        args["sketch_name"] = name
    made = await tools["create_sketch"](args)
    assert made["status"] == "success", made
    shape = "add_circle" if "radius" in draw else "add_rectangle"
    assert (await tools[shape](draw))["status"] == "success"
    closed = await tools["exit_sketch"]()
    assert closed["status"] == "success", closed
    return str(closed.get("sketch", made["sketch"])["name"])


async def _plate(tools: dict[str, Any], adapter: Any) -> None:
    """A 100 x 100 x 10 mm plate on the Top Plane, centred on the origin."""
    assert (await tools["create_part"]({"name": "plate"}))["status"] == "success"
    await _sketch(tools, "Top", {"x1": -50, "y1": -50, "x2": 50, "y2": 50})
    boss = await tools["create_extrusion"]({"depth": 10.0})
    assert boss["status"] == "success", boss


async def _hole(tools: dict[str, Any], x: float, radius: float = 3.0) -> str:
    """A through hole at (x, 0) on the Top Plane; the cut's name."""
    sketch = await _sketch(
        tools, "Top", {"center_x": x, "center_y": 0, "radius": radius}
    )
    cut = await tools["create_cut_extrude"](
        {"sketch_name": sketch, "depth": 10.0, "end_condition": "ThroughAll"}
    )
    assert cut["status"] == "success", cut
    return str(cut["cut_extrude"]["name"])


# ---- batch 1: sketch and feature inputs ----------------------------------------


async def test_extrude_an_earlier_sketch_by_name(scratch) -> None:
    """Two closed sketches; the named earlier one is extruded, a missing name fails."""
    tools = await _tools(scratch.adapter)
    assert (await tools["create_part"]({"name": "two_sketches"}))["status"] == "success"
    square = await _sketch(tools, "Front", {"x1": 0, "y1": 0, "x2": 20, "y2": 20})
    await _sketch(tools, "Top", {"center_x": 60, "center_y": 0, "radius": 5})

    missing = await tools["create_extrusion"]({"sketch_name": "Sketch9", "depth": 5.0})
    used = await tools["create_extrusion"]({"sketch_name": square, "depth": 5.0})
    volume = await _volume(scratch.adapter)
    evidence(
        "extrude the earlier 20 mm square by name (expect 2,000 mm³)",
        {
            "missing": missing.get("message"),
            "sketch_used": used.get("extrusion", {}).get("sketch"),
            "volume_mm3": round(volume, 2),
        },
        call=f'create_extrusion({{"sketch_name": "{square}", "depth": 5}})',
    )
    assert missing["status"] == "error" and square in missing["message"]
    assert used["status"] == "success", used
    assert used["extrusion"]["sketch"] == square
    assert volume == pytest.approx(2000.0, rel=1e-4)


async def test_revolve_about_a_named_axis(scratch) -> None:
    """A 10 x 20 mm rectangle 5 mm off Axis1, no centreline: a tube."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    assert (await tools["create_part"]({"name": "tube"}))["status"] == "success"
    profile = await _sketch(tools, "Front", {"x1": 5, "y1": 0, "x2": 15, "y2": 20})
    axis = (await adapter.create_axis("y")).data["name"]

    revolve = await tools["create_revolve"](
        {"sketch_name": profile, "axis_entity": axis, "angle": 360}
    )
    volume = await _volume(adapter)
    expected = math.pi * (15**2 - 5**2) * 20
    evidence(
        f"revolve about {axis} (expect π·(15² − 5²)·20 = {expected:,.1f} mm³)",
        {"revolve": revolve.get("revolve"), "volume_mm3": round(volume, 1)},
        call=f'create_revolve({{"sketch_name": "{profile}", "axis_entity": "{axis}", "angle": 360}})',
    )
    assert revolve["status"] == "success", revolve
    assert revolve["revolve"]["axis_entity"] == axis
    assert volume == pytest.approx(expected, rel=1e-3)


async def test_a_named_sketch_is_used_by_a_cut(scratch) -> None:
    """exit_sketch gives the name create_sketch was asked for; a cut finds it."""
    tools = await _tools(scratch.adapter)
    await _plate(tools, scratch.adapter)
    before = await _volume(scratch.adapter)
    named = await _sketch(
        tools, "Top", {"center_x": 0, "center_y": 0, "radius": 5}, name="HoleProfile"
    )
    # The same name again: the second sketch keeps SolidWorks' name.
    await tools["create_sketch"]({"plane": "Top", "sketch_name": "HoleProfile"})
    circle = {"center_x": 30, "center_y": 0, "radius": 2}
    assert (await tools["add_circle"](circle))["status"] == "success"
    taken = await tools["exit_sketch"]()

    cut = await tools["create_cut_extrude"](
        {"sketch_name": "HoleProfile", "depth": 10.0, "end_condition": "ThroughAll"}
    )
    removed = before - await _volume(scratch.adapter)
    evidence(
        "a sketch named HoleProfile, then cut by that name (expect π·5²·10 = 785.4 mm³)",
        {
            "named": named,
            "second_request": [taken["sketch"]["name"], taken.get("warning")],
            "removed_mm3": round(removed, 1),
            "tree": await _feature_names(scratch.adapter),
        },
        call='create_sketch({"plane": "Top", "sketch_name": "HoleProfile"})',
    )
    assert named == "HoleProfile"
    assert taken["sketch"]["name"] != "HoleProfile"
    assert "could not be named" in taken["warning"]
    assert cut["status"] == "success", cut
    assert removed == pytest.approx(math.pi * 25 * 10, rel=1e-3)


async def test_a_new_part_gets_its_material(scratch) -> None:
    tools = await _tools(scratch.adapter)

    made = await tools["create_part"]({"name": "steel", "material": "AISI 304"})
    unknown = await tools["create_part"]({"name": "odd", "material": "Unobtainium"})
    evidence(
        "create_part with a material, and with one that doesn't exist",
        {
            "aisi_304": made["part"]["material"],
            "unknown": [unknown["part"]["material"], unknown.get("warning")],
        },
        call='create_part({"name": "steel", "material": "AISI 304"})',
    )
    assert made["part"]["material"] == "AISI 304"
    assert unknown["status"] == "success"
    assert unknown["part"]["material"] is None
    assert "could not be assigned" in unknown["warning"]


# ---- batch 2: patterns, mirror and delete ---------------------------------------


async def test_a_ring_of_six_holes(scratch) -> None:
    """A Ø6 hole patterned 6 times round the y axis: 5 more holes cut."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    await _plate(tools, adapter)
    cut = await _hole(tools, 30.0)
    axis = (await adapter.create_axis("y")).data["name"]

    ring = await tools["pattern_circular"](
        {"features": [cut], "axis": axis, "count": 6}
    )
    expected = -5 * math.pi * 3**2 * 10
    evidence(
        f"a ring of 6 Ø6 holes (expect a change of {expected:,.1f} mm³)",
        {
            "message": ring.get("message"),
            "volume_change": ring.get("pattern", {}).get("volume_change"),
        },
        call=f'pattern_circular({{"features": ["{cut}"], "axis": "{axis}", "count": 6}})',
    )
    assert ring["status"] == "success", ring
    assert ring["pattern"]["volume_change"] == pytest.approx(expected, rel=1e-3)


async def test_a_mirrored_cut(scratch) -> None:
    """A hole at x = 30 mirrored about the Right Plane: a second hole at x = -30."""
    tools = await _tools(scratch.adapter)
    await _plate(tools, scratch.adapter)
    cut = await _hole(tools, 30.0)

    mirrored = await tools["mirror_feature"](
        {"features": [cut], "mirror_plane": "Right Plane", "mirror_bodies": False}
    )
    expected = -math.pi * 3**2 * 10
    evidence(
        f"a mirrored Ø6 hole (expect a change of {expected:,.1f} mm³)",
        {
            "message": mirrored.get("message"),
            "volume_change": mirrored.get("mirror", {}).get("volume_change"),
        },
        call=f'mirror_feature({{"features": ["{cut}"], "mirror_plane": "Right Plane", "mirror_bodies": false}})',
    )
    assert mirrored["status"] == "success", mirrored
    assert mirrored["mirror"]["volume_change"] == pytest.approx(expected, rel=1e-3)


async def test_deleting_a_sketch_names_the_cut_that_went_with_it(scratch) -> None:
    tools = await _tools(scratch.adapter)
    await _plate(tools, scratch.adapter)
    sketch = await _sketch(tools, "Top", {"center_x": 0, "center_y": 0, "radius": 5})
    cut = await tools["create_cut_extrude"](
        {"sketch_name": sketch, "depth": 10.0, "end_condition": "ThroughAll"}
    )
    assert cut["status"] == "success", cut

    deleted = await tools["delete_feature"]({"name": sketch})
    evidence(
        f"delete {sketch}, which the cut was built from",
        {
            "message": deleted.get("message"),
            "removed": deleted.get("data", {}).get("removed_features"),
        },
        call=f'delete_feature({{"name": "{sketch}"}})',
    )
    assert deleted["status"] == "success", deleted
    removed = deleted["data"]["removed_features"]
    assert sketch in removed and len(removed) >= 2
    assert "dependents" in deleted["message"]


# ---- batch 3: measurements ------------------------------------------------------


async def test_block_inertia_in_kg_mm2(scratch) -> None:
    """A 100 x 20 x 50 mm block: the moments match m(b² + c²)/12 per axis."""
    tools = await _tools(scratch.adapter)
    made = await tools["create_part"]({"name": "block", "material": "AISI 1020"})
    assert made["part"]["material"] == "AISI 1020", made
    await _sketch(tools, "Top", {"x1": -50, "y1": -25, "x2": 50, "y2": 25})
    assert (await tools["create_extrusion"]({"depth": 20.0}))["status"] == "success"

    props = (await tools["calculate_mass_properties"]({}))["mass_properties"]
    mass = props["mass"]["value"]
    inertia = props["moments_of_inertia"]
    expected = sorted(
        mass * (b * b + c * c) / 12 for b, c in ((20, 50), (100, 50), (100, 20))
    )
    measured = sorted(inertia[k] for k in ("Ixx", "Iyy", "Izz"))
    evidence(
        "block inertia about its centre (expect m(b²+c²)/12 in kg·mm²)",
        {
            "mass_kg": round(mass, 4),
            "measured": [round(v, 2) for v in measured],
            "expected": [round(v, 2) for v in expected],
            "products": [inertia[k] for k in ("Ixy", "Ixz", "Iyz")],
            "units": inertia["units"],
        },
        call="calculate_mass_properties({})",
    )
    assert inertia["units"] == "kg·mm²"
    assert measured == pytest.approx(expected, rel=1e-3)
    assert all(abs(inertia[k]) < 1e-6 * expected[-1] for k in ("Ixy", "Ixz", "Iyz"))


async def test_a_hidden_component_is_left_out_unless_asked(scratch, tmp_path) -> None:
    """The pin overlaps the plate; hidden, it counts only with include_hidden."""
    from solidworks_mcp.adapters import sw_type_info

    adapter = scratch.adapter
    tools = await _tools(adapter)
    plate, pin = await _plate_and_pin(scratch, tools, tmp_path, "hidden")
    assert (await adapter.create_assembly()).is_success
    assert (await adapter.insert_component(plate, 0.0, 0.0, 0.0)).is_success
    assert (await adapter.insert_component(pin, 0.0, 0.0, 0.0)).is_success
    scratch.written_files.append(str(tmp_path / "hidden.SLDASM"))
    _plate_name, pin_name = await _plate_then_pin(adapter)
    assembly = sw_type_info.flagged(adapter.currentModel, "IAssemblyDoc")
    for component in assembly.GetComponents(True):
        c = sw_type_info.flagged(component, "IComponent2")
        if str(c.Name2) == pin_name:
            c.Visible = 0  # swComponentHidden

    default = await tools["check_interference"]({})
    hidden_too = await tools["check_interference"]({"include_hidden": True})
    evidence(
        "the overlapping pin hidden: checked by default, then with include_hidden",
        {
            "default": default["data"]["interference_count"],
            "include_hidden": hidden_too["data"]["interference_count"],
        },
        call='check_interference({"include_hidden": true})',
    )
    assert default["data"]["interference_count"] == 0
    assert hidden_too["data"]["interference_count"] >= 1


async def test_get_material_reports_the_density(scratch) -> None:
    tools = await _tools(scratch.adapter)
    assert (await tools["create_part"]({"name": "steel", "material": "AISI 304"}))[
        "status"
    ] == "success"
    await _sketch(tools, "Top", {"x1": -10, "y1": -10, "x2": 10, "y2": 10})
    assert (await tools["create_extrusion"]({"depth": 10.0}))["status"] == "success"

    read = await tools["get_material"]({})
    evidence(
        "get_material on an AISI 304 part (expect 8,000 kg/m³)",
        read["data"],
        call="get_material({})",
    )
    assert read["data"]["material"] == "AISI 304"
    assert read["data"]["density_kg_m3"] == pytest.approx(8000.0)


# ---- batch 4: files and macros --------------------------------------------------


async def _saved_block(scratch: Any, tools: dict[str, Any], path: Path) -> None:
    assert (await tools["create_part"]({"name": path.stem}))["status"] == "success"
    await _sketch(tools, "Top", {"x1": -10, "y1": -10, "x2": 10, "y2": 10})
    assert (await tools["create_extrusion"]({"depth": 10.0}))["status"] == "success"
    saved = await tools["save_file"]({"file_path": str(path)})
    scratch.written_files.append(str(path))
    assert saved["status"] == "success", saved


async def test_save_as_keeps_an_existing_file(scratch, tmp_path) -> None:
    tools = await _tools(scratch.adapter)
    first = tmp_path / "keep.SLDPRT"
    await _saved_block(scratch, tools, first)
    copy = tmp_path / "copy.SLDPRT"
    scratch.written_files.append(str(copy))
    assert (await tools["save_as"]({"file_path": str(copy)}))["status"] == "success"
    stamp = (copy.stat().st_size, copy.stat().st_mtime_ns)

    kept = await tools["save_as"]({"file_path": str(copy)})
    untouched = (copy.stat().st_size, copy.stat().st_mtime_ns) == stamp
    replaced = await tools["save_as"]({"file_path": str(copy), "overwrite": True})
    force = await tools["save_file"]({"force_save": True})
    evidence(
        "save_as onto an existing file, without and with overwrite",
        {
            "without": kept.get("message"),
            "file_untouched": untouched,
            "with": replaced.get("status"),
            "force_save": force.get("message"),
        },
        call=f'save_as({{"file_path": "{copy.name}"}})',
    )
    assert kept["error_type"] == "invalid_input"
    assert stamp[0] > 0 and kept["status"] == "error" and untouched
    assert replaced["status"] == "success", replaced
    assert force["error_type"] == "invalid_input"


async def test_every_export_writes_its_file(scratch, tmp_path) -> None:
    """STEP, IGES and STL from the part; PDF and DWG from its drawing."""
    tools = await _tools(scratch.adapter)
    part = tmp_path / "export.SLDPRT"
    await _saved_block(scratch, tools, part)
    sizes: dict[str, int] = {}
    # Each tool named in full, so the support-level check finds it.
    for tool, ext in (
        ("export_step", "step"),
        ("export_iges", "igs"),
        ("export_stl", "stl"),
    ):
        target = tmp_path / f"export.{ext}"
        scratch.written_files.append(str(target))
        done = await tools[tool]({"file_path": str(target)})
        assert done["status"] == "success", done
        sizes[ext] = target.stat().st_size
    assert (await tools["create_drawing"]({"name": "export_drawing"}))[
        "status"
    ] == "success"
    views = await tools["create_technical_drawing"]({"model_file": str(part)})
    assert views["status"] == "success", views
    for tool, ext in (("export_pdf", "pdf"), ("export_dwg", "dwg")):
        target = tmp_path / f"export.{ext}"
        scratch.written_files.append(str(target))
        done = await tools[tool]({"file_path": str(target)})
        assert done["status"] == "success", done
        sizes[ext] = target.stat().st_size
    refused = await tools["export_step"](
        {"file_path": str(tmp_path / "x.step"), "options": {"a": 1}}
    )
    evidence(
        "every export's file size in bytes",
        {**sizes, "options": refused.get("message")},
        call="export_step/iges/stl/pdf/dwg",
    )
    assert all(size > 0 for size in sizes.values())
    assert refused["error_type"] == "invalid_input"


_MACRO = """Dim swApp As Object
Dim Part As Object
Sub main()
    Set swApp = Application.SldWorks
    Set Part = swApp.ActiveDoc
    Part.ClearSelection2 True
    Part.Extension.SelectByID2 "Front Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0
    Part.SketchManager.InsertSketch True
    Part.SketchManager.CreatePoint 0, 0, 0
    Part.SketchManager.InsertSketch True
End Sub
"""


async def test_a_macro_runs_three_times(scratch, tmp_path) -> None:
    """Each run adds one sketch, so three runs add three."""
    tools = await _tools(scratch.adapter)
    assert (await tools["create_part"]({"name": "macro"}))["status"] == "success"
    macro = tmp_path / "add_sketch.swb"
    macro.write_text(_MACRO, encoding="ascii")
    before = await _feature_names(scratch.adapter)

    ran = await tools["execute_macro"](
        {"macro_path": str(macro), "repeat_count": 3, "pause_between_runs": 1}
    )
    added = [n for n in await _feature_names(scratch.adapter) if n not in before]
    evidence(
        "a macro that adds one sketch, run 3 times",
        {
            "message": ran.get("message"),
            "runs_completed": ran.get("runs_completed"),
            "added": added,
        },
        call=f'execute_macro({{"macro_path": "{macro.name}", "repeat_count": 3}})',
    )
    assert ran["status"] == "success", ran
    assert ran["runs_completed"] == 3
    assert len(added) == 3


# ---- batch 5: drawings and the tutorial -----------------------------------------


async def test_new_documents_refuse_removed_inputs(scratch) -> None:
    tools = await _tools(scratch.adapter)

    assembly = await tools["create_assembly"]({"name": "asm"})
    refused_asm = await tools["create_assembly"](
        {"name": "asm2", "components": ["a.sldprt"]}
    )
    drawing = await tools["create_drawing"]({"name": "drw"})
    refused_drw = await tools["create_drawing"](
        {"name": "drw2", "model_path": "a.sldprt"}
    )
    evidence(
        "create_assembly and create_drawing, then each with a removed input",
        {
            "assembly": assembly.get("assembly"),
            "components": refused_asm.get("message"),
            "drawing": drawing.get("drawing"),
            "model_path": refused_drw.get("message"),
        },
        call='create_assembly({"name": "asm", "components": ["a.sldprt"]})',
    )
    assert assembly["status"] == "success" and drawing["status"] == "success"
    assert refused_asm["error_type"] == "invalid_input"
    assert refused_drw["error_type"] == "invalid_input"


async def test_three_views_and_one_more(scratch, tmp_path) -> None:
    """Standard views in first-angle projection, an isometric view, and a refused remove."""
    tools = await _tools(scratch.adapter)
    part = tmp_path / "views.SLDPRT"
    await _saved_block(scratch, tools, part)
    assert (await tools["create_drawing"]({"name": "views"}))["status"] == "success"

    standard = await tools["create_technical_drawing"](
        {"model_file": str(part), "projection": "first_angle"}
    )
    iso = await tools["add_drawing_view"](
        # The sheet's free lower right, clear of the three standard views.
        {"model_file": str(part), "view_type": "isometric", "position": [230, 100]}
    )
    remove = await tools["add_drawing_view"](
        {"operation": "remove", "view_name": "Drawing View1"}
    )
    listed = await tools["list_drawing_views"]()
    evidence(
        "three standard views (first angle), one isometric view, a refused remove",
        {
            "standard": standard.get("data", {}).get("views"),
            "projection": standard.get("data", {}).get("projection"),
            "iso": iso.get("status"),
            "remove": remove.get("message"),
            "count": listed.get("count"),
        },
        call='create_technical_drawing({"model_file": "views.SLDPRT", "projection": "first_angle"})',
    )
    assert standard["status"] == "success", standard
    assert len(standard["data"]["views"]) == 3
    assert iso["status"] == "success", iso
    assert remove["error_type"] == "invalid_input"
    assert listed["count"] == 4


async def test_the_hole_tutorial_runs_as_written(scratch) -> None:
    """Its sketch, then its suggested cut, makes a Ø5 hole in a plate."""
    tools = await _tools(scratch.adapter)
    await _plate(tools, scratch.adapter)
    before = await _volume(scratch.adapter)

    tutorial = await tools["sketch_tutorial_simple_hole"]()
    cut = await tools["create_cut_extrude"](tutorial["suggested_cut"])
    removed = before - await _volume(scratch.adapter)
    expected = math.pi * 2.5**2 * 10
    evidence(
        f"the tutorial's sketch and suggested cut (expect π·2.5²·10 = {expected:.1f} mm³)",
        {
            "next_step": tutorial["next_step"],
            "suggested_cut": tutorial["suggested_cut"],
            "removed_mm3": round(removed, 1),
        },
        call="sketch_tutorial_simple_hole(), then create_cut_extrude(suggested_cut)",
    )
    assert cut["status"] == "success", cut
    assert removed == pytest.approx(expected, rel=1e-3)
