from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any


from solidworks_mcp.adapters import create_adapter
from solidworks_mcp.adapters.base import ExtrusionParameters
from solidworks_mcp.config import load_config

ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = ROOT / "docs" / "getting-started" / "tutorial-parts"
OUTPUT_PART = ARTIFACT_DIR / "yoke_male_v2_from_prompt.SLDPRT"
OUTPUT_IMAGE = ARTIFACT_DIR / "yoke_male_v2_from_prompt_isometric.png"
ANSWER_KEY = Path(
    r"C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\U-Joint\Yoke_male.sldprt"
)
ANSWER_KEY_IMAGE = ARTIFACT_DIR / "answer_key_yoke_male_isometric.png"

# Dimensions reverse-engineered from Yoke_male.sldprt via read_yoke_geometry.py:
#
#   Base cylinder:  dia=38.10mm (r=19.050), height=47.625mm, Top(XZ) plane at Y=0
#   U-slot profile: Front(XY) plane — centerline (0,0)→(0,23.743), 5 lines + 3 arcs
#   Arm gap (slot): Right(YZ) plane — rect Z:±10.160mm, Y:-7.455..29.145mm, through-all
#   Pin bore:       Front(XY) plane — dia=9.525mm (r=4.7625), center (0,9.525), through-all
#   Stub shaft:     Face at Y=47.625mm — dia=12.70mm (r=6.350), extrude 19.050mm
#   Stub bore:      Face at Y=66.675mm — dia=12.70mm + keyway line (-4.762,4.200)→(-4.763,-4.200)


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
    # FeatureCut3 26-param SW 2022+ signature: Sd=True (solid), FlipSide=False,
    # Dir=True (through-all both), T1=T2=1 (swEndCondThroughAll), depth=0
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
        raise RuntimeError("FeatureCut3 through-all-both returned no feature")


async def build_part() -> None:
    config = load_config()
    adapter = await create_adapter(config)
    await adapter.connect()
    try:
        require(await adapter.create_part(name="yoke_male_v2_from_prompt"), "create_part")

        # ── Sketch1: Base cylinder ∅38.10mm on Top plane (XZ at Y=0) ─────────────
        # Extruded 47.625mm upward (+Y). Forms the yoke body, arms, and root of stub.
        require(await adapter.create_sketch("Top"), "create_sketch BaseCircle")
        require(await adapter.add_circle(0, 0, 19.050), "base circle r=19.050mm")
        require(await adapter.exit_sketch(), "exit_sketch BaseCircle")

        require(
            await adapter.create_extrusion(ExtrusionParameters(depth=47.625)),
            "Base-Extrude 47.625mm",
        )

        # ── Sketch2: U-slot profile on Front plane (XY at Z=0) ───────────────────
        # Construction centerline from origin to Y=23.743mm (mid-arm height).
        # Closed loop of 5 lines + 3 arcs defines the U-fork opening.
        # Cut through-all in both directions (Z+ and Z-).
        require(await adapter.create_sketch("Front"), "create_sketch USlot")
        require(
            await adapter.add_centerline(0, 0, 0, 23.743),
            "centerline origin→arm mid",
        )
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

        # ── Sketch8: Arm gap on Right plane (YZ at X=0) ──────────────────────────
        # Right-plane coords: sketch_x=world_Z, sketch_y=world_Y.
        # Rectangle Z:±10.160mm, Y:-7.455..29.145mm, cut through-all in X.
        # Leaves two yoke arms (front arm Z>10.160, back arm Z<-10.160).
        require(await adapter.create_sketch("Right"), "create_sketch ArmGap")
        require(await adapter.add_line(-10.160, -7.455, 10.160, -7.455), "gap bottom")
        require(await adapter.add_line(10.160, -7.455, 10.160, 29.145), "gap right")
        require(await adapter.add_line(10.160, 29.145, -10.160, 29.145), "gap top")
        require(await adapter.add_line(-10.160, 29.145, -10.160, -7.455), "gap left")
        require(await adapter.exit_sketch(), "exit_sketch ArmGap")
        create_through_all_cut(adapter)

        # ── Sketch11: Pin bore ∅9.525mm on Front plane (XY at Z=0) ───────────────
        # Circle center (0, 9.525) = arm centerline height. Through-all in Z.
        require(await adapter.create_sketch("Front"), "create_sketch PinBore")
        require(await adapter.add_circle(0, 9.525, 4.7625), "pin bore r=4.7625mm")
        require(await adapter.exit_sketch(), "exit_sketch PinBore")
        create_through_all_cut(adapter)

        # ── Sketch12: Stub shaft ∅12.70mm on Top plane ───────────────────────────
        # Sketching on Top(XZ) at Y=0 and extruding 66.675mm. SW merges the
        # ∅12.70mm cylinder with the existing ∅38.10mm cylinder below Y=47.625mm;
        # only the portion Y=47.625..66.675mm (19.05mm) adds visible new material.
        require(await adapter.create_sketch("Top"), "create_sketch StubShaft")
        require(await adapter.add_circle(0, 0, 6.350), "stub shaft r=6.350mm")
        require(await adapter.exit_sketch(), "exit_sketch StubShaft")
        require(
            await adapter.create_extrusion(ExtrusionParameters(depth=66.675)),
            "Boss-Extrude1 to Y=66.675mm",
        )

        # ── Sketch13: Stub bore ∅12.70mm on Top plane ────────────────────────────
        # Full-circle bore removes the stub shaft interior through-all.
        # The answer-key keyway chord (X=-4.7625mm flat) requires either a
        # blind cut from the top face or D-shape contour selection — both
        # require face-based sketching not yet supported via late-bound COM.
        require(await adapter.create_sketch("Top"), "create_sketch StubBore")
        require(await adapter.add_circle(0, 0, 6.350), "stub bore r=6.350mm")
        require(await adapter.exit_sketch(), "exit_sketch StubBore")
        create_through_all_cut(adapter)

        # ── Save and export ───────────────────────────────────────────────────────
        require(await adapter.save_file(str(OUTPUT_PART)), "save_file")
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
            "export_image v2",
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

    finally:
        await adapter.disconnect()


if __name__ == "__main__":
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    asyncio.run(build_part())
    print(OUTPUT_PART)
    print(OUTPUT_IMAGE)
    print(ANSWER_KEY_IMAGE)
