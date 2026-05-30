from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from solidworks_mcp.adapters import create_adapter
from solidworks_mcp.adapters.base import ExtrusionParameters
from solidworks_mcp.config import load_config

ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = ROOT / "docs" / "getting-started" / "tutorial-parts"
OUTPUT_PART = ARTIFACT_DIR / "u_bracket_from_prompt.sldprt"
OUTPUT_IMAGE = ARTIFACT_DIR / "u_bracket_from_prompt_isometric.png"
ANSWER_KEY = Path(
    r"C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\U-Joint\bracket.sldprt"
)
ANSWER_KEY_IMAGE = ARTIFACT_DIR / "answer_key_bracket_isometric.png"


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


def create_cut_extrude_direct(adapter: Any) -> None:
    raw_adapter = unwrap_for_method(adapter, "currentModel")
    if raw_adapter is None or raw_adapter.currentModel is None:
        raise RuntimeError("Could not access raw adapter currentModel for cut fallback")

    model = raw_adapter.currentModel
    feature_manager = model.FeatureManager

    # Blind cut 10 mm from Sketch2 (not through-all).
    feature = feature_manager.FeatureCut3(
        True,
        False,
        False,
        0,
        0,
        0.01,
        0.0,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        False,
        False,
        True,
        False,
        False,
        False,
        0,
        0.0,
        False,
    )
    if not feature:
        # Some installs flip the sketch normal on face/offset-plane sketches.
        feature = feature_manager.FeatureCut3(
            True,
            False,
            True,
            0,
            0,
            0.01,
            0.0,
            False,
            False,
            False,
            False,
            0.0,
            0.0,
            False,
            False,
            False,
            False,
            False,
            False,
            True,
            False,
            False,
            False,
            0,
            0.0,
            False,
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
    config = load_config()
    adapter = await create_adapter(config)
    await adapter.connect()
    try:
        require(await adapter.create_part(name="u_bracket_from_prompt"), "create_part")

        # Rebuild the SolidWorks sample bracket from measured sketch coordinates.
        # Feature tree target: Sketch1 -> Base-Extrude-Thin -> Sketch2 -> Cut-Extrude1.
        # Units are mm, derived from the sample model currently shipped with SW 2026.

        require(await adapter.create_sketch("Front"), "create_sketch Sketch1")

        require(await adapter.add_line(0.0, 0.0, 0.0, 82.55), "right web")
        require(await adapter.add_line(0.0, 82.55, -57.15, 82.55), "top flange")
        require(await adapter.add_line(-77.216, 27.494, -44.45, 0.0), "angled tab")
        require(await adapter.add_line(-44.45, 0.0, 0.0, 0.0), "bottom rail")
        require(await adapter.exit_sketch(), "exit_sketch Sketch1")

        # Base-Extrude-Thin: mid-plane 38.1 mm depth, 6.35 mm thin-wall.
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
            "create Base-Extrude-Thin",
        )

        # Sketch2: place the hole on the top flange face (highlighted sample face).
        # Offset is 12.70 mm from the left edge, diameter is 12.70 mm.
        create_sketch_on_top_planar_face(adapter, "Sketch2")
        require(
            await adapter.add_centerline(0.0, 0.0, -57.15, 0.0),
            "Sketch2 flange reference centerline",
        )
        require(await adapter.add_circle(-44.45, 0.0, 6.35), "sample bracket hole")
        definition_check = require(
            await adapter.check_sketch_fully_defined("Sketch2"),
            "check_sketch_fully_defined Sketch2",
        )
        if isinstance(definition_check.data, dict):
            is_defined = definition_check.data.get("is_fully_defined")
            if is_defined is False:
                print(
                    f"WARNING: Sketch2 may not be fully defined: {definition_check.data}"
                )
        require(await adapter.exit_sketch(), "exit_sketch Sketch2")

        create_cut_extrude_direct(adapter)

        require(await adapter.save_file(str(OUTPUT_PART)), "save_file tutorial part")
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

        # Keep only the rebuilt bracket active at end of run.
        # close_all_docs_and_restore(adapter, OUTPUT_PART)
        await ensure_saved_part_active(adapter, OUTPUT_PART, "restore tutorial part")
    finally:
        await adapter.disconnect()


if __name__ == "__main__":
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    asyncio.run(build_part())
    print(OUTPUT_PART)
    print(OUTPUT_IMAGE)
    print(ANSWER_KEY_IMAGE)
