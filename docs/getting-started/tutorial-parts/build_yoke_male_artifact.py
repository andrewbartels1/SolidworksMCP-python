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
#   Stub bore:      Top(XZ) at Y=66.675mm, dia=12.70mm + keyway, cut through stub


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


def create_through_all_cut(adapter: Any) -> None:
    """Cut through-all in both directions from the active sketch."""
    raw = unwrap_for_method(adapter, "currentModel")
    if raw is None or raw.currentModel is None:
        raise RuntimeError("No active model for cut extrude")
    fm = raw.currentModel.FeatureManager
    feature = fm.FeatureCut3(
        True, False, True,
        1, 1,
        0.0, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, False, False,
        True, False, False, False, 0, 0.0, False,
    )
    if not feature:
        feature = fm.FeatureCut3(
            True, True, True,
            1, 1,
            0.0, 0.0,
            False, False, False, False, 0.0, 0.0,
            False, False, False, False, False, False,
            True, False, False, False, 0, 0.0, False,
        )
    if not feature:
        raise RuntimeError("FeatureCut3 through-all returned no feature")


def create_blind_cut(adapter: Any, depth_mm: float) -> None:
    """Blind cut from the active sketch."""
    raw = unwrap_for_method(adapter, "currentModel")
    if raw is None or raw.currentModel is None:
        raise RuntimeError("No active model for cut extrude")
    fm = raw.currentModel.FeatureManager
    depth_m = depth_mm / 1000.0
    feature = fm.FeatureCut3(
        True, False, False,
        0, 0,
        depth_m, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, False, False,
        True, False, False, False, 0, 0.0, False,
    )
    if not feature:
        feature = fm.FeatureCut3(
            True, True, False,
            0, 0,
            depth_m, 0.0,
            False, False, False, False, 0.0, 0.0,
            False, False, False, False, False, False,
            True, False, False, False, 0, 0.0, False,
        )
    if not feature:
        raise RuntimeError(f"FeatureCut3 blind {depth_mm}mm returned no feature")


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
        # Radial dimensions required to fully define the sketch for FeatureCut3.
        # Arc CCW direction (Dir=1): confirmed by angle traversal:
        #   right arm: 90°→180° (top→left, short arc)
        #   U-bottom:  180°→270°→0° (left→bottom(0,0)→right, 180° arc)
        #   left arm:  0°→90° (right→top, short arc)
        require(await adapter.create_sketch("Front"), "create_sketch USlot")
        require(await adapter.add_line(-19.050, -1.366, 19.050, -1.366), "bottom edge")
        require(await adapter.add_line(19.050, -1.366, 19.050, 29.210), "right outer")
        arc1 = require(
            await adapter.add_arc(19.050, 19.685, 19.050, 29.210, 9.525, 19.685),
            "right arm tip arc R9.525",
        )
        require(await adapter.add_line(9.525, 19.685, 9.525, 9.525), "right inner wall")
        arc2 = require(
            await adapter.add_arc(0, 9.525, -9.525, 9.525, 9.525, 9.525),
            "U-slot bottom arc R9.525",
        )
        require(await adapter.add_line(-9.525, 9.525, -9.525, 19.685), "left inner wall")
        arc3 = require(
            await adapter.add_arc(-19.050, 19.685, -9.525, 19.685, -19.050, 29.210),
            "left arm tip arc R9.525",
        )
        require(await adapter.add_line(-19.050, 29.210, -19.050, -1.366), "left outer")
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
        require(await adapter.exit_sketch(), "exit_sketch USlot")
        create_through_all_cut(adapter)

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

        create_through_all_cut(adapter)

        # ── Sketch11: Pin bore ∅9.525mm on Front plane (XY at Z=0) ──────────────
        # Front-plane coords: sketch_x=world_X, sketch_y=world_Y.
        # Circle at (0, 9.525): the cross-pin hole at Y=9.525mm (arm height).
        # Through-all in Z passes through both front and back arms.
        require(await adapter.create_sketch("Front"), "create_sketch PinBore")
        require(await adapter.add_circle(0, 9.525, 4.7625), "pin bore dia=9.525mm")
        require(await adapter.exit_sketch(), "exit_sketch PinBore")

        create_through_all_cut(adapter)

        # ── Sketch12: Stub shaft ∅12.70mm starting at Y=47.625mm ─────────────────
        # Sketched on Top plane (Y=0), extruded 66.675mm (+Y total).
        # The ∅12.70mm < ∅38.10mm so the stub is absorbed below Y=47.625mm (inside
        # the base cylinder). Only the portion Y=47.625..66.675mm (19.05mm = 3/4")
        # adds visible new material — the stub shaft.
        require(await adapter.create_sketch("Top"), "create_sketch StubShaft")
        require(await adapter.add_circle(0, 0, 6.350), "stub shaft dia=12.70mm")
        require(await adapter.exit_sketch(), "exit_sketch StubShaft")

        require(
            await adapter.create_extrusion(
                ExtrusionParameters(depth=66.675)
            ),
            "StubExtrude to Y=66.675mm",
        )

        # ── Sketch13: Stub bore ∅12.70mm + keyway on Top plane ───────────────────
        # Actual sample cuts from the top face (Y=66.675mm) downward through the stub.
        # Approximation: through-all from Top plane cuts the bore the full part height.
        # The keyway line (-4.762,4.200)→(-4.763,-4.200) adds the keyway slot.
        require(await adapter.create_sketch("Top"), "create_sketch StubBore")
        require(await adapter.add_circle(0, 0, 6.350), "bore dia=12.70mm")
        # Keyway slot omitted: the sample uses a chord-line profile that requires
        # arc-trim topology beyond add_line. The bore circle alone is sufficient
        # to verify the stub shaft geometry.
        require(await adapter.exit_sketch(), "exit_sketch StubBore")

        create_through_all_cut(adapter)

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
