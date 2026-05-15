#!/usr/bin/env python
r"""Direct U-bracket builder artifact matching sample bracket 1:1.

This script demonstrates the complete, deterministic artifact build for a U-bracket
using the SolidWorks MCP adapter directly, without relying on planner output.

Matches reference model:
  C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\U-Joint\bracket.sldprt

Output files saved to:
  docs/getting-started/tutorial-parts/u_bracket_from_prompt.*
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

# Add parent paths to sys.path for import resolution
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from solidworks_mcp.adapters import create_adapter
from solidworks_mcp.adapters.base import ExtrusionParameters
from solidworks_mcp.config import load_config

ARTIFACT_DIR = ROOT / "docs" / "getting-started" / "tutorial-parts"
OUTPUT_PART = ARTIFACT_DIR / "u_bracket_from_prompt.sldprt"
OUTPUT_IMAGE = ARTIFACT_DIR / "u_bracket_from_prompt_isometric.png"
ANSWER_KEY = Path(
    r"C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\U-Joint\bracket.sldprt"
)
ANSWER_KEY_IMAGE = ARTIFACT_DIR / "answer_key_bracket_isometric.png"


def require(result: Any, label: str) -> Any:
    """Require successful result or raise."""
    if not result.is_success:
        raise RuntimeError(f"{label} failed: {result.error}")
    return result


def unwrap_for_method(adapter: Any, method_name: str) -> Any | None:
    """Unwrap adapter layers to find underlying COM object."""
    current: Any | None = adapter
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if hasattr(current, method_name):
            return current
        current = getattr(current, "adapter", None)
    return None


def create_cut_extrude_direct(adapter: Any) -> None:
    """Create cut extrude using direct COM when adapter abstraction is insufficient."""
    raw_adapter = unwrap_for_method(adapter, "currentModel")
    if raw_adapter is None or raw_adapter.currentModel is None:
        raise RuntimeError("Could not access raw adapter currentModel for cut fallback")

    model = raw_adapter.currentModel
    feature_manager = model.FeatureManager

    # Blind cut 10 mm from Sketch2 (not through-all).
    feature = feature_manager.FeatureCut3(
        True,   # Update part views
        False,  # Do not reverse cut direction
        False,  # Not through all
        0,      # Body cut scope
        0,      # Skip up to n surfaces
        0.01,   # Depth in meters (10mm = 0.01m)
        0.0,    # Draft angle
        False,  # Taper to next
        False,  # Remove faces
        False,  # Offset status
        False,  # Geometry pattern
        0.0,    # Offset distance
        0.0,    # Draft distance
        False,  # Offset second direction
        False,  # Reverse second direction
        False,  # Vertex opposite side
        False,  # Preserve faces
        False,  # Keep facets together
        False,  # Unique entity
        True,   # Use form
        False,  # Follow surface
        False,  # Trim surface
        False,  # Smooth surface
        0,      # Surface smoothness
        0.0,    # Surface radius
        False,  # Keep surface together
    )
    if not feature:
        # Some installs flip the sketch normal on face/offset-plane sketches.
        feature = feature_manager.FeatureCut3(
            True, False, True, 0, 0, 0.01, 0.0, False, False, False, False, 0.0, 0.0,
            False, False, False, False, False, False, True, False, False, False, 0, 0.0, False,
        )
    if not feature:
        raise RuntimeError("Direct FeatureCut3 fallback returned no feature")


def create_sketch_on_top_planar_face(adapter: Any, sketch_name: str) -> None:
    """Start Sketch2 on a deterministic plane aligned to the top flange face.

    On some COM bindings face-picking is unreliable, so this creates an offset
    plane from Top Plane at the measured top-face elevation (88.90 mm), then
    starts the sketch on that plane.
    """
    raw_adapter = unwrap_for_method(adapter, "currentModel")
    if raw_adapter is None or raw_adapter.currentModel is None:
        raise RuntimeError("Could not access raw adapter currentModel for face sketch")

    model = raw_adapter.currentModel

    top_plane = model.FeatureByName("Top Plane") or model.FeatureByName("Planta")
    if not top_plane:
        raise RuntimeError("Failed to find Top Plane for Sketch2 offset plane")

    model.ClearSelection2(True)
    if not top_plane.Select2(False, 0):
        raise RuntimeError("Failed to select Top Plane for Sketch2 offset plane")

    # swRefPlaneReferenceConstraint_Distance = 8
    offset_feature = model.FeatureManager.InsertRefPlane(
        8, 88.9 / 1000.0, 0, 0.0, 0, 0.0
    )
    if not offset_feature:
        raise RuntimeError("Failed to create top-face offset plane for Sketch2")

    model.ClearSelection2(True)
    if not offset_feature.Select2(False, 0):
        raise RuntimeError("Failed to select Sketch2 offset plane")

    sketch_manager = model.SketchManager
    try:
        sketch = sketch_manager.InsertSketch(True)
    except Exception:
        sketch = sketch_manager.InsertSketch()

    # Some COM variants return bool for InsertSketch; add_* operations only
    # require currentSketchManager, so keep a nullable currentSketch here.
    if isinstance(sketch, bool):
        sketch = None

    if hasattr(raw_adapter, "_reset_sketch_entity_registry"):
        raw_adapter._reset_sketch_entity_registry()

    raw_adapter.currentSketchManager = sketch_manager
    raw_adapter.currentSketch = sketch
    raw_adapter._sketch_count += 1
    raw_adapter._last_sketch_name = sketch_name


def close_all_docs_and_restore(adapter: Any, model_path: Path) -> None:
    """Close open docs and restore the saved tutorial part as active."""
    raw_adapter = unwrap_for_method(adapter, "swApp")
    if raw_adapter is None or raw_adapter.swApp is None:
        raise RuntimeError("Could not access raw adapter swApp for document cleanup")

    app = raw_adapter.swApp
    # Prevent stale PartXXX windows from remaining open between runs.
    try:
        app.CloseAllDocuments(True)
    except Exception:
        # Fallback: best effort close-all by title/path for older COM variants.
        app.CloseDoc(str(model_path))


async def ensure_saved_part_active(adapter: Any, model_path: Path, label: str) -> None:
    """Open the saved part and keep it as adapter/current active model."""
    require(await adapter.open_model(str(model_path)), label)


async def build_part() -> None:
    """Build the U-bracket from scratch matching sample exactly."""
    config = load_config()
    adapter = await create_adapter(config)
    await adapter.connect()
    try:
        # Step 1: Create part
        require(await adapter.create_part(name="u_bracket_from_prompt"), "create_part")
        print("✓ Created part")

        # Step 2: Create Sketch1 on Front plane
        require(await adapter.create_sketch("Front"), "create_sketch Sketch1")
        print("✓ Created Sketch1 on Front plane")

        # Step 3: Draw U-bracket profile (5 connected lines)
        # Sketch coordinates from sample bracket feature tree
        require(await adapter.add_line(0.0, 0.0, 0.0, 82.55), "add_line: right web")
        require(await adapter.add_line(0.0, 82.55, -57.15, 82.55), "add_line: top flange")
        require(
            await adapter.add_line(-57.15, 82.55, -77.216, 27.494),
            "add_line: diagonal transition",
        )
        require(await adapter.add_line(-77.216, 27.494, -44.45, 0.0), "add_line: angled tab")
        require(await adapter.add_line(-44.45, 0.0, 0.0, 0.0), "add_line: bottom rail")
        print("✓ Drew U-profile outline (5 lines)")

        # Step 4: Exit sketch and create Base-Extrude-Thin
        require(await adapter.exit_sketch(), "exit_sketch Sketch1")
        require(
            await adapter.create_extrusion(
                ExtrusionParameters(
                    depth=38.1,
                    thin_feature=True,
                    thin_thickness=6.35,
                    both_directions=True,
                    auto_fillet_corners=True,
                    fillet_corners_radius=3.175,
                )
            ),
            "create_extrusion: Base-Extrude-Thin",
        )
        print("✓ Created Base-Extrude-Thin (mid-plane 38.1mm, 6.35mm wall)")

        # Step 5: Create Sketch2 on top planar face via offset plane
        create_sketch_on_top_planar_face(adapter, "Sketch2")
        print("✓ Created Sketch2 on top flange offset plane")

        # Step 6: Draw hole geometry in Sketch2
        # Add centerline reference
        require(
            await adapter.add_centerline(0.0, 0.0, -57.15, 0.0),
            "add_centerline: flange reference",
        )
        # Add hole circle: center at (-44.45, 0), diameter 12.70mm (radius 6.35mm)
        require(
            await adapter.add_circle(-44.45, 0.0, 6.35),
            "add_circle: sample bracket hole",
        )
        print("✓ Drew hole geometry (∅12.70mm at (-44.45, 0))")

        # Step 7: Validate Sketch2 is fully defined
        definition_check = require(
            await adapter.check_sketch_fully_defined("Sketch2"),
            "check_sketch_fully_defined Sketch2",
        )
        if isinstance(definition_check.data, dict):
            is_defined = definition_check.data.get("is_fully_defined")
            if is_defined is False:
                print(
                    f"⚠️  WARNING: Sketch2 may not be fully defined: {definition_check.data}"
                )
            else:
                print("✓ Sketch2 is fully defined")

        # Step 8: Exit sketch and create cut
        require(await adapter.exit_sketch(), "exit_sketch Sketch2")
        create_cut_extrude_direct(adapter)
        print("✓ Created Cut-Extrude1 (10mm blind)")

        # Step 9: Save part
        require(await adapter.save_file(str(OUTPUT_PART)), "save_file tutorial part")
        print(f"✓ Saved part to {OUTPUT_PART}")

        # Step 10: Activate and export tutorial part
        await ensure_saved_part_active(
            adapter, OUTPUT_PART, "activate tutorial part before screenshot"
        )
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
            "export_image tutorial part",
        )
        print(f"✓ Exported tutorial isometric to {OUTPUT_IMAGE}")

        # Step 11: Export reference answer key if available
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
            print(f"✓ Exported answer key isometric to {ANSWER_KEY_IMAGE}")

        # Step 12: Keep only the rebuilt bracket active at end of run
        close_all_docs_and_restore(adapter, OUTPUT_PART)
        await ensure_saved_part_active(adapter, OUTPUT_PART, "restore tutorial part")
        print("✓ Cleanup complete; rebuilt bracket is active")

        print("\n" + "=" * 60)
        print("BUILD SUCCESSFUL: U-bracket artifact created")
        print("=" * 60)
        print(f"Part:   {OUTPUT_PART}")
        print(f"Image:  {OUTPUT_IMAGE}")
        if ANSWER_KEY.exists():
            print(f"Comparison: {ANSWER_KEY_IMAGE}")

    finally:
        await adapter.disconnect()


if __name__ == "__main__":
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        asyncio.run(build_part())
    except Exception as exc:
        print(f"\n❌ BUILD FAILED: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
