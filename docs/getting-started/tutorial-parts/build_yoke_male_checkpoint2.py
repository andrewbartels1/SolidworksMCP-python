"""Checkpoint: base extrude + Sketch2 U-slot cut with full dimension constraints.

Sketch2 profile on Front(XY) plane — closed loop of 5 lines + 3 arcs:
  Outer rect: X=±19.050, Y=-1.366 to 29.210 (38.100mm wide)
  U-slot inner walls: X=±9.525 (19.050mm slot opening)
  Arc centres: right arm=(19.050,19.685) r=9.525, U-bottom=(0,9.525) r=9.525,
               left arm=(-19.050,19.685) r=9.525
All arcs use CreateArc Dir=1 (CCW). Radial dimensions added to fully define sketch.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from solidworks_mcp.adapters import create_adapter
from solidworks_mcp.adapters.base import ExtrusionParameters
from solidworks_mcp.config import load_config

ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = ROOT / "docs" / "getting-started" / "tutorial-parts"
OUTPUT_PART = ARTIFACT_DIR / "yoke_male_checkpoint2.SLDPRT"
OUTPUT_IMAGE = ARTIFACT_DIR / "yoke_male_checkpoint2.png"


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


async def build_part() -> None:
    config = load_config()
    adapter = await create_adapter(config)
    await adapter.connect()
    try:
        require(await adapter.create_part(name="yoke_male_checkpoint2"), "create_part")

        # ── Step 1: Base cylinder ∅38.10mm on Top plane, 47.625mm ──────────────────
        require(await adapter.create_sketch("Top"), "create_sketch BaseCircle")
        require(await adapter.add_circle(0, 0, 19.050), "base circle r=19.050")
        require(await adapter.exit_sketch(), "exit_sketch BaseCircle")
        require(
            await adapter.create_extrusion(ExtrusionParameters(depth=47.625)),
            "BaseExtrude 47.625mm",
        )

        # ── Step 2: Sketch2 — U-slot cut on Front plane (XY at Z=0) ───────────────
        # Profile is a single closed loop: 5 lines + 3 arcs.
        # Removes the two arm-strip regions (X<-9.525 and X>9.525) from the cylinder
        # below Y=29.210, leaving the centre (X=±9.525) as the arm material.
        #
        # Arc convention: CreateArc Dir=1 = CCW when viewed from +Z (front).
        # Arc1 right arm tip: CCW from 90°(top) to 180°(left) = 90° short arc ✓
        # Arc2 U-slot bottom: CCW from 180°(left) through 270°(bottom) to 0°(right)
        #                     = 180° arc passing through (0, 0) ✓
        # Arc3 left arm tip: CCW from 0°(right) to 90°(top) = 90° short arc ✓
        require(await adapter.create_sketch("Front"), "create_sketch USlot")

        # Draw the closed profile
        require(await adapter.add_line(-19.050, -1.366, 19.050, -1.366), "bottom edge")
        require(await adapter.add_line(19.050, -1.366, 19.050, 29.210), "right outer")
        arc1 = require(
            await adapter.add_arc(19.050, 19.685, 19.050, 29.210, 9.525, 19.685),
            "right arm tip arc",
        )
        require(await adapter.add_line(9.525, 19.685, 9.525, 9.525), "right inner wall")
        arc2 = require(
            await adapter.add_arc(0, 9.525, -9.525, 9.525, 9.525, 9.525),
            "U-slot bottom arc",
        )
        require(await adapter.add_line(-9.525, 9.525, -9.525, 19.685), "left inner wall")
        arc3 = require(
            await adapter.add_arc(-19.050, 19.685, -9.525, 19.685, -19.050, 29.210),
            "left arm tip arc",
        )
        require(await adapter.add_line(-19.050, 29.210, -19.050, -1.366), "left outer")

        # Add radial dimensions to fully define each arc (R=9.525mm)
        require(
            await adapter.add_sketch_dimension(arc1.data, None, "radial", 9.525),
            "dim R9.525 right arm arc",
        )
        require(
            await adapter.add_sketch_dimension(arc2.data, None, "radial", 9.525),
            "dim R9.525 U-bottom arc",
        )
        require(
            await adapter.add_sketch_dimension(arc3.data, None, "radial", 9.525),
            "dim R9.525 left arm arc",
        )

        require(await adapter.exit_sketch(), "exit_sketch USlot")
        create_through_all_cut(adapter)

        # ── Save and export ────────────────────────────────────────────────────────
        require(await adapter.save_file(str(OUTPUT_PART)), "save_file")
        require(await adapter.open_model(str(OUTPUT_PART)), "reopen for screenshot")
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
    finally:
        await adapter.disconnect()


if __name__ == "__main__":
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    asyncio.run(build_part())
    print(OUTPUT_PART)
    print(OUTPUT_IMAGE)
