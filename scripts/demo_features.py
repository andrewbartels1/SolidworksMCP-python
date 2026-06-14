r"""Live end-to-end demo for solid-body feature operations.

Exercises the four feature tools that have no dedicated demo yet:

    create_revolve, create_cut_extrude, add_fillet, add_chamfer

Build sequence
--------------
1. **Annular ring** (revolve) — a rectangular profile on the Front plane
   (inner radius 10 mm, outer radius 30 mm, height 20 mm) revolved 360°
   around the Front-plane Y-axis (via a sketch centerline at x=0).
2. **Radial slot** (cut-extrude) — a small rectangle on the Top plane
   cutting a 5×15 mm radial slot through the ring wall (ThroughAll).
3. **Outer fillet** — ``add_fillet`` rounds the outer-top circular edge.
4. **Inner chamfer** — ``add_chamfer`` chamfers the outer-bottom edge.
5. Save the part and export an isometric PNG to ``out/``.

Edge selection
--------------
Edges are selected by coordinate rather than by topology name ("Edge<1>", etc.)
because topology names vary across SW versions and rebuild order.  The format
``"x,y,z"`` (three floats in *metres*, comma-separated) instructs the adapter
to call ``SelectByID2("", "EDGE", x, y, z, ...)`` which picks the edge closest
to the given point — reliable across all SW versions.

Geometry reference for this demo part:
    - Revolve: inner R=10 mm, outer R=30 mm, height +-10 mm about Y=0
    - Slot cut on Top plane: X in [8, 32] mm, Z in [-2.5, +2.5] mm (all Y)
    - Top outer arc fillet target (90 deg from slot, +Z side):
        X=0.000 m, Y=+0.010 m, Z=+0.030 m
    - Bottom outer arc chamfer target (same +Z side, bottom face):
        X=0.000 m, Y=-0.010 m, Z=+0.030 m

Run with the project virtualenv on a Windows box that has SolidWorks
open::

    .\.venv\Scripts\python.exe scripts\demo_features.py
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from solidworks_mcp.adapters.base import ExtrusionParameters, RevolveParameters  # noqa: E402
from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter  # noqa: E402


def _check(label: str, result) -> None:
    if not result.is_success:
        raise RuntimeError(f"{label} failed: {result.error}")
    print(f"  OK  {label}")


def _check_or_warn(label: str, result) -> bool:
    """Accept success; warn (don't fail) on edge-not-found or API-version errors."""
    if result.is_success:
        print(f"  OK  {label}")
        return True
    err = result.error or ""
    known = (
        "Failed to select edge" in err
        or "FeatureFillet3 returned 0" in err
        or "chamfer" in err.lower()
        or "Type mismatch" in err  # SW version API change for fillet/chamfer
    )
    if known:
        print(f"  --  {label} [known API limitation — noted]")
        print(f"       detail: {err[:160]}")
        return False
    raise RuntimeError(f"{label} failed unexpectedly: {err}")


async def build_demo_part(out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)

    adapter = PyWin32Adapter({})
    print("Connecting to SolidWorks ...")
    await adapter.connect()
    print(f"  Connected: swApp={type(adapter.swApp).__name__}")

    try:
        part = await adapter.create_part()
        _check("create_part", part)
        print(f"  doc: {part.data.name}")

        # ------------------------------------------------------------------
        # Feature 1: annular ring via revolve.
        #
        # Profile: rectangle from (10, -10) to (30, 10) mm entirely on the
        #          +X side of the sketch origin.
        # Axis:    construction centerline from (0, -50) to (0, 50) mm at
        #          x=0 — this becomes the auto-selected revolve axis.
        # Result:  a flat ring, inner-R=10 mm, outer-R=30 mm, height=20 mm.
        # ------------------------------------------------------------------
        sk = await adapter.create_sketch("Front")
        _check("create_sketch Front (revolve profile)", sk)

        # Closed rectangular profile fully on the +X half-plane
        for x1, y1, x2, y2 in [
            (10, -10, 30, -10),  # bottom
            (30, -10, 30,  10),  # right
            (30,  10, 10,  10),  # top
            (10,  10, 10, -10),  # left
        ]:
            _check(f"add_line ({x1},{y1})->({x2},{y2})", await adapter.add_line(x1, y1, x2, y2))

        # Vertical centerline at x=0 — FeatureRevolve2 auto-selects this as the axis
        _check("add_centerline (revolve axis at x=0)", await adapter.add_centerline(0, -50, 0, 50))

        _check("exit_sketch (revolve profile)", await adapter.exit_sketch())

        revolve = await adapter.create_revolve(RevolveParameters(angle=360.0))
        _check("create_revolve 360 deg (annular ring)", revolve)
        print(f"  feature: {revolve.data.name}")

        # ------------------------------------------------------------------
        # Feature 2: radial slot via cut-extrude.
        #
        # Sketch a 5×15 mm rectangle on the Top plane straddling the ring
        # wall (from x=8 to x=32, centred on the outer radius at x=20).
        # ------------------------------------------------------------------
        sk2 = await adapter.create_sketch("Top")
        _check("create_sketch Top (slot profile)", sk2)

        for x1, y1, x2, y2 in [
            (8.0,  -2.5, 32.0, -2.5),
            (32.0, -2.5, 32.0,  2.5),
            (32.0,  2.5,  8.0,  2.5),
            (8.0,   2.5,  8.0, -2.5),
        ]:
            _check(f"add_line slot ({x1},{y1})->({x2},{y2})", await adapter.add_line(x1, y1, x2, y2))

        _check("exit_sketch (slot)", await adapter.exit_sketch())

        cut = await adapter.create_cut_extrude(
            ExtrusionParameters(depth=25.0, end_condition="ThroughAllBoth")
        )
        _check("create_cut_extrude ThroughAll (radial slot)", cut)
        print(f"  feature: {cut.data.name}")

        # ------------------------------------------------------------------
        # Feature 3: fillet — top outer circular arc.
        #
        # Point: +Z side of the outer arc (R=30mm) at the top face (Y=+10mm).
        # Slot is in the +X direction so Z=+0.030 is 90 deg away from any gap.
        # Coordinates: X=0, Y=+0.010 m, Z=+0.030 m
        # ------------------------------------------------------------------
        fillet = await adapter.add_fillet(
            radius=1.0, edge_names=["0.0,0.010,0.030"]
        )
        _check("add_fillet R=1 mm (top outer arc)", fillet)
        if fillet.is_success:
            print(f"  feature: {fillet.data.name}")

        # ------------------------------------------------------------------
        # Feature 4: chamfer — bottom outer circular arc.
        #
        # Point: +Z side of the outer arc (R=30mm) at the bottom face (Y=-10mm).
        # Same +Z direction as fillet but on the opposite Y face.
        # Coordinates: X=0, Y=-0.010 m, Z=+0.030 m
        # ------------------------------------------------------------------
        chamfer = await adapter.add_chamfer(
            distance=0.5, edge_names=["0.0,-0.010,0.030"]
        )
        _check("add_chamfer D=0.5 mm (bottom outer arc)", chamfer)
        if chamfer.is_success:
            print(f"  feature: {chamfer.data.name}")

        # ------------------------------------------------------------------
        # Persist + screenshot.
        # ------------------------------------------------------------------
        part_path = (out_dir / "features_demo.SLDPRT").resolve()
        _check(f"save_file -> {part_path}", await adapter.save_file(str(part_path)))

        img_path = (out_dir / "features_demo_isometric.png").resolve()
        _check(
            f"export_image -> {img_path}",
            await adapter.export_image(
                {
                    "file_path": str(img_path),
                    "format_type": "png",
                    "width": 1600,
                    "height": 1000,
                    "view_orientation": "isometric",
                }
            ),
        )

        return {"part": str(part_path), "screenshot": str(img_path)}

    finally:
        try:
            await adapter.disconnect()
            print("Disconnected.")
        except Exception as exc:  # noqa: BLE001
            print(f"  WARN disconnect: {exc}")


def main() -> int:
    out_dir = REPO_ROOT / "out"
    try:
        artefacts = asyncio.run(build_demo_part(out_dir))
    except Exception:
        traceback.print_exc()
        return 1
    print("\nDemo artefacts:")
    for key, val in artefacts.items():
        print(f"  {key}: {val}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
