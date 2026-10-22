"""Real-SolidWorks regression tests for the Wave 3 tool additions.

Covers ``create_reference_point`` (#58), ``auto_center_marks`` (#63) and
``save_body_as_part`` (#62).

Gating, the ``scratch`` fixture and scratch-doc cleanup are shared from
``tests/live/conftest.py`` (not collected unless
``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows).

Cleanup closes only never-saved scratch documents (and deletes any file a
test wrote), so the suite is safe to run against a session with real work
open.
"""

from __future__ import annotations

import os

import pytest

from tests.live.evidence import evidence


async def _box_part(adapter) -> None:  # noqa: ANN001
    """Create a scratch part with a single 40x25x10 mm boss."""
    from solidworks_mcp.adapters.base import ExtrusionParameters

    assert (await adapter.create_part()).is_success
    assert (await adapter.create_sketch("Front")).is_success
    assert (await adapter.add_rectangle(0.0, 0.0, 40.0, 25.0)).is_success
    assert (await adapter.exit_sketch()).is_success
    assert (await adapter.create_extrusion(ExtrusionParameters(depth=10.0))).is_success


# ---- save_body_as_part (#62) -----------------------------------------


@pytest.mark.asyncio
async def test_save_body_as_part_writes_the_body_file(scratch, tmp_path):
    """The named solid body is written to a standalone part file."""
    from solidworks_mcp.adapters import sw_type_info

    adapter = scratch.adapter
    await _box_part(adapter)

    part = sw_type_info.flagged(adapter.currentModel, "IPartDoc")
    bodies = part.GetBodies2(0, False)
    first = bodies[0] if isinstance(bodies, (list, tuple)) else bodies
    body_name = str(sw_type_info.flagged(first, "IBody2").Name)

    target = tmp_path / "extracted_body.sldprt"
    scratch.written_files.append(str(target))

    result = await adapter.save_body_as_part(body_name, str(target))
    assert result.is_success, result.error
    assert result.data["body"] == body_name
    assert body_name in result.data["solid_bodies"]
    assert os.path.exists(target)


@pytest.mark.asyncio
async def test_save_body_as_part_unknown_body_lists_the_real_ones(scratch, tmp_path):
    """An unknown body name errors and names the bodies that do exist."""
    adapter = scratch.adapter
    await _box_part(adapter)

    result = await adapter.save_body_as_part("NoSuchBody", str(tmp_path / "x.sldprt"))
    assert not result.is_success
    assert "NoSuchBody" in (result.error or "")


@pytest.mark.asyncio
async def test_save_body_as_part_requires_a_part(scratch, tmp_path):
    """Called on a drawing, it refuses before touching anything."""
    adapter = scratch.adapter
    assert (await adapter.create_drawing()).is_success

    result = await adapter.save_body_as_part("B1", str(tmp_path / "x.sldprt"))
    assert not result.is_success
    assert "part document" in (result.error or "")


# ---- create_reference_point (#58) ----------------------------------


def _linear_edge_pick_mm(adapter, model) -> tuple[float, float, float]:
    """Return the midpoint (mm) of a straight box edge that a coordinate pick resolves.

    ``IEdge::GetStartVertex/GetEndVertex`` -> ``IVertex::GetPoint`` gives a
    clean 3-array in metres (far more reliable through pywin32 than
    ``GetCurveParams*``).

    ``SelectByID2`` silently fails when the pick coordinate lies on the
    ``x=0`` or ``z=0`` origin planes - it resolves the *reference plane*
    instead of the edge (measured on SW 2026). So edges whose midpoint sits
    on either plane are skipped; the first one clear of both is returned.
    """
    from solidworks_mcp.adapters import sw_type_info

    part = sw_type_info.flagged(model, "IPartDoc")
    bodies = part.GetBodies2(0, False)
    body = sw_type_info.flagged(
        bodies[0] if isinstance(bodies, (list, tuple)) else bodies, "IBody2"
    )

    edges = body.GetEdges()
    for raw in edges if isinstance(edges, (list, tuple)) else [edges]:
        edge = sw_type_info.flagged(raw, "IEdge")
        sv = adapter._attempt(lambda e=edge: e.GetStartVertex(), default=None)
        ev = adapter._attempt(lambda e=edge: e.GetEndVertex(), default=None)
        if sv is None or ev is None:
            continue
        p1 = sw_type_info.flagged(sv, "IVertex").GetPoint()
        p2 = sw_type_info.flagged(ev, "IVertex").GetPoint()
        if tuple(round(c, 9) for c in p1) == tuple(round(c, 9) for c in p2):
            continue
        mid = tuple((p1[i] + p2[i]) / 2 for i in range(3))
        if abs(mid[0]) < 1e-4 or abs(mid[2]) < 1e-4:  # on an origin plane
            continue
        return tuple(c * 1000.0 for c in mid)
    raise AssertionError("no straight edge clear of the origin planes on the box")


@pytest.mark.asyncio
async def test_create_reference_point_along_curve(scratch):
    """A point half-way along a real box edge adds a feature to the tree."""
    adapter = scratch.adapter
    await _box_part(adapter)

    mid_mm = _linear_edge_pick_mm(adapter, adapter.currentModel)

    before = (await adapter.list_features()).data or []
    result = await adapter.create_reference_point("along_curve", *mid_mm, percent=50.0)
    assert result.is_success, f"{result.error} (tried {mid_mm} mm)"
    assert result.data["features_after"] > result.data["features_before"]
    after = (await adapter.list_features()).data or []
    assert len(after) > len(before)


@pytest.mark.asyncio
async def test_create_reference_point_face_center(scratch):
    """A point at a box face centre adds a feature to the tree."""
    from solidworks_mcp.adapters import sw_type_info

    adapter = scratch.adapter
    await _box_part(adapter)

    part = sw_type_info.flagged(adapter.currentModel, "IPartDoc")
    bodies = part.GetBodies2(0, False)
    body = sw_type_info.flagged(
        bodies[0] if isinstance(bodies, (list, tuple)) else bodies, "IBody2"
    )
    box = [float(v) for v in body.GetBodyBox()]  # metres
    face_center_mm = (
        (box[0] + box[3]) / 2 * 1000.0,
        (box[1] + box[4]) / 2 * 1000.0,
        box[5] * 1000.0,  # the +Z face
    )

    result = await adapter.create_reference_point("face_center", *face_center_mm)
    assert result.is_success, f"{result.error} (tried {face_center_mm} mm)"
    assert result.data["features_after"] > result.data["features_before"]


@pytest.mark.asyncio
async def test_create_reference_point_validation(scratch):
    """Bad mode / parameter combinations are refused before any COM work."""
    adapter = scratch.adapter
    await _box_part(adapter)

    bad_mode = await adapter.create_reference_point("spiral", 0, 0, 0)
    assert not bad_mode.is_success
    assert "Unknown mode" in (bad_mode.error or "")

    both = await adapter.create_reference_point(
        "along_curve", 0, 0, 0, distance=5.0, percent=50.0
    )
    assert not both.is_success
    assert "exactly one" in (both.error or "")


# ---- auto_center_marks (#63) --------------------------------------


async def _plate_with_hole_drawing(adapter, tmp_path) -> str:
    """Create a plate with a through hole, save it, and lay out a drawing.

    Args:
        adapter: A connected ``PyWin32Adapter``.
        tmp_path: pytest ``tmp_path`` for the scratch ``.sldprt``.

    Returns:
        tuple[str, str]: The saved part path and the first drawing-view name.
    """
    from solidworks_mcp.adapters.base import ExtrusionParameters

    assert (await adapter.create_part()).is_success
    # Rectangle with an inner circle in one profile -> the extrude leaves a
    # through hole, without needing create_cut_extrude (broken here).
    assert (await adapter.create_sketch("Front")).is_success
    assert (await adapter.add_rectangle(0.0, 0.0, 60.0, 40.0)).is_success
    assert (await adapter.add_circle(30.0, 20.0, 4.0)).is_success
    assert (await adapter.exit_sketch()).is_success
    assert (await adapter.create_extrusion(ExtrusionParameters(depth=10.0))).is_success

    part_path = tmp_path / "plate.sldprt"
    assert (await adapter.save_file(str(part_path))).is_success

    assert (await adapter.create_drawing()).is_success
    drawing = await adapter.create_technical_drawing({"model_file": str(part_path)})
    assert drawing.is_success, drawing.error

    views = (await adapter.list_drawing_views()).data or []
    assert views, "no drawing views were created"
    return str(part_path), views[0]


@pytest.mark.asyncio
async def test_auto_center_marks_runs_on_a_view(scratch, tmp_path):
    """Auto-insert runs on a real view and reports a non-negative delta."""
    adapter = scratch.adapter
    part_path, view = await _plate_with_hole_drawing(adapter, tmp_path)
    scratch.written_files.append(part_path)

    result = await adapter.auto_center_marks(view, mark_holes=True)
    assert result.is_success, result.error
    assert result.data["center_marks_after"] >= result.data["center_marks_before"]
    assert result.data["center_marks_added"] >= 0


@pytest.mark.asyncio
async def test_auto_center_marks_unknown_view_is_an_error(scratch, tmp_path):
    """An unknown view name errors and lists the views that exist."""
    adapter = scratch.adapter
    part_path, _view = await _plate_with_hole_drawing(adapter, tmp_path)
    scratch.written_files.append(part_path)

    result = await adapter.auto_center_marks("Definitely Not A View")
    assert not result.is_success
    assert "No view named" in (result.error or "")


# ---- create_drawing without a template ------------------------------


@pytest.mark.asyncio
async def test_create_drawing_without_a_template_live(scratch, tmp_path, monkeypatch):
    """No usable drawing template (as after a settings reset): create_drawing
    falls back to a blank A-size drawing, and views can still be placed."""
    adapter = scratch.adapter
    await _box_part(adapter)
    part_path = tmp_path / "box.sldprt"
    assert (await adapter.save_file(str(part_path))).is_success
    evidence("box part saved", part_path.name)

    monkeypatch.setattr(adapter, "_resolve_template_path", lambda *a, **kw: None)
    created = await adapter.create_drawing()
    assert created.is_success, created.error
    model = adapter.currentModel
    active = adapter.swApp.ActiveDoc
    window = {
        "visible": bool(model.Visible),
        "active_doc": str(adapter._get_attr_or_call(active, "GetTitle"))
        if active
        else None,
    }
    evidence("create_drawing without template", created)
    evidence("drawing window", window)
    assert int(model.GetType()) == 3  # swDocDRAWING
    assert window["visible"], "the fallback drawing was created hidden"

    drawing = await adapter.create_technical_drawing({"model_file": str(part_path)})
    adapter._attempt(lambda: model.ViewZoomtofit2())
    views = (await adapter.list_drawing_views()).data or []
    evidence("views on the blank drawing", views)
    assert drawing.is_success, drawing.error
    assert views, "no drawing views were placed on the template-less drawing"


# ---- save_assembly(include_references=True): dead-code ledger item 13 ------


@pytest.mark.asyncio
async def test_save_assembly_with_references_live(scratch, tmp_path):
    """Record which path save_assembly(include_references=True) takes on this
    SolidWorks: the tool's native Pack-and-Go, or the dependency-copy fallback.

    Either way the copy must hold the assembly and its part.
    """
    from fastmcp import FastMCP

    from solidworks_mcp.tools.file_management import register_file_management_tools

    adapter = scratch.adapter
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    part_path = source_dir / "block.sldprt"
    asm_path = source_dir / "holder.sldasm"
    scratch.written_files += [str(part_path), str(asm_path)]

    await _box_part(adapter)
    assert (await adapter.save_file(str(part_path))).is_success
    assert (await adapter.create_assembly()).is_success
    assert (await adapter.insert_component(str(part_path), 0.0, 0.0, 0.0)).is_success
    assert (await adapter.save_file(str(asm_path))).is_success
    evidence("saved assembly", [part_path.name, asm_path.name])

    mcp = FastMCP("item-13-live")
    await register_file_management_tools(mcp, adapter, {})
    save_assembly = {t.name: t.fn for t in await mcp.list_tools()}["save_assembly"]

    target = tmp_path / "copy" / "holder_copy.sldasm"
    target.parent.mkdir()  # save_assembly requires an existing folder
    result = await save_assembly({"file_path": str(target), "include_references": True})
    evidence(
        "save_assembly(include_references=True)",
        {
            "status": result.get("status"),
            "copy_method": result.get("copy_method"),
            "native_pack_and_go_error": result.get("native_pack_and_go_error"),
            "copied": sorted(p.name for p in target.parent.glob("*")),
        },
    )
    assert result["status"] == "success", result
    names = {p.name.lower() for p in target.parent.glob("*")}
    assert "block.sldprt" in names, names
    assert any(n.endswith(".sldasm") for n in names), names

    # Show the copy is self-contained: close and delete the source, then open
    # the copy in SolidWorks and check where its part was loaded from.
    copied = [str(p) for p in target.parent.glob("*")]
    scratch.cleanup()  # closes the source docs and deletes the source files
    scratch.written_files += copied
    assert not part_path.exists() and not asm_path.exists()

    opened = await adapter.open_model(str(target))
    assert opened.is_success, opened.error
    model = adapter.currentModel
    adapter._attempt(lambda: model.ViewZoomtofit2())
    raw = adapter._attempt(lambda: model.GetComponents(False), default=None) or []
    components = raw if isinstance(raw, (list, tuple)) else [raw]
    loaded_from = [
        str(adapter._get_attr_or_call(c, "GetPathName")) for c in components if c
    ]
    evidence(
        "copy opened with the source deleted",
        {"assembly": target.name, "components_loaded_from": loaded_from},
    )
    assert loaded_from, "the copied assembly opened with no components"
    for path in loaded_from:
        assert os.path.normcase(os.path.dirname(path)) == os.path.normcase(
            str(target.parent)
        ), f"component loaded from {path}, not from the copy folder"
        assert os.path.exists(path), path
