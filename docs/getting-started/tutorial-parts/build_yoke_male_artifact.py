from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from solidworks_mcp.adapters import create_adapter
from solidworks_mcp.adapters.base import ExtrusionParameters
from solidworks_mcp.config import load_config

ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = ROOT / "docs" / "getting-started" / "tutorial-parts"
OUTPUT_PART = ARTIFACT_DIR / "yoke_male_from_prompt.SLDPRT"
OUTPUT_IMAGE = ARTIFACT_DIR / "yoke_male_from_prompt_isometric.png"
ANSWER_KEY = Path(
    r"C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\U-Joint\Yoke_male.sldprt"
)
ANSWER_KEY_IMAGE = ARTIFACT_DIR / "answer_key_yoke_male_isometric.png"

# Dimensions from read_yoke_geometry.py reverse-engineering of the SW 2026 sample:
#   Base cylinder:  dia=38.10mm (r=19.050), height=47.625mm (1-7/8"), Top(XZ) plane at Y=0
#   Arm gap (slot): Right(YZ) plane, slot Z:±10.160mm, Y:-7.455 to 29.145mm, through-all in X
#   U-slot profile: Front(XY) plane, complex arcs+lines (see Sketch2 in reader output)
#   Pin bore:       Front(XY) plane, dia=9.525mm (r=4.7625), center (0,9.525), through-all in Z
#   Stub shaft:     Top(XZ) at Y=47.625mm, dia=12.70mm (r=6.350), extrude to Y=66.675mm (19.05mm)
#   Stub bore:      Face1 (top of stub after chamfer), D-profile r=6.350 + chord at X=4.763


def require(result: Any, label: str) -> Any:
    if not result.is_success:
        raise RuntimeError(f"{label} failed: {result.error}")
    return result


def unwrap_for_method(adapter: Any, method_name: str) -> Any | None:
    current: Any | None = adapter
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if hasattr(current, method_name):
            return current
        current = getattr(current, "adapter", None)
    return None


def create_sketch_on_face_y(adapter: Any, y_mm: float) -> str:
    """Select the face at world Y=y_mm (on the Z=0 axis) and open a sketch on it.

    SelectByID2 requires a Callout parameter typed as ICallout*. Passing Python None
    marshals as VT_NULL which SolidWorks rejects; instead we pass a VT_DISPATCH null
    VARIANT (win32com.client.VARIANT(VT_DISPATCH, None)) which matches the expected
    COM null-pointer type.
    Runs through _handle_com_operation to respect the COM STA thread invariant.
    Returns the sketch name.
    """
    raw = unwrap_for_method(adapter, "_handle_com_operation")
    if raw is None or raw.currentModel is None:
        raise RuntimeError("No active model for face sketch")

    def _op() -> str:
        import pythoncom
        import win32com.client as _win32

        model = raw.currentModel
        y_m = y_mm / 1000.0
        null_callout = _win32.VARIANT(pythoncom.VT_DISPATCH, None)

        # Clear any lingering sketch/feature selection from the previous operation,
        # then rebuild so new faces from recent features are fully tessellated and
        # selectable. Without this, SelectByID2("", "FACE", ...) may return False
        # even when the face geometrically exists.
        try:
            model.ClearSelection2(True)
        except Exception:
            pass
        try:
            model.ForceRebuild3(True)
        except Exception:
            pass

        # Try a set of candidate (x, z) offsets in case the exact center misses.
        # The face of interest (top cap) has radius r ≈ 19mm; any interior point works.
        # Also try both Extension.SelectByID2 and the model-level SelectByID2.
        candidate_xz = [
            (0.0, 0.0), (0.005, 0.0), (-0.005, 0.0),
            (0.0, 0.005), (0.0, -0.005), (0.008, 0.008),
            (0.010, 0.0), (0.0, 0.010), (0.015, 0.015),
        ]
        selected = False
        for cx, cz in candidate_xz:
            for sel_fn in (
                lambda cx=cx, cz=cz: model.Extension.SelectByID2(
                    "", "FACE", cx, y_m, cz, False, 0, null_callout, 0
                ),
                lambda cx=cx, cz=cz: model.SelectByID2(
                    "", "FACE", cx, y_m, cz, False, 0, null_callout, 0
                ),
            ):
                try:
                    selected = bool(sel_fn())
                except Exception:
                    selected = False
                if selected:
                    break
            if selected:
                break
        if not selected:
            raise RuntimeError(f"SelectByID2 FACE at Y={y_mm}mm returned False for all candidate points")

        raw.currentSketchManager = model.SketchManager
        raw._reset_sketch_entity_registry()
        try:
            sketch = raw.currentSketchManager.InsertSketch(True)
        except Exception:
            sketch = raw.currentSketchManager.InsertSketch()
        raw.currentSketch = sketch
        raw._sketch_count += 1
        name = str(getattr(sketch, "Name", None) or f"Sketch_{raw._sketch_count}")
        raw._last_sketch_name = name
        return name

    result = raw._handle_com_operation(f"create_sketch_on_face_y{y_mm}", _op)
    if not result.is_success:
        raise RuntimeError(f"create_sketch_on_face_y({y_mm}) failed: {result.error}")
    return str(result.data)


def chamfer_edge_at(adapter: Any, wx_mm: float, wy_mm: float, wz_mm: float, distance_mm: float) -> None:
    """Chamfer the edge nearest to world coordinates. Non-fatal on failure."""
    raw = unwrap_for_method(adapter, "_handle_com_operation")
    if raw is None or raw.currentModel is None:
        return

    def _op() -> str:
        model = raw.currentModel
        selected = model.Extension.SelectByID2(
            "", "EDGE",
            wx_mm / 1000.0, wy_mm / 1000.0, wz_mm / 1000.0,
            False, 0, None, 0,
        )
        if not selected:
            raise RuntimeError(f"Failed to select edge at ({wx_mm}, {wy_mm}, {wz_mm})mm")
        fm = model.FeatureManager
        feature = fm.FeatureChamfer(
            1, distance_mm / 1000.0, distance_mm / 1000.0,
            0, 0, False, False, False, False,
        )
        if not feature:
            raise RuntimeError("FeatureChamfer returned None")
        return str(feature.Name)

    result = raw._handle_com_operation("chamfer_edge", _op)
    if not result.is_success:
        print(f"[warn] Chamfer skipped: {result.error}")


async def ensure_saved_part_active(adapter: Any, model_path: Path, label: str) -> None:
    require(await adapter.open_model(str(model_path)), label)


async def build_part() -> None:
    config = load_config()
    adapter = await create_adapter(config)
    await adapter.connect()
    try:
        require(await adapter.create_part(name="yoke_male_from_prompt"), "create_part")

        # ── Sketch1: Base cylinder ∅38.10mm on Top plane (XZ at Y=0) ─────────────
        # Extruded 47.625mm upward (+Y). The cylinder forms the yoke body and arm zone.
        # Arm zone: Y=0..29.145mm (the U-fork). Shaft zone: Y=29.145..47.625mm.
        require(await adapter.create_sketch("Top"), "create_sketch BaseCircle")
        require(await adapter.add_circle(0, 0, 19.050), "base circle dia=38.10mm")
        require(await adapter.exit_sketch(), "exit_sketch BaseCircle")

        require(
            await adapter.create_extrusion(
                ExtrusionParameters(depth=47.625)
            ),
            "BaseExtrude 47.625mm",
        )

        # ── Sketch2: U-slot cut on Front plane (XY at Z=0) ──────────────────────
        # Closed loop of 5 lines + 3 arcs. Removes the arm-strip regions (X>9.525
        # and X<-9.525) from the cylinder below Y=29.210, leaving the centre
        # X=±9.525 as the arm material with rounded arm tips.
        # Radial dimensions required to fully define the sketch for FeatureCut.
        # Arc CCW direction (Dir=1): confirmed by angle traversal:
        #   right arm: 90°→180° (top→left, short arc)
        #   U-bottom:  180°→270°→0° (left→bottom(0,0)→right, 180° arc)
        #   left arm:  0°→90° (right→top, short arc)
        require(await adapter.create_sketch("Front"), "create_sketch USlot")
        bottom_edge = require(
            await adapter.add_line(-19.050, -1.366, 19.050, -1.366), "bottom edge"
        )
        right_outer = require(await adapter.add_line(19.050, -1.366, 19.050, 29.210), "right outer")
        arc1 = require(
            await adapter.add_arc(19.050, 19.685, 19.050, 29.210, 9.525, 19.685),
            "right arm tip arc R9.525",
        )
        right_inner = require(
            await adapter.add_line(9.525, 19.685, 9.525, 9.525), "right inner wall"
        )
        arc2 = require(
            await adapter.add_arc(0, 9.525, -9.525, 9.525, 9.525, 9.525),
            "U-slot bottom arc R9.525",
        )
        left_inner = require(
            await adapter.add_line(-9.525, 9.525, -9.525, 19.685), "left inner wall"
        )
        arc3 = require(
            await adapter.add_arc(-19.050, 19.685, -9.525, 19.685, -19.050, 29.210),
            "left arm tip arc R9.525",
        )
        left_outer = require(await adapter.add_line(-19.050, 29.210, -19.050, -1.366), "left outer")
        xaxis = require(
            await adapter.add_centerline(-19.050, 0, 19.050, 0), "X-axis centerline"
        )
        require(
            await adapter.add_sketch_dimension(arc1.data, None, "radial", 9.525),
            "dim R9.525 right arm",
        )
        require(
            await adapter.add_sketch_dimension(arc2.data, None, "radial", 9.525),
            "dim R9.525 U-bottom",
        )
        require(
            await adapter.add_sketch_dimension(arc3.data, None, "radial", 9.525),
            "dim R9.525 left arm",
        )
        require(
            await adapter.add_sketch_constraint(right_outer.data, None, "fix"),
            "fix right outer wall",
        )
        require(
            await adapter.add_sketch_constraint(left_outer.data, None, "fix"),
            "fix left outer wall",
        )
        require(
            await adapter.add_sketch_constraint(arc2.data, xaxis.data, "tangent"),
            "arc2 tangent to X-axis (bottom at origin)",
        )
        require(
            await adapter.add_sketch_dimension(bottom_edge.data, None, "linear", 38.100),
            "dim bottom edge width 38.100mm",
        )
        require(
            await adapter.add_sketch_dimension(right_inner.data, None, "linear", 10.160),
            "dim right inner wall height 10.160mm",
        )
        require(
            await adapter.add_sketch_dimension(left_inner.data, None, "linear", 10.160),
            "dim left inner wall height 10.160mm",
        )
        require(await adapter.exit_sketch(), "exit_sketch USlot")
        require(
            await adapter.create_cut_extrude(
                ExtrusionParameters(depth=0.0, end_condition="ThroughAll", both_directions=True)
            ),
            "USlot cut through-all-both",
        )

        # ── Sketch8: Arm gap rectangular slot on Right plane (YZ at X=0) ─────────
        # Right-plane coords: sketch_x=world_Z, sketch_y=world_Y.
        # Removes material at Z:±10.160mm, Y:-7.455..29.145mm through-all in X.
        # This creates the two yoke arms (front arm Z>10.160, back arm Z<-10.160).
        require(await adapter.create_sketch("Right"), "create_sketch ArmGap")
        require(await adapter.add_line(-10.160, -7.455, 10.160, -7.455), "gap bottom")
        require(await adapter.add_line(10.160, -7.455, 10.160, 29.145), "gap right")
        require(await adapter.add_line(10.160, 29.145, -10.160, 29.145), "gap top")
        require(await adapter.add_line(-10.160, 29.145, -10.160, -7.455), "gap left")
        require(await adapter.exit_sketch(), "exit_sketch ArmGap")
        require(
            await adapter.create_cut_extrude(
                ExtrusionParameters(depth=0.0, end_condition="ThroughAll", both_directions=True)
            ),
            "ArmGap cut through-all-both",
        )

        # ── Sketch11: Pin bore ∅9.525mm on Front plane (XY at Z=0) ──────────────
        # Front-plane coords: sketch_x=world_X, sketch_y=world_Y.
        # Circle at (0, 9.525): the cross-pin hole at Y=9.525mm (arm height).
        # Through-all in Z passes through both front and back arms.
        require(await adapter.create_sketch("Front"), "create_sketch PinBore")
        require(await adapter.add_circle(0, 9.525, 4.7625), "pin bore dia=9.525mm")
        require(await adapter.exit_sketch(), "exit_sketch PinBore")
        require(
            await adapter.create_cut_extrude(
                ExtrusionParameters(depth=0.0, end_condition="ThroughAll", both_directions=True)
            ),
            "PinBore cut through-all-both",
        )

        # ── Sketch12: Stub shaft ∅12.70mm on Top plane ────────────────────────────
        # The target model starts Boss-Extrude2 from Face<1> (top of base cylinder
        # at Y=47.625mm) and extrudes 19.05mm. We achieve identical geometry by
        # sketching on the Top plane and extruding 66.675mm: the first 47.625mm of
        # the r=6.350mm column merges invisibly into the base cylinder (r=19.050mm);
        # only the top 19.05mm (Y=47.625..66.675mm) protrudes as the stub shaft.
        # This avoids face-selection issues with the parametric base-cylinder face.
        require(await adapter.create_sketch("Top"), "create_sketch StubShaft")
        require(await adapter.add_circle(0, 0, 6.350), "stub shaft dia=12.70mm")
        require(await adapter.exit_sketch(), "exit_sketch StubShaft")

        require(
            await adapter.create_extrusion(
                ExtrusionParameters(depth=66.675)
            ),
            "StubExtrude 66.675mm from Top (net protrusion 19.05mm above base)",
        )

        # ── Sketch13: Stub bore D-profile on Face<1> (top of stub shaft) ───────────
        # Sketch on the top face of the stub shaft at Y=66.675mm. ThroughAll Direction 1
        # cuts downward (-Y) through the 19.05mm stub. No both_directions needed.
        # D-profile = long CCW arc (≈277°, around left side) + chord line closing it.
        # Arc: center=(0,0) r=6.350, CCW from (4.763,4.200) to (4.763,-4.200).
        # Chord: closes from arc-end back to arc-start at X=4.763.
        # No radial dimension — coordinates already approximate r=6.350; adding a
        # driven dimension shifts endpoints and opens the closed profile.
        create_sketch_on_face_y(adapter, 66.675)
        require(
            await adapter.add_arc(0, 0, 4.763, 4.200, 4.763, -4.200),
            "D-bore arc CCW long",
        )
        require(await adapter.add_line(4.763, -4.200, 4.763, 4.200), "keyway chord")
        require(await adapter.exit_sketch(), "exit_sketch StubBore")

        require(
            await adapter.create_cut_extrude(
                ExtrusionParameters(depth=0.0, end_condition="ThroughAll", both_directions=False)
            ),
            "StubBore cut ThroughAll into stub",
        )

        # ── Save and export ───────────────────────────────────────────────────────
        require(await adapter.save_file(str(OUTPUT_PART)), "save_file")
        await ensure_saved_part_active(adapter, OUTPUT_PART, "reopen for screenshot")
        require(
            await adapter.export_image(
                {
                    "file_path": str(OUTPUT_IMAGE),
                    "format_type": "png",
                    "width": 1600,
                    "height": 1000,
                    "view_orientation": "isometric",
                }
            ),
            "export_image",
        )

        if ANSWER_KEY.exists():
            require(await adapter.open_model(str(ANSWER_KEY)), "open answer key")
            require(
                await adapter.export_image(
                    {
                        "file_path": str(ANSWER_KEY_IMAGE),
                        "format_type": "png",
                        "width": 1600,
                        "height": 1000,
                        "view_orientation": "isometric",
                    }
                ),
                "export_image answer key",
            )

        await ensure_saved_part_active(adapter, OUTPUT_PART, "restore tutorial part")
    finally:
        await adapter.disconnect()


if __name__ == "__main__":
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    asyncio.run(build_part())
    print(OUTPUT_PART)
    print(OUTPUT_IMAGE)
    print(ANSWER_KEY_IMAGE)
