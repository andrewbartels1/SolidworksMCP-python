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

# Dimensions from read_yoke_female_geometry.py reverse-engineering of the SW 2026 sample:
#   Base cylinder:  dia=38.10mm (r=19.050), height=47.625mm, Top(XZ) plane at Y=0
#   U-slot profile: Front(XY) plane — same 3 arcs + 4 walls as yoke_male, but outer
#                   walls end at Y=0 (not Y=-1.366); bottom edge closes at Y=0
#   Arm gap (slot): Right(YZ) plane, Z:+-10.160mm, Y:0..29.145mm (starts at Y=0,
#                   not Y=-7.455mm like yoke_male)
#   Pin bore:       Front(XY) plane, dia=9.525mm (r=4.7625), center (0,9.525),
#                   through-all in Z (same as yoke_male)
#   Bolt holes:     4x dia=6.35mm (r=3.175) circles on top face at Y=47.625mm,
#                   bolt circle r=12.700mm, at 0/90/180/270 deg (world X/Z axes),
#                   cut ThroughAll into cylinder


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


def create_sketch_on_offset_plane(adapter: Any, offset_mm: float) -> str:
    """Create a reference plane at offset_mm above the Top plane, open a sketch on it.

    Uses InsertRefPlane (swRefPlaneReferenceConstraints_Distance=8) which is more
    reliable than coordinate-based face selection after parametric cuts have been applied.
    Returns the offset plane feature name so it can be hidden later.
    """
    raw = unwrap_for_method(adapter, "_handle_com_operation")
    if raw is None or raw.currentModel is None:
        raise RuntimeError("No active model for offset-plane sketch")

    def _op() -> str:
        from solidworks_mcp.adapters import sw_type_info
        model = raw.currentModel
        sw_type_info.flag_doc(model, 1)

        # Find the Top Plane feature by name (try both English and Spanish/localised)
        top_plane = None
        for name in ("Top Plane", "Top", "Planta", "Plano Superior"):
            try:
                top_plane = model.FeatureByName(name)
                if top_plane is not None:
                    break
            except Exception:
                pass
        if top_plane is None:
            raise RuntimeError("Top plane feature not found")

        model.ClearSelection2(True)
        sw_type_info.flag_methods(top_plane, "IFeature")
        if not top_plane.Select2(False, 0):
            raise RuntimeError("Failed to select Top Plane for offset reference")

        # swRefPlaneReferenceConstraints_Distance = 8
        offset_m = offset_mm / 1000.0
        plane_feat = model.FeatureManager.InsertRefPlane(8, offset_m, 0, 0.0, 0, 0.0)
        if not plane_feat:
            raise RuntimeError(f"InsertRefPlane at {offset_mm}mm returned None")

        sw_type_info.flag_methods(plane_feat, "IFeature")
        plane_name = str(plane_feat.Name)

        model.ClearSelection2(True)
        if not plane_feat.Select2(False, 0):
            raise RuntimeError(f"Failed to select offset plane '{plane_name}'")

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

    result = raw._handle_com_operation(f"create_sketch_on_offset_{offset_mm}", _op)
    if not result.is_success:
        raise RuntimeError(f"create_sketch_on_offset_plane({offset_mm}) failed: {result.error}")
    return str(result.data)


async def ensure_saved_part_active(adapter: Any, model_path: Path, label: str) -> None:
    require(await adapter.open_model(str(model_path)), label)


async def build_part() -> None:
    config = load_config()
    adapter = await create_adapter(config)
    await adapter.connect()
    try:
        require(await adapter.create_part(name="yoke_female_from_prompt"), "create_part")

        # ── Sketch1: Base cylinder dia=38.10mm on Top plane (XZ at Y=0) ─────────
        # Identical to yoke_male. Extruded 47.625mm upward (+Y).
        require(await adapter.create_sketch("Top"), "create_sketch BaseCircle")
        require(await adapter.add_circle(0, 0, 19.050), "base circle r=19.050")
        require(await adapter.exit_sketch(), "exit_sketch BaseCircle")
        require(
            await adapter.create_extrusion(ExtrusionParameters(depth=47.625)),
            "BaseExtrude 47.625mm",
        )

        # ── Sketch2: U-slot cut on Front plane (XY at Z=0) ──────────────────────
        # Same 3 arcs + 4 walls as yoke_male, but:
        #   - Outer walls end at Y=0 (not Y=-1.366)
        #   - Bottom closing edge at Y=0 (not Y=-1.366)
        # Read from SW sample: outer walls span Y=0..29.210mm.
        require(await adapter.create_sketch("Front"), "create_sketch USlot")
        # bottom_edge at Y=-0.5 (below the solid base): arc2 dips to Y=0 at (0,0);
        # if bottom_edge were at Y=0 the arc would create a sketch self-intersection
        # at (0,0) making the profile invalid. The cut result is identical since the
        # cylinder base is at Y=0 — anything below is already outside the solid.
        bottom_edge = require(
            await adapter.add_line(-19.050, -0.5, 19.050, -0.5), "bottom edge Y=-0.5"
        )
        right_outer = require(
            await adapter.add_line(19.050, -0.5, 19.050, 29.210), "right outer"
        )
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
        left_outer = require(
            await adapter.add_line(-19.050, 29.210, -19.050, -0.5), "left outer"
        )
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
            "fix right outer",
        )
        require(
            await adapter.add_sketch_constraint(left_outer.data, None, "fix"),
            "fix left outer",
        )
        require(
            await adapter.add_sketch_constraint(arc2.data, xaxis.data, "tangent"),
            "arc2 tangent to X-axis",
        )
        require(
            await adapter.add_sketch_dimension(bottom_edge.data, None, "linear", 38.100),
            "dim bottom edge width 38.100mm",
        )
        require(
            await adapter.add_sketch_dimension(right_inner.data, None, "linear", 10.160),
            "dim right inner 10.160mm",
        )
        require(
            await adapter.add_sketch_dimension(left_inner.data, None, "linear", 10.160),
            "dim left inner 10.160mm",
        )
        require(await adapter.exit_sketch(), "exit_sketch USlot")
        require(
            await adapter.create_cut_extrude(
                ExtrusionParameters(depth=0.0, end_condition="ThroughAll", both_directions=True)
            ),
            "USlot cut through-all-both",
        )

        # ── Sketch8: Arm gap on Right plane (YZ at X=0) ──────────────────────────
        # Right-plane coords: sketch_x=world_Z, sketch_y=world_Y.
        # Female arm gap: Z:+-10.160mm, Y:0..29.145mm (starts at Y=0, not -7.455mm).
        require(await adapter.create_sketch("Right"), "create_sketch ArmGap")
        require(await adapter.add_line(-10.160, 0, 10.160, 0), "gap bottom Y=0")
        require(await adapter.add_line(10.160, 0, 10.160, 29.145), "gap right")
        require(await adapter.add_line(10.160, 29.145, -10.160, 29.145), "gap top")
        require(await adapter.add_line(-10.160, 29.145, -10.160, 0), "gap left")
        require(await adapter.exit_sketch(), "exit_sketch ArmGap")
        require(
            await adapter.create_cut_extrude(
                ExtrusionParameters(depth=0.0, end_condition="ThroughAll", both_directions=True)
            ),
            "ArmGap cut through-all-both",
        )

        # ── Sketch11: Pin bore dia=9.525mm on Front plane (XY at Z=0) ───────────
        # Front-plane coords: sketch_x=world_X, sketch_y=world_Y.
        # Circle at (0, 9.525): cross-pin hole at Y=9.525mm. Identical to yoke_male.
        require(await adapter.create_sketch("Front"), "create_sketch PinBore")
        require(await adapter.add_circle(0, 9.525, 4.7625), "pin bore r=4.7625mm")
        require(await adapter.exit_sketch(), "exit_sketch PinBore")
        require(
            await adapter.create_cut_extrude(
                ExtrusionParameters(depth=0.0, end_condition="ThroughAll", both_directions=True)
            ),
            "PinBore cut through-all-both",
        )

        # ── Sketch12: Bolt holes on top face (Y=47.625mm) ─────────────────────────
        # 4x dia=6.35mm (r=3.175mm) bolt holes on a r=12.700mm bolt circle.
        # Arranged at 0/90/180/270 deg (world X and Z axes) on the top face.
        # Use a reference plane offset from Top by 47.625mm to avoid unreliable
        # coordinate-based face selection after parametric cuts.
        # Sketch plane coords (offset plane parallel to Top): sketch_x=world_X, sketch_y=world_Z.
        # Cut ThroughAll downward (-Y) into the cylinder body.
        create_sketch_on_offset_plane(adapter, 47.625)
        BOLT_R = 12.700  # bolt circle radius
        HOLE_R = 3.175   # hole radius (dia=6.35mm)
        require(await adapter.add_circle(BOLT_R, 0, HOLE_R), "bolt hole +X")
        require(await adapter.add_circle(0, BOLT_R, HOLE_R), "bolt hole +Z")
        require(await adapter.add_circle(-BOLT_R, 0, HOLE_R), "bolt hole -X")
        require(await adapter.add_circle(0, -BOLT_R, HOLE_R), "bolt hole -Z")
        require(await adapter.exit_sketch(), "exit_sketch BoltHoles")
        require(
            await adapter.create_cut_extrude(
                ExtrusionParameters(
                    depth=0.0,
                    end_condition="ThroughAll",
                    both_directions=False,
                    reverse_direction=True,
                )
            ),
            "BoltHoles cut ThroughAll into cylinder",
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
