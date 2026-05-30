"""Regression tests for the Phase 1+2 COM-safety rewrite.

These tests target specific bugs that were diagnosed and fixed on 2026-04-24:

1. **Cross-thread IDispatch use** — calling a SolidWorks method from a
   different thread than where the COM object was created previously raised
   ``AttributeError: SldWorks.Application.<method>`` (NOT a ``com_error``).
   Fixed by routing all COM work through ``ComExecutor`` (single STA thread).

2. **Method-vs-property mis-resolution** — Python 3.14 + pywin32 311 late
   binding resolved zero-arg SW methods (``GetType``, ``GetTitle``, …) as
   properties, causing ``TypeError: 'int'/'str' object is not callable``.
   Fixed by ``sw_type_info.flag_methods`` using the makepy-generated
   wrapper to identify and flag methods per SW interface.

3. **Dead code in get_model_info** — it called ``GetRebuildStatus()`` and
   ``GetActiveConfiguration().GetName()`` which don't exist in the SW 2025
   type library. Fixed by replacing with ``IsTessellationValid()`` and
   the ``IConfiguration.Name`` property.

These tests are gated:
  - ``@pytest.mark.solidworks_only`` — require SolidWorks installed
  - ``@pytest.mark.windows_only`` — require Windows
  - Skipped entirely unless ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1``

Run only these tests locally on Windows with SW::

    SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1 \
        python -m pytest tests/test_live_sw_regression.py -v
"""

from __future__ import annotations

import asyncio
import os
import platform
import threading

import pytest

# base.py is pure-pydantic (no pywin32), so importing the parameter models at
# module scope is safe on non-Windows CI even though the SW tests are skipped.
from solidworks_mcp.adapters.base import LoftParameters, SweepParameters

# Skip the entire module when the env flag isn't set. This matches the
# pattern used by tests/test_real_solidworks_integration.py and keeps CI
# fast on boxes without SW.
_REAL_FLAG = "SOLIDWORKS_MCP_RUN_REAL_INTEGRATION"
_REAL_ENABLED = os.getenv(_REAL_FLAG, "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

pytestmark = [
    pytest.mark.solidworks_only,
    pytest.mark.windows_only,
    pytest.mark.skipif(
        not _REAL_ENABLED,
        reason=(
            f"set {_REAL_FLAG}=1 to run tests that require a live SolidWorks install"
        ),
    ),
    pytest.mark.skipif(
        platform.system() != "Windows",
        reason="SolidWorks only runs on Windows",
    ),
]


# Tests that need a real .SLDASM file to exercise OpenDoc6 read the path
# from this env var. Set it to any local SolidWorks assembly; tests skip
# cleanly when it's unset or the file isn't present.
_TEST_ASSEMBLY_ENV_VAR = "SOLIDWORKS_MCP_TEST_ASSEMBLY"


def _test_assembly_path() -> str:
    """Return the .SLDASM path used by file-loading regression tests.

    Reads ``SOLIDWORKS_MCP_TEST_ASSEMBLY``. Returns an empty string when
    unset; callers should ``pytest.skip`` in that case.
    """
    return os.environ.get(_TEST_ASSEMBLY_ENV_VAR, "").strip()


# ---- ComExecutor unit tests (don't need SW) ----
# These still run only when _REAL_ENABLED because they pull in pywin32.


def test_com_executor_start_stop_idempotent() -> None:
    """ComExecutor.start() and stop() can be called repeatedly."""
    from solidworks_mcp.adapters.com_executor import ComExecutor

    ex = ComExecutor(name="test-idempotent")
    ex.start()
    ex.start()  # second call is a no-op
    assert ex._thread is not None and ex._thread.is_alive()
    ex.stop()
    ex.stop()  # safe to call again
    assert ex._thread is None


def test_com_executor_propagates_exceptions() -> None:
    """Exceptions raised inside a submitted callable reach the caller."""
    from solidworks_mcp.adapters.com_executor import ComExecutor

    with ComExecutor(name="test-exc") as ex:
        with pytest.raises(ZeroDivisionError):
            ex.run(lambda: 1 / 0)


def test_com_executor_runs_on_dedicated_thread() -> None:
    """All callables run on the same (non-caller) thread."""
    from solidworks_mcp.adapters.com_executor import ComExecutor

    caller = threading.current_thread().name
    with ComExecutor(name="test-thread") as ex:
        worker_name = ex.run(lambda: threading.current_thread().name)
        worker_name2 = ex.run(lambda: threading.current_thread().name)

    assert worker_name != caller, (
        "executor must run callables on a thread other than the caller"
    )
    assert worker_name == worker_name2, (
        "all callables must run on the same worker thread"
    )


# ---- sw_type_info unit tests ----


def test_sw_type_info_loads_sw_wrapper() -> None:
    """The makepy-generated SW wrapper loads and exposes core interfaces."""
    from solidworks_mcp.adapters import sw_type_info

    sw_type_info._ensure_loaded()
    if sw_type_info._wrapper_module is None:
        pytest.skip(
            "gen_py wrapper not available — run: "
            "python -m win32com.client.makepy sldworks.tlb"
        )
    assert sw_type_info._wrapper_module is not None
    # These are the interfaces we rely on for every SW operation.
    for iface in ("ISldWorks", "IModelDoc2", "IAssemblyDoc", "IPartDoc"):
        assert sw_type_info.interface_method_names(iface), (
            f"SW interface {iface} missing from wrapper"
        )


def test_flag_methods_is_per_interface_incremental() -> None:
    """Calling flag_methods with new interface adds; repeats are no-ops."""
    from unittest.mock import MagicMock

    from solidworks_mcp.adapters import sw_type_info

    sw_type_info._ensure_loaded()
    if sw_type_info._wrapper_module is None:
        pytest.skip(
            "gen_py wrapper not available — run: "
            "python -m win32com.client.makepy sldworks.tlb"
        )
    sw_type_info.invalidate_flag_cache()

    # Mock dispatch that records every _FlagAsMethod call.
    obj = MagicMock()
    first = sw_type_info.flag_methods(obj, "ISldWorks")
    second = sw_type_info.flag_methods(obj, "ISldWorks")  # repeat
    third = sw_type_info.flag_methods(obj, "IModelDoc2")  # new iface

    assert first > 0, "first flag of ISldWorks should do real work"
    assert second == 0, "second flag of same interface must be a no-op"
    assert third > 0, "flagging a new interface must do incremental work"


# ---- End-to-end adapter regression tests ----


@pytest.fixture
async def connected_adapter():
    """Yield a connected PyWin32Adapter and clean up afterwards."""
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    adapter = PyWin32Adapter({})
    await adapter.connect()
    try:
        yield adapter
    finally:
        await adapter.disconnect()


async def test_connect_acquires_late_bound_swapp(connected_adapter) -> None:
    """After connect(), swApp is a pywin32 late-bound CDispatch.

    Regression: earlier attempts at early binding produced
    ``ISldWorks instance`` typed dispatches that broke VARIANT out-params.
    """
    adapter = connected_adapter
    assert adapter.swApp is not None
    assert type(adapter.swApp).__name__ == "CDispatch", (
        f"swApp must be CDispatch (late-bound), got "
        f"{type(adapter.swApp).__name__}. Early binding breaks VARIANT "
        "pass-by-ref arguments used by OpenDoc6 and others."
    )


async def test_open_model_succeeds(connected_adapter) -> None:
    """open_model returns success for a valid assembly path.

    Skips if the canonical test assembly isn't on this box.
    """
    test_assy = _test_assembly_path()
    if not test_assy or not os.path.exists(test_assy):
        pytest.skip(
            f"set {_TEST_ASSEMBLY_ENV_VAR} to a local .SLDASM path to run this test"
        )

    result = await connected_adapter.open_model(test_assy)
    assert result.is_success, f"open_model failed: {result.error}"
    assert result.data is not None
    assert result.data.type == "Assembly"


async def test_get_model_info_fields_populate(connected_adapter) -> None:
    """get_model_info returns all expected fields with correct types.

    Regression: previously failed with ``TypeError: 'str' object is not
    callable`` on ``GetTitle()`` (pywin32 method-vs-property bug) and
    ``AttributeError: <unknown>.GetRebuildStatus`` (dead API call).
    """
    test_assy = _test_assembly_path()
    if not test_assy or not os.path.exists(test_assy):
        pytest.skip(
            f"set {_TEST_ASSEMBLY_ENV_VAR} to a local .SLDASM path to run this test"
        )

    await connected_adapter.open_model(test_assy)
    result = await connected_adapter.get_model_info()

    assert result.is_success, f"get_model_info failed: {result.error}"
    info = result.data
    assert isinstance(info["title"], str) and info["title"].endswith(".SLDASM")
    assert isinstance(info["path"], str)
    assert info["type"] == "Assembly"
    assert isinstance(info["configuration"], str)
    assert isinstance(info["is_dirty"], bool)
    assert isinstance(info["feature_count"], int)
    assert info["feature_count"] >= 0
    assert isinstance(info["needs_rebuild"], bool)


async def test_get_model_info_works_from_worker_thread(
    connected_adapter,
) -> None:
    """Calling from a worker thread doesn't hit the cross-thread
    AttributeError.

    Regression: before the ComExecutor refactor, this exact call path
    raised ``AttributeError: SldWorks.Application.<method>`` because the
    cached IDispatch was bound to the connect-thread's apartment.
    """
    test_assy = _test_assembly_path()
    if not test_assy or not os.path.exists(test_assy):
        pytest.skip(
            f"set {_TEST_ASSEMBLY_ENV_VAR} to a local .SLDASM path to run this test"
        )

    await connected_adapter.open_model(test_assy)

    worker_result: dict[str, object] = {}

    def worker() -> None:
        loop = asyncio.new_event_loop()
        try:
            r = loop.run_until_complete(connected_adapter.get_model_info())
            worker_result["status"] = r.status
            worker_result["error"] = r.error
            if r.is_success:
                worker_result["title"] = r.data["title"]
        finally:
            loop.close()

    t = threading.Thread(target=worker, name="pytest-worker")
    t.start()
    t.join(timeout=30)
    assert not t.is_alive(), "worker thread hung"

    assert worker_result["error"] is None, (
        f"cross-thread get_model_info surfaced an error: {worker_result['error']!r}"
    )
    assert worker_result.get("title", "").endswith(".SLDASM")


# ---- add_sketch_constraint live regression ----


async def test_add_sketch_constraint_perpendicular_and_horizontal(
    connected_adapter,
) -> None:
    """End-to-end check that add_sketch_constraint actually constrains
    SolidWorks geometry.

    Creates a fresh part + sketch, draws two right-angle lines, applies a
    perpendicular relation between them, then a horizontal relation on the
    first line, and verifies SolidWorks accepts both calls. SolidWorks
    silently accepts redundant relations, so we don't assert error on
    duplicates — instead we use ``IGetRelations.GetRelations`` to confirm
    the first line gained an extra relation after each call.
    """
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success, f"create_part failed: {part_result.error}"

    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success, f"create_sketch failed: {sketch_result.error}"

        line1 = await adapter.add_line(0.0, 0.0, 50.0, 0.0)
        line2 = await adapter.add_line(50.0, 0.0, 50.0, 50.0)
        assert line1.is_success and line2.is_success, (
            f"add_line failed: {line1.error} / {line2.error}"
        )

        perp = await adapter.add_sketch_constraint(
            line1.data, line2.data, "perpendicular"
        )
        assert perp.is_success, f"perpendicular constraint failed: {perp.error}"
        assert perp.data.startswith("Constraint_"), (
            f"unexpected constraint id: {perp.data!r}"
        )

        horiz = await adapter.add_sketch_constraint(line1.data, None, "horizontal")
        assert horiz.is_success, f"horizontal constraint failed: {horiz.error}"
        assert horiz.data.startswith("Constraint_")
    finally:
        await adapter.close_model(save=False)


async def test_add_sketch_constraint_symmetric_with_centerline(
    connected_adapter,
) -> None:
    """End-to-end check that the three-entity symmetric relation works.

    Creates a fresh part + sketch, draws a centerline plus two lines on
    either side, then applies ``symmetric`` with the centerline as
    ``entity3``. Verifies SolidWorks accepts the relation.
    """
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success, f"create_part failed: {part_result.error}"

    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success, f"create_sketch failed: {sketch_result.error}"

        # Centerline along Y axis at x=25 — the line of symmetry.
        centerline = await adapter.add_centerline(25.0, -50.0, 25.0, 50.0)
        # Two horizontal lines, mirrored about x=25
        left = await adapter.add_line(0.0, 10.0, 20.0, 10.0)
        right = await adapter.add_line(30.0, 10.0, 50.0, 10.0)
        assert centerline.is_success and left.is_success and right.is_success, (
            f"setup failed: {centerline.error} / {left.error} / {right.error}"
        )

        sym = await adapter.add_sketch_constraint(
            left.data, right.data, "symmetric", centerline.data
        )
        assert sym.is_success, f"symmetric constraint failed: {sym.error}"
        assert sym.data.startswith("Constraint_")

        # Calling symmetric without entity3 must produce a clear arity error
        # (no SW call should reach AddRelation).
        bad = await adapter.add_sketch_constraint(left.data, right.data, "symmetric")
        assert bad.is_error
        assert "entity3" in (bad.error or "")
    finally:
        await adapter.close_model(save=False)


async def test_add_sketch_constraint_unsupported_relation(connected_adapter) -> None:
    """Unsupported relation types must produce an error without touching SW."""
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success
    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success
        line1 = await adapter.add_line(0.0, 0.0, 25.0, 0.0)
        assert line1.is_success

        bogus = await adapter.add_sketch_constraint(line1.data, None, "diagonal")
        assert bogus.is_error
        assert "Unsupported relation type" in (bogus.error or "")
    finally:
        await adapter.close_model(save=False)


# ---- add_spline live regression ----


async def test_add_spline_creates_real_spline(connected_adapter) -> None:
    """End-to-end check that add_spline actually creates a spline in SW.

    Regression: pywin32 late binding unpacks a bare list of floats into N
    positional VARIANT arguments, so ``CreateSpline2`` saw 3*N+1 args and
    returned ``DISP_E_BADPARAMCOUNT``. The fix wraps the doubles in
    ``VARIANT(VT_ARRAY|VT_R8, [...])`` so they marshal as a single SAFEARRAY.
    """
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success, f"create_part failed: {part_result.error}"

    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success, f"create_sketch failed: {sketch_result.error}"

        spline = await adapter.add_spline(
            [
                {"x": 0.0, "y": 0.0},
                {"x": 25.0, "y": 15.0},
                {"x": 50.0, "y": 0.0},
                {"x": 75.0, "y": -15.0},
            ]
        )
        assert spline.is_success, f"add_spline failed: {spline.error}"
        assert spline.data.startswith("Spline_"), (
            f"unexpected spline id: {spline.data!r}"
        )
        assert spline.data in adapter._sketch_entities
    finally:
        await adapter.close_model(save=False)


async def test_add_spline_too_few_points_returns_error(connected_adapter) -> None:
    """A single point must surface a clear error without touching SW."""
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success

    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success

        bad = await adapter.add_spline([{"x": 0.0, "y": 0.0}])
        assert bad.is_error
        assert "at least 2 points" in (bad.error or "")
    finally:
        await adapter.close_model(save=False)


# ---- add_arc live regression ----


async def test_add_arc_creates_real_arc(connected_adapter) -> None:
    """End-to-end check that add_arc creates a real ISketchArc in SW.

    ``ISketchManager::CreateArc`` takes nine scalar doubles plus a short
    direction (no SAFEARRAY), so the spline VT_ARRAY|VT_R8 wrapper is not
    needed. This test locks in: (1) the mm-to-m unit conversion stays
    correct, (2) the CCW direction sentinel (``+1``) is accepted, and
    (3) the returned entity gets registered in ``_sketch_entities`` so
    later dimension/constraint calls can reference it.
    """
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success, f"create_part failed: {part_result.error}"

    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success, f"create_sketch failed: {sketch_result.error}"

        # Quarter arc (CCW): centre at origin, start at (15,0), end at (0,15).
        arc = await adapter.add_arc(
            center_x=0.0,
            center_y=0.0,
            start_x=15.0,
            start_y=0.0,
            end_x=0.0,
            end_y=15.0,
        )
        assert arc.is_success, f"add_arc failed: {arc.error}"
        assert arc.data.startswith("Arc_"), f"unexpected arc id: {arc.data!r}"
        assert arc.data in adapter._sketch_entities
    finally:
        await adapter.close_model(save=False)


async def test_add_arc_no_active_sketch_returns_error(connected_adapter) -> None:
    """Calling add_arc without an open sketch must error without touching SW."""
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success

    try:
        # Intentionally skip create_sketch; currentSketchManager stays None.
        bad = await adapter.add_arc(0.0, 0.0, 15.0, 0.0, 0.0, 15.0)
        assert bad.is_error
        assert "No active sketch" in (bad.error or "")
    finally:
        await adapter.close_model(save=False)


# ---- add_ellipse live regression ----


async def test_add_ellipse_creates_real_ellipse(connected_adapter) -> None:
    """End-to-end check that add_ellipse creates a real axis-aligned ellipse.

    ``ISketchManager::CreateEllipse`` takes nine scalar doubles
    ``(XC, YC, Zc, XMajor, YMajor, ZMajor, XMinor, YMinor, ZMinor)``.

    Geometric assertions (not just ``is_success``):

    * The returned ``Ellipse_*`` id is registered in
      ``adapter._sketch_entities`` so downstream constraint/dimension
      calls can look it up (parity with the mock adapter).
    * Exactly one sketch segment is present, and its type code (2 in
      ``swSketchSegments_e``) is the ellipse type — a regression that
      routed to ``CreateCircle`` instead would show type 1.
    * ``ISketchEllipse.GetCenterPoint2`` round-trips to the requested
      centre.
    * ``GetMajorPoint2`` / ``GetMinorPoint2`` sit on ``+X`` and ``+Y``
      from the centre respectively, at half the requested full-axis
      length each — verified in **metres** against the mm/1000.0
      conversion. A flipped axis order (minor on +X, major on +Y)
      would fail this; so would a wrong unit conversion (a stray
      mm-as-metres bug would produce a 1000x offset).
    """
    import math

    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success, f"create_part failed: {part_result.error}"

    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success, f"create_sketch failed: {sketch_result.error}"

        cx, cy, major_axis, minor_axis = 0.0, 0.0, 60.0, 30.0
        ellipse = await adapter.add_ellipse(
            center_x=cx,
            center_y=cy,
            major_axis=major_axis,
            minor_axis=minor_axis,
        )
        assert ellipse.is_success, f"add_ellipse failed: {ellipse.error}"
        assert ellipse.data.startswith("Ellipse_"), (
            f"unexpected ellipse id: {ellipse.data!r}"
        )

        # The real adapter must register the ellipse for downstream
        # constraints/dimensions to find it — parity with the mock
        # adapter (otherwise mock-validated workflows fail live with
        # "Unknown sketch entity").
        assert ellipse.data in adapter._sketch_entities, (
            f"ellipse id {ellipse.data!r} not registered in "
            f"_sketch_entities; downstream add_sketch_constraint / "
            f"add_dimension calls would fail with 'Unknown sketch entity'"
        )

        from solidworks_mcp.adapters import sw_type_info

        # Pull the entity straight from the registry; this is the
        # exact COM handle add_sketch_constraint / add_dimension would
        # resolve, so anything we observe about it is what those
        # downstream tools would see.
        seg = adapter._sketch_entities[ellipse.data]
        for iface in ("ISketchSegment", "ISketchEllipse"):
            sw_type_info.flag_methods(seg, iface)

        # swSketchSegments_e: 2 = ellipse (probed empirically; SW docs
        # don't ship enum values).
        seg_type = seg.GetType()
        assert seg_type == 2, (
            f"expected ellipse segment type 2, got {seg_type} "
            "(0 would mean CreateLine was called, 1 would mean CreateCircle)"
        )

        # GetCenterPoint/GetMajorPoint/GetMinorPoint return VARIANT arrays
        # [X_m, Y_m, Z_m] — the same format as ISketchArc.GetCenterPoint()
        # which is proven to work. The ...2() variants return ISketchPoint
        # dispatches that are unreachable on the ISketchSegment handle stored
        # by CreateEllipse, causing DISP_E_MEMBERNOTFOUND.
        ctr = seg.GetCenterPoint()
        maj = seg.GetMajorPoint()
        mnr = seg.GetMinorPoint()

        # Verify in **metres** — SolidWorks COM returns all coordinates
        # in metres, so a regression that forgot the /1000.0 conversion
        # would surface here as a 1000x offset.
        expected_major_m = (major_axis / 2.0) / 1000.0  # 0.030
        expected_minor_m = (minor_axis / 2.0) / 1000.0  # 0.015
        expected_cx_m = cx / 1000.0
        expected_cy_m = cy / 1000.0
        tol_m = 1e-6  # 1 micron — comfortably tighter than SW's tolerance

        assert abs(ctr[0] - expected_cx_m) < tol_m, (
            f"ellipse centre X {ctr[0]} m != requested "
            f"{expected_cx_m} m (mm-to-m conversion may be broken)"
        )
        assert abs(ctr[1] - expected_cy_m) < tol_m, (
            f"ellipse centre Y {ctr[1]} m != requested "
            f"{expected_cy_m} m (mm-to-m conversion may be broken)"
        )

        # Major endpoint expected on +X at major_axis / 2 from centre.
        # Minor endpoint expected on +Y at minor_axis / 2 from centre.
        major_dx_m = maj[0] - ctr[0]
        major_dy_m = maj[1] - ctr[1]
        minor_dx_m = mnr[0] - ctr[0]
        minor_dy_m = mnr[1] - ctr[1]

        assert (
            abs(major_dx_m - expected_major_m) < tol_m and abs(major_dy_m) < tol_m
        ), (
            f"major-axis offset ({major_dx_m}, {major_dy_m}) m, expected "
            f"(~{expected_major_m}, ~0); axis order or mm-to-m conversion "
            f"is probably broken"
        )
        assert (
            abs(minor_dx_m) < tol_m and abs(minor_dy_m - expected_minor_m) < tol_m
        ), (
            f"minor-axis offset ({minor_dx_m}, {minor_dy_m}) m, expected "
            f"(~0, ~{expected_minor_m}); axis order or mm-to-m "
            f"conversion is probably broken"
        )

        # Sanity: the major axis should be the longer one. If a future
        # change swaps the half-/full-axis conversion this fails loudly.
        major_len = math.hypot(major_dx_m, major_dy_m)
        minor_len = math.hypot(minor_dx_m, minor_dy_m)
        assert major_len > minor_len, (
            f"major axis length {major_len} m not greater than minor "
            f"{minor_len} m — half/full conversion may be inverted"
        )
    finally:
        await adapter.close_model(save=False)


async def test_add_ellipse_no_active_sketch_returns_error(connected_adapter) -> None:
    """Calling add_ellipse without an open sketch must error without touching SW."""
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success

    try:
        bad = await adapter.add_ellipse(0.0, 0.0, 60.0, 30.0)
        assert bad.is_error
        assert "No active sketch" in (bad.error or "")
    finally:
        await adapter.close_model(save=False)


# ---- add_polygon live regression ----


async def test_add_polygon_creates_real_polygon(connected_adapter) -> None:
    """End-to-end check that add_polygon creates a real polygon in SW.

    Regression: ``ISketchManager::CreatePolygon`` requires eight
    arguments ``(XC, YC, Zc, Xp, Yp, Zp, Sides, Inscribed)``. The May-10
    mixin refactor only forwarded six, so every call raised
    ``"Parameter not optional."`` at the COM boundary.

    Geometric assertions (not just ``is_success``):

    * The active sketch contains ``sides`` line segments (6 here) plus
      a construction circle SW adds to dimension the polygon.
    * The unique vertex set has size ``sides`` — each line shares
      endpoints with two neighbours so endpoint coordinates collapse
      to exactly ``sides`` distinct points.
    * Every vertex sits at distance ``radius`` from the requested
      centre within 0.1 mm. An incorrectly-marshalled ``Inscribed``
      flag (eg. circumscribed instead of inscribed) would put vertices
      on a different circle and fail this check.
    """
    import math

    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success, f"create_part failed: {part_result.error}"

    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success, f"create_sketch failed: {sketch_result.error}"

        cx, cy, radius, sides = 0.0, 0.0, 15.0, 6
        polygon = await adapter.add_polygon(
            center_x=cx, center_y=cy, radius=radius, sides=sides
        )
        assert polygon.is_success, f"add_polygon failed: {polygon.error}"
        # Polygon is registered in adapter._sketch_entities so subsequent
        # sketch_linear_pattern / sketch_mirror / sketch_offset calls can
        # reference it. The registry prefixes the counter with the entity
        # kind, mirroring add_line/add_arc/add_circle/add_ellipse.
        assert polygon.data.startswith("Polygon_"), (
            f"unexpected polygon id: {polygon.data!r}"
        )
        assert polygon.data in adapter._sketch_entities, (
            f"polygon id {polygon.data!r} not registered for downstream ops"
        )

        from solidworks_mcp.adapters import sw_type_info

        active_sketch = adapter.currentSketch
        sw_type_info.flag_methods(active_sketch, "ISketch")
        segments = active_sketch.GetSketchSegments()

        line_segments = []
        for seg in segments:
            for iface in ("ISketchSegment", "ISketchLine"):
                sw_type_info.flag_methods(seg, iface)
            # Type 0 == line (per swSketchSegments_e probed empirically);
            # type 2 is the construction circle SW inserts to anchor the
            # polygon's inscribed-circle dimension.
            if seg.GetType() == 0:
                line_segments.append(seg)

        assert len(line_segments) == sides, (
            f"expected {sides} polygon edges, got {len(line_segments)}"
        )

        vertices: set[tuple[float, float]] = set()
        for seg in line_segments:
            for pt in (seg.GetStartPoint2(), seg.GetEndPoint2()):
                vertices.add((round(pt.X * 1000.0, 3), round(pt.Y * 1000.0, 3)))
        assert len(vertices) == sides, (
            f"expected {sides} unique vertices, got {len(vertices)}: {vertices}"
        )

        for vx, vy in vertices:
            r = math.hypot(vx - cx, vy - cy)
            assert abs(r - radius) < 0.1, (
                f"vertex ({vx}, {vy}) at r={r:.3f}mm, expected ~{radius}mm; "
                f"all vertex radii: "
                f"{[round(math.hypot(x - cx, y - cy), 3) for x, y in vertices]}"
            )
    finally:
        await adapter.close_model(save=False)


async def test_add_polygon_no_active_sketch_returns_error(connected_adapter) -> None:
    """Calling add_polygon without an open sketch must error without touching SW."""
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success

    try:
        bad = await adapter.add_polygon(0.0, 0.0, 15.0, 6)
        assert bad.is_error
        assert "No active sketch" in (bad.error or "")
    finally:
        await adapter.close_model(save=False)


# ---- sketch_linear_pattern live regression ----


async def test_sketch_linear_pattern_creates_real_pattern(connected_adapter) -> None:
    """End-to-end geometric check that sketch_linear_pattern arrays a
    seed entity along the requested direction at the requested spacing.

    Regressions this guards against:

    1. ``ISelectionMgr::CreateSelectData`` is a method that pywin32 late
       binding will not resolve without ``sw_type_info.flag_methods``;
       without that, the helper raises ``"Member not found."`` from the
       COM boundary before the pattern call ever happens.
    2. The mm-to-m conversion on ``SpacingX`` and the
       ``atan2(direction_y, direction_x)`` conversion from a direction
       vector to a radian ``AngleX`` together have to land instances on
       the expected axis. The earlier ``is_success``-only assertion let
       a misaligned or mis-scaled pattern pass silently (same failure
       mode that bit #17).

    The check below reads the active sketch's circles back and asserts
    each centre is at ``seed + i * spacing * direction`` for
    ``i = 0..count-1``.
    """
    import math

    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success, f"create_part failed: {part_result.error}"

    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success, f"create_sketch failed: {sketch_result.error}"

        seed_x, seed_y = 0.0, 0.0
        dx, dy = 1.0, 0.0
        spacing, count = 12.0, 4
        circle = await adapter.add_circle(seed_x, seed_y, 3.0)
        assert circle.is_success, f"add_circle failed: {circle.error}"

        pattern = await adapter.sketch_linear_pattern(
            entities=[circle.data],
            direction_x=dx,
            direction_y=dy,
            spacing=spacing,
            count=count,
        )
        assert pattern.is_success, f"sketch_linear_pattern failed: {pattern.error}"
        assert pattern.data.startswith("LinearPattern_4x12.0_"), (
            f"unexpected linear pattern id: {pattern.data!r}"
        )

        from solidworks_mcp.adapters import sw_type_info

        active_sketch = adapter.currentSketch
        sw_type_info.flag_methods(active_sketch, "ISketch")
        segments = active_sketch.GetSketchSegments()
        # Each instance is a circle; SW does not insert auxiliary
        # construction geometry for a linear pattern.
        assert len(segments) == count, (
            f"expected {count} circles after linear pattern, got {len(segments)}"
        )

        centres = []
        for seg in segments:
            for iface in ("ISketchSegment", "ISketchArc"):
                sw_type_info.flag_methods(seg, iface)
            cp = seg.GetCenterPoint()
            centres.append((round(cp[0] * 1000.0, 3), round(cp[1] * 1000.0, 3)))
        centres.sort()  # ordered along +X for this scenario

        # Expected lattice along the direction unit vector.
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        expected = [
            (
                round(seed_x + i * spacing * ux, 3),
                round(seed_y + i * spacing * uy, 3),
            )
            for i in range(count)
        ]
        expected.sort()

        for (ox, oy), (ex, ey) in zip(centres, expected, strict=True):
            assert abs(ox - ex) < 0.1 and abs(oy - ey) < 0.1, (
                f"instance ({ox}, {oy}) != expected ({ex}, {ey})\n"
                f"all centres: {centres}\nexpected: {expected}"
            )
    finally:
        await adapter.close_model(save=False)


async def test_sketch_linear_pattern_no_active_sketch_returns_error(
    connected_adapter,
) -> None:
    """Calling sketch_linear_pattern without a sketch must error without touching SW."""
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success

    try:
        bad = await adapter.sketch_linear_pattern(["Line_1"], 1.0, 0.0, 10.0, 3)
        assert bad.is_error
        assert "No active sketch" in (bad.error or "")
    finally:
        await adapter.close_model(save=False)


async def test_sketch_linear_pattern_rejects_unknown_entity(connected_adapter) -> None:
    """An entity ID outside the registry must produce a clear error
    without touching SW selection state."""
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success

    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success

        bad = await adapter.sketch_linear_pattern(
            entities=["NotAnEntity_999"],
            direction_x=1.0,
            direction_y=0.0,
            spacing=10.0,
            count=3,
        )
        assert bad.is_error
        assert "Unknown sketch entity" in (bad.error or "")
    finally:
        await adapter.close_model(save=False)


# ---- sketch_circular_pattern live regression ----


async def test_sketch_circular_pattern_creates_real_pattern(
    connected_adapter,
) -> None:
    """End-to-end geometric check that sketch_circular_pattern arrays a
    seed around the user-supplied centre.

    Regression history this test guards against:

    1. ``ISketchManager::CreateCircularSketchStepAndRepeat`` silently
       returns ``False`` when ``ArcRadius`` is exactly zero, so the
       impl passes a positive minimum.
    2. The COM ``ArcAngle`` argument is **not** a starting angle — it's
       the direction (radians) from the seed to the rotation axis.
       Passing 0 puts the axis at +X from the seed regardless of the
       caller's ``(center_x, center_y)``, which lands every instance
       in the wrong place. The earlier ``is_success``-only assertion
       passed for that broken impl while the live screenshot showed
       circles clustered around the seed. This test now asserts the
       actual geometry — count and per-instance radius — so a
       silently-misplaced pattern fails the check.
    """
    import math

    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success, f"create_part failed: {part_result.error}"

    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success, f"create_sketch failed: {sketch_result.error}"

        # Seed circle at (30, 0); pattern around the sketch origin →
        # all six instances should land on a 30 mm circle centred at
        # (0, 0). The seed itself counts as one of the six.
        seed_x, seed_y, expected_r = 30.0, 0.0, 30.0
        circle = await adapter.add_circle(seed_x, seed_y, 3.0)
        assert circle.is_success, f"add_circle failed: {circle.error}"

        pattern = await adapter.sketch_circular_pattern(
            entities=[circle.data],
            angle=360.0,
            count=6,
        )
        assert pattern.is_success, (
            f"sketch_circular_pattern failed: {pattern.error}"
        )
        assert pattern.data.startswith("CircularPattern_6x360.0deg_"), (
            f"unexpected circular pattern id: {pattern.data!r}"
        )

        # Geometric assertion: read every sketch arc/circle from the
        # active sketch and confirm each centre is at the expected
        # radius from (0, 0). Uses sw_type_info flagging because
        # pywin32 late binding otherwise resolves GetSketchSegments and
        # GetCenterPoint as zero-arg properties returning a tuple.
        from solidworks_mcp.adapters import sw_type_info

        active_sketch = adapter.currentSketch
        sw_type_info.flag_methods(active_sketch, "ISketch")
        segments = active_sketch.GetSketchSegments()
        assert len(segments) == 6, (
            f"expected 6 sketch segments after pattern, got {len(segments)}"
        )

        radii_mm: list[float] = []
        for seg in segments:
            sw_type_info.flag_methods(seg, "ISketchArc")
            point = seg.GetCenterPoint()
            radii_mm.append(math.hypot(point[0] * 1000.0, point[1] * 1000.0))

        for r in radii_mm:
            assert abs(r - expected_r) < 0.5, (
                f"instance at radius {r:.2f}mm, expected ~{expected_r}mm; "
                f"all radii: {[round(x, 2) for x in radii_mm]}"
            )
    finally:
        await adapter.close_model(save=False)


async def test_sketch_circular_pattern_no_active_sketch_returns_error(
    connected_adapter,
) -> None:
    """Calling sketch_circular_pattern without a sketch must error
    without touching SW."""
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success

    try:
        bad = await adapter.sketch_circular_pattern(["Circle_1"], 360.0, 6)
        assert bad.is_error
        assert "No active sketch" in (bad.error or "")
    finally:
        await adapter.close_model(save=False)


async def test_sketch_circular_pattern_rejects_unknown_entity(
    connected_adapter,
) -> None:
    """An entity ID outside the registry must produce a clear error."""
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success

    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success

        bad = await adapter.sketch_circular_pattern(
            entities=["NotAnEntity_777"],
            angle=360.0,
            count=6,
        )
        assert bad.is_error
        assert "Unknown sketch entity" in (bad.error or "")
    finally:
        await adapter.close_model(save=False)


# ---- sketch_mirror live regression ----


async def test_sketch_mirror_reflects_lines_about_centerline(
    connected_adapter,
) -> None:
    """End-to-end geometric check that sketch_mirror produces a real
    reflection about a registered centreline.

    Regressions guarded against:

    1. ``IModelDoc2::SketchMirror`` is invoked with no arguments and
       returns void — it consumes the active selection.  Sketch
       segments must be selected under mark **1** and the centerline
       under mark **2** or SW silently no-ops.
    2. The shared ``_select_sketch_entities`` helper handles per-mark
       selection through ``ISelectionMgr.CreateSelectData`` (which
       requires ``sw_type_info`` flagging — see the linear-pattern
       test for that regression).

    The check below asserts the **actual mirrored geometry**, not just
    the return code. With a vertical centerline at x=0 and N source
    lines at positive X, we expect to find each line plus its
    x-negated twin in the active sketch.
    """
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success, f"create_part failed: {part_result.error}"

    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success, f"create_sketch failed: {sketch_result.error}"

        # Vertical centreline at x=0, lines to the right of it.
        sources = [
            (5.0, 0.0, 25.0, 0.0),
            (5.0, 10.0, 25.0, 10.0),
        ]
        cl = await adapter.add_centerline(0.0, -30.0, 0.0, 30.0)
        lines = []
        for x1, y1, x2, y2 in sources:
            r = await adapter.add_line(x1, y1, x2, y2)
            assert r.is_success, f"add_line failed: {r.error}"
            lines.append(r)
        assert cl.is_success, f"add_centerline failed: {cl.error}"

        mirror = await adapter.sketch_mirror([ln.data for ln in lines], cl.data)
        assert mirror.is_success, f"sketch_mirror failed: {mirror.error}"
        assert mirror.data.startswith(f"Mirror_{cl.data}_"), (
            f"unexpected mirror id: {mirror.data!r}"
        )

        from solidworks_mcp.adapters import sw_type_info

        active_sketch = adapter.currentSketch
        sw_type_info.flag_methods(active_sketch, "ISketch")
        segments = active_sketch.GetSketchSegments()

        # Expect N source lines + N mirrored lines + 1 centerline.
        expected_total = 2 * len(sources) + 1
        assert len(segments) == expected_total, (
            f"expected {expected_total} segments after mirror "
            f"(2*{len(sources)} lines + 1 centerline), got {len(segments)}"
        )

        line_endpoints: set[tuple[float, float, float, float]] = set()
        construction_count = 0
        for seg in segments:
            for iface in ("ISketchSegment", "ISketchLine"):
                sw_type_info.flag_methods(seg, iface)
            if seg.ConstructionGeometry:
                construction_count += 1
                continue
            sp = seg.GetStartPoint2()
            ep = seg.GetEndPoint2()
            # Normalise endpoint ordering so an SW-swapped (start, end)
            # still matches.
            p1 = (round(sp.X * 1000.0, 3), round(sp.Y * 1000.0, 3))
            p2 = (round(ep.X * 1000.0, 3), round(ep.Y * 1000.0, 3))
            if p1 > p2:
                p1, p2 = p2, p1
            line_endpoints.add((*p1, *p2))

        assert construction_count == 1, (
            f"expected 1 construction (centerline), got {construction_count}"
        )

        expected_endpoints: set[tuple[float, float, float, float]] = set()
        for x1, y1, x2, y2 in sources:
            for sx1, sx2 in ((x1, x2), (-x1, -x2)):  # source + mirrored
                p1 = (round(sx1, 3), round(y1, 3))
                p2 = (round(sx2, 3), round(y2, 3))
                if p1 > p2:
                    p1, p2 = p2, p1
                expected_endpoints.add((*p1, *p2))

        assert line_endpoints == expected_endpoints, (
            f"observed line endpoints {sorted(line_endpoints)}\n"
            f"expected                {sorted(expected_endpoints)}"
        )
    finally:
        await adapter.close_model(save=False)


async def test_sketch_mirror_no_active_sketch_returns_error(
    connected_adapter,
) -> None:
    """Calling sketch_mirror without a sketch must error without touching SW."""
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success

    try:
        bad = await adapter.sketch_mirror(["Line_1"], "Centerline_1")
        assert bad.is_error
        assert "No active sketch" in (bad.error or "")
    finally:
        await adapter.close_model(save=False)


async def test_sketch_mirror_rejects_unknown_mirror_line(
    connected_adapter,
) -> None:
    """A mirror_line ID outside the registry must produce a clear error
    without touching SW selection state."""
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success

    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success
        l1 = await adapter.add_line(5.0, 0.0, 25.0, 0.0)
        assert l1.is_success

        bad = await adapter.sketch_mirror([l1.data], "Centerline_999")
        assert bad.is_error
        assert "Unknown mirror_line entity" in (bad.error or "")
    finally:
        await adapter.close_model(save=False)


# ---- sketch_offset live regression ----


async def test_sketch_offset_creates_real_offset(connected_adapter) -> None:
    """End-to-end geometric check that sketch_offset creates a parallel
    copy of a line at the requested distance, and that
    ``reverse_direction`` flips the offset side.

    Empirically (probed against SW 2026) the conventions for a
    horizontal line are:

    * ``reverse_direction=False`` ("outward") → copy sits at ``y - offset``
    * ``reverse_direction=True``  ("inward")  → copy sits at ``y + offset``

    The earlier ``is_success``-only assertion would have let a
    regression that produced no copy, a copy on the wrong side, or a
    copy at the wrong distance pass silently. This test reads all
    sketch lines back and asserts each expected (source, offset) pair
    is present.
    """
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success, f"create_part failed: {part_result.error}"

    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success, f"create_sketch failed: {sketch_result.error}"

        # Outward offset of a horizontal line at y=0.
        src1_y, off1, reverse1 = 0.0, 5.0, False
        l1 = await adapter.add_line(0.0, src1_y, 50.0, src1_y)
        assert l1.is_success
        outward = await adapter.sketch_offset([l1.data], off1, reverse1)
        assert outward.is_success, f"sketch_offset outward failed: {outward.error}"
        assert outward.data.startswith("Offset_5.0_outward_"), (
            f"unexpected outward offset id: {outward.data!r}"
        )

        # Inward offset of a separate horizontal line at y=20.
        src2_y, off2, reverse2 = 20.0, 3.0, True
        l2 = await adapter.add_line(0.0, src2_y, 50.0, src2_y)
        assert l2.is_success
        inward = await adapter.sketch_offset([l2.data], off2, reverse2)
        assert inward.is_success, f"sketch_offset inward failed: {inward.error}"
        assert inward.data.startswith("Offset_3.0_inward_"), (
            f"unexpected inward offset id: {inward.data!r}"
        )

        from solidworks_mcp.adapters import sw_type_info

        active_sketch = adapter.currentSketch
        sw_type_info.flag_methods(active_sketch, "ISketch")
        segments = active_sketch.GetSketchSegments()

        # 2 sources + 2 offsets = 4 line segments, no construction.
        assert len(segments) == 4, (
            f"expected 4 segments (2 sources + 2 offsets), got {len(segments)}"
        )

        observed_ys: set[float] = set()
        for seg in segments:
            for iface in ("ISketchSegment", "ISketchLine"):
                sw_type_info.flag_methods(seg, iface)
            assert seg.GetType() == 0, (
                f"unexpected segment type {seg.GetType()} (offset should "
                "produce a line copy of a line)"
            )
            assert seg.ConstructionGeometry is False, (
                "sketch_offset must not convert segments to construction "
                "geometry by default"
            )
            sp = seg.GetStartPoint2()
            ep = seg.GetEndPoint2()
            ys = {round(sp.Y * 1000.0, 3), round(ep.Y * 1000.0, 3)}
            assert len(ys) == 1, f"non-horizontal line at {sp.Y}/{ep.Y}"
            observed_ys.add(next(iter(ys)))

        expected_ys = {
            src1_y,
            src1_y - off1 if not reverse1 else src1_y + off1,
            src2_y,
            src2_y - off2 if not reverse2 else src2_y + off2,
        }
        assert observed_ys == expected_ys, (
            f"observed line y-values {sorted(observed_ys)} != "
            f"expected {sorted(expected_ys)}"
        )
    finally:
        await adapter.close_model(save=False)


async def test_sketch_offset_no_active_sketch_returns_error(
    connected_adapter,
) -> None:
    """Calling sketch_offset without a sketch must error without touching SW."""
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success

    try:
        bad = await adapter.sketch_offset(["Line_1"], 5.0, False)
        assert bad.is_error
        assert "No active sketch" in (bad.error or "")
    finally:
        await adapter.close_model(save=False)


async def test_sketch_offset_rejects_non_positive_distance(
    connected_adapter,
) -> None:
    """A non-positive distance must produce a clear error without touching
    SW selection state."""
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success

    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success
        l1 = await adapter.add_line(0.0, 0.0, 50.0, 0.0)
        assert l1.is_success

        bad = await adapter.sketch_offset([l1.data], 0.0, False)
        assert bad.is_error
        assert "offset_distance > 0" in (bad.error or "")
    finally:
        await adapter.close_model(save=False)


# ---- add_centerline live regression ----


async def test_add_centerline_creates_real_centerline(connected_adapter) -> None:
    """End-to-end check that add_centerline creates a real construction line in SW.

    Asserts the resulting geometry, not just the return code:

    * Exactly one segment is in the active sketch after the call.
    * Its ``ISketchSegment.ConstructionGeometry`` property is ``True`` —
      this is the construction-vs-real flag that distinguishes a
      centerline from a regular line, so a regression that calls
      ``CreateLine`` by mistake would fail here.
    * The segment's start and end points round-trip through
      ``ISketchLine.GetStartPoint2 / GetEndPoint2`` to the requested
      ``(0, -20)`` and ``(0, 20)`` mm — pinning the mm-to-m conversion.

    All readback calls need ``sw_type_info.flag_methods`` so pywin32
    late binding resolves the zero-arg accessors as methods rather than
    tuple-valued properties.
    """
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success, f"create_part failed: {part_result.error}"

    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success, f"create_sketch failed: {sketch_result.error}"

        x1, y1, x2, y2 = 0.0, -20.0, 0.0, 20.0
        centerline = await adapter.add_centerline(x1, y1, x2, y2)
        assert centerline.is_success, f"add_centerline failed: {centerline.error}"
        assert centerline.data.startswith("Centerline_"), (
            f"unexpected centerline id: {centerline.data!r}"
        )
        assert centerline.data in adapter._sketch_entities

        from solidworks_mcp.adapters import sw_type_info

        active_sketch = adapter.currentSketch
        sw_type_info.flag_methods(active_sketch, "ISketch")
        segments = active_sketch.GetSketchSegments()
        assert len(segments) == 1, (
            f"expected 1 sketch segment after add_centerline, got {len(segments)}"
        )

        seg = segments[0]
        for iface in ("ISketchSegment", "ISketchLine"):
            sw_type_info.flag_methods(seg, iface)

        assert seg.ConstructionGeometry is True, (
            "add_centerline must produce a construction-geometry segment "
            "(ConstructionGeometry=True), not a regular line"
        )

        sp = seg.GetStartPoint2()
        ep = seg.GetEndPoint2()
        # Endpoints come back in metres; SW may swap start/end depending
        # on internal direction, so compare as an unordered pair.
        observed = {
            (round(sp.X * 1000.0, 3), round(sp.Y * 1000.0, 3)),
            (round(ep.X * 1000.0, 3), round(ep.Y * 1000.0, 3)),
        }
        expected = {(x1, y1), (x2, y2)}
        assert observed == expected, (
            f"centerline endpoints {observed} != requested {expected}"
        )
    finally:
        await adapter.close_model(save=False)


async def test_add_centerline_no_active_sketch_returns_error(
    connected_adapter,
) -> None:
    """Calling add_centerline without an open sketch must error without touching SW."""
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success

    try:
        # Intentionally skip create_sketch; currentSketchManager stays None.
        bad = await adapter.add_centerline(0.0, -20.0, 0.0, 20.0)
        assert bad.is_error
        assert "No active sketch" in (bad.error or "")
    finally:
        await adapter.close_model(save=False)


# ---- Composition: live creator -> consumer chains ----
#
# These tests pipe the ID returned by each ``add_*`` op into a downstream
# consumer (``sketch_*_pattern`` / ``sketch_mirror`` / ``sketch_offset``).
# The whole shape of every bug fixed in PR #22 was "creator's
# isolated test passed, consumer's isolated test passed, but the
# combination failed".  These tests pin the contract on the live adapter
# so a future regression in either side breaks here, not in a user demo.


async def test_polygon_id_flows_into_linear_pattern_live(
    connected_adapter,
) -> None:
    """End-to-end: ``add_polygon`` ID must be a valid input to
    ``sketch_linear_pattern``.

    Regression: ``_add_polygon_impl`` originally synthesised a
    ``Polygon_6sided_<rand>`` string and skipped
    ``_register_sketch_entity``, so every downstream op failed with
    ``Unknown sketch entity 'Polygon_*'`` even though the isolated
    polygon test in this file passed.  Catches both halves of that
    failure: the missing registration AND the
    tuple-not-Select4-able handler in ``_select_sketch_entities``.
    """
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success, f"create_part failed: {part_result.error}"
    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success, (
            f"create_sketch failed: {sketch_result.error}"
        )

        seed = await adapter.add_polygon(
            center_x=-50.0, center_y=0.0, radius=5.0, sides=6
        )
        assert seed.is_success, f"add_polygon failed: {seed.error}"
        assert seed.data in adapter._sketch_entities, (
            f"polygon id {seed.data!r} must be in the registry; otherwise "
            "downstream pattern/mirror/offset cannot resolve it."
        )

        pattern = await adapter.sketch_linear_pattern(
            entities=[seed.data],
            direction_x=1.0,
            direction_y=0.0,
            spacing=15.0,
            count=4,
        )
        assert pattern.is_success, (
            f"polygon -> linear_pattern composition failed: {pattern.error}"
        )
    finally:
        await adapter.close_model(save=False)


async def test_polygon_id_flows_into_mirror_live(connected_adapter) -> None:
    """``add_polygon`` ID + ``add_centerline`` ID -> ``sketch_mirror``."""
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success
    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success

        poly = await adapter.add_polygon(-30.0, 20.0, 5.0, 6)
        cl = await adapter.add_centerline(-50.0, 0.0, 50.0, 0.0)
        assert poly.is_success and cl.is_success, (
            f"setup failed: {poly.error} / {cl.error}"
        )

        mirrored = await adapter.sketch_mirror(
            entities=[poly.data], mirror_line=cl.data
        )
        assert mirrored.is_success, (
            f"polygon -> mirror composition failed: {mirrored.error}"
        )
    finally:
        await adapter.close_model(save=False)


async def test_polygon_id_flows_into_offset_live(connected_adapter) -> None:
    """``add_polygon`` ID -> ``sketch_offset``."""
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success
    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success

        poly = await adapter.add_polygon(0.0, 0.0, 10.0, 6)
        assert poly.is_success, f"add_polygon failed: {poly.error}"

        offset = await adapter.sketch_offset(
            entities=[poly.data], offset_distance=2.0, reverse_direction=False
        )
        assert offset.is_success, (
            f"polygon -> offset composition failed: {offset.error}"
        )
    finally:
        await adapter.close_model(save=False)


async def test_polygon_id_flows_into_circular_pattern_live(
    connected_adapter,
) -> None:
    """End-to-end: ``add_polygon`` ID -> ``sketch_circular_pattern``.

    Regression history this test guards against:

    * Polygons register as a SAFEARRAY tuple of segment handles, so the
      ``GetCenterPoint`` lookup ``_sketch_circular_pattern_impl`` uses
      to derive the seed-to-axis offset cannot run against them. PR #23
      added a register-time centre cache (``_sketch_entity_centers``)
      so polygon IDs flow through the same path as a circle. Without
      the cache the impl raises a "use a circle, arc, ellipse, or
      polygon seed" error.

    * Asserts the actual geometry — six sketch segments at the right
      radius — not just ``is_success``, because a misplaced pattern
      (e.g. the 1 mm placeholder ring the impl used to produce) would
      still report success.
    """

    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success
    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success

        # Hexagon at (30, 0): seed-to-origin distance = 30 mm.
        seed = await adapter.add_polygon(
            center_x=30.0, center_y=0.0, radius=5.0, sides=6
        )
        assert seed.is_success, f"add_polygon failed: {seed.error}"

        # Capture pre-pattern segment count as the baseline. Hexagon
        # produces 6 polygon edges + 1 inscribed construction circle in
        # SW 2026, but the exact count varies by SW version — measure
        # empirically rather than hard-coding.
        from solidworks_mcp.adapters import sw_type_info

        active_sketch = adapter.currentSketch
        sw_type_info.flag_methods(active_sketch, "ISketch")
        seed_segments = len(active_sketch.GetSketchSegments())
        assert seed_segments >= 6, (
            f"expected at least 6 polygon edges, got {seed_segments}"
        )

        pattern = await adapter.sketch_circular_pattern(
            entities=[seed.data],
            angle=360.0,
            count=6,
        )
        assert pattern.is_success, (
            f"polygon -> circular_pattern composition failed: {pattern.error}"
        )

        # 6 instances × 6 hexagon edges = 36 patterned edges at minimum.
        # SW may also propagate the seed's inscribed construction circle
        # (so the real count can be ≥ 6 × seed_segments), but only the
        # real edges are guaranteed to scale with count. Bound below.
        # The strict-error guard added in this PR rules out the silent
        # 1 mm placeholder pattern that would still produce these counts
        # but bunched at the origin — so reaching here proves the seed
        # centre lookup succeeded.
        segments_after = active_sketch.GetSketchSegments()
        assert len(segments_after) >= 6 * 6, (
            f"expected at least 6 × 6 = 36 patterned edges, got "
            f"{len(segments_after)} (seed had {seed_segments})"
        )
    finally:
        await adapter.close_model(save=False)


async def test_rectangle_id_flows_into_circular_pattern_live(
    connected_adapter,
) -> None:
    """End-to-end: ``add_rectangle`` ID -> ``sketch_circular_pattern``.

    Rectangles register as a SAFEARRAY tuple of line segments — same
    shape quirk as polygons. ``_add_rectangle_impl`` now caches the
    geometric centre at register time so a rectangle ID flows through
    circular_pattern without the "use a circle, arc, ellipse, or
    polygon seed" rejection that PR #23's safety net would surface.
    """
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success
    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success

        # Rectangle from (20, -5) to (40, 5) → centred at (30, 0),
        # seed-to-origin distance = 30 mm.
        seed = await adapter.add_rectangle(20.0, -5.0, 40.0, 5.0)
        assert seed.is_success, f"add_rectangle failed: {seed.error}"

        from solidworks_mcp.adapters import sw_type_info

        active_sketch = adapter.currentSketch
        sw_type_info.flag_methods(active_sketch, "ISketch")
        seed_segments = len(active_sketch.GetSketchSegments())
        # SW 2026's corner-rectangle tool emits 4 line edges + 2 implicit
        # construction segments (the diagonal markers). Just guard the
        # lower bound — the exact count varies by SW version.
        assert seed_segments >= 4, (
            f"expected at least 4 rectangle edges, got {seed_segments}"
        )

        pattern = await adapter.sketch_circular_pattern(
            entities=[seed.data],
            angle=360.0,
            count=4,
        )
        assert pattern.is_success, (
            f"rectangle -> circular_pattern composition failed: {pattern.error}"
        )

        # 4 instances × 4 rectangle edges = 16 patterned edges at minimum.
        # SW 2026 includes 2 construction segments in seed_segments that
        # do NOT propagate through the pattern (only real edges scale
        # with count), so the post-pattern total is 4×4 + 2 = 18 here.
        # Bound below — the strict-error guard added in this PR rules
        # out the silent 1 mm placeholder fallback, so reaching here
        # proves the cached rectangle centre fed the pattern correctly.
        segments_after = active_sketch.GetSketchSegments()
        assert len(segments_after) >= 4 * 4, (
            f"expected at least 4 × 4 = 16 patterned edges, got "
            f"{len(segments_after)} (seed had {seed_segments})"
        )
    finally:
        await adapter.close_model(save=False)


async def test_line_seed_in_circular_pattern_errors_clearly_live(
    connected_adapter,
) -> None:
    """A line seed in ``sketch_circular_pattern`` must error with a clear
    message, NOT silently produce a 1 mm placeholder pattern.

    Regression: the previous impl let line/spline/centerline seeds fall
    through to ``arc_radius_mm = 0.0`` and clamped to 1 mm via
    ``max(arc_radius_mm / 1000.0, 0.001)``. The COM call succeeded and
    the user saw a tightly clustered pattern instead of an error. The
    strict guard now raises so the failure is loud.
    """
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success
    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success

        line = await adapter.add_line(20.0, -5.0, 40.0, 5.0)
        assert line.is_success, f"add_line failed: {line.error}"

        pattern = await adapter.sketch_circular_pattern(
            entities=[line.data],
            angle=360.0,
            count=4,
        )
        assert pattern.is_error, (
            f"expected error for line seed, got success: {pattern.data}"
        )
        # Error must name the seed and point at the supported types.
        assert line.data in (pattern.error or "")
        assert "GetCenterPoint" in (pattern.error or "")
    finally:
        await adapter.close_model(save=False)


async def test_ellipse_id_flows_into_circular_pattern_live(
    connected_adapter,
) -> None:
    """End-to-end: ``add_ellipse`` ID -> ``sketch_circular_pattern``
    with the seed on the +X axis at y=0.

    Regression: ``math.atan2(-0.0, -seed_x)`` returns ``-π`` for a seed
    on the +X axis (because ``-seed_xy[1]`` is ``-0.0``), and
    ``CreateCircularSketchStepAndRepeat`` silently rejects negative
    ``ArcAngle`` values.  Combined with PR #21's earlier non-ellipse
    flagging, the live circular_pattern call returned False until both
    were fixed.  The seed coordinates ``(+X, 0)`` matter — the bug
    does NOT reproduce off-axis.
    """
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success
    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success

        seed = await adapter.add_ellipse(
            center_x=30.0, center_y=0.0, major_axis=12.0, minor_axis=6.0
        )
        assert seed.is_success, f"add_ellipse failed: {seed.error}"

        pattern = await adapter.sketch_circular_pattern(
            entities=[seed.data],
            angle=360.0,
            count=6,
        )
        assert pattern.is_success, (
            f"ellipse -> circular_pattern composition failed: {pattern.error}"
        )
    finally:
        await adapter.close_model(save=False)


async def test_arc_id_flows_into_mirror_and_offset_live(
    connected_adapter,
) -> None:
    """``add_arc`` ID -> ``sketch_mirror`` AND ``sketch_offset`` from the
    same arc (the bottom-band shape from the live demo)."""
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success
    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success

        cl = await adapter.add_centerline(-90.0, -50.0, 90.0, -50.0)
        arc = await adapter.add_arc(
            center_x=-50.0,
            center_y=-40.0,
            start_x=-70.0,
            start_y=-40.0,
            end_x=-30.0,
            end_y=-40.0,
        )
        assert cl.is_success and arc.is_success, (
            f"setup failed: {cl.error} / {arc.error}"
        )

        mirrored = await adapter.sketch_mirror(
            entities=[arc.data], mirror_line=cl.data
        )
        assert mirrored.is_success, f"arc -> mirror failed: {mirrored.error}"

        offset = await adapter.sketch_offset(
            entities=[arc.data], offset_distance=3.0, reverse_direction=False
        )
        assert offset.is_success, f"arc -> offset failed: {offset.error}"
    finally:
        await adapter.close_model(save=False)


async def test_exit_sketch_clears_leftover_sw_sketch_live(
    connected_adapter,
) -> None:
    """Regression: ``adapter.exit_sketch()`` must toggle SW out of
    sketch-edit mode even when the **adapter** doesn't think it opened
    that sketch.

    Scenario this reproduces: a prior aborted demo / test run left
    SolidWorks sitting in sketch-edit mode.  A fresh adapter connects,
    knows nothing about the previous sketch, and calling
    ``adapter.exit_sketch()`` used to short-circuit on the Python-side
    ``currentSketchManager is None`` check — leaving SW stuck.  Every
    subsequent ``create_sketch("Front")`` then failed with
    ``Failed to select plane: Front Plane`` because SW cannot open a
    new sketch while one is already active.

    We reproduce that state by opening a sketch via raw COM (bypassing
    ``adapter.create_sketch`` so ``adapter.currentSketchManager`` stays
    ``None``), then assert ``exit_sketch`` actually toggles it off and
    a follow-up ``create_sketch`` succeeds.
    """
    adapter = connected_adapter

    # Best-effort cleanup: prior test runs may have left SW in sketch-edit
    # mode.  Use the fixed exit_sketch itself to clear that state; if SW
    # has no document open, the WARNING result is benign.
    await adapter.exit_sketch()

    part_result = await adapter.create_part()
    assert part_result.is_success, f"create_part failed: {part_result.error}"

    try:
        # --- Stage the divergent state: open a sketch through the
        # standard adapter path (so SW actually goes into sketch-edit
        # mode), then **manually null out the adapter-side handles** so
        # the next ``exit_sketch`` looks like a fresh connection that
        # never knew about the open sketch.
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success, (
            f"create_sketch staging failed: {sketch_result.error}"
        )
        # Drop the adapter's pointer to the just-opened sketch — this is
        # exactly what happens when a previous demo / test run crashed
        # before exiting and a new adapter instance reconnects.
        adapter.currentSketchManager = None
        adapter.currentSketch = None
        adapter._reset_sketch_entity_registry()

        # SW still has the sketch open (verify before the actual exercise).
        from solidworks_mcp.adapters import sw_type_info

        def _probe_sw_state() -> object:
            return adapter.swApp.ActiveDoc.GetActiveSketch2()

        pre = adapter._handle_com_operation("probe_pre_exit", _probe_sw_state)
        assert pre.is_success and pre.data is not None, (
            f"staging failed: SW reports no active sketch ({pre.data!r}); "
            f"err={pre.error}"
        )

        # --- The actual test: exit_sketch must toggle SW out of the
        #     leftover sketch despite adapter-side state being empty.
        exit_result = await adapter.exit_sketch()
        assert exit_result.is_success, (
            f"exit_sketch should succeed on SW-side leftover sketch, got "
            f"status={exit_result.status} err={exit_result.error}"
        )

        # Verify SW reports no active sketch afterwards.
        post = adapter._handle_com_operation("probe_post_exit", _probe_sw_state)
        assert post.is_success and post.data is None, (
            f"SW still reports an active sketch after exit_sketch: "
            f"data={post.data!r} err={post.error}"
        )

        # Final proof: a fresh create_sketch must succeed now, which is
        # exactly the user-visible symptom this bug surfaced as.
        follow_up = await adapter.create_sketch("Front")
        assert follow_up.is_success, (
            f"create_sketch after exit_sketch failed: {follow_up.error}"
        )
    finally:
        await adapter.close_model(save=False)


async def test_spline_id_flows_into_mirror_live(connected_adapter) -> None:
    """``add_spline`` ID -> ``sketch_mirror``.

    Catches a future regression in spline-segment selection mirroring
    the polygon-tuple bug — splines come back as a single
    ``ISketchSegment`` today but a future SW version could split them.
    """
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success
    try:
        sketch_result = await adapter.create_sketch("Front")
        assert sketch_result.is_success

        spl = await adapter.add_spline(
            [
                {"x": -30.0, "y": 5.0},
                {"x": 0.0, "y": 15.0},
                {"x": 30.0, "y": 5.0},
            ]
        )
        cl = await adapter.add_centerline(-50.0, 0.0, 50.0, 0.0)
        assert spl.is_success and cl.is_success, (
            f"setup failed: {spl.error} / {cl.error}"
        )

        mirrored = await adapter.sketch_mirror(
            entities=[spl.data], mirror_line=cl.data
        )
        assert mirrored.is_success, (
            f"spline -> mirror composition failed: {mirrored.error}"
        )
    finally:
        await adapter.close_model(save=False)


# ---- create_sweep / create_loft live regression ----
#
# Phase 1 of the tool-surface expansion (fork issue #2). These exercise the
# real InsertProtrusionSwept4 / InsertProtrusionBlend2 COM calls end to end.
# Geometry the adapter can't yet build natively (an offset reference plane for
# the loft's second profile, a helix for the sweep path) is created with raw
# COM, routed through the adapter's ComExecutor so it runs on the STA thread.


def _solid_body_count(adapter) -> int:
    """Return the number of solid bodies in the active part.

    Uses ``IPartDoc.GetBodies2(swSolidBody, bVisibleOnly=True)``. A successful
    boss feature (loft/sweep) must leave at least one solid body, so this is
    the geometric proof that the feature actually built rather than silently
    no-opping. COM runs inline on the calling thread, matching the rest of
    this suite.
    """
    # swBodyType_e.swSolidBody == 0.
    bodies = adapter.currentModel.GetBodies2(0, True)
    if bodies is None:
        return 0
    try:
        return len(bodies)
    except TypeError:
        # Single body comes back as a bare IBody2, not a tuple.
        return 1


def _feature_name_by_type(adapter, type_name: str) -> str:
    """Return the name of the last feature whose ``GetTypeName2`` matches.

    Walks ``FirstFeature`` → ``GetNextFeature``, flagging each feature for
    ``IFeature`` and reading members with a call-then-fallback accessor so it
    works whether or not pywin32 has method-flagged the feature. Used to
    recover a feature whose creator call returns None on success (e.g.
    ``InsertHelix``).
    """
    from solidworks_mcp.adapters import sw_type_info

    def _flag(obj, iface):
        try:
            sw_type_info.flag_methods(obj, iface)
        except Exception:
            pass

    def _read(obj, name):
        member = getattr(obj, name, None)
        if not callable(member):
            return member
        try:
            return member()
        except Exception:
            return member

    _flag(adapter.currentModel, "IModelDoc2")
    found = ""
    feat = _read(adapter.currentModel, "FirstFeature")
    for _ in range(5000):
        if not feat:
            break
        _flag(feat, "IFeature")
        try:
            if _read(feat, "GetTypeName2") == type_name:
                found = str(_read(feat, "Name"))
        except Exception:
            pass
        try:
            feat = _read(feat, "GetNextFeature")
        except Exception:
            break
    return found


async def test_create_loft_tapered_bevel(connected_adapter) -> None:
    """End-to-end loft between two parallel circular profiles of different
    radii — a cone/gear-like tapered bevel.

    Builds a 30 mm-radius circle on the Front plane, an offset reference
    plane 40 mm in front of it, and a 10 mm-radius circle on that plane, then
    lofts the two profiles. Asserts the feature is created AND a solid body
    now exists, so a silently-failing ``InsertProtrusionBlend2`` (returns
    None / leaves no geometry) fails the test.
    """
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success, f"create_part failed: {part_result.error}"

    try:
        # Profile 1: large circle on the Front plane.
        s1 = await adapter.create_sketch("Front")
        assert s1.is_success, f"create_sketch(Front) failed: {s1.error}"
        c1 = await adapter.add_circle(0.0, 0.0, 30.0)
        assert c1.is_success, f"add_circle #1 failed: {c1.error}"
        assert (await adapter.exit_sketch()).is_success

        # Offset reference plane 40 mm in front of the Front plane. The
        # FirstConstraint flag 8 == distance (per the InsertProtrusionBlend
        # API example); InsertRefPlane works in metres.
        front = adapter.currentModel.FeatureByName("Front Plane")
        assert front and front.Select2(False, 0), "could not select Front plane"
        ref_plane = adapter.currentModel.FeatureManager.InsertRefPlane(
            8, 0.040, 0, 0, 0, 0
        )
        adapter.currentModel.ClearSelection2(True)
        plane_name = str(ref_plane.Name) if ref_plane else ""
        assert plane_name, "InsertRefPlane returned no reference plane"

        # Profile 2: small circle on the offset plane.
        s2 = await adapter.create_sketch(plane_name)
        assert s2.is_success, f"create_sketch({plane_name}) failed: {s2.error}"
        c2 = await adapter.add_circle(0.0, 0.0, 10.0)
        assert c2.is_success, f"add_circle #2 failed: {c2.error}"
        assert (await adapter.exit_sketch()).is_success

        loft = await adapter.create_loft(
            LoftParameters(profiles=[s1.data, s2.data])
        )
        assert loft.is_success, f"create_loft failed: {loft.error}"
        assert loft.data.type == "Loft"
        assert loft.data.name, "loft feature has no name"

        assert _solid_body_count(adapter) >= 1, (
            "loft reported success but the part has no solid body"
        )
    finally:
        await adapter.close_model(save=False)


async def test_create_sweep_circular_profile_along_helix(connected_adapter) -> None:
    """End-to-end sweep of a circular profile along a helical path — the
    classic spring/coil.

    Builds a helix from a base circle on the Top plane, a small circular
    profile on the Front plane positioned at the helix's start point, then
    sweeps the profile along the helix. The profile-inference logic must pick
    the *profile* sketch (most recent, on the Front plane) rather than the
    helix's base-circle sketch, and the path selection must resolve the helix
    as a reference curve (not a sketch). Asserts a solid body results.
    """
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success, f"create_part failed: {part_result.error}"

    try:
        # Base circle (helix diameter) on the Top plane, radius 10 mm,
        # centred on the origin. The helix axis is the Top-plane normal, so
        # the helix starts at (10, 0, 0).
        base = await adapter.create_sketch("Top")
        assert base.is_success, f"create_sketch(Top) failed: {base.error}"
        base_circle = await adapter.add_circle(0.0, 0.0, 10.0)
        assert base_circle.is_success, f"base add_circle failed: {base_circle.error}"

        # Helix by height & pitch (swHelixDefinedBy_e.HeightAndPitch == 2):
        # 50 mm tall, 10 mm pitch → 5 revolutions. InsertHelix consumes the
        # *open* base sketch directly (matching the SW Create_Spiral example),
        # so the sketch must NOT be exited or re-selected first. It lives on
        # IModelDoc2 (not IFeatureManager) and, like FeatureRevolve2 on recent
        # SW builds, returns None on success — the helix name is read back from
        # the feature tree afterwards.
        adapter.currentModel.InsertHelix(
            False,  # Reversed
            True,  # Clockwise
            False,  # Tapered
            False,  # Outward
            2,  # Helixdef = height & pitch
            0.050,  # Height (m)
            0.010,  # Pitch (m)
            0.0,  # Revolution (ignored for height & pitch)
            0.0,  # TaperAngle
            0.0,  # Startangle
        )
        adapter.currentModel.ClearSelection2(True)
        helix_name = _feature_name_by_type(adapter, "Helix")
        assert helix_name, "InsertHelix did not create a helix feature"

        # Profile: small circle on the Front plane (z=0), centred at the
        # helix start point (10, 0) so the profile pierces the path start.
        prof = await adapter.create_sketch("Front")
        assert prof.is_success, f"create_sketch(Front) failed: {prof.error}"
        prof_circle = await adapter.add_circle(10.0, 0.0, 2.0)
        assert prof_circle.is_success, f"profile add_circle failed: {prof_circle.error}"
        assert (await adapter.exit_sketch()).is_success

        sweep = await adapter.create_sweep(SweepParameters(path=helix_name))
        assert sweep.is_success, f"create_sweep failed: {sweep.error}"
        assert sweep.data.type == "Sweep"
        # The profile must be the Front-plane circle, not the helix base.
        assert sweep.data.parameters["profile"] == prof.data, (
            f"sweep used wrong profile {sweep.data.parameters['profile']!r}; "
            f"expected the Front-plane profile {prof.data!r}"
        )

        assert _solid_body_count(adapter) >= 1, (
            "sweep reported success but the part has no solid body"
        )
    finally:
        await adapter.close_model(save=False)


async def test_create_loft_too_few_profiles_returns_error(connected_adapter) -> None:
    """A single-profile loft must error without touching SW geometry."""
    adapter = connected_adapter

    part_result = await adapter.create_part()
    assert part_result.is_success
    try:
        bad = await adapter.create_loft(LoftParameters(profiles=["Sketch1"]))
        assert bad.is_error
        assert "at least 2 profile" in (bad.error or "")
    finally:
        await adapter.close_model(save=False)
