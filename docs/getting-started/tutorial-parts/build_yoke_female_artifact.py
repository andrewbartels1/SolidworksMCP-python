from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from solidworks_mcp.adapters import create_adapter
from solidworks_mcp.adapters.base import ExtrusionParameters
from solidworks_mcp.config import load_config

ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = ROOT / "docs" / "getting-started" / "tutorial-parts"
OUTPUT_PART = ARTIFACT_DIR / "yoke_female_from_prompt.SLDPRT"
OUTPUT_IMAGE = ARTIFACT_DIR / "yoke_female_from_prompt_isometric.png"
ANSWER_KEY = Path(
    r"C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\U-Joint\Yoke_female.sldprt"
)
ANSWER_KEY_IMAGE = ARTIFACT_DIR / "answer_key_yoke_female_isometric.png"


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
        require(await adapter.create_part(name="yoke_female_from_prompt"), "create_part")

        # ── Sketch 1: U-shaped yoke profile on Front plane ───────────────────────
        # Yoke_female geometry is identical to Yoke_male (same body, arms, bore,
        # flange, and holes). The distinction between male/female is assembly
        # orientation, not part shape.
        #
        # Dimensions from the SW 2026 sample model:
        #   Body: 80mm wide × 8mm tall (Y=0..8)
        #   Arms: 15mm wide each, 68mm total height (Y=0..68)
        #   Gap between arms: 50mm (X=-25 to X=25)
        require(await adapter.create_sketch("Front"), "create_sketch Sketch1")
        require(await adapter.add_line(-40, 0, 40, 0), "bottom rail")
        require(await adapter.add_line(40, 0, 40, 68), "right outer up")
        require(await adapter.add_line(40, 68, 25, 68), "right arm top")
        require(await adapter.add_line(25, 68, 25, 8), "right arm inner down")
        require(await adapter.add_line(25, 8, -25, 8), "body top / U floor")
        require(await adapter.add_line(-25, 8, -25, 68), "left arm inner up")
        require(await adapter.add_line(-25, 68, -40, 68), "left arm top")
        require(await adapter.add_line(-40, 68, -40, 0), "left outer down")
        require(await adapter.exit_sketch(), "exit_sketch Sketch1")

        # ── BaseExtrude: 40mm mid-plane (yoke depth) ─────────────────────────────
        require(
            await adapter.create_extrusion(
                ExtrusionParameters(depth=40, both_directions=True)
            ),
            "BaseExtrude",
        )

        # ── Sketch 2: ∅8mm bore circle on Right plane ────────────────────────────
        # Right plane sketch coords: sketch_x = world Z, sketch_y = world Y.
        # Center: Y=38mm (arm mid-height), Z=0 (mid-depth).
        require(await adapter.create_sketch("Right"), "create_sketch CenterBore")
        require(await adapter.add_circle(0, 38, 4), "bore circle ∅8mm")
        require(await adapter.exit_sketch(), "exit_sketch CenterBore")

        create_through_all_cut(adapter)

        # ── Sketch 3: ∅60mm flange circle on Top plane ───────────────────────────
        # Top plane = XZ at Y=0 (body bottom). Extrude 3mm downward.
        require(await adapter.create_sketch("Top"), "create_sketch FlangeSketch")
        require(await adapter.add_circle(0, 0, 30), "flange circle ∅60mm")
        require(await adapter.exit_sketch(), "exit_sketch FlangeSketch")

        require(
            await adapter.create_extrusion(
                ExtrusionParameters(depth=3, reverse_direction=True)
            ),
            "FlangeExtrude 3mm down",
        )

        # ── Sketch 4: four ∅4.2mm holes on ∅50mm bolt circle (M4 clearance) ─────
        require(await adapter.create_sketch("Top"), "create_sketch FlangeHoles")
        require(await adapter.add_circle(25, 0, 2.1), "hole +X")
        require(await adapter.add_circle(-25, 0, 2.1), "hole -X")
        require(await adapter.add_circle(0, 25, 2.1), "hole +Z")
        require(await adapter.add_circle(0, -25, 2.1), "hole -Z")
        require(await adapter.exit_sketch(), "exit_sketch FlangeHoles")

        create_blind_cut(adapter, depth_mm=3.0)

        # ── FilletCorners: 1mm fillet on arm edges ────────────────────────────────
        # Edge selection for fillets requires picking specific edges by geometry;
        # use the `add_fillet` MCP tool in Claude Code after inspecting the model,
        # or call FeatureFillet3 directly via COM with the target edge references.

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
