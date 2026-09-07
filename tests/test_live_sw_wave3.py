"""Real-SolidWorks regression tests for the Wave 3 tool additions.

Covers ``create_reference_point`` (#58), ``auto_center_marks`` (#63) and
``save_body_as_part`` (#62).

Gating matches ``tests/test_live_sw_regression.py``:
  - ``@pytest.mark.solidworks_only`` / ``@pytest.mark.windows_only``
  - skipped unless ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1``

Cleanup closes only never-saved scratch documents (and deletes any file a
test wrote), so the suite is safe to run against a session with real work
open.
"""

from __future__ import annotations

import os
import platform
from collections.abc import AsyncIterator

import pytest

_REAL_FLAG = "SOLIDWORKS_MCP_RUN_REAL_INTEGRATION"
_REAL_ENABLED = os.getenv(_REAL_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}

pytestmark = [
    pytest.mark.solidworks_only,
    pytest.mark.windows_only,
    pytest.mark.skipif(
        not _REAL_ENABLED,
        reason=f"set {_REAL_FLAG}=1 to run tests that require a live SolidWorks install",
    ),
    pytest.mark.skipif(
        platform.system() != "Windows",
        reason="SolidWorks only runs on Windows",
    ),
]


class _ScratchSession:
    """A connected adapter plus cleanup of only the scratch docs a test made."""

    def __init__(self, adapter) -> None:  # noqa: ANN001
        """Snapshot the currently open documents as the do-not-close baseline.

        Args:
            adapter: A connected ``PyWin32Adapter``.
        """
        self.adapter = adapter
        self._baseline: set[str] = self._open_titles()
        self.written_files: list[str] = []

    def _open_docs(self) -> list:
        """Return the currently open ``IModelDoc2`` dispatches (never ``None``)."""
        raw = self.adapter._attempt(
            lambda: self.adapter.swApp.GetDocuments(), default=None
        )
        if isinstance(raw, (list, tuple)):
            return [d for d in raw if d is not None]
        return [raw] if raw else []

    def _open_titles(self) -> set[str]:
        """Return the window titles of every currently open document."""
        titles: set[str] = set()
        for d in self._open_docs():
            t = self.adapter._attempt(
                lambda d=d: self.adapter._get_attr_or_call(d, "GetTitle"), default=None
            )
            if t:
                titles.add(str(t))
        return titles

    def cleanup(self) -> None:
        """Close every scratch document opened here, and delete any files written.

        A document is closed when it is new since the baseline snapshot and
        either was never saved *or* was saved to one of this test's own
        ``written_files`` paths. A real file the user already had open is
        never touched.
        """
        owned = {os.path.normcase(os.path.abspath(f)) for f in self.written_files}
        for d in self._open_docs():
            title = self.adapter._attempt(
                lambda d=d: self.adapter._get_attr_or_call(d, "GetTitle"), default=None
            )
            path = self.adapter._attempt(
                lambda d=d: self.adapter._get_attr_or_call(d, "GetPathName"),
                default=None,
            )
            if not title or str(title) in self._baseline:
                continue
            if path and os.path.normcase(os.path.abspath(str(path))) not in owned:
                continue
            self.adapter._attempt(
                lambda t=str(title): self.adapter.swApp.CloseDoc(t)
            )
        for f in self.written_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except OSError:
                pass


@pytest.fixture
async def scratch() -> AsyncIterator[_ScratchSession]:
    """Yield a connected adapter; on teardown close only its scratch docs/files."""
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    adapter = PyWin32Adapter({})
    await adapter.connect()
    session = _ScratchSession(adapter)
    try:
        yield session
    finally:
        session.cleanup()
        await adapter.disconnect()


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

    result = await adapter.save_body_as_part(
        "NoSuchBody", str(tmp_path / "x.sldprt")
    )
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
    result = await adapter.create_reference_point(
        "along_curve", *mid_mm, percent=50.0
    )
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
    assert (
        await adapter.create_extrusion(ExtrusionParameters(depth=10.0))
    ).is_success

    part_path = tmp_path / "plate.sldprt"
    assert (await adapter.save_file(str(part_path))).is_success

    assert (await adapter.create_drawing()).is_success
    drawing = await adapter.create_technical_drawing(
        {"model_file": str(part_path)}
    )
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
