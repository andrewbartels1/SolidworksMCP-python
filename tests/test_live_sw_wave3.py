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
        """Close every scratch document opened here, and delete any files written."""
        for d in self._open_docs():
            title = self.adapter._attempt(
                lambda d=d: self.adapter._get_attr_or_call(d, "GetTitle"), default=None
            )
            path = self.adapter._attempt(
                lambda d=d: self.adapter._get_attr_or_call(d, "GetPathName"),
                default=None,
            )
            if not title or str(title) in self._baseline or path:
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


@pytest.mark.asyncio
async def test_create_reference_point_along_curve(scratch):
    """A point half-way along a real edge adds a feature to the tree."""
    from solidworks_mcp.adapters import sw_type_info

    adapter = scratch.adapter
    await _box_part(adapter)

    # Pick a real edge and a point on it, so the coordinate pick can resolve.
    part = sw_type_info.flagged(adapter.currentModel, "IPartDoc")
    bodies = part.GetBodies2(0, False)
    body = sw_type_info.flagged(
        bodies[0] if isinstance(bodies, (list, tuple)) else bodies, "IBody2"
    )
    edges = body.GetEdges()
    edge = sw_type_info.flagged(
        edges[0] if isinstance(edges, (list, tuple)) else edges, "IEdge"
    )
    # IEdge.GetCurveParams3 -> (startPt[3], endPt[3], ...) in metres.
    params = edge.GetCurveParams3()
    sx, sy, sz = params[0][0], params[0][1], params[0][2]
    ex, ey, ez = params[1][0], params[1][1], params[1][2]
    mid_mm = (
        (sx + ex) / 2 * 1000.0,
        (sy + ey) / 2 * 1000.0,
        (sz + ez) / 2 * 1000.0,
    )

    before = (await adapter.list_features()).data or []
    result = await adapter.create_reference_point(
        "along_curve", mid_mm[0], mid_mm[1], mid_mm[2], percent=50.0
    )
    assert result.is_success, result.error
    assert result.data["features_after"] > result.data["features_before"]
    after = (await adapter.list_features()).data or []
    assert len(after) > len(before)


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


@pytest.mark.asyncio
async def test_auto_center_marks_runs_on_a_view(scratch, tmp_path):
    """Auto-insert runs on a real view and reports a non-negative delta."""
    from solidworks_mcp.adapters.base import ExtrusionParameters

    adapter = scratch.adapter

    # A part with a through hole, saved so a drawing can reference it.
    assert (await adapter.create_part()).is_success
    assert (await adapter.create_sketch("Front")).is_success
    assert (await adapter.add_rectangle(0.0, 0.0, 60.0, 40.0)).is_success
    assert (await adapter.exit_sketch()).is_success
    assert (
        await adapter.create_extrusion(ExtrusionParameters(depth=10.0))
    ).is_success
    assert (await adapter.create_sketch("Front")).is_success
    assert (await adapter.add_circle(30.0, 20.0, 4.0)).is_success
    assert (await adapter.exit_sketch()).is_success
    cut = await adapter.create_cut_extrude(
        ExtrusionParameters(depth=10.0, end_condition="ThroughAll")
    )
    assert cut.is_success, cut.error

    part_path = tmp_path / "plate.sldprt"
    scratch.written_files.append(str(part_path))
    assert (await adapter.save_file(str(part_path))).is_success

    drawing = await adapter.create_technical_drawing({"model_path": str(part_path)})
    assert drawing.is_success, drawing.error

    views = (await adapter.list_drawing_views()).data or []
    assert views, "no drawing views were created"

    result = await adapter.auto_center_marks(views[0], mark_holes=True)
    assert result.is_success, result.error
    assert result.data["center_marks_after"] >= result.data["center_marks_before"]
    assert result.data["center_marks_added"] >= 0


@pytest.mark.asyncio
async def test_auto_center_marks_unknown_view_is_an_error(scratch, tmp_path):
    """An unknown view name errors and lists the views that exist."""
    from solidworks_mcp.adapters.base import ExtrusionParameters

    adapter = scratch.adapter
    assert (await adapter.create_part()).is_success
    assert (await adapter.create_sketch("Front")).is_success
    assert (await adapter.add_rectangle(0.0, 0.0, 30.0, 20.0)).is_success
    assert (await adapter.exit_sketch()).is_success
    assert (
        await adapter.create_extrusion(ExtrusionParameters(depth=5.0))
    ).is_success
    part_path = tmp_path / "b.sldprt"
    scratch.written_files.append(str(part_path))
    assert (await adapter.save_file(str(part_path))).is_success
    assert (
        await adapter.create_technical_drawing({"model_path": str(part_path)})
    ).is_success

    result = await adapter.auto_center_marks("Definitely Not A View")
    assert not result.is_success
    assert "No view named" in (result.error or "")
